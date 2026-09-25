# -*- coding: utf-8 -*-
"""
main.py — FastAPI service cho đồ án NSGA-II + SUMO.

Chạy:
    # Windows, sau khi setx NSGA2_PROJECT_SRC (xem HUONG_DAN_TICH_HOP.md)
    uvicorn api.main:app --reload --port 8000

Endpoints chính:
    GET  /scenarios              — danh sách kịch bản (từ config.SCENARIOS)
    POST /jobs                   — tạo job tối ưu hoá mới (chạy nền)
    GET  /jobs                   — liệt kê tất cả job
    GET  /jobs/{job_id}          — trạng thái job (poll để theo dõi tiến độ)
    POST /jobs/{job_id}/cancel   — yêu cầu huỷ job đang chạy
    GET  /jobs/{job_id}/pareto   — tập Pareto cuối (chỉ khi status=done)
    GET  /jobs/{job_id}/plot     — ảnh PNG 3 biểu đồ tổng kết

Lưu ý quan trọng:
    - Mỗi lần gọi SUMO trong evaluate() mất vài giây và một job đầy đủ có
      thể chạy HÀNG GIỜ (xem README gốc: ~2h CPU/kịch bản với pop=60,
      gen=30). Vì vậy job KHÔNG chạy trong request handler — nó được đưa
      vào JobManager (core/jobs.py), chạy trong 1 worker thread riêng,
      và client polling GET /jobs/{job_id} để theo dõi.
    - JobManager giới hạn 1 worker → các job chạy TUẦN TỰ. Đây là chủ ý,
      không phải giới hạn tạm thời: SUMOEvaluatorImproved ghi cố định vào
      sumo_model/output/<scenario_id>/..., hai job cùng lúc sẽ đè file
      của nhau và traci dùng cổng mặc định (không hỗ trợ nhiều kết nối
      song song nếu không sửa thêm `label=` — xem core/jobs.py mục "Mở rộng").
"""

import os

from core.bootstrap import get_results_base_dir, setup_project_path

# BẮT BUỘC gọi trước mọi import liên quan tới mã nguồn gốc của đồ án
setup_project_path()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from core.jobs import JobManager  # noqa: E402
from api.schemas import (  # noqa: E402
    JobStatusResponse,
    OptimizeRequest,
    ParetoPoint,
    ParetoResponse,
    ScenarioInfo,
)
from config import SCENARIOS  # noqa: E402  (module gốc của đồ án)

app = FastAPI(
    title="NSGA-II + SUMO Traffic Signal Optimization API",
    description="Bọc đồ án tối ưu tín hiệu giao thông (NSGA-II + SUMO) thành REST API.",
    version="1.0.0",
)

job_manager = JobManager(results_dir=get_results_base_dir())


def _job_to_response(job) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id,
        scenario=job.scenario,
        pop_size=job.pop_size,
        n_gen_max=job.n_gen_max,
        status=job.status.value,
        current_gen=job.current_gen,
        hv=job.hv,
        pareto_size=job.pareto_size,
        message=job.message,
        csv_path=job.csv_path,
        plot_path=job.plot_path,
        error=job.error,
    )


@app.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios():
    """Danh sách kịch bản khả dụng, đọc trực tiếp từ config.SCENARIOS gốc."""
    return [
        ScenarioInfo(key=k, total_hourly_demand=v["total_hourly_demand"], label=v["label"])
        for k, v in SCENARIOS.items()
    ]


@app.post("/jobs", response_model=JobStatusResponse, status_code=201)
def create_job(req: OptimizeRequest):
    """Tạo job NSGA-II mới. Trả về NGAY (không đợi chạy xong) với status=pending."""
    if req.scenario not in SCENARIOS:
        raise HTTPException(400, f"Kịch bản không hợp lệ. Có: {list(SCENARIOS)}")
    job = job_manager.submit(req.scenario, req.pop_size, req.n_gen_max)
    return _job_to_response(job)


@app.get("/jobs", response_model=list[JobStatusResponse])
def list_jobs():
    return [_job_to_response(j) for j in job_manager.list_jobs()]


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job")
    return _job_to_response(job)


@app.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str):
    ok = job_manager.cancel(job_id)
    if not ok:
        raise HTTPException(409, "Job không tồn tại hoặc đã kết thúc, không thể huỷ")
    return _job_to_response(job_manager.get(job_id))


@app.get("/jobs/{job_id}/pareto", response_model=ParetoResponse)
def get_pareto(job_id: str):
    """Trả về tập Pareto cuối (Rank=0) của job — chỉ khả dụng khi status=done."""
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job")
    if job.status.value != "done" or not job.csv_path:
        raise HTTPException(409, f"Job chưa hoàn thành (status={job.status.value})")

    import pandas as pd  # import cục bộ, tránh phụ thuộc pandas ở module-level nếu không cần

    df = pd.read_csv(job.csv_path)
    df_final_gen = df[df["Gen"] == df["Gen"].max()]
    pareto_df = df_final_gen[df_final_gen["Rank"] == 0].drop_duplicates(
        subset=["C", "g1_1", "g1_2", "g2_1", "g2_2", "Offset"]
    )

    points = [
        ParetoPoint(
            C=int(r.C), g1_1=int(r.g1_1), g1_2=int(r.g1_2),
            g2_1=int(r.g2_1), g2_2=int(r.g2_2), Offset=int(r.Offset),
            f1_control_delay=float(r.f1_mean_timeloss_s_per_veh),
            f2_co2=float(r.f2_co2_kg_per_veh),
        )
        for r in pareto_df.itertuples()
    ]
    return ParetoResponse(
        job_id=job_id, scenario=job.scenario, gen_final=int(df["Gen"].max()),
        n_points=len(points), points=points,
    )


@app.get("/jobs/{job_id}/plot")
def get_plot(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job")
    if not job.plot_path or not os.path.exists(job.plot_path):
        raise HTTPException(409, "Chưa có biểu đồ (job chưa hoàn thành hoặc bị lỗi)")
    return FileResponse(job.plot_path, media_type="image/png")


@app.get("/health")
def health():
    return {"status": "ok"}
