from typing import List, Optional

from pydantic import BaseModel, Field


class HealthProfile(BaseModel):
    gender: str = Field(default="female")
    age: int = Field(default=28, ge=10, le=100)
    height_cm: float = Field(default=165, ge=80, le=230)
    weight_kg: float = Field(default=62, ge=20, le=250)
    target_weight_kg: float = Field(default=55, ge=20, le=250)
    activity_level: str = Field(default="light")
    goal: str = Field(default="fat_loss")


class ChatRequest(BaseModel):
    question: str
    top_k: int = 6


class FoodLogItem(BaseModel):
    food_name: str
    grams: float = 100
    meal_type: str = "午餐"


class FoodLogRequest(BaseModel):
    items: List[FoodLogItem]
    note: str = ""


class MealRecord(BaseModel):
    id: str
    created_at: str
    meal_type: str
    source: str
    food_name: str
    grams: float
    calories: float
    protein: float
    fat: float
    carbs: float
    confidence: Optional[float] = None
    note: str = ""


class BodyMetricRecord(BaseModel):
    user_id: str = "default_user"
    date: str = ""
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None
    body_fat_percent: Optional[float] = None
    sleep_hours: Optional[float] = None
    steps: Optional[int] = None
    exercise_minutes: Optional[int] = None
    note: str = ""


class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: str = "default_user"
    use_memory: bool = True
    use_rag: bool = True
    top_k: int = 6


class AgentChatResponse(BaseModel):
    session_id: str
    answer: str
    intent: str
    tools_used: List[str]
    sources: List[dict]
    memory_used: dict
    agent_trace: List[dict]


class FeatureToggleRequest(BaseModel):
    key: str
    value: bool
