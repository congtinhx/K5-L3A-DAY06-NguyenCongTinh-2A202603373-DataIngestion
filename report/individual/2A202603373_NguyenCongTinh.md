# Báo cáo cá nhân — Day 6 — Nguyễn Công Tĩnh (2A202603373)


## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** World Bank, *World Development Report 2024: The Middle-Income Trap*, trích Part 1 (trang in 31–78), doi:10.1596/978-1-4648-2078-6, giấy phép **CC BY 3.0 IGO** (in ở trang 1 của PDF). PDF có 44 trang vật lý. Bỏ trang 1 (trang bản quyền) → ingest 43 trang. Quy tắc tính: trang còn ≥ 1000 ký tự sau chuẩn hóa và sau khi cắt Notes/References → **41 trang nội dung**. Trang 16 và 44 chủ yếu là Notes nên không tính. Chi tiết: `data/manifest.csv`, `results/page_stats.csv`.
- **Chuẩn hóa, lỗi và giới hạn:**
  - Unicode NFKC, gộp khoảng trắng.
  - Xóa ký tự điều khiển. Lỗi gặp thật khi chạy: pypdf trả về ký tự NUL `0x00` ở trang 40, PostgreSQL từ chối ghi (`text fields cannot contain NUL`). Đã sửa ở bước chuẩn hóa và ghi log `CONTROL_CHARS_REMOVED`.
  - Bỏ header/footer chạy trang (vd `34 | world develo Pment re Port 2024`), đồng thời đọc số trang in từ header. Bỏ dòng chỉ chứa số (nhãn trục biểu đồ).
  - Nối từ bị ngắt dòng dựa trên từ điển của chính tài liệu: `interna-tional` → `international`, giữ `middle-income`.
  - Cắt phần Notes cuối chương (trang 16, 44).
  - Log: `results/ingest_errors.log` (4 dòng: 1 SKIPPED, 2 NOTES_REMOVED, 1 CONTROL_CHARS_REMOVED).
  - Giới hạn: vẫn sót vài từ ngắt dòng khi từ ghép không xuất hiện ở chỗ khác (`combin-ing`, `mir-acle`); lỗi khoảng trắng của PDF (`middle- inco me`); chữ trích từ hình ảnh vẫn lọt vào (trang 28: "The time, manner and drawing…"); chú thích/trục biểu đồ trích thành chữ rời rạc (vd chunk B trang 11 bắt đầu bằng nhãn trục Figure 1.3); B có 1 chunk rất ngắn (9 ký tự, tiêu đề bảng không gộp được vì chunk kế tiếp đã gần 1000 ký tự).
- **Embedding, vector store, metric, lệnh chạy, chi phí:** `intfloat/multilingual-e5-small` qua sentence-transformers 6.3.0, chạy local CPU, **384 chiều**, max 512 token, tiền tố `query:` / `passage:`, vector chuẩn hóa độ dài 1. Không có fallback vector giả: lỗi thì dừng. Vector store: **PostgreSQL 16.16 + pgvector 0.8.7** (Docker `pgvector/pgvector:0.8.7-pg16`), cosine distance `<=>`, exact search (không dùng index ANN, vì chỉ 434 vector). Lệnh: `python -m src.run ingest | evaluate | reingest-check`. Thời gian lần nạp đầy đủ (`results/ingest_stats_full_run.json`): đọc + chuẩn hóa 14,95 s; embed + lưu A **38,66 s**, B **51,84 s**; tổng 166,5 s (gồm cả tải model). Chi phí **$0** (không gọi API). Thời điểm chạy (giờ +07): ingest đầy đủ 2026-11-14 00:52, evaluate 00:55, reingest-check 00:57. Phiên bản: Python 3.14, pypdf 6.21.4, psycopg 3.3.8, torch 2.15.0, sentence-transformers 6.3.0 (đầy đủ trong `results_pip_freeze.txt`). Không cần seed vì suy luận embedding là tất định. Khởi tạo store: `docker compose -p day6_student_starter up -d --wait` (cổng 127.0.0.1:55433, DB `day6_lab`, volume lưu bền `day6_student_starter_pg_data`); bảng `chunks` được tạo bằng `PgVectorStore.create_schema()`, gồm cột `embedding vector(384)` và index B-tree `(strategy, section)`.
- **Metadata:**
  - Bắt buộc: `document_id` (TEXT), `source` (TEXT, đường dẫn file), `page` (INTEGER, trang PDF đếm từ 1).
  - Bổ sung: `printed_page` (INTEGER, đọc từ header), `char_start` / `char_end` (INTEGER, vị trí trong trang, dùng để chọn mẫu coherence), và **`section`** (TEXT) làm trường lọc.
  - Giá trị `section`: `part1_overview`, `ch1_slowing_growth`, `spotlight`, `ch2_structural_stasis`, `ch3_shrinking_spaces`. Ranh giới lấy từ trang mở đầu chương trong PDF (trang 4 "1 Slowing Growth", 17 "Spotlight", 21 "2 Structural Stasis", 35 "3 Shrinking Spaces").
  - Lý do chọn `section`: tài liệu chia chương rõ, và nhiều chủ đề (Korea, năng lượng, tỷ lệ dân số, chuyển lên thu nhập cao) lặp lại ở nhiều chương.

