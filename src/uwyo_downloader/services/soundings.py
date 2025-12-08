import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import BASE_URL, CONNECT_TIMEOUT, REQUEST_TIMEOUT, USER_AGENT
from ..utils import make_filename


async def fetch_sounding(
    client: httpx.AsyncClient,
    station_id: str | int,
    dt: datetime,
    output_dir: Path,
    cancel_flag,
) -> Optional[Path]:
    if cancel_flag.is_set():
        raise asyncio.CancelledError()

    params = {
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "id": str(station_id),
        "type": "TEXT:LIST",
    }

    resp = await client.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)

    if cancel_flag.is_set():
        raise asyncio.CancelledError()

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
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = make_filename(station_name, dt, output_dir)
    out_path.write_text(text_block, encoding="utf-8")
    return out_path


def build_http_client(concurrency: int) -> httpx.AsyncClient:
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        limits=limits,
    )
