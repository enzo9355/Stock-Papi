from absorb.conversation.schemas import ConversationAnswer


def render_line(answer: ConversationAnswer, *, max_chars=4500) -> str:
    text = answer.text.strip()
    if len(text) <= max_chars:
        return text
    suffix = "\n\n內容較長，已保留結論與前段依據；請到 Web 查看完整分析。"
    return text[: max_chars - len(suffix)].rstrip() + suffix


def render_web(answer: ConversationAnswer) -> dict:
    return answer.to_dict()
