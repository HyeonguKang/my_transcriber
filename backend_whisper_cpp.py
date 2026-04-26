import os
import shutil
import tempfile
import time

import transcribe_engine as engine


_WHISPER_CPP_MODEL_MAP = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large": "ggml-large-v3.bin",
    "turbo": "ggml-large-v3-turbo.bin",
}


def _candidate_binary_paths():
    module_dir = os.path.dirname(os.path.abspath(engine.__file__))
    env_binary = os.environ.get("MYTRANSCRIBER_WHISPER_CPP_BIN", "").strip()
    candidates = []

    if env_binary:
        candidates.append(env_binary)

    candidates.extend(
        [
            os.path.join(module_dir, "whisper-cli"),
            os.path.join(module_dir, "bin", "whisper-cli"),
            os.path.join(module_dir, "..", "Resources", "whisper-cli"),
            os.path.join(module_dir, "..", "Frameworks", "whisper-cli"),
        ]
    )
    return candidates


def _find_whisper_cpp_binary():
    for candidate in _candidate_binary_paths():
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    resolved = shutil.which("whisper-cli")
    if resolved:
        return resolved
    raise RuntimeError(
        "Intel AMD GPU용 whisper.cpp 바이너리(`whisper-cli`)를 찾을 수 없습니다."
    )


def _candidate_model_dirs():
    module_dir = os.path.dirname(os.path.abspath(engine.__file__))
    env_dir = os.environ.get("MYTRANSCRIBER_WHISPER_CPP_MODELS", "").strip()
    candidates = []

    if env_dir:
        candidates.append(env_dir)

    candidates.extend(
        [
            os.path.join(module_dir, "models"),
            os.path.join(module_dir, "..", "Resources", "models"),
            os.path.join(engine.get_app_base_dir(), "models"),
        ]
    )
    return candidates


def _find_whisper_cpp_model(model_size):
    model_filename = _WHISPER_CPP_MODEL_MAP.get(model_size, f"ggml-{model_size}.bin")
    for model_dir in _candidate_model_dirs():
        candidate = os.path.join(model_dir, model_filename)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    raise RuntimeError(
        "Intel AMD GPU용 whisper.cpp 모델을 찾을 수 없습니다: "
        + model_filename
    )


def transcribe_with_whisper_cpp(
    audio_file,
    output_file,
    model_size,
    total_duration,
    progress,
    logger,
):
    whisper_cli = _find_whisper_cpp_binary()
    model_path = _find_whisper_cpp_model(model_size)
    logger(f"백엔드: whisper.cpp ({model_size})")
    logger(f"whisper.cpp 바이너리: {whisper_cli}")
    logger(f"whisper.cpp 모델: {model_path}")

    start_time = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "input.wav")
        output_prefix = os.path.join(tmpdir, "transcript")

        engine.extract_chunk(audio_file, 0, total_duration, wav_path)
        engine._run_command(
            [
                whisper_cli,
                "-m",
                model_path,
                "-f",
                wav_path,
                "-l",
                engine.LANGUAGE,
                "-osrt",
                "-of",
                output_prefix,
            ]
        )

        generated_srt = output_prefix + ".srt"
        if not os.path.exists(generated_srt):
            raise RuntimeError("whisper.cpp가 SRT 파일을 생성하지 않았습니다.")

        shutil.copyfile(generated_srt, output_file)

    elapsed = time.perf_counter() - start_time
    progress(
        total_duration,
        total_duration,
        1,
        1,
        elapsed,
        eta_sec=0,
        avg_chunk_time=None,
    )
