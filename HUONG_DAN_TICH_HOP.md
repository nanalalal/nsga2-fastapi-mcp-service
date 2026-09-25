# Hướng dẫn nhúng đồ án NSGA-II + SUMO vào FastAPI và MCP Server

Tài liệu này mô tả quy trình đưa đồ án *"Ứng dụng NSGA-II giải bài toán Điều khiển tín hiệu giao thông phối hợp tích hợp SUMO"* (thư mục `D:\DoAn_NSGA2_SUMO`) thành một dịch vụ có thể gọi qua REST API (FastAPI) và qua công cụ cho LLM (MCP Server), thay vì chỉ chạy được bằng lệnh `python run_nsga2_v2.py` từ terminal.

## 1. Hiểu đúng bản chất dự án trước khi nhúng

Đọc qua `README.md`, `src/run_nsga2_v2.py`, `src/problem_v2_honest.py`, `src/sumo_evaluator_ver2.py` và `src/repair_operator_ver2.py` cho thấy năm đặc điểm quyết định cách thiết kế service, khác hẳn một API CRUD thông thường.

Thứ nhất, mỗi lần đánh giá một cá thể (`SUMOEvaluatorImproved.evaluate()`) khởi động một tiến trình SUMO con qua TraCI, chạy mô phỏng 900 giây mô phỏng, và mất khoảng 4 giây thực. Một lần chạy đầy đủ NSGA-II (pop=60, gen=30) gọi khoảng 1800 lần như vậy, tức **khoảng 2 giờ CPU cho một kịch bản** — không thể trả kết quả trong một request/response HTTP thông thường.

Thứ hai, `traci` là thư viện đồng bộ (blocking), không hỗ trợ `async/await`, và theo cách project hiện dùng thì chỉ có **một kết nối TraCI hoạt động tại một thời điểm** trong tiến trình Python. Hai lần `evaluate()` chạy song song trong cùng tiến trình sẽ xung đột.

Thứ ba, `SUMOEvaluatorImproved.__init__` ghi cố định output vào `sumo_model/output/<scenario_id>/{tripinfo,summary,emission}.xml` — hai lần chạy cùng kịch bản `S1` song song (kể cả ở hai tiến trình khác nhau) sẽ **ghi đè lẫn nhau** vì dùng chung đường dẫn.

Thứ tư, `config.py` hiện hardcode đường dẫn tuyệt đối Windows (`D:\DoAn_NSGA2_VISSIM\sumo_model_s1\...`) — cần sửa để service chạy được từ vị trí khác, hoặc ít nhất phải nhận thức rõ ràng buộc này khi deploy.

Thứ năm, toàn bộ logic NSGA-II hiện nằm gói gọn trong hàm `main()` của `run_nsga2_v2.py`, gắn chặt với `argparse` và hành vi ghi file trực tiếp — không có một hàm nào có thể `import` và gọi lại được từ nơi khác mà không kéo theo việc parse `sys.argv`.

Năm đặc điểm này dẫn tới nguyên tắc thiết kế xuyên suốt tài liệu: **service không chạy tối ưu hoá "trong" request** mà chạy nền, tuần tự, và client theo dõi tiến độ bằng polling — giống mô hình "job queue" hơn là API tính toán nhanh.

## 2. Kiến trúc tổng thể đề xuất

```
                     ┌──────────────────────┐
   người dùng  ───▶  │   FastAPI (REST)     │
   (web/app)         │   api/main.py        │
                     └──────────┬───────────┘
                                │  dùng chung
                                ▼
                     ┌──────────────────────┐        ┌────────────────────┐
   LLM / Claude ───▶ │  MCP Server           │───▶    │  core/ (service     │
   (qua MCP)         │  mcp_server/server.py │        │  layer dùng chung)  │
                     └──────────────────────┘        │  - jobs.py          │
                                                       │  - bootstrap.py     │
                                                       └──────────┬──────────┘
                                                                  │ import
                                                                  ▼
                                                       ┌─────────────────────┐
                                                       │ src/nsga2_core.py    │
                                                       │ (mã nguồn GỐC        │
                                                       │  của đồ án, chỉ tách │
                                                       │  hàm, KHÔNG đổi      │
                                                       │  thuật toán)         │
                                                       └──────────┬──────────┘
                                                                  ▼
                                                       SUMO / TraCI (subprocess)
```

Cả FastAPI lẫn MCP server đều là **lớp vỏ mỏng** gọi vào cùng một `core/jobs.JobManager`, và `JobManager` gọi vào `nsga2_core.run_optimization()` — hàm lõi được tách ra từ `run_nsga2_v2.py` gốc mà không thay đổi một dòng thuật toán nào. Nhờ vậy nếu sau này sửa thuật toán (ví dụ đổi tham số SBX/PM), chỉ cần sửa một chỗ duy nhất và cả API lẫn MCP đều được cập nhật.

