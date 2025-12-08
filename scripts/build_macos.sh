#!/usr/bin/env bash
set -euo pipefail

# Builds PyInstaller bundle for macOS with versioned folder/zip.
# Version priority: APP_VERSION env -> latest git tag -> "dev".

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_VERSION="${APP_VERSION:-}"
if [[ -z "$APP_VERSION" ]]; then
  if git describe --tags --abbrev=0 >/dev/null 2>&1; then
    APP_VERSION="$(git describe --tags --abbrev=0)"
  else
    APP_VERSION="dev"
  fi
fi

echo "Using version: $APP_VERSION"

python scripts/generate_icons.py

python - <<'PY'
from pathlib import Path
import os

version = os.environ["APP_VERSION"]
version_file = Path("src/uwyo_downloader/version.py")
version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
print(f"Wrote version {version} to {version_file}")
PY

pyinstaller --noconfirm --windowed --name "profile-downloader-${APP_VERSION}" --paths src --icon assets/icons/app.icns --add-data "assets/icons/icon-256.png:assets/icons" main.py

cd dist
mv "profile-downloader-${APP_VERSION}" "profile-downloader-${APP_VERSION}-macos"
zip -r "../profile-downloader-${APP_VERSION}-macos.zip" "profile-downloader-${APP_VERSION}-macos"

echo "Artifact: dist/../profile-downloader-${APP_VERSION}-macos.zip"
