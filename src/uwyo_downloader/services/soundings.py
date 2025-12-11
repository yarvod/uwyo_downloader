import csv
import json
import math
from io import StringIO
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import BASE_URL, CONNECT_TIMEOUT, REQUEST_TIMEOUT, USER_AGENT
from ..utils import make_filename

_COLUMN_UNITS = {
    "PRES": "hPa",
    "HGHT": "m",
    "TEMP": "C",
    "DWPT": "C",
    "RELH": "%",
    "MIXR": "g/kg",
    "DRCT": "deg",
    "SKNT": "knot",
    "THTA": "K",
    "THTE": "K",
    "THTV": "K",
    "ABSH": "g/m3",
}


class SoundingFetchResult:
    def __init__(self, path: Path | None, content: str, station_name: str, payload_json: str) -> None:
        self.path = path
        self.content = content
        self.station_name = station_name
        self.payload_json = payload_json


def fetch_sounding(
    client: httpx.Client,
    station_id: str | int,
    dt: datetime,
    output_dir: Path,
    save_to_disk: bool = True,
) -> Optional[SoundingFetchResult]:
    params = {
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "id": str(station_id),
        "type": "TEXT:LIST",
    }

    resp = client.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)

    if resp.status_code == 404:
        return None

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    h3 = soup.find("h3")
    station_name = h3.get_text(strip=True) if h3 else str(station_id)

    pre = soup.find("pre")
    if pre is None:
        raise RuntimeError("Нет блока <pre> с данными")

    text_block = pre.get_text("\n", strip=False)
    payload_dict, csv_text = _parse_sounding(text_block)
    payload_json = json.dumps(payload_dict, ensure_ascii=False)
    out_path: Path | None = None
    if save_to_disk:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = make_filename(station_name, dt, output_dir, suffix=".csv")
        out_path.write_text(csv_text, encoding="utf-8")
    return SoundingFetchResult(out_path, csv_text, station_name, payload_json)


def build_http_client(concurrency: int) -> httpx.Client:
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        limits=limits,
    )


def _parse_sounding_to_json(text_block: str) -> str:
    payload_dict, _ = _parse_sounding(text_block)
    return json.dumps(payload_dict, ensure_ascii=False)


def _compute_absh(relh: Optional[float], temp_c: Optional[float]) -> Optional[float]:
    if relh is None or temp_c is None:
        return None
    try:
        return 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5)) * relh * 2.1674 / (273.15 + temp_c)
    except Exception:
        return None


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except Exception:
        return False


def _rows_to_csv(columns: list[str], rows: list[dict]) -> str:
    buf = StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") if row.get(col, "") is not None else "" for col in columns])
    return buf.getvalue()


def _parse_sounding(text_block: str) -> tuple[dict, str]:
    """
    Разметка текстового профиля в структуру + CSV:
    - читаем заголовок колонок;
    - заполняем значения до первой пустой строки;
    - считаем абсолютную влажность (ABSH) если есть RELH и TEMP;
    - добавляем единицы измерений в заголовки ("PRES,hPa").
    """
    lines = text_block.splitlines()
    columns_raw: list[str] = []
    rows_raw: list[dict[str, object]] = []
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if header_seen:
                break
            continue
        if not header_seen and stripped.startswith("PRES"):
            columns_raw = stripped.split()
            header_seen = True
            continue
        if header_seen:
            parts = stripped.split()
            if len(parts) < len(columns_raw):
                continue
            if not _is_number(parts[0]):
                # пропускаем строку с единицами или заголовок без чисел
                continue
            row: dict[str, object] = {}
            for key, value in zip(columns_raw, parts):
                try:
                    row[key] = float(value)
                except ValueError:
                    row[key] = value
            rows_raw.append(row)

    # абсолютная влажность
    if "RELH" in columns_raw and "TEMP" in columns_raw:
        columns_raw.append("ABSH")
        for row in rows_raw:
            relh = row.get("RELH")
            temp = row.get("TEMP")
            absh = _compute_absh(relh if isinstance(relh, (int, float)) else None, temp if isinstance(temp, (int, float)) else None)
            row["ABSH"] = absh

    label_map: dict[str, str] = {}
    for base in columns_raw:
        unit = _COLUMN_UNITS.get(base)
        label_map[base] = f"{base},{unit}" if unit else base
    columns_labeled = [label_map[c] for c in columns_raw]

    rows_labeled: list[dict[str, object]] = []
    for row in rows_raw:
        labeled_row: dict[str, object] = {}
        for base in columns_raw:
            labeled_row[label_map[base]] = row.get(base)
        rows_labeled.append(labeled_row)

    payload = {
        "columns": columns_labeled,
        "rows": rows_labeled,
        "raw": text_block,
        "units": _COLUMN_UNITS,
    }
    csv_text = _rows_to_csv(columns_labeled, rows_labeled)
    return payload, csv_text
