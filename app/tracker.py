"""后台定时轮询引擎：HGH 周边雷达、关注飞机追踪、航线推测与跑道识别。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app import adsb_client, db, geo
from config import HGH_LAT, HGH_LON, POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))


class SpotterState:
    """保存最近一次雷达快照与内存缓存。"""

    def __init__(self) -> None:
        self.last_updated: str = ""
        self.hgh_nearby: list[dict[str, Any]] = []
        self.watchlist_live: list[dict[str, Any]] = []
        self.route_cache: dict[str, tuple[str, str]] = {}
        self.alerted_recent: dict[str, datetime] = {}
        self.last_error: str = ""


state = SpotterState()


def _parse_alt(raw_alt: Any) -> int:
    if isinstance(raw_alt, (int, float)):
        return int(raw_alt)
    if str(raw_alt).lower() == "ground":
        return 0
    return 99999


async def _resolve_route(callsign: str) -> tuple[str, str]:
    cs = callsign.strip().upper()
    if not cs:
        return "", ""
    if cs in state.route_cache:
        return state.route_cache[cs]
    origin, dest = await adsb_client.lookup_route_by_callsign(cs)
    if origin or dest:
        state.route_cache[cs] = (origin, dest)
    return origin, dest


def _enrich_aircraft(ac: dict[str, Any], watch_item: dict[str, Any] | None, origin: str, dest: str) -> dict[str, Any]:
    lat = ac.get("lat")
    lon = ac.get("lon")
    alt_ft = _parse_alt(ac.get("alt_baro"))
    gs = ac.get("gs")
    track = ac.get("track")
    baro_rate = ac.get("baro_rate") or 0
    callsign = str(ac.get("flight") or "").strip().upper()
    hex_code = str(ac.get("hex") or "").strip().lower()

    dist_km = round(geo.haversine_km(lat, lon, HGH_LAT, HGH_LON), 1) if (lat is not None and lon is not None) else None
    eta_min = (
        geo.estimate_eta_minutes(lat, lon, gs)
        if (lat is not None and lon is not None and (dest in ("HGH", "ZSHC", "") or (dist_km is not None and dist_km < 250)))
        else None
    )

    return {
        "hex": hex_code,
        "reg": (watch_item or {}).get("reg") or str(ac.get("r") or "").upper(),
        "callsign": callsign,
        "model": (watch_item or {}).get("model") or str(ac.get("t") or ""),
        "airline": (watch_item or {}).get("airline") or "",
        "category": (watch_item or {}).get("category") or "普通航班",
        "livery_name": (watch_item or {}).get("livery_name") or "",
        "img_url": (watch_item or {}).get("img_url") or "",
        "is_watched": watch_item is not None,
        "lat": lat,
        "lon": lon,
        "alt_ft": alt_ft,
        "gs_knots": round(gs, 1) if isinstance(gs, (int, float)) else None,
        "track_deg": round(track, 1) if isinstance(track, (int, float)) else None,
        "baro_rate": baro_rate,
        "dist_hgh_km": dist_km,
        "eta_hgh_min": eta_min,
        "origin": origin,
        "dest": dest,
    }


async def run_once() -> None:
    """执行单轮雷达拉取、航线匹配、跑道判定与推送。"""
    watchlist = db.get_active_watchlist()
    nearby_raw, watch_raw = await asyncio.gather(
        adsb_client.fetch_hgh_nearby_aircraft(),
        adsb_client.fetch_aircraft_by_hexes(list(watchlist.keys())),
    )

    merged_by_hex: dict[str, dict[str, Any]] = {}
    for ac in nearby_raw:
        hx = str(ac.get("hex") or "").strip().lower()
        if hx:
            merged_by_hex[hx] = ac
    for ac in watch_raw:
        hx = str(ac.get("hex") or "").strip().lower()
        if hx:
            merged_by_hex[hx] = ac

    nearby_enriched: list[dict[str, Any]] = []
    watch_enriched: list[dict[str, Any]] = []

    for hx, ac in merged_by_hex.items():
        watch_item = watchlist.get(hx)
        callsign = str(ac.get("flight") or "").strip().upper()
        lat = ac.get("lat")
        lon = ac.get("lon")
        alt_ft = _parse_alt(ac.get("alt_baro"))
        gs = float(ac.get("gs") or 0)
        track = float(ac.get("track") or 0)
        baro_rate = float(ac.get("baro_rate") or 0)

        origin, dest = ("", "")
        if watch_item is not None and callsign:
            origin, dest = await _resolve_route(callsign)

        enriched = _enrich_aircraft(ac, watch_item, origin, dest)
        dist_km = enriched["dist_hgh_km"]

        if dist_km is not None and dist_km <= 160:
            nearby_enriched.append(enriched)

        if watch_item is not None:
            watch_enriched.append(enriched)
            if callsign and (origin or dest):
                db.record_flight(hx, callsign, origin, dest, source="hexdb_callsign")

            if lat is not None and lon is not None:
                db.append_track_point(hx, callsign, lat, lon, alt_ft, gs, track, baro_rate)

                # HGH 进近降落跑道自动识别
                if dist_km is not None and dist_km <= 15.0 and alt_ft <= 2500 and baro_rate < -200:
                    recent_pts = db.get_recent_track_points(hx, minutes=15)
                    pts_tuple = [
                        (p["lat"], p["lon"], p["track_deg"], p["alt_ft"])
                        for p in recent_pts
                        if p["alt_ft"] < 5000
                    ]
                    if pts_tuple:
                        rwy_ident, min_alt = geo.identify_hgh_runway(pts_tuple)
                        if rwy_ident not in ("未知", "非进近航向"):
                            db.record_runway_landing(
                                hex_code=hx,
                                reg=watch_item["reg"],
                                callsign=callsign,
                                runway_ident=rwy_ident,
                                min_alt_ft=min_alt,
                                is_daylight=geo.is_hangzhou_daylight(),
                            )

                # 接近 HGH 时触发手机提醒（同架飞机 1 小时内只推一次）
                approaching_hgh = (
                    (dest in ("HGH", "ZSHC") and dist_km is not None and dist_km <= 200)
                    or (dist_km is not None and dist_km <= 100 and baro_rate < -150)
                )
                if approaching_hgh:
                    now_dt = datetime.now(CHINA_TZ)
                    last_alert = state.alerted_recent.get(hx)
                    if last_alert is None or (now_dt - last_alert) > timedelta(hours=1):
                        state.alerted_recent[hx] = now_dt
                        eta_txt = f"约 {enriched['eta_hgh_min']} 分钟后落地" if enriched["eta_hgh_min"] else "正在接近 HGH"
                        title = f"HGH 拍机提醒: {watch_item['livery_name'] or watch_item['reg']}"
                        body = f"{watch_item['reg']} ({watch_item['model']}) 呼号 {callsign or '-'}，距萧山 {dist_km} km，{eta_txt}"
                        await adsb_client.send_phone_alert(title, body)

    # 关注飞机置顶，按距离排序
    nearby_enriched.sort(key=lambda x: (not x["is_watched"], x["dist_hgh_km"] or 9999))
    watch_enriched.sort(key=lambda x: x["dist_hgh_km"] or 9999)

    state.hgh_nearby = nearby_enriched
    state.watchlist_live = watch_enriched
    state.last_updated = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    state.last_error = ""
    db.cleanup_old_track_cache(hours=3)


async def polling_loop() -> None:
    """后台常驻轮询循环。"""
    while True:
        try:
            await run_once()
        except Exception as exc:
            logger.exception("雷达轮询异常: %s", exc)
            state.last_error = str(exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
