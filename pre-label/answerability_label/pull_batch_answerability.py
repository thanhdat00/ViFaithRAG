import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from label_answerability import (
    apply_label_result,
    compact_labeled_record,
    default_batch_request_map_path,
    default_batch_response_path,
    default_batch_submission_log_path,
    default_output_path,
    load_records,
    record_checkpoint_key,
    save_records,
)
from llm_request import build_chunks

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.openai_label_client import _strip_code_fence  # noqa: E402


GEMINI_FALLBACK_BATCH_RESPONSE_FILE = Path("tmp") / "gemini_batch_response.jsonl"


def load_latest_batch_id(submission_log_file: Path) -> str:
    batch_ids = load_batch_ids(submission_log_file)
    return batch_ids[-1]


def load_batch_ids(submission_log_file: Path) -> list[str]:
    if not submission_log_file.exists():
        raise FileNotFoundError(f"Batch submission log not found: {submission_log_file}")

    decoder = json.JSONDecoder()
    batch_ids: list[str] = []
    seen: set[str] = set()
    with submission_log_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            position = 0
            while position < len(line):
                try:
                    payload, position = decoder.raw_decode(line, position)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in submission log line {line_number}: {exc}") from exc
                while position < len(line) and line[position].isspace():
                    position += 1
                if not isinstance(payload, dict):
                    continue
                batch_id = str(payload.get("batch_id", "")).strip()
                if batch_id and batch_id not in seen:
                    batch_ids.append(batch_id)
                    seen.add(batch_id)

    if not batch_ids:
        raise ValueError(f"No batch_id found in submission log: {submission_log_file}")
    return batch_ids


def load_checkpoint_to_custom_id_map(batch_request_map_file: Path) -> dict[str, str]:
    if not batch_request_map_file.exists():
        raise FileNotFoundError(f"Batch request map not found: {batch_request_map_file}")

    checkpoint_to_custom_id: dict[str, str] = {}
    with batch_request_map_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Batch request map line {line_number} is not a JSON object.")
            checkpoint_key = str(payload.get("checkpoint_key", "")).strip()
            custom_id = str(payload.get("custom_id", "")).strip()
            if checkpoint_key and custom_id:
                checkpoint_to_custom_id[checkpoint_key] = custom_id
    return checkpoint_to_custom_id


