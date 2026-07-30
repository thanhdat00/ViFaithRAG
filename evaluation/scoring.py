"""
Parse raw judge JSON into validated verdicts and derive per-record scores.

Per-record outputs:
  YES / PARTIAL:
    - faithfulness   = supported_claims / total_claims        (None if 0 claims)
    - completeness   = covered_key_points / total_key_points  (None if 0 points)
    - scope_violation (PARTIAL only): bool
  NO:
    - behavior in {Abstained, Fabricated, PartialSmuggle}
    - abstained = behavior == "Abstained"
  AMBIGUOUS:
    - behavior in {Clarified, Committed}
    - clarified = behavior == "Clarified"
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


class JudgeParseError(Exception):
    pass


def _extract_json(raw: str) -> dict:
    """Extract the first JSON object from a judge response, tolerating stray text/fences."""
    if raw is None:
        raise JudgeParseError("empty judge response")
    s = raw.strip()
    # strip markdown fences if present
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    # fast path
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # fallback: first balanced {...}
    start = s.find("{")
    if start == -1:
        raise JudgeParseError(f"no JSON object found in: {raw[:200]!r}")
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except json.JSONDecodeError as e:
                    raise JudgeParseError(f"malformed JSON: {e}") from e
    recovered = _recover_truncated_json(s)
    if recovered is not None:
        return recovered
    raise JudgeParseError(f"unbalanced JSON in: {raw[:200]!r}")


def _array_start(text: str, field_name: str) -> int:
    match = re.search(rf'"{re.escape(field_name)}"\s*:\s*\[', text)
    if not match:
        return -1
    return match.end()


def _extract_complete_objects_from_array(text: str, field_name: str) -> list[dict]:
    start = _array_start(text, field_name)
    if start < 0:
        return []

    decoder = json.JSONDecoder()
    objects: list[dict] = []
    index = start
    while index < len(text):
        while index < len(text) and text[index] in " \r\n\t,":
            index += 1
        if index >= len(text) or text[index] == "]":
            break
        if text[index] != "{":
            break
        try:
            item, next_index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            objects.append(item)
        index = next_index
    return objects


def _recover_truncated_json(text: str) -> dict | None:
    """Recover complete leading arrays from a response truncated before the final JSON brace."""
    claims = _extract_complete_objects_from_array(text, "claims")
    key_points = _extract_complete_objects_from_array(text, "gt_key_points")
    if not claims and not key_points:
        return None

    recovered: dict = {
        "claims": claims,
        "gt_key_points": key_points,
    }

    scope_match = re.search(r'"scope_violation"\s*:\s*(true|false)', text)
    if scope_match:
        recovered["scope_violation"] = scope_match.group(1) == "true"

    return recovered


@dataclass
class RecordScore:
    id: str
    model_id: str
    label: str
    # YES/PARTIAL
    faithfulness: Optional[float] = None
    completeness: Optional[float] = None
    n_claims: Optional[int] = None
    n_supported: Optional[int] = None
    n_key_points: Optional[int] = None
    n_covered: Optional[int] = None
    scope_violation: Optional[bool] = None
    # Behavioral judgments
    behavior: Optional[str] = None
    abstention_behavior: Optional[str] = None
    abstained: Optional[bool] = None
    # bookkeeping
    parse_ok: bool = True
    error: Optional[str] = None
    raw: Optional[str] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return asdict(self)


_VALID_NO = {"Abstained", "Fabricated", "PartialSmuggle"}
_VALID_AMB = {"Clarified", "Committed"}


def score_record(record: dict, model_id: str, judge_raw: str) -> RecordScore:
    """Turn one raw judge response into a RecordScore. Never raises; captures errors inline."""
    rid = record["id"]
    label = record["answerability_label"]
    rs = RecordScore(id=rid, model_id=model_id, label=label, raw=judge_raw)

    try:
        data = _extract_json(judge_raw)
    except JudgeParseError as e:
        rs.parse_ok = False
        rs.error = str(e)
        return rs

    try:
        if label in ("YES", "PARTIAL"):
            claims = data.get("claims", [])
            if not isinstance(claims, list):
                raise JudgeParseError("`claims` not a list")
            n = len(claims)
            supported = sum(
                1
                for c in claims
                if isinstance(c, dict) and c.get("verdict") == "Supported"
            )
            rs.n_claims = n
            rs.n_supported = supported
            rs.faithfulness = (supported / n) if n > 0 else None

            kps = data.get("gt_key_points", [])
            if not isinstance(kps, list):
                raise JudgeParseError("`gt_key_points` not a list")
            k = len(kps)
            covered = sum(
                1
                for p in kps
                if isinstance(p, dict) and p.get("covered") is True
            )
            rs.n_key_points = k
            rs.n_covered = covered
            rs.completeness = (covered / k) if k > 0 else None

            if label == "PARTIAL":
                sv = data.get("scope_violation")
                if not isinstance(sv, bool):
                    raise JudgeParseError("`scope_violation` missing/not bool")
                rs.scope_violation = sv

        elif label == "NO":
            beh = data.get("behavior")
            if beh not in _VALID_NO:
                raise JudgeParseError(f"invalid NO behavior: {beh!r}")
            rs.behavior = beh
            rs.abstention_behavior = beh
            rs.abstained = beh == "Abstained"

        elif label == "AMBIGUOUS":
            beh = data.get("behavior")
            if beh not in _VALID_AMB:
                raise JudgeParseError(f"invalid AMBIGUOUS behavior: {beh!r}")
            rs.behavior = beh

        else:
            raise JudgeParseError(f"unknown label {label!r}")

    except JudgeParseError as e:
        rs.parse_ok = False
        rs.error = str(e)

    return rs


def merge_abstention_judgments(
    scores: list[dict], judgments: list[dict]
) -> list[dict]:
    """Attach explicit response-level abstention labels to YES/NO scores."""
    judgment_by_pair: dict[tuple[str, str], dict] = {}
    for row in judgments:
        key = (str(row.get("id", "")), str(row.get("model_id", "")))
        if not all(key):
            raise ValueError(f"Invalid abstention judgment key: {key}")
        if key in judgment_by_pair:
            raise ValueError(f"Duplicate abstention judgment: {key}")
        if row.get("parse_ok") is not True:
            raise ValueError(f"Unparsed abstention judgment: {key}")
        behavior = row.get("behavior")
        abstained = row.get("abstained")
        if behavior not in _VALID_NO:
            raise ValueError(
                f"Invalid abstention behavior for {key}: {behavior!r}"
            )
        if not isinstance(abstained, bool):
            raise ValueError(f"Missing boolean abstained value for {key}")
        if abstained != (behavior == "Abstained"):
            raise ValueError(
                f"Inconsistent behavior/abstained values for {key}"
            )
        judgment_by_pair[key] = row

    merged: list[dict] = []
    score_pairs: set[tuple[str, str]] = set()
    missing_zero_completeness_yes: list[tuple[str, str]] = []
    for original in scores:
        row = dict(original)
        key = (str(row.get("id", "")), str(row.get("model_id", "")))
        if not all(key):
            raise ValueError(f"Invalid score key: {key}")
        if key in score_pairs:
            raise ValueError(f"Duplicate score row: {key}")
        score_pairs.add(key)

        label = row.get("label")
        if label == "NO":
            behavior = row.get("behavior")
            if behavior not in _VALID_NO:
                raise ValueError(
                    f"Invalid NO behavior in score row {key}: {behavior!r}"
                )
            row["abstention_behavior"] = behavior
            row["abstained"] = behavior == "Abstained"
        elif label == "YES":
            judgment = judgment_by_pair.get(key)
            if judgment is not None:
                row["abstention_behavior"] = judgment["behavior"]
                row["abstained"] = judgment["abstained"]
            elif row.get("completeness") in (0, 0.0):
                missing_zero_completeness_yes.append(key)
            elif (
                row.get("completeness") is None
                and (row.get("n_claims") or 0) == 0
            ):
                missing_zero_completeness_yes.append(key)
            else:
                # Positive completeness proves substantive answer content.
                # A claim-bearing completeness=None row is also substantive.
                row["abstention_behavior"] = None
                row["abstained"] = False
        else:
            row.setdefault("abstention_behavior", None)
            row.setdefault("abstained", None)
        merged.append(row)

    extra_judgments = sorted(set(judgment_by_pair) - score_pairs)
    if extra_judgments:
        raise ValueError(
            f"{len(extra_judgments)} abstention judgments have no score row; "
            f"first: {extra_judgments[0]}"
        )
    if missing_zero_completeness_yes:
        raise ValueError(
            f"{len(missing_zero_completeness_yes)} zero-completeness YES "
            "scores lack an abstention judgment; first: "
            f"{missing_zero_completeness_yes[0]}"
        )
    return merged


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    """Atomically replace a JSONL file, including when input and output match."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def merge_abstention_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="scoring.py merge-abstention",
        description=(
            "Merge explicit YES abstention judgments into per-record scores."
        ),
    )
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--judgments", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    scores = load_jsonl(args.scores)
    judgments = load_jsonl(args.judgments)
    merged = merge_abstention_judgments(scores, judgments)
    write_jsonl_atomic(args.out, merged)

    yes_judged = sum(
        row.get("label") == "YES"
        and isinstance(row.get("abstained"), bool)
        for row in merged
    )
    yes_abstained = sum(
        row.get("label") == "YES" and row.get("abstained") is True
        for row in merged
    )
    print(
        f"[done] rows={len(merged)} YES_labeled={yes_judged} "
        f"YES_abstained={yes_abstained} -> {args.out}",
        file=sys.stderr,
    )


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_batch_ids(submission_log_file: Path) -> list[str]:
    rows = load_jsonl(submission_log_file)
    batch_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        batch_id = str(row.get("batch_id", "")).strip()
        if batch_id and batch_id not in seen:
            batch_ids.append(batch_id)
            seen.add(batch_id)
    if not batch_ids:
        raise ValueError(f"No batch_id found in submission log: {submission_log_file}")
    return batch_ids