## Cấu hình và benchmark
- **A / B / C:**
  - **A**: fixed-size 500 ký tự, overlap 50 → 277 chunk. Độ dài min/trung vị/TB/max = 52 / 500 / 462,1 / 500 ký tự; tổng 127.998 ký tự (lớn hơn văn bản gốc vì có overlap).
  - **B**: gom câu liên tiếp ≤ 1000 ký tự, không cắt giữa câu; dòng Box/Figure/Table/Key messages mở chunk mới; chunk < 200 ký tự được gộp → 157 chunk. Độ dài min/trung vị/TB/max = 9 / 850 / 740,5 / 999 ký tự; tổng 116.251 ký tự. Văn bản sau chuẩn hóa có 116.365 ký tự; không tính token vì không dùng API tính phí.
  - **C**: **dùng chung index của B** (cùng chunk, cùng vector), thêm lọc `section` trong SQL khi câu hỏi có filter. **Khác biệt duy nhất giữa B và C là filter.**
  - Cả ba dùng cùng corpus, cùng model, cùng vector store, cùng top-3 và cùng vector câu hỏi.
  - Chunk ID ổn định (`B:wdr2024_part1:p025:c001`) + `INSERT … ON CONFLICT DO UPDATE` + `content_hash` → nạp lại không trùng: `results/reingest_check.json` (A 277→277, B 157→157, embed lại 0 chunk, `no_duplicates: true`). **Khi tài liệu thay đổi:** chunk có `content_hash` khác sẽ được embed lại và cập nhật tại chỗ; chunk_id không còn trong tài liệu bị xóa (`DELETE … WHERE NOT chunk_id = ANY(...)`); chunk không đổi được bỏ qua.
- **Benchmark (`benchmark/questions.json`):** 22 câu, chia **16 dev / 6 test** trước khi chạy. Các loại câu: trực tiếp, diễn đạt lại (paraphrase), có điều kiện, có filter. **4 câu filter**: q10, q14 (dev), t03, t05 (test). Mỗi câu có `gold_page` + `evidence_quote`; 4 câu có `alt_gold` khi cùng thông tin xuất hiện ở nhiều trang. Kiểm chứng: `scripts/verify_benchmark.py` xác nhận cả 28 evidence nằm đúng trang (so khớp chỉ chữ và số, bỏ qua lỗi khoảng trắng/gạch nối của PDF). Một kết quả chỉ được tính **hit** khi chunk **đúng trang VÀ chứa đủ evidence**; đúng trang nhưng thiếu evidence được ghi là `page_only`.
- **Filter:** giá trị `section` là **input giả định được cung cấp trước khi truy xuất**: ngữ cảnh chương nằm sẵn trong câu hỏi ("In the Structural Stasis chapter…") và được ghi ở trường `filter` của câu. Filter không được suy ra từ gold page. C chỉ áp filter cho 4 câu có filter; 18 câu còn lại C chạy không lọc (`applied_filter: null` trong trace).
- **Tiêu chí chọn chiến lược (chốt trước khi chạy, `benchmark/selection_criteria.md`):** (1) Evidence Hit@3 dev cao nhất; (2) hòa → Hit@1 dev; (3) hòa → ít chunk hơn.

## Kết quả
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian embed+store | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 12/16 | 12/16 | 277 | 38,66 s | $0 |
| A | test | 3/6 | 4/6 | 277 | 38,66 s | $0 |
| B | dev | 13/16 | 15/16 | 157 | 51,84 s | $0 |
| B | test | 3/6 | 5/6 | 157 | 51,84 s | $0 |
| C | dev | 13/16 | 15/16 | 157 (chung với B) | 51,84 s (chung với B) | $0 |
| C | test | 3/6 | 5/6 | 157 (chung với B) | 51,84 s (chung với B) | $0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,90 (10) | 18/18 | dev 1/2, test 1/2 | 0/0/6 — 2,00 |
| B | 1,70 (10) | 18/18 | dev 1/2, test 1/2 | 1/0/5 — 1,67 |
| C | 1,70 (10, chung chunk B) | 18/18 | dev 2/2, test 2/2 | 1/0/5 — 1,67 |