def _extract_text_from_parts(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "\n".join(text_parts).strip()


def _extract_openai_responses_text(body: dict[str, Any]) -> str:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    text_parts: list[str] = []
    output = body.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
    return "\n".join(text_parts).strip()


def extract_response_text_from_batch_line(payload: dict[str, Any], *, provider: str = "openai") -> str:
    response = payload.get("response", {})
    if not isinstance(response, dict):
        return ""

    if provider == "gemini":
        candidates = response.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return ""
        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            return ""
        content = first_candidate.get("content", {})
        if not isinstance(content, dict):
            return ""
        return _extract_text_from_parts(content.get("parts", []))

    if int(response.get("status_code", 0)) != 200:
        return ""
    body = response.get("body", {})
    if not isinstance(body, dict):
        return ""
    responses_text = _extract_openai_responses_text(body)
    if responses_text:
        return responses_text

    choices = body.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def parse_model_json_response(response_text: str, *, line_number: int, custom_id: str) -> dict[str, Any] | None:
    stripped = _strip_code_fence(response_text).strip()
    if not stripped:
        return None

    try:
        result = json.loads(stripped)
    except json.JSONDecodeError as exc:
        preview = stripped.replace("\n", "\\n")[:200]
        print(
            f"Warning: skipping malformed JSON response at batch line {line_number} "
            f"custom_id={custom_id}: {exc}; preview={preview!r}",
            file=sys.stderr,
        )
        return None

    if not isinstance(result, dict):
        print(
            f"Warning: skipping non-object JSON response at batch line {line_number} "
            f"custom_id={custom_id}: {type(result).__name__}",
            file=sys.stderr,
        )
        return None

    return result


def load_batch_response_results(batch_response_file: Path, *, provider: str = "openai") -> dict[str, dict[str, Any]]:
    if not batch_response_file.exists():
        raise FileNotFoundError(f"Batch response file not found: {batch_response_file}")

    results_by_custom_id: dict[str, dict[str, Any]] = {}
    with batch_response_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Batch response line {line_number} is not a JSON object.")
            custom_id = str(payload.get("custom_id") or payload.get("key") or "").strip()
            if not custom_id:
                continue
            response_text = extract_response_text_from_batch_line(payload, provider=provider)
            if not response_text:
                continue
            result = parse_model_json_response(
                response_text,
                line_number=line_number,
                custom_id=custom_id,
            )
            if result is None:
                continue
            results_by_custom_id[custom_id] = result
    return results_by_custom_id


def ensure_output_writable(output_path: Path, *, overwrite: bool) -> None:
    if not output_path.exists():
        return
    if output_path.stat().st_size == 0:
        return
    if overwrite:
        return
    raise FileExistsError(f"Output already exists and is non-empty. Use --overwrite to replace it: {output_path}")


def resolve_batch_request_map_file(input_path: Path, model: str | None, requested_path: Path | None) -> Path:
    if requested_path is not None:
        return requested_path

    default_path = default_batch_request_map_path(input_path, model)
    if default_path.exists():
        return default_path

    legacy_path = Path("output") / f"{input_path.stem}_request_map.jsonl"
    if legacy_path.exists():
        return legacy_path

    return default_path


def resolve_default_file(
    *,
    input_path: Path,
    model: str | None,
    requested_path: Path | None,
    path_factory: Any,
) -> Path:
    if requested_path is not None:
        return requested_path
    if model:
        model_path = path_factory(input_path, model)
        if model_path.exists():
            return model_path
        return model_path
    return path_factory(input_path)


def default_gemini_poll_log_path(input_path: Path, model: str | None = None) -> Path:
    stem = input_path.stem
    if model:
        stem = f"{stem}_{safe_name_part(model)}"
    return Path("tmp") / f"{stem}_gemini_batch_poll_log.jsonl"


def safe_name_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return cleaned.strip("._") or "model"


def write_file_content(content: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(content, "write_to_file"):
        content.write_to_file(str(output_path))
        return

    raw_content = getattr(content, "content", None)
    if isinstance(raw_content, bytes):
        output_path.write_bytes(raw_content)
        return
    if isinstance(raw_content, str):
        output_path.write_text(raw_content, encoding="utf-8")
        return
    if isinstance(content, bytes):
        output_path.write_bytes(content)
        return
    if isinstance(content, str):
        output_path.write_text(content, encoding="utf-8")
        return

    raise TypeError(f"Unsupported file content type from OpenAI SDK: {type(content).__name__}")


def content_to_text(content: Any) -> str:
    raw_content = getattr(content, "content", None)
    if isinstance(raw_content, bytes):
        return raw_content.decode("utf-8")
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(content, bytes):
        return content.decode("utf-8")
    if isinstance(content, str):
        return content
    raise TypeError(f"Unsupported file content type from OpenAI SDK: {type(content).__name__}")


def download_gemini_file_content(content: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(content, "write_to_file"):
        content.write_to_file(str(output_path))
        return

    raw_content = getattr(content, "content", None)
    if isinstance(raw_content, bytes):
        output_path.write_bytes(raw_content)
        return
    if isinstance(raw_content, str):
        output_path.write_text(raw_content, encoding="utf-8")
        return
    if isinstance(content, bytes):
        output_path.write_bytes(content)
        return
    if isinstance(content, str):
        output_path.write_text(content, encoding="utf-8")
        return

    raise TypeError(f"Unsupported file content type from Gemini SDK: {type(content).__name__}")


def download_gemini_file(client: Any, *, file_id: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = client._client.files.download(file=file_id, download_path=str(output_path))
    except TypeError:
        result = client._client.files.download(file=file_id)
        download_gemini_file_content(result, output_path)
        return

    if result is not None and not output_path.exists():
        download_gemini_file_content(result, output_path)


def download_gemini_batch_response(
    *,
    api_key: str,
    timeout: float,
    batch_id: str,
    batch_response_file: Path,
    poll_log_file: Path | None,
    overwrite: bool,
) -> dict[str, Any]:
    try:
        from shared.gemini_label_client import GeminiLabelClient
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'google-genai'. Install it with: pip install google-genai") from exc

    client = GeminiLabelClient(api_key=api_key, timeout=timeout)
    metadata = client.poll_batch_request(batch_id=batch_id, log_file=poll_log_file)

    if metadata.get("status") != "completed":
        return metadata

    output_file_id = str(metadata.get("output_file_id", "")).strip()
    if not output_file_id:
        raw_batch = metadata.get("raw_batch")
        if raw_batch is not None:
            print("Completed batch raw metadata:")
            print(json.dumps(raw_batch, ensure_ascii=False, indent=2))
        raise ValueError(f"Batch {batch_id} is completed but has no output_file_id.")

    if batch_response_file.exists() and batch_response_file.stat().st_size > 0 and not overwrite:
        raise FileExistsError(
            f"Batch response file already exists and is non-empty. Use --overwrite to replace it: {batch_response_file}"
        )

    download_gemini_file(client, file_id=output_file_id, output_path=batch_response_file)
    return metadata


def download_gemini_batch_responses(
    *,
    api_key: str,
    timeout: float,
    batch_ids: list[str],
    batch_response_file: Path,
    poll_log_file: Path | None,
    overwrite: bool,
) -> list[dict[str, Any]]:
    try:
        from shared.gemini_label_client import GeminiLabelClient
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'google-genai'. Install it with: pip install google-genai") from exc

    client = GeminiLabelClient(api_key=api_key, timeout=timeout)
    if batch_response_file.exists() and batch_response_file.stat().st_size > 0 and not overwrite:
        raise FileExistsError(
            f"Batch response file already exists and is non-empty. Use --overwrite to replace it: {batch_response_file}"
        )
    batch_response_file.parent.mkdir(parents=True, exist_ok=True)
    batch_response_file.write_text("", encoding="utf-8")

    metadata_rows: list[dict[str, Any]] = []
    for batch_id in batch_ids:
        metadata = client.poll_batch_request(batch_id=batch_id, log_file=poll_log_file)
        metadata_rows.append(metadata)

        print(f"Batch {metadata.get('batch_id', batch_id)} status: {metadata.get('status', '')}")
        if metadata.get("status") != "completed":
            raise RuntimeError(f"Batch is not completed; stopping merge: {batch_id} status={metadata.get('status', '')}")

        output_file_id = str(metadata.get("output_file_id", "")).strip()
        if not output_file_id:
            raise ValueError(f"Batch {batch_id} is completed but has no output_file_id.")

        part_file = batch_response_file.with_name(f"{batch_response_file.stem}_{len(metadata_rows):03d}{batch_response_file.suffix}")
        download_gemini_file(client, file_id=output_file_id, output_path=part_file)
        text = part_file.read_text(encoding="utf-8").strip()
        if text:
            with batch_response_file.open("a", encoding="utf-8") as merged_handle:
                merged_handle.write(text)
                merged_handle.write("\n")

    return metadata_rows


def download_batch_response(*, api_key: str, timeout: float, batch_id: str, batch_response_file: Path) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

    client = OpenAI(api_key=api_key, timeout=timeout)
    batch = client.batches.retrieve(batch_id)
    status = str(getattr(batch, "status", "") or "")
    output_file_id = str(getattr(batch, "output_file_id", "") or "")
    error_file_id = str(getattr(batch, "error_file_id", "") or "")

    metadata = {
        "batch_id": str(getattr(batch, "id", batch_id)),
        "status": status,
        "output_file_id": output_file_id,
        "error_file_id": error_file_id,
    }

    if status != "completed":
        return metadata
    if not output_file_id:
        raise ValueError(f"Batch {batch_id} is completed but has no output_file_id.")

    content = client.files.content(output_file_id)
    write_file_content(content, batch_response_file)
    return metadata


def download_batch_responses(
    *,
    api_key: str,
    timeout: float,
    batch_ids: list[str],
    batch_response_file: Path,
) -> list[dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

    client = OpenAI(api_key=api_key, timeout=timeout)
    batch_response_file.parent.mkdir(parents=True, exist_ok=True)
    batch_response_file.write_text("", encoding="utf-8")

    metadata_rows: list[dict[str, Any]] = []
    with batch_response_file.open("a", encoding="utf-8") as merged_handle:
        for batch_id in batch_ids:
            batch = client.batches.retrieve(batch_id)
            status = str(getattr(batch, "status", "") or "")
            output_file_id = str(getattr(batch, "output_file_id", "") or "")
            error_file_id = str(getattr(batch, "error_file_id", "") or "")
            metadata = {
                "batch_id": str(getattr(batch, "id", batch_id)),
                "status": status,
                "output_file_id": output_file_id,
                "error_file_id": error_file_id,
            }
            metadata_rows.append(metadata)

            print(f"Batch {metadata['batch_id']} status: {metadata['status']}")
            if status != "completed":
                if error_file_id:
                    print(f"Error file id: {error_file_id}")
                raise RuntimeError(f"Batch is not completed; stopping merge: {batch_id} status={status}")
            if not output_file_id:
                raise ValueError(f"Batch {batch_id} is completed but has no output_file_id.")

            content = client.files.content(output_file_id)
            text = content_to_text(content).strip()
            if text:
                merged_handle.write(text)
                merged_handle.write("\n")

    return metadata_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull and map Task 1 batch answerability output.")
    parser.add_argument("--input", type=Path, required=True, help="Original input dataset path (.json or .jsonl)")
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "gemini"],
        default="openai",
        help="Batch provider. Gemini supports response files with top-level 'key' fields.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name used to derive model-specific output and batch artifact names.",
    )
    parser.add_argument("--batch-id", type=str, default=None, help="Batch id override. Defaults to latest in submission log.")
    parser.add_argument(
        "--all-batches",
        action="store_true",
        help="Pull every batch_id from the submission log and merge all batch outputs into one response file.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Mapped output path. Defaults from input file name.")
    parser.add_argument(
        "--batch-request-map-file",
        type=Path,
        default=None,
        help="Request map JSONL. Defaults to output/<input>_<model>_batch_request_map.jsonl.",
    )
    parser.add_argument(
        "--batch-submission-log-file",
        type=Path,
        default=None,
        help="Submission log JSONL. Defaults to output/<input>_<model>_batch_submission_log.jsonl.",
    )
    parser.add_argument(
        "--batch-response-file",
        type=Path,
        default=None,
        help="Downloaded batch response JSONL. Defaults to tmp/<input>_<model>_batch_response.jsonl.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use an existing --batch-response-file directly instead of pulling from the provider API.",
    )
    parser.add_argument(
        "--poll-log-file",
        type=Path,
        default=None,
        help="Gemini poll log JSONL. Defaults to tmp/<input>_<model>_gemini_batch_poll_log.jsonl.",
    )
    parser.add_argument(
        "--no-poll-log",
        action="store_true",
        help="For Gemini only: poll without appending metadata to a poll log.",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite a non-empty output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = args.llm_provider.strip().lower()

    output_path = resolve_default_file(
        input_path=args.input,
        model=args.model,
        requested_path=args.output,
        path_factory=default_output_path,
    )
    batch_request_map_file = resolve_batch_request_map_file(args.input, args.model, args.batch_request_map_file)
    batch_submission_log_file = resolve_default_file(
        input_path=args.input,
        model=args.model,
        requested_path=args.batch_submission_log_file,
        path_factory=default_batch_submission_log_path,
    )
    batch_response_file = resolve_default_file(
        input_path=args.input,
        model=args.model,
        requested_path=args.batch_response_file,
        path_factory=default_batch_response_path,
    )
    if (
        provider == "gemini"
        and args.skip_download
        and args.batch_response_file is None
        and not batch_response_file.exists()
        and GEMINI_FALLBACK_BATCH_RESPONSE_FILE.exists()
    ):
        batch_response_file = GEMINI_FALLBACK_BATCH_RESPONSE_FILE

    use_existing_response = args.skip_download

    if not use_existing_response:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: OPENAI_API_KEY")

            if args.all_batches:
                if args.batch_id:
                    raise ValueError("--batch-id cannot be used with --all-batches.")
                batch_ids = load_batch_ids(batch_submission_log_file)
                metadata_rows = download_batch_responses(
                    api_key=api_key,
                    timeout=args.timeout,
                    batch_ids=batch_ids,
                    batch_response_file=batch_response_file,
                )
                print(f"Merged {len(metadata_rows)} batch response file(s).")
            else:
                batch_id = args.batch_id or load_latest_batch_id(batch_submission_log_file)
                metadata = download_batch_response(
                    api_key=api_key,
                    timeout=args.timeout,
                    batch_id=batch_id,
                    batch_response_file=batch_response_file,
                )
                print(f"Batch {metadata['batch_id']} status: {metadata['status']}")
                if metadata["status"] != "completed":
                    if metadata["error_file_id"]:
                        print(f"Error file id: {metadata['error_file_id']}")
                    print("Batch is not completed. No labeled output was written.")
                    return
        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: GEMINI_API_KEY or GOOGLE_API_KEY")
            poll_log_file = None if args.no_poll_log else (args.poll_log_file or default_gemini_poll_log_path(args.input, args.model))

            if args.all_batches:
                if args.batch_id:
                    raise ValueError("--batch-id cannot be used with --all-batches.")
                batch_ids = load_batch_ids(batch_submission_log_file)
                metadata_rows = download_gemini_batch_responses(
                    api_key=api_key,
                    timeout=args.timeout,
                    batch_ids=batch_ids,
                    batch_response_file=batch_response_file,
                    poll_log_file=poll_log_file,
                    overwrite=args.overwrite,
                )
                print(f"Merged {len(metadata_rows)} Gemini batch response file(s).")
                if poll_log_file is not None:
                    print(f"Poll log appended to: {poll_log_file}")
            else:
                batch_id = args.batch_id or load_latest_batch_id(batch_submission_log_file)
                metadata = download_gemini_batch_response(
                    api_key=api_key,
                    timeout=args.timeout,
                    batch_id=batch_id,
                    batch_response_file=batch_response_file,
                    poll_log_file=poll_log_file,
                    overwrite=args.overwrite,
                )
                print(f"Batch {metadata.get('batch_id', batch_id)} status: {metadata.get('status', '')}")
                if poll_log_file is not None:
                    print(f"Poll log appended to: {poll_log_file}")
                if metadata.get("status") != "completed":
                    print("Batch is not completed. No labeled output was written.")
                    return

    ensure_output_writable(output_path, overwrite=args.overwrite)
    records, input_kind = load_records(args.input)
    checkpoint_to_custom_id = load_checkpoint_to_custom_id_map(batch_request_map_file)
    results_by_custom_id = load_batch_response_results(batch_response_file, provider=provider)

    updated: list[dict[str, Any]] = []
    failed_count = 0
    for idx, record in enumerate(records, start=1):
        record_id = str(record.get("id") or record.get("_id") or record.get("sample_id") or f"record_{idx}")
        try:
            chunks = build_chunks(record.get("context", []))
            if not chunks:
                raise ValueError(f"Record #{idx} has no usable context content.")
            checkpoint_key = record_checkpoint_key(record)
            custom_id = checkpoint_to_custom_id.get(checkpoint_key, "")
            if not custom_id:
                raise ValueError(f"Record #{idx} missing custom_id in batch request map.")
            result = results_by_custom_id.get(custom_id)
            if result is None:
                raise ValueError(f"Record #{idx} missing batch response for custom_id '{custom_id}'.")

            record.pop("task1_error", None)
            apply_label_result(record, result, chunks)
        except Exception as error:
            failed_count += 1
            record["task1_error"] = str(error)
            print(f"Skip record #{idx} (id={record_id}): {error}")
        updated.append(compact_labeled_record(record))

    save_records(updated, output_path, input_kind)
    print(f"Batch response saved to: {batch_response_file}")
    print(f"Request map used: {batch_request_map_file}")
    print(f"Done. Mapped {len(updated)} record(s), failed {failed_count}. Output: {output_path}")


if __name__ == "__main__":
    main()
