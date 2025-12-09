import os
from pathlib import Path

from .version import __version__

BASE_URL = "https://weather.uwyo.edu/wsgi/sounding"
STATIONS_URL = "https://weather.uwyo.edu/wsgi/sounding_json"
APP_VERSION = os.environ.get("APP_VERSION", __version__)
USER_AGENT = f"uwyo-sounding-gui/{APP_VERSION}"
DEFAULT_OUTPUT_DIR = Path("profiles")
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 30.0
CONNECT_TIMEOUT = 20.0
USE_MAP_SUBPROCESS = os.environ.get("MAP_IN_SUBPROCESS", "1") == "1"
