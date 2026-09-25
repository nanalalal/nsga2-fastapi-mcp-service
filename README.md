# NSGA-II + SUMO — Service Layer (FastAPI + MCP)

Lớp "service" bọc quanh đồ án tối ưu tín hiệu giao thông NSGA-II + SUMO
(mã nguồn gốc tại `D:\DoAn_NSGA2_SUMO\src`), expose ra ngoài qua **REST API
(FastAPI)** và **MCP server** (để LLM/Claude gọi trực tiếp như tool).

> **Repo lõi thuật toán (bắt buộc để chạy):** [nsga2-sumo-traffic-optimization](https://github.com/nanalalal/nsga2-sumo-traffic-optimization) —
> repo này KHÔNG copy lại mã nguồn NSGA-II/SUMO, mà nạp trực tiếp qua biến
> môi trường `NSGA2_PROJECT_SRC` (xem `core/bootstrap.py`). Clone repo lõi
> về máy trước, rồi mới chạy các lệnh trong mục "Chạy nhanh" bên dưới.

> README này được tạo bằng cách đọc trực tiếp toàn bộ code trong thư mục,
> dựa trên docstring/comment sẵn có trong từng file (viết ngày 2026-09-18).

## Nguyên tắc thiết kế cốt lõi

1. **Không copy lại code gốc.** `core/bootstrap.py` thêm `src/` gốc của đồ
   án vào `sys.path` thông qua biến môi trường `NSGA2_PROJECT_SRC` — mọi
   `import nsga2_core`, `from config import SCENARIOS` đều trỏ về đúng một
   bản mã nguồn duy nhất.
2. **Tách lõi thuật toán khỏi CLI.** `src_patch/nsga2_core.py` là bản tách
   ra từ `run_nsga2_v2.py` gốc: hàm `run_optimization()` không ghi file
   (side-effect-free) và nhận callback `on_generation` / `should_cancel` —
   đây là điểm nối để service layer theo dõi tiến độ & huỷ job giữa chừng.
3. **Job chạy nền, không block request.** Một job đầy đủ có thể chạy hàng
   giờ (SUMO qua TraCI), nên `core/jobs.py::JobManager` chạy job trong
   `ThreadPoolExecutor(max_workers=1)` — client tạo job xong nhận `job_id`
   ngay, sau đó poll trạng thái.
4. **Chỉ 1 job chạy tại một thời điểm** (chủ ý, không phải giới hạn tạm):
   `SUMOEvaluatorImproved` ghi cố định vào `sumo_model/output/<scenario_id>/...`
   và TraCI dùng cổng mặc định — 2 job song song sẽ đè file/tranh cổng nhau.

## Cấu trúc & vai trò từng file

```
nsga2_integration/
├── api/                  # REST service (FastAPI)
│   ├── main.py
│   └── schemas.py
├── core/                 # Logic dùng chung FastAPI <-> MCP
│   ├── bootstrap.py
│   └── jobs.py
├── mcp_server/            # MCP server cho LLM
│   ├── server.py
│   └── evaluation.xml
├── src_patch/             # Bản tách/patch lõi thuật toán từ code gốc
│   ├── nsga2_core.py
│   └── run_nsga2_v2_thin.py
├── docker/                 # Container hoá
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── prepare_context.ps1
│   ├── config_patched_example.py
│   └── requirements_project.txt
├── tests/                  # Test tích hợp (không cần SUMO thật)
│   ├── fake_evaluator.py
│   └── test_jobs.py
├── requirements_service.txt
├── HUONG_DAN_CONG_VIEC_CHI_TIET.md
└── HUONG_DAN_TICH_HOP.md
```

### `api/main.py`
FastAPI app (`title="NSGA-II + SUMO Traffic Signal Optimization API"`).
8 endpoint:

| Method | Path | Mục đích |
|---|---|---|
| GET | `/scenarios` | Danh sách kịch bản, đọc trực tiếp từ `config.SCENARIOS` gốc |
| POST | `/jobs` | Tạo job NSGA-II mới, trả về ngay `status=pending` |
| GET | `/jobs` | Liệt kê tất cả job |
| GET | `/jobs/{job_id}` | Trạng thái job (để client poll tiến độ) |
| POST | `/jobs/{job_id}/cancel` | Yêu cầu huỷ job đang chạy/chờ |
| GET | `/jobs/{job_id}/pareto` | Tập nghiệm Pareto (Rank=0) của thế hệ cuối — chỉ khi `status=done` |
| GET | `/jobs/{job_id}/plot` | Ảnh PNG 3 biểu đồ tổng kết |
| GET | `/health` | Health check |

### `api/schemas.py`
Pydantic models cho request/response (`OptimizeRequest`, `JobStatusResponse`,
`ParetoPoint`, `ParetoResponse`, `ScenarioInfo`) — tách biệt khỏi dataclass
nội bộ `core.jobs.Job` để đổi cấu trúc lưu trữ nội bộ không phá vỡ API.

### `core/bootstrap.py`
- `setup_project_path()`: thêm `src/` gốc (đọc từ env `NSGA2_PROJECT_SRC`,
  KHÔNG hardcode path Windows) vào `sys.path`. Bắt buộc gọi trước mọi
  import liên quan đồ án gốc — cả `api/main.py` lẫn `mcp_server/server.py`
  đều gọi ở dòng đầu tiên.
- `get_results_base_dir()`: thư mục lưu kết quả job của service
  (`<project_root>/results_service`, tách biệt với `results/` của CLI gốc
  để khỏi lẫn kết quả "chính thức" với kết quả thử nghiệm qua API).

### `core/jobs.py`
`JobManager` — bộ quản lý vòng đời job dùng chung giữa FastAPI và MCP
(mỗi tiến trình giữ 1 instance riêng, **không** chia sẻ trạng thái giữa
hai service — xem mục Giới hạn bên dưới).

- `Job` (dataclass): `job_id`, `scenario`, `status` (pending/running/done/
  failed/cancelled), `current_gen`, `hv`, `pareto_size`, `csv_path`,
  `plot_path`, `error`, ...
- `submit()`: validate `scenario` ngay lập tức (tránh lỗi cụt lủn kiểu
  `'S9'` nếu để tới tận `run_optimization()` mới raise), tạo job, đẩy vào
  `ThreadPoolExecutor`.
- `get()` / `list_jobs()` / `cancel()`: thread-safe qua `threading.Lock`.
- `_run_job()`: chạy `run_optimization()`, cập nhật `Job` qua callback
  `on_generation`, gọi `save_results()` khi xong. Có xử lý edge case: job
  bị huỷ *trước* generation đầu tiên → `history_df` rỗng → bỏ qua bước ghi
  file thay vì để job rơi vào `status=failed` (phát hiện qua
  `test_cancel_pending_job`).
- Cuối file có ghi chú 3 hướng "Mở rộng" chưa triển khai (xem mục Giới hạn).

### `mcp_server/server.py`
MCP server tên `nsga2_mcp`, viết theo best practice của skill `mcp-builder`
(tên tool có prefix `nsga2_`, input validate bằng Pydantic `extra="forbid"`,
mỗi tool khai báo `annotations` readOnly/destructive/idempotent/openWorld,
docstring đầy đủ Args/Returns/Examples/Error Handling cho LLM đọc). 6 tool:

- `nsga2_list_scenarios` — liệt kê S1/S2/S3 (đọc từ `config.SCENARIOS`).
- `nsga2_start_optimization` — tạo job mới (cảnh báo rõ: có thể chạy tới
  vài giờ CPU thật, trả về ngay không đợi).
- `nsga2_get_job_status` — tra tiến độ (để LLM polling).
- `nsga2_list_jobs` — liệt kê job (chỉ trong phạm vi tiến trình MCP này).
- `nsga2_cancel_job` — huỷ job pending/running.
- `nsga2_get_pareto_front` — lấy tập Pareto, trả markdown hoặc JSON.

Hỗ trợ 2 cách chạy: stdio (mặc định, cho Claude Desktop/Code tự spawn) hoặc
Streamable HTTP (`--http --port 8765`, dùng khi container hoá/nhiều client).

### `mcp_server/evaluation.xml`
Bộ câu hỏi đánh giá (Q&A cố định, chỉ dựa trên `SCENARIOS` tĩnh — không
dùng cho tool ngẫu nhiên/có side-effect) theo quy trình Phase 4 của skill
`mcp-builder`, dùng để kiểm tra MCP server trả lời đúng qua LLM/Inspector.

### `src_patch/nsga2_core.py`
File lớn nhất (≈22KB) — lõi thuật toán NSGA-II, tách nguyên vẹn từ
`run_nsga2_v2.py` gốc:

- `GenerationEvent`, `OptimizationResult` — dataclass giao tiếp với service.
- `RepairedSampling`, `HVEarlyStopping`, `RunningNormalizer`,
  `NSGA2WithDiversityInfill` — các thành phần thuật toán giữ **nguyên vẹn**
  logic gốc (sampling khả thi chống trùng lặp, early stopping theo
  Hypervolume, chuẩn hoá động, infill chống trùng nghiệm bằng
  mutation/random-fill).
- `plot_results()` — vẽ 3 biểu đồ (không gian mục tiêu f1/f2, lịch sử HV,
  kích thước Pareto front theo thế hệ), lưu PNG.
- `run_optimization()` — hàm lõi DUY NHẤT mà cả CLI lẫn service nên gọi;
  không ghi file, có callback tiến độ + huỷ.
- `save_results()` — ghi CSV + gọi `plot_results()`, tách khỏi
  `run_optimization()` để lớp gọi tự quyết định vị trí lưu (theo `job_id`
  thay vì theo `scenario` để nhiều job không đè nhau).

### `src_patch/run_nsga2_v2_thin.py`
Bản CLI "thin wrapper" tuỳ chọn thay cho `run_nsga2_v2.py` gốc: chỉ còn
argparse + gọi `run_optimization()` + `save_results()`. Hành vi dòng lệnh
giữ nguyên 100% (`python run_nsga2_v2.py --scenario S1 --pop_size 60
--n_gen_max 30`). Không bắt buộc dùng — có thể giữ file CLI gốc song song.

### `docker/`
- **Dockerfile**: image `ubuntu:22.04`, cài Python 3.10 + SUMO qua PPA
  chính thức, copy mã nguồn gốc (`project_src/`, `sumo_model_s1..3/`) và
  service layer (`core/`, `api/`, `mcp_server/`), chạy dưới user non-root.
- **docker-compose.yml**: 2 service từ cùng 1 image — `api` (port 8000) và
  `mcp` (port 8765, HTTP transport), dùng chung volume `results_data`. Có
  cảnh báo rõ: mỗi service có `JobManager` độc lập, và **không** được tăng
  `replicas` (tranh chấp cổng TraCI/ghi đè file output).
- **prepare_context.ps1**: script PowerShell chuẩn bị build context (copy
  `project_src/` + `sumo_model_s1..3/` từ `D:\DoAn_NSGA2_SUMO` vào `docker/`).
- **config_patched_example.py**: bản VÍ DỤ sửa `config.py` gốc để đường dẫn
  `sumo_cfg` tính tương đối theo vị trí file thay vì hardcode path Windows —
  điều kiện bắt buộc để chạy trong container Linux. Chỉ là tài liệu tham
  khảo, cần tự copy nội dung vào `config.py` thật.
- **requirements_project.txt**: thư viện gốc của đồ án (pymoo, pandas,
  matplotlib, numpy, scipy — traci/sumolib đi kèm SUMO qua PPA).

### `tests/`
- **fake_evaluator.py**: `FakeSUMOEvaluator` giả lập interface `evaluate()`
  của `SUMOEvaluatorImproved` — sinh f1 (trễ)/f2 (CO2) ngẫu nhiên có tương
  quan nghịch nhẹ để giả lập trade-off Pareto thật, cho phép test không
  cần cài SUMO/SUMO_HOME.
- **test_jobs.py**: test tích hợp (pytest), tự động monkeypatch
  `nsga2_core.SUMOEvaluatorImproved` bằng `FakeSUMOEvaluator` cho mọi test
  trong file. 5 test case:
  - `test_submit_and_complete` — job chạy xong, có CSV/PNG/pareto.
  - `test_invalid_scenario_raises_before_submit` — validate sớm.
  - `test_cancel_pending_job` — huỷ job đang chờ trong hàng đợi 1 worker.
  - `TestFastAPIWiring::test_endpoints_smoke` — smoke test `/scenarios`,
    `POST /jobs`, `/jobs/{id}/pareto` qua `TestClient`.
  - `TestMCPWiring::test_tools_smoke` — smoke test 3 tool MCP end-to-end.
  - Theo comment trong code: đã chạy PASSED 5/5 trong lúc xây scaffold.

### Tài liệu đi kèm (đã có sẵn, không phải do README này tạo)
- `HUONG_DAN_CONG_VIEC_CHI_TIET.md` — nhật ký/kế hoạch công việc chi tiết.
- `HUONG_DAN_TICH_HOP.md` — hướng dẫn tích hợp service vào đồ án gốc
  (bao gồm mục "Chia sẻ trạng thái giữa hai service" được nhắc tới nhiều
  lần trong code).

## Trạng thái hiện tại (đọc từ code, không suy đoán thêm)

**Đã làm xong:**
- Tách lõi thuật toán NSGA-II khỏi CLI, dùng chung được cho cả CLI gốc lẫn
  2 service mới, không copy trùng logic.
- `JobManager` quản lý job bất đồng bộ, tuần tự, thread-safe, có huỷ job
  và xử lý edge case job bị huỷ trước generation đầu tiên.
- FastAPI: đủ 8 endpoint (CRUD job + scenarios + pareto + plot + health).
- MCP server: đủ 6 tool, viết đúng chuẩn `mcp-builder` (annotations,
  docstring cho LLM, validate Pydantic, error message có gợi ý).
- Test tích hợp có evaluator giả — không cần SUMO thật để CI/dev.
- Docker hoá đầy đủ: Dockerfile cài SUMO + compose chạy song song 2 service.

**Giới hạn đã biết (tác giả tự ghi rõ trong code, chưa triển khai):**
1. Chỉ 1 job chạy cùng lúc (`max_workers=1`). Muốn song song nhiều kịch
   bản → phải sửa `SUMOEvaluatorImproved` dùng `traci.start(..., label=job_id)`
   và cổng TraCI riêng cho mỗi job.
2. FastAPI và MCP server có `JobManager` **độc lập theo tiến trình** — job
   tạo qua bên này không thấy ở bên kia. Muốn hợp nhất → chuyển state job
   từ `Dict` in-memory sang SQLite/Redis dùng chung.
3. State job chỉ giữ trong RAM → mất khi service restart (chưa persist
   xuống DB).
4. `docker/config_patched_example.py` là file tham khảo, chưa tự động áp
   dụng vào `config.py` gốc — cần copy tay.

## Tham số và ràng buộc đầy đủ

| Tham số | Kiểu | Mặc định | Ràng buộc |
|---|---|---|---|
| `scenario` | `str` | bắt buộc | Phải thuộc `config.SCENARIOS` (hiện `S1`/`S2`/`S3`) — kiểm tra thủ công, không phải Pydantic `Literal` |
| `pop_size` | `int` | `60` | `4 ≤ pop_size ≤ 500` |
| `n_gen_max` | `int` | `30` | `1 ≤ n_gen_max ≤ 200` |
| `seed` | `int` | `42` | Cố định trong `run_optimization()` — **chưa** có field tương ứng ở `OptimizeRequest`/`StartOptimizationInput`, không đổi được qua request |
| `response_format` (chỉ `nsga2_get_pareto_front`) | `"markdown"` \| `"json"` | `"markdown"` | — |

## Giới hạn khác cần biết (ngoài 4 điểm đã liệt kê ở mục Trạng thái)

- **Không có xác thực (auth) hay rate-limit**: ai gọi được tới cổng `8000`/`8765` đều dùng được toàn bộ API/MCP — chỉ phù hợp chạy cục bộ/demo, chưa sẵn sàng public.
- **Huỷ job không tức thời**: `nsga2_cancel_job`/`POST /jobs/{id}/cancel` chỉ đặt cờ — job dừng thật sau khi mô phỏng SUMO của thế hệ hiện tại chạy xong, không ngắt `traci` giữa chừng.
- **Chỉ đúng 3 kịch bản định sẵn**: không nhận `scenario` tuỳ ý hay override `total_hourly_demand`/đường dẫn SUMO qua request — muốn thêm kịch bản chỉ cần sửa `config.SCENARIOS` bên repo lõi (không cần sửa code service).

## Cấu hình MCP client (Claude Desktop / Claude Code) — chạy qua stdio

```json
{
  "mcpServers": {
    "nsga2_mcp": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "D:\\DoAn_NSGA2_SUMO\\service_fastapi_mcp\\nsga2_fastapi_mcp_scaffold\\nsga2_integration",
      "env": { "NSGA2_PROJECT_SRC": "D:\\DoAn_NSGA2_SUMO\\src" }
    }
  }
}
```

## Chạy nhanh

### 1. Khai báo biến môi trường (bắt buộc, trước mọi lệnh dưới đây)
```powershell
setx NSGA2_PROJECT_SRC "D:\DoAn_NSGA2_SUMO\src"
# mở lại terminal sau khi setx
```

### 2. Cài thư viện
```bash
pip install pymoo pandas matplotlib numpy scipy traci sumolib   # đồ án gốc
pip install -r requirements_service.txt                          # fastapi, uvicorn, pydantic, mcp[cli]
```

### 3. Chạy FastAPI
```bash
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### 4. Chạy MCP server
```bash
python mcp_server/server.py                       # stdio — cho Claude Desktop/Code
python mcp_server/server.py --http --port 8765     # HTTP — cho container/nhiều client
```

### 5. Chạy test (không cần cài SUMO thật)
```bash
pip install pytest
pytest tests/test_jobs.py -v -s
```

### 6. Chạy bằng Docker (cả 2 service)
```powershell
cd docker
.\prepare_context.ps1        # copy project_src + sumo_model_s1..3 vào docker/
docker compose up --build
# FastAPI:    http://localhost:8000/docs
# MCP (HTTP): http://localhost:8765/mcp
```
