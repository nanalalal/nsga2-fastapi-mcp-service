# Kế hoạch công việc chi tiết: Ghép FastAPI + MCP Server (kèm Docker) cho đồ án NSGA-II + SUMO

Tài liệu này là bản tiếp nối `HUONG_DAN_TICH_HOP.md` (đã gửi ở phiên trước) — thay vì mô tả quy trình ở mức khái niệm, tài liệu này chia nhỏ thành từng công việc cụ thể, có phụ thuộc, ước lượng thời gian, tiêu chí hoàn thành, và ghi rõ việc nào **đã làm và đã kiểm thử tự động trong phiên làm việc này**, việc nào **bạn cần tự làm trên máy có SUMO/Docker thật**. Kèm theo là bản cập nhật của `mcp_server/server.py` (tuân theo chuẩn thiết kế MCP server của `mcp-builder`) và bộ file Docker mới.

## 0. Việc đã hoàn thành và đã kiểm thử trong phiên này

Trước khi liệt kê việc còn lại, cần nói rõ những gì KHÔNG còn là rủi ro nữa — để bạn không mất thời gian kiểm tra lại từ đầu.

Toàn bộ chuỗi `nsga2_core.run_optimization()` → `core.jobs.JobManager` → `api.main` (FastAPI) → `mcp_server.server` đã được chạy **thực sự** (không chỉ kiểm tra cú pháp) bằng một `FakeSUMOEvaluator` giả lập SUMO (`tests/fake_evaluator.py`), và bộ 5 test tích hợp trong `tests/test_jobs.py` **chạy PASS 5/5**: tạo job và chờ hoàn thành, huỷ job đang chờ, gọi endpoint FastAPI (`/scenarios`, `POST /jobs`, `GET /jobs/{id}/pareto`), và gọi trực tiếp 2 tool MCP (`nsga2_list_scenarios`, `nsga2_start_optimization`, `nsga2_get_pareto_front`).

Quá trình chạy test đã **phát hiện và sửa một lỗi thật**: nếu một job bị huỷ (`nsga2_cancel_job`) ngay khi còn "pending" — trước khi thuật toán chạy dù chỉ một thế hệ — `algorithm.n_gen` của pymoo vẫn là `None`, khiến bước vẽ biểu đồ (`plot_results`) crash với `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`. Đã sửa bằng cách: `core/jobs.py` giờ chỉ gọi `save_results()` khi có ít nhất 1 generation đã chạy (`len(result.history_df) > 0`); `nsga2_core.save_results()` giờ raise `ValueError` rõ ràng thay vì để lỗi mù mờ lan ra nếu lỡ gọi sai. Đây là lý do nên **giữ nguyên** `tests/test_jobs.py` trong dự án của bạn — nó là bằng chứng sống cho việc refactor không phá vỡ hành vi gốc.

`mcp_server/server.py` đã được viết lại theo đúng checklist của `mcp-builder` (chi tiết ở Mục 3): đổi tên server thành `nsga2_mcp`, đổi tên tất cả tool sang dạng `nsga2_{action}`, thêm Pydantic input model cho từng tool, thêm `annotations` (`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`), viết docstring đầy đủ theo mẫu chuẩn (Args/Returns/Examples/Error Handling), và hỗ trợ cả hai transport (`stdio` mặc định, `--http` cho kịch bản Docker).

Điều **CHƯA** kiểm thử được trong môi trường này (không có SUMO/Docker): chạy với `SUMOEvaluatorImproved` thật (cần SUMO binary), build Docker image (cần tải gói SUMO qua APT trong quá trình build), và chạy MCP server qua transport `streamable-http` với client thật. Ba việc này nằm trong Mục 2 (M3, M4) — bạn cần tự chạy trên máy của mình.

## 1. Bảng milestone tổng quan

