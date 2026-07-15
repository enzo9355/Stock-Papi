"""Compatibility contract between deterministic LINE commands and chat fallback."""


FIXED_EXACT_COMMANDS = frozenset(
    {
        "大盤預測",
        "大盤",
        "今日盤勢",
        "預測",
        "熱門產業",
        "我的關注",
        "強勢訊號",
        "提醒管理",
        "完整分析",
        "投資試算",
        "功能選單",
        "產業列表",
        "免責聲明",
        "新手教學",
    }
)


FIXED_RULE_PREFIXES = ("試算", "分類第_", "選產業_")


def is_fixed_command(message: str) -> bool:
    message = str(message or "").strip()
    return message in FIXED_EXACT_COMMANDS or any(message.startswith(prefix) for prefix in FIXED_RULE_PREFIXES)
