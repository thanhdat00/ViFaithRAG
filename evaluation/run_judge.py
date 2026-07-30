"""
Run the ViFaithRAG Task-2 judge over one or more contestant models' answers.

INPUTS
------
1. Dataset JSONL (the benchmark): each line a record with at least
   {id, query, answerability_label, ground_truth_answer}.
2. Contestant answers JSONL: each line {id, model_id, answer}.
   (One file may contain multiple model_ids, or pass several files.)

OUTPUT
------
Per-record scores JSONL at --out: one line per (id, model_id) with the
RecordScore fields from scoring.py.

USAGE
-----
  # Claude Haiku via Batch API (cheapest):
  python run_judge.py \
      --dataset ViFaithRAG.jsonl \
      --answers answers_modelA.jsonl answers_modelB.jsonl \
      --backend anthropic --judge-model claude-haiku-4-5 \
      --out scores.jsonl

  # Qwen (OpenAI-compatible endpoint):
  JUDGE_BASE_URL=http://localhost:8000/v1 JUDGE_API_KEY=EMPTY \
  python run_judge.py \
      --dataset ViFaithRAG.jsonl --answers answers.jsonl \
      --backend openai --judge-model Qwen3.5-397B-A17B-FP8 \
      --out scores.jsonl

  # Claude Sonnet through OpenRouter (synchronous OpenAI-compatible API):
  OPENROUTER_API_KEY=... \
  python run_judge.py \
      --dataset ViFaithRAG.jsonl --answers answers.jsonl \
      --backend openrouter --judge-model claude-sonnet-4.6 \
      --out scores_openrouter_sonnet.jsonl

Notes
-----
- custom_id encodes (id, model_id) so batch results map back unambiguously.
- Anthropic backend submits the batch, logs metadata, and exits. Use
  scoring.py to pull the completed batch results and score them later.
- Claude Sonnet uses Anthropic prompt caching by default for the shared judge
  system prompt and fixed user prompt prefix. Override with --prompt-cache /
  --no-prompt-cache; default cache TTL is 5 minutes.
- Records whose label is YES/PARTIAL but which lack ground_truth_answer are skipped
  with an error row (should not happen in a clean dataset).
- Re-running is safe: existing --out is overwritten; use --resume to skip done pairs.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.judge import build_judge_message_parts, build_judge_messages  # noqa: E402
from scoring import score_record, RecordScore  # noqa: E402


SEP = "\u241f"  # unit separator, unlikely to appear in ids


def _pair_key(rec_id: str, model_id: str) -> str:
    return f"{rec_id}{SEP}{model_id}"


def _safe_custom_id(index: int, rec_id: str, model_id: str) -> str:
    digest = hashlib.md5(_pair_key(rec_id, model_id).encode("utf-8")).hexdigest()[:16]
    return f"judge_{index}_{digest}"


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_jsonl_many(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def default_batch_submission_log_path(out_path: Path, judge_model: str) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in judge_model)
    return out_path.with_name(f"{out_path.stem}_{safe_model}_batch_submission_log.jsonl")


def default_batch_request_map_path(out_path: Path, judge_model: str) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in judge_model)
    return out_path.with_name(f"{out_path.stem}_{safe_model}_batch_request_map.jsonl")


def default_batch_input_log_path(out_path: Path, judge_model: str) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in judge_model)
    return out_path.with_name(f"{out_path.stem}_{safe_model}_batch_input.jsonl")


def default_openrouter_raw_log_path(out_path: Path, judge_model: str) -> Path:
    safe_model = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
        for ch in judge_model
    )
    return out_path.with_name(f"{out_path.stem}_{safe_model}_openrouter_raw.jsonl")


def write_jsonl_many(path: Path, records: list[dict], *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_workitems(dataset: dict[str, dict], answers: list[dict]) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Create judge work items from contestant answers joined to dataset records."""
    items = []
    skipped = []
    for index, a in enumerate(answers, start=1):
        rid, model_id, ans = a["id"], a["model_id"], a["answer"]
        rec = dataset.get(rid)
        if rec is None:
            skipped.append((rid, model_id, "record id not in dataset"))
            continue
        try:
            system, user_cache_prefix, user_remainder, user_suffix = build_judge_message_parts(rec, ans)
            system, user = build_judge_messages(rec, ans)
        except Exception as e:  # noqa: BLE001
            skipped.append((rid, model_id, f"prompt build failed: {e}"))
            continue
        items.append(
            {
                "custom_id": _safe_custom_id(index, rid, model_id),
                "record_id": rid,
                "model_id": model_id,
                "system": system,
                "user": user,
                "user_cache_prefix": user_cache_prefix,
                "user_remainder": user_remainder,
                "user_suffix": user_suffix,
            }
        )
    return items, skipped


