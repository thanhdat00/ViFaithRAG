"""
Aggregate per-record judge scores (scores.jsonl) into the ViFaithRAG Task-2 metric suite,
per contestant model, with per-domain breakdown, support counts, and Wilson 95% CIs.

Metric suite (macro-averaged where an aggregate is reported):
  YES, PARTIAL : faithfulness rate, completeness rate, F-C F1, mean claims
  PARTIAL      : scope-violation rate
  NO           : abstention rate; over-answering rate (= 1 - abstention)
  AMBIGUOUS    : clarification rate; over-answering rate (= 1 - clarification)
  YES          : over-abstention rate (model refused an answerable query)
  Clean YES/NO : abstention precision, recall, and F1 (NO is the positive class)
  Calibration  : over-answering (NO+AMB) vs over-abstention (YES) side by side

USAGE
  python aggregate.py --scores scores.jsonl --dataset ViFaithRAG.jsonl --out metrics.json
  # optional: --by-domain to also emit legal/open splits

Requires the dataset only for the `domain` field per id (scores.jsonl carries label already).
"""

from __future__ import annotations
import argparse
import json
import math
from collections import defaultdict


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_abstention_audit(path):
    if not path:
        return {}
    audit = {}
    for row in load_jsonl(path):
        key = (row["id"], row["model_id"])
        if key in audit:
            raise ValueError(f"Duplicate abstention audit row: {key}")
        if not isinstance(row.get("abstained"), bool):
            raise ValueError(f"`abstained` must be boolean for: {key}")
        audit[key] = row["abstained"]
    return audit


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (None, None, None)
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(p, 4), round(center - half, 4), round(center + half, 4))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _safe_ratio(numerator: int, denominator: int):
    return round(numerator / denominator, 4) if denominator > 0 else None


def _abstains(row, abstention_audit):
    """Apply the paper's response-level a(r) rule to a YES or NO score row."""
    key = (row["id"], row["model_id"])
    explicit = row.get("abstained")
    if isinstance(explicit, bool):
        return explicit
    if key in abstention_audit:
        return abstention_audit[key]
    if row["label"] == "NO":
        return row.get("behavior") == "Abstained"
    if row["label"] == "YES":
        if row.get("completeness") not in (0, 0.0, None):
            return False
        if row.get("completeness") is None and (row.get("n_claims") or 0) > 0:
            return False
        raise ValueError(
            "Zero-completeness YES response requires an explicit "
            f"abstention audit label: {key}"
        )
    raise ValueError(f"Abstention is undefined for label {row['label']!r}: {key}")


