import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

LANGUAGE = "ko"
CHUNK_SECONDS = 30
DEFAULT_MODEL_SIZE = "large"


def format_korean_time(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h:02d}시 {m:02d}분 {s:02d}초"
    if m > 0:
        return f"{m:02d}분 {s:02d}초"
    return f"{s:02d}초"


def format_srt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))

    if ms == 1000:
        s += 1
        ms = 0
    if s == 60:
        m += 1
        s = 0
    if m == 60:
        h += 1
        m = 0

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _default_logger(message):
    print(message)


def _default_progress(done_sec, total_sec, chunk_idx, total_chunks, elapsed_sec):
    progress = (done_sec / total_sec * 100) if total_sec else 0
    line = (
        f"\r진행률: {progress:6.2f}% | "
        f"경과: {format_korean_time(elapsed_sec)} | "
        f"chunk: {chunk_idx}/{total_chunks}"
    )
    sys.stdout.write(line)
    sys.stdout.flush()

    if done_sec >= total_sec:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _run_command(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"필수 명령어를 찾을 수 없습니다: {cmd[0]}. ffmpeg/ffprobe 설치를 확인해주세요."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise RuntimeError(
            f"명령 실행에 실패했습니다: {' '.join(cmd)}"
            + (f"\n{stderr}" if stderr else "")
        ) from exc


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.expanduser("~/Documents/MyTranscriber")
    return os.path.dirname(os.path.abspath(__file__))


def get_output_dir():
    output_dir = os.path.join(get_app_base_dir(), "output_trans")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _candidate_binary_paths(binary_name):
    candidates = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        executable_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend(
            [
                os.path.join(meipass, binary_name),
                os.path.join(executable_dir, binary_name),
                os.path.join(executable_dir, "bin", binary_name),
                os.path.join(executable_dir, "..", "Resources", binary_name),
            ]
        )

    candidates.append(binary_name)
    return candidates


def find_binary(binary_name):
    for candidate in _candidate_binary_paths(binary_name):
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return os.path.abspath(candidate)
        if os.path.sep not in candidate:
            return candidate
    return binary_name


def get_audio_duration(path):
    result = _run_command(
        [
            find_binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ]
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_chunk(input_path, start_sec, duration_sec, output_path):
    _run_command(
        [
            find_binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-ss",
            str(start_sec),
            "-t",
            str(duration_sec),
            "-i",
            input_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            output_path,
        ]
    )


def transcribe_to_srt(
    audio_file,
    model_size=DEFAULT_MODEL_SIZE,
    progress_callback=None,
    log_callback=None,
):
    try:
        import mlx_whisper
    except Exception as exc:
        raise RuntimeError(
            "mlx_whisper 초기화에 실패했습니다. Apple Silicon 환경과 MLX 설치 상태를 확인해주세요."
        ) from exc

    if not audio_file:
        raise ValueError("입력 파일 경로가 비어 있습니다.")

    audio_file = os.path.abspath(audio_file)
    if not os.path.isfile(audio_file):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {audio_file}")

    model_repo = f"mlx-community/whisper-{model_size}-mlx"
    output_dir = get_output_dir()

    base_name = os.path.splitext(os.path.basename(audio_file))[0]
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    output_file = os.path.join(
        output_dir, f"{base_name}_mlx_{model_size}_{timestamp}.srt"
    )

    logger = log_callback or _default_logger
    progress = progress_callback or _default_progress
    start_time = time.perf_counter()

    logger(f"입력 파일: {audio_file}")
    logger(f"모델: {model_size}")
    logger("오디오 길이 확인 시작")

    total_duration = get_audio_duration(audio_file)
    if total_duration <= 0:
        raise ValueError("길이가 0초인 파일은 변환할 수 없습니다.")

    logger(f"오디오 길이 확인 완료: {format_korean_time(total_duration)}")

    total_chunks = math.ceil(total_duration / CHUNK_SECONDS)
    logger(f"chunk 분할 시작: 총 {total_chunks}개")

    srt_index = 1

    with tempfile.TemporaryDirectory() as tmpdir, open(
        output_file, "w", encoding="utf-8"
    ) as srt_file:
        for chunk_idx in range(total_chunks):
            chunk_start = chunk_idx * CHUNK_SECONDS
            chunk_duration = min(CHUNK_SECONDS, total_duration - chunk_start)
            chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx:05d}.wav")

            extract_chunk(audio_file, chunk_start, chunk_duration, chunk_path)

            result = mlx_whisper.transcribe(
                chunk_path,
                path_or_hf_repo=model_repo,
                language=LANGUAGE,
                word_timestamps=False,
            )

            for seg in result.get("segments", []):
                abs_start = chunk_start + float(seg["start"])
                abs_end = chunk_start + float(seg["end"])
                text = seg["text"].strip()

                if not text:
                    continue

                srt_file.write(f"{srt_index}\n")
                srt_file.write(
                    f"{format_srt_time(abs_start)} --> {format_srt_time(abs_end)}\n"
                )
                srt_file.write(text + "\n\n")
                srt_index += 1

            done_sec = min(chunk_start + chunk_duration, total_duration)
            elapsed = time.perf_counter() - start_time
            progress(done_sec, total_duration, chunk_idx + 1, total_chunks, elapsed)

    total_elapsed = time.perf_counter() - start_time
    logger(f"SRT 생성 완료: {output_file}")
    logger(f"총 실행 시간: {format_korean_time(total_elapsed)}")

    return output_file


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        print("사용법: python3 transcribe_mlx.py <audio_file> [model_size]")
        return 1

    audio_file = argv[0]
    model_size = argv[1] if len(argv) > 1 else DEFAULT_MODEL_SIZE

    try:
        transcribe_to_srt(audio_file, model_size=model_size)
        return 0
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
