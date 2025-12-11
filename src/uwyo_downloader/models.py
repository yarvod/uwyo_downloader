from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
import csv

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
        # CSV-текст с разделителем ";"
        return parse_csv_payload(self.payload_json)


def parse_csv_payload(text: str) -> dict:
    reader = csv.reader(text.splitlines(), delimiter=";")
    rows_iter = list(reader)
    if not rows_iter:
        return {"columns": [], "rows": [], "raw": text}
    columns = rows_iter[0]
    rows_data = []
    for row in rows_iter[1:]:
        row_dict = {}
        for col, val in zip(columns, row):
            if val == "":
                row_dict[col] = ""
                continue
            try:
                num = float(val)
                row_dict[col] = num
            except ValueError:
                row_dict[col] = val
        rows_data.append(row_dict)
    return {"columns": columns, "rows": rows_data, "raw": text}
