# -*- coding: utf-8 -*-
"""
schemas.py

Pydantic models cho FastAPI — định nghĩa hợp đồng request/response,
tách biệt với dataclass nội bộ (core.jobs.Job) để service có thể đổi
cấu trúc lưu trữ nội bộ mà không phá vỡ API công khai.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """Payload cho POST /jobs — yêu cầu chạy một job NSGA-II mới."""

    scenario: str = Field(..., description='Kịch bản: "S1", "S2" hoặc "S3"', examples=["S1"])
    pop_size: int = Field(60, ge=4, le=500, description="Kích thước quần thể NSGA-II")
    n_gen_max: int = Field(30, ge=1, le=200, description="Số thế hệ tối đa")


class JobStatusResponse(BaseModel):
    """Trạng thái job trả về cho client (polling)."""

    job_id: str
    scenario: str
    pop_size: int
    n_gen_max: int
    status: str
    current_gen: int
    hv: float
    pareto_size: int
    message: str
    csv_path: Optional[str] = None
    plot_path: Optional[str] = None
    error: Optional[str] = None


class ParetoPoint(BaseModel):
    """Một nghiệm trong tập Pareto cuối cùng — Phenotype 6 chiều + mục tiêu."""

    C: int
    g1_1: int
    g1_2: int
    g2_1: int
    g2_2: int
    offset: int = Field(..., alias="Offset")
    f1_control_delay: float = Field(..., description="s/xe")
    f2_co2: float = Field(..., description="kg/xe")

    model_config = {"populate_by_name": True}


class ParetoResponse(BaseModel):
    job_id: str
    scenario: str
    gen_final: int
    n_points: int
    points: List[ParetoPoint]


class ScenarioInfo(BaseModel):
    key: str
    total_hourly_demand: int
    label: str
