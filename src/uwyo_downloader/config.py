import os
import sys
from pathlib import Path

from .version import __version__

BASE_URL = "https://weather.uwyo.edu/wsgi/sounding"
STATIONS_URL = "https://weather.uwyo.edu/wsgi/sounding_json"
APP_VERSION = os.environ.get("APP_VERSION", __version__)
USER_AGENT = f"uwyo-sounding-gui/{APP_VERSION}"
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 30.0
CONNECT_TIMEOUT = 20.0


def _app_root() -> Path:
    """
    Корневая папка приложения:
    - в собранном бинаре — рядом с исполняемым файлом;
    - в разработке — корень репозитория.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:  # noqa: BLE001
        return Path.cwd()


def _user_data_dir() -> Path:
    home = Path.home()
    return home / ".local" / "share" / "uwyo-sounding"


def _resolve_app_data_dir() -> Path:
    # 1) explicit override
    custom = os.environ.get("UWYO_APP_DATA")
    if custom:
        return Path(custom).expanduser()

    # 2) next to executable (dev/bundle)
    candidate = _app_root()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception:
        pass

    # 3) fallback to user data dir
    fallback = _user_data_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


APP_DATA_DIR = _resolve_app_data_dir()
DEFAULT_OUTPUT_DIR = Path(
    os.environ.get("UWYO_OUTPUT_DIR", APP_DATA_DIR / "profiles")
).expanduser()
DATABASE_PATH = APP_DATA_DIR / "uwyo.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
