#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="MyTranscriber"
ARCH_RAW="$(uname -m)"
RELEASE_VERSION="${RELEASE_VERSION:-}"
BUILD_PROFILE="${MYTRANSCRIBER_BUILD_PROFILE:-}"

if [[ -z "$BUILD_PROFILE" ]]; then
  case "$ARCH_RAW" in
    arm64|aarch64)
      BUILD_PROFILE="arm64"
      ;;
    x86_64)
      BUILD_PROFILE="intel-cpu"
      ;;
    *)
      echo "지원하지 않는 아키텍처입니다: $ARCH_RAW"
      exit 1
      ;;
  esac
fi

case "$BUILD_PROFILE" in
  arm64)
    ARCH_LABEL="arm64"
    ;;
  intel-cpu)
    ARCH_LABEL="intel-cpu"
    ;;
  intel-amd-gpu)
    echo "intel-amd-gpu 빌드 프로필은 아직 whisper.cpp 기반 런타임 번들링이 완료되지 않아 사용할 수 없습니다."
    exit 1
    ;;
  *)
    echo "지원하지 않는 빌드 프로필입니다: $BUILD_PROFILE"
    exit 1
    ;;
esac

if [[ -n "$RELEASE_VERSION" ]]; then
  ZIP_NAME="${APP_NAME}-${RELEASE_VERSION}-macos-${ARCH_LABEL}.zip"
else
  ZIP_NAME="${APP_NAME}-macos-${ARCH_LABEL}.zip"
fi
PYTHON_REQUIREMENTS=("requirements.txt")

if [[ "$ARCH_LABEL" == "arm64" ]]; then
  PYTHON_REQUIREMENTS+=("requirements-apple-silicon.txt")
fi

if [[ ! -d ".venv" ]]; then
  echo ".venv 가 없습니다. 먼저 가상환경을 만들어주세요."
  exit 1
fi

source .venv/bin/activate

python -m pip install --upgrade pip

for requirement_file in "${PYTHON_REQUIREMENTS[@]}"; do
  python -m pip install -r "$requirement_file"
done

python -m pip install -r requirements-build.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg를 찾을 수 없습니다. brew install ffmpeg 후 다시 시도해주세요."
  exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffprobe를 찾을 수 없습니다. brew install ffmpeg 후 다시 시도해주세요."
  exit 1
fi

command rm -rf build dist release .pycache __pycache__

pyinstaller --clean MyTranscriber.spec

mkdir -p release
ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "release/${ZIP_NAME}"

echo ""
echo "빌드 완료:"
echo "  앱:  $SCRIPT_DIR/dist/${APP_NAME}.app"
echo "  압축: $SCRIPT_DIR/release/${ZIP_NAME}"
echo "  빌드 프로필: ${BUILD_PROFILE}"
