# ViFaithRAG

**A Vietnamese RAG benchmark for faithfulness on real-world queries**

ViFaithRAG evaluates whether retrieval-augmented generation (RAG) systems both
produce claims supported by retrieved evidence and recognize when that evidence
is incomplete, irrelevant, or ambiguous. The benchmark contains **4,117 real
Vietnamese queries**, each paired with the full text of its top three Google
Search results, a human-verified answerability label, supporting-document
annotations, and a reviewed reference response.

Unlike datasets whose questions are answerable by construction, ViFaithRAG
retains realistic retrieval failures and distractors. As a result, it supports
evaluation of both grounded answer quality and the decision to answer, qualify,
clarify, or abstain.

## Dataset overview

| Property | Value |
|---|---:|
| Records | 4,117 |
| Legal queries | 1,171 |
| Open-domain queries | 2,946 |
| Retrieved documents | 12,351 (3 per query) |
| YES/PARTIAL records | 2,998 |
| Not fully answerable records | 1,454 (35.3%) |
| Hard-subset records | 431 |
| Median query length | 10 words |
| Median three-document context length | 4,378 tokens |
| Unique source domains | 2,884 |

### Answerability distribution

| Domain | Records | YES | PARTIAL | NO | AMBIGUOUS | Not fully answerable |
|---|---:|---:|---:|---:|---:|---:|
| Legal | 1,171 | 779 (66.5%) | 80 (6.8%) | 302 (25.8%) | 10 (0.9%) | 392 (33.5%) |
| Open domain | 2,946 | 1,884 (64.0%) | 255 (8.7%) | 769 (26.1%) | 38 (1.3%) | 1,062 (36.1%) |
| **All** | **4,117** | **2,663 (64.7%)** | **335 (8.1%)** | **1,071 (26.0%)** | **48 (1.2%)** | **1,454 (35.3%)** |

The four mutually exclusive labels are:

- **YES** — the retrieved documents support every substantive part of the
  query.
- **PARTIAL** — the documents support at least one part of the query but leave
  another part unsupported.
- **NO** — the documents support no substantive answer.
- **AMBIGUOUS** — a missing referent or materially different interpretations
  prevent a determinate answer.

For time-sensitive claims, evidence is considered sufficient only when it
provides a relevant date or effective period.

### Construction and annotation

Approximately 30,000 naturally occurring Vietnamese queries were collected
from public Q&A pages, forums, and question portals. Rule-based and semantic
deduplication removed non-Vietnamese, personally identifiable, unusually short
or long, and near-duplicate queries. The remaining 4,117 queries comprise 1,171
legal and 2,946 open-domain examples.

For each query, the top three Google Search results were retrieved through the
Serper API. Page body text, headings, and tables were preserved without
relevance filtering, passage selection, or manual page cleaning. The contexts
therefore retain off-topic pages, incomplete evidence, conflicting sources, and
residual boilerplate.

GPT-5.5 and Gemini 3.1 Pro supplied candidate labels, rationales, and
supporting-document sets. Two annotators then independently labeled every
record, and disagreements were adjudicated. Before adjudication, four-way human
agreement was **87.35%** with Cohen's $\kappa=0.744$. For YES and PARTIAL
records, a model-drafted cited response was checked by a human reviewer for
support, coverage, scope, consistency, and language. NO and AMBIGUOUS records
received reviewed abstention or clarification responses.

The **hard subset** contains the 431 records for which the final human label
differs from both model pre-labels.

## Dataset schema

The dataset is released as JSON Lines: one JSON object per line in
`ViFaithRAG/final_dataset.jsonl`.

### Core evaluation fields

| Field | Type | Description |
|---|---|---|
| `id` | string (UUID) | Stable record identifier. |
| `query` | string | Original Vietnamese query; casing, diacritics, and typos are preserved. |
| `domain` | `legal` \| `open_domain` | Query domain. |
| `context` | `list<Document>` | Three retrieved documents in original rank order. |
| `answerability_label` | `YES` \| `PARTIAL` \| `NO` \| `AMBIGUOUS` | Final human-verified label. |
| `ground_truth_answer` | string | Reviewed, citation-free reference response that defines the supported answer scope. |
| `supporting_doc_indices` | `list<int>` | Directly supporting document ranks, drawn from `{1, 2, 3}`; empty for NO and AMBIGUOUS. |

