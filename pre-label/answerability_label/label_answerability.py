import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from llm_request import build_answerability_request, build_batch_request, build_chunks, build_user_prompt  # noqa: E402
from prompts.answerability_label import ANSWERABILITY_SYSTEM_PROMPT  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.custom_label_client import CustomLabelClient  # noqa: E402
from shared.gemini_label_client import GeminiLabelClient  # noqa: E402
from shared.openai_label_client import OpenAILabelClient  # noqa: E402


VALID_LABELS = {"YES", "PARTIAL", "NO", "AMBIGUOUS"}
DEFAULT_CUSTOM_BASE_URL = ""


def load_records(input_path: Path) -> tuple[list[dict[str, Any]], str]:
    if input_path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        with input_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"JSONL line {line_number} is not a JSON object.")
                records.append(payload)
        return records, "jsonl"

    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        records = []
        for idx, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"JSON array item {idx} is not a JSON object.")
            records.append(item)
        return records, "json_array"
    if isinstance(payload, dict):
        return [payload], "json_object"
    raise ValueError("Input must be JSON object, JSON array, or JSONL with JSON objects.")


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


def record_id_value(record: dict[str, Any], fallback: str = "") -> str:
    return str(record.get("id") or record.get("_id") or record.get("sample_id") or fallback).strip()


def compact_labeled_record(record: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "id": record_id_value(record),
        "mongo_record_id": str(record.get("mongo_record_id") or ""),
        "query": str(record.get("query") or ""),
        "domain": str(record.get("domain") or ""),
        "labels": record.get("labels") if isinstance(record.get("labels"), dict) else {},
        "missing_or_needed_clarification": record.get("missing_or_needed_clarification", []),
        "supporting_doc_ids": record.get("supporting_doc_ids", []),
    }
    if record.get("task1_error"):
        compact["task1_error"] = str(record.get("task1_error"))
    return compact


def safe_name_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return cleaned.strip("._") or "model"


def output_name_stem(input_path: Path, model: str | None = None) -> str:
    if model is None:
        return input_path.stem
    return f"{input_path.stem}_{safe_name_part(model)}"


def default_output_path(input_path: Path, model: str | None = None) -> Path:
    suffix = input_path.suffix if input_path.suffix.lower() in {".json", ".jsonl"} else ".jsonl"
    return Path("output") / f"{output_name_stem(input_path, model)}_labeled{suffix}"


def default_batch_input_path(input_path: Path, model: str | None = None) -> Path:
    return Path("tmp") / f"{output_name_stem(input_path, model)}_batch_input.jsonl"


def default_batch_request_map_path(input_path: Path, model: str | None = None) -> Path:
    return Path("output") / f"{output_name_stem(input_path, model)}_batch_request_map.jsonl"


def default_batch_response_path(input_path: Path, model: str | None = None) -> Path:
    return Path("tmp") / f"{output_name_stem(input_path, model)}_batch_response.jsonl"


def default_batch_submission_log_path(input_path: Path, model: str | None = None) -> Path:
    return Path("output") / f"{output_name_stem(input_path, model)}_batch_submission_log.jsonl"


