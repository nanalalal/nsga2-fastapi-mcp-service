# -*- coding: utf-8 -*-
"""
schemas.py

Pydantic models cho FastAPI — định nghĩa hợp đồng request/response,
tách biệt với dataclass nội bộ (core.jobs.Job) để service có thể đổi
cấu trúc lưu trữ nội bộ mà không phá vỡ API công khai.
"""

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """Payload cho POST /jobs — yêu cầu chạy một job NSGA-II mới.

    total_hourly_demand / cycle_bounds / green_bounds là THAM SỐ có thể
    ghi đè (mặc định None = dùng giá trị gốc của kịch bản, hành vi không
    đổi). Đây KHÔNG phải cấu hình mạng lưới SUMO — network topology (số
    giao lộ, hình học đường) vẫn cố định theo `scenario`, muốn dùng giao
    lộ khác phải xây model SUMO mới, không thể chỉnh qua API này.
    """

    scenario: str = Field(..., description='Kịch bản: "S1", "S2" hoặc "S3"', examples=["S1"])
    pop_size: int = Field(60, ge=4, le=500, description="Kích thước quần thể NSGA-II")
    n_gen_max: int = Field(30, ge=1, le=200, description="Số thế hệ tối đa")
    total_hourly_demand: Optional[float] = Field(
        None,
        gt=0,
        description="Ghi đè lưu lượng xe/giờ (mặc định: giá trị gốc của kịch bản trong config.SCENARIOS).",
    )
    cycle_min: Optional[float] = Field(
        None, gt=0, description="Ghi đè cận dưới chu kỳ đèn C [giây] (mặc định 60)."
    )
    cycle_max: Optional[float] = Field(
        None, gt=0, description="Ghi đè cận trên chu kỳ đèn C [giây] (mặc định 120)."
    )
    green_min: Optional[float] = Field(
        None, gt=0, description="Ghi đè cận dưới thời gian xanh mỗi pha [giây] (mặc định 15)."
    )
    green_max: Optional[float] = Field(
        None, gt=0, description="Ghi đè cận trên thời gian xanh mỗi pha [giây] (mặc định 90)."
    )

    def cycle_bounds(self) -> Optional[Tuple[float, float]]:
        if self.cycle_min is None and self.cycle_max is None:
            return None
        return (self.cycle_min or 60.0, self.cycle_max or 120.0)

    def green_bounds(self) -> Optional[Tuple[float, float]]:
        if self.green_min is None and self.green_max is None:
            return None
        return (self.green_min or 15.0, self.green_max or 90.0)


class JobStatusResponse(BaseModel):
    """Trạng thái job trả về cho client (polling)."""

    job_id: str
    scenario: str
    pop_size: int
    n_gen_max: int
    total_hourly_demand: Optional[float] = None
    cycle_bounds: Optional[Tuple[float, float]] = None
    green_bounds: Optional[Tuple[float, float]] = None
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
