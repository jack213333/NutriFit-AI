import csv
import uuid
from pathlib import Path
from typing import List

from app.config import DATA_DIR, RECORDS_FILE
from app.schemas import FoodLogItem, MealRecord
from app.services.storage import now_text, read_json, write_json


FOOD_DB = DATA_DIR / "food_database" / "common_foods.csv"


def load_foods():
    foods = []
    with FOOD_DB.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            foods.append(row)
    return foods


def find_food(food_name: str):
    foods = load_foods()
    for row in foods:
        if food_name in row["food_name"] or row["food_name"] in food_name:
            return row
    return None


def estimate_item(item: FoodLogItem, source: str = "manual", confidence=None) -> MealRecord:
    row = find_food(item.food_name)
    grams = float(item.grams)
    if row:
        factor = grams / 100
        calories = float(row["calories_per_100g"]) * factor
        protein = float(row["protein_per_100g"]) * factor
        fat = float(row["fat_per_100g"]) * factor
        carbs = float(row["carbs_per_100g"]) * factor
    else:
        calories = grams * 1.2
        protein = grams * 0.05
        fat = grams * 0.03
        carbs = grams * 0.15

    return MealRecord(
        id=str(uuid.uuid4()),
        created_at=now_text(),
        meal_type=item.meal_type,
        source=source,
        food_name=item.food_name,
        grams=grams,
        calories=round(calories, 1),
        protein=round(protein, 1),
        fat=round(fat, 1),
        carbs=round(carbs, 1),
        confidence=confidence,
    )


def add_records(records: List[MealRecord]):
    data = read_json(RECORDS_FILE, [])
    data.extend([record.model_dump() for record in records])
    write_json(RECORDS_FILE, data)
    return data


def list_records():
    return read_json(RECORDS_FILE, [])


def daily_summary():
    records = list_records()
    total = {
        "calories": round(sum(float(x.get("calories", 0)) for x in records), 1),
        "protein": round(sum(float(x.get("protein", 0)) for x in records), 1),
        "fat": round(sum(float(x.get("fat", 0)) for x in records), 1),
        "carbs": round(sum(float(x.get("carbs", 0)) for x in records), 1),
        "record_count": len(records),
    }
    return total
