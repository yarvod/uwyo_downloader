import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import httpx
from sqlalchemy.exc import OperationalError
from PySide6.QtCore import QObject, QThread, Signal

from ..config import DEFAULT_CONCURRENCY
from ..db.repositories import SoundingRepository, StationRepository
from ..models import SoundingRecord, StationInfo
from ..services.soundings import SoundingFetchResult, build_http_client, fetch_sounding
from ..services.stations import fetch_stations_for_datetime
from .state import SoundingPayload, add_sounding, reset_soundings, reset_stations, set_stations

logger = logging.getLogger(__name__)


def retry_on_lock(func: Callable, retries: int = 3, delay: float = 0.2):
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


class Thread(QThread):
    def pre_exit(self) -> None:
        """
        Hook that runs before any quit/exit/terminate.
        """
        pass

    def terminate(self) -> None:  # type: ignore[override]
        self.pre_exit()
        super().terminate()
        logger.info(f"[{self.__class__.__name__}.terminate] Terminated")

    def quit(self) -> None:  # type: ignore[override]
        self.pre_exit()
        super().quit()
        logger.info(f"[{self.__class__.__name__}.quit] Quited")

    def exit(self, returnCode: int = 0) -> None:  # type: ignore[override]
        self.pre_exit()
        super().exit(returnCode)
        logger.info(f"[{self.__class__.__name__}.exit] Exited")


class DownloadThread(Thread):
    progress = Signal(int, int)
    done = Signal(bool, str)

    def __init__(
        self,
        station_id: str,
        datetimes: List[datetime],
        output_dir: Path,
        station: StationInfo,
        save_to_disk: bool = True,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        super().__init__()
        self.station_id = station_id
        self.datetimes = datetimes
        self.output_dir = output_dir
        self.concurrency = max(1, concurrency)
        self.station = station
        self.save_to_disk = save_to_disk

    def run(self) -> None:  # noqa: D401
        reset_soundings()
        if not self.datetimes:
            self.done.emit(False, "Нет дат для загрузки")
            return
        total = len(self.datetimes)
        done = 0
        errors: list[str] = []
        fatal: Optional[str] = None
        try:
            with build_http_client(self.concurrency) as client:
                for dt in self.datetimes:
                    try:
                        result = fetch_sounding(
                            client,
                            self.station_id,
                            dt,
                            self.output_dir,
                            save_to_disk=self.save_to_disk,
                        )
                    except httpx.RequestError as exc:
                        fatal = f"Сеть недоступна или соединение разорвано: {exc}"
                        break
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{dt:%Y-%m-%d %H:%M} ошибка: {exc}")
                    else:
                        if isinstance(result, SoundingFetchResult):
                            station_name = result.station_name or self.station.name
                            add_sounding(
                                SoundingPayload(
                                    station_id=self.station_id,
                                    captured_at=dt,
                                    station_name=station_name,
                                    payload_json=result.payload_text,
                                    path=result.path,
                                )
                            )
                        else:
                            errors.append(f"{dt:%Y-%m-%d %H:%M} данных нет (404)")
                    done += 1
                    self.progress.emit(done, total)
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, str(exc))
            return

        if fatal:
            self.done.emit(False, fatal)
        elif errors:
            self.done.emit(False, "; ".join(errors[-3:]))
        else:
            self.done.emit(True, "Готово")

    def pre_exit(self) -> None:
        # keep collected state for persistence in UI thread
        pass


class StationThread(Thread):
    done = Signal(bool, str)

    def __init__(self, dt: datetime) -> None:
        super().__init__()
        self.dt = dt

    def run(self) -> None:  # noqa: D401
        reset_stations()
        try:
            stations = fetch_stations_for_datetime(self.dt)
            set_stations(stations)
            self.done.emit(True, f"Получено {len(stations)} станций")
        except Exception as exc:  # noqa: BLE001
            reset_stations()
            self.done.emit(False, str(exc))

    def pre_exit(self) -> None:
        # keep any fetched data for UI thread to decide
        pass
