"""批量注册号补全工具：通过 hexdb.io 自动查询注册号对应的 Hex、机型和参考图，写入 watchlist.json。

用法:
    python scripts/sync_watchlist.py B-2021 B-2001 B-2476
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import adsb_client, db
from config import WATCHLIST_PATH


async def main(regs: list[str]) -> None:
    existing = []
    if WATCHLIST_PATH.exists():
        existing = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    by_reg = {item["reg"].upper(): item for item in existing if "reg" in item}

    for reg in regs:
        clean_reg = reg.strip().upper()
        if not clean_reg:
            continue
        info = await adsb_client.lookup_aircraft_by_reg(clean_reg)
        if not info:
            print(f"[跳过] 未查到 {clean_reg} 的 Hex 信息")
            continue
        old = by_reg.get(clean_reg, {})
        by_reg[clean_reg] = {
            "hex": info["hex"],
            "reg": clean_reg,
            "category": old.get("category", "彩绘客机"),
            "airline": old.get("airline") or info["airline"],
            "model": old.get("model") or info["model"],
            "livery_name": old.get("livery_name") or clean_reg,
            "img_url": old.get("img_url") or info["img_url"],
            "is_active": True,
        }
        print(f"[成功] {clean_reg} -> hex={info['hex']} model={info['model']}")

    merged = list(by_reg.values())
    WATCHLIST_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    db.init_db()
    db.load_watchlist_from_json()
    print(f"已同步 {len(merged)} 架飞机到 watchlist.json 与 SQLite。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("请传入至少一个注册号，例如: python scripts/sync_watchlist.py B-2021")
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
