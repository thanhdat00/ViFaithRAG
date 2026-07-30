"""
OpenRouter client for the Gemma contestant.

Environment:
    OPENROUTER_API_KEY   required
    OPENROUTER_BASE_URL  optional, defaults to https://openrouter.ai/api/v1
    OPENROUTER_REFERER   optional, sent as HTTP-Referer for OpenRouter rankings
    OPENROUTER_TITLE     optional, sent as X-Title for OpenRouter rankings
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any

import requests


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_GEMMA_MODEL = "gemma-4-31b-it"


class OpenRouterGemmaClient:
    def __init__(
        self,
        model: str = DEFAULT_GEMMA_MODEL,
        base_url: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        max_tokens: int = 2048,
        timeout: float = 60.0,
        raw_response_log: str | Path | None = None,
    ) -> None:
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Missing API key. Set environment variable: {api_key_env}")

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        referer = os.getenv("OPENROUTER_REFERER", "").strip()
        title = os.getenv("OPENROUTER_TITLE", "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self.headers = headers
        self.model = model or DEFAULT_GEMMA_MODEL
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.raw_response_log = self._default_raw_response_log(raw_response_log)
        self._raw_response_log_lock = Lock()

    def generate(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "reasoning": {
                "enabled": False,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        self._log_raw_response(response)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {data}")
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError(f"OpenRouter returned malformed choice: {choices[0]}")
        return str(message.get("content") or "").strip()

    def _log_raw_response(self, response: requests.Response) -> None:
        self.raw_response_log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "logged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model,
            "status_code": response.status_code,
            "raw_response": self._response_payload(response),
        }
        with self._raw_response_log_lock:
            with self.raw_response_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    @classmethod
    def _default_raw_response_log(cls, raw_response_log: str | Path | None) -> Path:
        if raw_response_log is not None:
            return Path(raw_response_log)

        env_path = os.getenv("OPENROUTER_RAW_RESPONSE_LOG", "").strip()
        if env_path:
            return Path(env_path)

        return Path("tmp") / "contestants_openrouter_gemma_raw_responses.jsonl"

    @staticmethod
    def _response_payload(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text