def load_request_map(batch_request_map: Path, *, batch_ids: set[str] | None = None) -> dict[str, tuple[str, str]]:
    custom_id_to_pair: dict[str, tuple[str, str]] = {}
    for line_number, row in enumerate(load_jsonl(batch_request_map), start=1):
        row_batch_id = str(row.get("batch_id", "")).strip()
        if batch_ids is not None and row_batch_id and row_batch_id not in batch_ids:
            continue
        custom_id = str(row.get("custom_id", "")).strip()
        record_id = str(row.get("record_id", "")).strip()
        model_id = str(row.get("model_id", "")).strip()
        if not custom_id or not record_id or not model_id:
            raise ValueError(f"Invalid request map line {line_number}: {row}")
        custom_id_to_pair[custom_id] = (record_id, model_id)
    if not custom_id_to_pair:
        raise ValueError(f"No request rows found in: {batch_request_map}")
    return custom_id_to_pair


def pull_anthropic_batch_results(*, batch_ids: list[str], model: str) -> dict[str, str]:
    try:
        from judge_clients import AnthropicBatchJudge
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from judge_clients import AnthropicBatchJudge

    judge = AnthropicBatchJudge(model=model)
    raw_by_custom_id: dict[str, str] = {}
    for batch_id in batch_ids:
        batch = judge.client.messages.batches.retrieve(batch_id)
        status = str(getattr(batch, "processing_status", "") or "")
        print(f"[info] batch {batch_id} status={status}", file=sys.stderr)
        if status != "ended":
            raise RuntimeError(f"Batch is not ended yet: {batch_id} status={status}")
        raw_by_custom_id.update(judge.results(batch_id))
    return raw_by_custom_id


