# ViFaithRAG – ví dụ cho seminar

Generated from `final_dataset.jsonl` and `model_baseline_results/` (judge: claude-sonnet-4-6). Queries, answers, titles and model excerpts are verbatim from the data; each excerpt was checked as an exact substring of its source by `build_md.py`.

**Field-name mapping.** The real values differ from the brief, so I mapped them:
- `answer_provenance` "accepted / minor edit" = `model_accepted` / `model_minor_edited`.
- `final_label_source` "consensus" = `raw_agreement`. No `consensus` value exists in the data; `raw_agreement` is the closest, meaning both annotators agreed and the label was not changed later.

**Model results** come from:
- `model_baseline_results/final_answer_<model>.jsonl` (answers);
- `model_evaluation.jsonl` (`behavior`, `scope_violation`, claim and key-point counts);
- `all_model_judge_raw_results.jsonl` (judge claims and key points). This file is joined via `custom_id = judge_<i>_<md5(id␟model)[:16]>`. 16,468/16,469 rows joined; one judge call failed because of an API credit error.

**Process.**
1. A script (`filter_slots.py`) applied the automatic filters. Counts per filter are below.
2. Each shortlisted record was read in full: all 3 docs, 4 answers and the judge JSON.
3. The candidates were ranked.
4. The doc role, label explanation, slide fit and risk columns are human-style judgments made while reading.

⭐ = top pick for the slot.

<details><summary>Candidate counts after each filter (automatic stage)</summary>

```
Slot A: base pool 1884
   after exactly 1 supporting doc: 306
   after 1. query <= 15 words: 269
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 171
   after 3. provenance accepted/minor (YES/PARTIAL): 166
   after 4. neutral topic + not already used (keyword screen): 153
   after 5. readable docs (>=400 chars each, not link-list): 102
Slot B: base pool 779
   after exactly 1 supporting doc: 175
   after everyday-procedure keyword: 132
   after 1. query <= 15 words: 94
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 56
   after 3. provenance accepted/minor (YES/PARTIAL): 53
   after 4. neutral topic + not already used (keyword screen): 52
   after 5. readable docs (>=400 chars each, not link-list): 51
Slot C: base pool 335
   after 1. query <= 15 words: 265
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 91
   after 3. provenance accepted/minor (YES/PARTIAL): 88
   after 4. neutral topic + not already used (keyword screen): 81
   after 5. readable docs (>=400 chars each, not link-list): 47
Slot D: base pool 302
   after everyday-procedure keyword: 202
   after 1. query <= 15 words: 115
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 91
   after 3. provenance accepted/minor (YES/PARTIAL): 91
   after 4. neutral topic + not already used (keyword screen): 89
   after 5. readable docs (>=400 chars each, not link-list): 71
Slot E: base pool 769
   after 1. query <= 15 words: 651
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 504
   after 3. provenance accepted/minor (YES/PARTIAL): 504
   after 4. neutral topic + not already used (keyword screen): 486
   after 5. readable docs (>=400 chars each, not link-list): 355
Slot F: base pool 48
   after 1. query <= 15 words: 44
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 26
   after 3. provenance accepted/minor (YES/PARTIAL): 26
   after 4. neutral topic + not already used (keyword screen): 25
   after 5. readable docs (>=400 chars each, not link-list): 19
Slot G: base pool 214
   after 1. query <= 15 words: 185
   (2. clean label (a1=a2=final, raw_agreement, not changed): relaxed for this slot)
   after 3. provenance accepted/minor (YES/PARTIAL): 176
   after 4. neutral topic + not already used (keyword screen): 171
   after 5. readable docs (>=400 chars each, not link-list): 114
Slot H: base pool 2998
   after model w/ 3-5 claims, >=1 unsupported, misses >=1 of 2-3 key points: 455
   after 1. query <= 15 words: 372
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 224
   after 3. provenance accepted/minor (YES/PARTIAL): 212
   after 4. neutral topic + not already used (keyword screen): 203
   after 5. readable docs (>=400 chars each, not link-list): 164
Slot I: base pool 1071
   after >=3/4 models Fabricated: 297
   after 1. query <= 15 words: 243
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 146
   after 3. provenance accepted/minor (YES/PARTIAL): 146
   after 4. neutral topic + not already used (keyword screen): 139
   after 5. readable docs (>=400 chars each, not link-list): 112
   of which legal: 24
Slot J: base pool 335
   after all 4 models scope_violation: 30
   after 1. query <= 15 words: 18
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 9
   after 3. provenance accepted/minor (YES/PARTIAL): 9
   after 4. neutral topic + not already used (keyword screen): 9
   after 5. readable docs (>=400 chars each, not link-list): 3
Slot K: base pool 48
   after >=1 model Committed: 42
   after 1. query <= 15 words: 38
   after 2. clean label (a1=a2=final, raw_agreement, not changed): 23
   after 3. provenance accepted/minor (YES/PARTIAL): 23
   after 4. neutral topic + not already used (keyword screen): 22
   after 5. readable docs (>=400 chars each, not link-list): 17
```

</details>

