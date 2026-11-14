"""项目全局配置（针对杭州萧山国际机场 HGH / ZSHC）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("HGH_DB_PATH", str(BASE_DIR / "hgh_spotter.db")))
WATCHLIST_PATH = BASE_DIR / "watchlist.json"

# 杭州萧山国际机场 (HGH / ZSHC) 基准坐标
HGH_ICAO = "ZSHC"
HGH_IATA = "HGH"
HGH_LAT = 30.2371
HGH_LON = 120.4319

# 雷达扫描半径（海里）与轮询间隔（秒）
RADAR_RADIUS_NM = int(os.getenv("RADAR_RADIUS_NM", "80"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
USER_AGENT = "HGH-Plane-Spotter/0.2 (personal-hobby-tracker)"

# 可选手机推送配置（留空则不推送）
# Bark 示例: https://api.day.app/你的Key
BARK_URL = os.getenv("BARK_URL", "").strip()
# Server酱 / PushPlus 等通用 GET/POST Webhook
NOTIFY_WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL", "").strip()


@dataclass(frozen=True)
class RunwayEnd:
    """跑道端头信息。"""

    ident: str
    lat: float
    lon: float
    heading_deg: float


@dataclass(frozen=True)
class RunwayPair:
    """双向跑道几何定义。"""

    name: str
    end_a: RunwayEnd
    end_b: RunwayEnd


# HGH 两条平行跑道：07/25 与 06/24
HGH_RUNWAYS: tuple[RunwayPair, ...] = (
    RunwayPair(
        name="07/25",
        end_a=RunwayEnd(ident="07", lat=30.2212, lon=120.4178, heading_deg=69.0),
        end_b=RunwayEnd(ident="25", lat=30.2369, lon=120.4450, heading_deg=249.0),
    ),
    RunwayPair(
        name="06/24",
        end_a=RunwayEnd(ident="06", lat=30.2370, lon=120.4072, heading_deg=69.0),
        end_b=RunwayEnd(ident="24", lat=30.2510, lon=120.4387, heading_deg=249.0),
    ),
)
