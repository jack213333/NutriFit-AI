"""Vercel 入口：把 backend 加入 sys.path 后暴露 FastAPI 应用。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402
