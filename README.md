# MyTranscriber

macOS에서 음성/영상 파일을 SRT 자막으로 변환하는 간단한 GUI 앱입니다.

## 백엔드 동작 방식

- Apple Silicon Mac: `mlx-whisper`
- Intel Mac: `faster-whisper`

앱은 실행 중 Mac 아키텍처를 확인해서 전사 엔진을 자동 선택합니다.

## 개발 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-apple-silicon.txt  # Apple Silicon only
brew install ffmpeg
python gui_app.py
```

## 로컬 앱 빌드

```bash
python3 -m venv .venv
source .venv/bin/activate
./build_macos_app.sh
```

빌드가 끝나면 현재 머신 아키텍처에 맞는 이름으로 압축 파일이 생성됩니다.

- Apple Silicon: `release/MyTranscriber-macos-arm64.zip`
- Intel Mac: `release/MyTranscriber-macos-intel.zip`

## 멀티 아키텍처 배포 전략

- Apple Silicon에서 빌드하면 `arm64` 배포본이 생성됩니다.
- Intel Mac에서 빌드하면 `intel` 배포본이 생성됩니다.
- 두 아키텍처를 모두 배포하려면 보통 두 환경에서 각각 한 번씩 빌드합니다.
- 공통 의존성은 `requirements.txt`, Apple Silicon 전용 의존성은 `requirements-apple-silicon.txt`에 분리되어 있습니다.

## GitHub Actions CI

저장소에는 macOS CI 워크플로도 포함되어 있습니다.

- [`build-macos.yml`](/Users/hyeongu/Documents/my_transcriber/.github/workflows/build-macos.yml:1)
- `macos-14`에서 `arm64`
- `macos-15-intel`에서 `intel`

태그 푸시(`v*`) 또는 수동 실행으로 두 아키텍처 아티팩트를 자동 생성할 수 있습니다.
태그 푸시로 실행되면 빌드 결과 zip 파일이 GitHub Release 자산에도 첨부됩니다.

## 저장 위치

- 생성된 SRT 파일은 `~/Documents/MyTranscriber/output_trans/`에 저장됩니다.

## 배포 메모

- 이 앱은 빌드 시점의 Python 런타임을 함께 포함하므로 사용자는 Python을 따로 설치할 필요가 없습니다.
- `ffmpeg`, `ffprobe`도 빌드 머신에 있으면 앱에 함께 포함되도록 설정했습니다.
- 다른 Mac에 배포할 때는 Gatekeeper 경고가 뜰 수 있으니, 실제 배포 전에는 코드 서명과 notarization을 추가하는 편이 좋습니다.
