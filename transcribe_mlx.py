"""Compatibility wrapper for the engine-neutral transcription module."""

from transcribe_engine import *  # noqa: F401,F403


if __name__ == "__main__":
    from transcribe_engine import main

    raise SystemExit(main())
