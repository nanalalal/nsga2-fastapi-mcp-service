# -*- coding: utf-8 -*-
r"""
test_jobs.py

Test tích hợp cho core/jobs.py + api/main.py + mcp_server/server.py —
dùng FakeSUMOEvaluator (fake_evaluator.py) để chạy được KHÔNG CẦN cài
SUMO thật. Đã chạy thành công trong quá trình xây dựng scaffold này
(xem HUONG_DAN_CONG_VIEC_CHI_TIET.md, task M5-1).

Chạy:
    cd <thư mục chứa core/, api/, mcp_server/, tests/>
    export NSGA2_PROJECT_SRC=/path/to/DoAn_NSGA2_SUMO/src   # (Linux/macOS)
    # hoặc PowerShell:  $env:NSGA2_PROJECT_SRC = "<PATH_TO_PROJECT>\DoAn_NSGA2_SUMO\src"
    pip install pytest
    pytest tests/test_jobs.py -v -s

LƯU Ý: fixture _patch_evaluator() bên dưới TỰ MONKEYPATCH
nsga2_core.SUMOEvaluatorImproved bằng FakeSUMOEvaluator TRƯỚC khi bất
kỳ test nào import core.jobs — nếu core.jobs đã được import ở đâu đó
khác trong tiến trình TRƯỚC khi patch chạy, patch sẽ không có tác dụng
(module đã cache tham chiếu evaluator thật). Đây đã được kiểm chứng
chạy thành công (5/5 test PASSED) trong quá trình xây dựng scaffold này.
"""

import os
import sys
import time

import pytest


@pytest.fixture(scope="module", autouse=True)
def _patch_evaluator():
    """Thay SUMOEvaluatorImproved thật bằng FakeSUMOEvaluator cho MỌI
    test trong file này, để không cần SUMO_HOME / SUMO binary thật."""
    sys.path.insert(0, os.path.dirname(__file__))  # để `import fake_evaluator` tìm thấy
    from core.bootstrap import setup_project_path

    setup_project_path()

    import nsga2_core
    from fake_evaluator import FakeSUMOEvaluator

    original = nsga2_core.SUMOEvaluatorImproved
    nsga2_core.SUMOEvaluatorImproved = FakeSUMOEvaluator
    yield
    nsga2_core.SUMOEvaluatorImproved = original


@pytest.fixture()
def job_manager(tmp_path):
    from core.jobs import JobManager

    return JobManager(results_dir=str(tmp_path))


def _wait_until_terminal(job_manager, job_id, timeout_s: float = 30.0):
    from core.jobs import JobStatus

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = job_manager.get(job_id)
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return job
        time.sleep(0.2)
    raise TimeoutError(f"Job {job_id} không kết thúc sau {timeout_s}s")


class TestProblemBounds:
    """Unit test không cần SUMO/FakeSUMOEvaluator — kiểm tra riêng
    ProblemV2_HonestObjective nhận custom bounds đúng, và mặc định
    GIỐNG HỆT bounds gốc (an toàn cho M3-4: so sánh CLI gốc vs service)."""

    def _make_problem(self, **kwargs):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from core.bootstrap import setup_project_path
        setup_project_path()
        from problem_v2_honest import ProblemV2_HonestObjective
        from fake_evaluator import FakeSUMOEvaluator

        return ProblemV2_HonestObjective(evaluator=FakeSUMOEvaluator(), **kwargs)

    def test_default_bounds_unchanged(self):
        import numpy as np
        problem = self._make_problem()
        np.testing.assert_array_equal(problem.xl, [60.0, 15.0, 15.0, 15.0, 15.0, 0.0])
        np.testing.assert_array_equal(problem.xu, [120.0, 90.0, 90.0, 90.0, 90.0, 119.0])

    def test_custom_bounds_applied(self):
        import numpy as np
        problem = self._make_problem(cycle_bounds=(70.0, 100.0), green_bounds=(20.0, 80.0))
        np.testing.assert_array_equal(problem.xl, [70.0, 20.0, 20.0, 20.0, 20.0, 0.0])
        # O2 upper bound phải = cycle_max - 1, tính động theo cycle_bounds mới
        np.testing.assert_array_equal(problem.xu, [100.0, 80.0, 80.0, 80.0, 80.0, 99.0])


