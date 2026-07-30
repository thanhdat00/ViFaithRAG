# ViFaithRAG final dataset schema

This document describes the schema actually used by `final_dataset.jsonl`.
The current snapshot contains 4,117 UTF-8 JSON Lines records. Each non-empty
line is one complete JSON object; there is no header row.

Every record has the same 22 top-level fields. A field described as nullable is
still present in every record: its JSON value may be `null`.

## Notation

- `enum4` means one of `"YES"`, `"NO"`, `"PARTIAL"`, or `"AMBIGUOUS"`.
- `list<int>` means a JSON array of integers.
- `timestamp` means a string formatted as `YYYY-MM-DD HH:MM:SS`. The dataset
  does not encode a timezone.
- “Required” means the key is present, not that its value is non-null.

## Record schema

### Evaluation payload

| Field | Type | Meaning and constraints |
|---|---|---|
| `id` | string (UUID) | Stable, unique record identifier. All current values are valid UUID strings. |
| `query` | non-empty string | Original user query. Casing, diacritics, and typos are preserved. |
| `domain` | enum: `"legal"` or `"open_domain"` | Query domain. |
| `context` | `list<Document>` | Retrieved context. It has exactly three documents, ordered by `doc_index` as 1, 2, 3. |
| `answerability_label` | `enum4` | Settled final answerability label used for evaluation. |
| `ground_truth_answer` | non-empty string | Primary reference behavior used for evaluation. For `YES`/`PARTIAL`, this is normally the citation-stripped reference answer; for `NO`/`AMBIGUOUS`, it is the canonical response described below. See the snapshot caveats before assuming that every citation marker was removed. |
| `supporting_doc_indices` | `list<int>` | Sorted, duplicate-free subset of `[1, 2, 3]` containing documents judged to provide direct support. Label-dependent constraints are below. |

### Document schema

Each object in `context` has exactly these six fields:

| Field | Type | Meaning and constraints |
|---|---|---|
| `id` | non-empty string | Document identifier. It is unique within a record, but the same document ID may occur in different records. No particular string pattern should be assumed. |
| `doc_index` | integer: `1`, `2`, or `3` | Stable retrieval position and citation target. Documents are stored in ascending index order and must not be renumbered. |
| `url` | non-empty string | Source HTTP(S) URL. |
| `title` | non-empty string | Parsed page title. |
| `content` | string | Parsed page text. It may be empty when retrieval produced no body text. |
| `crawl_date` | `timestamp` | Retrieval timestamp. It includes seconds but no timezone. |

### Reference grounding and answer provenance

| Field | Type | Meaning and constraints |
|---|---|---|
| `answer_with_citations` | string or `null` | Citation-oriented version of the reference answer for `YES`/`PARTIAL`; `null` for `NO`/`AMBIGUOUS`. Citations generally use `[Doc N]`, where `N` resolves to `doc_index`. See the snapshot caveats below before parsing this field automatically. |
| `answer_provenance` | enum or `null` | For `YES`/`PARTIAL`, one of `"model_accepted"`, `"model_minor_edited"`, or `"model_major_edited"`; `null` for `NO`/`AMBIGUOUS`. |

The provenance values mean:

- `model_accepted`: the model draft was accepted as the answer.
- `model_minor_edited`: wording, terminology, spelling, or formatting was
  changed without a substantive change to the answer.
- `model_major_edited`: substantive corrections were made, such as changing
  scope, removing unsupported claims, or adding missing supported content.

### Annotation provenance

| Field | Type | Meaning and constraints |
|---|---|---|
| `annotator_1_label` | `enum4` | First annotator's raw Phase-1 label. |
| `annotator_1_supporting_doc_indices` | `list<int>` | First annotator's raw supporting-document selection; a duplicate-free subset of `[1, 2, 3]`. Preserve it as provenance rather than applying final-label validation rules to it. Its order is not guaranteed to be sorted. |
| `annotator_2_label` | `enum4` | Second annotator's raw Phase-1 label. |
| `annotator_2_supporting_doc_indices` | `list<int>` | Second annotator's raw supporting-document selection, with the same semantics as annotator 1's field. |
| `phase1_final_label` | `enum4` | Label at the end of Phase 1, before answer-review corrections. |
| `final_label_source` | enum: `"raw_agreement"`, `"adjudication"`, or `"answer_review"` | Pipeline stage recorded as the source of the final label. Definitions are below. |
| `label_changed_in_review` | boolean | Whether answer review changed `phase1_final_label`. In this snapshot it is exactly equivalent to `phase1_final_label != answerability_label`. |

`final_label_source` has these intended meanings:

- `raw_agreement`: the Phase-1 annotators agreed and no later label change was
  recorded.
- `adjudication`: Phase-1 adjudication produced or confirmed the final label.
- `answer_review`: answer review changed the Phase-1 label. In the current
  snapshot, all and only these records have `label_changed_in_review = true`.

The two annotator supporting-index fields are raw provenance. They can be empty
for raw `YES`/`PARTIAL` labels or non-empty for raw `NO`/`AMBIGUOUS` labels, so
consumers must not validate them using the final-label rules below. For all
records tagged `raw_agreement`, both raw supporting-index arrays equal the final
`supporting_doc_indices`.

### Reference-model metadata and record timestamp

| Field | Type | Meaning and constraints |
|---|---|---|
| `gpt_label` | `enum4` | GPT pre-label used for analysis only. |
| `gpt_reason` | string | GPT pre-label rationale. An empty string means no rationale was stored. |
| `gemini_label` | `enum4` or `null` | Gemini pre-label used for analysis only. `null` means the pre-label is unavailable. |
| `gemini_reason` | string | Gemini pre-label rationale. An empty string means no rationale was stored. |
| `is_hard` | boolean | Equivalent in this snapshot to `gpt_label != answerability_label AND gemini_label IS NOT NULL AND gemini_label != answerability_label`. |
| `created` | `timestamp` | Record timestamp as stored in the released data. In this snapshot it equals all three documents' `crawl_date` values for the same record. |