## 3. Quy trình thực hiện từng bước

### Bước 0 — Chuẩn bị môi trường

Giữ nguyên môi trường Python đã có theo README gốc (`pymoo`, `traci`, `sumolib`, `pandas`, `matplotlib`, `numpy`, `scipy`, biến môi trường `SUMO_HOME`). Cài thêm các gói cho service, liệt kê trong `requirements_service.txt` đi kèm tài liệu này: `fastapi`, `uvicorn[standard]`, `pydantic`, `mcp[cli]`.

```cmd
conda activate traffic_nsga2
pip install -r requirements_service.txt
```

Khai báo thêm một biến môi trường mới, trỏ tới thư mục `src/` của đồ án gốc — đây là điểm nối giữa service mới và code hiện có, không cần copy code:

```cmd
setx NSGA2_PROJECT_SRC "D:\DoAn_NSGA2_SUMO\src"
```

Mở lại terminal sau khi `setx` để biến có hiệu lực.

### Bước 1 — Tách lõi thuật toán khỏi CLI (`nsga2_core.py`)

Đây là bước quan trọng nhất và nên làm **trước tiên, độc lập với FastAPI/MCP**, vì nó tự nó đã là một cải thiện tốt cho project (dễ test, dễ tái sử dụng).

Sao chép file `src_patch/nsga2_core.py` (đi kèm tài liệu này) vào `D:\DoAn_NSGA2_SUMO\src\nsga2_core.py`. File này chứa lại **nguyên vẹn** các lớp `RepairedSampling`, `HVEarlyStopping`, `RunningNormalizer`, `NSGA2WithDiversityInfill`, và hàm `plot_results` — không đổi logic. Điểm khác biệt duy nhất là vòng lặp chính được bọc trong một hàm:

```python
def run_optimization(
    scenario: str,
    pop_size: int = 60,
    n_gen_max: int = 30,
    seed: int = 42,
    on_generation: Optional[Callable[[GenerationEvent], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> OptimizationResult:
    ...
```

Hàm này **không ghi file** — trả về một `OptimizationResult` (DataFrame lịch sử + hv_history + thế hệ dừng) trong bộ nhớ. Việc ghi CSV/PNG chuyển sang `save_results()`, gọi riêng. Tách như vậy để `run_optimization()` dùng được cả từ CLI, từ FastAPI (lưu theo `job_id`), và từ unit test (không đụng ổ đĩa).

Hai tham số mới là điểm móc nối với service: `on_generation` được gọi lại sau mỗi thế hệ để báo tiến độ (thay vì chỉ `print()`), và `should_cancel` được kiểm tra trước mỗi thế hệ để cho phép huỷ job giữa chừng — hữu ích vì một job có thể chạy hàng giờ và người dùng có quyền đổi ý.

File `run_nsga2_v2.py` gốc **không bắt buộc phải sửa** — bạn có thể tiếp tục chạy `python run_nsga2_v2.py --scenario S1 ...` y như cũ, `nsga2_core.py` chỉ là thêm chứ không thay. Nếu muốn dọn dẹp để tránh trùng lặp logic về lâu dài, `src_patch/run_nsga2_v2_thin.py` đi kèm cho thấy CLI gốc có thể rút gọn thành chỉ gọi `run_optimization()` + `save_results()`, giữ nguyên hành vi dòng lệnh.

### Bước 2 — Xây lớp service dùng chung (`core/`)

Thư mục `core/` (đi kèm tài liệu) chứa hai file không phụ thuộc FastAPI hay MCP, có thể test độc lập:

`core/bootstrap.py` thêm `NSGA2_PROJECT_SRC` vào `sys.path` để `from nsga2_core import run_optimization` tìm thấy đúng module, giống cách `run_nsga2_v2.py` gốc "thấy" `config.py` vì nằm cùng thư mục. Việc này thay thế cho giải pháp hardcode đường dẫn hoặc copy code vào service.

`core/jobs.py` chứa `JobManager` — quản lý vòng đời job bằng `ThreadPoolExecutor(max_workers=1)`. Cố định `max_workers=1` là chủ ý, không phải giới hạn tạm thời: vì lý do đã nêu ở Mục 1 (một kết nối TraCI, output path cố định theo `scenario_id`), các job phải chạy **tuần tự**. `JobManager` tự động lưu kết quả theo `results_service/<job_id>/` thay vì theo `scenario_id`, để hai job cùng kịch bản `S1` chạy trước/sau nhau không ghi đè kết quả của nhau.

Mỗi `Job` có các trường `status` (`pending` → `running` → `done`/`failed`/`cancelled`), `current_gen`, `hv`, `pareto_size`, `message` — được cập nhật trực tiếp từ callback `on_generation` chạy trong worker thread, có khoá (`threading.Lock`) để tránh race condition khi FastAPI đọc trạng thái đồng thời.

