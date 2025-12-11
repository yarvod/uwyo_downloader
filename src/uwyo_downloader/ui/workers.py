import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from sqlalchemy.exc import OperationalError
from PySide6.QtCore import QObject, Signal

from ..config import DEFAULT_CONCURRENCY
from ..db.repositories import SoundingRepository, StationRepository
from ..models import SoundingRecord, StationInfo
from ..services.soundings import SoundingFetchResult, build_http_client, fetch_sounding
from ..services.stations import fetch_stations_for_datetime


class DownloadWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)
    log = Signal(str)

    def __init__(
        self,
        station_id: str,
        datetimes: List[datetime],
        output_dir: Path,
        station: StationInfo,
        session_factory: Callable,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        super().__init__()
        self.station_id = station_id
        self.datetimes = datetimes
        self.output_dir = output_dir
        self.concurrency = max(1, concurrency)
        self.station = station
        self.session_factory = session_factory
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

    @staticmethod
    def _retry_on_lock(func: Callable, retries: int = 3, delay: float = 0.2):
        """
        Run DB action with small retry window to avoid UI hiccups on sqlite locks.
        """
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                return func()
            except OperationalError as exc:
                msg = str(exc).lower()
                if "database is locked" not in msg and "busy" not in msg:
                    raise
                last_exc = exc
                time.sleep(delay * (attempt + 1))
        if last_exc:
            raise last_exc

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        except asyncio.CancelledError:
            self.finished.emit(False, "Отменено")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def _run(self) -> None:
        if not self.datetimes:
            self.finished.emit(False, "Нет дат для загрузки")
            return

        total = len(self.datetimes)
        done = 0
        errors: List[str] = []

        async with build_http_client(self.concurrency) as client:
            sem = asyncio.Semaphore(self.concurrency)

            async def bounded_fetch(dt: datetime):
                if self._cancel_flag.is_set():
                    raise asyncio.CancelledError()
                async with sem:
                    try:
                        result = await fetch_sounding(
                            client,
                            self.station_id,
                            dt,
                            self.output_dir,
                            self._cancel_flag,
                        )
                        return dt, result, None
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        return dt, None, exc

            tasks = [asyncio.create_task(bounded_fetch(dt)) for dt in self.datetimes]

            try:
                for coro in asyncio.as_completed(tasks):
                    if self._cancel_flag.is_set():
                        raise asyncio.CancelledError()
                    dt, result, exc = await coro
                    done += 1
                    if isinstance(result, SoundingFetchResult):
                        station_name = result.station_name or self.station.name
                        try:
                            def _write():
                                with self.session_factory() as session:
                                    station_repo = StationRepository(session)
                                    sounding_repo = SoundingRepository(session)
                                    station_repo.ensure_station(
                                        self.station_id, station_name
                                    )
                                    sounding_repo.upsert_sounding(
                                        station_id=self.station_id,
                                        station_name=station_name,
                                        captured_at=dt,
                                        payload_json=result.payload_json,
                                    )

                            self._retry_on_lock(_write)
                            message = (
                                f"{dt:%Y-%m-%d %H:%M} сохранено -> {result.path.name} (в БД)"
                            )
                            self.log.emit(message)
                        except Exception as repo_exc:  # noqa: BLE001
                            errors.append(f"{dt:%Y-%m-%d %H:%M} база: {repo_exc}")
                            self.log.emit(errors[-1])
                    elif exc:
                        msg = f"{dt:%Y-%m-%d %H:%M} ошибка: {exc}"
                        errors.append(msg)
                        self.log.emit(msg)
                    else:
                        msg = f"{dt:%Y-%m-%d %H:%M} данных нет (404)"
                        self.log.emit(msg)
                    self.progress.emit(done, total, "")
            except asyncio.CancelledError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        if self._cancel_flag.is_set():
            self.finished.emit(False, "Отменено")
        elif errors:
            self.finished.emit(False, "; ".join(errors[-3:]))
        else:
            self.finished.emit(True, "Готово")


class StationListWorker(QObject):
    loaded = Signal(list)
    failed = Signal(str)
    canceled = Signal()
    finished = Signal()
    status = Signal(str)

    def __init__(self, dt: datetime, session_factory: Callable) -> None:
        super().__init__()
        self.dt = dt
        self.session_factory = session_factory
        self._cancel = threading.Event()

    def _check_canceled(self) -> bool:
        if self._cancel.is_set():
            self.canceled.emit()
            return True
        return False

    def run(self) -> None:
        try:
            self.status.emit("Запрашиваем станции у сервера...")
            stations = fetch_stations_for_datetime(self.dt)
            if self._check_canceled():
                return
            self.status.emit(f"Получено {len(stations)} станций, пишем в БД...")
            with self.session_factory() as session:
                repo = StationRepository(session)
                repo.upsert_many(stations)
            if self._check_canceled():
                return
            self.status.emit("Читаем список станций из БД...")
            with self.session_factory() as session:
                repo = StationRepository(session)
                db_stations = repo.list_all()
            if self._check_canceled():
                return
            self.loaded.emit(db_stations)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self._cancel.set()


class SoundingLoadWorker(QObject):
    loaded = Signal(list)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        session_factory: Callable,
        station_query: str | None,
        limit: int = 500,
    ) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.station_query = station_query
        self.limit = limit

    def run(self) -> None:
        try:
            def _read() -> List[SoundingRecord]:
                with self.session_factory() as session:
                    station_ids: list[str] | None = None
                    if self.station_query:
                        station_repo = StationRepository(session)
                        matches = station_repo.search(self.station_query, limit=50)
                        station_ids = [m.stationid for m in matches]
                        if not station_ids:
                            return []
                    repo = SoundingRepository(session)
                    return repo.list(
                        station_ids=station_ids,
                        start=None,
                        end=None,
                        limit=self.limit,
                    )

            records = DownloadWorker._retry_on_lock(_read, retries=5, delay=0.15)
            self.loaded.emit(records)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
