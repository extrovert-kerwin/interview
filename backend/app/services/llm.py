"""统一 LLM 工厂（智谱 GLM）。

为了让各 agent 代码零修改，这里提供一个轻量 shim：
- 暴露 `.invoke(messages)` 方法，接收一组 LangChain 的 SystemMessage/HumanMessage/AIMessage
- 返回一个带有 `.content` 字段的对象

这样既复用了 LangGraph + langchain_core.messages 的生态，又不依赖任何 langchain-* 厂商包。
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from zhipuai import ZhipuAI

from app.config import get_settings


@dataclass
class LLMResult:
    content: str


_CALL_LOCK = threading.Lock()
_LAST_CALL_AT = 0.0
_MIN_CALL_INTERVAL_SECONDS = 2.0
_RATE_LIMIT_RETRIES = 2


def _to_zhipu_messages(messages: Iterable[BaseMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = "user"
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out


class ZhipuChat:
    """与 LangChain ChatModel 形状对齐的极简封装。"""

    def __init__(self, model: str, temperature: float, max_tokens: int, api_key: str):
        self._client = ZhipuAI(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def invoke(self, messages: Iterable[BaseMessage]) -> LLMResult:
        payload = list(messages)
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                resp = self._create_completion(payload)
                break
            except Exception as e:
                if not _is_rate_limit_error(e) or attempt >= _RATE_LIMIT_RETRIES:
                    raise
                time.sleep(2.0 * (attempt + 1))
        choice = resp.choices[0]
        text = choice.message.content or ""
        # 推理模型（如 glm-4.7-flash）thinking 阶段在 reasoning_content，
        # 若 content 为空说明 max_tokens 太小、被推理过程耗尽
        if not text and choice.finish_reason == "length":
            raise RuntimeError(
                f"模型 {self._model} 返回空 content 且 finish_reason=length，"
                f"推理 token 耗尽——已将 max_tokens 调大，请重试"
            )
        return LLMResult(content=text)

    def _create_completion(self, messages: list[BaseMessage]):
        global _LAST_CALL_AT
        with _CALL_LOCK:
            elapsed = time.monotonic() - _LAST_CALL_AT
            if elapsed < _MIN_CALL_INTERVAL_SECONDS:
                time.sleep(_MIN_CALL_INTERVAL_SECONDS - elapsed)
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=_to_zhipu_messages(messages),
                temperature=max(0.01, min(0.99, self._temperature)),
                max_tokens=self._max_tokens,
            )
            _LAST_CALL_AT = time.monotonic()
            return resp


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error)
    return "429" in text or "1302" in text or "rate limit" in text.lower()


def chat(temperature: float = 0.4, max_tokens: int = 2048) -> ZhipuChat:
    settings = get_settings()
    if not settings.zhipuai_api_key:
        raise RuntimeError("未配置 ZHIPUAI_API_KEY，请在 backend/.env 中填写")
    return ZhipuChat(
        model=settings.zhipuai_model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=settings.zhipuai_api_key,
    )


def extract_json(text: str) -> Any:
    """从 LLM 输出里捞 JSON。容忍 ```json 包裹与杂前后缀。"""
    if not text:
        raise ValueError("空响应")

    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = min(
        (i for i in (text.find("{"), text.find("[")) if i >= 0),
        default=-1,
    )
    end = max(text.rfind("}"), text.rfind("]"))
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"无法解析为 JSON: {text[:200]}…")