### Bước 3 — FastAPI (`api/`)

`api/schemas.py` định nghĩa các model Pydantic cho request/response (`OptimizeRequest`, `JobStatusResponse`, `ParetoResponse`...), tách khỏi `Job` nội bộ để đổi cấu trúc lưu trữ sau này không phá vỡ hợp đồng API.

`api/main.py` là ứng dụng FastAPI với các endpoint:

| Endpoint | Mô tả |
|---|---|
| `GET /scenarios` | Danh sách kịch bản, đọc trực tiếp từ `config.SCENARIOS` gốc |
| `POST /jobs` | Tạo job mới `{scenario, pop_size, n_gen_max}`, trả về ngay với `status=pending` |
| `GET /jobs` | Liệt kê tất cả job |
| `GET /jobs/{job_id}` | Trạng thái job — client polling endpoint này để theo dõi tiến độ |
| `POST /jobs/{job_id}/cancel` | Yêu cầu huỷ job đang chạy |
| `GET /jobs/{job_id}/pareto` | Tập Pareto cuối (chỉ khi `status=done`) |
| `GET /jobs/{job_id}/plot` | Ảnh PNG 3 biểu đồ tổng kết |

Chạy thử:

```cmd
cd D:\đường_dẫn_tới_service
uvicorn api.main:app --reload --port 8000
```

Rồi mở `http://127.0.0.1:8000/docs` — FastAPI tự sinh giao diện Swagger để bạn gọi thử `POST /jobs` với một kịch bản, sau đó polling `GET /jobs/{job_id}` để xem `current_gen` tăng dần.

### Bước 4 — MCP Server (`mcp_server/`)

`mcp_server/server.py` dùng `FastMCP` (trong gói `mcp[cli]`) để expose các "tool" mà một LLM (Claude Desktop, Claude Code, hoặc bất kỳ ứng dụng hỗ trợ MCP nào) có thể gọi: `list_scenarios`, `start_optimization`, `get_job_status`, `cancel_job`, `list_jobs`, `get_pareto_front`. Về mặt logic, đây là lớp vỏ tương đương FastAPI nhưng giao tiếp bằng giao thức MCP (STDIO mặc định) thay vì HTTP, và mô tả docstring của mỗi tool chính là thứ LLM đọc để quyết định khi nào gọi tool nào — nên viết rõ ràng, có cảnh báo về thời gian chạy (đã có sẵn trong file mẫu).

Khai báo trong cấu hình MCP client (ví dụ `.mcp.json` của Claude Code, hoặc `claude_desktop_config.json` của Claude Desktop):

```json
{
  "mcpServers": {
    "nsga2-sumo": {
      "command": "python",
      "args": ["D:\\đường_dẫn_tới_service\\mcp_server\\server.py"],
      "env": { "NSGA2_PROJECT_SRC": "D:\\DoAn_NSGA2_SUMO\\src" }
    }
  }
}
```

Sau khi khai báo, bạn có thể trò chuyện với Claude kiểu: *"Chạy tối ưu kịch bản S1 với 20 thế hệ, khi xong cho tôi biết tập Pareto và giải thích trade-off giữa độ trễ và CO2"* — Claude sẽ tự gọi `start_optimization`, polling `get_job_status`, rồi `get_pareto_front` khi `status=done`.

**Lưu ý quan trọng:** FastAPI và MCP server trong bản scaffold này chạy ở **hai tiến trình riêng biệt**, mỗi bên giữ một `JobManager` (bộ nhớ) độc lập — job tạo qua MCP sẽ không hiện trong danh sách job của FastAPI và ngược lại. Với một đồ án cá nhân/luận văn, đây thường không phải vấn đề (bạn dùng một trong hai, không cả hai cùng lúc). Nếu cần hợp nhất, xem Mục 5.

### Bước 5 — Kiểm thử trước khi chạy thật với SUMO

Vì mỗi job thật có thể mất hàng giờ, đừng debug luồng API/MCP bằng cách chạy job đầy đủ. Hai cách rút ngắn vòng lặp kiểm thử:

Một, dùng tham số nhỏ khi gọi thử: `pop_size=6, n_gen_max=2` chạy trong khoảng nửa phút, đủ để xác nhận `status` chuyển `pending → running → done`, `current_gen` tăng, và file CSV/PNG được tạo đúng chỗ.

Hai, viết một `evaluator` giả (fake) thay `SUMOEvaluatorImproved` để test riêng `JobManager`/API mà không cần SUMO cài sẵn — hữu ích khi CI/CD chạy trên máy không có SUMO. Vì `ProblemV2_HonestObjective` chỉ cần một đối tượng có method `evaluate(C, g1_1, g1_2, g2_1, g2_2, O2) -> tuple[float, float, float, float]`, bạn có thể "duck-type" thay bằng hàm trả số ngẫu nhiên.

