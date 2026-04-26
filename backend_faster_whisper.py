import os
import platform
import time

import transcribe_engine as engine


def transcribe_with_faster_whisper(
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

    runtime_model = engine._normalize_model_name(model_size, "faster-whisper")
    runtime = engine._select_faster_whisper_runtime(logger)
    logger(
        f"백엔드: faster-whisper ({runtime_model}, "
        + f"{runtime['device']}, {runtime['compute_type']})"
    )
    logger(f"실행 프로필: {runtime['profile_label']}")
    if runtime["device"] == "cpu" and runtime.get("cpu_threads"):
        logger(f"CPU 스레드 수: {runtime['cpu_threads']}")
    logger("모델 로딩 시작")

    if runtime["device"] == "cpu" and platform.machine().lower() == "x86_64":
        os.environ.setdefault("CT2_USE_EXPERIMENTAL_PACKED_GEMM", "1")

    model = WhisperModel(
        runtime_model,
        device=runtime["device"],
        compute_type=runtime["compute_type"],
        cpu_threads=runtime.get("cpu_threads", 0),
    )

    logger("오디오 전사 시작")
    start_time = time.perf_counter()
    segments, info = model.transcribe(audio_file, language=engine.LANGUAGE, vad_filter=True)

    srt_index = 1
    total_chunks = 1
    detected_duration = info.duration or total_duration

    with open(output_file, "w", encoding="utf-8") as srt_file:
        for seg in segments:
            srt_index = engine._write_srt_segment(
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