Each object in `context` has the following structure:

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable document identifier. |
| `doc_index` | integer | Original Google rank: 1, 2, or 3. |
| `url` | string | Source page URL. |
| `title` | string | Parsed page title. |
| `content` | string | Full parsed page text with markup and scripts removed. |
| `crawl_date` | ISO 8601 string | Retrieval date used to anchor time-sensitive judgments. |

`doc_index` is stable and must not be renumbered: values in
`supporting_doc_indices` and inline `[Doc N]` citations refer to this index.

### Answer and annotation provenance

| Field | Type | Description |
|---|---|---|
| `answer_with_citations` | string \| null | Reviewed YES/PARTIAL response with `[Doc N]` citations; null for NO/AMBIGUOUS. |
| `answer_provenance` | enum \| null | `model_accepted`, `model_minor_edited`, or `model_major_edited`; null for NO/AMBIGUOUS. |
| `annotator_1_label` | answerability label | First raw human label. |
| `annotator_1_supporting_doc_indices` | `list<int>` | First annotator's supporting-document selection. |
| `annotator_2_label` | answerability label | Second raw human label. |
| `annotator_2_supporting_doc_indices` | `list<int>` | Second annotator's supporting-document selection. |
| `phase1_final_label` | answerability label | Label after first-phase agreement or adjudication. |
| `final_label_source` | enum | `raw_agreement`, `adjudication`, or `answer_review`. |
| `label_changed_in_review` | boolean | Whether answer review changed the Phase-1 label. |
| `gpt_label`, `gemini_label` | answerability label | Model pre-labels retained for analysis only. |
| `gpt_reason`, `gemini_reason` | string | Rationales accompanying the model pre-labels. |
| `is_hard` | boolean | Whether the final label differs from both model pre-labels. |

The pre-label and provenance fields are analysis metadata. They must not be
provided to a model under standard benchmark evaluation.

### Abbreviated example

```json
{
  "id": "003d62a7-d611-596f-90ea-b3be4bfc4216",
  "query": "công ty cổ phần thực phẩm kết tình bán những gì ?",
  "domain": "open_domain",
  "context": [
    {
      "id": "doc_...",
      "doc_index": 1,
      "url": "https://example.vn/...",
      "title": "...",
      "content": "...",
      "crawl_date": "2025-11-14"
    }
  ],
  "answerability_label": "NO",
  "supporting_doc_indices": [],
  "ground_truth_answer": "Ngữ cảnh không có thông tin để trả lời câu hỏi.",
  "answer_with_citations": null,
  "is_hard": false
}
```

The example abbreviates `context` to one document and omits provenance fields;
released records contain all three documents.

## Evaluation protocol

A contestant model receives only the original query and the untruncated full
text of the three retrieved pages. It does **not** receive the answerability
label, supporting-document annotations, reference response, or annotation
provenance. The paper's baseline setup uses temperature 0, disables reasoning
modes, and allows at most 2,048 output tokens.

Evaluation is label-conditioned:

| Label | Judge inputs | Outputs |
|---|---|---|
| YES | Query, model response, reference response | Atomic-claim support, key-point coverage, over-abstention |
| PARTIAL | Query, model response, reference response | Atomic-claim support, key-point coverage, scope violation |
| NO | Model response only | `Abstained`, `Fabricated`, or `PartialSmuggle` |
| AMBIGUOUS | Query and model response | `Clarified` or `Committed` |

The judge uses only these supplied inputs and does not replace the
human-verified evidence boundary with external knowledge. The paper evaluates
with Claude Sonnet 4.6 at temperature 0 and reports **94.5% agreement** with a
blinded human reviewer on 200 stratified record-response pairs.

## Evaluation metrics

### Faithfulness and completeness

For answerable record $i$, let $\mathcal{M}_i$ be the atomic claims in the
model response and $\mathcal{G}_i$ the key points in the reviewed reference.
Let $s(m)=1$ if claim $m$ is supported and $c(g)=1$ if key point $g$ is
covered:

$$
F_i=\frac{\sum_{m\in\mathcal{M}_i}s(m)}{|\mathcal{M}_i|},
\qquad
C_i=\frac{\sum_{g\in\mathcal{G}_i}c(g)}{|\mathcal{G}_i|}.
$$

