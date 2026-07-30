import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from answer_generation import (
    default_batch_request_map_path,
    default_batch_response_path,
    default_batch_submission_log_path,
)
from map_batch_output import (
    AMBIGUOUS_GROUND_TRUTH_ANSWER,
    NO_GROUND_TRUTH_ANSWER,
    VALID_LABELS,
    append_jsonl_record,
    clean_generated_answer,
    get_answerability_label,
    load_batch_response_answers,
    load_checkpoint_records,
    load_checkpoint_to_custom_id_map,
    load_records,
    record_checkpoint_key,
    save_records,
)


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


def load_latest_batch_id(submission_log_file: Path) -> str:
    return load_batch_ids(submission_log_file)[-1]


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


def download_batch_response(
    *,
    api_key: str,
    timeout: float,
    batch_id: str,
    batch_response_file: Path,
    overwrite: bool,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

    if batch_response_file.exists() and batch_response_file.stat().st_size > 0 and not overwrite:
        raise FileExistsError(
            f"Batch response file already exists and is non-empty. Use --overwrite to replace it: {batch_response_file}"
        )

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
    overwrite: bool,
) -> list[dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

    if batch_response_file.exists() and batch_response_file.stat().st_size > 0 and not overwrite:
        raise FileExistsError(
            f"Batch response file already exists and is non-empty. Use --overwrite to replace it: {batch_response_file}"
        )

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
    overwrite: bool,
) -> dict[str, Any]:
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from shared.gemini_label_client import GeminiLabelClient

    client = GeminiLabelClient(api_key=api_key, timeout=timeout)
    metadata = client.poll_batch_request(batch_id=batch_id, log_file=None)

    if metadata.get("status") != "completed":
        return metadata

    output_file_id = str(metadata.get("output_file_id", "")).strip()
    if not output_file_id:
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
    overwrite: bool,
) -> list[dict[str, Any]]:
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from shared.gemini_label_client import GeminiLabelClient

    if batch_response_file.exists() and batch_response_file.stat().st_size > 0 and not overwrite:
        raise FileExistsError(
            f"Batch response file already exists and is non-empty. Use --overwrite to replace it: {batch_response_file}"
        )

    client = GeminiLabelClient(api_key=api_key, timeout=timeout)
    batch_response_file.parent.mkdir(parents=True, exist_ok=True)
    batch_response_file.write_text("", encoding="utf-8")

    metadata_rows: list[dict[str, Any]] = []
    with batch_response_file.open("a", encoding="utf-8") as merged_handle:
        for batch_id in batch_ids:
            metadata = client.poll_batch_request(batch_id=batch_id, log_file=None)
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
                merged_handle.write(text)
                merged_handle.write("\n")

    return metadata_rows


