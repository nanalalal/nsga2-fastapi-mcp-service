#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — MCP server "nsga2_mcp" cho đồ án tối ưu tín hiệu giao thông
NSGA-II + SUMO.

Tuân theo mcp-builder best practices:
    - Tên server dạng {service}_mcp -> "nsga2_mcp"
    - Tên tool có prefix "nsga2_" + động từ hành động, tránh đụng tên
      với MCP server khác đang chạy cùng lúc trong client
    - Input validate bằng Pydantic (model_config extra="forbid")
    - Mỗi tool khai báo annotations (readOnlyHint/destructiveHint/
      idempotentHint/openWorldHint) để client (LLM) hiểu tác dụng phụ
      trước khi gọi — quan trọng vì nsga2_start_optimization có thể
      chạy hàng giờ và tốn CPU thật, LLM cần được cảnh báo rõ.
    - Docstring đầy đủ: mô tả, Args, Returns (schema JSON), Examples,
      Error Handling — đây là phần LLM đọc để quyết định gọi tool nào.
    - Trả lỗi dạng chuỗi "Error: ..." có gợi ý khắc phục, không raise
      exception thô ra ngoài.

Cài đặt:
    pip install "mcp[cli]"

Chạy độc lập (stdio — dùng khi khai báo trong Claude Desktop/Claude Code):
    python mcp_server/server.py

Chạy qua HTTP (khi container hoá / nhiều client cùng lúc — xem Dockerfile
và docker-compose.yml đi kèm):
    python mcp_server/server.py --http --port 8765
"""

import argparse
import json
from enum import Enum
from typing import List, Optional

from core.bootstrap import get_results_base_dir, setup_project_path

setup_project_path()

from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from core.jobs import JobManager  # noqa: E402
from config import SCENARIOS  # noqa: E402

# === Server & state ===

mcp = FastMCP("nsga2_mcp")
job_manager = JobManager(results_dir=get_results_base_dir())


# === Enums & Pydantic input models ===


class ResponseFormat(str, Enum):
    """Định dạng trả về của tool."""

    MARKDOWN = "markdown"
    JSON = "json"


class StartOptimizationInput(BaseModel):
    """Input cho nsga2_start_optimization."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    scenario: str = Field(
        ...,
        description='Khóa kịch bản mô phỏng, PHẢI là một trong "S1", "S2", "S3" '
        "(dùng nsga2_list_scenarios để xem chi tiết từng kịch bản trước khi chọn).",
    )
    pop_size: int = Field(
        default=60,
        ge=4,
        le=500,
        description="Kích thước quần thể NSGA-II. Mặc định 60 (giống CLI gốc). "
        "Giá trị nhỏ (ví dụ 6-10) hữu ích để chạy thử nhanh trước khi chạy đầy đủ.",
    )
    n_gen_max: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Số thế hệ tối đa. Mặc định 30. Thuật toán có thể dừng sớm hơn "
        "nếu Hypervolume không cải thiện (early stopping).",
    )


