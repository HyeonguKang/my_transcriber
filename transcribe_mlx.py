import json
import math
import multiprocessing
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime

LANGUAGE = "ko"
CHUNK_SECONDS = 30
DEFAULT_MODEL_SIZE = "large"
DEFAULT_COMPUTE_TYPE = "int8"
_BINARY_CACHE = {}


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


def get_log_dir():
    log_dir = os.path.join(get_app_base_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_debug_log_path():
    return os.path.join(get_log_dir(), "app-debug.log")


def append_debug_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(get_debug_log_path(), "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _default_progress(
    done_sec,
    total_sec,
    chunk_idx,
    total_chunks,
    elapsed_sec,
    eta_sec=None,
    avg_chunk_time=None,
):
    progress = (done_sec / total_sec * 100) if total_sec else 0
    line = (
        f"\r진행률: {progress:6.2f}% | "
        f"경과: {format_korean_time(elapsed_sec)} | "
        f"chunk: {chunk_idx}/{total_chunks}"
    )

    if eta_sec is not None and eta_sec > 0:
        line += f" | 남은 예상: {format_elapsed_time(eta_sec)}"

    sys.stdout.write(line)
    sys.stdout.flush()

    if done_sec >= total_sec:
        sys.stdout.write("\n")
        sys.stdout.flush()


def format_elapsed_time(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}시간 {minutes:02d}분 {secs:02d}초"
    if minutes > 0:
        return f"{minutes:02d}분 {secs:02d}초"
    return f"{secs:02d}초"


def _run_command(cmd):
    append_debug_log(f"run_command: {' '.join(cmd)}")
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        append_debug_log(
            "file_not_found: "
            + f"cmd0={cmd[0]} frozen={getattr(sys, 'frozen', False)} "
            + f"executable={sys.executable} cwd={os.getcwd()}"
        )
        raise RuntimeError(
            f"필수 명령어를 찾을 수 없습니다: {cmd[0]}. ffmpeg/ffprobe 설치를 확인해주세요."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        append_debug_log(
            "command_failed: "
            + f"cmd={' '.join(cmd)} returncode={exc.returncode} stderr={stderr}"
        )
        raise RuntimeError(
            f"명령 실행에 실패했습니다: {' '.join(cmd)}"
            + (f"\n{stderr}" if stderr else "")
        ) from exc
    except Exception:
        append_debug_log("run_command_unexpected:\n" + traceback.format_exc())
        raise


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
    module_dir = os.path.dirname(os.path.abspath(__file__))

    candidates.extend(
        [
            os.path.join(module_dir, binary_name),
            os.path.join(module_dir, "..", "Resources", binary_name),
            os.path.join(module_dir, "..", "Frameworks", binary_name),
        ]
    )

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        executable_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend(
            [
                os.path.join(meipass, binary_name),
                os.path.join(executable_dir, binary_name),
                os.path.join(executable_dir, "bin", binary_name),
                os.path.join(executable_dir, "..", "Resources", binary_name),
                os.path.join(executable_dir, "..", "Frameworks", binary_name),
            ]
        )

    candidates.append(binary_name)
    return candidates


def find_binary(binary_name):
    if binary_name in _BINARY_CACHE:
        return _BINARY_CACHE[binary_name]

    for candidate in _candidate_binary_paths(binary_name):
        if os.path.isabs(candidate) and os.path.exists(candidate):
            resolved = os.path.abspath(candidate)
            _BINARY_CACHE[binary_name] = resolved
            append_debug_log(f"find_binary({binary_name}) -> {resolved}")
            return resolved

    resolved = shutil.which(binary_name)
    if resolved:
        _BINARY_CACHE[binary_name] = resolved
        append_debug_log(f"find_binary({binary_name}) -> {resolved}")
        return resolved

    for prefix in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        candidate = os.path.join(prefix, binary_name)
        if os.path.exists(candidate):
            _BINARY_CACHE[binary_name] = candidate
            append_debug_log(f"find_binary({binary_name}) -> {candidate}")
            return candidate

    _BINARY_CACHE[binary_name] = binary_name
    append_debug_log(
        f"find_binary({binary_name}) -> fallback {binary_name}; "
        + f"candidates={_candidate_binary_paths(binary_name)}"
    )
    return binary_name


def ensure_binary_dir_on_path(binary_name):
    binary_path = find_binary(binary_name)
    if not os.path.isabs(binary_path):
        append_debug_log(
            f"ensure_binary_dir_on_path({binary_name}) skipped: unresolved path {binary_path}"
        )
        return binary_path

    binary_dir = os.path.dirname(binary_path)
    current_path = os.environ.get("PATH", "")
    path_entries = [entry for entry in current_path.split(os.pathsep) if entry]

    if binary_dir not in path_entries:
        os.environ["PATH"] = os.pathsep.join([binary_dir, *path_entries])
        append_debug_log(
            f"ensure_binary_dir_on_path({binary_name}) added {binary_dir} to PATH"
        )
    else:
        append_debug_log(
            f"ensure_binary_dir_on_path({binary_name}) already present: {binary_dir}"
        )

    return binary_path


def _patch_mlx_whisper_ffmpeg():
    ffmpeg_binary = ensure_binary_dir_on_path("ffmpeg")

    try:
        import mlx.core as mx
        import numpy as np
        import mlx_whisper.audio as mlx_audio
    except Exception as exc:
        raise RuntimeError(
            "MLX 오디오 로더 초기화에 실패했습니다. MLX 설치 상태를 확인해주세요."
        ) from exc

    if getattr(mlx_audio, "_mytranscriber_ffmpeg_patch", False):
        append_debug_log(
            f"mlx_whisper audio already patched with ffmpeg={ffmpeg_binary}"
        )
        return

    def _bundled_load_audio(
        file: str = None,
        sr: int = mlx_audio.SAMPLE_RATE,
        from_stdin=False,
    ):
        if from_stdin:
            cmd = [ffmpeg_binary, "-i", "pipe:0"]
        else:
            cmd = [ffmpeg_binary, "-nostdin", "-i", file]

        cmd.extend(
            [
                "-threads",
                "0",
                "-f",
                "s16le",
                "-ac",
                "1",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(sr),
                "-",
            ]
        )
        append_debug_log(f"mlx_whisper bundled load_audio uses {ffmpeg_binary}")

        try:
            out = subprocess.run(cmd, capture_output=True, check=True).stdout
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            append_debug_log(
                "mlx_whisper load_audio failed: "
                + f"returncode={exc.returncode} stderr={stderr}"
            )
            raise RuntimeError(f"Failed to load audio: {stderr}") from exc

        return (
            mx.array(np.frombuffer(out, np.int16)).flatten().astype(mx.float32)
            / 32768.0
        )

    mlx_audio.load_audio = _bundled_load_audio
    mlx_audio._mytranscriber_ffmpeg_patch = True
    append_debug_log(f"mlx_whisper audio patched with ffmpeg={ffmpeg_binary}")


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


def detect_backend():
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "mlx"
    return "faster-whisper"


def _normalize_model_name(model_size, backend):
    if backend == "mlx":
        return model_size

    model_map = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large": "large-v3",
        "turbo": "large-v3-turbo",
    }
    return model_map.get(model_size, model_size)


def _build_output_file(audio_file, backend_name, model_size):
    output_dir = get_output_dir()
    base_name = os.path.splitext(os.path.basename(audio_file))[0]
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    return os.path.join(output_dir, f"{base_name}-{timestamp}.srt")


def _parse_srt_blocks(srt_path):
    with open(srt_path, "r", encoding="utf-8") as srt_file:
        raw_content = srt_file.read().strip()

    if not raw_content:
        return []

    blocks = []
    for raw_block in raw_content.split("\n\n"):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue

        time_range = lines[1]
        start_text, end_text = [part.strip() for part in time_range.split("-->")]
        start_sec = _srt_timestamp_to_seconds(start_text)
        end_sec = _srt_timestamp_to_seconds(end_text)
        text_lines = lines[2:]

        if not text_lines:
            continue

        blocks.append(
            {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": "\n".join(text_lines),
            }
        )

    return blocks


def _srt_timestamp_to_seconds(timestamp_text):
    hours, minutes, seconds_ms = timestamp_text.split(":")
    seconds, milliseconds = seconds_ms.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def _format_txt_timeline(seconds, use_hour_format):
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if use_hour_format:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_timestamped_txt_output_path(srt_path):
    srt_path = os.path.abspath(srt_path)
    directory = os.path.dirname(srt_path)
    base_name = os.path.splitext(os.path.basename(srt_path))[0]
    normalized_base_name = re.sub(r"-\d{6}-\d{6}$", "", base_name)
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    return os.path.join(directory, f"{normalized_base_name}-{timestamp}.txt")


def convert_srt_to_txt(srt_path, output_path=None):
    if not srt_path:
        raise ValueError("SRT 파일 경로가 비어 있습니다.")

    srt_path = os.path.abspath(srt_path)
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"SRT 파일을 찾을 수 없습니다: {srt_path}")

    blocks = _parse_srt_blocks(srt_path)
    if not blocks:
        raise ValueError("변환할 자막 내용이 없습니다.")

    total_duration = max(block["end_sec"] for block in blocks)
    use_hour_format = total_duration >= 3600
    if output_path is None:
        output_path = os.path.splitext(srt_path)[0] + ".txt"
    else:
        output_path = os.path.abspath(output_path)

    minute_buckets = {}
    for block in blocks:
        minute_mark = int(block["start_sec"] // 60) * 60
        minute_buckets.setdefault(minute_mark, []).append(block)

    ordered_minutes = sorted(minute_buckets.keys())

    with open(output_path, "w", encoding="utf-8") as txt_file:
        for minute_index, minute_mark in enumerate(ordered_minutes):
            if minute_index > 0:
                txt_file.write("\n")

            txt_file.write(_format_txt_timeline(minute_mark, use_hour_format) + "\n\n")

            for block in minute_buckets[minute_mark]:
                txt_file.write(block["text"] + "\n\n")

    return output_path


def _write_srt_segment(srt_file, index, start_sec, end_sec, text):
    cleaned = text.strip()
    if not cleaned:
        return index

    srt_file.write(f"{index}\n")
    srt_file.write(f"{format_srt_time(start_sec)} --> {format_srt_time(end_sec)}\n")
    srt_file.write(cleaned + "\n\n")
    return index + 1


def _transcribe_with_mlx(
    audio_file,
    output_file,
    model_size,
    total_duration,
    progress,
    logger,
):
    ensure_binary_dir_on_path("ffmpeg")
    ensure_binary_dir_on_path("ffprobe")

    try:
        import mlx_whisper
    except Exception as exc:
        raise RuntimeError(
            "MLX 백엔드 초기화에 실패했습니다. Apple Silicon 환경과 MLX 설치 상태를 확인해주세요."
        ) from exc

    _patch_mlx_whisper_ffmpeg()

    model_repo = f"mlx-community/whisper-{model_size}-mlx"
    total_chunks = math.ceil(total_duration / CHUNK_SECONDS)
    logger(f"백엔드: MLX ({model_size})")
    logger(f"chunk 분할 시작: 총 {total_chunks}개")

    start_time = time.perf_counter()
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
                srt_index = _write_srt_segment(
                    srt_file,
                    srt_index,
                    abs_start,
                    abs_end,
                    seg["text"],
                )

            done_sec = min(chunk_start + chunk_duration, total_duration)
            elapsed = time.perf_counter() - start_time
            completed_chunks = chunk_idx + 1
            avg_chunk_time = elapsed / completed_chunks if completed_chunks else 0
            remaining_chunks = max(0, total_chunks - completed_chunks)
            eta_sec = avg_chunk_time * remaining_chunks
            progress(
                done_sec,
                total_duration,
                completed_chunks,
                total_chunks,
                elapsed,
                eta_sec=eta_sec,
                avg_chunk_time=avg_chunk_time,
            )


def _transcribe_with_faster_whisper(
    audio_file,
    output_file,
    model_size,
    total_duration,
    progress,
    logger,
):
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError(
            "faster-whisper 초기화에 실패했습니다. Intel Mac에서는 faster-whisper 설치 상태를 확인해주세요."
        ) from exc

    runtime_model = _normalize_model_name(model_size, "faster-whisper")
    logger(f"백엔드: faster-whisper ({runtime_model})")
    logger("모델 로딩 시작")

    model = WhisperModel(runtime_model, device="cpu", compute_type=DEFAULT_COMPUTE_TYPE)

    logger("오디오 전사 시작")
    start_time = time.perf_counter()
    segments, info = model.transcribe(audio_file, language=LANGUAGE, vad_filter=True)

    srt_index = 1
    total_chunks = 1
    detected_duration = info.duration or total_duration

    with open(output_file, "w", encoding="utf-8") as srt_file:
        for seg in segments:
            srt_index = _write_srt_segment(
                srt_file,
                srt_index,
                float(seg.start),
                float(seg.end),
                seg.text,
            )

            elapsed = time.perf_counter() - start_time
            done_sec = min(float(seg.end), detected_duration)
            progress_ratio = (done_sec / detected_duration) if detected_duration else 0
            expected_total_sec = (
                elapsed / progress_ratio if progress_ratio > 0 else None
            )
            eta_sec = (
                max(0, expected_total_sec - elapsed)
                if expected_total_sec is not None
                else None
            )
            progress(
                done_sec,
                detected_duration,
                1,
                total_chunks,
                elapsed,
                eta_sec=eta_sec,
                avg_chunk_time=None,
            )

    elapsed = time.perf_counter() - start_time
    progress(
        detected_duration,
        detected_duration,
        1,
        total_chunks,
        elapsed,
        eta_sec=0,
        avg_chunk_time=None,
    )


def transcribe_to_srt(
    audio_file,
    model_size=DEFAULT_MODEL_SIZE,
    progress_callback=None,
    log_callback=None,
):
    if not audio_file:
        raise ValueError("입력 파일 경로가 비어 있습니다.")

    audio_file = os.path.abspath(audio_file)
    if not os.path.isfile(audio_file):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {audio_file}")

    logger = log_callback or _default_logger
    progress = progress_callback or _default_progress

    logger(f"입력 파일: {audio_file}")
    logger("오디오 길이 확인 시작")

    total_duration = get_audio_duration(audio_file)
    if total_duration <= 0:
        raise ValueError("길이가 0초인 파일은 변환할 수 없습니다.")

    logger(f"오디오 길이 확인 완료: {format_korean_time(total_duration)}")

    backend = detect_backend()
    runtime_model = _normalize_model_name(model_size, backend)
    output_file = _build_output_file(audio_file, backend, runtime_model)

    if backend == "mlx":
        _transcribe_with_mlx(
            audio_file,
            output_file,
            model_size,
            total_duration,
            progress,
            logger,
        )
    else:
        _transcribe_with_faster_whisper(
            audio_file,
            output_file,
            model_size,
            total_duration,
            progress,
            logger,
        )

    logger(f"SRT 생성 완료: {output_file}")
    return output_file


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        print("사용법: python3 transcribe_mlx.py <audio_file> [model_size]")
        return 1

    audio_file = argv[0]
    model_size = argv[1] if len(argv) > 1 else DEFAULT_MODEL_SIZE

    try:
        output_file = transcribe_to_srt(audio_file, model_size=model_size)
        print(f"SRT 생성 완료: {output_file}")
        return 0
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
