from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.llm.prompts import SITE_SELECTION_REPORT_PROMPT
from app.llm.schemas import DeepSeekResult


class DeepSeekConfigError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
    ):
        settings = get_settings()
        from app.system_config.service import resolve_config_value

        self.api_key = (
            api_key if api_key is not None else resolve_config_value("deepseek_api_key", settings.deepseek_api_key)
        ).strip()
        self.base_url = (
            base_url or resolve_config_value("deepseek_base_url", settings.deepseek_base_url)
        ).rstrip("/")
        self.model = model or resolve_config_value("deepseek_model", settings.deepseek_model)
        self.client = client

    def ensure_configured(self) -> None:
        if not self.api_key:
            raise DeepSeekConfigError("DeepSeek API Key未配置")

    def generate_report(self, analysis_input: dict[str, Any], prompt: str = SITE_SELECTION_REPORT_PROMPT) -> DeepSeekResult:
        self.ensure_configured()
        user_content = json.dumps(analysis_input, ensure_ascii=False, default=str)
        started = time.perf_counter()
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=60)
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                client.close()
        content = self._extract_content(data)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return DeepSeekResult(
            content=content,
            model=str(data.get("model") or self.model),
            duration_ms=duration_ms,
            input_length=len(user_content),
            output_length=len(content),
        )

    def generate_chat(self, chat_input: dict[str, Any], prompt: str) -> DeepSeekResult:
        return self.generate_report(chat_input, prompt=prompt)

    def check_connectivity(self) -> None:
        self.ensure_configured()
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=10)
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "只回复OK"}],
                    "temperature": 0,
                    "max_tokens": 5,
                },
            )
            response.raise_for_status()
            self._extract_content(response.json())
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"])
        raise RuntimeError("DeepSeek response missing choices[0].message.content")
