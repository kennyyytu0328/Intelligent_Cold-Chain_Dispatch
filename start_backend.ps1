# ICCDDS Backend Startup Script
# Sets correct database credentials before starting FastAPI

Write-Host "Starting ICCDDS Backend..." -ForegroundColor Green

# Set environment variables explicitly
$env:DATABASE_URL = "postgresql+asyncpg://iccdds:iccdds_password@localhost:5433/iccdds"
$env:DATABASE_URL_SYNC = "postgresql://iccdds:iccdds_password@localhost:5433/iccdds"

Write-Host "Database URL: $env:DATABASE_URL" -ForegroundColor Cyan

# Start uvicorn
uvicorn app.main:app --reload --port 8000
