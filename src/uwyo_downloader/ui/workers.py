import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Signal

from ..config import DEFAULT_CONCURRENCY
from ..services.soundings import build_http_client, fetch_sounding
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
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        super().__init__()
        self.station_id = station_id
        self.datetimes = datetimes
        self.output_dir = output_dir
        self.concurrency = max(1, concurrency)
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except asyncio.CancelledError:
            self.finished.emit(False, "Отменено")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))

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
                        path = await fetch_sounding(
                            client,
                            self.station_id,
                            dt,
                            self.output_dir,
                            self._cancel_flag,
                        )
                        return dt, path, None
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        return dt, None, exc

            tasks = [asyncio.create_task(bounded_fetch(dt)) for dt in self.datetimes]

            try:
                for coro in asyncio.as_completed(tasks):
                    if self._cancel_flag.is_set():
                        raise asyncio.CancelledError()
                    dt, path, exc = await coro
                    done += 1
                    if path:
                        message = (
                            f"{dt:%Y-%m-%d %H:%M} сохранено -> {path.name}"
                        )
                        self.log.emit(message)
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
    finished = Signal()

    def __init__(self, dt: datetime) -> None:
        super().__init__()
        self.dt = dt

    def run(self) -> None:
        try:
            stations = fetch_stations_for_datetime(self.dt)
            self.loaded.emit(stations)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
