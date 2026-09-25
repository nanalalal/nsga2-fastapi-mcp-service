# -*- coding: utf-8 -*-
"""
fake_evaluator.py

Evaluator giả lập thay cho SUMOEvaluatorImproved — dùng để kiểm thử
JobManager, FastAPI, và MCP server MÀ KHÔNG CẦN cài SUMO / chạy mô
phỏng thật. Hữu ích cho CI hoặc máy dev không có SUMO_HOME.

Cách dùng: xem tests/test_jobs.py — inject FakeSUMOEvaluator vào chỗ
ProblemV2_HonestObjective(evaluator=...) thay vì SUMOEvaluatorImproved
thật, thông qua monkeypatch của pytest.

FakeSUMOEvaluator implement ĐÚNG interface mà ProblemV2_HonestObjective
cần — chỉ một method:
    evaluate(C, g1_1, g1_2, g2_1, g2_2, O2) -> (f1, f2, cv, f1_val)
Vì Python dùng duck typing, không cần kế thừa SUMOEvaluatorImproved.
"""

import random
from typing import Tuple


class FakeSUMOEvaluator:
    """Trả về giá trị mục tiêu NGẪU NHIÊN NHƯNG HỢP LÝ, không chạy SUMO.

    f1, f2 được sinh có tương quan nghịch nhẹ (giả lập trade-off Pareto
    thật) để NSGA-II có front không suy biến khi test — hữu ích hơn so
    với trả về hằng số cố định (front sẽ suy biến về 1 điểm).
    """

    def __init__(self, *args, seed: int = 0, **kwargs) -> None:
        # Chấp nhận mọi kwargs mà SUMOEvaluatorImproved thật nhận
        # (sumo_config_path, total_hourly_demand, scenario_id, ...) để
        # có thể "cắm thẳng" vào chỗ khởi tạo evaluator hiện có.
        self._rng = random.Random(seed)
        self.eval_count = 0

    def evaluate(
        self, C: int, g1_1: int, g1_2: int, g2_1: int, g2_2: int, O2: int, retry: int = 0
    ) -> Tuple[float, float, float, float]:
        self.eval_count += 1
        # f1 tỉ lệ nghịch (xấp xỉ) với tổng thời gian xanh -> chu kỳ dài,
        # xanh nhiều -> trễ thấp nhưng CO2 cao hơn (giả lập trade-off).
        green_ratio = (g1_1 + g1_2 + g2_1 + g2_2) / max(1, 4 * C)
        f1 = max(5.0, 60.0 * (1.0 - green_ratio) + self._rng.uniform(-2, 2))
        f2 = max(0.05, 0.10 + 0.20 * green_ratio + self._rng.uniform(-0.01, 0.01))
        cv = 0.0  # luôn khả thi trong bản giả lập
        f1_val = f1 * 1.05
        return f1, f2, cv, f1_val
