import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe_mlx import get_output_dir, transcribe_to_srt


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MLX Transcriber MVP")
        self.root.geometry("720x320")
        self.root.resizable(False, False)

        self.selected_file = ""
        self.output_file = ""
        self.worker_thread = None
        self.event_queue = queue.Queue()

        self.file_var = tk.StringVar(value="선택된 파일이 없습니다.")
        self.status_var = tk.StringVar(value="대기 중")
        self.result_var = tk.StringVar(value="아직 생성된 SRT 파일이 없습니다.")

        self._build_ui()
        self.root.after(100, self._poll_events)

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="선택 파일").pack(anchor="w")
        ttk.Label(
            container,
            textvariable=self.file_var,
            wraplength=660,
            justify="left",
        ).pack(fill="x", pady=(4, 16))

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(0, 16))

        self.select_button = ttk.Button(
            button_row, text="1. 음성/영상 파일 선택", command=self.select_file
        )
        self.select_button.pack(side="left", padx=(0, 8))

        self.start_button = ttk.Button(
            button_row, text="2. 변환 시작", command=self.start_transcription
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.open_button = ttk.Button(
            button_row,
            text="3. 출력 폴더 열기",
            command=self.open_output_folder,
        )
        self.open_button.pack(side="left")

        ttk.Label(container, text="상태").pack(anchor="w")
        ttk.Label(
            container,
            textvariable=self.status_var,
            wraplength=660,
            justify="left",
        ).pack(fill="x", pady=(4, 16))

        ttk.Label(container, text="생성된 SRT").pack(anchor="w")
        ttk.Label(
            container,
            textvariable=self.result_var,
            wraplength=660,
            justify="left",
        ).pack(fill="x", pady=(4, 0))

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
        self.file_var.set(file_path)
        self.status_var.set("파일이 선택되었습니다. 변환을 시작할 수 있습니다.")
        self.result_var.set("아직 생성된 SRT 파일이 없습니다.")

    def start_transcription(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("진행 중", "이미 변환이 진행 중입니다.")
            return

        if not self.selected_file:
            messagebox.showwarning("파일 필요", "먼저 음성 또는 영상 파일을 선택해주세요.")
            return

        self.status_var.set("변환 준비 중...")
        self.result_var.set("변환이 끝나면 여기에 SRT 경로가 표시됩니다.")
        self._set_busy_state(True)

        self.worker_thread = threading.Thread(
            target=self._run_transcription,
            daemon=True,
        )
        self.worker_thread.start()

    def _run_transcription(self):
        def log_callback(message):
            self.event_queue.put(("status", message))

        def progress_callback(done_sec, total_sec, chunk_idx, total_chunks, elapsed_sec):
            progress = (done_sec / total_sec * 100) if total_sec else 0
            message = (
                f"변환 중... {progress:5.1f}% "
                f"({chunk_idx}/{total_chunks} chunk, {int(elapsed_sec)}초 경과)"
            )
            self.event_queue.put(("status", message))

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

            if event_type == "status":
                self.status_var.set(payload)
            elif event_type == "success":
                self.output_file = payload
                self.status_var.set("변환이 완료되었습니다.")
                self.result_var.set(payload)
                self._set_busy_state(False)
            elif event_type == "error":
                self.status_var.set("변환 중 오류가 발생했습니다.")
                self.result_var.set("생성된 SRT 파일이 없습니다.")
                self._set_busy_state(False)
                messagebox.showerror("변환 실패", payload)

        self.root.after(100, self._poll_events)

    def open_output_folder(self):
        target_path = self.output_file or get_output_dir()

        folder_path = (
            target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
        )

        try:
            os.makedirs(folder_path, exist_ok=True)
            subprocess.run(["open", folder_path], check=True)
        except Exception as exc:
            messagebox.showerror("폴더 열기 실패", str(exc))

    def _set_busy_state(self, is_busy):
        button_state = tk.DISABLED if is_busy else tk.NORMAL
        self.select_button.config(state=button_state)
        self.start_button.config(state=button_state)
        self.open_button.config(state=tk.NORMAL)


def main():
    root = tk.Tk()
    TranscriberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
