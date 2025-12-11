from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from .db.database import SessionLocal, init_database
from .db.repositories import SoundingRepository, StationRepository


class Container:
    def __init__(self) -> None:
        self._ready = False

    def ensure_ready(self) -> None:
        if self._ready:
            return
        init_database()
        self._ready = True

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            raise
        finally:
            session.close()

    def station_repo(self, session: Session) -> StationRepository:
        return StationRepository(session)

    def sounding_repo(self, session: Session) -> SoundingRepository:
        return SoundingRepository(session)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container
