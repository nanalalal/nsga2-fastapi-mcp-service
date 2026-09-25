# Dockerfile — đóng gói FastAPI + MCP server + SUMO cho đồ án NSGA-II/SUMO.
#
# Build context PHẢI chứa (xem docker/prepare_context.ps1 để tự copy):
#   docker/project_src/        <- copy từ D:\DoAn_NSGA2_SUMO\src
#   docker/sumo_model_s1/      <- copy từ D:\DoAn_NSGA2_SUMO\sumo_model_s1
#   docker/sumo_model_s2/, docker/sumo_model_s3/  <- tương tự
#   requirements_project.txt   <- pymoo, traci, sumolib, pandas, matplotlib, numpy, scipy
#   requirements_service.txt   <- fastapi, uvicorn, pydantic, mcp[cli]
#   core/, api/, mcp_server/   <- service layer (đi kèm HUONG_DAN_TICH_HOP.md)
#
# Build:
#   cd docker
#   docker build -t nsga2-sumo-service:latest .
#
# LƯU Ý: image cài SUMO qua PPA chính thức của dự án SUMO cho Ubuntu.
# Nếu build fail vì PPA đổi địa chỉ, xem hướng dẫn cài đặt mới nhất tại
# https://sumo.dlr.de/docs/Installing/Linux_Build.html

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    SUMO_HOME=/usr/share/sumo \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Cài Python 3.10 + SUMO (qua PPA chính thức) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
        python3.10 python3-pip python3.10-venv \
        curl ca-certificates gnupg \
    && add-apt-repository -y ppa:sumo/stable \
    && apt-get update \
    && apt-get install -y --no-install-recommends sumo sumo-tools \
    && rm -rf /var/lib/apt/lists/*

# PYTHONPATH cho traci/sumolib (đi kèm cài đặt SUMO, không qua pip)
ENV PYTHONPATH="${SUMO_HOME}/tools:${PYTHONPATH}"

RUN python3.10 -m pip install --no-cache-dir --upgrade pip

WORKDIR /app

# --- Cài thư viện Python (tách 2 file để tận dụng Docker layer cache) ---
COPY requirements_project.txt requirements_service.txt ./
RUN pip install --no-cache-dir -r requirements_project.txt -r requirements_service.txt

# --- Mã nguồn GỐC của đồ án (không sửa nội dung, chỉ copy) ---
COPY project_src/ /app/project_src/
COPY sumo_model_s1/ /app/sumo_model_s1/
COPY sumo_model_s2/ /app/sumo_model_s2/
COPY sumo_model_s3/ /app/sumo_model_s3/

# --- Mã nguồn service layer mới ---
COPY core/ /app/core/
COPY api/ /app/api/
COPY mcp_server/ /app/mcp_server/

ENV NSGA2_PROJECT_SRC=/app/project_src \
    NSGA2_RESULTS_DIR=/app/results_service

RUN mkdir -p /app/results_service

# --- Chạy dưới user không phải root (an toàn hơn) ---
RUN useradd -m nsga2 && chown -R nsga2:nsga2 /app
USER nsga2

EXPOSE 8000 8765

# Mặc định chạy FastAPI. docker-compose.yml override "command" cho service mcp.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