- **Faithfulness ($F$)** is the macro-average of $F_i$ over valid
  claim-bearing YES/PARTIAL responses.
- **Completeness ($C$)** is the macro-average of $C_i$ over all valid
  YES/PARTIAL evaluations.
- **F–C F1** is the harmonic mean:
  $\mathrm{F\text{-}C\ F1}=2FC/(F+C)$.
- **Claims** is the mean number of extracted atomic claims per response.

If a response contains no atomic claims, its faithfulness is undefined and it
is excluded from $F$, while its completeness remains 0. This prevents
abstaining on an answerable record from inflating F–C F1.

### Evidence-boundary behavior

**Scope-violation rate (SVR, lower is better).** The fraction of PARTIAL
records on which a model substantively answers an unsupported part instead of
omitting it or acknowledging the gap:

$$
\mathrm{SVR}=
\frac{N_{\mathrm{PARTIAL}}^{\mathrm{scope\ violation}}}
{N_{\mathrm{PARTIAL}}}
$$

**Over-abstention rate (OAR, lower is better).** The fraction of YES records
on which a model incorrectly abstains:

$$
\mathrm{OAR}=
\frac{N_{\mathrm{YES}}^{\mathrm{abstained}}}
{N_{\mathrm{YES}}}
$$

**Clarification rate (CR, higher is better).** The fraction of AMBIGUOUS
records for which the response asks for missing information, preserves
multiple interpretations, or explicitly identifies the ambiguity:

$$
\mathrm{CR}=
\frac{N_{\mathrm{AMBIGUOUS}}^{\mathrm{clarified}}}
{N_{\mathrm{AMBIGUOUS}}}
$$

### Abstention on the clean YES/NO subset

Treating abstention as the positive prediction and NO as the positive class:

$$
P_{\mathrm{abs}}=
\frac{N_{\mathrm{NO}}^{\mathrm{abstained}}}
{N_{\mathrm{NO}}^{\mathrm{abstained}}+N_{\mathrm{YES}}^{\mathrm{abstained}}},
\qquad
R_{\mathrm{abs}}=
\frac{N_{\mathrm{NO}}^{\mathrm{abstained}}}{N_{\mathrm{NO}}},
$$

$$
\mathrm{F1}_{\mathrm{abs}}=
\frac{2P_{\mathrm{abs}}R_{\mathrm{abs}}}
{P_{\mathrm{abs}}+R_{\mathrm{abs}}}.
$$

PARTIAL and AMBIGUOUS records are evaluated separately because they require
qualification and clarification rather than a binary answer-or-abstain
decision. Behavior rates are reported with Wilson 95% confidence intervals;
AMBIGUOUS results are descriptive because the class contains only 48 records.

## Baseline results

Four instruction-tuned models were evaluated under the same protocol:
DeepSeek-V4-Flash, Qwen3.5-397B-A17B, Gemma-4-31B-IT, and Qwen3-8B.

### Grounded answer quality on YES/PARTIAL

| Model | Faithfulness ↑ | Completeness ↑ | F–C F1 ↑ |
|---|---:|---:|---:|
| DeepSeek-V4-Flash | **78.54** | 63.79 | 70.40 |
| Qwen3.5-397B-A17B | 67.37 | 77.74 | 72.18 |
| Gemma-4-31B-IT | 69.89 | **84.97** | **76.70** |
| Qwen3-8B | 64.92 | 60.03 | 62.38 |

### Evidence-boundary behavior

| Model | SVR ↓ | OAR ↓ | Abstention precision ↑ | Abstention recall ↑ | Abstention F1 ↑ | Clarification ↑ |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek-V4-Flash | **22.39** | 4.39 | 86.76 | **71.62** | 78.47 | 47.92 |
| Qwen3.5-397B-A17B | 35.52 | 1.58 | 94.59 | 68.63 | **79.55** | **52.08** |
| Gemma-4-31B-IT | 32.54 | **0.86** | **96.50** | 59.20 | 73.38 | 41.67 |
| Qwen3-8B | 59.40 | 0.90 | 90.08 | 20.35 | 33.21 | 18.75 |

All values are percentages. Different models lead faithfulness, completeness,
and abstention F1, illustrating why a single correctness score does not capture
faithful RAG behavior.
