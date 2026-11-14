"""飞机双维度分类：宽体机 / 窄体机 / 货机 / 其他，以及是否为彩绘机。"""

from __future__ import annotations

from typing import Any

WIDEBODY_MODELS = {
    "A332", "A333", "A338", "A339",
    "A342", "A343", "A345", "A346",
    "A359", "A35K", "A388",
    "B744", "B748", "B74S",
    "B762", "B763", "B764",
    "B772", "B77L", "B77W", "B773",
    "B788", "B789", "B78X",
    "C929", "IL96",
}

NARROWBODY_MODELS = {
    "A318", "A319", "A320", "A321", "A19N", "A20N", "A21N",
    "B712", "B733", "B734", "B735", "B736", "B737", "B738", "B739",
    "B37M", "B38M", "B39M", "B752", "B753",
    "C919", "ARJ2", "AJ27",
    "E170", "E175", "E190", "E195", "E290", "E295",
    "BCS1", "BCS3", "MD82", "MD83", "MD88", "MD90",
}

CARGO_MODELS = {
    "B74F", "B74Y", "B74R", "B77F", "B76F", "B75F", "B73F",
    "A306", "A30B", "A310", "A33F",
    "MD11", "DC10", "AN12", "A124", "A225", "IL76", "C130", "Y20",
}

CARGO_CALLSIGN_PREFIXES = (
    "CSS",  # 顺丰航空
    "CYZ",  # 中国邮政航空
    "CAO",  # 中国国际货运航空
    "CKK",  # 中国货运航空
    "CSG",  # 南航货运
    "HTK",  # 天津货运航空
    "YZR",  # 金鹏航空(原扬子江快运)
    "HYT",  # 圆通货运航空
    "CGZ",  # 中原龙浩航空
    "JDL",  # 京东货运航空
    "FDX",  # FedEx
    "UPS",  # UPS
    "CLX",  # Cargolux
    "GTI",  # Atlas Air
    "CKS",  # Kalitta Air
    "ABW",  # AirBridgeCargo
    "BOX",  # AeroLogic
    "GEC",  # Lufthansa Cargo
    "SQC",  # Singapore Airlines Cargo
    "NCA",  # Nippon Cargo
    "MPH",  # Martinair Cargo
    "PAC",  # Polar Air Cargo
    "DHK",  # DHL Air
    "BCS",  # European Air Transport (DHL)
)


def classify_aircraft(
    model: str,
    callsign: str,
    watch_item: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """返回 (body_type, is_special_livery)。

    body_type 取值: "货机" | "宽体机" | "窄体机" | "其他"
    """
    m = (model or "").strip().upper()
    cs = (callsign or "").strip().upper()

    is_special = False
    is_cargo_watch = False
    if watch_item is not None:
        cat = str(watch_item.get("category") or "")
        is_special = bool(watch_item.get("is_special_livery")) or ("彩绘" in cat)
        is_cargo_watch = "货机" in cat

    # 1. 货机判定（清单标记 / 纯货机机型 / 货运航司呼号前缀）
    if is_cargo_watch or m in CARGO_MODELS or (cs and cs.startswith(CARGO_CALLSIGN_PREFIXES)):
        return "货机", is_special

    # 2. 宽体机判定
    if m in WIDEBODY_MODELS:
        return "宽体机", is_special

    # 3. 窄体机判定
    if m in NARROWBODY_MODELS:
        return "窄体机", is_special

    return "其他", is_special