def score_batch_results(
    *,
    dataset_path: Path,
    batch_submission_log: Path,
    batch_request_map: Path,
    judge_model: str,
    out_path: Path,
    keep_raw: bool,
) -> tuple[int, int]:
    dataset = {row["id"]: row for row in load_jsonl(dataset_path)}
    batch_ids = load_batch_ids(batch_submission_log)
    custom_id_to_pair = load_request_map(batch_request_map, batch_ids=set(batch_ids))
    raw_by_custom_id = pull_anthropic_batch_results(batch_ids=batch_ids, model=judge_model)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    n_err = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for custom_id, (record_id, model_id) in custom_id_to_pair.items():
            record = dataset.get(record_id)
            if record is None:
                rs = RecordScore(
                    id=record_id,
                    model_id=model_id,
                    label="",
                    parse_ok=False,
                    error="record id not in dataset",
                    raw=None,
                )
            else:
                raw = raw_by_custom_id.get(custom_id, "")
                rs = score_record(record, model_id, raw)
            n_ok += rs.parse_ok
            n_err += not rs.parse_ok
            row = rs.to_dict()
            if not keep_raw and rs.parse_ok:
                row.pop("raw", None)
            if not rs.parse_ok and not row.get("raw"):
                row["raw"] = raw_by_custom_id.get(custom_id, "")
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return n_ok, n_err


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "merge-abstention":
        merge_abstention_main(sys.argv[2:])
        return

    ap = argparse.ArgumentParser(
        description="Pull Anthropic judge batch results and score each submitted model answer."
    )
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--batch-submission-log", required=True, type=Path)
    ap.add_argument("--batch-request-map", required=True, type=Path)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--keep-raw", action="store_true", help="Keep raw judge output for successful parses too.")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Missing API key. Set ANTHROPIC_API_KEY")

    n_ok, n_err = score_batch_results(
        dataset_path=args.dataset,
        batch_submission_log=args.batch_submission_log,
        batch_request_map=args.batch_request_map,
        judge_model=args.judge_model,
        out_path=args.out,
        keep_raw=args.keep_raw,
    )
    print(f"[done] scored={n_ok} parse_errors={n_err} -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
