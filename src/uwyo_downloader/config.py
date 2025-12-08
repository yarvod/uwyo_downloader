from pathlib import Path

BASE_URL = "https://weather.uwyo.edu/wsgi/sounding"
STATIONS_URL = "https://weather.uwyo.edu/wsgi/sounding_json"
USER_AGENT = "uwyo-sounding-gui/1.1"
DEFAULT_OUTPUT_DIR = Path("profiles")
DEFAULT_CONCURRENCY = 4
REQUEST_TIMEOUT = 30.0
CONNECT_TIMEOUT = 20.0
