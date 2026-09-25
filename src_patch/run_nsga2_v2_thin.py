# -*- coding: utf-8 -*-
"""
run_nsga2_v2.py (phiên bản "thin wrapper")

Sau khi tách logic ra nsga2_core.py, file CLI này chỉ còn nhiệm vụ:
    1. Đọc tham số dòng lệnh (argparse).
    2. Gọi run_optimization() từ nsga2_core.
    3. Gọi save_results() để ghi CSV + PNG như hành vi gốc.

Hành vi dòng lệnh (cách gọi, output) GIỮ NGUYÊN 100% so với bản gốc:
    python run_nsga2_v2.py --scenario S1 --pop_size 60 --n_gen_max 30

=> Đây là bản THAY THẾ tùy chọn cho src/run_nsga2_v2.py hiện tại.
   Bạn có thể giữ file gốc và chỉ dùng nsga2_core.py cho service mới —
   không bắt buộc phải đổi file CLI. File này chỉ để tham khảo nếu muốn
   dọn dẹp, tránh trùng lặp logic giữa hai nơi.
"""

import argparse
import os

from nsga2_core import run_optimization, save_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", type=str, required=True, choices=["S1", "S2", "S3"],
        help="Bắt buộc nhập S1, S2 hoặc S3",
    )
    parser.add_argument("--pop_size", type=int, default=60)
    parser.add_argument("--n_gen_max", type=int, default=30)
    args = parser.parse_args()

    print(f"\n{'=' * 60}\nKỊCH BẢN: {args.scenario}\n{'=' * 60}\n")

    result = run_optimization(
        scenario=args.scenario,
        pop_size=args.pop_size,
        n_gen_max=args.n_gen_max,
    )

    results_dir = os.path.join(os.getcwd(), "results")
    save_results(result, results_dir)


if __name__ == "__main__":
    main()
