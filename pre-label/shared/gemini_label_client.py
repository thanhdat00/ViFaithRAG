import json
import time
from pathlib import Path
from typing import Any

from .openai_label_client import _strip_code_fence


GEMINI_BATCH_TERMINAL_STATES = {
    "BATCH_STATE_SUCCEEDED",
    "BATCH_STATE_FAILED",
    "BATCH_STATE_CANCELLED",
    "BATCH_STATE_EXPIRED",
}

GEMINI_BATCH_STATUS_MAP = {
    "BATCH_STATE_PENDING": "pending",
    "BATCH_STATE_RUNNING": "running",
    "BATCH_STATE_SUCCEEDED": "completed",
    "BATCH_STATE_FAILED": "failed",
    "BATCH_STATE_CANCELLED": "cancelled",
    "BATCH_STATE_EXPIRED": "expired",
}


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


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)

    return str(content)


class GeminiLabelClient:
    def __init__(self, *, api_key: str, timeout: float) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency 'google-genai'. Install it with: pip install google-genai"
            ) from exc

        self._types = types
        self._api_key = api_key
        self._timeout = timeout
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )

        # Updated after each SDK generate_content call.
        # Use this to check cached_content_token_count.
        self.last_usage_metadata: Any | None = None

    # ---------------------------------------------------------------------
    # Public single-call APIs
    # ---------------------------------------------------------------------

    def single_call(self, *, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        content = self.text_call(request=request)
        parsed = json.loads(_strip_code_fence(content))

        if not isinstance(parsed, dict):
            raise ValueError("Gemini output is not a JSON object.")

        return parsed, content

    def text_call(self, *, request: dict[str, Any]) -> str:
        text, _usage_metadata = self.text_call_with_metadata(request=request)
        return text

    def text_call_with_metadata(self, *, request: dict[str, Any]) -> tuple[str, Any | None]:
        """
        Returns:
            (response_text, usage_metadata)

        To verify cache hit, inspect usage_metadata for:
            cached_content_token_count
        """
        model = str(request.get("model", "")).strip()
        if not model:
            raise ValueError("Gemini request is missing a model.")

        contents, system_instruction = self._convert_messages(request.get("messages", []))
        config = self._build_config(request, system_instruction=system_instruction)

        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        self.last_usage_metadata = getattr(response, "usage_metadata", None)

        return self._response_text(response).strip(), self.last_usage_metadata

    # ---------------------------------------------------------------------
    # Explicit prompt cache APIs
    # ---------------------------------------------------------------------

    def create_prompt_cache(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        contents: list[Any] | str | None = None,
        system_instruction: str | None = None,
        display_name: str | None = None,
        ttl: str = "3600s",
    ) -> str:
        """
        Create an explicit Gemini prompt cache.

        Option A: cache OpenAI-style messages:
            cache_name = client.create_prompt_cache(
                model="gemini-2.5-flash",
                messages=[
                    {"role": "system", "content": "...long stable rules..."},
                    {"role": "user", "content": "...long stable context..."},
                ],
            )

        Option B: cache raw contents:
            cache_name = client.create_prompt_cache(
                model="gemini-2.5-flash",
                system_instruction="...",
                contents=["...long stable document..."],
            )

        Later reuse:
            client.text_call({
                "model": "gemini-2.5-flash",
                "cached_content": cache_name,
                "messages": [
                    {"role": "user", "content": "Question about cached context"}
                ],
            })
        """
        model = model.strip()
        if not model:
            raise ValueError("Gemini cache requires a model.")

        cache_contents: list[Any]
        cache_system_instruction = system_instruction

        if messages is not None:
            converted_contents, converted_system_instruction = self._convert_messages(messages)
            cache_contents = converted_contents

            if cache_system_instruction is None:
                cache_system_instruction = converted_system_instruction

        elif contents is not None:
            if isinstance(contents, str):
                cache_contents = [contents]
            elif isinstance(contents, list):
                cache_contents = contents
            else:
                raise ValueError("contents must be a string, a list, or None.")
        else:
            raise ValueError("create_prompt_cache requires either messages or contents.")

        kwargs: dict[str, Any] = {
            "contents": cache_contents,
            "ttl": ttl,
        }

        if display_name:
            kwargs["display_name"] = display_name

        if cache_system_instruction:
            kwargs["system_instruction"] = cache_system_instruction

        cache = self._client.caches.create(
            model=model,
            config=self._types.CreateCachedContentConfig(**kwargs),
        )

        cache_name = getattr(cache, "name", None)
        if not isinstance(cache_name, str) or not cache_name:
            raise RuntimeError(f"Gemini cache create returned no cache name: {cache!r}")

        return cache_name

    def update_prompt_cache_ttl(self, *, cache_name: str, ttl: str) -> Any:
        """
        Extend or reduce cache TTL.
        Only TTL / expire_time can be changed after creation.
        """
        if not cache_name:
            raise ValueError("cache_name is required.")

        return self._client.caches.update(
            name=cache_name,
            config=self._types.UpdateCachedContentConfig(ttl=ttl),
        )

    def delete_prompt_cache(self, *, cache_name: str) -> Any:
        if not cache_name:
            raise ValueError("cache_name is required.")

        return self._client.caches.delete(name=cache_name)

    # ---------------------------------------------------------------------
    # Message conversion / config
    # ---------------------------------------------------------------------

    def _convert_messages(self, messages: Any) -> tuple[list[Any], str | None]:
        if not isinstance(messages, list):
            raise ValueError("Gemini request messages must be a list.")

        contents: list[Any] = []
        system_parts: list[str] = []

        for message in messages:
            if not isinstance(message, dict):
                continue

            role = str(message.get("role", "")).strip().lower()
            text = _message_content_to_text(message.get("content", "")).strip()

            if not text:
                continue

            if role == "system":
                system_parts.append(text)
                continue

            contents.append(
                self._types.Content(
                    role="model" if role == "assistant" else "user",
                    parts=[self._types.Part.from_text(text=text)],
                )
            )

        if not contents:
            raise ValueError("Gemini request has no user or assistant messages.")

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return contents, system_instruction

    def _build_config(self, request: dict[str, Any], *, system_instruction: str | None) -> Any:
        kwargs: dict[str, Any] = {}

        cached_content = request.get("cached_content") or request.get("cachedContent")

        # If explicit cache is used, prefer system_instruction stored inside the cache.
        # Passing another system_instruction together with cached_content can be invalid
        # or confusing depending on the Gemini model/API behavior.
        if cached_content:
            kwargs["cached_content"] = str(cached_content)
        elif system_instruction:
            kwargs["system_instruction"] = system_instruction

        if "temperature" in request:
            kwargs["temperature"] = request["temperature"]

        if "top_p" in request:
            kwargs["top_p"] = request["top_p"]

        if "n" in request:
            kwargs["candidate_count"] = request["n"]

        max_output_tokens = self._max_output_tokens_for_model(request)
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens

        stop = request.get("stop")
        if isinstance(stop, str):
            kwargs["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            kwargs["stop_sequences"] = [str(item) for item in stop]

        response_format = request.get("response_format")
        if response_format is not None:
            kwargs["response_mime_type"] = "application/json"
            schema = self._extract_json_schema(response_format)
            if schema is not None:
                kwargs["response_schema"] = schema

        thinking_config = self._thinking_config_for_model(str(request.get("model", "")))
        if thinking_config == "low":
            kwargs["thinking_config"] = self._types.ThinkingConfig(thinking_level="low")
        elif thinking_config == "zero_budget":
            kwargs["thinking_config"] = self._types.ThinkingConfig(thinking_budget=0)

        return self._types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _extract_json_schema(response_format: Any) -> dict[str, Any] | None:
        if not isinstance(response_format, dict):
            return None

        json_schema = response_format.get("json_schema")
        if not isinstance(json_schema, dict):
            return None

        schema = json_schema.get("schema")
        return _sanitize_response_schema(schema) if isinstance(schema, dict) else None

    @staticmethod
    def _response_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text:
            return text

        candidates = getattr(response, "candidates", None) or []
        parts: list[str] = []

        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    parts.append(part_text)

        return "".join(parts)

    # ---------------------------------------------------------------------
    # Batch APIs
    # ---------------------------------------------------------------------

    def batch_call(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
    ) -> dict[str, Any]:
        if not requests:
            raise ValueError("Gemini batch requires at least one request.")

        model = self._batch_model(requests)

        input_file.parent.mkdir(parents=True, exist_ok=True)
        with input_file.open("w", encoding="utf-8") as handle:
            for request in requests:
                handle.write(json.dumps(self._convert_batch_request(request), ensure_ascii=False) + "\n")

        uploaded_file = self._client.files.upload(
            file=str(input_file),
            config=self._types.UploadFileConfig(
                display_name=input_file.stem,
                mime_type="jsonl",
            ),
        )
        active_file = self._wait_for_uploaded_file(uploaded_file)

        batch = self._create_batch_job_rest(
            model=model,
            file_name=active_file.name,
            display_name=input_file.stem,
        )

        metadata = self._batch_metadata(batch)
        metadata.update(
            {
                "provider": "gemini",
                "model": model,
                "implicit_cache": True,
                "implicit_cache_strategy": "stable system_instruction prefix",
                "completion_window": completion_window,
                "input_file_id": getattr(active_file, "name", ""),
                "input_file_uri": getattr(active_file, "uri", ""),
                "input_file": str(input_file),
                "request_count": len(requests),
            }
        )

        return metadata

    def _wait_for_uploaded_file(
        self,
        uploaded_file: Any,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 120.0,
    ) -> Any:
        file_name = getattr(uploaded_file, "name", "")
        if not file_name:
            raise RuntimeError(f"Gemini file upload returned no file name: {uploaded_file!r}")

        deadline = time.monotonic() + timeout_seconds
        file_info = self._client.files.get(name=file_name)
        while self._file_state_name(file_info) == "PROCESSING":
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Gemini uploaded batch input file stayed PROCESSING "
                    f"for more than {timeout_seconds:.0f}s: {file_name}"
                )
            time.sleep(poll_interval_seconds)
            file_info = self._client.files.get(name=file_name)

        latest_state = self._file_state_name(file_info)
        if latest_state in {"FAILED", "FILE_STATE_FAILED"}:
            raise RuntimeError(
                f"Gemini uploaded batch input file failed processing: "
                f"{file_name} ({latest_state})"
            )

        return file_info

    @staticmethod
    def _file_state_name(file_obj: Any) -> str:
        state = getattr(file_obj, "state", "")
        name = getattr(state, "name", None)
        if isinstance(name, str) and name:
            return name.upper()
        value = getattr(state, "value", None)
        if isinstance(value, str) and value:
            return value.upper()
        return str(state).rsplit(".", 1)[-1].upper()

    def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        return self._batch_metadata(self._get_batch_job_rest(batch_id))

    def poll_batch_request(
        self,
        *,
        batch_id: str,
        log_file: Path | None = None,
    ) -> dict[str, Any]:
        """Poll one Gemini batch once without waiting.

        This is intended for manual polling from scripts or notebooks after a
        batch has already been submitted. It performs a single GET request,
        returns normalized metadata, and optionally appends that metadata to a
        JSONL log.
        """
        batch_id = batch_id.strip()
        if not batch_id:
            raise ValueError("batch_id is required.")

        metadata = self.retrieve_batch(batch_id)
        metadata["provider"] = "gemini"
        metadata["polled_manually"] = True

        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        return metadata

    def wait_for_batch(self, *, batch_id: str, poll_interval_seconds: float) -> dict[str, Any]:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0.")

        while True:
            metadata = self.retrieve_batch(batch_id)
            state = str(metadata.get("provider_state", ""))
            status = str(metadata.get("status", ""))

            print(f"Batch {batch_id} status: {status} ({state})")

            if state in GEMINI_BATCH_TERMINAL_STATES:
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
            part_input_file = input_file.with_name(
                f"{input_file.stem}_part{part_index:03d}{input_file.suffix}"
            )

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
                if status not in {"failed", "expired", "cancelled"}:
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

    def _batch_model(self, requests: list[dict[str, Any]]) -> str:
        models = {
            str(self._openai_batch_body(request).get("model", "")).strip()
            for request in requests
        }

        models.discard("")

        if not models:
            raise ValueError("Gemini batch request is missing a model.")

        if len(models) != 1:
            raise ValueError(
                f"Gemini batch requests must use one model per batch, got: {sorted(models)}"
            )

        return next(iter(models))

    def _convert_batch_request(self, request: dict[str, Any]) -> dict[str, Any]:
        custom_id = str(request.get("custom_id") or request.get("key") or "").strip()
        if not custom_id:
            raise ValueError("Gemini batch request is missing custom_id/key.")

        return {
            "key": custom_id,
            "request": self._convert_generate_content_request(
                self._openai_batch_body(request)
            ),
        }

    @staticmethod
    def _openai_batch_body(request: dict[str, Any]) -> dict[str, Any]:
        body = request.get("body", request)

        if not isinstance(body, dict):
            raise ValueError("Gemini batch request body must be a JSON object.")

        return body

    def _convert_generate_content_request(self, request: dict[str, Any]) -> dict[str, Any]:
        contents, system_instruction = _convert_messages_to_dicts(
            request.get("messages", []),
            require_content_message=True,
            empty_content_error="Gemini batch requests require at least one user or assistant message.",
        )

        converted: dict[str, Any] = {}

        cached_content = request.get("cached_content") or request.get("cachedContent")

        if cached_content:
            # REST field name is camelCase.
            converted["cachedContent"] = str(cached_content)
        elif system_instruction:
            # Gemini implicit caching is automatic. Keeping the large stable
            # instruction prefix first improves the chance of cache hits.
            converted["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }

        converted["contents"] = contents

        generation_config = self._build_generation_config_dict(request)
        if generation_config:
            converted["generation_config"] = generation_config

        return converted

    def _build_generation_config_dict(self, request: dict[str, Any]) -> dict[str, Any]:
        config: dict[str, Any] = {}

        if "temperature" in request:
            config["temperature"] = request["temperature"]

        if "top_p" in request:
            config["top_p"] = request["top_p"]

        if "n" in request:
            config["candidate_count"] = request["n"]

        max_output_tokens = self._max_output_tokens_for_model(request)
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens

        stop = request.get("stop")
        if isinstance(stop, str):
            config["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            config["stop_sequences"] = [str(item) for item in stop]

        response_format = request.get("response_format")
        if response_format is not None:
            config["response_mime_type"] = "application/json"
            schema = self._extract_json_schema(response_format)
            if schema is not None:
                config["response_schema"] = schema

        thinking_config = self._thinking_config_for_model(str(request.get("model", "")))
        if thinking_config == "low":
            config["thinking_config"] = {"thinking_level": "low"}
        elif thinking_config == "zero_budget":
            config["thinking_config"] = {"thinking_budget": 0}

        return config

    @staticmethod
    def _thinking_config_for_model(model: str) -> str:
        normalized = model.strip().lower()
        if normalized.startswith("models/"):
            normalized = normalized.removeprefix("models/")

        if normalized.startswith("gemini-3.1-pro"):
            return "low"

        if normalized.startswith("gemini-3"):
            return ""

        return "zero_budget"

    @classmethod
    def _max_output_tokens_for_model(cls, request: dict[str, Any]) -> int | None:
        value = request.get("max_output_tokens", request.get("max_completion_tokens"))
        if value is None:
            return None

        try:
            max_output_tokens = int(value)
        except (TypeError, ValueError):
            return value

        model = str(request.get("model", "")).strip().lower()
        if model.startswith("models/"):
            model = model.removeprefix("models/")

        if model.startswith("gemini-3.1-pro"):
            return max(max_output_tokens, 3072)

        return max_output_tokens

    def _create_batch_job_rest(
        self,
        *,
        model: str,
        file_name: str,
        display_name: str,
    ) -> dict[str, Any]:
        response = self._request_rest(
            "post",
            f"{self._model_path(model)}:batchGenerateContent",
            json_body={
                "batch": {
                    "display_name": display_name,
                    "input_config": {"file_name": file_name},
                }
            },
        )

        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected Gemini batch create response: {response!r}")

        return response

    def _get_batch_job_rest(self, batch_id: str) -> dict[str, Any]:
        response = self._request_rest("get", batch_id)

        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected Gemini batch get response: {response!r}")

        return response

    def _request_rest(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency 'requests'. Install it with: pip install requests"
            ) from exc

        url = f"https://generativelanguage.googleapis.com/v1beta/{path.lstrip('/')}"

        response = requests.request(
            method,
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            json=json_body,
            timeout=self._timeout,
        )

        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini Batch API request failed ({response.status_code}): {payload}"
            )

        return payload

    @staticmethod
    def _model_path(model: str) -> str:
        model = model.strip().lstrip("/")
        return model if model.startswith("models/") else f"models/{model}"

    @staticmethod
    def _batch_metadata(batch: Any) -> dict[str, Any]:
        metadata = _get(batch, "metadata", {}) or {}
        state = _state_name(_get(batch, "state", _get(metadata, "state", "")))
        dest = _get(batch, "dest", _get(metadata, "dest", None))
        output_config = _get(batch, "output_config", _get(batch, "outputConfig", None))
        output = _get(metadata, "output", _get(batch, "output", None))
        response = _get(batch, "response", None)
        output_file_id = _first_non_empty(
            _get(dest, "file_name", ""),
            _get(dest, "fileName", ""),
            _get(dest, "uri", ""),
            _get(output_config, "file_name", ""),
            _get(output_config, "fileName", ""),
            _get(output_config, "uri", ""),
            _get(output, "responses_file", ""),
            _get(output, "responsesFile", ""),
            _get(response, "responses_file", ""),
            _get(response, "responsesFile", ""),
            _get(batch, "output_file_id", ""),
            _get(batch, "outputFileId", ""),
            _find_first_key(
                batch,
                {"responsesFile", "responses_file", "fileName", "file_name", "outputFile", "output_file"},
            ),
        )

        return {
            "batch_id": _get(batch, "name", ""),
            "display_name": _get(batch, "display_name", _get(batch, "displayName", "")),
            "provider_state": state,
            "status": GEMINI_BATCH_STATUS_MAP.get(state, state.lower()),
            "output_file_id": output_file_id,
            "error": _jsonable(_get(batch, "error", None)),
            "batch_stats": _jsonable(
                _get(batch, "batch_stats", _get(metadata, "batch_stats", None))
            ),
            "raw_batch": _jsonable(batch),
        }


def _sanitize_response_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {
            key: _sanitize_response_schema(value)
            for key, value in schema.items()
            if key not in {"additionalProperties", "$schema"}
        }

    if isinstance(schema, list):
        return [_sanitize_response_schema(item) for item in schema]

    return schema


def _convert_messages_to_dicts(
    messages: Any,
    *,
    require_content_message: bool = True,
    empty_content_error: str = "Gemini request has no user or assistant messages.",
) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(messages, list):
        raise ValueError("Gemini request messages must be a list.")

    contents: list[dict[str, Any]] = []
    system_parts: list[str] = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        role = str(message.get("role", "")).strip().lower()
        text = _message_content_to_text(message.get("content", "")).strip()

        if not text:
            continue

        if role == "system":
            system_parts.append(text)
            continue

        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )

    if require_content_message and not contents:
        raise ValueError(empty_content_error)

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return contents, system_instruction


def _state_name(state: Any) -> str:
    name = getattr(state, "name", None)

    if isinstance(name, str):
        return name

    if isinstance(state, str):
        return state

    return str(state)


def _get(value: Any, snake_name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        if snake_name in value:
            return value[snake_name]

        camel_name = _snake_to_camel(snake_name)
        return value.get(camel_name, default)

    return getattr(value, snake_name, default)


def _snake_to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _find_first_key(value: Any, keys: set[str]) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                text = str(item or "").strip()
                if text:
                    return text
            found = _find_first_key(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_key(item, keys)
            if found:
                return found
    return ""


def _jsonable(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()

    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_jsonable(item) for item in value]

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)