| Mã | Milestone | Trạng thái | Việc chính |
|---|---|---|---|
| M0 | Refactor lõi thuật toán | ✅ Xong, đã test | Tách `run_optimization()` khỏi CLI |
| M1 | FastAPI service | ✅ Xong, đã test (fake evaluator) | REST API + JobManager |
| M2 | MCP server chuẩn mcp-builder | ✅ Xong, đã test (fake evaluator) | Đổi tên tool, annotations, docstring |
| M3 | Kiểm thử với SUMO thật | ⬜ Bạn cần làm | Chạy 1 job thật, đối chiếu kết quả với CLI gốc |
| M4 | Đóng gói Docker | ⬜ Bạn cần làm | Build image, chạy `docker compose up` |
| M5 | Vận hành & tài liệu | ⬜ Bạn cần làm | README service, biến môi trường, bàn giao |
| M6 (tuỳ chọn) | Mở rộng | ⬜ Chưa cần ngay | State dùng chung, SSE, resume-from-checkpoint |

## 2. Work Breakdown Structure chi tiết

Ký hiệu ước lượng thời gian tính cho một người làm một mình, đã quen với project (không tính thời gian học SUMO/FastAPI/Docker từ đầu).

### M0 — Refactor lõi thuật toán (✅ đã xong)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M0-1 | Tách `run_optimization()`/`save_results()` khỏi `run_nsga2_v2.py` | — | `src_patch/nsga2_core.py` | Đã xong | Chạy được với evaluator giả, output giống cấu trúc CSV gốc |
| M0-2 | Copy `nsga2_core.py` vào `D:\DoAn_NSGA2_SUMO\src\` | M0-1 | File tồn tại trong `src/` | 5 phút | `python -c "import nsga2_core"` chạy trong đúng thư mục không lỗi |
| M0-3 | **[CHẶN M4]** Sửa `config.py` bỏ hardcode đường dẫn Windows tuyệt đối | — | `config.py` dùng đường dẫn tương đối | 15 phút | Tham khảo `docker/config_patched_example.py` đi kèm; CLI gốc (`python run_nsga2_v2.py --scenario S1 ...`) vẫn chạy đúng sau khi sửa |
| M0-4 (tuỳ chọn) | Thay `run_nsga2_v2.py` bằng bản thin wrapper | M0-1 | `run_nsga2_v2.py` gọi `run_optimization()` | 15 phút | Output CLI giống hệt trước khi đổi (so sánh CSV) |

M0-3 được đánh dấu **CHẶN M4** vì Docker chạy Linux — đường dẫn kiểu `D:\DoAn_NSGA2_VISSIM\...` không tồn tại trong container, image sẽ crash ngay khi gọi `SUMOEvaluatorImproved` nếu chưa sửa.

### M1 — FastAPI service (✅ đã xong, đã test với evaluator giả)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M1-1 | `core/bootstrap.py` — nối `sys.path` tới `src/` gốc qua biến môi trường | M0-1 | File đã có | Đã xong | `setup_project_path()` raise lỗi rõ ràng nếu thiếu biến môi trường |
| M1-2 | `core/jobs.py` — `JobManager` (hàng đợi tuần tự, 1 worker) | M1-1 | File đã có | Đã xong | 5/5 test trong `tests/test_jobs.py` pass |
| M1-3 | `api/schemas.py` — Pydantic request/response | — | File đã có | Đã xong | — |
| M1-4 | `api/main.py` — 7 endpoint (`/scenarios`, `/jobs`, `/jobs/{id}`, `/jobs/{id}/cancel`, `/jobs/{id}/pareto`, `/jobs/{id}/plot`, `/health`) | M1-2, M1-3 | File đã có | Đã xong | `TestClient` gọi được, trả đúng status code |
| M1-5 | Chạy thử `uvicorn api.main:app --reload` với SUMO thật, 1 job nhỏ (`pop_size=6, n_gen_max=2`) | M0-3, M1-4 | Log chạy thành công | 20-30 phút (chờ SUMO) | `GET /jobs/{id}` cuối cùng trả `status=done`, có `csv_path`/`plot_path` hợp lệ |
| M1-6 (tuỳ chọn) | Thêm xác thực API key nếu định expose ra ngoài `localhost` | M1-4 | Middleware FastAPI | 30-60 phút | Request thiếu key bị từ chối 401 |

### M2 — MCP server chuẩn mcp-builder (✅ đã xong, đã test với evaluator giả)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M2-1 | Đổi tên server thành `nsga2_mcp`, tool thành `nsga2_{action}` | — | `mcp_server/server.py` | Đã xong | Không còn tên tool trùng khả năng đụng độ với MCP server khác |
| M2-2 | Pydantic input model cho mỗi tool (`extra="forbid"`, `Field(..., description=...)`) | M2-1 | Đã có (`StartOptimizationInput`, `JobIdInput`, `GetParetoFrontInput`) | Đã xong | Gọi tool với field thừa bị từ chối (Pydantic validation) |
| M2-3 | `annotations` cho từng tool (`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`) | M2-1 | Đã có | Đã xong | Xem bảng đối chiếu ở Mục 3 |
| M2-4 | Docstring đầy đủ (Args/Returns schema/Examples/Error Handling) | M2-1 | Đã có | Đã xong | LLM client đọc docstring là đủ hiểu cách dùng, không cần hỏi lại |
| M2-5 | Response format nhất quán (`json.dumps(..., ensure_ascii=False)`, lỗi dạng `"Error: ..."`) | M2-1 | Đã có | Đã xong | Không raise exception thô ra ngoài tool |
| M2-6 | Hỗ trợ 2 transport: `stdio` (mặc định) và `--http` (Streamable HTTP) | M2-1 | Đã có (`main()` với `argparse`) | Đã xong | `python server.py --help` chạy không lỗi |
| M2-7 | Khai báo trong Claude Desktop/Claude Code (`.mcp.json`) | M2-6 | Cấu hình MCP client | 10 phút | Claude liệt kê được 6 tool `nsga2_*` khi hỏi "bạn có tool gì" |
| M2-8 | Test bằng MCP Inspector (`npx @modelcontextprotocol/inspector`) | M2-6 | Log kiểm thử | 20 phút | Gọi thử `nsga2_list_scenarios` qua Inspector UI, thấy đúng JSON |
| M2-9 | Chạy bộ eval 6 câu hỏi (`mcp_server/evaluation.xml`) | M2-8 | Kết quả eval | 15 phút | LLM trả lời đúng cả 6 câu (dữ liệu tĩnh từ `config.SCENARIOS`, không phụ thuộc ngẫu nhiên) |

### M3 — Kiểm thử với SUMO thật (⬜ bạn cần làm trên máy có SUMO)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M3-1 | Cài `requirements_service.txt` lên môi trường conda hiện có | M0 | `pip install` thành công | 10 phút | `python -c "import fastapi, mcp"` không lỗi |
| M3-2 | Chạy `pytest tests/test_jobs.py -v` với `NSGA2_PROJECT_SRC` trỏ đúng | M1, M2 | 5/5 test pass trên máy bạn | 10 phút | Kết quả giống phiên làm việc này (đã pass ở đây với Python 3.11 + pymoo 0.6.2) |
| M3-3 | Chạy 1 job thật qua API (`pop_size=8, n_gen_max=2`, kịch bản S1) | M1-5 | CSV + PNG trong `results_service/<job_id>/` | 5-15 phút | Số cột CSV, tên cột khớp với CSV do CLI gốc sinh ra |
| M3-4 | Đối chiếu: chạy CÙNG tham số bằng CLI gốc (`run_nsga2_v2.py --scenario S1 --pop_size 8 --n_gen_max 2`, cùng seed) | M3-3 | 2 file CSV để so sánh | 5-15 phút | Kết quả **giống hệt** nhau (cùng seed=42 cố định trong `run_optimization`) — xác nhận refactor không đổi thuật toán |
| M3-5 | Chạy 1 job đầy đủ qua MCP từ Claude Desktop/Code, theo dõi tới khi `done` | M2-7 | Hội thoại mẫu | Vài giờ (chạy nền, không cần ngồi canh) | `nsga2_get_pareto_front` trả về nghiệm hợp lý (so khớp khoảng giá trị với `results/pareto_final_S1.csv` gốc trong README) |

### M4 — Đóng gói Docker (⬜ bạn cần làm, file scaffold đã có nhưng CHƯA build-test)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M4-1 | Sửa `config.py` (M0-3) — **bắt buộc trước khi build** | M0-3 | — | — | — |
| M4-2 | Chạy `docker/prepare_context.ps1` để copy `src/` + 3 thư mục `sumo_model_s*` vào `docker/` | M4-1 | `docker/project_src/`, `docker/sumo_model_s1..3/` tồn tại | 5 phút | `docker/project_src/config.py` không còn `D:\` hardcode |
| M4-3 | `docker build -t nsga2-sumo-service:latest .` (trong thư mục `docker/`) | M4-2 | Image build thành công | 15-30 phút (tải PPA SUMO) | `docker run --rm nsga2-sumo-service:latest sumo --version` in ra phiên bản SUMO |
| M4-4 | `docker compose up --build` — chạy đồng thời service `api` (port 8000) và `mcp` (port 8765, HTTP) | M4-3 | 2 container chạy | 5 phút | `curl http://localhost:8000/health` trả `{"status":"ok"}` |
| M4-5 | Chạy thử 1 job qua API trong container | M4-4 | Kết quả trong volume `results_data` | 5-15 phút | `docker exec nsga2_api ls /app/results_service` thấy thư mục job |
| M4-6 | Kiểm tra `SUMO_HOME`/`PYTHONPATH` trong container đúng | M4-3 | — | 5 phút | `docker exec nsga2_api python3.10 -c "import traci, sumolib"` không lỗi |
| M4-7 (tuỳ chọn) | Publish image lên registry riêng (Docker Hub/GHCR) nếu cần triển khai máy khác | M4-4 | Image trên registry | 15 phút | `docker pull` về được từ máy khác |

