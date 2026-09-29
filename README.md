# NSGA-II + SUMO — Service Layer (FastAPI + MCP)

Lớp service bọc quanh đồ án tối ưu tín hiệu giao thông NSGA-II + SUMO, expose ra ngoài qua **REST API (FastAPI)** và **MCP server** (để LLM/Claude gọi trực tiếp như tool). Không copy lại mã nguồn thuật toán — nạp trực tiếp từ repo lõi qua biến môi trường, nên chỉ có một bản mã nguồn duy nhất cho cả CLI gốc và service này.

**Repo lõi thuật toán (bắt buộc, clone trước khi dùng repo này):** [nsga2-sumo-traffic-optimization](https://github.com/nanalalal/nsga2-sumo-traffic-optimization)

## Mục lục

1. [Yêu cầu hệ thống](#1-yêu-cầu-hệ-thống)
2. [Cài đặt & chạy nhanh](#2-cài-đặt--chạy-nhanh)
3. [Cấu hình MCP client](#3-cấu-hình-mcp-client-claude-desktop--claude-code)
4. [Tham khảo API (REST)](#4-tham-khảo-api-rest)
5. [Tham khảo MCP tools](#5-tham-khảo-mcp-tools)
6. [Kiểm thử](#6-kiểm-thử)
7. [Chạy bằng Docker](#7-chạy-bằng-docker)
8. [Nguyên tắc thiết kế](#8-nguyên-tắc-thiết-kế)
9. [Cấu trúc thư mục & vai trò từng file](#9-cấu-trúc-thư-mục--vai-trò-từng-file)
10. [Trạng thái & giới hạn đã biết](#10-trạng-thái--giới-hạn-đã-biết)

---

## 1. Yêu cầu hệ thống

- Python 3.10+
- Repo lõi [nsga2-sumo-traffic-optimization](https://github.com/nanalalal/nsga2-sumo-traffic-optimization) đã clone về máy, SUMO đã cài đặt theo README của repo đó (bao gồm biến môi trường `SUMO_HOME`)
- Các thư viện Python liệt kê trong `requirements_service.txt`

## 2. Cài đặt & chạy nhanh

> Mọi đường dẫn `<...>` bên dưới là placeholder — thay bằng đường dẫn thật trên máy bạn. Vì đây là repo public, đường dẫn tuyệt đối trên máy tác giả không có ý nghĩa gì với máy bạn.

### Bước 1 — Trỏ tới repo lõi

Biến môi trường `NSGA2_PROJECT_SRC` phải trỏ tới thư mục `src/` bên trong repo lõi bạn vừa clone.

**Windows (PowerShell hoặc Anaconda Prompt):**
```powershell
setx NSGA2_PROJECT_SRC "<đường-dẫn-bạn-clone-repo-lõi>\src"
```
Ví dụ: nếu bạn clone repo lõi vào `C:\projects\nsga2-sumo-traffic-optimization`, giá trị cần set là `C:\projects\nsga2-sumo-traffic-optimization\src`.

**Linux / macOS:**
```bash
export NSGA2_PROJECT_SRC="<đường-dẫn-bạn-clone-repo-lõi>/src"
```

> ⚠️ Sau `setx`, phải **mở lại terminal** (và activate lại conda/venv nếu dùng) để biến có hiệu lực — terminal đang mở sẽ không tự thấy biến mới.

### Bước 2 — Cài thư viện

```bash
pip install pymoo pandas matplotlib numpy scipy traci sumolib   # đồ án gốc (bỏ qua nếu đã cài theo README repo lõi)
pip install -r requirements_service.txt                          # fastapi, uvicorn, pydantic, mcp[cli]
```

### Bước 3 — Chạy server

Cần **giữ nguyên terminal này chạy**, không đóng:
```bash
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

(Tuỳ chọn) MCP server ở một terminal khác:
```bash
python mcp_server/server.py                       # stdio — cho Claude Desktop/Code tự spawn
python mcp_server/server.py --http --port 8765     # HTTP — cho container hoặc nhiều client
```

### Bước 4 — Gọi thử bằng client mẫu

Với server ở Bước 3 vẫn đang chạy, mở **một terminal khác**:
```bash
pip install requests
python examples/client_example.py
```
Script tạo 1 job nhỏ (`pop_size=8, n_gen_max=2` — vài chục giây tới vài phút thay vì hàng giờ), poll trạng thái, rồi in tập Pareto trả về. Đây cũng là ví dụ tối thiểu cho việc gọi API từ bên ngoài bằng Python thuần (`requests`), không cần biết gì về code nội bộ.

## 3. Cấu hình MCP client (Claude Desktop / Claude Code)

```json
{
  "mcpServers": {
    "nsga2_mcp": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "<đường-dẫn-tới-thư-mục-nsga2_integration-trên-máy-bạn>",
      "env": { "NSGA2_PROJECT_SRC": "<đường-dẫn-tới-src-của-repo-lõi>" }
    }
  }
}
```
Trên Windows, JSON cần dấu `\\` kép, ví dụ `"cwd": "C:\\projects\\nsga2_integration"`.

## 4. Tham khảo API (REST)

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

Schema đầy đủ: xem `api/schemas.py` hoặc mở Swagger UI (`/docs`) khi server đang chạy.

### Tham số của `POST /jobs`

| Tham số | Kiểu | Mặc định | Ràng buộc |
|---|---|---|---|
| `scenario` | `str` | bắt buộc | Phải thuộc `config.SCENARIOS` (hiện `S1`/`S2`/`S3`) |
| `pop_size` | `int` | `60` | `4 ≤ pop_size ≤ 500` |
| `n_gen_max` | `int` | `30` | `1 ≤ n_gen_max ≤ 200` |
| `total_hourly_demand` | `float`, optional | giá trị gốc của `scenario` | `> 0` — ghi đè lưu lượng xe/giờ |
| `cycle_min` / `cycle_max` | `float`, optional | `60` / `120` | `> 0` — ghi đè bounds chu kỳ đèn C [giây] |
| `green_min` / `green_max` | `float`, optional | `15` / `90` | `> 0` — ghi đè bounds thời gian xanh mỗi pha [giây] |

**Tham số vs. hạ tầng:** `total_hourly_demand`/`cycle_*`/`green_*` là THAM SỐ, chỉnh được qua request mà không cần sửa code. Ngược lại, **network topology của SUMO** (số giao lộ, hình học đường — hiện cố định 2 giao lộ J1/J2) là INPUT HẠ TẦNG, dựng thủ công trong SUMO cho từng kịch bản — muốn áp dụng cho giao lộ khác phải xây model SUMO mới, không phải việc sửa API/service.

## 5. Tham khảo MCP tools

Server tên `nsga2_mcp`, viết theo best practice của skill `mcp-builder` (tên tool prefix `nsga2_`, input validate bằng Pydantic `extra="forbid"`, mỗi tool khai báo `annotations` readOnly/destructive/idempotent/openWorld, docstring đầy đủ Args/Returns/Examples cho LLM đọc).

| Tool | Chức năng |
|---|---|
| `nsga2_list_scenarios` | Liệt kê S1/S2/S3 |
| `nsga2_start_optimization` | Tạo job mới (cảnh báo có thể chạy tới vài giờ CPU thật, trả về ngay không đợi) |
| `nsga2_get_job_status` | Tra tiến độ job (để LLM polling) |
| `nsga2_list_jobs` | Liệt kê job (chỉ trong phạm vi tiến trình MCP này) |
| `nsga2_cancel_job` | Huỷ job pending/running |
| `nsga2_get_pareto_front` | Lấy tập Pareto, trả markdown hoặc JSON |

## 6. Kiểm thử

```bash
pip install pytest
pytest tests/test_jobs.py -v
```
Dùng `FakeSUMOEvaluator` (`tests/fake_evaluator.py`) giả lập interface `evaluate()` — không cần cài SUMO thật, phù hợp CI/dev nhanh. Hiện 8/8 test pass, gồm smoke test cho cả REST API và MCP tools, cộng test riêng cho việc ghi đè tham số qua request (`cycle_bounds`/`green_bounds` không phá vỡ default hành vi gốc).

## 7. Chạy bằng Docker

```powershell
cd docker
.\prepare_context.ps1        # copy project_src + sumo_model_s1..3 từ repo lõi vào docker/ — SỬA biến $ProjectRoot trong script này trỏ đúng máy bạn trước khi chạy
docker compose up --build
```
```
FastAPI:    http://localhost:8000/docs
MCP (HTTP): http://localhost:8765/mcp
```

Lưu ý: mỗi service (`api`, `mcp`) chạy trong tiến trình riêng, mỗi bên có `JobManager` độc lập — job tạo qua MCP không hiện trong danh sách job của FastAPI và ngược lại. Không tăng `replicas`: `SUMOEvaluatorImproved` dùng TraCI với cổng mặc định và ghi output cố định theo `scenario_id`, nhiều instance cùng lúc sẽ tranh chấp cổng/đè file.

## 8. Nguyên tắc thiết kế

1. **Không copy lại code gốc.** `core/bootstrap.py` thêm `src/` gốc vào `sys.path` qua biến môi trường `NSGA2_PROJECT_SRC` — mọi `import nsga2_core`, `from config import SCENARIOS` đều trỏ về đúng một bản mã nguồn duy nhất.
2. **Tách lõi thuật toán khỏi CLI.** `src_patch/nsga2_core.py` tách từ `run_nsga2_v2.py` gốc: `run_optimization()` không ghi file (side-effect-free) và nhận callback `on_generation`/`should_cancel` — điểm nối để service theo dõi tiến độ & huỷ job giữa chừng.
3. **Job chạy nền, không block request.** Một job đầy đủ có thể chạy hàng giờ (SUMO qua TraCI), nên `core/jobs.py::JobManager` chạy job trong `ThreadPoolExecutor(max_workers=1)` — client tạo job xong nhận `job_id` ngay, sau đó poll trạng thái.
4. **Chỉ 1 job chạy tại một thời điểm** (chủ ý, không phải giới hạn tạm): `SUMOEvaluatorImproved` ghi cố định vào `sumo_model/output/<scenario_id>/...` và TraCI dùng cổng mặc định — 2 job song song sẽ đè file/tranh cổng nhau.

## 9. Cấu trúc thư mục & vai trò từng file

```
nsga2_integration/
├── api/                    # REST service (FastAPI)
│   ├── main.py
│   └── schemas.py
├── core/                   # Logic dùng chung FastAPI <-> MCP
│   ├── bootstrap.py
│   └── jobs.py
├── mcp_server/             # MCP server cho LLM
│   ├── server.py
│   └── evaluation.xml
├── src_patch/              # Bản tách/patch lõi thuật toán từ code gốc
│   ├── nsga2_core.py
│   └── run_nsga2_v2_thin.py
├── docker/                 # Container hoá
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── prepare_context.ps1
│   ├── config_patched_example.py
│   └── requirements_project.txt
├── examples/                # Ví dụ client gọi API từ bên ngoài
│   └── client_example.py
├── tests/                  # Test tích hợp (không cần SUMO thật)
│   ├── fake_evaluator.py
│   └── test_jobs.py
└── requirements_service.txt
```

<details>
<summary>Chi tiết vai trò từng file (bấm để mở)</summary>

### `api/main.py` / `api/schemas.py`
FastAPI app + Pydantic models cho request/response (`OptimizeRequest`, `JobStatusResponse`, `ParetoPoint`, `ParetoResponse`, `ScenarioInfo`) — tách biệt khỏi dataclass nội bộ `core.jobs.Job` để đổi cấu trúc lưu trữ nội bộ không phá vỡ API.

### `core/bootstrap.py`
- `setup_project_path()`: thêm `src/` gốc (đọc từ env `NSGA2_PROJECT_SRC`, không hardcode path) vào `sys.path`. Bắt buộc gọi trước mọi import liên quan đồ án gốc.
- `get_results_base_dir()`: thư mục lưu kết quả job của service (`results_service/`, tách biệt với `results/` của CLI gốc).

### `core/jobs.py`
`JobManager` — quản lý vòng đời job dùng chung giữa FastAPI và MCP (mỗi tiến trình giữ 1 instance riêng, không chia sẻ trạng thái giữa hai service — xem mục 10).

- `Job` (dataclass): `job_id`, `scenario`, `status` (pending/running/done/failed/cancelled), `current_gen`, `hv`, `pareto_size`, `csv_path`, `plot_path`, `error`, ...
- `submit()`: validate `scenario` ngay lập tức, tạo job, đẩy vào `ThreadPoolExecutor`.
- `get()` / `list_jobs()` / `cancel()`: thread-safe qua `threading.Lock`.
- `_run_job()`: chạy `run_optimization()`, cập nhật `Job` qua callback, gọi `save_results()` khi xong. Xử lý edge case: job bị huỷ trước generation đầu tiên → bỏ qua bước ghi file thay vì rơi vào `status=failed`.

### `mcp_server/server.py`
MCP server — chi tiết tool xem mục 5. Hỗ trợ 2 cách chạy: stdio (mặc định, Claude Desktop/Code tự spawn) hoặc Streamable HTTP (`--http --port 8765`).

### `mcp_server/evaluation.xml`
Bộ câu hỏi đánh giá (Q&A cố định dựa trên `SCENARIOS` tĩnh) theo quy trình Phase 4 của skill `mcp-builder`, dùng để kiểm tra MCP server trả lời đúng qua LLM/Inspector.

### `src_patch/nsga2_core.py`
Lõi thuật toán NSGA-II, tách nguyên vẹn từ `run_nsga2_v2.py` gốc:
- `GenerationEvent`, `OptimizationResult` — dataclass giao tiếp với service.
- `RepairedSampling`, `HVEarlyStopping`, `RunningNormalizer`, `NSGA2WithDiversityInfill` — các thành phần thuật toán giữ nguyên vẹn logic gốc.
- `plot_results()` — vẽ 3 biểu đồ, lưu PNG.
- `run_optimization()` — hàm lõi duy nhất mà cả CLI lẫn service gọi; không ghi file, có callback tiến độ + huỷ.
- `save_results()` — ghi CSV + gọi `plot_results()`, lưu theo `job_id` thay vì `scenario` để nhiều job không đè nhau.

### `src_patch/run_nsga2_v2_thin.py`
Bản CLI "thin wrapper" tuỳ chọn: chỉ còn argparse + gọi `run_optimization()` + `save_results()`. Hành vi dòng lệnh giữ nguyên 100% so với `run_nsga2_v2.py` gốc.

### `docker/`
- **Dockerfile**: image `ubuntu:22.04`, cài Python 3.10 + SUMO qua PPA chính thức, copy mã nguồn gốc và service layer, chạy dưới user non-root.
- **docker-compose.yml**: 2 service từ cùng 1 image — `api` (port 8000) và `mcp` (port 8765).
- **prepare_context.ps1**: script PowerShell chuẩn bị build context (copy `project_src/` + `sumo_model_s1..3/` từ repo lõi vào `docker/`) — cần sửa biến `$ProjectRoot` trỏ đúng máy bạn.
- **config_patched_example.py**: bản ví dụ sửa `config.py` gốc để đường dẫn `sumo_cfg` tính tương đối thay vì hardcode path Windows — điều kiện để chạy trong container Linux. Chỉ là tài liệu tham khảo, cần tự copy nội dung vào `config.py` thật.

### `tests/`
- **fake_evaluator.py**: `FakeSUMOEvaluator` giả lập interface `evaluate()` của `SUMOEvaluatorImproved`, sinh f1/f2 ngẫu nhiên có tương quan nghịch nhẹ để giả lập trade-off Pareto thật.
- **test_jobs.py**: test tích hợp (pytest), tự động monkeypatch `SUMOEvaluatorImproved` bằng `FakeSUMOEvaluator`. 8 test case bao gồm submit/cancel/validate job, smoke test REST + MCP, và test riêng cho tham số ghi đè qua request.

</details>

## 10. Trạng thái & giới hạn đã biết

**Đã hoàn thành:**
- Tách lõi thuật toán NSGA-II khỏi CLI, dùng chung cho cả CLI gốc lẫn 2 service mới, không copy trùng logic.
- `JobManager` quản lý job bất đồng bộ, tuần tự, thread-safe, có huỷ job và xử lý edge case job bị huỷ trước generation đầu tiên.
- FastAPI: đủ 8 endpoint (CRUD job + scenarios + pareto + plot + health).
- MCP server: đủ 6 tool theo chuẩn `mcp-builder`.
- Test tích hợp có evaluator giả — không cần SUMO thật để CI/dev.
- Docker hoá đầy đủ: Dockerfile cài SUMO + compose chạy song song 2 service.
- `total_hourly_demand` và bounds của 6 biến quyết định (`cycle_min/max`, `green_min/max`) ghi đè được qua request (REST + MCP), mặc định giữ nguyên hành vi gốc nếu không truyền.

**Giới hạn đã biết (chưa triển khai):**
1. Chỉ 1 job chạy cùng lúc (`max_workers=1`). Muốn song song nhiều kịch bản → phải sửa `SUMOEvaluatorImproved` dùng `traci.start(..., label=job_id)` và cổng TraCI riêng cho mỗi job.
2. FastAPI và MCP server có `JobManager` **độc lập theo tiến trình** — job tạo qua bên này không thấy ở bên kia. Muốn hợp nhất → chuyển state job từ `Dict` in-memory sang SQLite/Redis dùng chung.
3. State job chỉ giữ trong RAM → mất khi service restart (chưa persist xuống DB).
4. `docker/config_patched_example.py` là file tham khảo, chưa tự động áp dụng vào `config.py` gốc — cần copy tay.
5. Không có xác thực (auth) hay rate-limit — chỉ phù hợp chạy cục bộ/demo, chưa sẵn sàng public.
6. Huỷ job không tức thời: `nsga2_cancel_job`/`POST /jobs/{id}/cancel` chỉ đặt cờ — job dừng thật sau khi mô phỏng SUMO của thế hệ hiện tại chạy xong.
7. Chỉ đúng 3 kịch bản định sẵn về network topology — mỗi kịch bản gắn với một model mạng lưới SUMO dựng thủ công, muốn thêm kịch bản mới cần sửa `config.SCENARIOS` bên repo lõi (không cần sửa code service).
