import datetime

from stock_papi.services.recommendation_engine import (
    RecommendationInput,
    build_recommendation,
)
from stock_papi.shared.formatting import clamp as _clamp
from stock_papi.shared.formatting import safe_float as _safe_float


def dashboard_top_picks(cards, limit=3):
    picks = []
    for card in cards[:limit]:
        leader = card["leader"]
        picks.append({
            "code": leader["code"],
            "name": leader["name"],
            "headline": leader["recommendation"]["headline"],
            "summary": f"五日上漲機率 {leader['prob']}%・{leader['trend']}・外資5日 {leader['foreign_net_5']:,}",
            "recommendation": leader["recommendation"],
        })
    return picks


def build_market_heatmap(cards):
    heatmap = []
    for card in cards or []:
        probability = _clamp(
            _safe_float((card.get("leader") or {}).get("prob"), card.get("score", 50)),
            0,
            100,
        )
        heatmap.append({
            "name": str(card.get("name") or "未分類"),
            "probability": round(probability, 1),
            "count": int(_safe_float(card.get("count"))),
            "tone": "hot" if probability >= 60 else "cold" if probability < 45 else "steady",
            "code": str((card.get("leader") or {}).get("code") or ""),
        })
    return sorted(heatmap, key=lambda item: item["probability"], reverse=True)



def cached_opportunities(cache, now, expiry_seconds, limit=5):
    timestamp_now = now()
    items = []
    for code, (data, timestamp) in cache.items():
        if code == "TAIEX" or timestamp_now - timestamp >= expiry_seconds:
            continue
        if all(key in data for key in ("name", "prob")):
            items.append({"code": code, "name": data["name"], "prob": data["prob"]})
    return sorted(items, key=lambda item: item["prob"], reverse=True)[:limit]


def dashboard_sector_cards(load_snapshot, line_store, fallback_items, safe_float, limit=6):
    try:
        snapshot = load_snapshot(line_store)
    except Exception:
        snapshot = {}
    cards = []
    for name, items in (snapshot or {}).get("sectors", {}).items():
        if not items:
            continue
        leader = items[0]
        try:
            as_of = datetime.date.fromisoformat(str(leader.get("as_of") or ""))
        except ValueError:
            as_of = None
        recommendation = build_recommendation(RecommendationInput(
            scope="industry",
            entity_id=str(name),
            probability=leader.get("prob"),
            trend=leader.get("trend"),
            data_as_of=as_of,
            current_date=datetime.date.today(),
            foreign_net_5=leader.get("foreign_net_5"),
            sample_count=leader.get("sample_count", leader.get("trades")),
            industry_coverage=leader.get("coverage"),
            rotation=leader.get("rotation"),
            near_rotation_boundary=leader.get("near_rotation_boundary") is True,
            data_quality_warning=leader.get("data_quality_warning") is True,
        )).to_dict()
        cards.append({
            "name": name,
            "count": len(items),
            "score": round(safe_float(leader.get("score")), 1),
            "leader": {
                "code": str(leader.get("code") or ""),
                "name": str(leader.get("name") or ""),
                "prob": int(safe_float(leader.get("prob"))),
                "trend": str(leader.get("trend") or "中性"),
                "foreign_net_5": int(safe_float(leader.get("foreign_net_5"))),
                "as_of": str(leader.get("as_of") or ""),
                "recommendation": recommendation,
            },
        })
    if cards:
        return sorted(cards, key=lambda item: item["score"], reverse=True)[:limit]
    fallback = []
    for item in fallback_items(limit):
        fallback.append({
            "name": "熱門觀察",
            "count": 1,
            "score": float(item["prob"]),
            "leader": {
                "code": item["code"],
                "name": item["name"],
                "prob": int(item["prob"]),
                "trend": "等待更新",
                "foreign_net_5": 0,
                "as_of": "",
                "recommendation": build_recommendation(RecommendationInput(
                    scope="industry", entity_id="熱門觀察",
                    probability=item["prob"], trend="等待更新",
                )).to_dict(),
            },
        })
    return fallback
