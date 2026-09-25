# -*- coding: utf-8 -*-
"""
jobs.py

Quản lý vòng đời "job tối ưu hoá" — lớp trung gian dùng chung giữa
FastAPI (api/main.py) và MCP server (mcp_server/server.py).

Vì SUMO/TraCI:
    - chạy BLOCKING (không async), CPU-bound trong Python + I/O socket
      tới tiến trình SUMO con;
    - chỉ nên chạy MỘT job tại một thời điểm cho mỗi output_dir/scenario
      (SUMOEvaluatorImproved ghi cố định vào
      sumo_model/output/<scenario_id>/... — hai job cùng scenario chạy
      song song sẽ GHI ĐÈ lẫn nhau);

...JobManager dùng một ThreadPoolExecutor(max_workers=1) để LUÔN LUÔN
xử lý job tuần tự, không cần lo tranh chấp cổng TraCI hay ghi đè file.
Muốn chạy song song nhiều kịch bản cùng lúc, xem phần "Mở rộng" ở cuối
file — cần tách output_dir theo job_id, không chỉ theo scenario_id.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from nsga2_core import SCENARIOS, GenerationEvent, OptimizationResult, run_optimization, save_results


class JobStatus(str, Enum):
    """Trạng thái vòng đời của một job tối ưu hoá."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Trạng thái đầy đủ của một job — được cập nhật trực tiếp bởi worker thread."""

    job_id: str
    scenario: str
    pop_size: int
    n_gen_max: int
    status: JobStatus = JobStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_gen: int = 0
    hv: float = 0.0
    pareto_size: int = 0
    message: str = ""
    csv_path: Optional[str] = None
    plot_path: Optional[str] = None
    error: Optional[str] = None
    _cancel_requested: bool = field(default=False, repr=False)


class JobManager:
    """Bộ quản lý job dùng chung — import DUY NHẤT MỘT instance trong mỗi
    tiến trình (FastAPI có instance riêng, MCP server có instance riêng;
    xem HUONG_DAN_TICH_HOP.md mục "Chia sẻ trạng thái giữa hai service"
    nếu cần hợp nhất chúng qua SQLite/Redis).
    """

    def __init__(self, results_dir: str, max_workers: int = 1) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._results_dir = results_dir

    # ------------------------------------------------------------------ #
    # API công khai
    # ------------------------------------------------------------------ #

    def submit(self, scenario: str, pop_size: int = 60, n_gen_max: int = 30) -> Job:
        """Tạo job mới và đưa vào hàng đợi thực thi (không block).

        Validate `scenario` ngay tại đây (không chỉ dựa vào lớp gọi như
        api/main.py hay mcp_server/server.py) — để BẤT KỲ nơi nào gọi
        JobManager.submit() trực tiếp trong tương lai (ví dụ thêm CLI/
        entrypoint mới) cũng nhận lỗi rõ ràng ngay lập tức, thay vì lỡ
        quên validate và để job chạy tới tận run_optimization() mới
        raise KeyError, bị nuốt vào except trong _run_job() thành
        status="failed" với error cụt lủn kiểu "'S9'".

        Raises:
            ValueError: Nếu `scenario` không có trong config.SCENARIOS.
        """
        if scenario not in SCENARIOS:
            raise ValueError(
                f"Kịch bản '{scenario}' không hợp lệ. Các kịch bản có trong "
                f"config.SCENARIOS: {list(SCENARIOS)}."
            )
        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id=job_id, scenario=scenario, pop_size=pop_size, n_gen_max=n_gen_max)
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run_job, job_id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        """Đánh dấu job cần huỷ. Job đang chạy sẽ dừng sau thế hệ hiện tại
        (kiểm tra should_cancel trước mỗi generation.next() trong
        run_optimization)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                return False
            job._cancel_requested = True
            return True

    # ------------------------------------------------------------------ #
    # Nội bộ — chạy trong worker thread
    # ------------------------------------------------------------------ #

    def _run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return

        with self._lock:
            job.status = JobStatus.RUNNING
            job.message = "Đang chạy NSGA-II + SUMO..."

        def on_generation(evt: GenerationEvent) -> None:
            with self._lock:
                job.current_gen = evt.gen
                job.hv = evt.hv
                job.pareto_size = evt.pareto_size
                job.message = evt.stop_reason or f"Thế hệ {evt.gen}/{evt.n_gen_max}"

        def should_cancel() -> bool:
            with self._lock:
                return job._cancel_requested

        try:
            result: OptimizationResult = run_optimization(
                scenario=job.scenario,
                pop_size=job.pop_size,
                n_gen_max=job.n_gen_max,
                on_generation=on_generation,
                should_cancel=should_cancel,
            )
            # EDGE CASE (phát hiện qua tests/test_jobs.py::test_cancel_pending_job):
            # nếu job bị huỷ NGAY TRƯỚC generation đầu tiên (should_cancel()==True
            # trước cả algorithm.next() lần đầu), history_df rỗng và gen_final=None
            # -> save_results() sẽ raise ValueError. Trường hợp này không có gì để
            # lưu, nên bỏ qua bước ghi file thay vì để job rơi vào status="failed".
            if len(result.history_df) > 0:
                # Lưu theo job_id để nhiều job cùng kịch bản không ghi đè nhau
                job_results_dir = f"{self._results_dir}/{job_id}"
                result = save_results(result, job_results_dir)

            with self._lock:
                if job._cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.message = "Job đã bị huỷ theo yêu cầu"
                else:
                    job.status = JobStatus.DONE
                    job.message = "Hoàn thành"
                job.csv_path = result.csv_path
                job.plot_path = result.plot_path

        except Exception as exc:  # noqa: BLE001 — muốn bắt mọi lỗi để job không "treo"
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.message = f"Lỗi: {exc}"


# === Mở rộng (không bắt buộc triển khai ngay) ===
#
# 1. Chạy song song nhiều kịch bản: tăng max_workers, nhưng PHẢI sửa
#    SUMOEvaluatorImproved để mỗi job dùng traci.start(..., label=job_id)
#    và cổng TraCI riêng — bản gốc dùng traci mặc định (1 kết nối toàn cục).
#
# 2. Chia sẻ trạng thái job giữa FastAPI và MCP server: thay Dict in-memory
#    bằng bảng SQLite (sqlite3/SQLAlchemy) hoặc Redis — cả hai service đọc/
#    ghi cùng một chỗ thay vì mỗi bên giữ bản sao riêng.
#
# 3. Muốn chống mất job khi restart service: persist Job dataclass xuống
#    SQLite mỗi lần cập nhật thay vì chỉ giữ trong RAM.
