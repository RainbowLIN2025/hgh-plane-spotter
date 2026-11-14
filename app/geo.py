"""地理计算、ETA 估算与 HGH 跑道识别算法。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from config import HGH_LAT, HGH_LON, HGH_RUNWAYS

EARTH_RADIUS_KM = 6371.0
NM_TO_KM = 1.852
CHINA_TZ = timezone(timedelta(hours=8))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点之间的球面距离（公里）。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def heading_diff_deg(h1: float, h2: float) -> float:
    """计算两个航向角之间的最小夹角（0~180 度）。"""
    diff = abs((h1 - h2) % 360.0)
    return 360.0 - diff if diff > 180.0 else diff


def _to_local_xy_km(lat: float, lon: float, ref_lat: float = HGH_LAT, ref_lon: float = HGH_LON) -> tuple[float, float]:
    """将经纬度投影到以参考点为原点的局部平面坐标（单位：公里）。"""
    lat_rad = math.radians(ref_lat)
    x = math.radians(lon - ref_lon) * EARTH_RADIUS_KM * math.cos(lat_rad)
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_KM
    return x, y


def point_to_line_distance_km(
    lat: float, lon: float, p1_lat: float, p1_lon: float, p2_lat: float, p2_lon: float
) -> float:
    """计算点到跑道中心延长线的垂直距离（公里）。"""
    px, py = _to_local_xy_km(lat, lon)
    x1, y1 = _to_local_xy_km(p1_lat, p1_lon)
    x2, y2 = _to_local_xy_km(p2_lat, p2_lon)

    dx = x2 - x1
    dy = y2 - y1
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return math.hypot(px - x1, py - y1)
    return abs(dx * (y1 - py) - (x1 - px) * dy) / norm


def identify_hgh_runway(
    points: list[tuple[float, float, float, float]],
) -> tuple[str, int]:
    """根据最后一组低空轨迹点识别 HGH 降落跑道。

    Args:
        points: [(lat, lon, track_deg, alt_ft), ...] 按时间升序排列。

    Returns:
        (runway_ident, min_alt_ft)
        例如 ("06", 650) 或 ("06/07方向", 3200) 或 ("未知", 99999)。
    """
    if not points:
        return "未知", 99999

    min_alt = int(min(p[3] for p in points))
    last_lat, last_lon, last_track, _ = points[-1]

    # 判定飞行大方向：向东北偏东落地 (06/07) 或向西南偏西落地 (24/25)
    diff_east = heading_diff_deg(last_track, 69.0)
    diff_west = heading_diff_deg(last_track, 249.0)

    if min(diff_east, diff_west) > 55.0:
        return "非进近航向", min_alt

    is_eastbound = diff_east <= diff_west

    # 若最低高度仍高于 3000ft（低空信号缺失），只返回大方向，避免平行跑道误判
    if min_alt > 3000:
        return ("06/07方向" if is_eastbound else "24/25方向"), min_alt

    # 取最后最多 3 个低空点计算到各平行跑道延长线的平均垂直距离
    tail_points = points[-3:]
    best_ident = "未知"
    best_dist = float("inf")

    for rwy in HGH_RUNWAYS:
        avg_dist = sum(
            point_to_line_distance_km(
                pt[0], pt[1], rwy.end_a.lat, rwy.end_a.lon, rwy.end_b.lat, rwy.end_b.lon
            )
            for pt in tail_points
        ) / len(tail_points)

        if avg_dist < best_dist:
            best_dist = avg_dist
            best_ident = rwy.end_a.ident if is_eastbound else rwy.end_b.ident

    return best_ident, min_alt


def estimate_eta_minutes(
    lat: float,
    lon: float,
    gs_knots: float | None,
    dest_lat: float = HGH_LAT,
    dest_lon: float = HGH_LON,
) -> int | None:
    """估算距离目标机场的剩余分钟数（含 12 分钟进近冗余）。"""
    if gs_knots is None or gs_knots < 60:
        return None
    dist_km = haversine_km(lat, lon, dest_lat, dest_lon)
    speed_kmh = gs_knots * NM_TO_KM
    cruise_minutes = (dist_km / speed_kmh) * 60.0
    buffer_minutes = 3.0 if dist_km < 25.0 else 12.0
    return max(1, round(cruise_minutes + buffer_minutes))


def is_hangzhou_daylight(dt: datetime | None = None) -> bool:
    """粗略判断杭州当前是否处于适合拍机的白天光线时段（06:00 ~ 18:30）。"""
    now = dt or datetime.now(CHINA_TZ)
    local_dt = now.astimezone(CHINA_TZ)
    hour_float = local_dt.hour + local_dt.minute / 60.0
    return 6.0 <= hour_float <= 18.5