def map_batch_answers(
    *,
    input_path: Path,
    output_path: Path,
    batch_response_file: Path,
    batch_request_map_file: Path,
    provider: str = "openai",
) -> tuple[int, int, Path]:
    if not batch_request_map_file.exists():
        raise FileNotFoundError(f"Batch request map file not found: {batch_request_map_file}")
    if not batch_response_file.exists():
        raise FileNotFoundError(f"Batch response file not found: {batch_response_file}")

    records, input_kind = load_records(input_path)
    if not records:
        raise ValueError("No valid records found in input.")

    checkpoint_file = output_path if output_path.suffix.lower() == ".jsonl" else Path(f"{output_path}.progress.jsonl")
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    resumed_records, processed_keys = load_checkpoint_records(checkpoint_file)

    checkpoint_to_custom_id = load_checkpoint_to_custom_id_map(batch_request_map_file)
    answers_by_custom_id = load_batch_response_answers(batch_response_file, provider=provider)

    updated: list[dict[str, Any]] = list(resumed_records)
    failed_count = 0

    for idx, record in enumerate(records, start=1):
        record_id = str(record.get("id") or record.get("_id") or record.get("sample_id") or f"record_{idx}")
        checkpoint_key = record_checkpoint_key(record)
        if checkpoint_key in processed_keys:
            continue
        try:
            label = get_answerability_label(record)
            if not label or label not in VALID_LABELS:
                raise ValueError(f"Record #{idx} has invalid or missing 'answerability' label: '{label}'.")
            if label == "NO":
                answer = NO_GROUND_TRUTH_ANSWER
            elif label == "AMBIGUOUS":
                answer = AMBIGUOUS_GROUND_TRUTH_ANSWER
            else:
                custom_id = checkpoint_to_custom_id.get(checkpoint_key, "")
                if not custom_id:
                    raise ValueError(f"Record #{idx} missing custom_id in batch request map.")
                answer = answers_by_custom_id.get(custom_id, "").strip()
                if not answer:
                    raise ValueError(f"Record #{idx} missing answer in batch response for custom_id '{custom_id}'.")
                answer = clean_generated_answer(answer)

            record["ground_truth_answer"] = answer
            updated.append(record)
            append_jsonl_record(checkpoint_file, record)
            processed_keys.add(checkpoint_key)
        except Exception as error:
            failed_count += 1
            print(f"Skip record #{idx} (id={record_id}): {error}")

    save_records(updated, output_path, input_kind)
    return len(updated), failed_count, checkpoint_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull and map Task 2 batch answer-generation output.")
    parser.add_argument("--input", type=Path, required=True, help="Input labeled records (.json or .jsonl)")
    parser.add_argument("--output", type=Path, required=True, help="Output path (.json or .jsonl)")
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "gemini"],
        default="openai",
        help="Batch provider used for submission.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Model name used during task2 batch submission. Used to resolve default batch file paths.",
    )
    parser.add_argument("--batch-id", type=str, default=None, help="Batch id override. Defaults to latest in submission log.")
    parser.add_argument(
        "--all-batches",
        action="store_true",
        help="Pull every batch_id from the submission log and merge all batch outputs into one response file.",
    )
    parser.add_argument(
        "--batch-request-map-file",
        type=Path,
        default=None,
        help="Request map JSONL created by task2 answer_generation.py.",
    )
    parser.add_argument(
        "--batch-submission-log-file",
        type=Path,
        default=None,
        help="Submission log JSONL created by task2 answer_generation.py.",
    )
    parser.add_argument(
        "--batch-response-file",
        type=Path,
        default=None,
        help="Downloaded batch response JSONL.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use an existing --batch-response-file directly instead of pulling from the provider.",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite a non-empty batch response file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_id and args.all_batches:
        raise ValueError("--batch-id cannot be used with --all-batches.")

    if args.batch_request_map_file is None:
        args.batch_request_map_file = default_batch_request_map_path(args.input, args.model)
    if args.batch_submission_log_file is None:
        args.batch_submission_log_file = default_batch_submission_log_path(args.input, args.model)
    if args.batch_response_file is None:
        args.batch_response_file = default_batch_response_path(args.input, args.model)

    if not args.skip_download:
        if args.llm_provider == "openai" and args.all_batches:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: OPENAI_API_KEY")
            batch_ids = load_batch_ids(args.batch_submission_log_file)
            metadata_rows = download_batch_responses(
                api_key=api_key,
                timeout=args.timeout,
                batch_ids=batch_ids,
                batch_response_file=args.batch_response_file,
                overwrite=args.overwrite,
            )
            print(f"Merged {len(metadata_rows)} batch response file(s).")
        elif args.llm_provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: OPENAI_API_KEY")
            batch_id = args.batch_id or load_latest_batch_id(args.batch_submission_log_file)
            metadata = download_batch_response(
                api_key=api_key,
                timeout=args.timeout,
                batch_id=batch_id,
                batch_response_file=args.batch_response_file,
                overwrite=args.overwrite,
            )
            print(f"Batch {metadata['batch_id']} status: {metadata['status']}")
            if metadata["status"] != "completed":
                if metadata["error_file_id"]:
                    print(f"Error file id: {metadata['error_file_id']}")
                print("Batch is not completed. No generated-answer output was written.")
                return
        elif args.llm_provider == "gemini" and args.all_batches:
            api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: GEMINI_API_KEY or GOOGLE_API_KEY")
            batch_ids = load_batch_ids(args.batch_submission_log_file)
            metadata_rows = download_gemini_batch_responses(
                api_key=api_key,
                timeout=args.timeout,
                batch_ids=batch_ids,
                batch_response_file=args.batch_response_file,
                overwrite=args.overwrite,
            )
            print(f"Merged {len(metadata_rows)} Gemini batch response file(s).")
        elif args.llm_provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Missing API key. Set environment variable: GEMINI_API_KEY or GOOGLE_API_KEY")
            batch_id = args.batch_id or load_latest_batch_id(args.batch_submission_log_file)
            metadata = download_gemini_batch_response(
                api_key=api_key,
                timeout=args.timeout,
                batch_id=batch_id,
                batch_response_file=args.batch_response_file,
                overwrite=args.overwrite,
            )
            print(f"Batch {metadata.get('batch_id', batch_id)} status: {metadata.get('status', '')}")
            if metadata.get("status") != "completed":
                print("Batch is not completed. No generated-answer output was written.")
                return

    mapped_count, failed_count, checkpoint_file = map_batch_answers(
        input_path=args.input,
        output_path=args.output,
        batch_response_file=args.batch_response_file,
        batch_request_map_file=args.batch_request_map_file,
        provider=args.llm_provider.strip().lower(),
    )
    print(f"Batch response saved to: {args.batch_response_file}")
    print(f"Request map used: {args.batch_request_map_file}")
    print(f"Processed checkpoint saved to: {checkpoint_file}")
    print(f"Done. Mapped {mapped_count} record(s), failed {failed_count}. Output: {args.output}")


if __name__ == "__main__":
    main()
