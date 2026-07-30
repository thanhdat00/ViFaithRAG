"""
Rejudge zero-completeness model answers with the NO behavioral prompt.

Every input row is judged with ``JUDGE_USER_NO`` regardless of its original
answerability label. This detects abstentions among YES responses whose
completeness score is zero.

Example (Claude Sonnet through OpenRouter):

    python evaluation/rejudge_completeness_zero_as_no.py \
        --backend openrouter \
        --judge-model claude-sonnet-4.6

The parsed output contains ``behavior`` and ``abstained`` fields. A separate
raw JSONL records the exact API request and response for auditing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.judge import JUDGE_SYSTEM_PROMPT, JUDGE_USER_NO  # noqa: E402
from scoring import RecordScore, score_record  # noqa: E402


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    EVALUATION_DIR / "eval_results" / "completeness_zero_model_answers.jsonl"
)
DEFAULT_OUTPUT = (
    EVALUATION_DIR
    / "eval_results"
    / "completeness_zero_model_answers_no_judge.jsonl"
)
PAIR_SEPARATOR = "\u241f"


def pair_key(record_id: str, model_id: str) -> str:
    return f"{record_id}{PAIR_SEPARATOR}{model_id}"


def safe_custom_id(index: int, record_id: str, model_id: str) -> str:
    digest = hashlib.md5(
        pair_key(record_id, model_id).encode("utf-8")
    ).hexdigest()[:16]
    return f"no_rejudge_{index}_{digest}"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected a JSON object in {path} at line {line_number}"
                )
            rows.append(row)
    return rows


def load_candidates(path: Path) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    for line_number, row in enumerate(load_jsonl(path), start=1):
        record_id = str(row.get("id", "")).strip()
        model_id = str(row.get("model_id", "")).strip()
        model_answer = row.get("model_answer")
        if not isinstance(model_answer, str) or not model_answer.strip():
            model_answer = row.get("answer")

        if not record_id:
            raise ValueError(f"Missing id in {path} at row {line_number}")
        if not model_id:
            raise ValueError(
                f"Missing model_id in {path} at row {line_number}"
            )
        if not isinstance(model_answer, str) or not model_answer.strip():
            raise ValueError(
                f"Missing model_answer/answer in {path} at row {line_number}"
            )
        if row.get("completeness") not in (0, 0.0):
            raise ValueError(
                f"Expected completeness=0 in {path} at row {line_number}; "
                f"got {row.get('completeness')!r}"
            )

        key = pair_key(record_id, model_id)
        if key in seen:
            raise ValueError(
                f"Duplicate (id, model_id) pair in {path} at row "
                f"{line_number}: {record_id}/{model_id}"
            )
        seen.add(key)
        candidates.append(
            {
                "id": record_id,
                "model_id": model_id,
                "model_answer": model_answer.strip(),
                "answerability_label": row.get(
                    "answerability_label", row.get("label")
                ),
                "completeness": row.get("completeness"),
            }
        )

    if not candidates:
        raise ValueError(f"No candidate rows found in {path}")
    return candidates


def build_items(candidates: Iterable[dict]) -> list[dict]:
    items: list[dict] = []
    for index, candidate in enumerate(candidates, start=1):
        model_answer = candidate["model_answer"]
        items.append(
            {
                "custom_id": safe_custom_id(
                    index, candidate["id"], candidate["model_id"]
                ),
                "record_id": candidate["id"],
                "model_id": candidate["model_id"],
                "system": JUDGE_SYSTEM_PROMPT,
                "user": JUDGE_USER_NO.format(model_answer=model_answer),
                "source_answerability_label": candidate.get(
                    "answerability_label"
                ),
                "source_completeness": candidate.get("completeness"),
                "model_answer": model_answer,
            }
        )
    return items


def default_raw_output_path(output_path: Path, judge_model: str) -> Path:
    safe_model = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in judge_model
    )
    return output_path.with_name(
        f"{output_path.stem}_{safe_model}_raw.jsonl"
    )


def write_jsonl(
    path: Path, rows: Iterable[dict], *, append: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_result(
    item: dict,
    raw_result: dict,
    *,
    backend: str,
    judge_model: str,
) -> dict:
    response_text = str(raw_result.get("response_text", "") or "")
    api_error = raw_result.get("error")
    projected_record = {
        "id": item["record_id"],
        "answerability_label": "NO",
    }
    score: RecordScore = score_record(
        projected_record, item["model_id"], response_text
    )
    parse_ok = score.parse_ok and not api_error
    behavior = score.behavior if parse_ok else None

    output = {
        "id": item["record_id"],
        "model_id": item["model_id"],
        "answerability_label": item.get("source_answerability_label"),
        "completeness": item.get("source_completeness"),
        "model_answer": item["model_answer"],
        "judge_prompt": "JUDGE_USER_NO",
        "judge_label": "NO",
        "judge_model": judge_model,
        "backend": backend,
        "behavior": behavior,
        "abstained": behavior == "Abstained" if parse_ok else None,
        "parse_ok": parse_ok,
        "error": api_error or score.error,
    }
    if not parse_ok:
        output["raw"] = response_text
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Judge every zero-completeness model answer with JUDGE_USER_NO "
            "and emit abstention labels."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=None,
        help=(
            "Raw request/response JSONL. Defaults to "
            "<out_stem>_<judge_model>_raw.jsonl."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=["openrouter", "openai"],
        required=True,
    )
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--judge-base-url", default=None)
    parser.add_argument("--judge-max-tokens", type=int, default=512)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip (id, model_id) pairs already present in --out.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count requests without calling the judge.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    candidates = load_candidates(args.input)

    done: set[str] = set()
    if args.resume and args.out.exists():
        for row in load_jsonl(args.out):
            done.add(pair_key(str(row["id"]), str(row["model_id"])))

    items = [
        item
        for item in build_items(candidates)
        if pair_key(item["record_id"], item["model_id"]) not in done
    ]
    print(
        f"[info] candidates={len(candidates)} already_done={len(done)} "
        f"judge_calls={len(items)}",
        file=sys.stderr,
    )

    if args.dry_run:
        print("[done] dry run; no API calls were made", file=sys.stderr)
        return
    if not items:
        print("[done] no remaining judge calls", file=sys.stderr)
        return

    if args.backend == "openrouter":
        from judge_clients import OpenRouterJudge

        judge = OpenRouterJudge(
            model=args.judge_model,
            base_url=args.judge_base_url,
            max_tokens=args.judge_max_tokens,
        )
    else:
        from judge_clients import OpenAICompatJudge

        judge = OpenAICompatJudge(
            model=args.judge_model,
            base_url=args.judge_base_url,
            max_tokens=args.judge_max_tokens,
        )

    raw_by_custom_id = judge.judge_many_raw(
        items, max_workers=args.max_workers
    )
    raw_output_path = args.raw_out or default_raw_output_path(
        args.out, args.judge_model
    )
    raw_rows: list[dict] = []
    output_rows: list[dict] = []
    n_ok = 0

    for item in items:
        raw_result = raw_by_custom_id.get(
            item["custom_id"],
            {
                "request": None,
                "response": None,
                "response_text": "",
                "error": "missing judge result",
            },
        )
        raw_rows.append(
            {
                "custom_id": item["custom_id"],
                "record_id": item["record_id"],
                "model_id": item["model_id"],
                "source_answerability_label": item.get(
                    "source_answerability_label"
                ),
                "judge_prompt": "JUDGE_USER_NO",
                "judge_model": judge.model,
                "backend": args.backend,
                "request": raw_result.get("request"),
                "response": raw_result.get("response"),
                "response_text": raw_result.get("response_text", ""),
                "error": raw_result.get("error"),
            }
        )
        output_row = parse_result(
            item,
            raw_result,
            backend=args.backend,
            judge_model=judge.model,
        )
        output_rows.append(output_row)
        n_ok += bool(output_row["parse_ok"])

    append = args.resume and args.out.exists()
    write_jsonl(raw_output_path, raw_rows, append=append)
    write_jsonl(args.out, output_rows, append=append)
    n_error = len(output_rows) - n_ok
    print(
        f"[done] scored={n_ok} errors={n_error} -> {args.out}",
        file=sys.stderr,
    )
    print(f"[info] raw log -> {raw_output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