def default_prompt_cache_enabled(backend: str, judge_model: str) -> bool:
    model = judge_model.lower()
    return backend == "anthropic" and "claude" in model and "sonnet" in model


def prompt_cache_sort_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("user_cache_prefix", "")),
        str(item.get("record_id", "")),
        str(item.get("model_id", "")),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--answers", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", choices=["anthropic", "openai", "openrouter"], required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--judge-base-url", default=None)
    ap.add_argument("--judge-max-tokens", type=int, default=4096)
    ap.add_argument("--max-workers", type=int, default=8, help="openai/openrouter sync backends only")
    ap.add_argument(
        "--openrouter-raw-log",
        type=Path,
        default=None,
        help=(
            "OpenRouter request/response audit JSONL. Defaults to "
            "<out_stem>_<judge_model>_openrouter_raw.jsonl."
        ),
    )
    ap.add_argument(
        "--batch-submission-log",
        type=Path,
        default=None,
        help="Anthropic batch submission log JSONL. Defaults to <out_stem>_<judge_model>_batch_submission_log.jsonl.",
    )
    ap.add_argument(
        "--batch-request-map",
        type=Path,
        default=None,
        help="Anthropic custom_id map JSONL. Defaults to <out_stem>_<judge_model>_batch_request_map.jsonl.",
    )
    ap.add_argument(
        "--batch-input-log",
        type=Path,
        default=None,
        help="Anthropic batch input JSONL. Defaults to <out_stem>_<judge_model>_batch_input.jsonl.",
    )
    ap.add_argument(
        "--no-submit",
        action="store_true",
        help="Build and log Anthropic batch inputs, then exit before submitting to the Batch API.",
    )
    cache_group = ap.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--prompt-cache",
        dest="prompt_cache",
        action="store_true",
        default=None,
        help="Enable Anthropic prompt caching for the shared system prompt and fixed user prompt prefix.",
    )
    cache_group.add_argument(
        "--no-prompt-cache",
        dest="prompt_cache",
        action="store_false",
        help="Disable Anthropic prompt caching.",
    )
    ap.add_argument(
        "--prompt-cache-ttl",
        choices=["5m", "1h"],
        default="1h",
        help="Anthropic prompt cache TTL. The 1h TTL costs more; default is 5m.",
    )
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    if args.prompt_cache is None:
        args.prompt_cache = default_prompt_cache_enabled(args.backend, args.judge_model)
    out_path = Path(args.out)
    if args.batch_submission_log is None:
        args.batch_submission_log = default_batch_submission_log_path(out_path, args.judge_model)
    if args.batch_request_map is None:
        args.batch_request_map = default_batch_request_map_path(out_path, args.judge_model)
    if args.batch_input_log is None:
        args.batch_input_log = default_batch_input_log_path(out_path, args.judge_model)
    if args.backend == "openrouter" and args.openrouter_raw_log is None:
        args.openrouter_raw_log = default_openrouter_raw_log_path(
            out_path, args.judge_model
        )

    dataset = {r["id"]: r for r in load_jsonl(args.dataset)}
    answers = []
    for p in args.answers:
        answers.extend(load_jsonl(p))
    print(f"[info] {len(dataset)} records, {len(answers)} contestant answers", file=sys.stderr)

    done: set[str] = set()
    if args.resume and Path(args.out).exists():
        for r in load_jsonl(args.out):
            done.add(_pair_key(r["id"], r["model_id"]))
        print(f"[info] resume: {len(done)} pairs already scored", file=sys.stderr)

    items, skipped = build_workitems(dataset, answers)
    if args.resume:
        items = [it for it in items if _pair_key(it["record_id"], it["model_id"]) not in done]
    if args.backend == "anthropic" and args.prompt_cache:
        items = sorted(items, key=prompt_cache_sort_key)
        cache_prefix_count = len({str(it.get("user_cache_prefix", "")) for it in items})
        print(
            f"[info] grouped Anthropic batch by {cache_prefix_count} cached user prompt prefix(es)",
            file=sys.stderr,
        )
    for rid, mid, why in skipped:
        print(f"[warn] skip {rid}/{mid}: {why}", file=sys.stderr)
    print(f"[info] {len(items)} judge calls to run", file=sys.stderr)

    # --- run judge ---
    if args.backend == "anthropic":
        from judge_clients import AnthropicBatchJudge
        judge = AnthropicBatchJudge(
            model=args.judge_model,
            max_tokens=args.judge_max_tokens,
            prompt_cache=args.prompt_cache,
            prompt_cache_ttl=args.prompt_cache_ttl,
        )
        if args.prompt_cache:
            print(
                "[info] Anthropic prompt caching enabled for shared judge system prompt "
                f"and fixed user prompt prefix (ttl={args.prompt_cache_ttl})",
                file=sys.stderr,
            )
        batch_requests = judge.build_requests(items)
        append_jsonl_many(args.batch_input_log, batch_requests)
        if args.no_submit:
            append_jsonl_many(
                args.batch_request_map,
                [
                    {
                        "batch_id": "",
                        "custom_id": it["custom_id"],
                        "record_id": it["record_id"],
                        "model_id": it["model_id"],
                    }
                    for it in items
                ],
            )
            print("[done] wrote Anthropic batch input log; submission skipped", file=sys.stderr)
            print(f"[info] batch input: {args.batch_input_log}", file=sys.stderr)
            print(f"[info] request map: {args.batch_request_map}", file=sys.stderr)
            return
        batch_id = judge.submit(items, requests=batch_requests)
        append_jsonl_many(
            args.batch_request_map,
            [
                {
                    "batch_id": batch_id,
                    "custom_id": it["custom_id"],
                    "record_id": it["record_id"],
                    "model_id": it["model_id"],
                }
                for it in items
            ],
        )
        append_jsonl(
            args.batch_submission_log,
            {
                "batch_id": batch_id,
                "judge_model": args.judge_model,
                "backend": args.backend,
                "request_count": len(items),
                "judge_max_tokens": args.judge_max_tokens,
                "prompt_cache": bool(args.prompt_cache),
                "prompt_cache_ttl": args.prompt_cache_ttl if args.prompt_cache else None,
                "batch_input_log": str(args.batch_input_log),
                "batch_request_map": str(args.batch_request_map),
                "target_scores": str(out_path),
                "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        print(f"[done] submitted Anthropic batch {batch_id}", file=sys.stderr)
        print(f"[info] submission log: {args.batch_submission_log}", file=sys.stderr)
        print(f"[info] batch input: {args.batch_input_log}", file=sys.stderr)
        print(f"[info] request map: {args.batch_request_map}", file=sys.stderr)
        print("[info] run evaluation/scoring.py after the batch completes", file=sys.stderr)
        return
    else:
        if args.backend == "openrouter":
            from judge_clients import OpenRouterJudge
            judge = OpenRouterJudge(
                model=args.judge_model,
                base_url=args.judge_base_url,
                max_tokens=args.judge_max_tokens,
            )
            raw_result_by_cid = judge.judge_many_raw(
                items, max_workers=args.max_workers
            )
            raw_by_cid = {
                cid: result.get("response_text", "")
                for cid, result in raw_result_by_cid.items()
            }
            raw_log_rows = []
            for item in items:
                result = raw_result_by_cid.get(
                    item["custom_id"],
                    {
                        "request": None,
                        "response": None,
                        "response_text": "",
                        "error": "missing OpenRouter result",
                    },
                )
                raw_log_rows.append(
                    {
                        "custom_id": item["custom_id"],
                        "record_id": item["record_id"],
                        "model_id": item["model_id"],
                        "judge_model": judge.model,
                        "backend": "openrouter",
                        "request": result.get("request"),
                        "response": result.get("response"),
                        "response_text": result.get("response_text", ""),
                        "error": result.get("error"),
                    }
                )
            write_jsonl_many(
                args.openrouter_raw_log,
                raw_log_rows,
                append=args.resume and args.openrouter_raw_log.exists(),
            )
            print(
                f"[info] OpenRouter raw request/response log: "
                f"{args.openrouter_raw_log}",
                file=sys.stderr,
            )
        else:
            from judge_clients import OpenAICompatJudge
            judge = OpenAICompatJudge(
                model=args.judge_model,
                base_url=args.judge_base_url,
                max_tokens=args.judge_max_tokens,
            )
            raw_by_cid = judge.judge_many(items, max_workers=args.max_workers)

    # --- score + write ---
    mode = "a" if (args.resume and Path(args.out).exists()) else "w"
    n_ok = n_err = 0
    with open(args.out, mode, encoding="utf-8") as f:
        for it in items:
            cid = it["custom_id"]
            rid, model_id = it["record_id"], it["model_id"]
            rec = dataset[rid]
            raw = raw_by_cid.get(cid, "")
            rs: RecordScore = score_record(rec, model_id, raw)
            n_ok += rs.parse_ok
            n_err += (not rs.parse_ok)
            d = rs.to_dict()
            d.pop("raw", None)  # keep scores file lean; raw kept only on failures
            if not rs.parse_ok:
                d["raw"] = raw
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"[done] scored={n_ok} parse_errors={n_err} -> {args.out}", file=sys.stderr)
    if n_err:
        print(f"[warn] {n_err} parse failures; inspect `raw` fields and re-run --resume",
              file=sys.stderr)


if __name__ == "__main__":
    main()
