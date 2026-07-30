import json
import time
from pathlib import Path
from typing import Any


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return text


def _extract_text_from_responses_body(body: dict[str, Any]) -> str:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    parts: list[str] = []
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
                    parts.append(text)
    return "\n".join(parts).strip()


BATCH_TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled", "cancelling"}


def _iter_json_objects_from_line(line: str, *, line_number: int) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    while index < len(line):
        while index < len(line) and line[index].isspace():
            index += 1
        if index >= len(line):
            break
        try:
            payload, next_index = decoder.raw_decode(line, index)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in batch submission log line {line_number}: {exc}") from exc
        if isinstance(payload, dict):
            objects.append(payload)
        index = next_index
    return objects


class OpenAILabelClient:
    def __init__(self, *, api_key: str, timeout: float) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Missing dependency 'openai'. Install it with: pip install openai") from exc

        self._client = OpenAI(api_key=api_key, timeout=timeout)

    def single_call(self, *, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        content = self.text_call(request=request)
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI output is not a JSON object.")
        return parsed, content

    def text_call(self, *, request: dict[str, Any]) -> str:
        if "instructions" in request and "input" in request:
            response = self._client.responses.create(**request)
            output_text = getattr(response, "output_text", None)
            if isinstance(output_text, str):
                return output_text.strip()
            if hasattr(response, "model_dump"):
                return _extract_text_from_responses_body(response.model_dump(mode="json"))
            if hasattr(response, "to_dict"):
                return _extract_text_from_responses_body(response.to_dict())
            return ""

        response = self._client.chat.completions.create(**request)
        return (response.choices[0].message.content or "").strip()

    def batch_call(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
    ) -> dict[str, Any]:
        
        input_file.parent.mkdir(parents=True, exist_ok=True)
        with input_file.open("w", encoding="utf-8") as handle:
            for request in requests:
                handle.write(json.dumps(request, ensure_ascii=False) + "\n")

        with input_file.open("rb") as handle:
            uploaded_file = self._client.files.create(file=handle, purpose="batch")

        endpoint = str(requests[0].get("url") or "/v1/chat/completions") if requests else "/v1/chat/completions"
        batch = self._client.batches.create(
            input_file_id=uploaded_file.id,
            endpoint=endpoint,
            completion_window=completion_window,
        )
        return {
            "batch_id": batch.id,
            "input_file_id": uploaded_file.id,
            "endpoint": batch.endpoint,
            "completion_window": batch.completion_window,
            "status": batch.status,
            "request_count": len(requests),
            "input_file": str(input_file),
        }

    def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        batch = self._client.batches.retrieve(batch_id)
        return {
            "batch_id": batch.id,
            "endpoint": batch.endpoint,
            "completion_window": batch.completion_window,
            "status": batch.status,
            "input_file_id": getattr(batch, "input_file_id", ""),
            "output_file_id": getattr(batch, "output_file_id", ""),
            "error_file_id": getattr(batch, "error_file_id", ""),
        }

    def wait_for_batch(self, *, batch_id: str, poll_interval_seconds: float) -> dict[str, Any]:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0.")

        while True:
            metadata = self.retrieve_batch(batch_id)
            status = str(metadata.get("status", ""))
            print(f"Batch {batch_id} status: {status}")
            if status in BATCH_TERMINAL_STATUSES:
                return metadata
            time.sleep(poll_interval_seconds)

    @staticmethod
    def _load_submission_log_parts(log_file: Path | None, *, total_parts: int) -> dict[int, dict[str, Any]]:
        if log_file is None or not log_file.exists():
            return {}

        parts: dict[int, dict[str, Any]] = {}
        with log_file.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                for metadata in _iter_json_objects_from_line(line, line_number=line_number):
                    try:
                        part_index = int(metadata.get("batch_part", 0))
                        part_count = int(metadata.get("batch_part_count", 0))
                    except (TypeError, ValueError):
                        continue
                    if part_index < 1 or part_index > total_parts or part_count != total_parts:
                        continue
                    if not str(metadata.get("batch_id", "")).strip():
                        continue
                    parts[part_index] = metadata
        return parts

    def batch_call_sequential(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
        batch_size: int,
        poll_interval_seconds: float,
        submission_log_file: Path | None = None,
    ) -> list[dict[str, Any]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")

        batch_metadata_rows: list[dict[str, Any]] = []
        total_parts = (len(requests) + batch_size - 1) // batch_size
        logged_parts = self._load_submission_log_parts(submission_log_file, total_parts=total_parts)
        for part_index, start in enumerate(range(0, len(requests), batch_size), start=1):
            chunk = requests[start : start + batch_size]
            part_input_file = input_file.with_name(f"{input_file.stem}_part{part_index:03d}{input_file.suffix}")

            logged_metadata = logged_parts.get(part_index)
            if logged_metadata and int(logged_metadata.get("request_count", 0) or 0) == len(chunk):
                metadata = dict(logged_metadata)
                metadata["input_file"] = str(part_input_file)
                status = str(metadata.get("status", ""))
                if status == "completed":
                    batch_metadata_rows.append(metadata)
                    print(
                        f"Batch part {part_index}/{total_parts} already completed: "
                        f"{metadata['batch_id']} ({len(chunk)} request(s))"
                    )
                    continue
                if status not in BATCH_TERMINAL_STATUSES:
                    print(
                        f"Batch part {part_index}/{total_parts} already submitted; "
                        f"resuming poll: {metadata['batch_id']} ({len(chunk)} request(s))"
                    )
                else:
                    print(
                        f"Batch part {part_index}/{total_parts} previously stopped with "
                        f"status {status}; resubmitting."
                    )
                    metadata = {}
            else:
                metadata = {}

            if not metadata:
                metadata = self.batch_call(
                    requests=chunk,
                    input_file=part_input_file,
                    completion_window=completion_window,
                )
                metadata.update(
                    {
                        "log_event": "submitted",
                        "batch_part": part_index,
                        "batch_part_count": total_parts,
                        "input_file": str(part_input_file),
                    }
                )
                self._append_submission_log(submission_log_file, metadata)
                print(
                    f"Batch part {part_index}/{total_parts} submitted: "
                    f"{metadata['batch_id']} ({metadata['request_count']} request(s))"
                )

            final_metadata = self.wait_for_batch(
                batch_id=str(metadata["batch_id"]),
                poll_interval_seconds=poll_interval_seconds,
            )
            metadata.update(final_metadata)
            metadata.update(
                {
                    "log_event": "completed",
                    "batch_part": part_index,
                    "batch_part_count": total_parts,
                    "input_file": str(part_input_file),
                    "request_count": len(chunk),
                }
            )
            self._append_submission_log(submission_log_file, metadata)
            batch_metadata_rows.append(metadata)
            if metadata["status"] != "completed":
                raise RuntimeError(
                    f"Batch part {part_index}/{total_parts} stopped with status "
                    f"{metadata['status']}: {metadata['batch_id']}"
                )

        return batch_metadata_rows

    @staticmethod
    def _append_submission_log(log_file: Path | None, metadata: dict[str, Any]) -> None:
        if log_file is None:
            return
        log_file.parent.mkdir(parents=True, exist_ok=True)
        needs_newline = log_file.exists() and log_file.stat().st_size > 0
        with log_file.open("a", encoding="utf-8") as handle:
            if needs_newline:
                with log_file.open("rb") as raw:
                    raw.seek(-1, 2)
                    if raw.read(1) not in {b"\n", b"\r"}:
                        handle.write("\n")
            handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            handle.flush()
