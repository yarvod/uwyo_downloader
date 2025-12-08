from dataclasses import dataclass
from typing import Optional


@dataclass
class StationInfo:
    stationid: str
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    src: Optional[str] = None

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None
