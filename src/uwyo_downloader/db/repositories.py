from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models import SoundingRecord, StationInfo
from .orm import Sounding, Station


def _ensure_dt(dt: datetime | str | None) -> datetime:
    if dt is None:
        return datetime.utcnow()
    if isinstance(dt, str):
        return datetime.fromisoformat(dt)
    return dt


class StationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_many(self, stations: Iterable[StationInfo]) -> int:
        rows = []
        for station in stations:
            rows.append(
                {
                    "id": station.stationid,
                    "name": station.name,
                    "lat": station.lat,
                    "lon": station.lon,
                    "src": station.src,
                    "updated_at": _ensure_dt(station.updated_at),
                }
            )
        if not rows:
            return 0

        stmt = insert(Station).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Station.id],
            set_={
                "name": stmt.excluded.name,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "src": stmt.excluded.src,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        self.session.execute(stmt)
        return len(rows)

    def get_by_id(self, station_id: str) -> Optional[StationInfo]:
        row = self.session.get(Station, station_id)
        return StationInfo.model_validate(row, from_attributes=True) if row else None

    def list_all(self) -> List[StationInfo]:
        rows = self.session.scalars(select(Station).order_by(Station.id)).all()
        return [
            StationInfo.model_validate(row, from_attributes=True) for row in rows
        ]

    def search(self, query: str, limit: int = 50) -> List[StationInfo]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Station)
            .where(
                (Station.name.ilike(pattern))
                | (Station.id.ilike(pattern))
            )
            .order_by(Station.name)
            .limit(limit)
        )
        rows = self.session.scalars(stmt).all()
        return [
            StationInfo.model_validate(row, from_attributes=True) for row in rows
        ]

    def ensure_station(self, station_id: str, name: Optional[str] = None) -> StationInfo:
        existing = self.get_by_id(station_id)
        if existing:
            return existing
        info = StationInfo(
            stationid=station_id,
            name=name or station_id,
            updated_at=datetime.utcnow(),
        )
        self.upsert_many([info])
        return info


class SoundingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_sounding(
        self,
        station_id: str,
        station_name: Optional[str],
        captured_at: datetime,
        payload_json: str,
    ) -> int:
        stmt = insert(Sounding).values(
            station_id=station_id,
            station_name=station_name,
            captured_at=_ensure_dt(captured_at),
            payload_json=payload_json,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Sounding.station_id, Sounding.captured_at],
            set_={
                "payload_json": stmt.excluded.payload_json,
                "station_name": stmt.excluded.station_name,
                "downloaded_at": datetime.utcnow(),
            },
        )
        result = self.session.execute(stmt)
        inserted_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        if inserted_id:
            return int(inserted_id)
        # fetch existing id for the unique pair
        existing = self.session.scalar(
            select(Sounding.id).where(
                Sounding.station_id == station_id,
                Sounding.captured_at == _ensure_dt(captured_at),
            )
        )
        return int(existing) if existing is not None else 0

    def _filters(
        self,
        station_ids: Optional[list[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list:
        conditions = []
        if station_ids:
            conditions.append(Sounding.station_id.in_(station_ids))
        if start:
            conditions.append(Sounding.captured_at >= _ensure_dt(start))
        if end:
            conditions.append(Sounding.captured_at <= _ensure_dt(end))
        return conditions

    def list(
        self,
        station_ids: Optional[list[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[SoundingRecord]:
        stmt = (
            select(Sounding)
            .where(*self._filters(station_ids, start, end))
            .order_by(Sounding.captured_at.desc())
            .offset(max(0, offset))
            .limit(limit)
        )
        rows = self.session.scalars(stmt).all()
        return [self._to_record(row) for row in rows]

    def count(
        self,
        station_ids: Optional[list[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        stmt = select(func.count()).select_from(Sounding).where(
            *self._filters(station_ids, start, end)
        )
        return int(self.session.scalar(stmt) or 0)

    def get_by_id(self, record_id: int) -> Optional[SoundingRecord]:
        row = self.session.get(Sounding, record_id)
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: Sounding) -> SoundingRecord:
        return SoundingRecord.model_validate(
            {
                "id": row.id,
                "station_id": row.station_id,
                "station_name": row.station_name,
                "captured_at": row.captured_at,
                "downloaded_at": row.downloaded_at,
                "payload_json": row.payload_json,
            }
        )
