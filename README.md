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
brew install ffmpeg
python gui_app.py
```

## macOS 앱으로 빌드

최종 사용자가 Python을 설치하지 않아도 되게 하려면 `.app`으로 묶어 배포하면 됩니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
./build_macos_app.sh
```

빌드가 끝나면 아래 앱이 생성됩니다.

```bash
dist/MyTranscriber.app
```

## 아키텍처 배포 메모

- Apple Silicon에서 빌드한 앱은 기본적으로 Apple Silicon용입니다.
- Intel Mac에서 배포하려면 Intel Mac에서 별도로 빌드하는 것이 가장 안전합니다.
- 즉, 배포용 앱은 보통 `macos-arm64`, `macos-intel` 두 개를 따로 만드는 방식이 현실적입니다.

## 저장 위치

- 생성된 SRT 파일은 `~/Documents/MyTranscriber/output_trans/`에 저장됩니다.

## 배포 메모

- 이 앱은 빌드 시점의 Python 런타임을 함께 포함하므로 사용자는 Python을 따로 설치할 필요가 없습니다.
- `ffmpeg`, `ffprobe`도 빌드 머신에 있으면 앱에 함께 포함되도록 설정했습니다.
- 다른 Mac에 배포할 때는 Gatekeeper 경고가 뜰 수 있으니, 실제 배포 전에는 코드 서명과 notarization을 추가하는 편이 좋습니다.
