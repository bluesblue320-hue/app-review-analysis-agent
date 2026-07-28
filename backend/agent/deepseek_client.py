"""Small DeepSeek client dedicated to controlled function calling."""

from __future__ import annotations

import json
from typing import Any, Callable

import requests

from ai_analysis import load_ai_config
from backend.agent.prompts import (
    TOOL_SYNTHESIS_SYSTEM_PROMPT,
    build_planner_messages,
)
from backend.core.config import settings


class ToolCallingError(Exception):
    """Base error for a recoverable model-side tool-calling failure."""


class ToolCallingTimeout(ToolCallingError):
    """Raised when DeepSeek does not respond before the configured deadline."""


class ToolCallingUnavailable(ToolCallingError):
    """Raised when DeepSeek is not configured or cannot be reached."""


class ToolCallingResponseError(ToolCallingError):
    """Raised when DeepSeek returns an invalid or unsuccessful response."""


class DeepSeekToolClient:
    def __init__(
        self,
        *,
        post_func: Callable[..., Any] = requests.post,
        config_loader: Callable[[], dict[str, Any]] = load_ai_config,
        timeout_seconds: int | None = None,
    ) -> None:
        self._post = post_func
        self._config_loader = config_loader
        self._timeout_seconds = timeout_seconds or settings.llm_timeout_seconds

    def plan(
        self,
        *,
        question: str,
        scope_label: str,
        tools: list[dict[str, object]],
    ) -> dict[str, Any]:
        payload = {
            "messages": build_planner_messages(question, scope_label),
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 1200,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        return self._chat(payload)

    def synthesize(
        self,
        *,
        question: str,
        scope_label: str,
        assistant_message: dict[str, Any],
        tool_messages: list[dict[str, Any]],
        tools: list[dict[str, object]],
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": TOOL_SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"分析范围：{scope_label}\n用户问题：{question}",
            },
            assistant_message,
            *tool_messages,
        ]
        response_message = self._chat(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": "none",
                "temperature": 0.1,
                "max_tokens": 2000,
                "stream": False,
                "thinking": {"type": "disabled"},
            }
        )
        content = response_message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ToolCallingResponseError("DeepSeek 未返回可用回答。")
        return content.strip()

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config_loader()
        if config.get("provider") != "deepseek":
            raise ToolCallingUnavailable("当前 AI_PROVIDER 不是 deepseek。")
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ToolCallingUnavailable("未配置 DEEPSEEK_API_KEY。")

        request_payload = {"model": config.get("model"), **payload}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        try:
            response = self._post(
                config.get("base_url"),
                headers=headers,
                json=request_payload,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as exc:
            raise ToolCallingTimeout("DeepSeek 请求超时。") from exc
        except requests.RequestException as exc:
            raise ToolCallingUnavailable(f"DeepSeek 请求失败：{exc}") from exc

        if response.status_code != 200:
            raise ToolCallingResponseError(
                f"DeepSeek 返回异常状态码 {response.status_code}。"
            )
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ToolCallingResponseError("DeepSeek 返回结构异常。") from exc
        if not isinstance(message, dict):
            raise ToolCallingResponseError("DeepSeek message 结构异常。")

        normalized = {
            "role": "assistant",
            "content": message.get("content"),
        }
        tool_calls = message.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, list):
                raise ToolCallingResponseError("DeepSeek tool_calls 结构异常。")
            normalized["tool_calls"] = json.loads(json.dumps(tool_calls))
        return normalized
