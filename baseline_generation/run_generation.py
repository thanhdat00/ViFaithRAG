"""
Generate contestant answers over the ViFaithRAG dataset.

Output keeps the judge-required fields and also records the API model name:
    {"id": ..., "model_id": ..., "model": ..., "answer": ...}
one line per record, so it feeds straight into run_judge.py --answers.

USAGE
-----
  # sync (any backend)
  python task/contestants/run_generation.py \
      --dataset ViFaithRAG.jsonl \
      --backend openai --model gpt-5.5 --model-id gpt-5.5 \
      --out answers_gpt.jsonl --max-workers 8

  # local / OpenAI-compatible endpoint (e.g., a served open model)
  OPENAI_BASE_URL=http://localhost:8000/v1 OPENAI_API_KEY=EMPTY \
  python task/contestants/run_generation.py --dataset ViFaithRAG.jsonl \
      --backend openai --model my-open-model --model-id my-open-model \
      --out answers_open.jsonl

  # Gemma via OpenRouter
  OPENROUTER_API_KEY=... \
  python task/contestants/run_generation.py --dataset ViFaithRAG.jsonl \
      --backend openrouter-gemma --model gemma-4-31b-it --model-id gemma-4-31b-it \
      --out answers_gemma-4-31b-it.jsonl

  # Claude via Batch API (best for large runs)
  python task/contestants/run_generation.py --dataset ViFaithRAG.jsonl \
      --backend anthropic --model claude-sonnet-4-6 --model-id claude-sonnet-4-6 \
      --out answers_sonnet.jsonl --use-batch

  # Gemini via Batch API
  python task/contestants/run_generation.py --dataset ViFaithRAG.jsonl \
      --backend google --model gemini-3.1-pro --model-id gemini-3.1-pro \
      --out answers_gemini.jsonl --use-batch --batch-size 1000

NOTES
-----
- --model-id is the label that appears in outputs and on the leaderboard; keep it
  the exact pinned model string.
- Generation sees the FULL 3-doc context and is NOT told the label (fair setting).
- temperature 0; --resume skips ids already generated.
- Contestant answers are generated once and reused across judge runs.
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.ground_truth_generation import build_generation_messages  # noqa: E402
from gen_clients import make_client  # noqa: E402
try:
    from .gemini_client import GeminiBatchClient  # noqa: E402
except ImportError:
    from gemini_client import GeminiBatchClient  # noqa: E402


SEP = "\u241f"


def safe_name_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return cleaned.strip("._") or "model"


def default_output_path(
    dataset_path: Path,
    model_id: str,
    *,
    output_dir: Path | None = None,
    output_prefix: str = "answers",
) -> Path:
    dataset_name = safe_name_part(dataset_path.stem)
    model_name = safe_name_part(model_id)
    prefix = safe_name_part(output_prefix)
    output_dir = output_dir or Path(__file__).resolve().parent
    return output_dir / f"{prefix}_{dataset_name}_{model_name}.jsonl"


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def default_error_log_path(out_path: Path) -> Path:
    return out_path.with_name(f"{out_path.stem}_errors.jsonl")


def log_error(error_log: Path, *, record_id: str, args: argparse.Namespace, error: Any, stage: str) -> None:
    append_jsonl(
        error_log,
        {
            "id": record_id,
            "model_id": args.model_id,
            "model": args.model,
            "backend": args.backend,
            "stage": stage,
            "error": str(error),
            "logged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def is_valid_answer_record(record: dict, model_id: str) -> bool:
    return (
        isinstance(record, dict)
        and str(record.get("id") or "").strip()
        and str(record.get("model_id") or "").strip() == model_id
        and isinstance(record.get("answer"), str)
        and bool(record["answer"].strip())
        and not record.get("contestant_error")
    )


def load_completed_records(path: Path, model_id: str, model: str) -> dict[str, dict]:
    completed: dict[str, dict] = {}
    if not path.exists():
        return completed
    for record in load_jsonl(path):
        if is_valid_answer_record(record, model_id):
            completed[str(record["id"])] = {
                "id": str(record["id"]),
                "model_id": model_id,
                "model": str(record.get("model") or model),
                "answer": record["answer"].strip(),
            }
    return completed


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def contestant_batch_stem(out_path: Path, model_id: str) -> str:
    return f"{out_path.stem}_{safe_name_part(model_id)}"


def gemini_batch_input_path(out_path: Path, model_id: str) -> Path:
    return Path("tmp") / f"{contestant_batch_stem(out_path, model_id)}_contestant_batch_input.jsonl"


def gemini_batch_response_path(out_path: Path, model_id: str) -> Path:
    return Path("tmp") / f"{contestant_batch_stem(out_path, model_id)}_contestant_batch_response.jsonl"


def gemini_batch_submission_log_path(out_path: Path, model_id: str) -> Path:
    return out_path.with_name(f"{contestant_batch_stem(out_path, model_id)}_contestant_batch_submission_log.jsonl")


def build_gemini_batch_request(record: dict, *, model: str, max_tokens: int) -> dict[str, Any]:
    sysp, usr = build_generation_messages(record)
    return {
        "custom_id": str(record["id"]),
        "body": {
            "model": model,
            "temperature": 0,
            "max_output_tokens": max_tokens,
            "thinking_level": "minimal",
            "include_thoughts": False,
            "messages": [
                {"role": "system", "content": sysp},
                {"role": "user", "content": usr},
            ],
        },
    }


def extract_gemini_batch_text(payload: dict[str, Any]) -> str:
    response = payload.get("response", {})
    if not isinstance(response, dict):
        return ""
    candidates = response.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        return ""
    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return ""
    finish_reason = str(first_candidate.get("finishReason") or "").strip().upper()
    if finish_reason in {"MAX_TOKENS", "SAFETY", "RECITATION", "MALFORMED_FUNCTION_CALL", "OTHER"}:
        return ""
    content = first_candidate.get("content", {})
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts", [])
    if not isinstance(parts, list):
        return ""
    text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(text for text in text_parts if isinstance(text, str)).strip()


def load_gemini_batch_answers(response_file: Path) -> dict[str, str]:
    answers: dict[str, str] = {}
    with response_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Gemini batch response line {line_number} is not a JSON object.")
            custom_id = str(payload.get("key") or payload.get("custom_id") or "").strip()
            if not custom_id:
                continue
            answer = extract_gemini_batch_text(payload)
            if answer:
                answers[custom_id] = answer
    return answers


def run_gemini_batch(records: list[dict], args: argparse.Namespace, out_path: Path) -> None:
    if args.batch_size <= 0:
        sys.exit("--batch-size must be greater than 0")
    if args.batch_poll_interval <= 0:
        sys.exit("--batch-poll-interval must be greater than 0")

    client = GeminiBatchClient(timeout=args.timeout)
    batch_requests = [
        build_gemini_batch_request(record, model=args.model, max_tokens=args.max_tokens)
        for record in records
    ]
    input_file = gemini_batch_input_path(out_path, args.model_id)
    response_file = gemini_batch_response_path(out_path, args.model_id)
    submission_log_file = gemini_batch_submission_log_path(out_path, args.model_id)

    metadata_rows = client.batch_call_sequential(
        requests=batch_requests,
        input_file=input_file,
        completion_window=args.batch_completion_window,
        batch_size=args.batch_size,
        poll_interval_seconds=args.batch_poll_interval,
        submission_log_file=submission_log_file,
    )

    response_file.parent.mkdir(parents=True, exist_ok=True)
    response_file.write_text("", encoding="utf-8")
    with response_file.open("a", encoding="utf-8") as merged_handle:
        for index, metadata in enumerate(metadata_rows, start=1):
            output_file_id = str(metadata.get("output_file_id", "")).strip()
            if not output_file_id:
                raise RuntimeError(f"Gemini batch completed without output_file_id: {metadata.get('batch_id', '')}")
            part_file = response_file.with_name(f"{response_file.stem}_part{index:03d}{response_file.suffix}")
            client.download_file(file_id=output_file_id, output_path=part_file)
            text = part_file.read_text(encoding="utf-8").strip()
            if text:
                merged_handle.write(text)
                merged_handle.write("\n")

    answers = load_gemini_batch_answers(response_file)
    written = 0
    failed = 0
    for record in tqdm(records, total=len(records), desc="Writing Gemini batch answers", unit="record"):
        rid = str(record["id"])
        answer = (answers.get(rid, "") or "").strip()
        if not answer:
            failed += 1
            log_error(args.error_log, record_id=rid, args=args, error="empty Gemini batch answer", stage="gemini_batch_output")
            print(f"[warn] empty Gemini batch answer id={rid}; will retry on next --resume", file=sys.stderr)
            continue
        append_jsonl(out_path, {"id": rid, "model_id": args.model_id, "model": args.model, "answer": answer})
        written += 1

    print(
        f"[done] Gemini batch wrote {written} new answers, failed {failed} -> {args.out}",
        file=sys.stderr,
    )
    print(f"[info] Gemini batch submission log: {submission_log_file}", file=sys.stderr)
    print(f"[info] Gemini batch response file: {response_file}", file=sys.stderr)
    print(f"[info] error log: {args.error_log}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument(
        "--out",
        default=None,
        help=(
            "Output JSONL path. Defaults to "
            "task/contestants/answers_<dataset_stem>_<model_id>.jsonl"
        ),
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the auto-generated output path when --out is omitted.",
    )
    ap.add_argument(
        "--output-prefix",
        default="answers",
        help="Filename prefix for the auto-generated output path when --out is omitted.",
    )
    ap.add_argument(
        "--backend",
        choices=["anthropic", "openai", "google", "custom", "deepseek", "openrouter", "openrouter-gemma"],
        required=True,
    )
    ap.add_argument("--model", required=True, help="API model string")
    ap.add_argument("--model-id", required=True, help="label for outputs/leaderboard")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--max-workers", type=int, default=8, help="sync backends")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--use-batch", action="store_true", help="Use provider batch API where supported.")
    ap.add_argument("--batch-size", type=int, default=1000, help="Requests per batch part for Gemini batch mode.")
    ap.add_argument("--batch-poll-interval", type=float, default=30.0, help="Seconds between batch status checks.")
    ap.add_argument("--batch-completion-window", default="24h", help="Batch completion window metadata.")
    ap.add_argument(
        "--error-log",
        type=Path,
        default=None,
        help="JSONL file for failed records. Defaults to <out_stem>_errors.jsonl next to --out.",
    )
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--clear-cache", action="store_true")
    args = ap.parse_args()

    dataset_path = Path(args.dataset)
    if args.out is None:
        out_path = default_output_path(
            dataset_path,
            args.model_id,
            output_dir=args.output_dir,
            output_prefix=args.output_prefix,
        )
        args.out = str(out_path)
        print(f"[info] auto output path: {out_path}", file=sys.stderr)
    else:
        if args.output_dir is not None or args.output_prefix != "answers":
            sys.exit("--output-dir/--output-prefix can only be used when --out is omitted")
        out_path = Path(args.out)

    records = load_jsonl(dataset_path)
    print(f"[info] {len(records)} records", file=sys.stderr)

    if args.max_workers <= 0:
        sys.exit("--max-workers must be greater than 0")

    if args.error_log is None:
        args.error_log = default_error_log_path(out_path)
    if args.clear_cache and out_path.exists():
        out_path.unlink()
        print(f"[info] cleared checkpoint/output: {out_path}", file=sys.stderr)
    if args.clear_cache and args.error_log.exists():
        args.error_log.unlink()
        print(f"[info] cleared error log: {args.error_log}", file=sys.stderr)

    completed = load_completed_records(out_path, args.model_id, args.model) if args.resume else {}
    if args.resume and completed:
        write_jsonl(out_path, list(completed.values()))
        print(f"[info] resume: {len(completed)} valid completed answer(s)", file=sys.stderr)
    elif not args.resume:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")

    records = [r for r in records if str(r["id"]) not in completed]
    if not records:
        print(f"[done] resumed {len(completed)}, no new records -> {args.out}", file=sys.stderr)
        return

    # ---- Batch paths ----
    if args.use_batch:
        if args.backend == "google":
            run_gemini_batch(records, args, out_path)
            return
        if args.backend != "anthropic":
            sys.exit("--use-batch is supported for anthropic and google backends")
        client = make_client(args.backend, args.model, args.base_url, args.max_tokens, timeout=args.timeout)
        items = []
        for r in records:
            sysp, usr = build_generation_messages(r)
            items.append({"custom_id": r["id"], "system": sysp, "user": usr})
        bid = client.submit_batch(items)
        print(f"[info] submitted batch {bid}; poll the console/API for completion", file=sys.stderr)
        # For simplicity we block via the judge-style poll on the SDK object:
        while True:
            b = client.client.messages.batches.retrieve(bid)
            if b.processing_status == "ended":
                break
            time.sleep(30)
        res = client.batch_results(bid)
        written = 0
        failed = 0
        for r in tqdm(records, total=len(records), desc="Writing Anthropic batch answers", unit="record"):
            ans = (res.get(r["id"], "") or "").strip()
            if not ans:
                failed += 1
                log_error(args.error_log, record_id=str(r["id"]), args=args, error="empty batch answer", stage="anthropic_batch_output")
                print(f"[warn] empty batch answer id={r['id']}; will retry on next --resume", file=sys.stderr)
                continue
            append_jsonl(out_path, {"id": r["id"], "model_id": args.model_id, "model": args.model, "answer": ans})
            written += 1
        print(f"[done] wrote {written} new answers, failed {failed} -> {args.out}", file=sys.stderr)
        print(f"[info] error log: {args.error_log}", file=sys.stderr)
        return

    client = make_client(args.backend, args.model, args.base_url, args.max_tokens, timeout=args.timeout)

    # ---- sync path (threaded) ----
    def one(r):
        sysp, usr = build_generation_messages(r)
        ans = client.generate(sysp, usr).strip()
        if not ans:
            raise ValueError("empty generated answer")
        return {"id": r["id"], "model_id": args.model_id, "model": args.model, "answer": ans}

    written = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = {ex.submit(one, r): r["id"] for r in records}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="Generating", unit="record"):
            rid = futs[fut]
            try:
                record = fut.result()
            except Exception as error:  # noqa: BLE001
                failed += 1
                log_error(
                    args.error_log,
                    record_id=str(rid),
                    args=args,
                    error=error,
                    stage="sync_worker",
                )
                print(f"[warn] gen failed id={rid}: {error}; will retry on next --resume", file=sys.stderr)
                continue
            append_jsonl(out_path, record)
            written += 1

    print(
        f"[done] resumed {len(completed)}, wrote {written} new answers, failed {failed} -> {args.out}",
        file=sys.stderr,
    )
    print(f"[info] error log: {args.error_log}", file=sys.stderr)


if __name__ == "__main__":
    main()
