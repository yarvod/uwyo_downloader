from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..models import StationInfo


@dataclass
class SoundingPayload:
    station_id: str
    captured_at: datetime
    station_name: str
    payload_json: str  # stored as CSV text
    path: Optional[Path]


_soundings: list[SoundingPayload] = []
_stations: list[StationInfo] = []


def reset_soundings() -> None:
    _soundings.clear()


def add_sounding(payload: SoundingPayload) -> None:
    _soundings.append(payload)


def drain_soundings() -> list[SoundingPayload]:
    drained = list(_soundings)
    _soundings.clear()
    return drained


def reset_stations() -> None:
    _stations.clear()


def set_stations(stations: List[StationInfo]) -> None:
    _stations.clear()
    _stations.extend(stations)


def drain_stations() -> list[StationInfo]:
    drained = list(_stations)
    _stations.clear()
    return drained
