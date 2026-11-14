"""SQLite 数据库初始化与读写操作。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from config import DB_PATH, WATCHLIST_PATH

CHINA_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


@contextmanager
def get_conn(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """获取 SQLite 连接并自动提交/关闭。"""
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    """初始化四张核心数据表。"""
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS aircraft_watchlist (
                hex TEXT PRIMARY KEY,
                reg TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '彩绘客机',
                airline TEXT DEFAULT '',
                model TEXT DEFAULT '',
                livery_name TEXT DEFAULT '',
                img_url TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS flight_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hex TEXT NOT NULL,
                callsign TEXT DEFAULT '',
                origin_icao TEXT DEFAULT '',
                dest_icao TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'adsb_infer',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                weekday INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_flight_hex_time
                ON flight_records(hex, last_seen_at DESC);

            CREATE TABLE IF NOT EXISTS runway_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hex TEXT NOT NULL,
                reg TEXT DEFAULT '',
                callsign TEXT DEFAULT '',
                airport_icao TEXT NOT NULL DEFAULT 'ZSHC',
                runway_ident TEXT NOT NULL,
                min_alt_ft INTEGER NOT NULL,
                landed_at TEXT NOT NULL,
                is_daylight INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_runway_time
                ON runway_logs(landed_at DESC);

            CREATE TABLE IF NOT EXISTS observed_aircraft (
                hex TEXT PRIMARY KEY,
                reg TEXT DEFAULT '',
                model TEXT DEFAULT '',
                callsign TEXT DEFAULT '',
                body_type TEXT DEFAULT '其他',
                is_special_livery INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hgh_schedules (
                flight_key TEXT PRIMARY KEY,
                direction TEXT DEFAULT '进港',
                flight_iata TEXT DEFAULT '',
                flight_icao TEXT DEFAULT '',
                airline_iata TEXT DEFAULT '',
                aircraft_icao TEXT DEFAULT '',
                status TEXT DEFAULT '',
                dep_iata TEXT DEFAULT '',
                dep_time TEXT DEFAULT '',
                dep_estimated TEXT DEFAULT '',
                dep_actual TEXT DEFAULT '',
                arr_iata TEXT DEFAULT 'HGH',
                arr_time TEXT DEFAULT '',
                arr_estimated TEXT DEFAULT '',
                arr_actual TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS adsb_track_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hex TEXT NOT NULL,
                callsign TEXT DEFAULT '',
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                alt_ft INTEGER NOT NULL,
                gs_knots REAL DEFAULT 0,
                track_deg REAL DEFAULT 0,
                baro_rate REAL DEFAULT 0,
                seen_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_track_hex_time
                ON adsb_track_cache(hex, seen_at DESC);
            """
        )
        # 兼容已有数据库：补充 direction 列
        cols = {row[1] for row in conn.execute("PRAGMA table_info(hgh_schedules)").fetchall()}
        if "direction" not in cols:
            conn.execute("ALTER TABLE hgh_schedules ADD COLUMN direction TEXT DEFAULT '进港'")


def load_watchlist_from_json(db_path: Path = DB_PATH, json_path: Path = WATCHLIST_PATH) -> int:
    """将 watchlist.json 中的预设飞机同步到 SQLite。"""
    if not json_path.exists():
        return 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return 0

    now = _now_iso()
    count = 0
    with get_conn(db_path) as conn:
        for item in data:
            hex_code = str(item.get("hex", "")).strip().lower()
            reg = str(item.get("reg", "")).strip().upper()
            if not hex_code or not reg:
                continue
            conn.execute(
                """
                INSERT INTO aircraft_watchlist (
                    hex, reg, category, airline, model, livery_name, img_url, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hex) DO UPDATE SET
                    reg=excluded.reg,
                    category=excluded.category,
                    airline=excluded.airline,
                    model=excluded.model,
                    livery_name=excluded.livery_name,
                    img_url=excluded.img_url,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (
                    hex_code,
                    reg,
                    item.get("category", "彩绘客机"),
                    item.get("airline", ""),
                    item.get("model", ""),
                    item.get("livery_name", ""),
                    item.get("img_url", ""),
                    1 if item.get("is_active", True) else 0,
                    now,
                ),
            )
            count += 1
    return count


def get_active_watchlist(db_path: Path = DB_PATH) -> dict[str, dict[str, Any]]:
    """返回 {hex: row_dict} 映射。"""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM aircraft_watchlist WHERE is_active = 1 ORDER BY reg ASC"
        ).fetchall()
        return {row["hex"].lower(): dict(row) for row in rows}


def upsert_watchlist_item(item: dict[str, Any], db_path: Path = DB_PATH) -> None:
    """新增或更新单架监控飞机。"""
    now = _now_iso()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO aircraft_watchlist (
                hex, reg, category, airline, model, livery_name, img_url, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(hex) DO UPDATE SET
                reg=excluded.reg,
                category=excluded.category,
                airline=excluded.airline,
                model=excluded.model,
                livery_name=excluded.livery_name,
                img_url=excluded.img_url,
                is_active=1,
                updated_at=excluded.updated_at
            """,
            (
                item["hex"].strip().lower(),
                item["reg"].strip().upper(),
                item.get("category", "彩绘客机"),
                item.get("airline", ""),
                item.get("model", ""),
                item.get("livery_name", ""),
                item.get("img_url", ""),
                now,
            ),
        )


