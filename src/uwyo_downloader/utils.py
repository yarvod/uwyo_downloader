from datetime import datetime, timedelta
from pathlib import Path
from typing import List


def make_filename(
    station_name: str,
    dt: datetime,
    output_dir: Path,
    suffix: str = ".csv",
) -> Path:
    safe_station = station_name.strip().split(",")[0].strip().lower()
    safe_station = safe_station.replace(" ", "_")
    filename = f"{safe_station}_{dt:%Y_%m_%d_%H}{suffix}"
    return output_dir / filename


def build_datetimes(start: datetime, end: datetime, step_hours: int) -> List[datetime]:
    if step_hours <= 0:
        raise ValueError("Шаг должен быть больше 0 часов")
    if start > end:
        raise ValueError("Начальная дата позже конечной")
    current = start
    result: List[datetime] = []
    while current <= end:
        result.append(current)
        current += timedelta(hours=step_hours)
    return result
