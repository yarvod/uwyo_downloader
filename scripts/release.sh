#!/usr/bin/env bash
set -euo pipefail

# Release helper: writes the requested version tag into src/uwyo_downloader/version.py,
# commits it, tags the repo, and pushes the branch + tag to origin.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION_INPUT="${1:-${APP_VERSION:-}}"
if [[ -z "$VERSION_INPUT" ]]; then
  echo "Usage: APP_VERSION=v1.2.3 ./scripts/release.sh [v1.2.3]" >&2
  exit 1
fi

if [[ "$VERSION_INPUT" == v* ]]; then
  TAG="$VERSION_INPUT"
else
  TAG="v${VERSION_INPUT}"
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag $TAG already exists. Bailing out." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes before releasing." >&2
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "HEAD" ]]; then
  echo "Detach detected. Check out a branch before releasing." >&2
  exit 1
fi

VERSION_TAG="$TAG" python - <<'PY'
from pathlib import Path
import os

version = os.environ["VERSION_TAG"]
path = Path("src/uwyo_downloader/version.py")
path.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
print(f"Updated {path} -> {version}")
PY

git add src/uwyo_downloader/version.py
if git diff --cached --quiet; then
  echo "No changes to commit after updating version." >&2
  exit 1
fi

git commit -m "Release ${TAG}"
git tag "${TAG}"
git push origin "${BRANCH}"
git push origin "${TAG}"
echo "Pushed release ${TAG} (branch ${BRANCH} + tag)."
