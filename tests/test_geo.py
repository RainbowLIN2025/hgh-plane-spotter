"""地理算法、HGH 跑道识别与数据库基础测试。"""

from __future__ import annotations

from pathlib import Path

from app import db, geo


def test_identify_hgh_runway_07_and_06() -> None:
    # 贴近 07 跑道进近端（航向约 69 度，低空 600ft）
    rwy_07, alt_07 = geo.identify_hgh_runway([(30.2150, 120.4010, 69.0, 600)])
    assert rwy_07 == "07"
    assert alt_07 == 600

    # 贴近 06 跑道进近端（航向约 69 度，低空 550ft）
    rwy_06, alt_06 = geo.identify_hgh_runway([(30.2320, 120.3940, 69.0, 550)])
    assert rwy_06 == "06"
    assert alt_06 == 550


def test_identify_hgh_runway_25_and_high_alt_fallback() -> None:
    # 贴近 25 跑道进近端（航向约 249 度）
    rwy_25, _ = geo.identify_hgh_runway([(30.2420, 120.4590, 249.0, 700)])
    assert rwy_25 == "25"

    # 高于 3000ft 只返回大方向
    direction, alt = geo.identify_hgh_runway([(30.2420, 120.4590, 249.0, 3800)])
    assert direction == "24/25方向"
    assert alt == 3800


def test_estimate_eta_minutes() -> None:
    # 约 100km 外以 300 节飞行，大约 11 分钟巡航 + 12 分钟冗余 ≈ 23 分钟
    eta = geo.estimate_eta_minutes(31.1, 120.4319, 300.0)
    assert eta is not None
    assert 15 <= eta <= 35


def test_db_runway_and_prediction(tmp_path: Path) -> None:
    test_db = tmp_path / "test.db"
    db.init_db(test_db)
    db.upsert_watchlist_item(
        {"hex": "7809e4", "reg": "B-2021", "category": "彩绘客机", "model": "B77W", "livery_name": "测试彩绘"},
        db_path=test_db,
    )
    inserted = db.record_runway_landing("7809e4", "B-2021", "CCA123", "07", 550, True, db_path=test_db)
    assert inserted is True
    # 30 分钟内重复不写入
    inserted_dup = db.record_runway_landing("7809e4", "B-2021", "CCA123", "07", 520, True, db_path=test_db)
    assert inserted_dup is False

    history = db.get_runway_history(db_path=test_db)
    assert len(history["logs"]) == 1
    assert history["logs"][0]["runway_ident"] == "07"

    db.record_flight("7809e4", "CCA123", "PEK", "HGH", "test", db_path=test_db)
    preds = db.get_route_predictions(db_path=test_db)
    assert len(preds) == 1
    assert preds[0]["dest_icao"] == "HGH"
