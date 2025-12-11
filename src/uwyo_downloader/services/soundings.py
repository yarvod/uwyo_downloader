import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import BASE_URL, CONNECT_TIMEOUT, REQUEST_TIMEOUT, USER_AGENT
from ..utils import make_filename


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
    out_path: Path | None = None
    if save_to_disk:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = make_filename(station_name, dt, output_dir)
        out_path.write_text(text_block, encoding="utf-8")
    payload_json = _parse_sounding_to_json(text_block)
    return SoundingFetchResult(out_path, text_block, station_name, payload_json)


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
    """
    Простая разметка текстового профиля в JSON: ищем строку заголовка столбцов и читаем
    значения до первой пустой строки. Формат UWYO: множественные пробелы между значениями.
    """
    lines = text_block.splitlines()
    columns: list[str] = []
    rows: list[dict] = []
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if header_seen:
                break
            continue
        if not header_seen and stripped.startswith("PRES"):
            columns = stripped.split()
            header_seen = True
            continue
        if header_seen:
            parts = stripped.split()
            if len(parts) < len(columns):
                continue
            row: dict[str, object] = {}
            for key, value in zip(columns, parts):
                try:
                    row[key] = float(value)
                except ValueError:
                    row[key] = value
            rows.append(row)
    payload = {"columns": columns, "rows": rows, "raw": text_block}
    return json.dumps(payload, ensure_ascii=False)
