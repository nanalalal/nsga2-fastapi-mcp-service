# prepare_context.ps1
#
# Chuẩn bị build context cho Docker: copy mã nguồn GỐC của đồ án (src/,
# sumo_model_s1..s3/) vào thư mục docker/ để Dockerfile COPY được — Docker
# build KHÔNG đọc được file ngoài build context (ví dụ không thể COPY
# trực tiếp D:\DoAn_NSGA2_SUMO\src vào image nếu Dockerfile nằm ở chỗ khác).
#
# Chạy từ PowerShell, đứng trong thư mục docker/:
#   cd D:\đường_dẫn_tới_service\docker
#   .\prepare_context.ps1
#
# Sau khi chạy xong, kiểm tra docker/ có đủ:
#   project_src/, sumo_model_s1/, sumo_model_s2/, sumo_model_s3/
# trước khi `docker build`.

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\DoAn_NSGA2_SUMO"
$ScriptDir   = $PSScriptRoot

Write-Host "Copy $ProjectRoot\src -> $ScriptDir\project_src ..."
Remove-Item -Recurse -Force "$ScriptDir\project_src" -ErrorAction SilentlyContinue
Copy-Item -Recurse "$ProjectRoot\src" "$ScriptDir\project_src"
# Không cần copy __pycache__ cũ
Remove-Item -Recurse -Force "$ScriptDir\project_src\__pycache__" -ErrorAction SilentlyContinue

foreach ($scenario in @("sumo_model_s1", "sumo_model_s2", "sumo_model_s3")) {
    Write-Host "Copy $ProjectRoot\$scenario -> $ScriptDir\$scenario ..."
    Remove-Item -Recurse -Force "$ScriptDir\$scenario" -ErrorAction SilentlyContinue
    # Chỉ cần network.net.xml, routes.rou.xml, simulation.sumocfg — KHÔNG cần
    # copy output/ (có thể rất lớn, xem README gốc: emission.xml ~ 200MB+)
    New-Item -ItemType Directory -Force -Path "$ScriptDir\$scenario" | Out-Null
    Copy-Item "$ProjectRoot\$scenario\network.net.xml" "$ScriptDir\$scenario\"
    Copy-Item "$ProjectRoot\$scenario\routes.rou.xml" "$ScriptDir\$scenario\"
    Copy-Item "$ProjectRoot\$scenario\simulation.sumocfg" "$ScriptDir\$scenario\"
    New-Item -ItemType Directory -Force -Path "$ScriptDir\$scenario\output" | Out-Null
}

Write-Host ""
Write-Host "XONG. Nhắc lại: PHẢI sửa config.py (trong project_src/) trước khi build," `
    "vì đường dẫn sumo_cfg hiện hardcode kiểu D:\DoAn_NSGA2_VISSIM\... (Windows)," `
    "không tồn tại bên trong container Linux. Xem HUONG_DAN_CONG_VIEC_CHI_TIET.md, task M0-3."
