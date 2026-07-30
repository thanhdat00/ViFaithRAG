"""
ViFaithRAG Task-2 judge prompts.

Design (locked):
  - GT-only judging: the judge never sees the retrieved context.
  - YES / PARTIAL  -> claim-level BINARY faithfulness (Supported / Unsupported)
                      + completeness + (PARTIAL) scope-violation, judged against
                      the human-verified ground_truth_answer.
  - NO / AMBIGUOUS -> behavioral judging (no reference answer).

All prompts force strict JSON output for deterministic parsing.
The judge must be a model family that did NOT author the GT or pre-label
(e.g., Qwen3.5-397B-A17B-FP8 or Claude Haiku 4.5), and must not grade a
contestant of its own family without a cross-judge check.
"""

# --------------------------------------------------------------------------
# Shared system prompt
# --------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """Bạn là giám khảo đánh giá tính trung thực (faithfulness) của câu trả lời do một mô hình AI sinh ra, trong một benchmark tiếng Việt về hallucination của hệ thống RAG.

NGUYÊN TẮC CỐT LÕI:
1. Bạn đánh giá câu trả lời của mô hình DỰA TRÊN "CÂU TRẢ LỜI THAM CHIẾU" (ground-truth) được cung cấp, KHÔNG dùng kiến thức bên ngoài, KHÔNG tự phán đoán sự thật ngoài đời.
2. Một mệnh đề (claim) là "Supported" nếu nó được câu trả lời tham chiếu khẳng định hoặc suy ra trực tiếp. Là "Unsupported" nếu nó mâu thuẫn với tham chiếu HOẶC cần thông tin nằm ngoài tham chiếu.
3. Suy luận hợp lệ: mệnh đề chỉ diễn đạt lại hoặc là hệ quả logic trực tiếp của tham chiếu -> Supported. Mệnh đề cần thêm bất kỳ thông tin nào không có trong tham chiếu -> Unsupported.
4. KHÔNG thưởng hay phạt theo độ dài. Câu trả lời ngắn mà đúng không bị coi là kém; câu dài không được cộng điểm. Chỉ xét tính grounding và độ bao phủ.
5. Bỏ qua khác biệt về cách diễn đạt, thứ tự, văn phong. Chỉ xét nội dung mệnh đề.
6. Chỉ xuất JSON hợp lệ theo đúng schema được yêu cầu. Không thêm lời dẫn, giải thích ngoài JSON, hay markdown.
"""

# --------------------------------------------------------------------------
# YES / PARTIAL — claim-level binary faithfulness
# --------------------------------------------------------------------------
# {label} in {YES, PARTIAL}; PARTIAL adds the scope-violation check.

JUDGE_USER_YES = """NHÃN: YES (câu hỏi trả lời được đầy đủ từ ngữ cảnh).

YÊU CẦU:
1. Tách câu trả lời của mô hình thành các mệnh đề nguyên tử (atomic claims). Mỗi mệnh đề là một thông tin có thể kiểm chứng độc lập.
2. Với mỗi mệnh đề, gán nhãn "Supported" hoặc "Unsupported" so với câu trả lời tham chiếu (theo nguyên tắc 2-3 ở trên).
3. Xác định các ý chính (key points) trong câu trả lời THAM CHIẾU, và với mỗi ý chính, cho biết câu trả lời của mô hình có bao phủ (covered) hay không.

CHỈ XUẤT JSON theo schema:
{{
  "claims": [
    {{"claim": "<nội dung mệnh đề>", "verdict": "Supported" | "Unsupported"}}
  ],
  "gt_key_points": [
    {{"point": "<ý chính trong tham chiếu>", "covered": true | false}}
  ]
}}

CÂU HỎI:
{query}

CÂU TRẢ LỜI THAM CHIẾU (ground-truth, đã được người kiểm chứng):
{ground_truth_answer}

CÂU TRẢ LỜI CỦA MÔ HÌNH (cần đánh giá):
{model_answer}
"""

JUDGE_USER_PARTIAL = """NHÃN: PARTIAL (ngữ cảnh chỉ trả lời được MỘT PHẦN câu hỏi).