## Slot A. YES, open domain – ba vai trò tài liệu

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | answer_with_citations (rút gọn) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `612dad5c-9c70-58f5-85e9-6143dadf2b0f` | open_domain | YES | dưa hấu giả là gì ? | Doc 1 mô tả trực tiếp dưa hấu giả (bề ngoài như thật, ruột dẻo như cao su, làm từ chất giả như cao su), nên câu hỏi trả lời được trọn vẹn từ một tài liệu. | **1** · Xuất hiện dưa hấu giả dẻo như cao su gây hoang mang · *hỗ trợ – định nghĩa dưa hấu giả dẻo như cao su*<br>**2** · Cận cảnh quy trình 'làm giả' miếng dưa hấu rẻ tiền trở thành thịt cá ngừ đắt giá, hầu hết người xem đều bị lừa khi lần đầu nhìn thấy · *cùng chủ đề – "làm giả" dưa hấu thành sushi cá ngừ (bẫy từ khóa)*<br>**3** · Đây là loại dưa hấu 'lạ', bé bất ngờ, trước cả trăm nghìn đồng/kg, nay bán đầy chợ với giá 'siêu rẻ' · *nhiễu – giá dưa hấu mini Hàn Quốc* | Dưa hấu giả là trái dưa có bề ngoài không khác gì dưa hấu thật, ruột đầy nước và màu sắc như thật nhưng lại dẻo như cao su, không giòn như dưa hấu thật và được làm từ chất giả như cao su [Doc 1]. | YES / YES | Câu hỏi 5 từ; ba vai trò rõ như sách giáo khoa; bẫy "làm giả" ở Doc 2 hiểu ngay. Bonus: deepseek-v4-flash từ chối sai, qwen3-8b kéo nội dung Doc 2/3 vào thành "các loại". | Doc 1 là tin clip lan truyền cũ, có câu quy cho "hàng Trung Quốc giả" – không chiếu đoạn 2 của Doc 1. |
| 2 | `f2660dfe-d166-5038-96ed-0093776b4a45` | open_domain | YES | sữa và sửa khác nhau như thế nào? | Doc 1 giải nghĩa rõ "sửa" (làm lại, khắc phục) và "sữa" (chất lỏng giàu dinh dưỡng), đủ để phân biệt hai từ. | **1** · Sữa chữa hay sửa chữa đúng chính tả tiếng Việt? · *hỗ trợ – định nghĩa sửa/sữa*<br>**2** · Phân biệt thế nào là sửa chữa nhỏ (sửa chữa thường ... · *nhiễu – hỏi đáp Bộ Tài chính về sửa chữa trụ sở, chỉ trùng chữ "sữa chữa" viết sai*<br>**3** · Sữa đầu và sữa cuối mất cân bằng có tác hại gì? · *cùng chủ đề – về sữa mẹ, không so sánh hai từ* | "Sửa" có nghĩa là làm lại, khắc phục lại một vật hoặc một điều gì đó cho đúng, thường dùng để chỉ hành động khắc phục lại lỗi lầm, những chỗ sai sót [Doc 1]. Trong khi đó, "sữa" là một danh từ dùng để chỉ chất lỏng giàu dinh dưỡng được tiết từ tuyến vú hoặc chiết xuất từ các loại đậu [Doc 1]. | YES / YES | Rất "Việt", vui; Doc 2 minh họa nhiễu do khớp từ khóa (chính nó viết sai "sữa chữa"). | Doc 3 là bài về nuôi con bằng sữa mẹ của một trang y tế (chỉ là tài liệu gây nhiễu); ranh giới cùng chủ đề/nhiễu của Doc 3 hơi mờ. |
| 3 | `7a267a7f-bf6d-5e0f-8afc-c6de3f29aad7` | open_domain | YES | làm thế nào để thực hiện nước đi "check mate" trong cờ vua? | Doc 1 (mục "Chiếu" và "Chiếu hết") nêu chiếu hết là khi Vua bị chiếu mà không thể thoát, đủ để trả lời cách thực hiện chiếu hết. | **1** · Tất tần tật Luật chơi cờ vua đơn giản - dễ hiểu - dễ ghi nhớ · *hỗ trợ – trang luật cờ, mục chiếu/chiếu hết*<br>**2** · (Thi thố) Cờ vua · *nhiễu – bài diễn đàn voz về chững Elo*<br>**3** · Cô gái khiếm thị mang vinh quang về cho Tổ quốc · *cùng chủ đề – chuyện kỳ thủ khiếm thị, chỉ giải thích "check mate là chiếu hết"* | Để thực hiện "check mate" (chiếu hết), người chơi cần đưa ra nước chiếu khiến quân Vua của đối phương không thể thoát khỏi tình trạng bị chiếu [Doc 1]. | YES / YES | Doc 3 là ví dụ đẹp của "nhắc thuật ngữ nhưng không trả lời". | Nhãn YES hơi mềm (deepseek cho rằng tài liệu chỉ định nghĩa, không chỉ "cách"); Doc 2 và 3 đều liên quan cờ vua nên nhiễu/cùng chủ đề chỉ khác mức độ. |

## Slot B. YES, legal – thủ tục đời thường

⚠️ Không ứng viên legal nào có tài liệu **nhiễu thật sự** (cả ba tài liệu thường cùng từ dichvucong.gov.vn / thuvienphapluat.vn). "nhiễu (tương đối)" = tài liệu pháp lý nhưng vô dụng cho câu hỏi này.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | answer_with_citations (rút gọn) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `1b8df05b-e97d-5cef-9ac7-dce5fd3d2744` | legal | YES | ứng dụng định danh quốc gia tải ở đâu | Doc 3 hướng dẫn rõ: tải VNeID trên CH Play (Android) hoặc App Store (iOS). | **1** · Cấp tài khoản định danh điện tử mức độ 01 cho công dân ... · *cùng chủ đề – thủ tục chính thức ghi "tải và cài đặt VNeID" nhưng không nói tải ở đâu*<br>**2** · Cấp tài khoản định danh điện tử cho cơ quan, tổ chức · *nhiễu (tương đối) – thủ tục cấp tài khoản cho cơ quan, tổ chức*<br>**3** · Hướng dẫn đăng ký, kích hoạt và sử dụng tài khoản định danh điện tử trên ứng dụng VNeID đơn giản, chính xác nhất? · *hỗ trợ – bước "Tải ứng dụng" nêu CH Play/App Store* | Người dùng có thể tải ứng dụng định danh điện tử quốc gia (VNeID) trên ứng dụng CH Play (đối với thiết bị sử dụng hệ điều hành Android) hoặc App store (đối với thiết bị sử dụng hệ điều hành IOS) [Doc 3]. | YES / YES | Ai trong phòng cũng đã dùng VNeID; đáp án 1 dòng; Doc 1 là "near-miss" đẹp (nhắc tải nhưng không nói ở đâu). Cả 4 mô hình trả lời đúng. | Doc 2 vẫn liên quan VNeID nên không phải nhiễu thật; Doc 3 có nhắc thông tin tiêm vắc xin COVID (không chiếu). |
| 2 | `0f74f82c-9ff0-46ff-a2f4-7815e950224c` | legal | YES | có thể nhập chung 2 giấy phép lái xe ô tô và xe máy không? | Doc 3 dẫn Điều 32 Thông tư 35/2024/TT-BGTVT: cá nhân có nhu cầu thì được tích hợp GPLX xe máy với ô tô qua thủ tục đổi, không bắt buộc. | **1** · Có được sử dụng đồng thời 2 giấy phép lái xe ô tô không? · *nhiễu (tương đối) – giữ hai GPLX ô tô cùng lúc, Thông tư 12/2017 cũ (gây hiểu nhầm)*<br>**2** · Gộp bằng lái xe thì khi bị tước giấy phép điều khiển xe ô tô có còn được tiếp tục điều khiển xe máy không? · *cùng chủ đề – GPLX tích hợp khi bị tạm giữ phần ô tô, không có thủ tục*<br>**3** · Từ năm 2025, có phải tích hợp bằng lái xe máy với bằng lái ô tô không? · *hỗ trợ – tích hợp tùy chọn từ 2025* | Có thể nhập chung 2 giấy phép lái xe ô tô và xe máy nếu cá nhân có nhu cầu bằng cách đăng ký vào đơn đề nghị đổi (cấp lại) giấy phép lái xe và làm thủ tục đổi giấy phép lái xe [Doc 3]. Việc tích hợp này không bắt buộc và chỉ thực hiện khi người dân có nhu cầu [Doc 3]. | YES / YES | Câu hỏi đời thường về bằng lái. Bonus: qwen3-8b bị Doc 1 đánh lừa, mở đầu bằng "Không được nhập chung 2 giấy phép lái xe ô tô". | Thủ tục ở Doc 3 (Sở GTVT) đã lỗi thời vì từ 3/2025 chuyển sang công an – chỉ chiếu ý "có thể, không bắt buộc". |
| 3 | `af9c1dae-e412-5941-aded-92810cbbcb8e` | legal | YES | làm thế nào để kiểm tra xem mình đã đăng ký kt3 hay chưa? | Doc 1 hướng dẫn xem nơi tạm trú ở mục "Thông tin cư trú" trên VNeID (tài khoản mức 2), đúng nhu cầu kiểm tra đã đăng ký tạm trú (KT3) hay chưa. | **1** · Hướng dẫn xem địa chỉ tạm trú và hộ khẩu điện tử trên ứng dụng VneID · *hỗ trợ – VNeID → Ví giấy tờ → Thông tin cư trú*<br>**2** · Gia hạn tạm trú · *cùng chủ đề – gia hạn tạm trú (thủ tục trực tiếp)*<br>**3** · Xóa đăng ký tạm trú · *cùng chủ đề – xóa đăng ký tạm trú* | Để kiểm tra xem đã đăng ký tạm trú hay chưa, công dân có thể xem thông tin nơi tạm trú trên ứng dụng VNeID thông qua tài khoản định danh điện tử mức độ 2 và phiên bản ứng dụng mới nhất [Doc 1]. | YES / YES | Ai từng thuê trọ đều hiểu; Doc 2 và 3 là bẫy "đúng chủ đề, sai thủ tục". | Không có tài liệu nhiễu; "KT3" là thuật ngữ cũ cần giải thích; trùng chủ đề VNeID với #1. |

## Slot C. PARTIAL – tài liệu chỉ trả lời một phần

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | answer_with_citations (rút gọn) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `ce335062-4957-5f3c-a7b0-539ea7c8e9cb` | open_domain | PARTIAL | giá của hoa tươi trong dịp 8/3 và 20/10 là bao nhiêu? | Tài liệu có giá chi tiết từng loại hoa dịp 8/3, nhưng với dịp 20/10 chỉ có một dòng quảng cáo "thiết kế hoa theo yêu cầu từ 500K", không có giá hoa tươi cụ thể. | **1** · Hoa tươi tăng giá mạnh trước ngày 8/3 · *hỗ trợ – giá hoa 8/3 ở chợ Hồ Thị Kỷ, Emart (TP.HCM)*<br>**2** · Giá hoa tươi tăng nhẹ, thị trường quà tặng sôi động trước thềm 8/3 · *hỗ trợ – giá hoa 8/3 tại Hà Nội*<br>**3** · Đặt Hoa 20-10 Đẹp Tặng Chúc Mừng Mẹ, Vợ, Bạn Gái - Giao Miễn Phí · *hỗ trợ (yếu) – quảng cáo tiệm hoa 20/10, chỉ "từ 500K"* | Đối với dịp 20/10, dịch vụ thiết kế hoa theo yêu cầu có mức giá chỉ từ 500K [Doc 3]. Ngữ cảnh không đề cập chi tiết mức giá của từng loại hoa tươi cụ thể trong dịp 20/10. | YES / PARTIAL | Câu hỏi hai vế, một vế có, một vế không – phần thiếu nói trong một câu; cả 4 mô hình đều nêu đúng phần thiếu (đối chiếu đẹp với slot J). | Giá là của tháng 3/2025; "từ 500K" dễ bị hiểu là giá hoa 20/10 – cần nói rõ đó là dịch vụ thiết kế. |
| 2 | `91804d53-f70e-5f37-94fd-d65ed8b87f53` | open_domain | PARTIAL | so sánh dòng đàn yamaha clp-835 và clp735 | Tài liệu có đủ thông số CLP-735 (phím GrandTouch S, ampli 30W x 2, loa 16cm x 2) nhưng về CLP-835 chỉ có giới thiệu chung dòng CLP-800 và một nhận xét người dùng, nên không so sánh được thông số. | **1** · REVIEW PIANO ĐIỆN YAMAHA CLP735 – CLP745 – CLP775 \| SERIES MỚI · *hỗ trợ – review thông số CLP-735/745/775*<br>**2** · 「Sale 10%」Đàn Piano Điện YAMAHA CLP-735 R - Chính Hãng - Trả Góp 0% \| PIANO HOUSE · *hỗ trợ – trang bán CLP-735*<br>**3** · Digital Piano Yamaha CLP-835 · *hỗ trợ (yếu) – marketing CLP-800, một trích dẫn người dùng về CLP-835* | Yamaha CLP-835 thuộc dòng CLP-800, được người dùng đánh giá là một cây đàn piano cơ bản tuyệt vời với âm thanh và cảm giác chơi được cải thiện rõ rệt [Doc 3]. Ngữ cảnh không đề cập chi tiết các thông số kỹ thuật (như phím, loa, công suất, bảng điều khiển) của dòng Yamaha CLP-835 để so sánh toàn diện với CLP-735. | PARTIAL / PARTIAL | So sánh A với B mà chỉ A có dữ liệu – hiểu ngay; chủ đề trung tính. | Sản phẩm hơi ngách; qwen3-8b nói cả hai dùng GrandTouch-S (overclaim nhẹ). |
| 3 | `03019cc8-5151-5919-bc56-60e4c8e919d7` | open_domain | PARTIAL | mixue có bao nhiêu chi nhánh rồi | Tài liệu chỉ có các con số cũ và không thống nhất (36.000 chi nhánh toàn cầu; 21.582 cửa hàng tính đến 3/2023; 1.000 cửa hàng tại Việt Nam), không có số chi nhánh hiện tại. | **1** · Không có trình độ học vấn thì chẳng thể làm gì: Bài học thấm thía từ ông chủ đế chế Mixue trị giá 2,9 tỷ USD, học hết cấp 2 đã đòi khởi nghiệp và cú 'vả mặt' đầu đời · *hỗ trợ – chuyện nhà sáng lập, "36.000 chi nhánh"*<br>**2** · Mixue cán mốc 1.000 cửa hàng tại Việt Nam sau 6 năm: Kem Tràng Tiền đang cạnh tranh thế nào trên sân nhà? · *hỗ trợ – 1.000 cửa hàng tại Việt Nam*<br>**3** · Từ quán ven đường trở thành Top5 chuỗi fastfood toàn cầu: công thức nào cho sự bành trướng của Mixue? · *hỗ trợ – 21.582 cửa hàng đến 3/2023* | Tại Việt Nam, Mixue có 1.000 cửa hàng [Doc 2] và tại Indonesia có khoảng 1.500 cửa hàng tính đến tháng 3/2023 [Doc 3]. Ngữ cảnh không đề cập số lượng chi nhánh chính xác mới nhất của Mixue ở thời điểm hiện tại. | PARTIAL / YES | Khoảng trống "rồi/hiện nay" kinh điển, thương hiệu ai cũng biết. | Số liệu mâu thuẫn nhau nên thông điệp thành hai ý (độ mới + không nhất quán). |

## Slot D. NO, legal – đúng chủ đề nhưng thiếu con số / chủ thể

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `a71f9525-32df-413d-a4a6-3eac477ca213` | legal | NO | làm số nhà ở thành phố hồ chí minh mất bao nhiêu tiền | Tài liệu chỉ mô tả thủ tục cấp/cấp lại số nhà (10 ngày làm việc, nơi nộp) và ghi chung "nộp lệ phí theo quy định", hoàn toàn không có mức phí bằng tiền tại TP.HCM. | **1** · Cấp giấy chứng nhận số nhà (cấp lần đầu) · *cùng chủ đề – thủ tục cấp số nhà lần đầu, có nhắc phí nhưng không có số*<br>**2** · Thủ tục cấp lại, chỉnh sửa số nhà · *cùng chủ đề – thủ tục cấp lại, "đóng lệ phí theo quy định"*<br>**3** · Việc cấp biển số nhà được quy định như thế nào? Cơ quan nào là cơ quan có thẩm quyền cấp biển số nhà? · *cùng chủ đề – quy tắc đánh số nhà (QĐ 05/2006)* | NO / NO | Ca "bao nhiêu tiền?" sạch: tài liệu cứ nói "phí theo quy định" mà không có con số; cả 4 mô hình đều từ chối đúng. | Doc 3 mở đầu bằng câu hỏi của bạn đọc có tên riêng – không chiếu dòng đó. |
| 2 | `22330154-37a5-4946-89a2-73507af86d6a` | legal | NO | có cách nào tra cứu phạt nguội trên zalo không? | Tài liệu liệt kê 5 cách tra cứu phạt nguội (VNeTraffic, web CSGT, Cục Đăng kiểm, Sở GTVT, app) và chỉ nhắc Zalo như kênh gửi phản ánh vi phạm, không nói có tra cứu phạt nguội trên Zalo được hay không. | **1** · 05 cách tra cứu phạt nguội vi phạm giao thông online mới nhất 2025 · *cùng chủ đề – 5 cách tra cứu, không có Zalo*<br>**2** · Tổng hợp các link tra cứu phạt nguội 2025 online nhanh chóng · *cùng chủ đề – link tra cứu, không có Zalo*<br>**3** · Cách gửi phản ánh vi phạm giao thông tới cảnh sát qua VNeTraffic, Zalo, đường dây nóng 2025? · *cùng chủ đề – Zalo dùng để phản ánh, không phải tra cứu* | NO / NO | Bẫy từ vựng đẹp: "Zalo" có trong tài liệu nhưng với mục đích khác. | Doc 2 có byline phóng viên và một dòng link "văn khấn" lạc chỗ (nhỏ). |
| 3 | `a9dabcbc-5ba0-5550-9825-38f29d8c4f6b` | legal | NO | tôi bị mất cccd, vậy mai cơ quan hành chính có làm việc k | Tài liệu nói rõ nơi, thủ tục, lệ phí (70.000đ) và thời hạn cấp lại CCCD nhưng không có lịch/giờ làm việc của cơ quan, nên không thể biết "mai" cơ quan có làm việc hay không. | **1** · Cách làm lại căn cước công dân khi bị mất · *cùng chủ đề – các bước cấp lại, lệ phí, hạn 15 ngày*<br>**2** · Bị mất thẻ Căn cước công dân thì xin cấp lại ở đâu? Thời hạn cấp lại thẻ Căn cước công dân được quy định như thế nào? · *cùng chủ đề – nơi cấp lại, thời hạn*<br>**3** · Mất chứng minh nhân dân có làm thẻ căn cước công dân được không? Muốn làm thẻ căn cước công dân khi chứng minh nhân dân bị mất phải thực hiện như thế nào? · *cùng chủ đề – mất CMND cũ, thủ tục* | PARTIAL / NO | Ai cũng thấy tài liệu không thể biết "ngày mai"; bonus: qwen3-8b bịa "Cơ quan hành chính có làm việc vào ngày mai." | Tài liệu dẫn Luật CCCD 2014 (cũ) – không ảnh hưởng nhãn; câu hỏi ghép hai ý (mất CCCD + lịch làm việc). |

## Slot E. NO, open domain – chủ đề đời thường

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `785f0620-3873-5516-8044-202559267af6` | open_domain | NO | thời gian bay từ vienna, áo đến bắc kinh là bao lâu? | Tài liệu có thời gian bay Hà Nội–Bắc Kinh (3 giờ 35 phút) và Việt Nam–Vienna (9–19 tiếng) nhưng không có chặng Vienna–Bắc Kinh mà câu hỏi cần. | **1** · Thời gian bay từ Hà Nội đến Bắc Kinh (Beijing) mất bao lâu? · *cùng chủ đề – thời gian bay Hà Nội–Bắc Kinh*<br>**2** · MỚI! Thời gian bay từ Việt Nam đến Áo mất bao lâu? · *cùng chủ đề – Việt Nam–Vienna, nối chuyến*<br>**3** · ﻿Vé máy bay đi Áo (Austria) của Eva Air · *cùng chủ đề – EVA Air đi Áo, giá vé* | NO / NO | Có đủ hai "nửa" của hành trình nhưng không có tổ hợp cần hỏi – rất trực quan; cả 4 mô hình từ chối đúng. | Văn bản quảng cáo đại lý vé; Doc 3 ghi sai Áo là thành viên NATO (không chiếu). |
| 2 | `74b70a69-5b1f-59f3-82aa-f3f04725aaff` | open_domain | NO | gợi ý món ăn sáng với ngân sách 2000 đồng | Tài liệu chỉ có thực đơn 200.000đ cho 2 bữa và 30.000đ/ngày (bánh mì 5.000đ, trứng chiên ~20.000đ), không có món ăn sáng nào vừa ngân sách 2.000 đồng. | **1** · Cầm 200.000 đồng ra chợ mua gì để có 2 bữa cơm vừa dinh dưỡng vừa ngon miệng? · *cùng chủ đề – thực đơn đi chợ 200k*<br>**2** · 10+ các món ăn nhanh không cần nấu đơn giản và ngon · *cùng chủ đề – món không cần nấu, không có giá (quảng cáo Kamereo)*<br>**3** · Thực đơn 1 tuần 200k - Thực đơn 30k 1 ngày ngon dễ làm · *cùng chủ đề – thực đơn 200k/tuần* | NO / NO | Lệch số vui (2k vs 200k) ai cũng hiểu; qwen3-8b tự mâu thuẫn: nói vượt 2000 đồng rồi vẫn gợi ý bánh mì 5.000 đồng. | Khán giả có thể nghĩ "2000" là gõ nhầm 20.000 – nhãn vẫn đúng vì tài liệu cũng không có bữa sáng 20.000đ. |
| 3 | `56dda98b-ca14-515a-8930-783163ec7199` | open_domain | NO | máy chủ của tiki nằm ở đâu? | Tài liệu chỉ có địa chỉ văn phòng (52 Út Tịch, 174 Thái Hà…) và kho bãi của Tiki, không có thông tin về vị trí đặt máy chủ. | **1** · Giới thiệu trụ sở văn phòng Tiki tại TPHCM và Hà Nội · *cùng chủ đề – địa chỉ văn phòng*<br>**2** · Giới thiệu về Tiki · *cùng chủ đề – giới thiệu công ty*<br>**3** · Giới thiệu các mô hình vận hành Tiki cho nhà bán hàng · *cùng chủ đề – mô hình bán hàng, kho bãi* | NO / NO | Cho thấy khác biệt giữa "địa chỉ văn phòng" và "vị trí máy chủ"; cả 4 mô hình từ chối đúng. | Nửa sau Doc 3 là boilerplate; thông tin công ty có thể cũ; một tài liệu nhắc khoản đầu tư của VNG (lưu ý vì người trình bày ở VNG). |

## Slot F. AMBIGUOUS – nhiều cách hiểu

Cả 3 ứng viên cũng xuất hiện ở slot K; top pick F (#1) khác top pick K.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `c6c0f7d6-3e67-5dcf-8b72-63e4d9f94e4f` | open_domain | AMBIGUOUS | khi nào cần tìm ai để hỏi | Chữ "ai" viết thường có thể là đại từ "ai" (khi nào cần tìm một người/chuyên gia để hỏi) hoặc "AI" (khi nào nên hỏi trí tuệ nhân tạo) – hai cách hiểu dẫn tới hai câu trả lời khác hẳn nhau. | **1** · Ngày càng nhiều thông tin sai, có nên tìm kiếm, hỏi AI? · *cùng chủ đề – khi nào câu trả lời của AI sai, cần kiểm chứng (chỉ hợp cách hiểu "AI")*<br>**2** · Một số câu hỏi thường gặp về trí tuệ nhân tạo \| Báo Nhân Dân điện tử · *cùng chủ đề – FAQ về AI, có header/footer boilerplate*<br>**3** · Muốn sử dụng AI, bắt đầu từ đâu? · *cùng chủ đề – bắt đầu học AI* | AMBIGUOUS / AMBIGUOUS | 7 từ, trò chơi chữ ai/AI hiểu ngay; cả gpt_reason và gemini_reason đều nêu đúng hai cách hiểu. | Doc 2 là bài 2023 ("ChatGPT … cuối tháng 11 năm ngoái") – chỉ dùng làm nền, đừng chiếu. |
| 2 | `07216974-614c-5867-8818-d78727c1a22e` | open_domain | AMBIGUOUS | lịch sử ngày 14 như thế nào | "Ngày 14" không nói rõ tháng: có thể là 14/2 (Valentine đỏ, gốc La Mã) hoặc 14/3 (Valentine trắng, khởi nguồn ở Nhật năm 1977), và tài liệu có lịch sử của cả hai ngày. | **1** · Ý nghĩa và nguồn gốc ngày Valentine 14/3 - Valentine trắng · *cùng chủ đề – nguồn gốc 14/3; nhiều boilerplate điều hướng*<br>**2** · Nguồn gốc và ý nghĩa của ngày lễ Giáng Sinh · *cùng chủ đề – nguồn gốc 14/2 (Thánh Valentine); tiêu đề ghi nhầm "Giáng Sinh"*<br>**3** · 14/2 là ngày gì? 14/2 là ngày của con trai hay con gái? · *cùng chủ đề – nguồn gốc 14/2 và phong tục tặng quà* | AMBIGUOUS / AMBIGUOUS | Hai cách hiểu ứng với các tài liệu khác nhau – vẽ thành hình rất trực quan. | Doc 2 có chi tiết về thánh tử đạo và các nước Hồi giáo cấm Valentine (gần tôn giáo) – cắt bỏ khi chiếu; Doc 1 nhiều chữ điều hướng. |
| 3 | `6a353767-3bda-5c7c-84b1-a8d2edb9417d` | open_domain | AMBIGUOUS | ok bn là ai z | "bn" có thể là "bạn" (hỏi chính trợ lý "bạn là ai") hoặc tên rapper "Binz" ("OK" còn là tên MV của Binz), nên không xác định được người hỏi đang hỏi về ai. | **1** · Rapper Binz thời chưa nổi tiếng · *cùng chủ đề – tiểu sử Binz, nhắc bài "OK"*<br>**2** · Rapper Binz và khối tài sản khủng đáng mơ ước · *cùng chủ đề – tài sản của Binz*<br>**3** · Cuộc sống như 'ông hoàng' của rapper số 1 Việt Nam Binz · *cùng chủ đề – thu nhập YouTube, MV "OK"* | YES / AMBIGUOUS | Ngôn ngữ chat tuổi teen, cú "lật" vui khi lộ ra cả 3 tài liệu đều về Binz. | gpt_label = YES (gemini = AMBIGUOUS); có thể có người cho rằng "bạn" là cách hiểu chính. Doc 1–2 có tin đồn tình cảm (Châu Bùi). |

## Slot G. Hard subset – LLM pre-label YES, người gán NO

Nhiều bản ghi G nhãn NO nhưng tài liệu **thực ra có đáp án** (vd. 3a9b20ec, 0a5d305e, 588b990d, c9f84e79, 6bb36461, bf30327c, d5070bf1 …) – đã loại. gpt_reason/gemini_reason rỗng cho cả ba ứng viên vì pre-labeler chỉ ghi lý do khi không trả lời YES. Mô hình lỗi được ghi kèm cho tham khảo.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Mô hình lỗi + trích nguyên văn | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `c22e81f9-a893-55ca-898f-46a863be3e96` | open_domain | NO | có thể hủy thẻ tín dụng online tại ngân hàng acb không? | Tài liệu nói về phí hủy thẻ ACB, gia hạn thẻ online qua ACB ONE, đóng thẻ tại chi nhánh và việc "một số ngân hàng" chưa hỗ trợ hủy online, nhưng không câu nào nói ACB có cho hủy thẻ online hay không. | **1** · Giải đáp thắc mắc từ A - Z khi thẻ tín dụng hết hạn · *cùng chủ đề – thẻ ACB hết hạn, gia hạn online (không phải hủy), đóng thẻ tại chi nhánh*<br>**2** · Một ngân hàng lớn thông báo thu thêm phí hủy thẻ trong trường hợp sau · *cùng chủ đề – phí hủy thẻ ACB; "một số ngân hàng chưa hỗ trợ hủy thẻ tín dụng online"*<br>**3** · Làm thẻ tín dụng trả góp mà không sử dụng có sao không? · *cùng chủ đề – phí của thẻ không dùng* | YES / YES | **Qwen3-8B**: “Không thể hủy thẻ tín dụng online tại ngân hàng ACB.”<br>3/4 mô hình Fabricated (chỉ deepseek từ chối).<br><sub>DeepSeek-V4-Flash: Abstained; Qwen3.5-397B-A17B: Fabricated; Gemma-4-31B-IT: Fabricated; Qwen3-8B: Fabricated</sub> | Near-miss kép: thao tác (gia hạn online ≠ hủy online) và phạm vi ("một số ngân hàng" ≠ ACB) – trông trả lời được, nhưng NO hiển nhiên khi chỉ ra. Nhãn sạch (raw_agreement). | Tên ngân hàng thật; thông tin phí là của 2025. |
| 2 | `a2da973d-5a31-5d61-8886-d64172f975ed` | open_domain | NO | nghĩa của tên mai an là gì? | Tài liệu giải nghĩa tên "Mai", "Mai Anh" và tên đệm "An Mai", nhưng không hề giải nghĩa tên "Mai An". | **1** · Ý nghĩa tên Mai và những tên đệm, biệt danh cho tên Mai hay nhất · *cùng chủ đề – nghĩa tên Mai; tên đệm có "An Mai"*<br>**2** · Biệt danh cho tên Mai Anh Hay – Độc – Lạ, mẹ lưu lại ngay nhé! · *cùng chủ đề – biệt danh cho Mai Anh*<br>**3** · Ý nghĩa tên Mai Anh là gì mà bố mẹ thi nhau đặt cho con? · *cùng chủ đề – nghĩa tên Mai Anh (có chút phong thủy)* | YES / YES | **Qwen3-8B**: “Tên Mai Anh mang ý nghĩa là một người thanh cao, cao quý, thông minh, tài hoa, có vóc dáng thanh tú và tràn đầy sức sống.”<br><sub>DeepSeek-V4-Flash: Abstained; Qwen3.5-397B-A17B: Fabricated; Gemma-4-31B-IT: Fabricated; Qwen3-8B: Fabricated</sub> | Thực thể lệch một chữ cái (An vs Anh) và đảo thứ tự (An Mai) – thấy ngay vì sao LLM bị lừa. | Có thể có người cãi PARTIAL (ghép "An = bình yên" từ "An Mai"); qwen3.5 làm đúng như vậy. |
| 3 | `c32c5c32-acf2-5795-8dbd-958e5a12f920` | open_domain | NO | trường tiểu học xã tân bình, tỉnh bình thuận nay là trường gì | Tài liệu chỉ liệt kê Trường Tiểu học Tân Bình (thị xã La Gi) theo tên cũ, không có thông tin trường được đổi tên hay sáp nhập thành trường nào. | **1** · DANH SÁCH CÁC TRƯỜNG TIỂU HỌC TRÊN ĐỊA BÀN THỊ XÃ LA GI · *cùng chủ đề – danh sách trường tiểu học La Gi*<br>**2** · Xã Tân Bình, Thị xã La Gi sau sáp nhập · *cùng chủ đề – trang SEO "sau sáp nhập" không có thông tin sáp nhập*<br>**3** · Top 8 Trường tiểu học xuất sắc nhất ở tỉnh Bình Thuận - Mytour.vn · *nhiễu – top 8 trường (Mytour)* | YES / YES | **Qwen3-8B**: “Trường Tiểu học Tân Bình, tỉnh Bình Thuận hiện nay là Trường Tiểu học Tân Bình thuộc danh sách các trường tiểu học trên địa bàn thị xã La Gi.”<br><sub>DeepSeek-V4-Flash: Fabricated; Qwen3.5-397B-A17B: Fabricated; Gemma-4-31B-IT: Abstained; Qwen3-8B: Fabricated</sub> | Near-miss thời gian (tên cũ vs "nay là"). | Yếu nhất: Doc 1 có tên hiệu trưởng (cá nhân); Doc 2 là văn bản SEO/AI; cần giải thích bối cảnh sáp nhập 2025. |

## Slot H. Claim decomposition – mệnh đề & ý chính

Lưu ý: judge chấm mệnh đề **so với câu trả lời tham chiếu**, không so với tài liệu (theo thiết kế của `prompts/judge.py`). Các mệnh đề Unsupported dưới đây đều có trong tài liệu, chỉ không có trong tham chiếu – trên slide nên gọi là "ngoài tham chiếu", không phải "bịa".

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | answer_with_citations (rút gọn) | gpt / gemini | Mô hình lỗi + trích nguyên văn | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `6b3d3408-26af-5da5-bd01-4201038c697c` | open_domain | YES | số hữu tỉ là gì ? | Cả ba tài liệu đều định nghĩa số hữu tỉ là số viết được dưới dạng a/b (a, b nguyên, b ≠ 0) hoặc số thập phân vô hạn tuần hoàn, nên câu hỏi trả lời được đầy đủ. | **1** · Số hữu tỉ là gì? Khái niệm, tính chất và ví dụ các dạng toán liên quan · *hỗ trợ – định nghĩa (kèm boilerplate shop)*<br>**2** · Cập nhật kiến thức tổng hợp về số hữu tỉ mới nhất 2023 · *hỗ trợ – định nghĩa, ký hiệu Q*<br>**3** · Số hữu tỉ là gì? Số vô tỉ là gì? Bài tập về số hữu tỉ và số vô tỉ · *hỗ trợ – định nghĩa* | Số hữu tỉ là tập hợp các số có thể viết được dưới dạng phân số a/b, trong đó a và b là các số nguyên và b khác 0, hoặc có thể biểu diễn dưới dạng số thập phân vô hạn tuần hoàn [Doc 1][Doc 2][Doc 3]. | YES / YES | **DeepSeek-V4-Flash**: “Số hữu tỉ là tập hợp các số có thể viết được dưới dạng phân số a/b, với a và b là các số nguyên và b khác 0, ký hiệu là Q.”<br>4 claims (1 Unsupported: "ký hiệu là Q"); 2 key points, thiếu "thập phân vô hạn tuần hoàn" → faithfulness 0.75, completeness 0.5.<br><sub>DeepSeek-V4-Flash: 3/4 claims, 1/2 KP; Qwen3.5-397B-A17B: 4/5 claims, 3/3 KP; Gemma-4-31B-IT: 5/7 claims, 3/3 KP; Qwen3-8B: 4/5 claims, 2/2 KP</sub> | Tham chiếu 1 câu / 2 ý chính, câu trả lời 1 câu / 4 mệnh đề – tính 3/4 và 1/2 ngay trên slide. | "Q" có trong cả 3 tài liệu – đúng sự thật, chỉ ngoài tham chiếu. Doc 3 đăng trên site công ty luật (nội dung thuần toán). |
| 2 | `e5679311-d9d8-5ae7-b216-0b957d21f377` | open_domain | YES | petrichor nghĩa là gì | Doc 2 định nghĩa petrichor là mùi đất ẩm sau mưa và Doc 3 mô tả nó là nốt hương trầm lắng sau mưa, nên câu hỏi trả lời được. | **1** · Petrichor là gì? \| Từ điển Anh - Việt \| ZIM Dictionary · *nhiễu – trang từ điển chỉ còn nav/footer*<br>**2** · Petrichor: Mùi Đất Sau Mưa - Từ Điển, Ý Nghĩa, và Cách Sử Dụng · *hỗ trợ – ngữ pháp và định nghĩa*<br>**3** · Bộ Sưu Tập Petrichor – Nốt Hương Trầm Lắng Sau Cơn Mưa · *hỗ trợ – blog trang sức, định nghĩa thơ mộng* | "Petrichor" là một danh từ tiếng Anh thường dùng để chỉ mùi hương đất ẩm sau cơn mưa [Doc 2], hay những nốt hương trầm lắng, ẩm ướt ẩn sâu trong lòng cỏ lá mang dư vị của mưa [Doc 3]. | YES / YES | **Gemma-4-31B-IT**: “Petrichor là một danh từ không đếm được trong tiếng Anh, dùng để chỉ mùi hương đất ẩm sau cơn mưa.”<br>3 claims (1 Unsupported: "không đếm được"); 3 key points, thiếu 1.<br><sub>DeepSeek-V4-Flash: 1/1 claims, 1/3 KP; Qwen3.5-397B-A17B: 3/4 claims, 3/3 KP; Gemma-4-31B-IT: 2/3 claims, 2/3 KP; Qwen3-8B: 3/5 claims, 2/3 KP</sub> | Câu trả lời ngắn nhất (3 mệnh đề), từ đẹp. | "không đếm được" có nguyên văn ở Doc 2; ý chính bị thiếu là văn quảng cáo của blog trang sức; tham chiếu có 3 ý (giới hạn trên). |
| 3 | `ea82cf71-ab01-5334-96ab-e19de89500dd` | open_domain | YES | con chó có thể đẻ ra mèo không | Cả ba bài báo đều dẫn lời giáo sư thú y rằng chó không thể đẻ ra mèo vì nhiễm sắc thể hai loài khác nhau, và con vật kia có thể chỉ là chó con trông giống mèo. | **1** · Chuyện lạ: Chó sinh ra mèo · *hỗ trợ – câu chuyện + trích chuyên gia (sidebar clickbait)*<br>**2** · Kỳ lạ chó đẻ ra... mèo? · *hỗ trợ – cùng câu chuyện*<br>**3** · Chó đẻ ra mèo? · *hỗ trợ – bản ngắn* | Chó không thể sinh ra mèo do số lượng và đặc điểm nhiễm sắc thể ở hai loài hoàn toàn khác nhau, và những trường hợp được cho là chó sinh ra mèo có thể chỉ là chó con có ngoại hình giống mèo [Doc 1][Doc 2][Doc 3]. | YES / YES | **Qwen3.5-397B-A17B**: “Dựa trên các tài liệu, mặc dù có ghi nhận lời kể của ông Jeong Pyong-bong về việc chó sinh ra con giống mèo, nhưng các chuyên gia khoa học thú y khẳng định chó không thể đẻ ra mèo vì bộ gen và số lượng nhiễm sắc thể của hai loài này hoàn toàn khác nhau.”<br>4 claims (1 Unsupported); 3 key points, thiếu "chỉ là chó con giống mèo".<br><sub>DeepSeek-V4-Flash: 3/3 claims, 2/3 KP; Qwen3.5-397B-A17B: 3/4 claims, 2/3 KP; Gemma-4-31B-IT: 4/6 claims, 3/3 KP; Qwen3-8B: 4/4 claims, 3/3 KP</sub> | Câu hỏi vui; ý bị thiếu (chỉ là chó con giống mèo) rất dễ thấy. | Câu trả lời là một câu dài 253 ký tự; nêu tên một người dân (nhân vật bài báo) – che tên khi chiếu; judge không nhất quán về "bộ gen" giữa các mô hình; Doc 1 có tiêu đề clickbait thô ở sidebar. |

**H #1** – `6b3d3408-26af-5da5-bd01-4201038c697c`, model `deepseek-v4-flash`, judge output (verbatim):

| claim | verdict |
|---|---|
| Số hữu tỉ là tập hợp các số có thể viết được dưới dạng phân số a/b | Supported |
| a và b là các số nguyên | Supported |
| b khác 0 | Supported |
| Số hữu tỉ ký hiệu là Q | Unsupported |

| gt_key_point | covered |
|---|---|
| Số hữu tỉ có thể viết dưới dạng phân số a/b với a, b nguyên và b khác 0 | true |
| Số hữu tỉ có thể biểu diễn dưới dạng số thập phân vô hạn tuần hoàn | false |

**H #2** – `e5679311-d9d8-5ae7-b216-0b957d21f377`, model `gemma-4-31b-it`, judge output (verbatim):

| claim | verdict |
|---|---|
| Petrichor là một danh từ trong tiếng Anh | Supported |
| Petrichor là danh từ không đếm được | Unsupported |
| Petrichor dùng để chỉ mùi hương đất ẩm sau cơn mưa | Supported |

| gt_key_point | covered |
|---|---|
| Petrichor là danh từ tiếng Anh | true |
| Chỉ mùi hương đất ẩm sau cơn mưa | true |
| Những nốt hương trầm lắng, ẩm ướt ẩn sâu trong lòng cỏ lá mang dư vị của mưa | false |

**H #3** – `ea82cf71-ab01-5334-96ab-e19de89500dd`, model `qwen3.5-397b-a17b`, judge output (verbatim):

| claim | verdict |
|---|---|
| Chó không thể đẻ ra mèo | Supported |
| Bộ gen và số lượng nhiễm sắc thể của chó và mèo hoàn toàn khác nhau | Supported |
| Có ghi nhận lời kể của ông Jeong Pyong-bong về việc chó sinh ra con giống mèo | Unsupported |
| Các chuyên gia khoa học thú y khẳng định chó không thể đẻ ra mèo | Supported |

| gt_key_point | covered |
|---|---|
| Chó không thể sinh ra mèo | true |
| Số lượng và đặc điểm nhiễm sắc thể ở hai loài hoàn toàn khác nhau | true |
| Những trường hợp được cho là chó sinh ra mèo có thể chỉ là chó con có ngoại hình giống mèo | false |

## Slot I. NO – mô hình bịa đáp án (≥3/4 Fabricated)

⚠️ **Không ứng viên legal nào qua hết bộ lọc** (24 legal sau lọc tự động; đa số hoặc tài liệu thực ra có đáp án, hoặc judge sai, hoặc câu hỏi mơ hồ). Hai ứng viên đầu là open domain; #3 là legal gần nhất.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Mô hình lỗi + trích nguyên văn | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `1b6b09fa-a792-5f2a-a4f7-1a05e43369e2` | open_domain | NO | năm 605 trước công nguyên thuộc thế kỷ nào | Tài liệu chỉ nhắc năm 605 TCN như mốc sự kiện (trận Carchemish, vườn treo Babylon) mà không nêu năm đó thuộc thế kỷ nào. | **1** · Đế chế Assyria - vị chúa tể trên chiến trường, ra đời và sụp đổ như thế nào? · *cùng chủ đề – Assyria, trận đánh năm 605 TCN*<br>**2** · Danh sách bảy kỳ quan thế giới cổ đại mang đậm dấu ấn kiến trúc · *cùng chủ đề – bảy kỳ quan, vườn treo Babylon "605"*<br>**3** · Bảo tàng Campuchia trưng bày ký tự số 0 cổ nhất thế giới · *nhiễu – số 0 của người Khmer; "năm 605" theo lịch khác* | NO / NO | **Qwen3-8B**: “năm 605 trước công nguyên thuộc thế kỷ thứ 6.”<br>**DeepSeek-V4-Flash**: “Năm 605 trước Công nguyên thuộc thế kỷ thứ 7 trước Công nguyên.”<br>deepseek đúng về kiến thức nhưng không có trong tài liệu; qwen3-8b sai (605 TCN thuộc thế kỷ 7 TCN).<br><sub>DeepSeek-V4-Flash: Fabricated; Qwen3.5-397B-A17B: Fabricated; Gemma-4-31B-IT: Abstained; Qwen3-8B: Fabricated</sub> | Cho thấy kiến thức nội tại rò rỉ vào câu trả lời – và một mô hình còn sai. | Khán giả có thể phản biện "chỉ là phép tính" – nhấn mạnh benchmark đo faithfulness, không phải correctness. |
| 2 | `ed50148e-0efb-5f16-aa24-27fae70a6bcb` | open_domain | NO | vgc là gì trong bối cảnh pokémon? | Tài liệu chỉ nhắc "VGC" (Wolfe Glick vô địch VGC 2016 với Rayquaza; "chuỗi trò chơi chính thức, VGC hay Pokemon GO") mà không định nghĩa VGC là gì. | **1** · 10 Pokemon hệ Rồng siêu mạnh trong thế giới Pokemon · *cùng chủ đề – danh sách hệ Rồng, nhắc VGC 2016*<br>**2** · Top 5 Pokemon hệ bay tốt nhất trong Pokemon GO · *cùng chủ đề – Pokémon GO, chỉ nêu tên VGC*<br>**3** · Switch 2: Tổng hợp tin đồn về console mới của Nintendo · *nhiễu – tin đồn Switch 2; "VGC" ở đây là tên trang tin* | NO / NO | **Qwen3-8B**: “VGC là viết tắt của "Victory Game Championship", một giải đấu lớn trong cộng đồng Pokémon, nơi các huấn luyện viên thi đấu để tranh chức vô địch.”<br>**Gemma-4-31B-IT**: “Trong bối cảnh Pokémon, VGC là nơi mà người chơi Pokémon Wolfe Glick đã sử dụng Rayquaza để giành chức vô địch thế giới vào năm 2016.”<br><sub>DeepSeek-V4-Flash: Fabricated; Qwen3.5-397B-A17B: Abstained; Gemma-4-31B-IT: Fabricated; Qwen3-8B: Fabricated</sub> | Bịa cách viết tắt rất dễ thấy; trùng tên "VGC" ở Doc 3 là bonus. | Doc 1 và 3 nhiều boilerplate shop/menu – cắt khi chiếu; tin đồn Switch 2 đã cũ. |
| 3 | `846795ae-70ee-5302-8dae-bbf0768cb332` | legal | NO | giấy khóa thuế làm thoi gian bao lâu | Tài liệu chỉ nêu thời hạn cấp giấy chứng nhận đăng ký thuế / thông báo mã số thuế (03 ngày, cấp lại 02 ngày), không có thông tin gì về "giấy khóa thuế" (đóng/chấm dứt mã số thuế). | **1** · Thời hạn cấp giấy chứng nhận đăng ký thuế là bao lâu? · *cùng chủ đề – thời hạn cấp giấy chứng nhận đăng ký thuế*<br>**2** · Thời hạn giải quyết, kết quả giải quyết hồ sơ đăng ký thuế lần đầu đối với người nộp thuế là tổ chức kinh tế, tổ chức khác? · *cùng chủ đề – thời hạn đăng ký lần đầu (tổ chức)*<br>**3** · Thời gian thông báo mã số thuế là bao nhiêu ngày? · *cùng chủ đề – thời hạn thông báo mã số thuế* | YES / NO | **DeepSeek-V4-Flash**: “Thời hạn cấp giấy chứng nhận đăng ký thuế là 03 ngày làm việc kể từ ngày nhận đủ hồ sơ.”<br>Câu này cũng xuất hiện nguyên văn trong câu trả lời của qwen3-8b; gemma = PartialSmuggle.<br><sub>DeepSeek-V4-Flash: Fabricated; Qwen3.5-397B-A17B: Fabricated; Gemma-4-31B-IT: PartialSmuggle; Qwen3-8B: Fabricated</sub> | Ví dụ legal về thay thế bằng câu hỏi lân cận (đăng ký ≠ khóa mã số thuế). | gpt_label = YES; câu hỏi khó hiểu với khán giả phổ thông. **Fails filter: query hiểu trong 5 giây (lỗi chính tả "thoi gian", thuật ngữ ít gặp "giấy khóa thuế").** |

## Slot J. PARTIAL – vi phạm phạm vi (scope violation)

⚠️ **Không ứng viên nào qua bài kiểm "cả 4 mô hình thật sự overclaim".** Chỉ 3 bản ghi qua lọc tự động có cờ scope_violation ở cả 4 mô hình, và khi đọc thì chỉ 1–3/4 thật sự overclaim (judge gắn cờ nhầm một số câu có trong tài liệu). 7 bản ghi PARTIAL có ≥3/4 vi phạm qua hết bộ lọc. Dưới đây là các ứng viên gần nhất.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | answer_with_citations (rút gọn) | gpt / gemini | Mô hình lỗi + trích nguyên văn | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `6201b226-286a-5446-a60f-9fc47cf36122` | open_domain | PARTIAL | kho ngoại quan là gì, đó là hình thức xuất khẩu? | Tài liệu chỉ định nghĩa kho ngoại quan theo Luật Hải quan 2014, hoàn toàn không nói đó có phải là một hình thức xuất khẩu hay không. | **1** · Kho ngoại quan là gì? 04 điều cần biết về kho ngoại quan · *hỗ trợ – định nghĩa khoản 10 Điều 4*<br>**2** · Kho ngoại quan là gì? Quy định về kho ngoại quan · *hỗ trợ – định nghĩa và quy định*<br>**3** · Kho ngoại quan là gì? Những quy định về kho ngoại quan · *hỗ trợ – định nghĩa và quy định* | Ngữ cảnh không đề cập việc kho ngoại quan có phải là một hình thức xuất khẩu hay không. | YES / PARTIAL | **Qwen3-8B**: “Đây là hình thức xuất khẩu thông qua việc lưu giữ hàng hóa tại kho ngoại quan trước khi xuất khẩu.”<br>**DeepSeek-V4-Flash**: “Gửi hàng vào kho ngoại quan là việc hàng hóa từ nội địa Việt Nam hoặc từ nước ngoài được đưa vào lưu giữ, không phải là hình thức xuất khẩu.”<br>qwen3.5 cũng khẳng định "không phải là hình thức xuất khẩu"; gemma-4-31b-it từ chối đúng – ba mô hình tự tin trả lời vế bị thiếu và mâu thuẫn nhau (có / không).<br><sub>DeepSeek-V4-Flash: scope_violation=true; Qwen3.5-397B-A17B: scope_violation=true; Gemma-4-31B-IT: scope_violation=false; Qwen3-8B: scope_violation=true</sub> | Ba mô hình trả lời tự tin vế không có trong tài liệu và còn mâu thuẫn nhau; gemma là đối chứng đúng. | Chủ đề hơi chuyên môn; câu "không phải" của qwen3.5 là suy luận hợp lý từ quy trình hải quan. **Fails filter: chỉ 3/4 mô hình vi phạm (gemma không).** |
| 2 | `ad67bf5b-2954-5f4d-bab9-a83705840197` | open_domain | PARTIAL | danh sách 8 tuyến và 3 monorail metro hà nội | Tài liệu liệt kê các tuyến theo quy hoạch 10 hoặc 14 tuyến và nói có 3 tuyến monorail, nhưng không có danh sách "8 tuyến" và không nêu tên 3 tuyến monorail. | **1** · Bản đồ Metro Hà Nội: Hướng dẫn di chuyển với 14 tuyến Metro · *hỗ trợ – 14 tuyến + "3 monorail" (trang SEO thuê xe)*<br>**2** · Bản đồ quy hoạch các tuyến Metro Hà Nội chi tiết nhất? · *hỗ trợ – QĐ 519/2016, 10 tuyến*<br>**3** · Bản đồ 14 tuyến Đường sắt đô thị Hà Nội và hướng tuyến · *hỗ trợ – quy hoạch 2024, 14 tuyến* | Ngữ cảnh không đề cập danh sách cụ thể của 8 tuyến metro và tên, hướng tuyến của 3 tuyến monorail. | PARTIAL / PARTIAL | **Qwen3-8B**: “8 tuyến metro Hà Nội là: tuyến 1, 2, 2A, 3, 4, 5, 6, 7. 3 tuyến monorail là: tuyến 8, 9, 10.”<br>Theo đọc của reviewer chỉ 2/4 thật sự overclaim (qwen3-8b, gemma).<br><sub>DeepSeek-V4-Flash: scope_violation=true; Qwen3.5-397B-A17B: scope_violation=false; Gemma-4-31B-IT: scope_violation=true; Qwen3-8B: scope_violation=true</sub> | qwen3-8b ép danh sách 8 + 3 tuyến từ quy hoạch 10–14 tuyến – overclaim rất dễ thấy. | Tiền đề "8 tuyến" sai làm thông điệp lẫn lộn; Doc 1 là trang SEO thuê xe. **Fails filter: chỉ 3/4 bị judge gắn cờ, 2/4 thật sự overclaim.** |
| 3 | `488c8b44-2850-5f41-950e-2acacb451b2f` | open_domain | PARTIAL | thông tin kinh tế xã hội tuần qua của vietnam | Tài liệu có bản tin tuần 20–24/10 và 19–25/10 nhưng không xác định "tuần qua" là tuần nào, và Doc 2 là trang chủ ngày 06/10/2025 với số liệu tháng 9/quý 3. | **1** · Điểm lại thông tin kinh tế tuần từ 20 - 24/10 · *hỗ trợ – điểm tin kinh tế tuần 20–24/10*<br>**2** · Nhịp sống kinh tế Việt Nam & Thế giới - VnEconomy · *hỗ trợ (yếu) – trang chủ VnEconomy 06/10/2025, nhiều boilerplate*<br>**3** · Sự kiện kinh tế Việt Nam nổi bật tuần qua · *hỗ trợ – sự kiện kinh tế nổi bật tuần qua* | Thông tin kinh tế - xã hội Việt Nam tuần qua (từ 20 - 24/10) trên thị trường trong nước ghi nhận tỷ giá trung tâm chốt ngày 24/10 ở mức 25.098 VND/USD, Ngân hàng Nhà nước bơm ròng 72.852,35 tỷ đồng qua kênh thị trường mở và chỉ số VN-Index giảm còn 1.683,18 điểm [Doc 1]. | PARTIAL / YES | **DeepSeek-V4-Flash**: “(4) GDP quý 3/2025 tăng 8,23%, GDP 9 tháng tăng 7,85%.”<br>Theo đọc của reviewer 3/4 thật sự overclaim (deepseek, qwen3.5, qwen3-8b đưa số liệu tháng 9/quý 3 vào "tuần qua"); gemma giữ trong 20–24/10.<br><sub>DeepSeek-V4-Flash: scope_violation=true; Qwen3.5-397B-A17B: scope_violation=true; Gemma-4-31B-IT: scope_violation=true; Qwen3-8B: scope_violation=true</sub> | Cơ chế overclaim "tuần qua" rõ, nhưng câu trả lời rất dài. | Tin tháng 10/2025 – đã cũ khi trình bày; câu trả lời quá dài cho slide. **Fails filter: 5. readable docs (Doc 2 là trang chủ boilerplate) và 4. neutral (Công ước LHQ, gần chính trị); 3/4 thật sự overclaim.** |

## Slot K. AMBIGUOUS – mô hình tự chọn một cách hiểu

Không trích qwen3.5 / gemma ở #1: judge chấm Committed nhưng thực ra hai mô hình này liệt kê cả 14/2 và 14/3.

| # | id | domain | label | query | Vì sao nhãn đúng | Docs (rank · title · vai trò) | gpt / gemini | Mô hình lỗi + trích nguyên văn | Phù hợp slide | Rủi ro |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 ⭐ | `07216974-614c-5867-8818-d78727c1a22e` | open_domain | AMBIGUOUS | lịch sử ngày 14 như thế nào | "Ngày 14" không nói rõ tháng: có thể là 14/2 (Valentine đỏ, gốc La Mã) hoặc 14/3 (Valentine trắng, khởi nguồn ở Nhật năm 1977), và tài liệu có lịch sử của cả hai ngày. | **1** · Ý nghĩa và nguồn gốc ngày Valentine 14/3 - Valentine trắng · *cùng chủ đề – nguồn gốc 14/3; nhiều boilerplate điều hướng*<br>**2** · Nguồn gốc và ý nghĩa của ngày lễ Giáng Sinh · *cùng chủ đề – nguồn gốc 14/2 (Thánh Valentine); tiêu đề ghi nhầm "Giáng Sinh"*<br>**3** · 14/2 là ngày gì? 14/2 là ngày của con trai hay con gái? · *cùng chủ đề – nguồn gốc 14/2 và phong tục tặng quà* | AMBIGUOUS / AMBIGUOUS | **Qwen3-8B**: “Ngày 14/2 là ngày lễ tình nhân (Valentine đỏ), bắt nguồn từ câu chuyện về Thánh Valentine, một linh mục thời La Mã cổ đại.”<br>Đối chứng: deepseek-v4-flash = Clarified.<br><sub>DeepSeek-V4-Flash: Clarified; Qwen3.5-397B-A17B: Committed; Gemma-4-31B-IT: Committed; Qwen3-8B: Committed</sub> | qwen3-8b chọn thẳng 14/2, bỏ qua 14/3 có trong tài liệu; deepseek làm rõ đúng. | Doc 2 có chi tiết về thánh tử đạo và các nước Hồi giáo cấm Valentine (gần tôn giáo) – cắt bỏ khi chiếu; Doc 1 nhiều chữ điều hướng. |
| 2 | `6a353767-3bda-5c7c-84b1-a8d2edb9417d` | open_domain | AMBIGUOUS | ok bn là ai z | "bn" có thể là "bạn" (hỏi chính trợ lý "bạn là ai") hoặc tên rapper "Binz" ("OK" còn là tên MV của Binz), nên không xác định được người hỏi đang hỏi về ai. | **1** · Rapper Binz thời chưa nổi tiếng · *cùng chủ đề – tiểu sử Binz, nhắc bài "OK"*<br>**2** · Rapper Binz và khối tài sản khủng đáng mơ ước · *cùng chủ đề – tài sản của Binz*<br>**3** · Cuộc sống như 'ông hoàng' của rapper số 1 Việt Nam Binz · *cùng chủ đề – thu nhập YouTube, MV "OK"* | YES / AMBIGUOUS | **DeepSeek-V4-Flash**: “Tôi là trợ lý trả lời câu hỏi dựa trên các tài liệu được cung cấp.”<br>**Qwen3-8B**: “Tôi là trợ lý AI được lập trình để hỗ trợ trả lời câu hỏi dựa trên các tài liệu được cung cấp.”<br>gemma-4-31b-it trả lời đúng câu như deepseek; chỉ qwen3.5 Clarified.<br><sub>DeepSeek-V4-Flash: Committed; Qwen3.5-397B-A17B: Clarified; Gemma-4-31B-IT: Committed; Qwen3-8B: Committed</sub> | 3/4 mô hình hiểu "bn" = "bạn" dù cả 3 tài liệu đều về Binz. | gpt_label = YES (gemini = AMBIGUOUS); có thể có người cho rằng "bạn" là cách hiểu chính. Doc 1–2 có tin đồn tình cảm (Châu Bùi). |
| 3 | `c6c0f7d6-3e67-5dcf-8b72-63e4d9f94e4f` | open_domain | AMBIGUOUS | khi nào cần tìm ai để hỏi | Chữ "ai" viết thường có thể là đại từ "ai" (khi nào cần tìm một người/chuyên gia để hỏi) hoặc "AI" (khi nào nên hỏi trí tuệ nhân tạo) – hai cách hiểu dẫn tới hai câu trả lời khác hẳn nhau. | **1** · Ngày càng nhiều thông tin sai, có nên tìm kiếm, hỏi AI? · *cùng chủ đề – khi nào câu trả lời của AI sai, cần kiểm chứng (chỉ hợp cách hiểu "AI")*<br>**2** · Một số câu hỏi thường gặp về trí tuệ nhân tạo \| Báo Nhân Dân điện tử · *cùng chủ đề – FAQ về AI, có header/footer boilerplate*<br>**3** · Muốn sử dụng AI, bắt đầu từ đâu? · *cùng chủ đề – bắt đầu học AI* | AMBIGUOUS / AMBIGUOUS | **Qwen3-8B**: “Khi thông tin đầu vào sai hoặc yêu cầu AI phản biện, cần tìm người có kiến thức chuyên môn để xác minh sự thật.”<br>3 mô hình còn lại Clarified.<br><sub>DeepSeek-V4-Flash: Clarified; Qwen3.5-397B-A17B: Clarified; Gemma-4-31B-IT: Clarified; Qwen3-8B: Committed</sub> | qwen3-8b chọn nghĩa "ai" = người; chỉ dùng nếu F lấy bản ghi khác. | Câu trả lời pha trộn cả hai cách hiểu nên "commit" kém rõ; trùng top pick F. |

## Top picks

| Slot | Mục đích | id | query | label | chủ đề | lý do chọn |
|---|---|---|---|---|---|---|
| A | YES, open domain – ba vai trò tài liệu | `612dad5c-9c70-58f5-85e9-6143dadf2b0f` | dưa hấu giả là gì ? | YES | thực phẩm (dưa hấu) | Câu hỏi 5 từ; ba vai trò rõ như sách giáo khoa; bẫy "làm giả" ở Doc 2 hiểu ngay. Bonus: deepseek-v4-flash từ chối sai, qwen3-8b kéo nội dung Doc 2/3 vào thành "các loại". |
| B | YES, legal – thủ tục đời thường | `1b8df05b-e97d-5cef-9ac7-dce5fd3d2744` | ứng dụng định danh quốc gia tải ở đâu | YES | VNeID / định danh điện tử | Ai trong phòng cũng đã dùng VNeID; đáp án 1 dòng; Doc 1 là "near-miss" đẹp (nhắc tải nhưng không nói ở đâu). Cả 4 mô hình trả lời đúng. |
| C | PARTIAL – tài liệu chỉ trả lời một phần | `ce335062-4957-5f3c-a7b0-539ea7c8e9cb` | giá của hoa tươi trong dịp 8/3 và 20/10 là bao nhiêu? | PARTIAL | hoa / quà tặng | Câu hỏi hai vế, một vế có, một vế không – phần thiếu nói trong một câu; cả 4 mô hình đều nêu đúng phần thiếu (đối chiếu đẹp với slot J). |
| D | NO, legal – đúng chủ đề nhưng thiếu con số / chủ thể | `a71f9525-32df-413d-a4a6-3eac477ca213` | làm số nhà ở thành phố hồ chí minh mất bao nhiêu tiền | NO | số nhà | Ca "bao nhiêu tiền?" sạch: tài liệu cứ nói "phí theo quy định" mà không có con số; cả 4 mô hình đều từ chối đúng. |
| E | NO, open domain – chủ đề đời thường | `785f0620-3873-5516-8044-202559267af6` | thời gian bay từ vienna, áo đến bắc kinh là bao lâu? | NO | du lịch / chuyến bay | Có đủ hai "nửa" của hành trình nhưng không có tổ hợp cần hỏi – rất trực quan; cả 4 mô hình từ chối đúng. |
| F | AMBIGUOUS – nhiều cách hiểu | `c6c0f7d6-3e67-5dcf-8b72-63e4d9f94e4f` | khi nào cần tìm ai để hỏi | AMBIGUOUS | AI / chơi chữ | 7 từ, trò chơi chữ ai/AI hiểu ngay; cả gpt_reason và gemini_reason đều nêu đúng hai cách hiểu. |
| G | Hard subset – LLM pre-label YES, người gán NO | `c22e81f9-a893-55ca-898f-46a863be3e96` | có thể hủy thẻ tín dụng online tại ngân hàng acb không? | NO | ngân hàng / thẻ tín dụng | Near-miss kép: thao tác (gia hạn online ≠ hủy online) và phạm vi ("một số ngân hàng" ≠ ACB) – trông trả lời được, nhưng NO hiển nhiên khi chỉ ra. Nhãn sạch (raw_agreement). |
| H | Claim decomposition – mệnh đề & ý chính | `6b3d3408-26af-5da5-bd01-4201038c697c` | số hữu tỉ là gì ? | YES | toán học | Tham chiếu 1 câu / 2 ý chính, câu trả lời 1 câu / 4 mệnh đề – tính 3/4 và 1/2 ngay trên slide. |
| I | NO – mô hình bịa đáp án (≥3/4 Fabricated) | `1b6b09fa-a792-5f2a-a4f7-1a05e43369e2` | năm 605 trước công nguyên thuộc thế kỷ nào | NO | lịch sử | Cho thấy kiến thức nội tại rò rỉ vào câu trả lời – và một mô hình còn sai. |
| J | PARTIAL – vi phạm phạm vi (scope violation) | `6201b226-286a-5446-a60f-9fc47cf36122` | kho ngoại quan là gì, đó là hình thức xuất khẩu? | PARTIAL | hải quan / logistics | Ba mô hình trả lời tự tin vế không có trong tài liệu và còn mâu thuẫn nhau; gemma là đối chứng đúng. |
| K | AMBIGUOUS – mô hình tự chọn một cách hiểu | `07216974-614c-5867-8818-d78727c1a22e` | lịch sử ngày 14 như thế nào | AMBIGUOUS | lễ Valentine | qwen3-8b chọn thẳng 14/2, bỏ qua 14/3 có trong tài liệu; deepseek làm rõ đúng. |

### Note on topic variety
- No topic appears in more than 2 slots among the top picks.
- No top pick is about football, since Manchester United is already in the deck.
- VNeID appears only in B (#1 and #3 are both candidates; use only one).
- The CCCD record in D (#3) is not a top pick.

### Data issues found while reading (worth noting in the thesis)
- **G (hard subset):** many records labelled NO have docs that actually contain the answer. Examples: 3a9b20ec, 0a5d305e, 588b990d, c9f84e79, 6bb36461, f25184b0, bf30327c, 3205b080, d5070bf1, ad11a331, b1b25cff, 4ec6fe26. In these cases the LLM pre-labels (YES) look more correct than the human labels.
- **I (legal):** of the 24 legal candidates, many records judged "Fabricated" have docs that actually contain the answer (b88f25b8, 26f355ad, 0e7f0a75, c27f2198, 7d884dcf, 854b4ce4), or the judge got it wrong (826af88e).
- **J / K:** the judge flags `scope_violation` and `Committed` too readily. Some flagged claims are actually in the docs, and some answers marked Committed actually list both readings (07216974: qwen3.5, gemma).
- **H:** claims are judged against the reference answer, not the docs, so "Unsupported" often means "outside the reference", not "fabricated".
- **Outdated legal facts:** several legal YES records rely on superseded rules, e.g. the 2014 CCCD law and Thông tư 12/2017 (82b952a7, 5ee3dd73, fecc6627). Driving licences moved to the police in 3/2025.