def upsert_observed_aircraft(
    hex_code: str,
    reg: str,
    model: str,
    callsign: str,
    body_type: str,
    is_special_livery: bool,
    db_path: Path = DB_PATH,
) -> None:
    """记录所有观测到的飞机档案。"""
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO observed_aircraft (
                hex, reg, model, callsign, body_type, is_special_livery, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hex) DO UPDATE SET
                reg = CASE WHEN excluded.reg != '' THEN excluded.reg ELSE observed_aircraft.reg END,
                model = CASE WHEN excluded.model != '' THEN excluded.model ELSE observed_aircraft.model END,
                callsign = CASE WHEN excluded.callsign != '' THEN excluded.callsign ELSE observed_aircraft.callsign END,
                body_type = excluded.body_type,
                is_special_livery = MAX(observed_aircraft.is_special_livery, excluded.is_special_livery),
                last_seen_at = excluded.last_seen_at
            """,
            (
                hex_code.strip().lower(),
                reg.strip().upper(),
                model.strip().upper(),
                callsign.strip().upper(),
                body_type,
                1 if is_special_livery else 0,
                _now_iso(),
            ),
        )


def delete_watchlist_item(hex_code: str, db_path: Path = DB_PATH) -> None:
    """停用监控清单中的飞机。"""
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE aircraft_watchlist SET is_active = 0, updated_at = ? WHERE hex = ?",
            (_now_iso(), hex_code.strip().lower()),
        )


def append_track_point(
    hex_code: str,
    callsign: str,
    lat: float,
    lon: float,
    alt_ft: int,
    gs_knots: float,
    track_deg: float,
    baro_rate: float,
    db_path: Path = DB_PATH,
) -> None:
    """写入一条轨迹缓存点。"""
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO adsb_track_cache (
                hex, callsign, lat, lon, alt_ft, gs_knots, track_deg, baro_rate, seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (hex_code.lower(), callsign, lat, lon, alt_ft, gs_knots, track_deg, baro_rate, _now_iso()),
        )


def get_recent_track_points(hex_code: str, minutes: int = 20, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """查询某架飞机最近 N 分钟的轨迹点（按时间升序）。"""
    cutoff = (datetime.now(CHINA_TZ) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM adsb_track_cache
            WHERE hex = ? AND seen_at >= ?
            ORDER BY seen_at ASC
            """,
            (hex_code.lower(), cutoff),
        ).fetchall()
        return [dict(r) for r in rows]