**Đường dẫn và cách chọn mẫu:**
- Trace top-3: `results/traces_{A,B,C}.jsonl`. Tổng hợp: `results/summary.md`, `results/summary.json`.
- Nhãn tay:
  - `results/audit_coherence.csv`: 10 vị trí cố định, là điểm giữa của 10 trang nội dung đầu tiên (trang 2–11), chọn bằng code trước khi chấm. Mỗi vị trí lấy chunk chứa nó ở từng chiến lược.
  - `results/audit_metadata.csv`: 6 câu test × top-3 × 3 chiến lược = 54 dòng (37 chunk khác nhau). Đối chiếu với text gốc của trang PDF, trang mở đầu chương và số trang in ở header.
  - `results/audit_grounding.csv`: 6 câu test × 3 chiến lược, chỉ dựa vào 3 đoạn truy xuất.
  - Tổng hợp nhãn: `results/manual_summary.md`.
- **Ghi chú chạy lại:** `evaluate` đã chạy 2 lần với cùng cấu hình. Lần 2 diễn ra sau khi xóa bảng và nạp lại, để cột thời gian ghi đúng lần nạp đầy đủ (lần đầu đã bị ghi đè bởi `reingest-check`). Hit@1/Hit@3 giữ nguyên. Không chỉnh tham số nào theo kết quả test.

## Phân tích và kết luận
- **A–B (chỉ đổi cách chunk):**
  - B hơn A về Evidence Hit@3: dev 15/16 so với 12/16, test 5/6 so với 4/6, với **ít hơn 43% chunk** (157 so với 277). Bù lại, thời gian embed của B lâu hơn (51,8 s so với 38,7 s), có thể do mỗi chunk dài hơn nên tốn nhiều token/phép tính hơn.
  - Cả 4 câu dev A trượt (q04, q07, q09, q13) đều có kết quả `page_only`: đúng trang nhưng **câu bằng chứng bị cắt đôi ở ranh giới 500 ký tự**. Ví dụ q07: chunk hạng 1 bắt đầu bằng "…rom 0.5 percent of GDP in 1980", còn hạng 2 kết thúc ở "…to 1.6 percent in 1".
  - Coherence phản ánh đúng điều này: A 0,90/2 (gần như mọi chunk A bị cắt giữa từ ở hai đầu), B 1,70/2.
- **B–C (chỉ đổi filter):**
  - Hit@1 và Hit@3 giống hệt. Khác biệt là **tuân thủ filter**: 1/2 → 2/2 ở cả dev và test.
  - Ví dụ t03 (filter chương 3): top-3 của B có 1 đoạn từ trang 20 (Spotlight); C thay bằng đoạn trang 35 (chương 3).
  - Filter không tăng Hit, vì ở các câu filter, chunk đúng vốn đã nằm trong top-3, hoặc chunk gây nhiễu cùng chương với chunk đúng.
- **Chấm tự động và chấm tay lệch nhau (grounding):**
  - Theo grounding thủ công, **A đạt 6/6 câu test đủ bằng chứng (2,00)**, cao hơn B/C (1,67). Ngược lại, Evidence Hit@3 tự động của A chỉ 4/6.
  - Lý do: ở t02 và t03, chunk của A **có chứa đáp án** nhưng evidence bị cắt mất 1–2 ký tự ở ranh giới ("**e** costs associated with…", "…about double that in high-income **co**"), nên phép so khớp chặt tính là trượt.
  - Kết luận: Evidence Hit@3 chặt là thước đo "chunk có giữ trọn câu không", còn grounding đo "người đọc có trả lời được không". Hai chỉ số này cần đọc cùng nhau.
- **Ví dụ sai 1 — q14 (dev, gold trang 25):**
  - A trúng hạng 1. B và C trượt: hạng 1 **đúng trang 25** nhưng `page_only`. Chunk bắt đầu từ câu "Specifically, firms received tax credits for royalty payments or R&D expenditures…", còn câu evidence "Korea subsidized the adoption of foreign technologies and innovation through tax credits" nằm ở **cuối chunk trước** (ranh giới gom câu rơi giữa hai câu liền nhau). Chunk trước đó dài và nhiều nội dung khác nên không lọt top-3.
  - Filter của C không cứu được, vì cả chunk đúng lẫn chunk nhiễu đều ở chương 2. Hạng 2 còn là chữ rác trích từ hình ảnh (trang 28).