YÊU CẦU:
1. Tách câu trả lời của mô hình thành các mệnh đề nguyên tử. Gán "Supported"/"Unsupported" so với tham chiếu.
2. Xác định các ý chính trong tham chiếu; với mỗi ý, cho biết mô hình có bao phủ hay không.
3. VI PHẠM PHẠM VI (scope_violation): chỉ đúng khi mô hình BỊA RA một đáp án thực chất cho phần câu hỏi mà THAM CHIẾU không trả lời được.
   Nguyên tắc: so sánh phần nào của câu hỏi được THAM CHIẾU trả lời và phần nào không. scope_violation = true KHI VÀ CHỈ KHI mô hình khẳng định một đáp án cho phần mà tham chiếu KHÔNG trả lời, và đáp án đó KHÔNG được tham chiếu hỗ trợ.
   Ngược lại, scope_violation = false — bao gồm mọi trường hợp: mô hình không đụng tới phần đó, mô hình thừa nhận phần đó thiếu thông tin, hoặc tham chiếu vốn không nêu phần nào là thiếu.
   Việc mô hình thừa nhận thiếu thông tin KHÔNG BAO GIỜ là vi phạm.

CHỈ XUẤT JSON theo schema:
{{
  "claims": [
    {{"claim": "<nội dung mệnh đề>", "verdict": "Supported" | "Unsupported"}}
  ],
  "gt_key_points": [
    {{"point": "<ý chính trong tham chiếu>", "covered": true | false}}
  ],
  "scope_violation": true | false
}}

CÂU HỎI:
{query}

CÂU TRẢ LỜI THAM CHIẾU (ground-truth, đã được người kiểm chứng):
{ground_truth_answer}

CÂU TRẢ LỜI CỦA MÔ HÌNH (cần đánh giá):
{model_answer}
"""

# --------------------------------------------------------------------------
# NO — behavioral abstention judging (no reference answer)
# --------------------------------------------------------------------------

JUDGE_USER_NO = """NHÃN: NO (ngữ cảnh KHÔNG đủ thông tin để trả lời câu hỏi).

Hành vi đúng khi ngữ cảnh không đủ thông tin là TỪ CHỐI trả lời (nêu rõ không đủ thông tin), KHÔNG bịa ra đáp án cho câu hỏi.

LƯU Ý QUAN TRỌNG — phân biệt hai loại nội dung thực chất:
- Nội dung GIẢI THÍCH vì sao tài liệu KHÔNG đủ (ví dụ: nêu tài liệu CÓ nói gì, rồi chỉ ra rằng điều đó không trả lời đúng câu hỏi) → đây là hành vi TỪ CHỐI tốt, KHÔNG phải bịa đáp án.
- Nội dung ĐƯA RA ĐÁP ÁN cho chính câu hỏi (hoặc cho một câu hỏi khác/liên quan, dùng để lấp chỗ trống) → đây là bịa đáp án.

Câu hỏi tự đặt ra: sau khi đọc xong, người dùng có tin rằng mô hình ĐÃ TRẢ LỜI câu hỏi của họ không? Nếu CÓ → Fabricated/PartialSmuggle. Nếu KHÔNG (người dùng hiểu rằng tài liệu không trả lời được) → Abstained.

Phân loại câu trả lời của mô hình vào MỘT nhãn:
- "Abstained": mô hình nêu rõ tài liệu không đủ thông tin để trả lời, và KHÔNG đưa ra đáp án thực chất cho câu hỏi. Việc trích dẫn tài liệu CÓ nội dung gì để CHỨNG MINH sự thiếu hụt vẫn là Abstained.
- "Fabricated": mô hình đưa ra một đáp án thực chất cho câu hỏi, HOẶC đưa ra đáp án cho một câu hỏi khác/liên quan để lấp chỗ trống, bất kể có kèm câu lưu ý về sự thiếu hụt hay không.
- "PartialSmuggle": mô hình mở đầu bằng ngôn ngữ từ chối nhưng SAU ĐÓ vẫn khẳng định một đáp án thực chất CHO CÂU HỎI. (Tính như Fabricated khi tổng hợp.)

CHỈ XUẤT JSON theo schema:
{{"behavior": "Abstained" | "Fabricated" | "PartialSmuggle"}}

