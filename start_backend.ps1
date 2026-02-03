# ICCDDS Backend Startup Script
# IMPORTANT: Create a .env file with your database credentials before running
# See .env.example for template

Write-Host "Starting ICCDDS Backend..." -ForegroundColor Green

# Check if .env file exists
if (-Not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.example to .env and set your credentials" -ForegroundColor Yellow
    Write-Host "Example: cp .env.example .env" -ForegroundColor Cyan
    exit 1
}

# Load .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.+?)\s*$') {
        $name = $matches[1]
        $value = $matches[2]
        Set-Item -Path "env:$name" -Value $value
    }
}

Write-Host "Environment loaded from .env" -ForegroundColor Green
Write-Host "Database: $env:DATABASE_URL" -ForegroundColor Cyan

# Start uvicorn
uvicorn app.main:app --reload --port 8000
