from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StationInfo(BaseModel):
    stationid: str = Field(
        validation_alias=AliasChoices("stationid", "id"),
        serialization_alias="id",
    )
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    src: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None


class SoundingRecord(BaseModel):
    record_id: int = Field(alias="id")
    station_id: str
    station_name: Optional[str] = None
    captured_at: datetime
    downloaded_at: datetime
    payload_json: str

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    def parsed_payload(self) -> dict:
        try:
            return json.loads(self.payload_json)
        except Exception:  # noqa: BLE001
            return {"raw": self.payload_json, "columns": [], "rows": []}
