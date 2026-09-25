# -*- coding: utf-8 -*-
"""
bootstrap.py

Kết nối service layer (FastAPI/MCP) với mã nguồn GỐC của đồ án
(D:\\DoAn_NSGA2_SUMO\\src), KHÔNG copy/paste lại code — tránh có hai
bản song song bị lệch nhau.

Cách hoạt động:
    Thêm thư mục src/ của đồ án gốc vào sys.path, để các câu lệnh
    `from nsga2_core import run_optimization` (hoặc `from config import
    SCENARIOS`) tìm thấy đúng module — y hệt cách run_nsga2_v2.py gốc
    tự "thấy" config.py vì nó nằm cùng thư mục.

Bắt buộc gọi setup_project_path() TRƯỚC khi import bất kỳ thứ gì từ
nsga2_core ở bất kỳ đâu trong service (api/main.py và mcp_server/server.py
đều gọi hàm này ở dòng đầu tiên).
"""

import os
import sys


def setup_project_path() -> str:
    """Thêm src/ của đồ án gốc vào sys.path.

    Đường dẫn lấy từ biến môi trường NSGA2_PROJECT_SRC — KHÔNG hardcode
    "D:\\DoAn_NSGA2_SUMO\\src" trong code, để service chạy được trên cả
    Windows lẫn máy khác (kể cả container Linux nếu sau này deploy).

    Returns:
        Đường dẫn tuyệt đối tới thư mục src/ đã thêm vào sys.path.

    Raises:
        EnvironmentError: Nếu biến môi trường NSGA2_PROJECT_SRC chưa được
            khai báo hoặc đường dẫn không tồn tại.
    """
    src_dir = os.environ.get("NSGA2_PROJECT_SRC")
    if not src_dir:
        raise EnvironmentError(
            "Vui lòng khai báo biến môi trường NSGA2_PROJECT_SRC trỏ tới "
            "thư mục src/ của đồ án gốc, ví dụ trên Windows:\n"
            '  setx NSGA2_PROJECT_SRC "D:\\DoAn_NSGA2_SUMO\\src"\n'
            "rồi mở lại terminal trước khi chạy FastAPI/MCP server."
        )
    if not os.path.isdir(src_dir):
        raise EnvironmentError(f"NSGA2_PROJECT_SRC trỏ tới thư mục không tồn tại: {src_dir}")

    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    return src_dir


def get_results_base_dir() -> str:
    """Thư mục gốc để service ghi kết quả job (results/<job_id>/...).

    Mặc định là <project_root>/results_service để KHÔNG lẫn với
    results/ gốc do chạy CLI trực tiếp — tránh nhầm lẫn giữa kết quả
    "chính thức" của luận văn và kết quả job thử nghiệm qua API.
    """
    src_dir = os.environ.get("NSGA2_PROJECT_SRC", "")
    project_root = os.path.dirname(src_dir) if src_dir else os.getcwd()
    return os.environ.get(
        "NSGA2_RESULTS_DIR", os.path.join(project_root, "results_service")
    )