- **Ví dụ sai 2 — t04 (test, gold trang 33):**
  - A trúng hạng 1 (chunk 500 ký tự tập trung quanh câu "82 percent of the transitions…").
  - B và C trượt hoàn toàn: top-3 đến từ trang 5, 3, 6 (đoạn tổng quan lặp lại cụm "transitioned to high-income status"), grounding = 0.
  - Chunk B ở trang 33 dài gần 1000 ký tự, phần lớn về định nghĩa "investment acceleration", nên câu số liệu bị **loãng** trong vector của cả chunk.
  - Đây là **đánh đổi** của chunk lớn: giữ trọn câu (cứu q04/q07/q09/q13) nhưng làm chìm câu chứa con số cụ thể.
- **Chiến lược chọn:**
  - Theo tiêu chí đã chốt: A bị loại ở tiêu chí 1. **B và C hòa cả 3 tiêu chí** (15/16; 13/16; 157 chunk).
  - Tiêu chí phụ **bổ sung sau khi thấy hòa** (ghi rõ để minh bạch): tuân thủ filter trên dev, C 2/2 so với B 1/2 → chọn **C**.
  - Điều kiện áp dụng: tài liệu có cấu trúc chương rõ, và câu hỏi mang ngữ cảnh chương đáng tin. Nếu filter sai chương, C sẽ loại mất kết quả đúng.
  - Với câu hỏi về con số cụ thể nằm trong đoạn dài, chunk nhỏ kiểu A lại có lợi (t04).
- **Hạn chế:**
  - Test chỉ 6 câu: chênh lệch 4/6 và 5/6 là **1 câu**, nên không khái quát được ngoài tài liệu này.
  - Chỉ 1 tài liệu, tiếng Anh.
  - Câu hỏi và nhãn có AI hỗ trợ soạn nháp; nhãn do 1 người rà soát, chưa đo độ đồng thuận giữa người chấm.
  - t05 (test) dùng chung trang 4/5 với q01/q02 (dev) → nguy cơ rò rỉ chủ đề.
  - Metadata được kiểm bằng đối chiếu text trang gốc và mở PDF xác nhận trang mở chương, không đọc tay từng dòng.
  - Thời gian đo một lần trên CPU một máy; tổng thời gian gồm cả tải model.
  - Exact search nên chưa đo hiệu năng index ANN.
- **Nếu làm lại / mở rộng:**
  - Thêm tài liệu và tăng tập test (≥ 20 câu).
  - Thử `max_size` 600–800 cho B, chỉnh trên dev.
  - Cho phép chunk B chồng lấn 1 câu để evidence không rơi đúng ranh giới.
  - Hybrid BM25 + vector cho câu chứa số liệu.
  - Lọc chữ trích từ hình ảnh và chú thích biểu đồ.
  - Thêm index HNSW khi dữ liệu lớn.
  - Đo grounding bằng hai người chấm độc lập.

### Minh bạch về việc sử dụng AI

Trong quá trình thực hiện Day 6, tôi sử dụng Claude (Anthropic) như một công cụ hỗ trợ phát triển và rà soát. Cụ thể, AI hỗ trợ đề xuất một số đoạn code cho pipeline, xây dựng bản nháp 22 câu benchmark và đề xuất nhãn đánh giá ban đầu cho các tiêu chí coherence, metadata và grounding.

Tôi trực tiếp triển khai, chạy thử pipeline trên máy cá nhân, kiểm tra kết quả trong thư mục `results/`, đối chiếu metadata với nội dung PDF gốc và rà soát các nhãn đánh giá trước khi sử dụng. Các nhãn có tiền tố `[Claude cham nhap, hoc vien ra soat]` trong các file `results/audit_*.csv` để phân biệt rõ phần AI đề xuất và phần học viên đã kiểm tra.

**Hạn chế và nguy cơ thiên lệch:** Do AI hỗ trợ cả quá trình xây dựng pipeline và đề xuất nhãn đánh giá, có nguy cơ xuất hiện thiên lệch trong thiết kế và đánh giá. Ngoài ra, bộ nhãn chưa được kiểm chứng bởi người chấm thứ hai độc lập. Vì vậy, tôi không xem các nhãn này là kết quả đánh giá độc lập tuyệt đối; tôi chịu trách nhiệm về việc kiểm tra, điều chỉnh và giải trình các kết quả cuối cùng.