#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d ".venv" ]]; then
  echo ".venv 가 없습니다. 먼저 가상환경을 만들어주세요."
  exit 1
fi

source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg를 찾을 수 없습니다. `brew install ffmpeg` 후 다시 시도해주세요."
  exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffprobe를 찾을 수 없습니다. `brew install ffmpeg` 후 다시 시도해주세요."
  exit 1
fi

command rm -rf build dist
pyinstaller --clean MyTranscriber.spec

echo ""
echo "빌드 완료:"
echo "  $SCRIPT_DIR/dist/MyTranscriber.app"
