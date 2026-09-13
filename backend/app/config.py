import os
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "backend" / "storage"
if os.getenv("VERCEL"):
    # Vercel 函数文件系统只读，运行时数据放 /tmp（实例内有效，冷启动后清空）
    STORAGE_DIR = Path("/tmp/nutrifit/storage")
UPLOAD_DIR = STORAGE_DIR / "uploads"
RECORDS_FILE = STORAGE_DIR / "meal_records.json"
PROFILE_FILE = STORAGE_DIR / "user_profile.json"
CONFIG_DIR = BASE_DIR / "backend" / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONFIG_EXAMPLE_FILE = CONFIG_DIR / "config.example.yaml"
MEMORY_DIR = STORAGE_DIR / "memory"
SHORT_MEMORY_DIR = MEMORY_DIR / "short_term"
LONG_MEMORY_DIR = MEMORY_DIR / "long_term"
BODY_METRICS_FILE = LONG_MEMORY_DIR / "body_metrics.json"
RUNTIME_SETTINGS_FILE = STORAGE_DIR / "runtime_settings.json"


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_settings() -> dict:
    settings = load_yaml(CONFIG_EXAMPLE_FILE)
    settings = deep_merge(settings, load_yaml(CONFIG_FILE))
    llm = settings.setdefault("llm", {})
    chat = llm.setdefault("chat", {})
    vision = llm.setdefault("vision", {})
    server = settings.setdefault("server", {})
    rag = settings.setdefault("rag", {})
    memory = settings.setdefault("memory", {})

    chat["api_key"] = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or chat.get("api_key", "") or llm.get("api_key", "")
    chat["base_url"] = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or chat.get("base_url", "https://api.deepseek.com/v1")
    chat["model"] = os.getenv("NUTRIFIT_CHAT_MODEL") or chat.get("model", "deepseek-v4-flash")

    vision["api_key"] = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or vision.get("api_key", "") or llm.get("api_key", "")
    vision["base_url"] = os.getenv("DASHSCOPE_BASE_URL") or os.getenv("OPENAI_BASE_URL") or vision.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vision["model"] = os.getenv("NUTRIFIT_VISION_MODEL") or vision.get("model", "qwen-vl-plus")

    server["host"] = os.getenv("NUTRIFIT_HOST") or server.get("host", "127.0.0.1")
    server["port"] = int(os.getenv("NUTRIFIT_PORT") or server.get("port", 8008))
    rag["top_k"] = int(rag.get("top_k", 6))
    memory["short_term_max_turns"] = int(memory.get("short_term_max_turns", 12))
    return settings


SETTINGS = load_settings()
CHAT_API_KEY = SETTINGS["llm"]["chat"].get("api_key", "")
CHAT_BASE_URL = SETTINGS["llm"]["chat"].get("base_url", "https://api.deepseek.com/v1")
CHAT_MODEL = SETTINGS["llm"]["chat"].get("model", "deepseek-v4-flash")
VISION_API_KEY = SETTINGS["llm"]["vision"].get("api_key", "")
VISION_BASE_URL = SETTINGS["llm"]["vision"].get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
VISION_MODEL = SETTINGS["llm"]["vision"].get("model", "qwen-vl-plus")
OPENAI_API_KEY = CHAT_API_KEY
OPENAI_BASE_URL = CHAT_BASE_URL
LLM_TEMPERATURE = float(SETTINGS["llm"].get("temperature", 0.2))
SHORT_TERM_MAX_TURNS = int(SETTINGS["memory"].get("short_term_max_turns", 12))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
SHORT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
LONG_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def get_features() -> dict:
    """功能开关：config.yaml 的 features 为默认值，运行时修改覆盖在 runtime_settings.json。

    每次调用都重新读文件，保证开关改动即时生效、无需重启。
    """
    from app.services.storage import read_json, write_json

    defaults = SETTINGS.get("features", {}) or {}
    runtime = read_json(RUNTIME_SETTINGS_FILE, {})
    if not isinstance(runtime, dict) or "features" not in runtime:
        runtime = {"features": {}}
    return {**defaults, **(runtime.get("features") or {})}


def set_feature(key: str, value: bool) -> dict:
    """更新单个功能开关，只写 runtime_settings.json，不动含 API Key 的 config.yaml。"""
    from app.services.storage import read_json, write_json

    current = get_features()
    if key not in current:
        raise KeyError(f"未知的功能开关：{key}")
    current[key] = bool(value)
    runtime = read_json(RUNTIME_SETTINGS_FILE, {})
    if not isinstance(runtime, dict):
        runtime = {}
    runtime["features"] = current
    write_json(RUNTIME_SETTINGS_FILE, runtime)
    return current
