import csv
import math
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from openai import OpenAI

from app.config import CHAT_MODEL, DATA_DIR, OPENAI_API_KEY, OPENAI_BASE_URL
from app.services.sse import sse_event


EXCLUDED_KNOWLEDGE_FILES = set()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def tokenize(text: str):
    return re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", (text or "").lower())


def chunk_text(text: str, chunk_size=520, overlap=90):
    text = normalize_text(text)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def infer_domain(path: Path):
    name = path.name
    if "体重" in name or "减脂" in name:
        return "体重管理"
    if "食谱" in name:
        return "食谱推荐"
    if "运动" in name:
        return "运动建议"
    if "睡眠" in name:
        return "生活方式"
    if "客服" in name or "合规" in name:
        return "客服合规"
    if path.parent.name == "food_database":
        return "食物营养库"
    return "健康知识"


class HashVectorizer:
    """sklearn HashingVectorizer 的轻量替代（char_wb、2-4 gram、L2 归一化）。

    Vercel 函数打包体积上限 225MB，scikit-learn/scipy 装不下，改用 numpy 实现。
    """

    def __init__(self, n_features=1536, ngram_range=(2, 4)):
        self.n_features = n_features
        self.ngram_range = ngram_range

    def _grams(self, text):
        text = (text or "").lower()
        out = []
        for word in text.split():
            for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
                padded = f" {word} "
                for i in range(len(padded) - n + 1):
                    out.append(padded[i : i + n])
        return out

    def transform(self, texts):
        mat = np.zeros((len(texts), self.n_features), dtype=np.float32)
        for i, text in enumerate(texts):
            for gram in self._grams(text):
                mat[i, zlib.crc32(gram.encode("utf-8")) % self.n_features] += 1.0
            norm = float(np.linalg.norm(mat[i])) or 1.0
            mat[i] /= norm
        return mat


class RAGService:
    def __init__(self):
        self.docs = []
        self.vectorizer = HashVectorizer(n_features=1536, ngram_range=(2, 4))
        self.matrix = None
        self.doc_tokens = []
        self.idf = {}
        self.avgdl = 1
        self.load()

    def load(self):
        docs = []
        for folder in [DATA_DIR / "knowledge_base", DATA_DIR / "recipes", DATA_DIR / "food_database"]:
            for path in sorted(folder.glob("*")):
                if path.is_dir() or path.name.startswith(".") or path.name in EXCLUDED_KNOWLEDGE_FILES:
                    continue
                if path.suffix.lower() in {".md", ".txt"}:
                    chunks = chunk_text(path.read_text(encoding="utf-8", errors="ignore"))
                elif path.suffix.lower() == ".csv":
                    chunks = []
                    with path.open("r", encoding="utf-8-sig", newline="") as file:
                        reader = csv.DictReader(file)
                        for row in reader:
                            chunks.append("；".join([f"{k}：{v}" for k, v in row.items() if v]))
                else:
                    continue
                for idx, chunk in enumerate(chunks, 1):
                    docs.append({
                        "source": path.name,
                        "domain": infer_domain(path),
                        "chunk_id": idx,
                        "content": chunk,
                    })
        self.docs = docs
        texts = [x["content"] for x in docs] or [""]
        self.matrix = self.vectorizer.transform(texts)
        self._build_bm25(texts)
        return self

    def _build_bm25(self, texts):
        self.doc_tokens = [tokenize(text) for text in texts]
        df = defaultdict(int)
        for tokens in self.doc_tokens:
            for token in set(tokens):
                df[token] += 1
        total = max(len(texts), 1)
        self.idf = {token: math.log(1 + (total - count + 0.5) / (count + 0.5)) for token, count in df.items()}
        self.avgdl = sum(len(tokens) for tokens in self.doc_tokens) / total

    def _bm25(self, query):
        q_tokens = tokenize(query)
        scores = []
        for tokens in self.doc_tokens:
            tf = Counter(tokens)
            doc_len = len(tokens) or 1
            score = 0
            for token in q_tokens:
                if token not in tf:
                    continue
                score += self.idf.get(token, 0) * (tf[token] * 2.5) / (
                    tf[token] + 1.5 * (1 - 0.75 + 0.75 * doc_len / max(self.avgdl, 1))
                )
            scores.append(score)
        return scores

    def retrieve(self, question: str, top_k=6):
        q_vec = self.vectorizer.transform([question])
        vector_scores = q_vec.dot(self.matrix.T)[0]  # 行已 L2 归一化，点积即余弦相似度
        bm25_scores = self._bm25(question)
        max_v = max(vector_scores) if len(vector_scores) else 1
        max_b = max(bm25_scores) if bm25_scores else 1
        rows = []
        for idx, doc in enumerate(self.docs):
            score = 0.65 * (vector_scores[idx] / max_v if max_v else 0) + 0.35 * (bm25_scores[idx] / max_b if max_b else 0)
            rows.append((idx, score))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [
            {"rank": rank, **self.docs[idx], "score": round(float(score), 4)}
            for rank, (idx, score) in enumerate(rows[:top_k], 1)
        ]

    def _prepare_answer(self, question: str, top_k: int):
        sources = self.retrieve(question, top_k)
        context = "\n\n".join([f"[{i}] {x['source']} | {x['domain']}\n{x['content']}" for i, x in enumerate(sources, 1)])
        if not OPENAI_API_KEY:
            fallback = "当前未配置 API Key，先给出基于知识库证据的抽取式摘要：\n" + "\n".join(
                [f"- {x['content'][:160]}... [{i}]" for i, x in enumerate(sources[:4], 1)]
            )
            return sources, None, fallback
        prompt = f"""你是健康管理平台的 AI 营养顾问。请基于证据回答，不做医疗诊断，不承诺治疗或快速瘦身。
回答结构：直接结论、执行建议、风险提示、引用来源。

用户问题：{question}

证据：
{context}
"""
        return sources, prompt, None

    def answer(self, question: str, top_k=6):
        sources, prompt, fallback = self._prepare_answer(question, top_k)
        if fallback is not None:
            answer = fallback
        else:
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = resp.choices[0].message.content
        return {"answer": answer, "sources": sources}

    def answer_stream(self, question: str, top_k=6):
        """SSE 流式回答：delta 逐块推送，done 携带最终全文与证据。"""
        sources, prompt, fallback = self._prepare_answer(question, top_k)

        def generate():
            parts = []
            try:
                if fallback is not None:
                    for line in fallback.splitlines(keepends=True):
                        parts.append(line)
                        yield sse_event("delta", content=line)
                else:
                    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
                    stream = client.chat.completions.create(
                        model=CHAT_MODEL,
                        temperature=0.2,
                        messages=[{"role": "user", "content": prompt}],
                        stream=True,
                    )
                    for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                        if delta:
                            parts.append(delta)
                            yield sse_event("delta", content=delta)
            except Exception as exc:
                yield sse_event("error", message=f"生成中断：{exc.__class__.__name__}")
            yield sse_event("done", answer="".join(parts), sources=sources)

        return generate()


rag_service = RAGService()
