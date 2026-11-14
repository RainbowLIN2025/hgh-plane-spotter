"""异步 ADS-B、HexDB 与手机推送客户端。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import BARK_URL, HGH_LAT, HGH_LON, NOTIFY_WEBHOOK_URL, RADAR_RADIUS_NM

logger = logging.getLogger(__name__)


async def fetch_hgh_nearby_aircraft(radius_nm: int = RADAR_RADIUS_NM) -> list[dict[str, Any]]:
    """查询 HGH 周边指定海里范围内的实时飞机。"""
    url = f"https://api.adsb.lol/v2/point/{HGH_LAT}/{HGH_LON}/{radius_nm}"
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("ac", []) or []


async def fetch_aircraft_by_hexes(hex_list: list[str]) -> list[dict[str, Any]]:
    """批量按 hex 查询关注飞机的当前实时状态（每次最多 30 个）。"""
    if not hex_list:
        return []
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=12.0) as client:
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
    """通过 hexdb.io 查询呼号对应的起降机场代码。"""
    cs = callsign.strip().upper()
    if not cs:
        return "", ""
    url = f"https://hexdb.io/api/v1/route/iata/{cs}"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return "", ""
            data = resp.json()
            route_str = str(data.get("route", "")).strip()
            if "-" in route_str:
                parts = [p.strip() for p in route_str.split("-") if p.strip()]
                if len(parts) >= 2:
                    return parts[0], parts[-1]
    except Exception:
        return "", ""
    return "", ""


async def lookup_aircraft_by_reg(reg: str) -> dict[str, Any] | None:
    """通过注册号查询 hex 编码、机型和社区参考图。"""
    clean_reg = reg.strip().upper()
    if not clean_reg:
        return None
    url = f"https://hexdb.io/api/v2/aircraft?registration={clean_reg}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
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