def cleanup_old_track_cache(hours: int = 3, db_path: Path = DB_PATH) -> None:
    """清理超过 N 小时的轨迹缓存，控制数据库体积。"""
    cutoff = (datetime.now(CHINA_TZ) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM adsb_track_cache WHERE seen_at < ?", (cutoff,))


def record_flight(
    hex_code: str,
    callsign: str,
    origin_icao: str,
    dest_icao: str,
    source: str,
    db_path: Path = DB_PATH,
) -> None:
    """记录或更新最近 6 小时内的同一航段记录。"""
    now_dt = datetime.now(CHINA_TZ)
    now = now_dt.isoformat(timespec="seconds")
    cutoff = (now_dt - timedelta(hours=6)).isoformat(timespec="seconds")
    weekday = now_dt.isoweekday()

    with get_conn(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id, origin_icao, dest_icao FROM flight_records
            WHERE hex = ? AND callsign = ? AND last_seen_at >= ?
            ORDER BY id DESC LIMIT 1
            """,
            (hex_code.lower(), callsign, cutoff),
        ).fetchone()

        if existing:
            new_origin = origin_icao or existing["origin_icao"]
            new_dest = dest_icao or existing["dest_icao"]
            conn.execute(
                """
                UPDATE flight_records
                SET origin_icao = ?, dest_icao = ?, last_seen_at = ?, source = ?
                WHERE id = ?
                """,
                (new_origin, new_dest, now, source, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO flight_records (
                    hex, callsign, origin_icao, dest_icao, source, first_seen_at, last_seen_at, weekday
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (hex_code.lower(), callsign, origin_icao, dest_icao, source, now, now, weekday),
            )


def record_runway_landing(
    hex_code: str,
    reg: str,
    callsign: str,
    runway_ident: str,
    min_alt_ft: int,
    is_daylight: bool,
    db_path: Path = DB_PATH,
) -> bool:
    """记录 HGH 降落跑道（30 分钟内同一架飞机不重复写入）。"""
    now_dt = datetime.now(CHINA_TZ)
    now = now_dt.isoformat(timespec="seconds")
    cutoff = (now_dt - timedelta(minutes=30)).isoformat(timespec="seconds")

    with get_conn(db_path) as conn:
        dup = conn.execute(
            "SELECT id FROM runway_logs WHERE hex = ? AND landed_at >= ? LIMIT 1",
            (hex_code.lower(), cutoff),
        ).fetchone()
        if dup:
            return False

        conn.execute(
            """
            INSERT INTO runway_logs (
                hex, reg, callsign, airport_icao, runway_ident, min_alt_ft, landed_at, is_daylight
            ) VALUES (?, ?, ?, 'ZSHC', ?, ?, ?, ?)
            """,
            (hex_code.lower(), reg, callsign, runway_ident, min_alt_ft, now, 1 if is_daylight else 0),
        )
        return True


def get_runway_history(limit: int = 80, db_path: Path = DB_PATH) -> dict[str, Any]:
    """查询历史跑道记录及各跑道分布统计（覆盖所有观测到的飞机）。"""
    with get_conn(db_path) as conn:
        logs = conn.execute(
            """
            SELECT r.*,
                   COALESCE(w.livery_name, '') AS livery_name,
                   COALESCE(NULLIF(w.model, ''), o.model, '') AS model,
                   COALESCE(w.category, o.body_type, '其他') AS category,
                   COALESCE(o.body_type, '其他') AS body_type,
                   CASE WHEN w.hex IS NOT NULL AND w.is_active = 1 AND w.category LIKE '%彩绘%' THEN 1
                        ELSE COALESCE(o.is_special_livery, 0) END AS is_special_livery
            FROM runway_logs r
            LEFT JOIN aircraft_watchlist w ON r.hex = w.hex
            LEFT JOIN observed_aircraft o ON r.hex = o.hex
            ORDER BY r.landed_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        stats = conn.execute(
            """
            SELECT runway_ident, COUNT(*) AS cnt,
                   SUM(is_daylight) AS daylight_cnt
            FROM runway_logs
            GROUP BY runway_ident
            ORDER BY cnt DESC
            """
        ).fetchall()

        return {
            "logs": [dict(r) for r in logs],
            "stats": [dict(s) for s in stats],
        }


def get_route_predictions(days: int = 14, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """基于过去 N 天历史航线规律，生成未来 1~2 天的串飞参考预测（覆盖所有观测飞机）。"""
    now_dt = datetime.now(CHINA_TZ)
    cutoff = (now_dt - timedelta(days=days)).isoformat(timespec="seconds")
    tomorrow_wd = (now_dt + timedelta(days=1)).isoweekday()
    day_after_wd = (now_dt + timedelta(days=2)).isoweekday()

    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT f.hex,
                   COALESCE(NULLIF(w.reg, ''), o.reg, f.hex) AS reg,
                   COALESCE(w.livery_name, '') AS livery_name,
                   COALESCE(w.category, o.body_type, '其他') AS category,
                   COALESCE(NULLIF(w.model, ''), o.model, '') AS model,
                   COALESCE(o.body_type, '其他') AS body_type,
                   CASE WHEN w.hex IS NOT NULL AND w.is_active = 1 AND w.category LIKE '%彩绘%' THEN 1
                        ELSE COALESCE(o.is_special_livery, 0) END AS is_special_livery,
                   f.callsign, f.origin_icao, f.dest_icao, f.weekday,
                   COUNT(*) AS freq, MAX(f.last_seen_at) AS last_seen_at
            FROM flight_records f
            LEFT JOIN aircraft_watchlist w ON f.hex = w.hex
            LEFT JOIN observed_aircraft o ON f.hex = o.hex
            WHERE f.last_seen_at >= ?
              AND (f.origin_icao IN ('HGH', 'ZSHC') OR f.dest_icao IN ('HGH', 'ZSHC'))
            GROUP BY f.hex, f.callsign, f.origin_icao, f.dest_icao, f.weekday
            ORDER BY is_special_livery DESC, freq DESC, last_seen_at DESC
            LIMIT 150
            """,
            (cutoff,),
        ).fetchall()

    results = []
    for r in rows:
        item = dict(r)
        wd = item["weekday"]
        item["match_window"] = (
            "明日规律匹配" if wd == tomorrow_wd else ("后日规律匹配" if wd == day_after_wd else f"周{wd}常飞")
        )
        item["confidence"] = "高" if item["freq"] >= 2 else "中/待观察"
        results.append(item)
    return results


def upsert_hgh_schedules(items: list[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    """保存或更新 HGH 进出港时刻表（计划/预计/实际起降时间）。"""
    now = _now_iso()
    count = 0
    with get_conn(db_path) as conn:
        for it in items:
            f_iata = str(it.get("flight_iata") or "").strip().upper()
            f_icao = str(it.get("flight_icao") or "").strip().upper()
            dep_iata = str(it.get("dep_iata") or "").strip().upper()
            arr_iata = str(it.get("arr_iata") or "").strip().upper()
            direction = str(it.get("direction") or ("进港" if arr_iata == "HGH" else "出港"))
            dep_time = str(it.get("dep_time") or "").strip()
            arr_time = str(it.get("arr_time") or "").strip()
            anchor_time = arr_time if direction == "进港" else dep_time
            flight_key = f"{direction}_{f_icao or f_iata}_{anchor_time}"
            if not (f_iata or f_icao):
                continue
            conn.execute(
                """
                INSERT INTO hgh_schedules (
                    flight_key, direction, flight_iata, flight_icao, airline_iata, aircraft_icao, status,
                    dep_iata, dep_time, dep_estimated, dep_actual,
                    arr_iata, arr_time, arr_estimated, arr_actual, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(flight_key) DO UPDATE SET
                    direction=excluded.direction,
                    status=excluded.status,
                    aircraft_icao=COALESCE(NULLIF(excluded.aircraft_icao, ''), hgh_schedules.aircraft_icao),
                    dep_estimated=excluded.dep_estimated,
                    dep_actual=excluded.dep_actual,
                    arr_estimated=excluded.arr_estimated,
                    arr_actual=excluded.arr_actual,
                    updated_at=excluded.updated_at
                """,
                (
                    flight_key,
                    direction,
                    f_iata,
                    f_icao,
                    str(it.get("airline_iata") or "").upper(),
                    str(it.get("aircraft_icao") or "").upper(),
                    str(it.get("status") or "").lower(),
                    dep_iata,
                    dep_time,
                    str(it.get("dep_estimated") or ""),
                    str(it.get("dep_actual") or ""),
                    arr_iata,
                    arr_time,
                    str(it.get("arr_estimated") or ""),
                    str(it.get("arr_actual") or ""),
                    now,
                ),
            )
            count += 1
    return count


def get_hgh_schedules(limit: int = 300, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """查询本地缓存的 HGH 进出港时刻表，严格按时间顺序排列。"""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM hgh_schedules
            ORDER BY
                CASE WHEN direction = '进港'
                     THEN COALESCE(NULLIF(arr_actual, ''), NULLIF(arr_estimated, ''), arr_time)
                     ELSE COALESCE(NULLIF(dep_actual, ''), NULLIF(dep_estimated, ''), dep_time)
                END ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_schedule_map_by_icao(db_path: Path = DB_PATH) -> dict[str, dict[str, Any]]:
    """返回 {flight_icao: schedule_row} 映射，用于在实时雷达上匹配计划/实际时间。"""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM hgh_schedules WHERE flight_icao != '' ORDER BY updated_at DESC"
        ).fetchall()
    mapping: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = r["flight_icao"].upper()
        if code not in mapping:
            mapping[code] = dict(r)
    return mapping
