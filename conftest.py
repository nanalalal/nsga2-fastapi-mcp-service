# -*- coding: utf-8 -*-
"""
conftest.py

Dam bao thu muc goc cua service (nsga2_integration/, chua core/, api/,
mcp_server/) luon co trong sys.path khi chay `pytest` truc tiep.

Ly do can file nay: lenh `pytest ...` (khac voi `python -m pytest ...`)
KHONG tu them thu muc lam viec hien tai (cwd) vao sys.path. Vi tests/
khong co __init__.py, pytest tu chen tests/ vao sys.path (de tim duoc
fake_evaluator.py) nhung KHONG chen thu muc cha (nsga2_integration/) --
khien `from core.bootstrap import ...` bao loi
`ModuleNotFoundError: No module named 'core'` du core/ ton tai ngay do.

pytest luon import moi conftest.py trong rootdir TRUOC khi chay bat ky
fixture/test nao, nen chi can them dong sys.path.insert o day la du,
khong can sua gi trong tests/test_jobs.py.
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
