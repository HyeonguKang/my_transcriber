import mlx_whisper
import sys
import os
import time
import math
import json
import subprocess
import tempfile
from datetime import datetime

if len(sys.argv) < 2:
    print("사용법: python3 transcribe_mlx.py <audio_file>")
    sys.exit(1)

audio_file = os.path.abspath(sys.argv[1])

# ===== 모델 선택 (여기만 바꾸면 됨) =====
# medium이 약 2.5배 더 소요 (1시간 기준: small 4분 / medium 10분)
# medium이 확실히 더 정확하고 품질이 좋음.
# MODEL_SIZE = "small"   # "small" or "medium"
# MODEL_SIZE = "medium"   # "small" or "medium"
# MODEL_SIZE = "turbo"   # "turbo is optimized large"
MODEL_SIZE = "large"  # "turbo is optimized large"

MODEL_REPO = f"mlx-community/whisper-{MODEL_SIZE}-mlx"

# ===== 출력 경로: script/output 폴더 =====
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output_trans")
os.makedirs(output_dir, exist_ok=True)

base_name = os.path.splitext(os.path.basename(audio_file))[0]

# 🔥 타임스탬프 추가
timestamp = datetime.now().strftime("%y%m%d-%H%M%S")

output_file = os.path.join(output_dir, f"{base_name}_mlx_{MODEL_SIZE}_{timestamp}.srt")

print(f"입력 파일: {audio_file}")
print(f"모델: {MODEL_SIZE}")
print(f"출력 파일: {output_file}")

# ===== 설정 =====
LANGUAGE = "ko"
CHUNK_SECONDS = 30

start_time = time.perf_counter()
last_line_length = 0


def format_korean_time(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h:02d}시 {m:02d}분 {s:02d}초"
    elif m > 0:
        return f"{m:02d}분 {s:02d}초"
    else:
        return f"{s:02d}초"


def log(msg):
    global last_line_length

    if last_line_length > 0:
        sys.stdout.write("\n")
        sys.stdout.flush()
        last_line_length = 0

    elapsed = time.perf_counter() - start_time
    print(f"[{format_korean_time(elapsed)}] {msg}")


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


def get_audio_duration(path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_chunk(input_path, start_sec, duration_sec, output_path):
    cmd = [
        "ffmpeg",
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
    subprocess.run(cmd, check=True)


def print_progress(done_sec, total_sec, chunk_idx, total_chunks):
    global last_line_length

    progress = (done_sec / total_sec * 100) if total_sec else 0
    elapsed = time.perf_counter() - start_time

    line = (
        f"진행률: {progress:6.2f}% | "
        f"경과: {format_korean_time(elapsed)} | "
        f"chunk: {chunk_idx}/{total_chunks}"
    )

    padding = " " * max(0, last_line_length - len(line))
    sys.stdout.write("\r" + line + padding)
    sys.stdout.flush()
    last_line_length = len(line)


# ===== 실행 =====
log("오디오 길이 확인 시작")
total_duration = get_audio_duration(audio_file)
log(f"오디오 길이 확인 완료: {format_korean_time(total_duration)}")

total_chunks = math.ceil(total_duration / CHUNK_SECONDS)
log(f"chunk 분할 시작: 총 {total_chunks}개")

srt_index = 1

with tempfile.TemporaryDirectory() as tmpdir, open(
    output_file, "w", encoding="utf-8"
) as f:
    for chunk_idx in range(total_chunks):
        chunk_start = chunk_idx * CHUNK_SECONDS
        chunk_duration = min(CHUNK_SECONDS, total_duration - chunk_start)
        chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx:05d}.wav")

        extract_chunk(audio_file, chunk_start, chunk_duration, chunk_path)

        result = mlx_whisper.transcribe(
            chunk_path,
            path_or_hf_repo=MODEL_REPO,
            language=LANGUAGE,
            word_timestamps=False,
        )

        segments = result.get("segments", [])

        for seg in segments:
            abs_start = chunk_start + float(seg["start"])
            abs_end = chunk_start + float(seg["end"])
            text = seg["text"].strip()

            if not text:
                continue

            f.write(f"{srt_index}\n")
            f.write(f"{format_srt_time(abs_start)} --> {format_srt_time(abs_end)}\n")
            f.write(text + "\n\n")
            srt_index += 1

        done_sec = min(chunk_start + chunk_duration, total_duration)
        print_progress(done_sec, total_duration, chunk_idx + 1, total_chunks)

# 진행줄 마무리
if last_line_length > 0:
    sys.stdout.write("\n")
    sys.stdout.flush()
    last_line_length = 0

log("SRT 생성 완료")

total_elapsed = time.perf_counter() - start_time
print(f"\n총 실행 시간: {format_korean_time(total_elapsed)}")
print(f"SRT 생성 완료: {output_file}")