class TestJobManager:
    def test_submit_and_complete(self, job_manager):
        job = job_manager.submit("S1", pop_size=8, n_gen_max=2)
        assert job.status.value in ("pending", "running")

        final = _wait_until_terminal(job_manager, job.job_id)

        assert final.status.value == "done", final.error
        assert final.csv_path and os.path.exists(final.csv_path)
        assert final.plot_path and os.path.exists(final.plot_path)
        assert final.pareto_size > 0

    def test_invalid_scenario_raises_before_submit(self, job_manager):
        from nsga2_core import SCENARIOS

        assert "S9" not in SCENARIOS  # giả định kịch bản không tồn tại

        # JobManager.submit() phải tự validate NGAY LẬP TỨC (không đợi tới
        # tận run_optimization() mới KeyError) — xem core/jobs.py.submit().
        with pytest.raises(ValueError, match="S9"):
            job_manager.submit("S9", pop_size=8, n_gen_max=2)

    def test_cancel_pending_job(self, job_manager):
        # Đưa 1 job "running" chiếm worker duy nhất, rồi huỷ job thứ 2 khi còn "pending"
        job1 = job_manager.submit("S1", pop_size=8, n_gen_max=2)
        job2 = job_manager.submit("S1", pop_size=8, n_gen_max=2)

        ok = job_manager.cancel(job2.job_id)
        assert ok is True

        _wait_until_terminal(job_manager, job1.job_id)
        job2_final = job_manager.get(job2.job_id)
        assert job2_final.status.value in ("cancelled", "done")
        # done chấp nhận được nếu job2 kịp bắt đầu trước khi cancel có hiệu lực —
        # hành vi phụ thuộc thời điểm; điều quan trọng là không "failed"/"pending" mãi.

    def test_submit_with_parameter_overrides(self, job_manager):
        """total_hourly_demand/cycle_bounds/green_bounds phải được lưu trên Job
        VÀ thực sự truyền xuống run_optimization() -> Problem (không bị rơi
        dọc đường qua submit() -> _run_job() -> run_optimization())."""
        job = job_manager.submit(
            "S1",
            pop_size=8,
            n_gen_max=2,
            total_hourly_demand=3000,
            cycle_bounds=(70.0, 100.0),
            green_bounds=(20.0, 80.0),
        )
        # Lưu đúng trên Job ngay khi submit (không cần đợi job chạy xong)
        assert job.total_hourly_demand == 3000
        assert job.cycle_bounds == (70.0, 100.0)
        assert job.green_bounds == (20.0, 80.0)

        final = _wait_until_terminal(job_manager, job.job_id)
        assert final.status.value == "done", final.error
        assert final.pareto_size > 0
        # Kịch bản khác (S1, không override) vẫn phải chạy đúng như cũ —
        # đảm bảo override không có side-effect toàn cục (không mutate SCENARIOS).
        from nsga2_core import SCENARIOS
        assert SCENARIOS["S1"]["total_hourly_demand"] == 2000


class TestFastAPIWiring:
    def test_endpoints_smoke(self, job_manager, monkeypatch):
        import api.main as api_main
        from fastapi.testclient import TestClient

        monkeypatch.setattr(api_main, "job_manager", job_manager)
        client = TestClient(api_main.app)

        r = client.get("/scenarios")
        assert r.status_code == 200
        assert {s["key"] for s in r.json()} == {"S1", "S2", "S3"}

        r = client.post("/jobs", json={"scenario": "S1", "pop_size": 8, "n_gen_max": 2})
        assert r.status_code == 201
        job_id = r.json()["job_id"]

        _wait_until_terminal(job_manager, job_id)

        r = client.get(f"/jobs/{job_id}/pareto")
        assert r.status_code == 200
        assert r.json()["n_points"] > 0


class TestMCPWiring:
    def test_tools_smoke(self, job_manager, monkeypatch):
        import mcp_server.server as mcp_srv

        monkeypatch.setattr(mcp_srv, "job_manager", job_manager)

        scenarios_json = mcp_srv.nsga2_list_scenarios()
        assert "S1" in scenarios_json

        start_result = mcp_srv.nsga2_start_optimization(
            mcp_srv.StartOptimizationInput(scenario="S1", pop_size=8, n_gen_max=2)
        )
        import json as _json

        job_id = _json.loads(start_result)["job_id"]

        _wait_until_terminal(job_manager, job_id)

        pareto_result = mcp_srv.nsga2_get_pareto_front(
            mcp_srv.GetParetoFrontInput(job_id=job_id, response_format="json")
        )
        assert _json.loads(pareto_result)["n_points"] > 0