Rủi ro riêng của M4 (không tự tin 100% nếu chưa build thử): gói APT `sumo`/`sumo-tools` qua PPA `ppa:sumo/stable` cho Ubuntu 22.04 — nếu PPA đổi cấu trúc hoặc phiên bản Ubuntu khác đi, bước `add-apt-repository` trong `Dockerfile` có thể cần chỉnh. Nếu build lỗi ở bước này, xem hướng dẫn cài đặt SUMO mới nhất tại `sumo.dlr.de/docs/Installing/Linux_Build.html` và sửa `docker/Dockerfile` cho khớp — đây là lý do M4 được đánh dấu "bạn cần làm" thay vì "đã xong": môi trường phiên làm việc này không có Docker daemon lẫn quyền cài SUMO thật để build-test.

### M5 — Vận hành & tài liệu (⬜ bạn cần làm)

| Mã | Việc | Phụ thuộc | Deliverable | Ước lượng | Tiêu chí hoàn thành |
|---|---|---|---|---|---|
| M5-1 | Viết `README.md` riêng cho thư mục service (khác README gốc của đồ án) | M3 | File README | 30 phút | Người khác đọc và chạy được `uvicorn`/`docker compose up` mà không hỏi lại bạn |
| M5-2 | Ghi lại trong luận văn/báo cáo: kiến trúc service (sơ đồ ở `HUONG_DAN_TICH_HOP.md` mục 2) | — | Đoạn báo cáo | 30-60 phút | — |
| M5-3 | Quyết định: chạy service này thường trực hay chỉ chạy khi cần demo? | M3, M4 | Ghi chú vận hành | 10 phút | — |
| M5-4 (tuỳ chọn) | Thêm `.env.example` liệt kê `NSGA2_PROJECT_SRC`, `NSGA2_RESULTS_DIR` | — | File `.env.example` | 5 phút | — |

