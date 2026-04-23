import os
import multiprocessing
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe_mlx import (
    append_debug_log,
    build_timestamped_txt_output_path,
    convert_srt_to_txt,
    format_elapsed_time,
    get_output_dir,
    transcribe_to_srt,
)

MEDIA_FILE_EXTENSIONS = (
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".mp4",
    ".mov",
    ".mkv",
    ".flac",
    ".webm",
)


class TranscriberApp:
    def __init__(self, root, open_new_window_callback, window_number=1):
        self.root = root
        self.root.title(
            "MyTranscriber" if window_number == 1 else f"MyTranscriber {window_number}"
        )
        self.root.geometry("760x560")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

        self.open_new_window_callback = open_new_window_callback
        self.window_number = window_number
        self.selected_path = ""
        self.selected_path_kind = None
        self.output_file = ""
        self.output_files = []
        self.txt_output_file = ""
        self.txt_output_files = []
        self.is_transcribing = False
        self.is_closed = False
        self.worker_thread = None
        self.event_queue = queue.Queue()

        self.file_var = tk.StringVar(value="선택된 파일이 없습니다.")
        self.status_var = tk.StringVar(
            value="파일을 선택하면 변환을 시작할 수 있습니다."
        )
        self.txt_result_var = tk.StringVar(
            value="버튼 클릭 후 txt 파일로 변환할 자막을 선택할 수 있습니다."
        )

        self.transcription_started_at = None
        self.last_progress = {
            "progress_percent": 0.0,
            "elapsed_sec": 0,
            "eta_sec": None,
            "expected_total_sec": None,
            "avg_chunk_time": None,
            "chunk_idx": 0,
            "total_chunks": 0,
            "current_item_index": None,
            "total_items": None,
            "current_item_name": "",
        }

        self._build_ui()
        self._refresh_button_states()
        self.root.after(100, self._poll_events)
        self.root.after(1000, self._tick_status)

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Section.TFrame", padding=18)
        style.configure("Info.TLabel", font=("Helvetica", 12), wraplength=640)
        style.configure("Choice.TFrame", padding=0)

        container = ttk.Frame(self.root, padding=24)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 20))

        ttk.Label(
            header,
            text="간단한 자막 변환기",
            font=("Helvetica", 20, "bold"),
        ).pack(side="left")

        tk.Button(
            header,
            text="새 창 열기",
            command=self.open_new_window_callback,
            font=("Helvetica", 12, "bold"),
            relief="ridge",
            bd=2,
            padx=12,
            pady=6,
        ).pack(side="right")

        self.select_button = self._create_selection_section(
            container,
            self.file_var,
        )
        self.start_button = self._create_action_section(
            container,
            "2. 자막 변환 시작",
            self.handle_second_button,
            self.status_var,
        )
        self.txt_section = self._create_txt_section(
            container,
            self.txt_result_var,
        )

    def _create_action_section(self, parent, button_text, command, text_variable):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.pack(fill="x", pady=10)

        button = tk.Button(
            section,
            text=button_text,
            command=command,
            font=("Helvetica", 16, "bold"),
            height=2,
            relief="ridge",
            bd=2,
        )
        button.pack(fill="x")

        ttk.Label(
            section,
            textvariable=text_variable,
            style="Info.TLabel",
            justify="left",
        ).pack(fill="x", pady=(12, 0))

        return button

    def _create_selection_section(self, parent, text_variable):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.pack(fill="x", pady=10)

        button_row = ttk.Frame(section, style="Choice.TFrame")
        button_row.pack(fill="x")

        self.select_file_button = tk.Button(
            button_row,
            text="1. 음성/영상 파일 선택",
            command=self.select_file,
            font=("Helvetica", 16, "bold"),
            height=2,
            relief="ridge",
            bd=2,
        )
        self.select_file_button.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.select_directory_button = tk.Button(
            button_row,
            text="1. 음성/영상 디렉토리 선택",
            command=self.select_directory,
            font=("Helvetica", 16, "bold"),
            height=2,
            relief="ridge",
            bd=2,
        )
        self.select_directory_button.pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )

        ttk.Label(
            section,
            textvariable=text_variable,
            style="Info.TLabel",
            justify="left",
        ).pack(fill="x", pady=(12, 0))

        return section

    def _create_txt_section(self, parent, text_variable):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.pack(fill="x", pady=10)

        button_row = ttk.Frame(section, style="Choice.TFrame")
        button_row.pack(fill="x")

        self.txt_file_button = tk.Button(
            button_row,
            text="3. 자막 파일 선택",
            command=self.handle_txt_file_button,
            font=("Helvetica", 16, "bold"),
            height=2,
            relief="ridge",
            bd=2,
        )
        self.txt_file_button.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.txt_directory_button = tk.Button(
            button_row,
            text="3. 자막 디렉토리 선택",
            command=self.handle_txt_directory_button,
            font=("Helvetica", 16, "bold"),
            height=2,
            relief="ridge",
            bd=2,
        )
        self.txt_directory_button.pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )

        ttk.Label(
            section,
            textvariable=text_variable,
            style="Info.TLabel",
            justify="left",
        ).pack(fill="x", pady=(12, 0))

        return section

    def select_file(self):
        selected_path = filedialog.askopenfilename(
            title="음성 또는 영상 파일 선택",
            filetypes=[
                (
                    "Media Files",
                    "*.mp3 *.wav *.m4a *.aac *.mp4 *.mov *.mkv *.flac *.webm",
                ),
                ("All Files", "*.*"),
            ],
        )
        if not selected_path:
            return

        self._set_selected_media_input(selected_path, "file")

    def select_directory(self):
        selected_path = filedialog.askdirectory(title="미디어 디렉토리 선택")
        if not selected_path:
            return

        self._set_selected_media_input(selected_path, "directory")

    def _set_selected_media_input(self, selected_path, selected_kind):
        self.selected_path = selected_path
        self.selected_path_kind = selected_kind
        self.output_file = ""
        self.output_files = []
        self.txt_output_file = ""
        self.txt_output_files = []
        self.is_transcribing = False
        self.file_var.set(selected_path)

        if selected_kind == "directory":
            self.status_var.set("폴더 선택 완료. 변환 시작 버튼을 누르면 폴더 내 파일을 순차 변환합니다.")
        else:
            self.status_var.set("파일 선택 완료. 변환 시작 버튼을 눌러주세요.")
        self.txt_result_var.set("변환이 끝나면 txt 파일로 변환할 수 있습니다.")
        self._refresh_button_states()

    def start_transcription(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("진행 중", "이미 변환이 진행 중입니다.")
            return

        if not self.selected_path:
            messagebox.showwarning(
                "선택 필요", "먼저 음성 파일, 영상 파일, 또는 폴더를 선택해주세요."
            )
            return

        self.transcription_started_at = time.perf_counter()
        self.last_progress = {
            "progress_percent": 0.0,
            "elapsed_sec": 0,
            "eta_sec": None,
            "expected_total_sec": None,
            "avg_chunk_time": None,
            "chunk_idx": 0,
            "total_chunks": 0,
            "current_item_index": None,
            "total_items": None,
            "current_item_name": "",
        }
        self.status_var.set("변환 준비 중...")
        self.is_transcribing = True
        self.txt_result_var.set("SRT 생성 후 txt 변환이 가능합니다.")
        self._refresh_button_states(is_busy=True)

        self.worker_thread = threading.Thread(
            target=self._run_transcription,
            daemon=True,
        )
        self.worker_thread.start()

    def _run_transcription(self):
        append_debug_log(
            f"transcription_start: selected_path={self.selected_path} "
            + f"kind={self.selected_path_kind} pid={os.getpid()}"
        )

        def log_callback(message):
            self.event_queue.put(("log", message))

        def progress_callback(
            done_sec,
            total_sec,
            chunk_idx,
            total_chunks,
            elapsed_sec,
            eta_sec=None,
            avg_chunk_time=None,
        ):
            progress_percent = (done_sec / total_sec * 100) if total_sec else 0
            self.event_queue.put(
                (
                    "progress",
                    {
                        "progress_percent": progress_percent,
                        "elapsed_sec": elapsed_sec,
                        "eta_sec": eta_sec,
                        "expected_total_sec": (
                            elapsed_sec + eta_sec if eta_sec is not None else None
                        ),
                        "avg_chunk_time": avg_chunk_time,
                        "chunk_idx": chunk_idx,
                        "total_chunks": total_chunks,
                    },
                )
            )

        try:
            input_files = self._collect_transcription_inputs(
                self.selected_path,
                self.selected_path_kind,
            )
            if not input_files:
                raise ValueError("변환할 미디어 파일이 없습니다.")

            generated_files = []
            total_items = len(input_files)

            for item_index, input_file in enumerate(input_files, start=1):
                self.event_queue.put(
                    (
                        "item_started",
                        {
                            "current_index": item_index,
                            "total_items": total_items,
                            "item_name": os.path.basename(input_file),
                        },
                    )
                )
                output_file = transcribe_to_srt(
                    input_file,
                    model_size="large",
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                )
                generated_files.append(output_file)

            self.event_queue.put(
                (
                    "success",
                    {
                        "generated_files": generated_files,
                        "processed_count": len(generated_files),
                    },
                )
            )
        except Exception as exc:
            append_debug_log("transcription_exception:\n" + traceback.format_exc())
            self.event_queue.put(("error", str(exc)))

    def _poll_events(self):
        if self.is_closed or not self.root.winfo_exists():
            return

        while not self.event_queue.empty():
            event_type, payload = self.event_queue.get()

            if event_type == "progress":
                self.last_progress.update(payload)
                self._update_status_text()
            elif event_type == "item_started":
                self.last_progress.update(
                    {
                        "progress_percent": 0.0,
                        "elapsed_sec": 0,
                        "eta_sec": None,
                        "expected_total_sec": None,
                        "current_item_index": payload["current_index"],
                        "total_items": payload["total_items"],
                        "current_item_name": payload["item_name"],
                    }
                )
                total_items = payload["total_items"]
                current_index = payload["current_index"]
                item_name = payload["item_name"]
                if total_items > 1:
                    self.status_var.set(
                        f"{current_index}/{total_items} 파일 준비 중: {item_name}"
                    )
                else:
                    self.status_var.set(f"변환 준비 중: {item_name}")
            elif event_type == "log":
                if payload.startswith(("백엔드:", "대기 중:", "대기 완료:")):
                    self.status_var.set(payload)
            elif event_type == "success":
                self.output_files = payload["generated_files"]
                self.output_file = self.output_files[-1] if self.output_files else ""
                elapsed_sec = 0
                if self.transcription_started_at is not None:
                    elapsed_sec = time.perf_counter() - self.transcription_started_at
                self.is_transcribing = False
                processed_count = payload["processed_count"]
                if processed_count > 1:
                    self.status_var.set(
                        f"{processed_count}개 파일 변환 완료. 총 소요 시간: {format_elapsed_time(elapsed_sec)}"
                    )
                else:
                    self.status_var.set(
                        f"변환 완료. 총 소요 시간: {format_elapsed_time(elapsed_sec)}"
                    )
                self.txt_output_file = ""
                self.txt_output_files = []
                self.txt_result_var.set("이제 txt 파일로 변환할 수 있습니다.")
                self.transcription_started_at = None
                self._refresh_button_states(is_busy=False)
            elif event_type == "error":
                self.is_transcribing = False
                self.status_var.set("변환 중 오류가 발생했습니다.")
                self.txt_result_var.set(
                    "버튼 클릭 후 txt 파일로 변환할 자막을 선택할 수 있습니다."
                )
                self.transcription_started_at = None
                self._refresh_button_states(is_busy=False)
                messagebox.showerror("변환 실패", payload)

        if not self.is_closed and self.root.winfo_exists():
            self.root.after(100, self._poll_events)

    def _tick_status(self):
        if self.is_closed or not self.root.winfo_exists():
            return

        if (
            self.transcription_started_at
            and self.worker_thread
            and self.worker_thread.is_alive()
        ):
            elapsed_sec = time.perf_counter() - self.transcription_started_at
            self.last_progress["elapsed_sec"] = elapsed_sec
            expected_total_sec = self.last_progress.get("expected_total_sec")
            if expected_total_sec is not None:
                self.last_progress["eta_sec"] = max(0, expected_total_sec - elapsed_sec)
            self._update_status_text()

        if not self.is_closed and self.root.winfo_exists():
            self.root.after(1000, self._tick_status)

    def _update_status_text(self):
        progress = self.last_progress["progress_percent"]
        elapsed_text = format_elapsed_time(self.last_progress["elapsed_sec"])

        first_line_parts = [f"진행률 {progress:5.1f}%", f"경과 시간 {elapsed_text}"]

        eta_sec = self.last_progress["eta_sec"]
        if eta_sec is not None and eta_sec > 0:
            first_line_parts.append(f"예상 남은 시간 {format_elapsed_time(eta_sec)}")

        total_items = self.last_progress.get("total_items")
        current_item_index = self.last_progress.get("current_item_index")
        current_item_name = self.last_progress.get("current_item_name")
        second_line_parts = []
        if total_items and current_item_index:
            second_line_parts.append(f"{current_item_index}/{total_items}")
            if current_item_name:
                second_line_parts.append(current_item_name)

        status_lines = [" | ".join(first_line_parts)]
        if second_line_parts:
            status_lines.append(" | ".join(second_line_parts))

        self.status_var.set("\n".join(status_lines))

    def _open_target_folder(self, target_path):
        target_path = target_path or get_output_dir()

        folder_path = (
            target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
        )

        try:
            os.makedirs(folder_path, exist_ok=True)
            subprocess.run(["open", folder_path], check=True)
        except Exception as exc:
            messagebox.showerror("폴더 열기 실패", str(exc))

    def handle_second_button(self):
        if self.output_file and not self.is_transcribing:
            self._open_target_folder(self.output_file)
            return

        self.start_transcription()

    def _collect_files_with_extensions(self, directory_path, extensions):
        if not directory_path or not os.path.isdir(directory_path):
            return []

        collected = []
        for entry_name in sorted(os.listdir(directory_path)):
            full_path = os.path.join(directory_path, entry_name)
            if not os.path.isfile(full_path):
                continue

            _, extension = os.path.splitext(entry_name)
            if extension.lower() in extensions:
                collected.append(full_path)

        return collected

    def _collect_transcription_inputs(self, selected_path, selected_kind):
        if selected_kind == "directory":
            return self._collect_files_with_extensions(
                selected_path,
                {ext.lower() for ext in MEDIA_FILE_EXTENSIONS},
            )

        if selected_path:
            return [selected_path]

        return []

    def _convert_srt_path_to_txt(self, srt_path, output_path=None):
        try:
            return convert_srt_to_txt(srt_path, output_path=output_path)
        except Exception as exc:
            messagebox.showerror("txt 변환 실패", str(exc))
            return None

    def handle_txt_file_button(self):
        if self.txt_output_file and not self.is_transcribing:
            self._open_target_folder(self.txt_output_file)
            return

        self.convert_selected_srt_file_to_txt()

    def handle_txt_directory_button(self):
        if self.txt_output_file and not self.is_transcribing:
            self._open_target_folder(self.txt_output_file)
            return

        self.convert_selected_srt_directory_to_txt()

    def convert_selected_srt_file_to_txt(self):
        srt_path = filedialog.askopenfilename(
            title="자막 파일 선택",
            filetypes=[("SRT Files", "*.srt"), ("All Files", "*.*")],
        )
        if not srt_path:
            return
        self._convert_selected_srt_inputs(
            [srt_path],
            force_timestamped_output=False,
        )

    def convert_selected_srt_directory_to_txt(self):
        selected_path = filedialog.askdirectory(title="자막 디렉토리 선택")
        if not selected_path:
            return

        srt_files = self._collect_files_with_extensions(selected_path, {".srt"})
        self._convert_selected_srt_inputs(srt_files, force_timestamped_output=True)

    def _convert_selected_srt_inputs(self, srt_files, force_timestamped_output):
        if not srt_files:
            messagebox.showwarning("파일 없음", "변환할 SRT 파일이 없습니다.")
            return

        converted_paths = []
        total_items = len(srt_files)
        for item_index, srt_path in enumerate(srt_files, start=1):
            self.txt_result_var.set(
                f"{item_index}/{total_items} txt 변환 중: {os.path.basename(srt_path)}"
            )
            output_path = (
                build_timestamped_txt_output_path(srt_path)
                if force_timestamped_output or not self.output_files
                else None
            )
            converted_path = self._convert_srt_path_to_txt(
                srt_path,
                output_path=output_path,
            )
            if not converted_path:
                return
            converted_paths.append(converted_path)

        self.txt_output_files = converted_paths
        self.txt_output_file = converted_paths[-1] if converted_paths else ""
        self.txt_result_var.set(
            "변환 완료" if len(converted_paths) == 1 else f"{len(converted_paths)}개 파일 변환 완료"
        )
        self._refresh_button_states()

    def _refresh_button_states(self, is_busy=False):
        selection_state = tk.DISABLED if is_busy else tk.NORMAL
        self.select_file_button.config(state=selection_state)
        self.select_directory_button.config(state=selection_state)
        start_state = tk.NORMAL if self.selected_path and not is_busy else tk.DISABLED
        self.start_button.config(
            state=start_state,
            text=(
                "2. 자막 폴더 열기"
                if self.output_file and not is_busy
                else "2. 자막 변환 시작"
            ),
        )
        txt_state = tk.NORMAL if not is_busy else tk.DISABLED
        self.txt_file_button.config(
            state=txt_state,
            text=(
                "3. txt 폴더 열기"
                if self.txt_output_file and not is_busy
                else "3. 자막 파일 선택"
            ),
            command=(
                (lambda: self._open_target_folder(self.txt_output_file))
                if self.txt_output_file and not is_busy
                else self.handle_txt_file_button
            ),
        )
        self.txt_directory_button.config(
            state=txt_state,
            text=(
                "3. txt 폴더 열기"
                if self.txt_output_file and not is_busy
                else "3. 자막 디렉토리 선택"
            ),
            command=(
                (lambda: self._open_target_folder(self.txt_output_file))
                if self.txt_output_file and not is_busy
                else self.handle_txt_directory_button
            ),
        )

    def close_window(self):
        if self.worker_thread and self.worker_thread.is_alive():
            should_close = messagebox.askyesno(
                "창 닫기",
                "이 창에서 전사가 진행 중입니다. 그래도 창을 닫을까요?",
            )
            if not should_close:
                return

        self.is_closed = True
        self.root.destroy()


class AppManager:
    def __init__(self, root):
        self.root = root
        self.window_count = 0
        self._bind_new_window_shortcut()

    def create_window(self):
        if self.window_count == 0:
            window = self.root
        else:
            window = tk.Toplevel(self.root)

        self.window_count += 1
        TranscriberApp(
            window,
            open_new_window_callback=self.create_window,
            window_number=self.window_count,
        )
        return window

    def _bind_new_window_shortcut(self):
        self.root.bind_all("<Command-n>", self._handle_new_window_shortcut)
        self.root.bind_all("<Command-N>", self._handle_new_window_shortcut)

    def _handle_new_window_shortcut(self, event):
        self.create_window()
        return "break"


def main():
    multiprocessing.freeze_support()
    append_debug_log(
        f"gui_main_start: pid={os.getpid()} executable={sys.executable if 'sys' in globals() else 'unknown'}"
    )
    root = tk.Tk()
    manager = AppManager(root)
    manager.create_window()
    root.mainloop()


if __name__ == "__main__":
    main()
