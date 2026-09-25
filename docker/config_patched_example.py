# -*- coding: utf-8 -*-
"""
config_patched_example.py

VÍ DỤ sửa config.py gốc để hết hardcode đường dẫn Windows tuyệt đối —
điều kiện BẮT BUỘC để chạy được trong Docker (Linux). Đây là bản THAM
KHẢO, không tự động ghi đè config.py của bạn — copy nội dung phù hợp
vào D:\DoAn_NSGA2_SUMO\src\config.py sau khi đã hiểu rõ thay đổi.

Nguyên tắc: đường dẫn sumo_cfg tính TƯƠNG ĐỐI theo vị trí file config.py
(os.path.dirname(__file__)) thay vì hardcode "D:\\DoAn_NSGA2_VISSIM\\...".
Cách này chạy đúng cả khi:
  - chạy CLI trực tiếp trên Windows (như hiện tại),
  - chạy trong container Linux (đường dẫn Docker: /app/sumo_model_s1/...),
vì luôn suy ra từ vị trí file, không phụ thuộc hệ điều hành hay ổ đĩa.
"""

import os

# Thư mục gốc của đồ án = thư mục CHA của src/ (nơi chứa config.py này)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sumo_cfg_path(scenario_dir: str) -> str:
    """Ghép đường dẫn sumo_cfg tương đối theo _PROJECT_ROOT.

    Ví dụ trên Windows: D:\\DoAn_NSGA2_SUMO\\sumo_model_s1\\simulation.sumocfg
    Ví dụ trong Docker:  /app/sumo_model_s1/simulation.sumocfg
    (os.path.join tự dùng đúng dấu phân cách theo hệ điều hành.)
    """
    return os.path.join(_PROJECT_ROOT, scenario_dir, "simulation.sumocfg")


SCENARIOS = {
    "S1": {
        "total_hourly_demand": 2000,
        "label": "Duoi_bao_hoa_doi_xung",
        "sumo_cfg": _sumo_cfg_path("sumo_model_s1"),
    },
    "S2": {
        "total_hourly_demand": 2000,
        "label": "Duoi_bao_hoa_bat_doi_xung",
        "sumo_cfg": _sumo_cfg_path("sumo_model_s2"),
    },
    "S3": {
        "total_hourly_demand": 3600,
        "label": "Gan_bao_hoa_bat_doi_xung",
        "sumo_cfg": _sumo_cfg_path("sumo_model_s3"),
    },
}