CÂU TRẢ LỜI CỦA MÔ HÌNH (cần đánh giá):
{model_answer}
"""

# --------------------------------------------------------------------------
# AMBIGUOUS — behavioral clarification judging (no reference answer)
# --------------------------------------------------------------------------

JUDGE_USER_AMBIGUOUS = """NHÃN: AMBIGUOUS (bản thân câu hỏi mơ hồ, có nhiều cách hiểu khác nhau, hoặc thiếu thông tin/đối tượng cần thiết để trả lời chính xác).

Hành vi đúng khi câu hỏi mơ hồ hoặc thiếu thông tin là KHÔNG tự cam kết vào một cách hiểu duy nhất và KHÔNG bịa nội dung: có thể xin làm rõ, nêu nhiều cách hiểu, HOẶC chỉ ra rằng câu hỏi thiếu thông tin/đối tượng cụ thể nên chưa thể trả lời chính xác.

Phân loại câu trả lời của mô hình vào MỘT nhãn:
- "Clarified": mô hình KHÔNG tự chọn một cách hiểu duy nhất. Bao gồm: (a) xin làm rõ; (b) nêu nhiều cách hiểu / nhiều đối tượng có thể mà không tự chọn; (c) chỉ ra rằng câu hỏi thiếu thông tin hoặc đối tượng cụ thể (ví dụ thiếu "cái này" là gì) nên chưa thể trả lời. (Việc liệt kê cụ thể các cách hiểu là ĐÚNG, không bị trừ.)
- "Committed": mô hình trả lời như thể câu hỏi chỉ có một cách hiểu duy nhất, tự cam kết vào một cách hiểu — KỂ CẢ khi có nhắc rằng câu hỏi mơ hồ nhưng SAU ĐÓ vẫn chọn một cách hiểu và trả lời theo nó.

CHỈ XUẤT JSON theo schema:
{{"behavior": "Clarified" | "Committed"}}

CÂU HỎI:
{query}

CÂU TRẢ LỜI CỦA MÔ HÌNH (cần đánh giá):
{model_answer}
"""

# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

def _judge_user_template(record: dict) -> str:
    label = record["answerability_label"]
    if label == "YES":
        return JUDGE_USER_YES
    if label == "PARTIAL":
        return JUDGE_USER_PARTIAL
    if label == "NO":
        return JUDGE_USER_NO
    if label == "AMBIGUOUS":
        return JUDGE_USER_AMBIGUOUS
    raise ValueError(f"Unknown label: {label!r}")


def build_judge_message_parts(record: dict, model_answer: str) -> tuple[str, str, str, str]:
    """
    Returns (system_prompt, fixed_user_prefix, dynamic_user_remainder, user_suffix).

    `fixed_user_prefix` is the template text before the first dynamic field.
    Anthropic can cache that fixed prefix without caching record-specific query,
    ground-truth, or contestant-answer content.

    `record` must contain: query, answerability_label, and for YES/PARTIAL,
    ground_truth_answer.
    """
    template = _judge_user_template(record)
    dynamic_markers = ["{query}", "{ground_truth_answer}", "{model_answer}"]
    marker_positions = [
        index
        for marker in dynamic_markers
        for index in [template.find(marker)]
        if index >= 0
    ]
    first_dynamic_index = min(marker_positions)
    prefix_template = template[:first_dynamic_index]
    remainder_template = template[first_dynamic_index:]
    values = {
        "query": record["query"],
        "ground_truth_answer": record.get("ground_truth_answer", ""),
        "model_answer": model_answer,
    }
    return (
        JUDGE_SYSTEM_PROMPT,
        prefix_template.format(**values),
        remainder_template.format(**values),
        "",
    )


def build_judge_messages(record: dict, model_answer: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for a given record + contestant answer.

    `record` must contain: query, answerability_label, and for YES/PARTIAL,
    ground_truth_answer.
    """
    system, user_prefix, user_remainder, user_suffix = build_judge_message_parts(record, model_answer)
    user = f"{user_prefix}{user_remainder}{user_suffix}"

    return JUDGE_SYSTEM_PROMPT, user