The `gpt_*` and `gemini_*` fields are analysis metadata, not model inputs.
Evaluation involving those model families should disclose the possible
circularity.

## Label-dependent invariants

These constraints hold for every record in the current file:

| Final label | `supporting_doc_indices` | `answer_with_citations` | `answer_provenance` | `ground_truth_answer` |
|---|---|---|---|---|
| `YES` | Non-empty subset of `[1, 2, 3]` | Non-empty string | Non-null provenance enum | Reference answer |
| `PARTIAL` | Non-empty subset of `[1, 2, 3]` | Non-empty string | Non-null provenance enum | Answer to the supported portion, normally also identifying what is missing |
| `NO` | `[]` | `null` | `null` | `"Ngữ cảnh được cung cấp không chứa đủ thông tin để trả lời câu hỏi này."` |
| `AMBIGUOUS` | `[]` | `null` | `null` | `"Câu hỏi có thể được hiểu theo nhiều cách khác nhau. Vui lòng làm rõ ý định của câu hỏi để có thể trả lời chính xác."` |

`supporting_doc_indices` identifies all documents judged to contain direct
support. It is not guaranteed to equal the set of citation tokens appearing in
`answer_with_citations`; do not derive one field from the other.

## Citation and index rules

`doc_index` is the stable join key among:

- an element of `context`;
- an integer in `supporting_doc_indices`; and
- a citation such as `[Doc 2]` in `answer_with_citations`.

Filtering or reordering context must not change `doc_index`. If a consumer
selects only some documents, it must retain their original indices.

The intended citation spelling is `[Doc N]`. The current snapshot is not strict
enough for a parser to require that form in every answer:

- 53 `YES`/`PARTIAL` records have no exact `[Doc N]` token in
  `answer_with_citations`; some use variants such as `[Doc1]` or
  `[Doc 1, Doc 2]`, while others contain no citation token.
- In 538 records, the set of exact `[Doc N]` tokens is not identical to
  `supporting_doc_indices`. This can occur because the support field records all
  supporting documents while the answer cites only those used in a particular
  sentence, as well as because of formatting inconsistencies.
- Although `ground_truth_answer` is intended to be citation-stripped, 11
  records still contain one or more bracketed `Doc`-like markers such as
  `[Doc1]` or `[Doc 1, Doc 2]`.

Treat `supporting_doc_indices` as the authoritative structured grounding field.
Treat `answer_with_citations` as human-readable attribution unless citation
syntax is normalized in a future release.

## Current snapshot audit

This table documents the file that was checked against this schema. Counts are
descriptive, not permanent schema constraints.

| Property | Count |
|---|---:|
| Records | 4,117 |
| `YES` | 2,663 |
| `PARTIAL` | 335 |
| `NO` | 1,071 |
| `AMBIGUOUS` | 48 |
| `open_domain` | 2,946 |
| `legal` | 1,171 |
| `label_changed_in_review = true` | 54 |
| `final_label_source = "raw_agreement"` | 2,930 |
| `final_label_source = "adjudication"` | 1,133 |
| `final_label_source = "answer_review"` | 54 |
| `is_hard = true` | 431 |
| Documents with empty `content` | 122 documents in 99 records |
| Records with `gemini_label = null` | 4 |

## Complete illustrative record

The following is a compact structural example. Its text values are illustrative;
real records contain full document text.

```json
{
  "id": "080392b5-41da-58c7-b5ef-9ee3a5f0bb87",
  "query": "Câu hỏi của người dùng",
  "domain": "open_domain",
  "context": [
    {
      "id": "doc_example_1",
      "doc_index": 1,
      "url": "https://example.org/1",
      "title": "Tài liệu 1",
      "content": "Nội dung tài liệu 1",
      "crawl_date": "2025-11-14 10:30:00"
    },
    {
      "id": "doc_example_2",
      "doc_index": 2,
      "url": "https://example.org/2",
      "title": "Tài liệu 2",
      "content": "Nội dung tài liệu 2",
      "crawl_date": "2025-11-14 10:30:00"
    },
    {
      "id": "doc_example_3",
      "doc_index": 3,
      "url": "https://example.org/3",
      "title": "Tài liệu 3",
      "content": "Nội dung tài liệu 3",
      "crawl_date": "2025-11-14 10:30:00"
    }
  ],
  "answerability_label": "YES",
  "ground_truth_answer": "Câu trả lời tham chiếu.",
  "supporting_doc_indices": [1],
  "answer_with_citations": "Câu trả lời tham chiếu [Doc 1].",
  "answer_provenance": "model_minor_edited",
  "annotator_1_label": "YES",
  "annotator_1_supporting_doc_indices": [1],
  "annotator_2_label": "YES",
  "annotator_2_supporting_doc_indices": [1],
  "phase1_final_label": "YES",
  "final_label_source": "raw_agreement",
  "label_changed_in_review": false,
  "gpt_label": "YES",
  "gpt_reason": "",
  "gemini_label": "YES",
  "gemini_reason": "",
  "is_hard": false,
  "created": "2025-11-14 10:30:00"
}
```

## Dataset-level metadata

The following belongs in a dataset card or release manifest, not in each JSONL
record:

- dataset version;
- license and takedown policy for crawled content;
- intended use and model-family circularity caveat;
- full four-label annotation guidelines;
- version-pinned label/domain counts;
- contamination-detection canary, if the release uses one.
