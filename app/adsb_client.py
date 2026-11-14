"""多数据源并发 ADS-B、HexDB 与手机推送客户端。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config import BARK_URL, HGH_LAT, HGH_LON, NOTIFY_WEBHOOK_URL, RADAR_RADIUS_NM, SCHEDULE_MAX_PAGES, USER_AGENT

logger = logging.getLogger(__name__)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


def merge_adsb_records(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """合并多个 ADS-B 数据源的返回结果，按 hex 去重并保留最新鲜的点位。"""
    merged: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for ac in batch:
            hx = str(ac.get("hex") or "").strip().lower()
            if not hx:
                continue
            prev = merged.get(hx)
            if prev is None:
                merged[hx] = dict(ac)
                continue

            # 优先保留 seen 更小（更新鲜）的坐标，同时补齐缺失字段
            prev_seen = float(prev.get("seen") if prev.get("seen") is not None else 9999)
            cur_seen = float(ac.get("seen") if ac.get("seen") is not None else 9999)
            if cur_seen < prev_seen:
                combined = {**prev, **ac}
            else:
                combined = {**ac, **prev}
            merged[hx] = combined
    return list(merged.values())


async def _fetch_single_source(
    client: httpx.AsyncClient, name: str, url: str
) -> tuple[str, list[dict[str, Any]]]:
    resp = await client.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("ac") or payload.get("aircraft") or []
    return name, items


async def fetch_hgh_nearby_multi_source(
    radius_nm: int = RADAR_RADIUS_NM,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """并发从多个免费 ADS-B 源拉取 HGH 周边实时飞机并合并去重。

    Returns:
        (merged_aircraft, ok_source_names, total_sources)
    """
    sources = [
        ("adsb.lol", f"https://api.adsb.lol/v2/point/{HGH_LAT}/{HGH_LON}/{radius_nm}"),
        ("airplanes.live", f"https://api.airplanes.live/v2/point/{HGH_LAT}/{HGH_LON}/{radius_nm}"),
        ("adsb.one", f"https://api.adsb.one/v2/point/{HGH_LAT}/{HGH_LON}/{radius_nm}"),
        ("adsb.fi", f"https://opendata.adsb.fi/api/v2/lat/{HGH_LAT}/lon/{HGH_LON}/dist/{radius_nm}"),
    ]

    async with httpx.AsyncClient(timeout=8.0) as client:
        tasks = [_fetch_single_source(client, name, url) for name, url in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    batches: list[list[dict[str, Any]]] = []
    ok_names: list[str] = []
    for res in results:
        if isinstance(res, Exception):
            logger.debug("ADS-B 数据源请求失败: %s", res)
            continue
        name, items = res
        ok_names.append(name)
        batches.append(items)

    return merge_adsb_records(batches), ok_names, len(sources)


async def fetch_aircraft_by_hexes(hex_list: list[str]) -> list[dict[str, Any]]:
    """批量按 hex 查询关注飞机的当前实时状态（每次最多 30 个）。"""
    if not hex_list:
        return []
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=8.0, headers=DEFAULT_HEADERS) as client:
        for i in range(0, len(hex_list), 30):
            chunk = ",".join(hex_list[i : i + 30])
            url = f"https://api.adsb.lol/v2/hex/{chunk}"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    results.extend(resp.json().get("ac", []) or [])
            except Exception as exc:
                logger.warning("批量查询 hex 失败: %s", exc)
    return results


async def lookup_route_by_callsign(callsign: str) -> tuple[str, str]:
    """优先通过 adsbdb.com 查询呼号航线，查不到时兜底查询 hexdb.io。"""
    cs = callsign.strip().upper()
    if not cs:
        return "", ""
    async with httpx.AsyncClient(timeout=5.0, headers=DEFAULT_HEADERS) as client:
        # 1. adsbdb.com (覆盖率高)
        try:
            resp = await client.get(f"https://api.adsbdb.com/v0/callsign/{cs}")
            if resp.status_code == 200:
                fr = (resp.json().get("response") or {}).get("flightroute") or {}
                ori = (fr.get("origin") or {}).get("iata_code") or (fr.get("origin") or {}).get("icao_code") or ""
                dst = (fr.get("destination") or {}).get("iata_code") or (fr.get("destination") or {}).get("icao_code") or ""
                if ori or dst:
                    return str(ori).upper(), str(dst).upper()
        except Exception:
            pass

        # 2. hexdb.io 兜底
        try:
            resp = await client.get(f"https://hexdb.io/api/v1/route/iata/{cs}")
            if resp.status_code == 200:
                route_str = str(resp.json().get("route", "")).strip()
                if "-" in route_str:
                    parts = [p.strip() for p in route_str.split("-") if p.strip()]
                    if len(parts) >= 2:
                        return parts[0], parts[-1]
        except Exception:
            pass
    return "", ""


async def lookup_aircraft_by_reg(reg: str) -> dict[str, Any] | None:
    """通过注册号查询 hex 编码、机型和社区参考图。"""
    clean_reg = reg.strip().upper()
    if not clean_reg:
        return None
    url = f"https://hexdb.io/api/v2/aircraft?registration={clean_reg}"
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=DEFAULT_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            if not isinstance(data, dict):
                return None
            mode_s = str(data.get("ModeS") or data.get("hex") or "").strip().lower()
            if not mode_s:
                return None
            images = data.get("images") or {}
            img_url = ""
            if isinstance(images, dict):
                img_url = images.get("thumbnail") or images.get("full") or ""
            return {
                "hex": mode_s,
                "reg": clean_reg,
                "model": str(data.get("ICAOTypeCode") or data.get("Type") or ""),
                "airline": str(data.get("RegisteredOwners") or ""),
                "img_url": img_url,
            }
    except Exception as exc:
        logger.warning("查询注册号 %s 失败: %s", clean_reg, exc)
        return None


async def _fetch_airlabs_direction(
    client: httpx.AsyncClient,
    api_key: str,
    query_param: str,
    direction: str,
    max_pages: int = SCHEDULE_MAX_PAGES,
) -> list[dict[str, Any]]:
    url = "https://airlabs.co/api/v9/schedules"
    collected: list[dict[str, Any]] = []
    offset = 0

    for _ in range(max_pages):
        params = {
            query_param: "HGH",
            "api_key": api_key,
            "offset": offset,
            "_fields": (
                "airline_iata,flight_iata,flight_icao,aircraft_icao,status,"
                "dep_iata,dep_time,dep_estimated,dep_actual,"
                "arr_iata,arr_time,arr_estimated,arr_actual"
            ),
        }
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"].get("message") or payload["error"]))
        rows = payload.get("response") or []
        if not rows:
            break
        for r in rows:
            r["direction"] = direction
        collected.extend(rows)

        has_more = (payload.get("request") or {}).get("has_more")
        if has_more is False:
            break
        offset += len(rows)

    return collected


async def fetch_hgh_arrivals_schedule(api_key: str) -> list[dict[str, Any]]:
    """通过 AirLabs Schedules API 并发拉取 HGH 进港与出港排班。"""
    key = api_key.strip()
    if not key:
        return []
    async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS) as client:
        arr_rows, dep_rows = await asyncio.gather(
            _fetch_airlabs_direction(client, key, "arr_iata", "进港"),
            _fetch_airlabs_direction(client, key, "dep_iata", "出港"),
        )
    return arr_rows + dep_rows


async def fetch_hgh_airlabs_live(api_key: str) -> list[dict[str, Any]]:
    """通过 AirLabs /flights bbox 一次性拉取 HGH 周边实时飞机（仅耗 1 次额度）。"""
    key = api_key.strip()
    if not key:
        return []
    url = "https://airlabs.co/api/v9/flights"
    params = {
        "bbox": "28.5,118.5,32.0,122.5",
        "api_key": key,
    }
    async with httpx.AsyncClient(timeout=12.0, headers=DEFAULT_HEADERS) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"].get("message") or payload["error"]))
        return payload.get("response") or []


async def fetch_hgh_metar() -> dict[str, Any] | None:
    """从 AviationWeather 获取 ZSHC (HGH) 实时 METAR 风向与能见度。"""
    url = "https://aviationweather.gov/api/data/metar?ids=ZSHC&format=json"
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=DEFAULT_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0]
    except Exception as exc:
        logger.debug("获取 ZSHC METAR 失败: %s", exc)
    return None


async def send_phone_alert(title: str, body: str) -> None:
    """向手机发送 Bark 或通用 Webhook 提醒。"""
    if not BARK_URL and not NOTIFY_WEBHOOK_URL:
        return
    async with httpx.AsyncClient(timeout=8.0) as client:
        if BARK_URL:
            try:
                base = BARK_URL.rstrip("/")
                await client.post(base, json={"title": title, "body": body, "group": "HGH拍机"})
            except Exception as exc:
                logger.warning("Bark 推送失败: %s", exc)
        if NOTIFY_WEBHOOK_URL:
            try:
                await client.post(NOTIFY_WEBHOOK_URL, json={"title": title, "content": body})
            except Exception as exc:
                logger.warning("Webhook 推送失败: %s", exc)