## 4. Rủi ro và điểm cần lưu ý khi vận hành

Đường dẫn tuyệt đối Windows hardcode trong `config.py` (`D:\DoAn_NSGA2_VISSIM\...`) là điểm giòn nhất của hệ thống — nếu chuyển máy, đổi tên thư mục, hay build Docker image, các đường dẫn này sẽ gãy. Cân nhắc sửa `config.py` để dùng đường dẫn tương đối tính từ vị trí file (`os.path.dirname(__file__)`) hoặc đọc từ biến môi trường, tương tự cách `bootstrap.py` đã làm cho `NSGA2_PROJECT_SRC`.

Vì `max_workers=1`, hai request `POST /jobs` liên tiếp sẽ xếp hàng — request thứ hai không chạy song song mà đợi request thứ nhất xong. Đây là hành vi đúng theo ràng buộc kỹ thuật hiện tại (Mục 1), nhưng cần thông báo rõ cho người dùng API/MCP để họ không tưởng nhầm là bug. Muốn chạy thật sự song song nhiều kịch bản, phải sửa `SUMOEvaluatorImproved` để mỗi lần `evaluate()` dùng `traci.start(..., label=job_id)` với cổng riêng — đây là thay đổi không nhỏ vào code gốc, nên cân nhắc kỹ có thực sự cần thiết không trước khi làm.

Một job chạy hàng giờ nghĩa là nếu tiến trình FastAPI/MCP server bị restart (deploy lại, máy tắt), toàn bộ tiến độ job đang chạy mất trắng vì `JobManager` chỉ giữ trạng thái trong RAM. Với mục đích cá nhân/luận văn thường chấp nhận được; nếu cần độ tin cậy cao hơn, cần cơ chế checkpoint (project đã có sẵn ý tưởng này trong `resume_nsga.py` — có thể tích hợp logic resume-từ-CSV vào `JobManager` như một bước nâng cấp sau).

Nếu định expose FastAPI ra ngoài internet (không chỉ chạy `localhost`), cần thêm xác thực (API key tối thiểu) vì mỗi request `POST /jobs` kích hoạt tính toán tốn CPU trong hàng giờ — không nên để công khai không kiểm soát.

## 5. Hướng mở rộng (không bắt buộc làm ngay)

Muốn FastAPI và MCP server thấy chung một danh sách job (thay vì mỗi bên một bộ nhớ riêng), thay `Dict` trong `JobManager` bằng một bảng SQLite (dùng `sqlite3` chuẩn thư viện là đủ, không cần ORM phức tạp) — cả hai tiến trình đọc/ghi cùng một file `.db`. Đây là bước tự nhiên tiếp theo nếu bạn muốn giao diện web (gọi FastAPI) và trợ lý AI (gọi MCP) luôn đồng bộ trạng thái.

Muốn hiển thị tiến độ real-time thay vì client phải polling `GET /jobs/{job_id}` liên tục, thêm một endpoint Server-Sent Events (SSE) hoặc WebSocket trong FastAPI, đẩy mỗi `GenerationEvent` ra ngay khi `on_generation` được gọi.

Muốn chạy trong Docker, lưu ý image phải cài được SUMO (không chỉ `pip install`), và cần build kỹ vì SUMO có phụ thuộc hệ thống (thư viện đồ hoạ, v.v.) — nên bắt đầu từ image chính thức của SUMO nếu có, hoặc image Ubuntu rồi cài theo hướng dẫn `sumo.dlr.de`.

## 6. Danh sách file đi kèm tài liệu này

`src_patch/nsga2_core.py` — copy vào `D:\DoAn_NSGA2_SUMO\src\` (file mới, không ghi đè gì).

`src_patch/run_nsga2_v2_thin.py` — bản CLI rút gọn tham khảo, tuỳ chọn, không bắt buộc dùng.

`core/`, `api/`, `mcp_server/` — mã nguồn service mới, đặt ở một thư mục riêng (không cần nằm trong `D:\DoAn_NSGA2_SUMO`), chỉ cần khai báo đúng `NSGA2_PROJECT_SRC` trỏ về `src/` của đồ án gốc.

`requirements_service.txt` — danh sách gói cần cài thêm.

Tất cả các file `.py` trong bản scaffold đã được kiểm tra cú pháp hợp lệ (`ast.parse`), nhưng **chưa chạy thử với SUMO thật** trong môi trường này (môi trường phát triển hiện tại không có SUMO cài sẵn) — cần bạn tự chạy thử theo Bước 5 trên máy có SUMO trước khi coi là hoàn thiện.
