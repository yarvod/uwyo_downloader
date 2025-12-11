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

export APP_VERSION
echo "Using version: $APP_VERSION"

DIST_DIR="$ROOT_DIR/dist"
APP_NAME="profile-downloader-${APP_VERSION}"
TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"

# Clean previous artifacts for this version to avoid mv/zip conflicts.
rm -rf "${DIST_DIR:?}/${APP_NAME}" "${DIST_DIR:?}/${APP_NAME}.app" "${DIST_DIR:?}/${APP_NAME}-macos" "${DIST_DIR:?}/${APP_NAME}-macos.app"
rm -f "${ROOT_DIR}/${APP_NAME}-macos.zip"

python - <<'PY'
from pathlib import Path
import os

version = os.environ["APP_VERSION"]
version_file = Path("src/uwyo_downloader/version.py")
version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
print(f"Wrote version {version} to {version_file}")
PY

pyinstaller --noconfirm --windowed \
  --name "profile-downloader-${APP_VERSION}" \
  --paths src \
  --icon assets/icons/app.icns \
  --target-arch "${TARGET_ARCH}" \
  --hidden-import logging.config \
  --add-data "assets/icons/icon-256.png:assets/icons" \
  --add-data "src/uwyo_downloader/db/alembic:uwyo_downloader/db/alembic" \
  main.py

APP_DIR="$DIST_DIR/${APP_NAME}"
APP_BUNDLE="$DIST_DIR/${APP_NAME}.app"

if [[ -d "$APP_BUNDLE" ]]; then
  SRC_PATH="$APP_BUNDLE"
  FINAL_NAME="${APP_NAME}-macos.app"
elif [[ -d "$APP_DIR" ]]; then
  SRC_PATH="$APP_DIR"
  FINAL_NAME="${APP_NAME}-macos"
else
  echo "PyInstaller output not found in dist/ (${APP_NAME} or ${APP_NAME}.app)." >&2
  exit 1
fi

mv "$SRC_PATH" "$DIST_DIR/$FINAL_NAME"

(
  cd "$DIST_DIR"
  ditto -ck --rsrc --sequesterRsrc --keepParent "$FINAL_NAME" "../${APP_NAME}-macos.zip"
)

echo "Artifact: ${APP_NAME}-macos.zip"
