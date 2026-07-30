import hashlib
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.answerability_label import ANSWERABILITY_USER_PROMPT_TEMPLATE  # noqa: E402


ANSWERABILITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answerability": {"type": "string", "enum": ["YES", "PARTIAL", "NO", "AMBIGUOUS"]},
        "missing_or_needed_clarification": {
            "type": "array",
            "items": {"type": "string"},
        },
        "supporting_doc_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "answerability",
        "missing_or_needed_clarification",
        "supporting_doc_ids",
    ],
    "additionalProperties": False,
}

ANSWERABILITY_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "answerability_result",
        "strict": True,
        "schema": ANSWERABILITY_SCHEMA,
    },
}

ANSWERABILITY_RESPONSE_TEXT_FORMAT: dict[str, Any] = {
    "format": {
        "type": "json_schema",
        "name": "answerability_result",
        "strict": True,
        "schema": ANSWERABILITY_SCHEMA,
    }
}


def build_chunks(contexts: Any) -> list[dict[str, str]]:
    if not isinstance(contexts, list):
        return []

    chunks: list[dict[str, str]] = []
    for idx, item in enumerate(contexts):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        raw_doc_id = str(item.get("id", "")).strip()
        if raw_doc_id:
            doc_id = raw_doc_id
        else:
            seed = f"{item.get('url', '')}|{item.get('title', '')}|{idx}|{content[:200]}"
            doc_id = f"doc_{hashlib.md5(seed.encode('utf-8')).hexdigest()[:12]}"
            item["id"] = doc_id
        chunk_id = f"{doc_id}#c0"
        chunks.append({"doc_id": doc_id, "chunk_id": chunk_id, "text": content})
    return chunks


def build_user_prompt(query: str, chunks: list[dict[str, str]]) -> str:
    chunks_text = "".join(f"\n[{c['chunk_id']}] (doc_id={c['doc_id']})\n{c['text']}\n" for c in chunks)
    return ANSWERABILITY_USER_PROMPT_TEMPLATE.format(query=query, chunks_text=chunks_text)


def build_answerability_request(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    use_responses_api: bool = False,
) -> dict[str, Any]:
    if use_responses_api:
        return {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "prompt_cache_key": "rag-answerability",
            "prompt_cache_retention": "24h",
            "max_output_tokens": 400,
            "store": False,
            "reasoning": {"effort": "none"},
            "text": ANSWERABILITY_RESPONSE_TEXT_FORMAT,
        }

    return {
        "model": model,
        "max_completion_tokens": 400,
        "n": 1,
        "store": False,
        "reasoning": {"effort": "none"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": ANSWERABILITY_JSON_SCHEMA,
    }


def build_batch_request(*, custom_id: str, request: dict[str, Any]) -> dict[str, Any]:
    url = "/v1/responses" if "instructions" in request and "input" in request else "/v1/chat/completions"
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": url,
        "body": request,
    }
