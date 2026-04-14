import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe_mlx import (
    build_timestamped_txt_output_path,
    convert_srt_to_txt,
    format_elapsed_time,
    get_output_dir,
    transcribe_to_srt,
)


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MyTranscriber")
        self.root.geometry("760x560")
        self.root.resizable(False, False)

        self.selected_file = ""
        self.output_file = ""
        self.txt_output_file = ""
        self.is_transcribing = False
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
        }

        self._build_ui()
        self._refresh_button_states()
        self.root.after(100, self._poll_events)
        self.root.after(1000, self._tick_status)

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Section.TFrame", padding=18)
        style.configure("Info.TLabel", font=("Helvetica", 12), wraplength=640)

        container = ttk.Frame(self.root, padding=24)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="간단한 자막 변환기",
            font=("Helvetica", 20, "bold"),
        ).pack(anchor="center", pady=(0, 20))

        self.select_button = self._create_action_section(
            container,
            "1. 음성/영상 파일 선택",
            self.select_file,
            self.file_var,
        )
        self.start_button = self._create_action_section(
            container,
            "2. 자막 변환 시작",
            self.handle_second_button,
            self.status_var,
        )
        self.txt_button = self._create_action_section(
            container,
            "3. txt 파일로 변환",
            self.handle_third_button,
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

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="음성 또는 영상 파일 선택",
            filetypes=[
                ("Media Files", "*.mp3 *.wav *.m4a *.aac *.mp4 *.mov *.mkv *.flac"),
                ("All Files", "*.*"),
            ],
        )
        if not file_path:
            return

        self.selected_file = file_path
        self.output_file = ""
        self.txt_output_file = ""
        self.is_transcribing = False
        self.file_var.set(file_path)
        self.status_var.set("파일 선택 완료. 변환 시작 버튼을 눌러주세요.")
        self.txt_result_var.set("변환이 끝나면 txt 파일로 변환할 수 있습니다.")
        self._refresh_button_states()

    def start_transcription(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("진행 중", "이미 변환이 진행 중입니다.")
            return

        if not self.selected_file:
            messagebox.showwarning(
                "파일 필요", "먼저 음성 또는 영상 파일을 선택해주세요."
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
            output_file = transcribe_to_srt(
                self.selected_file,
                model_size="large",
                progress_callback=progress_callback,
                log_callback=log_callback,
            )
            self.event_queue.put(("success", output_file))
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def _poll_events(self):
        while not self.event_queue.empty():
            event_type, payload = self.event_queue.get()

            if event_type == "progress":
                self.last_progress.update(payload)
                self._update_status_text()
            elif event_type == "log":
                if payload.startswith("백엔드:"):
                    self.status_var.set(payload)
            elif event_type == "success":
                self.output_file = payload
                elapsed_sec = 0
                if self.transcription_started_at is not None:
                    elapsed_sec = time.perf_counter() - self.transcription_started_at
                self.is_transcribing = False
                self.status_var.set(
                    f"변환 완료. 총 소요 시간: {format_elapsed_time(elapsed_sec)}"
                )
                self.txt_output_file = ""
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

        self.root.after(100, self._poll_events)

    def _tick_status(self):
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

        self.root.after(1000, self._tick_status)

    def _update_status_text(self):
        progress = self.last_progress["progress_percent"]
        elapsed_text = format_elapsed_time(self.last_progress["elapsed_sec"])

        parts = [f"진행률 {progress:5.1f}%", f"경과 시간 {elapsed_text}"]

        eta_sec = self.last_progress["eta_sec"]
        if eta_sec is not None and eta_sec > 0:
            parts.append(f"예상 남은 시간 {format_elapsed_time(eta_sec)}")

        self.status_var.set(" | ".join(parts))

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

    def _convert_srt_path_to_txt(self, srt_path, output_path=None):
        try:
            return convert_srt_to_txt(srt_path, output_path=output_path)
        except Exception as exc:
            messagebox.showerror("txt 변환 실패", str(exc))
            return None

    def convert_latest_srt_to_txt(self):
        if not self.output_file:
            self.convert_selected_srt_to_txt()
            return

        converted_path = self._convert_srt_path_to_txt(self.output_file)
        if not converted_path:
            return

        self.txt_output_file = converted_path
        self.txt_result_var.set("변환 완료")
        self._refresh_button_states()

    def handle_third_button(self):
        if self.txt_output_file and not self.is_transcribing:
            self._open_target_folder(self.txt_output_file)
            return

        self.convert_latest_srt_to_txt()

    def convert_selected_srt_to_txt(self):
        srt_path = filedialog.askopenfilename(
            title="자막 파일 선택",
            filetypes=[("SRT Files", "*.srt"), ("All Files", "*.*")],
        )
        if not srt_path:
            return

        output_path = build_timestamped_txt_output_path(srt_path)
        converted_path = self._convert_srt_path_to_txt(srt_path, output_path=output_path)
        if not converted_path:
            return

        self.txt_output_file = converted_path
        self.txt_result_var.set("변환 완료")
        self._refresh_button_states()

    def _refresh_button_states(self, is_busy=False):
        self.select_button.config(state=tk.DISABLED if is_busy else tk.NORMAL)
        start_state = tk.NORMAL if self.selected_file and not is_busy else tk.DISABLED
        self.start_button.config(
            state=start_state,
            text=(
                "2. 자막 폴더 열기"
                if self.output_file and not is_busy
                else "2. 자막 변환 시작"
            ),
        )
        txt_state = tk.NORMAL if not is_busy else tk.DISABLED
        self.txt_button.config(state=txt_state)
        self.txt_button.config(
            text=(
                "3. txt 폴더 열기"
                if self.txt_output_file and not is_busy
                else "3. txt 파일로 변환"
            )
        )


def main():
    root = tk.Tk()
    TranscriberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