def aggregate(scores, domain_by_id, abstention_audit=None, domain_filter=None):
    """Return a metrics dict for the subset of scores matching domain_filter (or all)."""
    abstention_audit = abstention_audit or {}
    # group by model
    by_model = defaultdict(list)
    for s in scores:
        if not s.get("parse_ok", True):
            continue
        if domain_filter and domain_by_id.get(s["id"]) != domain_filter:
            continue
        by_model[s["model_id"]].append(s)

    out = {}
    for model_id, rows in sorted(by_model.items()):
        by_label = defaultdict(list)
        for r in rows:
            by_label[r["label"]].append(r)

        yes, partial = by_label["YES"], by_label["PARTIAL"]
        no, amb = by_label["NO"], by_label["AMBIGUOUS"]

        # --- YES/PARTIAL answer quality (record-mean of per-record rates) ---
        # A confirmed full abstention on a YES record is excluded from
        # faithfulness even if the first-pass judge extracted refusal-like
        # statements as claims. Completeness still uses every valid score.
        answer_quality = yes + partial
        faith_rows = [
            r
            for r in answer_quality
            if r.get("faithfulness") is not None
            and not (
                r["label"] == "YES"
                and _abstains(r, abstention_audit)
            )
        ]
        completeness_rows = [
            r for r in answer_quality if r.get("completeness") is not None
        ]
        claim_count_rows = [
            r for r in answer_quality if isinstance(r.get("n_claims"), int)
        ]
        faith_yp = _mean([r["faithfulness"] for r in faith_rows])
        comp_yp = _mean([r["completeness"] for r in completeness_rows])
        mean_claims = _mean([r["n_claims"] for r in claim_count_rows])
        f1 = None
        if (
            faith_yp is not None
            and comp_yp is not None
            and (faith_yp + comp_yp) > 0
        ):
            f1 = round(2 * faith_yp * comp_yp / (faith_yp + comp_yp), 4)

        # --- PARTIAL scope violation ---
        sv_n = sum(1 for r in partial if r.get("scope_violation") is not None)
        sv_k = sum(1 for r in partial if r.get("scope_violation") is True)
        scope_viol = wilson(sv_k, sv_n)

        # --- NO abstention under the shared response-level a(r) rule ---
        no_n = len(no)
        no_abstain = sum(1 for r in no if _abstains(r, abstention_audit))
        abstention = wilson(no_abstain, no_n)
        over_answer_no = wilson(no_n - no_abstain, no_n)

        # --- AMBIGUOUS clarification ---
        amb_n = len(amb)
        amb_clar = sum(1 for r in amb if r["behavior"] == "Clarified")
        clarification = wilson(amb_clar, amb_n)
        over_answer_amb = wilson(amb_n - amb_clar, amb_n)

        # --- YES over-abstention under the same response-level a(r) rule ---
        yes_refused = sum(1 for r in yes if _abstains(r, abstention_audit))
        over_abstain_yes = wilson(yes_refused, len(yes))

        # --- Abstention classification over clean YES/NO only. ---
        # Positive ground truth: NO (the model should abstain).
        # Negative ground truth: YES (the model should answer).
        abstention_tp = no_abstain
        abstention_fn = no_n - no_abstain
        abstention_fp = yes_refused
        abstention_tn = len(yes) - yes_refused
        abstention_precision = _safe_ratio(
            abstention_tp, abstention_tp + abstention_fp
        )
        abstention_recall = _safe_ratio(
            abstention_tp, abstention_tp + abstention_fn
        )
        abstention_f1_denominator = (
            2 * abstention_tp + abstention_fp + abstention_fn
        )
        abstention_f1 = _safe_ratio(
            2 * abstention_tp, abstention_f1_denominator
        )

        # --- combined over-answering across NO+AMBIGUOUS ---
        oa_n = no_n + amb_n
        oa_k = (no_n - no_abstain) + (amb_n - amb_clar)
        over_answer_all = wilson(oa_k, oa_n)

        out[model_id] = {
            "n_records": len(rows),
            "support": {
                "YES": len(yes), "PARTIAL": len(partial),
                "NO": no_n, "AMBIGUOUS": amb_n,
            },
            "faithfulness_yes_partial": faith_yp,
            "completeness_yes_partial": comp_yp,
            "faith_comp_f1": f1,
            "answer_quality": {
                "support": len(answer_quality),
                "n_faithfulness": len(faith_rows),
                "n_completeness": len(completeness_rows),
                "n_claim_count": len(claim_count_rows),
                "mean_claims": mean_claims,
            },
            "partial_scope_violation_rate": _ci_obj(scope_viol),
            "abstention_rate_no": _ci_obj(abstention),
            "over_answer_rate_no": _ci_obj(over_answer_no),
            "clarification_rate_ambiguous": _ci_obj(clarification),
            "over_answer_rate_ambiguous": _ci_obj(over_answer_amb),
            "over_abstention_rate_yes": _ci_obj(over_abstain_yes),
            "abstention_clean_yes_no": {
                "precision": abstention_precision,
                "precision_ci95": _ci_obj(
                    wilson(abstention_tp, abstention_tp + abstention_fp)
                ),
                "recall": abstention_recall,
                "recall_ci95": _ci_obj(
                    wilson(abstention_tp, abstention_tp + abstention_fn)
                ),
                "f1": abstention_f1,
                "support": {
                    "YES": len(yes),
                    "NO": no_n,
                },
                "confusion_matrix": {
                    "tp": abstention_tp,
                    "fp": abstention_fp,
                    "fn": abstention_fn,
                    "tn": abstention_tn,
                },
            },
            "calibration": {
                "over_answering_no_amb": _ci_obj(over_answer_all),
                "over_abstention_yes": _ci_obj(over_abstain_yes),
            },
        }
    return out


def _ci_obj(t):
    p, lo, hi = t
    return {"rate": p, "ci95": [lo, hi]} if p is not None else {"rate": None, "ci95": [None, None]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--abstention-audit",
        help=(
            "Optional fallback JSONL with id, model_id, and boolean abstained "
            "fields. Explicit `abstained` fields in --scores take precedence."
        ),
    )
    ap.add_argument("--by-domain", action="store_true")
    args = ap.parse_args()

    scores = load_jsonl(args.scores)
    domain_by_id = {r["id"]: r.get("domain") for r in load_jsonl(args.dataset)}
    abstention_audit = load_abstention_audit(args.abstention_audit)

    result = {"overall": aggregate(scores, domain_by_id, abstention_audit)}
    if args.by_domain:
        result["legal"] = aggregate(scores, domain_by_id, abstention_audit, "legal")
        result["open_domain"] = aggregate(scores, domain_by_id, abstention_audit, "open_domain")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # console summary
    for model_id, m in result["overall"].items():
        print(f"\n=== {model_id} (n={m['n_records']}, support={m['support']}) ===")
        print(f"  faithfulness (YES/PARTIAL): {m['faithfulness_yes_partial']}")
        print(f"  completeness (YES/PARTIAL): {m['completeness_yes_partial']}")
        print(f"  abstention (NO):            {m['abstention_rate_no']['rate']}")
        print(
            "  abstention P/R/F1 (YES/NO): "
            f"{m['abstention_clean_yes_no']['precision']} / "
            f"{m['abstention_clean_yes_no']['recall']} / "
            f"{m['abstention_clean_yes_no']['f1']}"
        )
        print(f"  clarification (AMBIGUOUS):  {m['clarification_rate_ambiguous']['rate']}")
        print(f"  PARTIAL scope-violation:    {m['partial_scope_violation_rate']['rate']}")
        print(f"  calibration over-answer(NO+AMB)/over-abstain(YES): "
              f"{m['calibration']['over_answering_no_amb']['rate']} / "
              f"{m['calibration']['over_abstention_yes']['rate']}")
    print(f"\n[done] -> {args.out}")


if __name__ == "__main__":
    main()
