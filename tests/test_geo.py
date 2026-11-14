"""地理算法、机型分类、多源合并与数据库基础测试。"""

from __future__ import annotations

from pathlib import Path

from app import adsb_client, classifier, db, geo


def test_identify_hgh_runway_07_and_06() -> None:
    rwy_07, alt_07 = geo.identify_hgh_runway([(30.2150, 120.4010, 69.0, 600)])
    assert rwy_07 == "07"
    assert alt_07 == 600

    rwy_06, alt_06 = geo.identify_hgh_runway([(30.2320, 120.3940, 69.0, 550)])
    assert rwy_06 == "06"
    assert alt_06 == 550


def test_identify_hgh_runway_25_and_high_alt_fallback() -> None:
    rwy_25, _ = geo.identify_hgh_runway([(30.2420, 120.4590, 249.0, 700)])
    assert rwy_25 == "25"

    direction, alt = geo.identify_hgh_runway([(30.2420, 120.4590, 249.0, 3800)])
    assert direction == "24/25方向"
    assert alt == 3800


def test_estimate_eta_minutes() -> None:
    eta = geo.estimate_eta_minutes(31.1, 120.4319, 300.0)
    assert eta is not None
    assert 15 <= eta <= 35


def test_classifier_wide_narrow_cargo_and_livery() -> None:
    assert classifier.classify_aircraft("A359", "CES5101", None) == ("宽体机", False)
    assert classifier.classify_aircraft("B738", "CSN3456", None) == ("窄体机", False)
    assert classifier.classify_aircraft("B77F", "CKK201", None) == ("货机", False)
    assert classifier.classify_aircraft("B752", "CSS7001", None) == ("货机", False)
    assert classifier.classify_aircraft("B77W", "CES202", {"category": "彩绘客机"}) == ("宽体机", True)
    assert classifier.classify_aircraft("B748", "CSS123", {"category": "彩绘货机"}) == ("货机", True)


def test_classify_flight_phase() -> None:
    assert classifier.classify_flight_phase("PEK", "HGH", 150.0, 0, 20000) == "进港"
    assert classifier.classify_flight_phase("HGH", "CAN", 40.0, 1500, 5000) == "出港"
    assert classifier.classify_flight_phase("", "", 30.0, -800, 3000) == "进港"
    assert classifier.classify_flight_phase("", "", 30.0, 1200, 4000) == "出港"
    assert classifier.classify_flight_phase("PVG", "CAN", 120.0, 0, 32000) == "过境"


def test_merge_adsb_records_prefers_freshest() -> None:
    b1 = [{"hex": "7809e4", "lat": 30.1, "lon": 120.2, "seen": 5.0, "r": "B-2021"}]
    b2 = [{"hex": "7809E4", "lat": 30.2, "lon": 120.3, "seen": 0.4, "t": "B77W"}]
    merged = adsb_client.merge_adsb_records([b1, b2])
    assert len(merged) == 1
    assert merged[0]["lat"] == 30.2
    assert merged[0]["r"] == "B-2021"
    assert merged[0]["t"] == "B77W"


def test_db_all_aircraft_runway_and_prediction(tmp_path: Path) -> None:
    test_db = tmp_path / "test.db"
    db.init_db(test_db)
    db.upsert_observed_aircraft("780001", "B-1234", "A320", "CES5101", "窄体机", False, db_path=test_db)
    db.record_runway_landing("780001", "B-1234", "CES5101", "07", 550, True, db_path=test_db)
    db.record_flight("780001", "CES5101", "PEK", "HGH", "test", db_path=test_db)

    history = db.get_runway_history(db_path=test_db)
    assert len(history["logs"]) == 1
    assert history["logs"][0]["body_type"] == "窄体机"

    preds = db.get_route_predictions(db_path=test_db)
    assert len(preds) == 1
    assert preds[0]["dest_icao"] == "HGH"
