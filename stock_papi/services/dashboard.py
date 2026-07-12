from stock_papi.shared.formatting import clamp as _clamp
from stock_papi.shared.formatting import safe_float as _safe_float


def dashboard_top_picks(cards, limit=3):
    picks = []
    for card in cards[:limit]:
        leader = card["leader"]
        picks.append({
            "code": leader["code"],
            "name": leader["name"],
            "headline": f"{card['name']}優先觀察",
            "summary": f"AI 勝率 {leader['prob']}%・{leader['trend']}・外資5日 {leader['foreign_net_5']:,}",
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

