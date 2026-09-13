"""Vercel 冷启动演示数据播种。

线上函数实例冷启动后 /tmp 清空，首页会全空。每次冷启动检测到存储为空时，
写入一份演示饮食/身体数据，保证线上演示 URL 始终有内容可看。
仅 VERCEL 环境生效；已有数据（含用户真实记录）时不播种。
"""
import os
import uuid
from datetime import date, timedelta

from app.config import BODY_METRICS_FILE, PROFILE_FILE, RECORDS_FILE
from app.schemas import FoodLogItem, HealthProfile
from app.services.food import estimate_item
from app.services.health import calculate_profile
from app.services.storage import read_json, write_json


# 3 天饮食（offset 天，今天只有早/午，演示"进行中"状态）
MEALS = {
    -2: [
        ("早餐", "熟燕麦", 60), ("早餐", "低脂牛奶", 250),
        ("午餐", "熟糙米饭", 150), ("午餐", "鸡胸肉", 120), ("午餐", "西兰花", 150),
        ("晚餐", "三文鱼", 100), ("晚餐", "生菜", 100), ("晚餐", "番茄", 80),
        ("加餐", "苹果", 200),
    ],
    -1: [
        ("早餐", "全麦面包", 80), ("早餐", "鸡蛋", 50), ("早餐", "无糖酸奶", 150),
        ("午餐", "熟糙米饭", 150), ("午餐", "虾仁", 120), ("午餐", "黄瓜", 80),
        ("晚餐", "北豆腐", 150), ("晚餐", "番茄", 100), ("晚餐", "生菜", 80),
        ("加餐", "香蕉", 120),
    ],
    0: [
        ("早餐", "熟燕麦", 50), ("早餐", "低脂牛奶", 200), ("早餐", "蓝莓", 60),
        ("午餐", "熟糙米饭", 120), ("午餐", "鸡胸肉", 100), ("午餐", "西兰花", 120),
    ],
}
MEAL_TIMES = {"早餐": "07:40", "午餐": "12:15", "晚餐": "18:30", "加餐": "10:00"}


def _records():
    out = []
    today = date.today()
    for offset, items in MEALS.items():
        day = today + timedelta(days=offset)
        for meal_type, food_name, grams in items:
            rec = estimate_item(
                FoodLogItem(food_name=food_name, grams=grams, meal_type=meal_type),
                source="demo",
            )
            rec.id = str(uuid.uuid4())
            rec.created_at = f"{day} {MEAL_TIMES[meal_type]}"
            out.append(rec.model_dump())
    return out


def _body_metrics():
    weights = [71.0, 70.8, 70.7, 70.5, 70.4, 70.2, 70.1, 70.0, 69.9, 69.9, 69.8, 69.8]
    steps = [8234, 11205, 6890, 10433, 9571, 12048, 8122, 10021, 9348, 11002, 7633, 9654]
    today = date.today()
    rows = []
    for i, weight in enumerate(weights):
        day = today - timedelta(days=len(weights) - 1 - i)
        bmi = calculate_profile(HealthProfile(weight_kg=weight, height_cm=175))["bmi"]
        rows.append({
            "user_id": "default_user",
            "date": day.isoformat(),
            "weight_kg": weight,
            "bmi": bmi,
            "steps": steps[i],
            "sleep_hours": round(6.5 + (i % 4) * 0.5, 1),
            "exercise_minutes": 45 if i % 3 == 0 else 0,
            "note": "",
        })
    return rows


def seed_demo_data():
    """冷启动且存储为空时写入演示数据；任何已有数据都不覆盖。"""
    if not os.getenv("VERCEL"):
        return
    if read_json(PROFILE_FILE, None) or read_json(RECORDS_FILE, []) or read_json(BODY_METRICS_FILE, []):
        return
    profile = HealthProfile(
        gender="male", age=24, height_cm=175, weight_kg=69.8,
        target_weight_kg=65, activity_level="moderate", goal="fat_loss",
    )
    write_json(PROFILE_FILE, profile.model_dump())
    write_json(RECORDS_FILE, _records())
    write_json(BODY_METRICS_FILE, _body_metrics())
