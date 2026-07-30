"""
Contestant-model clients for generation.

Supported backends (add your own by matching the .generate(system, user) -> str contract):
  - AnthropicClient      : Claude models (sync or Batch API)
  - OpenAIClient         : GPT / OpenAI-compatible (incl. local vLLM/TGI, Qwen, etc.)
  - OpenRouterGemmaClient: Gemma via OpenRouter
  - GoogleClient         : Gemini models via google-genai

Every client uses temperature 0 for reproducibility and takes max_tokens.
Pin model + version strings in the paper — the contestant list IS the leaderboard.

Dependencies (install only what you use):
    pip install anthropic openai google-genai
"""

from __future__ import annotations
import os
import sys
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
if str(TASK_ROOT) not in sys.path:
    sys.path.insert(0, str(TASK_ROOT))

try:
    from .gemini_client import GoogleClient
    from .openrouter_gemma_client import OpenRouterGemmaClient
except ImportError:
    from gemini_client import GoogleClient
    from openrouter_gemma_client import OpenRouterGemmaClient


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicClient:
    def __init__(self, model: str, max_tokens: int = 1024):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system: str, user: str) -> str:
        msg = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens, temperature=0,
            system=system, messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    # Batch API for large runs (50% cheaper); mirror judge_clients.AnthropicBatchJudge
    def submit_batch(self, items: list[dict]) -> str:
        reqs = [{
            "custom_id": it["custom_id"],
            "params": {
                "model": self.model, "max_tokens": self.max_tokens, "temperature": 0,
                "system": it["system"],
                "messages": [{"role": "user", "content": it["user"]}],
            },
        } for it in items]
        return self.client.messages.batches.create(requests=reqs).id

    def batch_results(self, batch_id: str) -> dict[str, str]:
        out = {}
        for e in self.client.messages.batches.results(batch_id):
            if e.result.type == "succeeded":
                out[e.custom_id] = "".join(
                    b.text for b in e.result.message.content if b.type == "text")
            else:
                out[e.custom_id] = ""
        return out


# ---------------------------------------------------------------------------
# OpenAI-compatible (GPT, Qwen, local endpoints)
# ---------------------------------------------------------------------------

class OpenAIClient:
    def __init__(self, model: str, base_url: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", max_tokens: int = 1024):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=os.environ.get(api_key_env, "EMPTY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        )
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system: str, user: str) -> str:
        r = self.client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return r.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Custom OpenAI-compatible provider used by Task 1 labeling
# ---------------------------------------------------------------------------

class CustomClient:
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key_env: str = "CUSTOM_API_KEY",
        max_tokens: int = 1024,
        timeout: float = 60.0,
    ):
        from shared.custom_label_client import CustomLabelClient

        api_key = (
            os.environ.get(api_key_env)
            or CustomLabelClient.DEFAULT_API_KEY
        )
        self.client = CustomLabelClient(
            base_url=base_url or os.environ.get("CUSTOM_BASE_URL") or CustomLabelClient.DEFAULT_BASE_URL,
            api_key=api_key,
            timeout=timeout,
        )
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system: str, user: str) -> str:
        return self.client.text_call(
            request={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_client(backend: str, model: str, base_url: str | None = None,
                max_tokens: int = 1024, timeout: float = 60.0):
    if backend == "anthropic":
        return AnthropicClient(model, max_tokens)
    if backend == "openai":
        return OpenAIClient(model, base_url=base_url, max_tokens=max_tokens)
    if backend in {"openrouter", "openrouter-gemma"}:
        return OpenRouterGemmaClient(model, base_url=base_url, max_tokens=max_tokens, timeout=timeout)
    if backend in {"custom", "deepseek"}:
        return CustomClient(model, base_url=base_url, max_tokens=max_tokens, timeout=timeout)
    if backend == "google":
        return GoogleClient(model, max_tokens, timeout=timeout)
    raise ValueError(f"unknown backend {backend!r}")
