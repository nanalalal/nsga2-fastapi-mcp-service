#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client_example.py

Vi du mot CLIENT BEN NGOAI (khong can biet gi ve code Python goc cua du an,
chi can biet dia chi HTTP va "hop dong" JSON cua API) goi NSGA-II + SUMO
REST API de chay MOT JOB TOI UU THAT SU NHO (pop_size=8, n_gen_max=2) va
lay ket qua Pareto front ve.

Dung pop_size/n_gen_max nho o day CHI DE DEMO/TEST NHANH (vai chuc giay
den vai phut tuy toc do SUMO tren may) -- mac dinh that cua he thong la
pop_size=60, n_gen_max=30, chay hang gio CPU, khong phu hop de test nhanh.

Yeu cau truoc khi chay:
    1) Server dang chay o MOT terminal khac (da set NSGA2_PROJECT_SRC va
       cai du pymoo/traci/sumolib/SUMO that theo README goc):
           uvicorn api.main:app --port 8000
    2) pip install requests   (neu chua co san trong moi truong)

Chay:
    python examples/client_example.py

Neu goi tu MAY KHAC (khong phai localhost), doi BASE_URL ben duoi thanh
dia chi/IP that cua server, vi du "http://192.168.1.10:8000".
"""

import time

import requests

BASE_URL = "http://127.0.0.1:8000"


def wait_for_result(job_id: str, poll_every_s: float = 2.0, timeout_s: float = 600.0) -> dict:
    """Poll GET /jobs/{job_id} cho toi khi job ket thuc (done/failed/cancelled)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/jobs/{job_id}")
        r.raise_for_status()
        job = r.json()
        print(
            f"  [{job['status']:>10}] gen={job['current_gen']} "
            f"hv={job['hv']:.4f}  {job['message']}"
        )
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(poll_every_s)
    raise TimeoutError(f"Job {job_id} chua xong sau {timeout_s}s")


def main() -> None:
    # 1) Xem danh sach kich ban kha dung
    scenarios = requests.get(f"{BASE_URL}/scenarios").json()
    print("Kich ban kha dung:", scenarios)

    # 2) Tao MOT JOB NHO de chay nhanh, dong thoi demo tinh nang MOI:
    #    ghi de total_hourly_demand + signal-timing bounds qua request
    #    (khong can sua code/config tren server).
    payload = {
        "scenario": "S1",
        "pop_size": 8,
        "n_gen_max": 2,
        "total_hourly_demand": 1800,  # ghi de luu luong xe/gio (mac dinh S1 = 2000)
        "cycle_min": 70,
        "cycle_max": 100,
    }
    r = requests.post(f"{BASE_URL}/jobs", json=payload)
    r.raise_for_status()
    job = r.json()
    job_id = job["job_id"]
    print(f"\nDa tao job: {job_id} (status ban dau: {job['status']})")

    # 3) Poll toi khi xong (client ben ngoai KHONG duoc block server —
    #    day chinh la ly do API thiet ke theo kieu job-queue bat dong bo)
    print("\nDang theo doi tien do...")
    final_job = wait_for_result(job_id)

    if final_job["status"] != "done":
        print(f"\nJob KHONG thanh cong: {final_job['error']}")
        return

    # 4) Lay tap Pareto (ket qua toi uu cuoi cung)
    pareto = requests.get(f"{BASE_URL}/jobs/{job_id}/pareto").json()
    print(f"\nTap Pareto: {pareto['n_points']} nghiem (the he cuoi = {pareto['gen_final']})")
    for p in pareto["points"][:5]:
        print(
            f"  C={p['C']:>3}s  green=({p['g1_1']},{p['g1_2']},{p['g2_1']},{p['g2_2']})  "
            f"offset={p['offset']:>3}s  ->  delay={p['f1_control_delay']:.2f}s/xe, "
            f"CO2={p['f2_co2']:.4f}kg/xe"
        )


if __name__ == "__main__":
    main()