class JobIdInput(BaseModel):
    """Input cho các tool thao tác trên một job đã tồn tại."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    job_id: str = Field(
        ..., description="ID job trả về từ nsga2_start_optimization, ví dụ 'a1b2c3d4e5f6'."
    )


class GetParetoFrontInput(JobIdInput):
    """Input cho nsga2_get_pareto_front — kế thừa job_id, thêm response_format."""

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' để đọc nhanh (mặc định) hoặc 'json' để xử lý bằng code.",
    )


# === Shared helpers (tránh lặp code giữa các tool) ===


def _format_error(message: str, hint: Optional[str] = None) -> str:
    """Định dạng lỗi nhất quán cho mọi tool."""
    if hint:
        return f"Error: {message} {hint}"
    return f"Error: {message}"


def _load_pareto_points(csv_path: str) -> List[dict]:
    """Đọc CSV kết quả và trích tập Pareto (Rank=0) của thế hệ cuối.

    Tách thành hàm dùng chung để nsga2_get_pareto_front không phải là
    nơi duy nhất cần logic này nếu sau này thêm tool khác (ví dụ
    nsga2_compare_scenarios).
    """
    import pandas as pd

    df = pd.read_csv(csv_path)
    df_final = df[df["Gen"] == df["Gen"].max()]
    pareto_df = df_final[df_final["Rank"] == 0].drop_duplicates(
        subset=["C", "g1_1", "g1_2", "g2_1", "g2_2", "Offset"]
    )
    return [
        {
            "C": int(r.C), "g1_1": int(r.g1_1), "g1_2": int(r.g1_2),
            "g2_1": int(r.g2_1), "g2_2": int(r.g2_2), "offset": int(r.Offset),
            "f1_control_delay_s_per_veh": round(float(r.f1_mean_timeloss_s_per_veh), 4),
            "f2_co2_kg_per_veh": round(float(r.f2_co2_kg_per_veh), 6),
        }
        for r in pareto_df.itertuples()
    ]


# === Tools ===


@mcp.tool(
    name="nsga2_list_scenarios",
    annotations={
        "title": "Liệt kê kịch bản mô phỏng giao thông",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def nsga2_list_scenarios() -> str:
    """Liệt kê các kịch bản mô phỏng giao thông khả dụng (S1/S2/S3).

    Đọc trực tiếp từ config.py gốc của đồ án — không hardcode trong MCP
    server, nên luôn khớp với CLI (run_nsga2_v2.py --scenario ...).
    Gọi tool này TRƯỚC nsga2_start_optimization nếu chưa chắc kịch bản
    nào phù hợp với câu hỏi của người dùng (ví dụ "lưu lượng cao nhất").

    Returns:
        str: JSON object, khóa là mã kịch bản, giá trị gồm:
            {
              "S1": {"total_hourly_demand": 2000, "label": "Duoi_bao_hoa_doi_xung"},
              "S2": {...},
              "S3": {...}
            }

    Examples:
        - Dùng khi: "Kịch bản nào có lưu lượng cao nhất?" -> đọc total_hourly_demand.
        - Không dùng khi: đã biết chắc mã kịch bản (S1/S2/S3) rồi.
    """
    data = {
        k: {"total_hourly_demand": v["total_hourly_demand"], "label": v["label"]}
        for k, v in SCENARIOS.items()
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool(
    name="nsga2_start_optimization",
    annotations={
        "title": "Bắt đầu tối ưu hoá NSGA-II (chạy SUMO thật)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def nsga2_start_optimization(params: StartOptimizationInput) -> str:
    """Bắt đầu một job tối ưu hoá NSGA-II mới cho một kịch bản giao thông.

    CẢNH BÁO CHI PHÍ: tool này chạy mô phỏng SUMO THẬT qua TraCI, tốn CPU
    thực. Với tham số mặc định (pop_size=60, n_gen_max=30) một job có thể
    chạy TỚI VÀI GIỜ (README gốc ước tính ~2h CPU/kịch bản). Hàm trả về
    NGAY LẬP TỨC với job_id và status="pending" — KHÔNG đợi job chạy
    xong. Dùng nsga2_get_job_status(job_id) lặp lại để theo dõi tiến độ.

    Nếu người dùng chỉ muốn "thử nhanh xem có chạy được không", hãy dùng
    pop_size nhỏ (6-10) và n_gen_max nhỏ (2-3) trước khi chạy đầy đủ.

    Chỉ một job chạy tại một thời điểm (hàng đợi tuần tự) — nếu có job
    khác đang "running", job mới sẽ ở trạng thái "pending" cho tới khi
    tới lượt.

    Args:
        params (StartOptimizationInput): Tham số đã validate gồm:
            - scenario (str): "S1" | "S2" | "S3"
            - pop_size (int): kích thước quần thể, mặc định 60
            - n_gen_max (int): số thế hệ tối đa, mặc định 30

    Returns:
        str: JSON object:
        {
          "job_id": str,     # dùng cho các tool khác (get_job_status, cancel_job, get_pareto_front)
          "status": "pending",
          "scenario": str
        }

        Lỗi: "Error: Kịch bản không hợp lệ. Có: ['S1', 'S2', 'S3']"

    Examples:
        - Dùng khi: "Chạy tối ưu cho kịch bản S1" -> params.scenario="S1".
        - Dùng khi: "Thử nhanh S2 trước" -> pop_size=8, n_gen_max=2.
        - Không dùng khi: chỉ muốn xem kết quả CŨ đã có sẵn trong results/
          (tool này KHÔNG đọc kết quả cũ, chỉ tạo job MỚI).

    Error Handling:
        - scenario không nằm trong SCENARIOS -> trả lỗi kèm danh sách hợp lệ.
    """
    if params.scenario not in SCENARIOS:
        return _format_error(
            f"Kịch bản '{params.scenario}' không hợp lệ.",
            f"Các kịch bản hợp lệ: {list(SCENARIOS)}. Gọi nsga2_list_scenarios để xem chi tiết.",
        )
    job = job_manager.submit(params.scenario, params.pop_size, params.n_gen_max)
    return json.dumps(
        {"job_id": job.job_id, "status": job.status.value, "scenario": job.scenario},
        indent=2, ensure_ascii=False,
    )


@mcp.tool(
    name="nsga2_get_job_status",
    annotations={
        "title": "Tra cứu tiến độ job tối ưu hoá",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def nsga2_get_job_status(params: JobIdInput) -> str:
    """Tra cứu tiến độ một job đã tạo bằng nsga2_start_optimization.

    Gọi lặp lại tool này (polling) để theo dõi một job đang chạy — mỗi
    lần gọi trả về trạng thái TẠI THỜI ĐIỂM GỌI, không tự động chờ tới
    khi xong. Khoảng cách hợp lý giữa các lần gọi: 10-30 giây (mỗi thế
    hệ NSGA-II mất từ vài chục giây tới vài phút tuỳ pop_size).

    Args:
        params (JobIdInput): job_id lấy từ nsga2_start_optimization.

    Returns:
        str: JSON object:
        {
          "job_id": str,
          "scenario": str,
          "status": "pending" | "running" | "done" | "failed" | "cancelled",
          "current_gen": int,       # thế hệ hiện tại
          "n_gen_max": int,
          "hv": float,              # Hypervolume chuẩn hoá hiện tại
          "pareto_size": int,       # số nghiệm Rank=0 hiện tại
          "message": str,
          "error": str | null       # chi tiết lỗi nếu status="failed"
        }

        Lỗi: "Error: Không tìm thấy job_id=<id>. ..."

    Examples:
        - Dùng khi: vừa gọi nsga2_start_optimization và muốn biết đã chạy tới đâu.
        - Dùng khi: người dùng hỏi "tối ưu xong chưa?".

    Error Handling:
        - job_id không tồn tại -> gợi ý dùng nsga2_list_jobs để xem job hiện có.
    """
    job = job_manager.get(params.job_id)
    if job is None:
        return _format_error(
            f"Không tìm thấy job_id={params.job_id}.",
            "Dùng nsga2_list_jobs để xem các job hiện có trong tiến trình này.",
        )
    return json.dumps(
        {
            "job_id": job.job_id,
            "scenario": job.scenario,
            "status": job.status.value,
            "current_gen": job.current_gen,
            "n_gen_max": job.n_gen_max,
            "hv": round(job.hv, 6),
            "pareto_size": job.pareto_size,
            "message": job.message,
            "error": job.error,
        },
        indent=2, ensure_ascii=False,
    )


@mcp.tool(
    name="nsga2_list_jobs",
    annotations={
        "title": "Liệt kê tất cả job trong tiến trình MCP server này",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def nsga2_list_jobs() -> str:
    """Liệt kê mọi job đã tạo trong tiến trình MCP server hiện tại.

    LƯU Ý PHẠM VI: chỉ thấy job tạo qua MCP server này, KHÔNG thấy job
    tạo qua FastAPI (hai service chạy hai tiến trình riêng, mỗi bên giữ
    JobManager độc lập — xem HUONG_DAN_TICH_HOP.md mục "Chia sẻ trạng
    thái giữa hai service" nếu cần hợp nhất).

    Returns:
        str: JSON array các object rút gọn:
        [{"job_id": str, "scenario": str, "status": str, "current_gen": int}, ...]

    Examples:
        - Dùng khi: "Có job nào đang chạy không?"
        - Dùng khi: quên job_id, cần tra lại.
    """
    jobs = [
        {"job_id": j.job_id, "scenario": j.scenario, "status": j.status.value, "current_gen": j.current_gen}
        for j in job_manager.list_jobs()
    ]
    return json.dumps(jobs, indent=2, ensure_ascii=False)


@mcp.tool(
    name="nsga2_cancel_job",
    annotations={
        "title": "Huỷ job tối ưu hoá đang chạy hoặc đang chờ",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def nsga2_cancel_job(params: JobIdInput) -> str:
    """Yêu cầu huỷ một job đang "running" hoặc "pending".

    Job KHÔNG dừng ngay lập tức — nó dừng SAU KHI hoàn tất thế hệ NSGA-II
    hiện tại (có thể mất thêm vài chục giây), vì SUMO đang mô phỏng dở
    không thể ngắt an toàn giữa chừng. Gọi nsga2_get_job_status sau đó để
    xác nhận status đã chuyển sang "cancelled".

    Args:
        params (JobIdInput): job_id cần huỷ.

    Returns:
        str: JSON object {"cancelled": bool}. False nếu job không tồn
        tại hoặc đã ở trạng thái kết thúc (done/failed/cancelled).

    Examples:
        - Dùng khi: người dùng nói "dừng job lại", "huỷ tối ưu đi".
        - Không dùng khi: job đã "done" (không có gì để huỷ).
    """
    ok = job_manager.cancel(params.job_id)
    return json.dumps({"cancelled": ok}, indent=2)


@mcp.tool(
    name="nsga2_get_pareto_front",
    annotations={
        "title": "Lấy tập nghiệm Pareto của job đã hoàn thành",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def nsga2_get_pareto_front(params: GetParetoFrontInput) -> str:
    """Lấy tập nghiệm Pareto cuối cùng (Rank=0) của một job đã "done".

    Mỗi nghiệm gồm 6 biến quyết định vật lý — C (chu kỳ đèn, giây), g1_1/
    g1_2 (thời gian xanh 2 pha tại nút J1), g2_1/g2_2 (tương tự tại J2),
    offset (độ lệch pha J2, giây) — và 2 giá trị mục tiêu: f1 (trễ điều
    khiển trung bình, s/xe — càng THẤP càng tốt) và f2 (phát thải CO2
    trung bình, kg/xe — càng THẤP càng tốt). Đây là dữ liệu để giải
    thích trade-off cho người dùng (ví dụ: nghiệm nào giảm trễ nhưng
    tăng phát thải, và ngược lại).

    Args:
        params (GetParetoFrontInput): job_id + response_format.

    Returns:
        str: Nếu response_format="json":
        {
          "job_id": str, "scenario": str, "n_points": int,
          "points": [
            {"C": int, "g1_1": int, "g1_2": int, "g2_1": int, "g2_2": int,
             "offset": int, "f1_control_delay_s_per_veh": float,
             "f2_co2_kg_per_veh": float}, ...
          ]
        }
        Nếu response_format="markdown": bảng Markdown tương đương, dễ đọc
        trực tiếp trong hội thoại.

        Lỗi: "Error: Job chưa hoàn thành (status=running). ..."

    Examples:
        - Dùng khi: status của job đã là "done" và người dùng muốn xem/
          so sánh các phương án đèn tín hiệu.
        - Không dùng khi: job chưa "done" — gọi nsga2_get_job_status trước.

    Error Handling:
        - job_id không tồn tại hoặc job chưa xong -> lỗi kèm trạng thái hiện tại.
    """
    job = job_manager.get(params.job_id)
    if job is None:
        return _format_error(f"Không tìm thấy job_id={params.job_id}.")
    if job.status.value != "done" or not job.csv_path:
        return _format_error(
            f"Job chưa hoàn thành (status={job.status.value}).",
            "Dùng nsga2_get_job_status để theo dõi tới khi status='done'.",
        )

    points = _load_pareto_points(job.csv_path)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {"job_id": params.job_id, "scenario": job.scenario, "n_points": len(points), "points": points},
            indent=2, ensure_ascii=False,
        )

    lines = [
        f"# Tập Pareto — job {params.job_id} (kịch bản {job.scenario})",
        "",
        f"{len(points)} nghiệm không bị trội (Rank=0):",
        "",
        "| C | g1_1 | g1_2 | g2_1 | g2_2 | offset | f1 (s/xe) | f2 (kg/xe) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in points:
        lines.append(
            f"| {p['C']} | {p['g1_1']} | {p['g1_2']} | {p['g2_1']} | {p['g2_2']} | "
            f"{p['offset']} | {p['f1_control_delay_s_per_veh']} | {p['f2_co2_kg_per_veh']} |"
        )
    return "\n".join(lines)


def main() -> None:
    """Entry point — hỗ trợ cả stdio (mặc định) và streamable HTTP (--http).

    stdio: dùng khi MCP client (Claude Desktop/Claude Code) tự spawn tiến
    trình này làm subprocess — phù hợp chạy local, một người dùng.

    streamable HTTP: dùng khi container hoá (xem Dockerfile/docker-compose
    đi kèm) và cần nhiều client kết nối cùng lúc qua mạng.
    """
    parser = argparse.ArgumentParser(description="nsga2_mcp server")
    parser.add_argument("--http", action="store_true", help="Chạy qua Streamable HTTP thay vì stdio")
    parser.add_argument("--host", default="127.0.0.1", help="Host khi dùng --http (mặc định 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port khi dùng --http")
    args = parser.parse_args()

    if args.http:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
