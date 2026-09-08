import json


def sse_event(event_type: str, **payload) -> str:
    """把事件编码为一条 SSE 消息（data: 行 + 空行分隔）。

    event_type: stage | delta | done | error
    """
    data = {"type": event_type, **payload}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