### M6 — Mở rộng (⬜ chưa cần ngay, để dành khi thực sự cần)

| Mã | Việc | Lý do trì hoãn |
|---|---|---|
| M6-1 | Hợp nhất trạng thái job giữa FastAPI và MCP (SQLite/Redis dùng chung) | Chỉ cần khi dùng CẢ HAI cùng lúc và muốn thấy chung 1 danh sách job |
| M6-2 | SSE/WebSocket để đẩy tiến độ real-time thay vì polling | Polling đã đủ dùng cho quy mô cá nhân/luận văn |
| M6-3 | Tích hợp logic `resume_nsga.py` (resume từ checkpoint) vào `JobManager` | Chỉ cần nếu lo ngại mất tiến độ khi service bị restart giữa job dài |
| M6-4 | Cho phép nhiều job chạy song song (mỗi job 1 cổng TraCI riêng) | Đòi hỏi sửa sâu `SUMOEvaluatorImproved` (thêm `label=` cho `traci.start`) — cân nhắc kỹ trước khi làm |

## 3. Đối chiếu tool MCP với chuẩn mcp-builder

| Tool | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Lý do |
|---|:---:|:---:|:---:|:---:|---|
| `nsga2_list_scenarios` | true | false | true | false | Chỉ đọc `config.SCENARIOS` tĩnh, không tác dụng phụ |
| `nsga2_start_optimization` | false | false | false | true | Tạo job mới + chạy SUMO thật (tương tác hệ thống ngoài); gọi 2 lần với cùng tham số tạo 2 job khác nhau (không idempotent) |
| `nsga2_get_job_status` | true | false | true | false | Chỉ đọc trạng thái, gọi lại bao nhiêu lần cũng ra kết quả nhất quán tại một thời điểm |
| `nsga2_list_jobs` | true | false | true | false | Tương tự |
| `nsga2_cancel_job` | false | true | true | false | Thay đổi trạng thái job (destructive theo nghĩa dừng công việc đang chạy); gọi lại nhiều lần trên job đã huỷ không gây thêm tác dụng phụ (idempotent) |
| `nsga2_get_pareto_front` | true | false | true | false | Chỉ đọc CSV kết quả đã có sẵn |

