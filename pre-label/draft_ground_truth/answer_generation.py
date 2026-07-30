import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.answer_generation import (  # noqa: E402
    ANSWER_GENERATION_PARTIAL_SYSTEM_PROMPT,
    ANSWER_GENERATION_PARTIAL_USER_PROMPT_TEMPLATE,
    ANSWER_GENERATION_YES_SYSTEM_PROMPT,
    ANSWER_GENERATION_YES_USER_PROMPT_TEMPLATE,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.custom_label_client import CustomLabelClient  # noqa: E402
from shared.gemini_label_client import GeminiLabelClient  # noqa: E402
from shared.openai_label_client import OpenAILabelClient  # noqa: E402

VALID_LABELS = {"YES", "PARTIAL", "NO", "AMBIGUOUS"}
NO_GROUND_TRUTH_ANSWER = "Ngữ cảnh được cung cấp không đủ thông tin để trả lời câu hỏi."
AMBIGUOUS_GROUND_TRUTH_ANSWER = "Câu hỏi được cung cấp không rõ ràng hoặc thiếu thông tin, cần làm rõ thêm."
DEFAULT_CUSTOM_BASE_URL = ""
DEFAULT_MAX_OUTPUT_TOKENS = 4096


def safe_name_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return cleaned.strip("._") or "model"


def output_name_stem(input_path: Path, model: str | None = None) -> str:
    if model is None:
        return input_path.stem
    return f"{input_path.stem}_{safe_name_part(model)}"


def default_output_path(input_path: Path, model: str | None = None) -> Path:
    suffix = input_path.suffix if input_path.suffix.lower() in {".json", ".jsonl"} else ".jsonl"
    return Path("output") / f"{output_name_stem(input_path, model)}_answered{suffix}"


def default_pretty_json_output_path(input_path: Path, model: str | None = None) -> Path:
    return Path("output") / f"{output_name_stem(input_path, model)}_answered.json"


def default_batch_input_path(input_path: Path, model: str | None = None) -> Path:
    return Path("tmp") / f"{output_name_stem(input_path, model)}_task2_batch_input.jsonl"


def default_batch_request_map_path(input_path: Path, model: str | None = None) -> Path:
    return Path("output") / f"{output_name_stem(input_path, model)}_task2_batch_request_map.jsonl"


def default_batch_response_path(input_path: Path, model: str | None = None) -> Path:
    return Path("tmp") / f"{output_name_stem(input_path, model)}_task2_batch_response.jsonl"


def default_batch_submission_log_path(input_path: Path, model: str | None = None) -> Path:
    return Path("output") / f"{output_name_stem(input_path, model)}_task2_batch_submission_log.jsonl"

def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return text

def clean_generated_answer(text: str) -> str:
    answer = _strip_code_fence(text).strip()
    if not answer:
        raise ValueError("Generated ground_truth_answer is empty.")
    if not answer.endswith((".", "!", "?", "]", ")", "”", "\"")):
        raise ValueError("Generated ground_truth_answer appears truncated.")
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", "-", "*", ">", "```")):
            raise ValueError("Generated ground_truth_answer contains markdown formatting.")
    return answer

def load_records(input_path: Path) -> tuple[list[dict[str, Any]], str]:
    if input_path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        with input_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    records.append(payload)
        return records, "jsonl"
    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        return records, "json_array"
    if isinstance(payload, dict):
        return [payload], "json_object"
    raise ValueError("Input must be JSON object, JSON array, or JSONL")

def save_records(records: list[dict[str, Any]], output_path: Path, input_kind: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_kind == "jsonl":
        with output_path.open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return
    payload: Any = records[0] if input_kind == "json_object" and records else records
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

def save_pretty_json(records: list[dict[str, Any]], output_path: Path, input_kind: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Any = records[0] if input_kind == "json_object" and records else records
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl_records(output_path: Path, records: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def remove_file_if_exists(path: Path) -> bool:
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError(f"Refusing to clear non-file path: {path}")
    path.unlink()
    return True


def build_label_client(args: argparse.Namespace) -> Any:
    provider = args.llm_provider.strip().lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Missing API key. Set environment variable: OPENAI_API_KEY")
        return OpenAILabelClient(api_key=api_key, timeout=args.timeout)

    if provider in {"custom", "deepseek"}:
        if args.batch_mode:
            raise ValueError("Custom provider supports direct single-call mode only. Use --no-batch-mode.")
        api_key = os.getenv("CUSTOM_API_KEY", "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip() or "EMPTY"
        return CustomLabelClient(base_url=args.custom_base_url, api_key=api_key, timeout=args.timeout)

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Missing API key. Set environment variable: GEMINI_API_KEY or GOOGLE_API_KEY")
        return GeminiLabelClient(api_key=api_key, timeout=args.timeout)

    raise ValueError(f"Unsupported LLM provider: {args.llm_provider}")

def append_jsonl_record(output_path: Path, record: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

def record_checkpoint_key(record: dict[str, Any]) -> str:
    for field in ("id", "_id", "sample_id"):
        value = str(record.get(field, "")).strip()
        if value:
            return f"{field}:{value}"
    
    context_items: list[dict[str, str]] = []
    raw_context = record.get("context", [])
    if isinstance(raw_context, list):
        for item in raw_context:
            if not isinstance(item, dict): continue
            context_items.append({
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "published_date": str(item.get("published_date", "")).strip(),
                "content": str(item.get("content", "")).strip(),
            })
    canonical = {
        "query": str(record.get("query", "")).strip(),
        "domain": str(record.get("domain", "")).strip(),
        "context": context_items,
    }
    digest = hashlib.md5(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"hash:{digest}"

def load_checkpoint_records(checkpoint_file: Path) -> tuple[list[dict[str, Any]], set[str]]:
    if not checkpoint_file.exists():
        return [], set()

    resumed_records: list[dict[str, Any]] = []
    processed_keys: set[str] = set()
    with checkpoint_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            resumed_records.append(payload)
            processed_keys.add(record_checkpoint_key(payload))
    return resumed_records, processed_keys

def get_context_doc_id(item: dict[str, Any]) -> str:
    doc_id = str(item.get("id", "")).strip()
    if doc_id:
        return doc_id
    return str(item.get("doc_id", "")).strip()


def get_context_doc_index(item: dict[str, Any], fallback_index: int) -> int:
    for field in ("doc_index", "index"):
        try:
            doc_index = int(item.get(field, 0))
        except (TypeError, ValueError):
            doc_index = 0
        if doc_index > 0:
            return doc_index
    return fallback_index

def build_chunks(contexts: Any, supporting_doc_ids: set[str], label: str) -> list[dict[str, str]]:
    if label in {"YES", "PARTIAL"} and not supporting_doc_ids:
        raise ValueError(f"Label {label} requires supporting_doc_ids for answer generation.")
    if not isinstance(contexts, list):
        return []

    chunks: list[dict[str, str]] = []
    for idx, item in enumerate(contexts):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        doc_id = get_context_doc_id(item)
        if not doc_id:
            continue
        if doc_id not in supporting_doc_ids:
            continue

        doc_index = get_context_doc_index(item, idx + 1)
        doc_label = f"Doc {doc_index}"
        chunk_id = f"{doc_id}#c0"

        chunks.append({
            "doc_id": doc_id,
            "doc_index": str(doc_index),
            "doc_label": doc_label,
            "chunk_id": chunk_id,
            "text": content,
        })
    return chunks

def build_user_prompt(query: str, chunks: list[dict[str, str]], label: str) -> str:
    supporting_docs = "".join(
        f"\n[{c['doc_label']}]\n{c['text']}\n"
        for c in chunks
    )
    if label == "YES":
        template = ANSWER_GENERATION_YES_USER_PROMPT_TEMPLATE
    elif label == "PARTIAL":
        template = ANSWER_GENERATION_PARTIAL_USER_PROMPT_TEMPLATE
    else:
        raise ValueError(f"Unsupported generated-answer label: {label}")
    return template.format(query=query, supporting_docs=supporting_docs)


def prompt_cache_key_for_label(label: str) -> str:
    if label == "YES":
        return "rag-answer-gen-yes"
    return "rag-answer-gen-partial"


def build_answer_generation_request(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    label: str,
    use_responses_api: bool = True,
) -> dict[str, Any]:
    if use_responses_api:
        return {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
            "prompt_cache_key": prompt_cache_key_for_label(label),
            "prompt_cache_retention": "24h",
            "store": False,
            "reasoning": {"effort": "none"},
        }

    return {
        "model": model,
        "max_completion_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "n": 1,
        "store": False,
        "reasoning": {"effort": "none"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }


def build_batch_request(
    *,
    custom_id: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    label: str,
    use_responses_api: bool = True,
) -> dict[str, Any]:
    request = build_answer_generation_request(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        label=label,
        use_responses_api=use_responses_api,
    )
    url = "/v1/responses" if use_responses_api else "/v1/chat/completions"
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": url,
        "body": request,
    }

def get_answerability_label(record: dict[str, Any]) -> str:
    labels = record.get("labels", {})
    if isinstance(labels, dict):
        answerability = labels.get("answerability")
        if isinstance(answerability, dict):
            return str(answerability.get("value", "")).strip().upper()
        if isinstance(answerability, str):
            return answerability.strip().upper()
    top_level_label = record.get("answerability")
    if isinstance(top_level_label, str):
        return top_level_label.strip().upper()
    return ""

def get_supporting_doc_ids(record: dict[str, Any]) -> set[str]:
    raw_doc_ids = record.get("supporting_doc_ids", [])
    if not isinstance(raw_doc_ids, list):
        return set()
    return {str(item).strip() for item in raw_doc_ids if str(item).strip()}

def fixed_ground_truth_answer(label: str) -> str | None:
    if label == "NO":
        return NO_GROUND_TRUTH_ANSWER
    if label == "AMBIGUOUS":
        return AMBIGUOUS_GROUND_TRUTH_ANSWER
    return None

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2: Generate Answer based on label")
    parser.add_argument("--input", type=Path, required=True, help="Input path (.json or .jsonl)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (.json or .jsonl). Defaults to output/<input_stem>_<model>_answered<input_suffix>.",
    )
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model name")
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "custom", "deepseek", "gemini"],
        default="openai",
        help=(
            "LLM provider to use. Batch mode supports openai and gemini; "
            "custom/deepseek use an OpenAI-compatible endpoint."
        ),
    )
    parser.add_argument(
        "--custom-base-url",
        "--deepseek-base-url",
        dest="custom_base_url",
        type=str,
        default=DEFAULT_CUSTOM_BASE_URL,
        help="OpenAI-compatible custom provider base URL. --deepseek-base-url is kept as a compatibility alias.",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--completion-window",
        type=str,
        default="24h",
        help="OpenAI Batch API completion window (e.g. 24h)",
    )
    parser.add_argument(
        "--batch-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable/disable OpenAI Batch API mode. Use --no-batch-mode for direct per-record calls.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of requests per OpenAI Batch submission. Sequential parts wait for the previous part to complete.",
    )
    parser.add_argument(
        "--batch-poll-interval",
        type=float,
        default=60.0,
        help="Seconds between OpenAI Batch status checks before submitting the next batch part.",
    )
    parser.add_argument(
        "--log-prompt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable prompt logging to task/task2/prompt_log.txt",
    )
    parser.add_argument(
        "--pretty-json-output",
        type=Path,
        default=None,
        help="Optional path to also save labeled results as pretty-formatted JSON.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the existing checkpoint/output and batch metadata for this run before processing from the beginning.",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if args.output is None:
        args.output = default_output_path(args.input, args.model)
    label_client = build_label_client(args)
    provider = args.llm_provider.strip().lower()
    use_responses_api = provider == "openai"

    if args.input.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        with args.input.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line: continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"JSONL line {line_number} is not a JSON object.")
                records.append(payload)
        input_kind = "jsonl"
    else:
        records, input_kind = load_records(args.input)

    if not records:
        raise ValueError("No valid records found in input.")

    prompt_log_file = Path("task") / "task2" / "prompt_log.txt"
    batch_submission_log_file = default_batch_submission_log_path(args.input, args.model)
    batch_request_map_file = default_batch_request_map_path(args.input, args.model)

    checkpoint_file = args.output if args.output.suffix.lower() == ".jsonl" else Path(f"{args.output}.progress.jsonl")
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    if args.clear_cache:
        removed_paths: list[str] = []
        for path in (checkpoint_file, args.output, batch_request_map_file, batch_submission_log_file):
            if remove_file_if_exists(path):
                removed_paths.append(str(path))
        if args.pretty_json_output is not None and remove_file_if_exists(args.pretty_json_output):
            removed_paths.append(str(args.pretty_json_output))
        if removed_paths:
            print(f"Cleared cache file(s): {', '.join(removed_paths)}")
        else:
            print("Clear cache requested; no existing checkpoint/output files found.")
    resumed_records, processed_keys = load_checkpoint_records(checkpoint_file)

    updated: list[dict[str, Any]] = list(resumed_records)
    failed_count = 0
    resumed_count = len(resumed_records)
    batch_requests: list[dict[str, Any]] = []
    batch_request_map_rows: list[dict[str, Any]] = []

    for idx, record in tqdm(enumerate(records, start=1), total=len(records), desc="Preparing", unit="record"):
        record_id = str(record.get("id") or record.get("_id") or record.get("sample_id") or f"record_{idx}")
        checkpoint_key = record_checkpoint_key(record)
        if checkpoint_key in processed_keys:
            continue
        try:
            query = str(record.get("query", "")).strip()
            if not query:
                raise ValueError(f"Record #{idx} missing 'query'.")
            
            label = get_answerability_label(record)
            if not label or label not in VALID_LABELS:
                raise ValueError(f"Record #{idx} has invalid or missing 'answerability' label: '{label}'. Needs task 1 first.")

            fixed_answer = fixed_ground_truth_answer(label)
            if fixed_answer is not None:
                record["ground_truth_answer"] = fixed_answer
                updated.append(record)
                append_jsonl_record(checkpoint_file, record)
                processed_keys.add(checkpoint_key)
                continue

            supporting_doc_ids = get_supporting_doc_ids(record)
            chunks = build_chunks(record.get("context", []), supporting_doc_ids, label)
            if not chunks:
                raise ValueError(f"Record #{idx} has no readable context matching supporting_doc_ids.")
            
            user_prompt = build_user_prompt(query, chunks, label)
            system_prompt = ANSWER_GENERATION_YES_SYSTEM_PROMPT if label == "YES" else ANSWER_GENERATION_PARTIAL_SYSTEM_PROMPT
            
            if args.log_prompt:
                with prompt_log_file.open("a", encoding="utf-8") as prompt_log:
                    prompt_log.write(f"{'=' * 20} USER PROMPT RECORD #{idx} ({label}) {'=' * 20}\n")
                    prompt_log.write(user_prompt)
                    prompt_log.write("\n\n")

            if args.batch_mode:
                custom_id = f"record_{idx}_{hashlib.md5(checkpoint_key.encode('utf-8')).hexdigest()[:12]}"
                batch_requests.append(build_batch_request(
                    custom_id=custom_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=args.model,
                    label=label,
                    use_responses_api=use_responses_api,
                ))
                batch_request_map_rows.append(
                    {
                        "custom_id": custom_id,
                        "record_id": record_id,
                        "checkpoint_key": checkpoint_key,
                        "record_index": idx,
                        "label": label,
                        "supporting_doc_ids": sorted(supporting_doc_ids),
                        "supporting_doc_indices": [int(chunk["doc_index"]) for chunk in chunks],
                    }
                )
            else:
                request = build_answer_generation_request(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=args.model,
                    label=label,
                    use_responses_api=use_responses_api,
                )
                answer = label_client.text_call(request=request)
                record["ground_truth_answer"] = clean_generated_answer(answer)
                updated.append(record)
                append_jsonl_record(checkpoint_file, record)
                processed_keys.add(checkpoint_key)
        except Exception as error:
            failed_count += 1
            print(f"Skip record #{idx} (id={record_id}): {error}")
            continue

    if args.batch_mode and batch_requests:
        write_jsonl_records(batch_request_map_file, batch_request_map_rows)
        batch_input_file = default_batch_input_path(args.input, args.model)
        batch_metadata_rows = label_client.batch_call_sequential(
            requests=batch_requests,
            input_file=batch_input_file,
            completion_window=args.completion_window,
            batch_size=args.batch_size,
            poll_interval_seconds=args.batch_poll_interval,
            submission_log_file=batch_submission_log_file,
        )
        print(f"Batch part(s) completed: {len(batch_metadata_rows)}")
        print(f"Request map saved to: {batch_request_map_file}")
        print(f"Submission log saved to: {batch_submission_log_file}")

    save_records(updated, args.output, input_kind)
    if args.pretty_json_output is not None:
        save_pretty_json(updated, args.pretty_json_output, input_kind)
    if args.log_prompt:
        print(f"Prompts saved to: {prompt_log_file}")
    if args.pretty_json_output is not None:
        print(f"Pretty JSON output saved to: {args.pretty_json_output}")
    print(f"Processed checkpoint saved to: {checkpoint_file}")
    print(f"Resumed from checkpoint: {resumed_count} record(s)")
    if args.batch_mode:
        print(f"Done. Batch mode on. Saved {len(updated)} immediate record(s), failed {failed_count}. Output: {args.output}")
    else:
        print(f"Done. Batch mode off. Generated answer for {len(updated)} record(s), failed {failed_count}. Output: {args.output}")

if __name__ == "__main__":
    main()
