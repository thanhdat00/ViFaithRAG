import json
from pathlib import Path
from typing import Any

from .openai_label_client import _strip_code_fence


class CustomLabelClient:
    DEFAULT_BASE_URL = ""
    DEFAULT_API_KEY = "EMPTY"

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, api_key: str = DEFAULT_API_KEY, timeout: float) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

        self._client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key, timeout=timeout)

    def single_call(self, *, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        content = self.text_call(request=request)
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("Custom provider output is not a JSON object.")
        return parsed, content

    def text_call(self, *, request: dict[str, Any]) -> str:
        model = "Qwen3.5-397B-A17B-FP8"
        messages = request.get("messages")
        if not model:
            raise ValueError("Custom provider request is missing model.")
        if not isinstance(messages, list):
            raise ValueError("Custom provider request is missing chat messages.")

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            extra_body={
                "chat_template_kwargs": {
                    "thinking": True,
                    "reasoning_effort": "low",
                },
            },
        )
        return (response.choices[0].message.content or "").strip()

    def batch_call(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
    ) -> dict[str, Any]:
        raise NotImplementedError("Custom provider does not support this project's OpenAI Batch API flow.")

    def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        raise NotImplementedError("Custom provider does not support this project's OpenAI Batch API flow.")

    def wait_for_batch(self, *, batch_id: str, poll_interval_seconds: float) -> dict[str, Any]:
        raise NotImplementedError("Custom provider does not support this project's OpenAI Batch API flow.")

    def batch_call_sequential(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
        batch_size: int,
        poll_interval_seconds: float,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Custom provider does not support this project's OpenAI Batch API flow.")
