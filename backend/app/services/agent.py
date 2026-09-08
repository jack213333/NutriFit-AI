import re
from typing import Dict, List, Tuple

from openai import OpenAI

from app.config import CHAT_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY, OPENAI_BASE_URL, PROFILE_FILE, get_features
from app.schemas import AgentChatRequest, AgentChatResponse, FoodLogItem, HealthProfile
from app.services.body_metrics import add_body_metric, parse_body_metric_from_text, trend_summary
from app.services.food import add_records, daily_summary, estimate_item, list_records
from app.services.health import calculate_profile
from app.services.memory import get_recent_context, new_session_id, save_turn
from app.services.rag import rag_service
from app.services.sse import sse_event
from app.services.storage import read_json


FORBIDDEN_TERMS = ["治疗", "治愈", "保证瘦", "一定瘦", "替代药物", "降糖药替代", "吃了就瘦"]


class NutriFitAgent:
    """Plan-and-Solve + ReAct + Reflection agent for nutrition workflows."""

    def classify_intent(self, message: str) -> str:
        if any(word in message for word in ["体重", "腰围", "体脂", "睡眠", "步数"]) and re.search(r"\d", message):
            return "body_metric_recording"
        if any(word in message for word in ["吃了", "记录", "早餐", "午餐", "晚餐", "加餐"]) and re.search(r"\d", message):
            return "meal_logging"
        if any(word in message for word in ["食谱", "一周", "安排", "搭配", "方案", "推荐", "计划"]):
            return "meal_plan"
        if any(word in message for word in ["运动", "跑步", "力量", "训练", "有氧"]):
            return "exercise_advice"
        if any(word in message for word in ["睡眠", "熬夜", "压力", "暴食"]):
            return "sleep_stress_advice"
        if any(word in message for word in ["话术", "能不能说", "合规", "宣传"]):
            return "compliance_check"
        if any(word in message for word in ["热量", "减脂", "减肥", "蛋白质", "轻食", "控糖"]):
            return "nutrition_qa"
        return "general_health_qa"

    def plan(self, intent: str) -> List[Dict]:
        steps = [
            {"stage": "Plan", "message": f"识别用户意图：{intent}"},
            {"stage": "Plan", "message": "读取会话上下文、身体档案、长期健康档案、今日饮食记录和知识库证据。"},
        ]
        if intent == "body_metric_recording":
            steps.append({"stage": "Plan", "message": "从文本中抽取体重、腰围、体脂、睡眠、步数等指标，并写入长期健康档案。"})
        elif intent == "meal_logging":
            steps.append({"stage": "Plan", "message": "解析饮食文本，估算热量与营养素，并写入热量记录。"})
        elif intent == "meal_plan":
            steps.append({"stage": "Plan", "message": "结合当前页面表单、已保存档案、长期趋势、今日饮食和 RAG 证据生成个性化方案。"})
        else:
            steps.append({"stage": "Plan", "message": "调用 RAG 检索健康知识库，生成带证据的专业回答。"})
        steps.append({"stage": "Plan", "message": "执行 Reflection，检查合规性、可执行性和风险提示。"})
        return steps

    def parse_food_items(self, message: str) -> List[FoodLogItem]:
        items = []
        for name, grams in re.findall(r"([\u4e00-\u9fffA-Za-z]{2,12})\s*(\d+(?:\.\d+)?)\s*(?:g|克|公斤|千克)?", message):
            value = float(grams)
            if "公斤" in message or "千克" in message:
                value *= 1000
            if name not in {"今天", "中午", "晚上", "早上", "早餐", "午餐", "晚餐", "体重", "腰围", "体脂"}:
                meal = "午餐"
                if "早餐" in message or "早上" in message:
                    meal = "早餐"
                elif "晚餐" in message or "晚上" in message:
                    meal = "晚餐"
                elif "加餐" in message:
                    meal = "加餐"
                items.append(FoodLogItem(food_name=name, grams=value, meal_type=meal))
        return items[:6]

    def load_profile_context(self) -> Dict:
        saved_profile = read_json(PROFILE_FILE, None)
        if saved_profile:
            try:
                profile = HealthProfile(**saved_profile)
                return {"profile": saved_profile, "analysis": calculate_profile(profile)}
            except Exception:
                return {"profile": saved_profile, "analysis": None}
        default_profile = HealthProfile()
        return {"profile": None, "analysis": calculate_profile(default_profile)}

    def load_food_context(self) -> Dict:
        records = list_records()
        return {
            "today_summary": daily_summary(),
            "recent_records": records[-8:],
        }

    def run_tools(self, intent: str, request: AgentChatRequest, session_id: str, use_long_term: bool = True) -> Tuple[List[str], List[Dict], Dict, List[Dict]]:
        trace = []
        tools_used = []
        sources: List[Dict] = []
        tool_state: Dict = {}

        short_context = get_recent_context(session_id) if request.use_memory else {"summary": "", "turns": []}
        if use_long_term:
            long_memory = trend_summary(request.user_id)
        else:
            long_memory = {"summary": "（长期身体记忆已关闭，改用当前页面数据）", "records": [], "latest": None}
        profile_context = self.load_profile_context()
        food_context = self.load_food_context()

        tools_used.extend(["ShortTermMemory", "HealthProfileReader", "FoodRecordReader"])
        if use_long_term:
            tools_used.append("LongTermBodyMemory")
        trace.append({
            "stage": "ReAct",
            "thought": "方案推荐需要同时读取当前会话、身体档案、长期身体趋势和今日饮食记录。",
            "action": "ReadUserContext",
            "observation": (
                f"会话 {len(short_context['turns'])} 轮；"
                f"长期身体记录 {len(long_memory['records'])} 条；"
                f"今日饮食记录 {food_context['today_summary'].get('record_count', 0)} 条。"
            ),
        })
        tool_state["short_context"] = short_context
        tool_state["long_memory"] = long_memory
        tool_state["profile_context"] = profile_context
        tool_state["food_context"] = food_context

        metric_record = parse_body_metric_from_text(request.message, request.user_id)
        if intent == "body_metric_recording" and metric_record:
            saved = add_body_metric(metric_record)
            tools_used.append("BodyMetricRecorder")
            tool_state["saved_metric"] = saved
            trace.append({
                "stage": "ReAct",
                "thought": "用户提供了身体指标。",
                "action": "BodyMetricRecorder",
                "observation": "已写入长期健康档案。",
            })

        if intent == "meal_logging":
            items = self.parse_food_items(request.message)
            if items:
                records = [estimate_item(item, source="agent_text") for item in items]
                add_records(records)
                tools_used.append("MealRecordTool")
                tool_state["meal_records"] = [record.model_dump() for record in records]
                tool_state["food_context"] = self.load_food_context()
                trace.append({
                    "stage": "ReAct",
                    "thought": "用户提供了饮食文本。",
                    "action": "MealRecordTool",
                    "observation": f"已记录 {len(records)} 个食物。",
                })

        if request.use_rag:
            sources = rag_service.retrieve(request.message, request.top_k)
            tools_used.append("RAGRetrieverTool")
            trace.append({
                "stage": "ReAct",
                "thought": "需要知识库证据支撑回答。",
                "action": "RAGRetrieverTool",
                "observation": f"召回 {len(sources)} 条证据。",
            })

        tools_used.append("ComplianceGuardTool")
        return tools_used, sources, tool_state, trace

    def build_prompt(self, request: AgentChatRequest, intent: str, sources: List[Dict], tool_state: Dict) -> str:
        short_turns = tool_state.get("short_context", {}).get("turns", [])
        short_text = "\n".join([f"用户：{x.get('user')}\n助手：{x.get('assistant')}" for x in short_turns[-4:]])
        long_memory = tool_state.get("long_memory", {})
        profile_context = tool_state.get("profile_context", {})
        food_context = tool_state.get("food_context", {})
        source_text = "\n\n".join([f"[{i}] {src['source']} | {src['domain']}\n{src['content']}" for i, src in enumerate(sources, 1)])
        saved_metric = tool_state.get("saved_metric")
        meal_records = tool_state.get("meal_records")

        return f"""你是 NutriFit AI 的专业健康体重管理 Agent。你遵循 Plan-and-Solve + ReAct + Reflection 工作流：先理解目标，再基于工具结果回答，最后进行健康合规复核。

非常重要：
1. 下面的“用户消息”中可能包含前端当前表单里的身体数据，即使这些数据还没有点击保存，也必须用于方案推荐。
2. 如果用户消息、已保存身体档案、长期健康档案之间存在差异，优先使用“用户消息中的当前页面表单数据”，并在回答中说明“以下基于当前页面填写的数据估算”。
3. 生成方案时必须显式参考已有的身高、体重、腰围、体脂率、睡眠时长、步数、运动分钟、活动水平、推荐热量、今日饮食记录等数据。
4. 只要任意来源里有身体或饮食数据，就不要说“你尚未提供身体数据”。

专业表达要求：
1. 先给直接结论。
2. 再说明依据和原因。
3. 给出饮食、运动、睡眠和记录建议。
4. 给出风险提示和适用边界。
5. 使用 [1][2] 形式引用知识库证据。
6. 不做医疗诊断，不承诺治疗，不承诺快速瘦身。

用户意图：{intent}

用户消息：
{request.message}

已保存身体档案：
{profile_context.get("profile") or "暂无已保存身体档案"}

已保存身体档案计算结果：
{profile_context.get("analysis") or "暂无"}

长期健康档案摘要：
{long_memory.get("summary", "暂无")}

长期健康档案最新记录：
{long_memory.get("latest") or "暂无"}

长期健康档案记录数：
{len(long_memory.get("records", []))}

今日饮食汇总：
{food_context.get("today_summary") or "暂无"}

最近饮食记录：
{food_context.get("recent_records") or "暂无"}

短期会话上下文：
{short_text or "暂无"}

本轮自动写入的身体指标：
{saved_metric or "无"}

本轮自动写入的饮食：
{meal_records or "无"}

检索证据：
{source_text or "无"}
"""

    def generate_answer(self, request: AgentChatRequest, intent: str, sources: List[Dict], tool_state: Dict) -> str:
        if OPENAI_API_KEY:
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                temperature=LLM_TEMPERATURE,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业、审慎、合规的健康体重管理顾问。必须优先使用用户当前提供的身体数据和饮食记录。",
                    },
                    {"role": "user", "content": self.build_prompt(request, intent, sources, tool_state)},
                ],
            )
            return response.choices[0].message.content

        profile_context = tool_state.get("profile_context", {})
        food_context = tool_state.get("food_context", {})
        long_memory = tool_state.get("long_memory", {})
        lines = ["结论：当前未配置 API Key，系统先基于当前身体数据、饮食记录和知识库证据给出抽取式建议。"]
        lines.append(f"当前页面数据已接收：{request.message[:800]}")
        lines.append(f"已读取身体档案：{profile_context.get('profile') or '暂无已保存档案，请以前端当前填写数据为准。'}")
        lines.append(f"健康指标估算：{profile_context.get('analysis') or '暂无'}")
        lines.append(f"长期趋势：{long_memory.get('summary', '暂无')}")
        lines.append(f"今日饮食：{food_context.get('today_summary') or '暂无'}")
        if tool_state.get("saved_metric"):
            lines.append(f"已记录身体指标：{tool_state['saved_metric']}")
        if tool_state.get("meal_records"):
            lines.append(f"已记录饮食：{len(tool_state['meal_records'])} 项。")
        for idx, src in enumerate(sources[:4], 1):
            lines.append(f"{idx}. {src['content'][:180]}... [{idx}]")
        lines.append("风险提示：以上为健康科普和生活方式建议，特殊疾病、孕期或进食障碍风险请咨询医生或注册营养师。")
        return "\n".join(lines)

    def reflect(self, answer: str, intent: str, add_risk_notice: bool = True) -> Tuple[str, List[Dict]]:
        trace = []
        revised = answer
        hit_terms = [term for term in FORBIDDEN_TERMS if term in revised]
        if hit_terms:
            for term in hit_terms:
                revised = revised.replace(term, "辅助健康管理")
            trace.append({"stage": "Reflection", "check": "合规词检查", "observation": f"替换潜在风险表达：{hit_terms}"})
        else:
            trace.append({"stage": "Reflection", "check": "合规词检查", "observation": "未发现明显医疗化或绝对化表达。"})
        if add_risk_notice and "医生" not in revised and intent in {"nutrition_qa", "body_metric_recording", "sleep_stress_advice", "meal_plan"}:
            revised += "\n\n风险提示：以上内容仅用于健康科普和生活方式建议，如有基础疾病、孕期、长期失眠、进食障碍或用药情况，请咨询医生或注册营养师。"
            trace.append({"stage": "Reflection", "check": "风险提示", "observation": "已补充专业边界提示。"})
        return revised, trace

    def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        session_id = request.session_id or new_session_id()
        features = get_features()
        intent = self.classify_intent(request.message)
        trace = self.plan(intent)
        tools_used, sources, tool_state, react_trace = self.run_tools(
            intent, request, session_id, use_long_term=features.get("enable_long_term_memory", True)
        )
        trace.extend(react_trace)
        answer = self.generate_answer(request, intent, sources, tool_state)
        answer, reflection_trace = self.reflect(
            answer, intent, add_risk_notice=features.get("enable_health_risk_notice", True)
        )
        trace.extend(reflection_trace)
        save_turn(session_id, request.message, answer, intent, tools_used)
        return AgentChatResponse(
            session_id=session_id,
            intent=intent,
            answer=answer,
            sources=sources,
            tools_used=tools_used,
            agent_trace=trace if features.get("enable_agent_trace", True) else [],
            memory_used={
                "short_term": bool(tool_state.get("short_context", {}).get("turns")),
                "long_term_records": len(tool_state.get("long_memory", {}).get("records", [])),
                "profile_loaded": bool(tool_state.get("profile_context", {}).get("profile")),
                "food_records": tool_state.get("food_context", {}).get("today_summary", {}).get("record_count", 0),
            },
        )

    def chat_stream(self, request: AgentChatRequest):
        """SSE 流式 agent 对话。

        stage 事件实时推送 Plan/ReAct/Reflection 过程；delta 逐块推送答案原文；
        流结束后执行 reflect 合规修正，done 携带修正版全文（与流式版不同时前端以 done 为准）。
        """
        session_id = request.session_id or new_session_id()
        features = get_features()
        intent = self.classify_intent(request.message)
        emit_trace = features.get("enable_agent_trace", True)

        def generate():
            trace = self.plan(intent)
            if emit_trace:
                for step in trace:
                    yield sse_event("stage", step=step)
            tools_used, sources, tool_state, react_trace = self.run_tools(
                intent, request, session_id, use_long_term=features.get("enable_long_term_memory", True)
            )
            trace.extend(react_trace)
            if emit_trace:
                for step in react_trace:
                    yield sse_event("stage", step=step)

            parts = []
            try:
                if OPENAI_API_KEY:
                    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
                    stream = client.chat.completions.create(
                        model=CHAT_MODEL,
                        temperature=LLM_TEMPERATURE,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是专业、审慎、合规的健康体重管理顾问。必须优先使用用户当前提供的身体数据和饮食记录。",
                            },
                            {"role": "user", "content": self.build_prompt(request, intent, sources, tool_state)},
                        ],
                        stream=True,
                    )
                    for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                        if delta:
                            parts.append(delta)
                            yield sse_event("delta", content=delta)
                else:
                    fallback = self.generate_answer(request, intent, sources, tool_state)
                    for line in fallback.splitlines(keepends=True):
                        parts.append(line)
                        yield sse_event("delta", content=line)
            except Exception as exc:
                yield sse_event("error", message=f"生成中断：{exc.__class__.__name__}")

            answer, reflection_trace = self.reflect(
                "".join(parts) or "生成中断，请稍后重试。",
                intent,
                add_risk_notice=features.get("enable_health_risk_notice", True),
            )
            trace.extend(reflection_trace)
            if emit_trace:
                for step in reflection_trace:
                    yield sse_event("stage", step=step)
            save_turn(session_id, request.message, answer, intent, tools_used)
            yield sse_event(
                "done",
                session_id=session_id,
                intent=intent,
                answer=answer,
                sources=sources,
                tools_used=tools_used,
                agent_trace=trace if emit_trace else [],
                memory_used={
                    "short_term": bool(tool_state.get("short_context", {}).get("turns")),
                    "long_term_records": len(tool_state.get("long_memory", {}).get("records", [])),
                    "profile_loaded": bool(tool_state.get("profile_context", {}).get("profile")),
                    "food_records": tool_state.get("food_context", {}).get("today_summary", {}).get("record_count", 0),
                },
            )

        return generate()


agent_service = NutriFitAgent()
agent = agent_service