Bảng này nên giữ lại trong code review nội bộ nếu sau này thêm tool mới — mỗi tool mới cần tự hỏi 4 câu hỏi trên trước khi viết annotations, tránh khai sai (ví dụ đánh dấu `readOnlyHint=true` cho một tool có ghi file sẽ khiến LLM/client đưa ra quyết định sai về mức độ an toàn khi gọi).

## 4. Checklist tổng hợp trước khi coi là "hoàn thiện"

Đánh dấu dần khi thực hiện — thứ tự đề xuất đi từ trên xuống vì có phụ thuộc:

- [ ] M0-3: `config.py` hết hardcode đường dẫn Windows tuyệt đối
- [ ] M0-2: `nsga2_core.py` đã nằm trong `D:\DoAn_NSGA2_SUMO\src\`
- [ ] M3-2: `pytest tests/test_jobs.py -v` pass 5/5 trên máy bạn (xác nhận môi trường đúng)
- [ ] M3-4: Kết quả CSV từ service khớp với CLI gốc cùng tham số/seed (xác nhận refactor không đổi thuật toán)
- [ ] M1-5: Chạy 1 job thật qua FastAPI thành công
- [ ] M2-7, M2-8: MCP server khai báo được trong Claude Desktop/Code, MCP Inspector gọi thử thành công
- [ ] M2-9: 6/6 câu hỏi trong `evaluation.xml` đúng
- [ ] M4-2 → M4-6: Docker build + chạy thành công (nếu bạn cần deploy, không bắt buộc nếu chỉ chạy local)
- [ ] M5-1: README riêng cho service đã viết

## 5. Danh sách file trong gói cập nhật lần này

So với gói gửi ở phiên trước, lần này có: `src_patch/nsga2_core.py` (đã sửa lỗi edge-case huỷ job sớm), `core/jobs.py` (đã sửa theo), `mcp_server/server.py` (viết lại theo chuẩn mcp-builder — đổi tên tool, thêm annotations/Pydantic/docstring chuẩn), `mcp_server/evaluation.xml` (bộ 6 câu hỏi eval), `tests/fake_evaluator.py` + `tests/test_jobs.py` (bộ test tích hợp, đã chạy PASS 5/5 trong phiên này), và toàn bộ thư mục `docker/` (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `prepare_context.ps1`, `requirements_project.txt`, `config_patched_example.py`).

Các file không đổi so với phiên trước: `core/bootstrap.py`, `api/schemas.py`, `api/main.py`, `src_patch/run_nsga2_v2_thin.py`, `HUONG_DAN_TICH_HOP.md` (vẫn nên đọc — chứa giải thích kiến trúc tổng thể mà tài liệu này không lặp lại).
