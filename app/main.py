"""FastAPI Web 服务与 API 入口。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import adsb_client, classifier, db, tracker
from config import AIRLABS_API_KEY, BASE_DIR, HGH_IATA, HGH_ICAO, HGH_LAT, HGH_LON, POLL_INTERVAL_SECONDS, RADAR_RADIUS_NM

STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    db.load_watchlist_from_json()
    task = asyncio.create_task(tracker.polling_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="HGH 个人拍机助手", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class WatchlistCreateReq(BaseModel):
    reg: str
    hex: str = ""
    category: str = "彩绘客机"
    airline: str = ""
    model: str = ""
    livery_name: str = ""
    img_url: str = ""


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "airport": f"{HGH_IATA} / {HGH_ICAO}",
        "center": {"lat": HGH_LAT, "lon": HGH_LON},
        "radius_nm": RADAR_RADIUS_NM,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "sources_ok": tracker.state.sources_ok,
        "sources_total": tracker.state.sources_total,
        "last_updated": tracker.state.last_updated,
        "last_error": tracker.state.last_error,
    }


@app.get("/api/radar")
async def get_radar(body_type: str = "", livery: str = "", phase: str = "") -> dict[str, Any]:
    def _match(item: dict[str, Any]) -> bool:
        if body_type and body_type != "全部" and item.get("body_type") != body_type:
            return False
        if livery == "仅彩绘" and not item.get("is_special_livery"):
            return False
        if livery == "非彩绘" and item.get("is_special_livery"):
            return False
        if phase and phase != "全部" and item.get("flight_phase") != phase:
            return False
        return True

    return {
        "last_updated": tracker.state.last_updated,
        "last_error": tracker.state.last_error,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "sources_ok": tracker.state.sources_ok,
        "sources_total": tracker.state.sources_total,
        "watchlist_live": [x for x in tracker.state.watchlist_live if _match(x)],
        "hgh_nearby": [x for x in tracker.state.hgh_nearby if _match(x)],
    }


@app.post("/api/radar/refresh")
async def refresh_radar() -> dict[str, Any]:
    await tracker.run_once()
    return await get_radar()


@app.get("/api/watchlist")
async def list_watchlist() -> list[dict[str, Any]]:
    return list(db.get_active_watchlist().values())


@app.post("/api/watchlist")
async def add_watchlist(req: WatchlistCreateReq) -> dict[str, Any]:
    hex_code = req.hex.strip().lower()
    model = req.model.strip()
    airline = req.airline.strip()
    img_url = req.img_url.strip()

    if not hex_code:
        resolved = await adsb_client.lookup_aircraft_by_reg(req.reg)
        if not resolved:
            raise HTTPException(status_code=400, detail="未能从 hexdb.io 自动查到该注册号的 Hex，请手动填写 hex")
        hex_code = resolved["hex"]
        model = model or resolved["model"]
        airline = airline or resolved["airline"]
        img_url = img_url or resolved["img_url"]

    item = {
        "hex": hex_code,
        "reg": req.reg.strip().upper(),
        "category": req.category,
        "airline": airline,
        "model": model,
        "livery_name": req.livery_name.strip() or req.reg.strip().upper(),
        "img_url": img_url,
    }
    db.upsert_watchlist_item(item)
    return {"ok": True, "item": item}


@app.delete("/api/watchlist/{hex_code}")
async def remove_watchlist(hex_code: str) -> dict[str, Any]:
    db.delete_watchlist_item(hex_code)
    return {"ok": True}


@app.get("/api/predictions")
async def get_predictions(days: int = 14) -> list[dict[str, Any]]:
    return db.get_route_predictions(days=days)


@app.get("/api/runways")
async def get_runways(limit: int = 80) -> dict[str, Any]:
    return db.get_runway_history(limit=limit)


@app.get("/api/schedules")
async def get_schedules(limit: int = 300) -> dict[str, Any]:
    rows = db.get_hgh_schedules(limit=limit)
    for r in rows:
        body_type, is_special = classifier.classify_aircraft(
            r.get("aircraft_icao", ""), r.get("flight_icao", ""), None
        )
        r["body_type"] = body_type
        r["is_special_livery"] = is_special
        r["flight_phase"] = r.get("direction") or ("进港" if r.get("arr_iata") == "HGH" else "出港")
    return {
        "configured": bool(AIRLABS_API_KEY),
        "last_sync": tracker.state.last_schedule_sync.isoformat(timespec="seconds")
        if tracker.state.last_schedule_sync
        else "",
        "rows": rows,
    }


@app.post("/api/schedules/refresh")
async def refresh_schedules() -> dict[str, Any]:
    if not AIRLABS_API_KEY:
        raise HTTPException(status_code=400, detail="未配置 AIRLABS_API_KEY 环境变量")
    cnt = await tracker.sync_schedules_once()
    return {"ok": True, "count": cnt}
