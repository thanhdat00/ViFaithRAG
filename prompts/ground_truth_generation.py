"""
Contestant-model generation prompts for ViFaithRAG Task 2.

Design (locked):
  - Each contestant sees the query + the FULL three-document context (the noisy
    retrieval is the point of the benchmark). No relevance filtering, no passage
    selection — the same context the dataset ships.
  - The contestant is NOT told the answerability label.
  - The instruction is FIXED across all contestants (fair comparison): answer from
    the documents; if they don't contain enough information, say so; be concise.
  - The abstention affordance is explicit and neutral, so a faithful model *can*
    decline — otherwise "failure to abstain" would be an artifact of the prompt,
    not the model.

The instruction is deliberately close to a realistic RAG system prompt. Keep it
identical for every contestant and pin it in the paper (Appendix), because the
generation prompt is part of the evaluation protocol.
"""

# --------------------------------------------------------------------------
# System prompt — fixed across all contestant models
# --------------------------------------------------------------------------

GENERATION_SYSTEM_PROMPT = """Bạn là trợ lý trả lời câu hỏi dựa trên các tài liệu được cung cấp.

QUY TẮC:
1. Chỉ trả lời dựa trên nội dung các tài liệu được cung cấp. Không dùng kiến thức bên ngoài.
2. Nếu các tài liệu KHÔNG chứa đủ thông tin để trả lời, hãy nói rõ rằng không đủ thông tin để trả lời, thay vì suy đoán.
3. Nếu các tài liệu chỉ trả lời được một phần câu hỏi, hãy trả lời phần có thông tin và nêu rõ phần nào không có trong tài liệu.
4. Nếu câu hỏi mơ hồ hoặc có thể hiểu theo nhiều cách khác nhau, hãy nêu rõ điều đó hoặc hỏi lại cho rõ, thay vì tự chọn một cách hiểu.
5. Không thêm lời khuyên, cảnh báo, hay thông tin ngoài phạm vi câu hỏi.
6. Văn phong: trực tiếp, ngắn gọn, trung lập, tiếng Việt chuẩn, đúng thuật ngữ pháp lý nếu là câu hỏi pháp luật.
7. Nếu câu hỏi yêu cầu thông tin "hiện nay", "mới nhất", "đang áp dụng" hoặc gắn với một thời điểm: hãy trả lời dựa trên thông tin có trong tài liệu, NHƯNG nếu tài liệu thiếu mốc thời gian, ngày hiệu lực, hoặc dấu hiệu đủ rõ để xác nhận thông tin còn phù hợp với thời điểm được hỏi, hãy nêu rõ hạn chế này. Không tự suy đoán thông tin còn hiệu lực hay không.
8. Định dạng đầu ra:
   - Chỉ xuất câu trả lời cuối cùng. Không tiêu đề, không lời dẫn, không lặp
     lại câu hỏi, không giải thích hay quá trình suy luận.
   - Không dùng markdown (không #, *, -, bảng, bullet list).
   - Với câu hỏi nhiều ý, được phép đánh số dạng văn xuôi trong đoạn:
     "(1) ..., (2) ..., (3) ...".
9. Độ dài: câu trả lời phải NGẮN NHẤT CÓ THỂ mà vẫn đầy đủ — đúng một câu trả lời trực tiếp cho mỗi ý được hỏi tường minh. Không mở bài, không nhắc lại câu hỏi, không bối cảnh, không kết luận, không tổng hợp lặp lại.
   - Câu hỏi một ý dạng tra cứu: thường 1-3 câu.
   - Câu hỏi nhiều ý: mỗi ý 1-3 câu.
"""

# --------------------------------------------------------------------------
# User prompt — query + full context
# --------------------------------------------------------------------------

GENERATION_USER_TEMPLATE = """CÂU HỎI:
{query}

CÁC TÀI LIỆU:
{documents}

Hãy trả lời câu hỏi dựa trên các tài liệu trên."""


def format_documents(context: list[dict]) -> str:
    """
    Render the 3-doc context into the prompt. Preserves original doc_index so the
    numbering the contestant sees matches the released dataset (Doc 1/2/3).
    `context` elements: {doc_index, title, content, ...}.
    """
    blocks = []
    for doc in sorted(context, key=lambda d: d["doc_index"]):
        idx = doc["doc_index"]
        title = doc.get("title", "").strip()
        content = doc.get("content", "").strip()
        header = f"[Tài liệu {idx}]" + (f" {title}" if title else "")
        blocks.append(f"{header}\n{content}")
    return "\n\n".join(blocks)


def build_generation_messages(record: dict) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for a contestant model on one record."""
    documents = format_documents(record["context"])
    user = GENERATION_USER_TEMPLATE.format(query=record["query"], documents=documents)
    return GENERATION_SYSTEM_PROMPT, user
