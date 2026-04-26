import math
import os
import tempfile
import time

import transcribe_engine as engine


def transcribe_with_mlx(
    audio_file,
    output_file,
    model_size,
    total_duration,
    progress,
    logger,
):
    engine.ensure_binary_dir_on_path("ffmpeg")
    engine.ensure_binary_dir_on_path("ffprobe")

    try:
        import mlx_whisper
    except Exception as exc:
        raise RuntimeError(
            "MLX 백엔드 초기화에 실패했습니다. Apple Silicon 환경과 MLX 설치 상태를 확인해주세요."
        ) from exc

    engine._patch_mlx_whisper_ffmpeg()

    model_repo = f"mlx-community/whisper-{model_size}-mlx"
    total_chunks = math.ceil(total_duration / engine.CHUNK_SECONDS)
    logger(f"백엔드: MLX ({model_size})")
    logger(f"chunk 분할 시작: 총 {total_chunks}개")

    start_time = time.perf_counter()
    srt_index = 1

    with tempfile.TemporaryDirectory() as tmpdir, open(
        output_file, "w", encoding="utf-8"
    ) as srt_file:
        for chunk_idx in range(total_chunks):
            chunk_start = chunk_idx * engine.CHUNK_SECONDS
            chunk_duration = min(engine.CHUNK_SECONDS, total_duration - chunk_start)
            chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx:05d}.wav")

            engine.extract_chunk(audio_file, chunk_start, chunk_duration, chunk_path)

            result = mlx_whisper.transcribe(
                chunk_path,
                path_or_hf_repo=model_repo,
                language=engine.LANGUAGE,
                word_timestamps=False,
            )

            for seg in result.get("segments", []):
                abs_start = chunk_start + float(seg["start"])
                abs_end = chunk_start + float(seg["end"])
                srt_index = engine._write_srt_segment(
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
