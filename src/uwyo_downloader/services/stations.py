from datetime import datetime
from typing import List

import httpx

from ..config import CONNECT_TIMEOUT, REQUEST_TIMEOUT, STATIONS_URL, USER_AGENT
from ..models import StationInfo


def fetch_stations_for_datetime(dt: datetime) -> List[StationInfo]:
    params = {"datetime": dt.strftime("%Y-%m-%d %H:%M:%S")}
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)
    resp = httpx.get(
        STATIONS_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    payload = resp.json()
    stations: List[StationInfo] = []
    fetched_at = datetime.utcnow()
    for raw in payload.get("stations", []):
        stations.append(
            StationInfo(
                stationid=str(raw.get("stationid", "")).strip(),
                name=str(raw.get("name", "")).strip(),
                lat=raw.get("lat"),
                lon=raw.get("lon"),
                src=raw.get("src"),
                updated_at=fetched_at,
            )
        )
    return stations