def append_jsonl_record(output_path: Path, record: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def record_checkpoint_key(record: dict[str, Any]) -> str:
    digest = _record_content_digest(record, include_identity=True)
    value = record_id_value(record)
    if value:
        return f"id:{value}:hash:{digest}"
    return f"hash:{digest}"


def legacy_record_checkpoint_key(record: dict[str, Any]) -> str:
    value = record_id_value(record)
    if value:
        return f"id:{value}"
    digest = _record_content_digest(record, include_identity=False)
    return f"hash:{digest}"


def record_resume_keys(record: dict[str, Any]) -> set[str]:
    keys = {record_checkpoint_key(record), legacy_record_checkpoint_key(record)}
    value = record_id_value(record)
    if value:
        keys.add(f"identity:{value}")
    mongo_record_id = str(record.get("mongo_record_id") or "").strip()
    if mongo_record_id:
        keys.add(f"mongo:{mongo_record_id}")
    query = str(record.get("query") or "").strip()
    domain = str(record.get("domain") or "").strip()
    if query:
        digest = hashlib.md5(f"{domain}\n{query}".encode("utf-8")).hexdigest()
        keys.add(f"query:{digest}")
    return keys


def checkpoint_identity_key(record: dict[str, Any]) -> str:
    value = record_id_value(record)
    if value:
        return f"id:{value}"
    mongo_record_id = str(record.get("mongo_record_id") or "").strip()
    if mongo_record_id:
        return f"mongo:{mongo_record_id}"
    query = str(record.get("query") or "").strip()
    domain = str(record.get("domain") or "").strip()
    if query:
        digest = hashlib.md5(f"{domain}\n{query}".encode("utf-8")).hexdigest()
        return f"query:{digest}"
    return record_checkpoint_key(record)


def answerability_label_value(record: dict[str, Any]) -> str:
    labels = record.get("labels")
    if not isinstance(labels, dict):
        return ""
    answerability = labels.get("answerability")
    if not isinstance(answerability, dict):
        return ""
    return str(answerability.get("value") or "").strip().upper()


def has_valid_answerability_label(record: dict[str, Any]) -> bool:
    if record.get("task1_error"):
        return False
    return answerability_label_value(record) in VALID_LABELS


def _record_content_digest(record: dict[str, Any], *, include_identity: bool) -> str:
    context_items: list[dict[str, str]] = []
    raw_context = record.get("context", [])
    if isinstance(raw_context, list):
        for item in raw_context:
            if not isinstance(item, dict):
                continue
            context_items.append(
                {
                    "title": str(item.get("title", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "published_date": str(item.get("published_date", "")).strip(),
                    "content": str(item.get("content", "")).strip(),
                }
            )

    canonical: dict[str, Any] = {
        "query": str(record.get("query", "")).strip(),
        "domain": str(record.get("domain", "")).strip(),
        "context": context_items,
    }
    if include_identity:
        canonical.update(
            {
                "id": str(record.get("id", "")).strip(),
                "_id": str(record.get("_id", "")).strip(),
                "sample_id": str(record.get("sample_id", "")).strip(),
            }
        )
    return hashlib.md5(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_checkpoint_records(checkpoint_file: Path) -> tuple[list[dict[str, Any]], set[str]]:
    if not checkpoint_file.exists():
        return [], set()

    latest_valid_records: dict[str, dict[str, Any]] = {}
    processed_keys: set[str] = set()
    with checkpoint_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            if not has_valid_answerability_label(payload):
                continue
            latest_valid_records[checkpoint_identity_key(payload)] = payload
            processed_keys.update(record_resume_keys(payload))
    return list(latest_valid_records.values()), processed_keys


def is_record_processed(record: dict[str, Any], processed_keys: set[str]) -> bool:
    return bool(record_resume_keys(record) & processed_keys)


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


def apply_label_result(record: dict[str, Any], result: dict[str, Any], chunks: list[dict[str, str]]) -> None:
    label = str(result.get("answerability", "")).strip().upper()
    if label not in VALID_LABELS:
        raise ValueError(f"Invalid answerability label: {label}")

    missing_items_raw = result.get("missing_or_needed_clarification", [])
    if not isinstance(missing_items_raw, list):
        missing_items_raw = []
    missing_items = [str(item).strip() for item in missing_items_raw if str(item).strip()]

    chunk_to_doc_id = {c["chunk_id"]: c["doc_id"] for c in chunks}
    allowed_doc_ids = {c["doc_id"] for c in chunks}

    supporting_doc_ids_raw = result.get("supporting_doc_ids", [])
    supporting_doc_ids: list[str] = []
    if isinstance(supporting_doc_ids_raw, list):
        for item in supporting_doc_ids_raw:
            doc_id = ""
            if isinstance(item, str):
                doc_id = item.strip()
            elif isinstance(item, dict):
                doc_id = str(item.get("doc_id", "")).strip()
                if not doc_id:
                    chunk_id = str(item.get("chunk_id", "")).strip()
                    doc_id = chunk_to_doc_id.get(chunk_id, "")
            if doc_id in allowed_doc_ids and doc_id not in supporting_doc_ids:
                supporting_doc_ids.append(doc_id)

    if label in {"YES", "PARTIAL"} and not supporting_doc_ids:
        raise ValueError(f"Label {label} requires at least one supporting_doc_id.")
    if label == "YES" and missing_items:
        raise ValueError("Label YES requires missing_or_needed_clarification to be empty.")
    if label == "NO":
        if supporting_doc_ids:
            raise ValueError("Label NO requires supporting_doc_ids to be empty.")
        if not missing_items:
            raise ValueError("Label NO requires a missing_or_needed_clarification explanation.")
    if label == "PARTIAL" and not missing_items:
        raise ValueError("Label PARTIAL requires a missing_or_needed_clarification explanation.")
    if label == "AMBIGUOUS" and not missing_items:
        raise ValueError("Label AMBIGUOUS requires a missing_or_needed_clarification explanation.")

    labels = record.get("labels")
    if not isinstance(labels, dict):
        labels = {}

    labels["answerability"] = {"value": label, "definition_version": "answerability_v1"}
    # labels["ambiguity"] = {
    #     "value": "AMBIGUOUS" if label == "AMBIGUOUS" else "NOT_AMBIGUOUS",
    #     "reason": ", ".join(missing_items),
    # }
    record["labels"] = labels
    record["missing_or_needed_clarification"] = missing_items
    record["supporting_doc_ids"] = supporting_doc_ids


def process_single_record(
    *,
    idx: int,
    record: dict[str, Any],
    checkpoint_key: str,
    record_id: str,
    model: str,
    label_client: Any,
    use_responses_api: bool,
) -> dict[str, Any]:
    try:
        query = str(record.get("query", "")).strip()
        if not query:
            raise ValueError(f"Record #{idx} missing 'query'.")

        chunks = build_chunks(record.get("context", []))
        if not chunks:
            raise ValueError(f"Record #{idx} has no usable context content.")

        user_prompt = build_user_prompt(query, chunks)
        request = build_answerability_request(
            system_prompt=ANSWERABILITY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=model,
            use_responses_api=use_responses_api,
        )
        result, _ = label_client.single_call(request=request)

        record.pop("task1_error", None)
        apply_label_result(record, result, chunks)
        return {
            "idx": idx,
            "record_id": record_id,
            "checkpoint_key": checkpoint_key,
            "record": record,
            "ok": True,
            "error": None,
        }
    except Exception as error:
        record["task1_error"] = str(error)
        return {
            "idx": idx,
            "record_id": record_id,
            "checkpoint_key": checkpoint_key,
            "record": record,
            "ok": False,
            "error": error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 1: label answerability using OpenAI API")
    parser.add_argument("--input", type=Path, required=True, help="Input path (.json or .jsonl)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (.json or .jsonl). Defaults to output/<input_stem>_<model>_labeled<input_suffix>.",
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
        "--concurrency",
        type=int,
        default=1,
        help="Maximum concurrent direct single-call LLM requests. Ignored in batch mode.",
    )
    parser.add_argument(
        "--batch-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Submit valid records with provider batch API instead of direct synchronous calls.",
    )
    parser.add_argument(
        "--completion-window",
        type=str,
        default="24h",
        help="OpenAI Batch API completion window. Ignored by Gemini batch jobs.",
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
        "--clear-cache",
        action="store_true",
        help="Delete the existing checkpoint/output for this run before processing from the beginning.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output is None:
        args.output = default_output_path(args.input, args.model)

    label_client = build_label_client(args)

    records, input_kind = load_records(args.input)

    if not records:
        raise ValueError("No valid records found in input.")

    batch_request_map_file = default_batch_request_map_path(args.input, args.model)
    batch_submission_log_file = default_batch_submission_log_path(args.input, args.model)

    checkpoint_file = args.output if args.output.suffix.lower() == ".jsonl" else Path(f"{args.output}.progress.jsonl")
    if not args.batch_mode:
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    if args.clear_cache:
        removed_paths: list[str] = []
        if not args.batch_mode and remove_file_if_exists(checkpoint_file):
            removed_paths.append(str(checkpoint_file))
        if not args.batch_mode and args.output != checkpoint_file and remove_file_if_exists(args.output):
            removed_paths.append(str(args.output))
        if args.batch_mode:
            for path in (args.output, batch_request_map_file, batch_submission_log_file):
                if remove_file_if_exists(path):
                    removed_paths.append(str(path))
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
    pending_records: list[tuple[int, dict[str, Any], str, str]] = []

    if args.batch_mode:
        for idx, record in tqdm(
            enumerate(records, start=1),
            total=len(records),
            desc="Preparing",
            unit="record",
        ):
            record_id = str(record.get("id") or record.get("_id") or record.get("sample_id") or f"record_{idx}")
            checkpoint_key = record_checkpoint_key(record)
            if is_record_processed(record, processed_keys):
                continue
            try:
                query = str(record.get("query", "")).strip()
                if not query:
                    raise ValueError(f"Record #{idx} missing 'query'.")

                chunks = build_chunks(record.get("context", []))
                if not chunks:
                    raise ValueError(f"Record #{idx} has no usable context content.")

                user_prompt = build_user_prompt(query, chunks)
                request = build_answerability_request(
                    system_prompt=ANSWERABILITY_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    model=args.model,
                    use_responses_api=args.llm_provider == "openai",
                )
                custom_id = f"record_{idx}_{hashlib.md5(checkpoint_key.encode('utf-8')).hexdigest()[:12]}"
                batch_requests.append(build_batch_request(custom_id=custom_id, request=request))
                batch_request_map_rows.append(
                    {
                        "custom_id": custom_id,
                        "record_id": record_id,
                        "checkpoint_key": checkpoint_key,
                        "record_index": idx,
                        "chunk_doc_ids": [chunk["doc_id"] for chunk in chunks],
                    }
                )
            except Exception as error:
                failed_count += 1
                record["task1_error"] = str(error)
                updated.append(record)
                processed_keys.add(checkpoint_key)
                print(f"Skip record #{idx} (id={record_id}): {error}")
                continue
    else:
        if args.concurrency <= 0:
            raise ValueError("--concurrency must be greater than 0.")

        for idx, record in enumerate(records, start=1):
            record_id = str(record.get("id") or record.get("_id") or record.get("sample_id") or f"record_{idx}")
            checkpoint_key = record_checkpoint_key(record)
            if is_record_processed(record, processed_keys):
                continue
            pending_records.append((idx, record, checkpoint_key, record_id))

        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(
                    process_single_record,
                    idx=idx,
                    record=record,
                    checkpoint_key=checkpoint_key,
                    record_id=record_id,
                    model=args.model,
                    label_client=label_client,
                    use_responses_api=args.llm_provider == "openai",
                )
                for idx, record, checkpoint_key, record_id in pending_records
            ]
            for future in tqdm(
                futures,
                total=len(futures),
                desc="Processing",
                unit="record",
            ):
                result = future.result()
                record = result["record"]
                checkpoint_key = str(result["checkpoint_key"])
                output_record = compact_labeled_record(record)
                updated.append(output_record)
                append_jsonl_record(checkpoint_file, output_record)
                processed_keys.add(checkpoint_key)
                processed_keys.update(record_resume_keys(output_record))
                if not result["ok"]:
                    failed_count += 1
                    print(f"Skip record #{result['idx']} (id={result['record_id']}): {result['error']}")

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

    if not args.batch_mode:
        deduped_updated: dict[str, dict[str, Any]] = {}
        for record in updated:
            deduped_updated[checkpoint_identity_key(record)] = record
        updated = list(deduped_updated.values())
        write_jsonl_records(checkpoint_file, updated)

    if not args.batch_mode and (args.output != checkpoint_file or input_kind != "jsonl"):
        save_records(updated, args.output, input_kind)

    print(f"Resumed from checkpoint: {resumed_count} record(s)")
    if args.batch_mode:
        print(f"Done. Batch mode on. Submitted {len(batch_requests)} request(s), failed {failed_count}.")
    else:
        labeled_count = sum(1 for record in updated if has_valid_answerability_label(record))
        print(f"Processed checkpoint saved to: {checkpoint_file}")
        print(f"Done. Labeled {labeled_count} record(s), failed {failed_count}. Output: {args.output}")


if __name__ == "__main__":
    main()
