import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app.config import SHORT_MEMORY_DIR, SHORT_TERM_MAX_TURNS
from app.services.storage import read_json, write_json


def new_session_id() -> str:
    return f"session_{uuid.uuid4().hex[:12]}"


def session_path(session_id: str) -> Path:
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"_", "-"})
    return SHORT_MEMORY_DIR / f"{safe_id}.json"


def load_session(session_id: str) -> Dict:
    return read_json(
        session_path(session_id),
        {
            "session_id": session_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "turns": [],
            "summary": "",
        },
    )


def save_turn(session_id: str, user_message: str, assistant_answer: str, intent: str, tools_used: List[str]):
    session = load_session(session_id)
    session["turns"].append(
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": user_message,
            "assistant": assistant_answer,
            "intent": intent,
            "tools_used": tools_used,
        }
    )
    if len(session["turns"]) > SHORT_TERM_MAX_TURNS:
        removed = session["turns"][:-SHORT_TERM_MAX_TURNS]
        session["summary"] = build_summary(session.get("summary", ""), removed)
        session["turns"] = session["turns"][-SHORT_TERM_MAX_TURNS:]
    write_json(session_path(session_id), session)
    return session


def build_summary(previous_summary: str, turns: List[Dict]) -> str:
    facts = []
    for turn in turns[-6:]:
        facts.append(f"用户问题：{turn.get('user', '')}；助手回复主题：{turn.get('intent', '')}")
    joined = "；".join(facts)
    if previous_summary:
        return f"{previous_summary}；{joined}"[-1200:]
    return joined[-1200:]


def get_recent_context(session_id: str) -> Dict:
    session = load_session(session_id)
    return {
        "summary": session.get("summary", ""),
        "turns": session.get("turns", [])[-SHORT_TERM_MAX_TURNS:],
    }


def list_sessions():
    sessions = []
    for path in SHORT_MEMORY_DIR.glob("*.json"):
        item = read_json(path, {})
        sessions.append(
            {
                "session_id": item.get("session_id", path.stem),
                "created_at": item.get("created_at", ""),
                "turn_count": len(item.get("turns", [])),
                "last_message": (item.get("turns", [])[-1].get("user", "") if item.get("turns") else ""),
            }
        )
    return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)
