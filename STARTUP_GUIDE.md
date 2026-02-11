# ICCDDS 完整啟動指南

> 包含後端 API、前端 UI、以及 Docker 部署

---

## 📋 目錄

1. [快速啟動 (Docker)](#-docker-一鍵部署推薦)
2. [開發環境啟動](#-開發環境啟動)
   - [後端啟動](#後端-backend)
   - [前端啟動](#前端-frontend)
3. [完整工作流程](#-完整工作流程推薦)
4. [API 測試](#-api-快速測試)
5. [常見問題](#-常見問題)

---

## 🐳 Docker 一鍵部署（推薦）

### 前置要求
- Docker Desktop 或 Docker Engine
- Docker Compose

### 啟動所有服務

```bash
# 1. 複製環境變數檔案
cp .env.example .env

# 2. 編輯 .env（可選，修改密碼等）
# 預設帳號: admin / admin123

# 3. 啟動所有服務
docker-compose up -d

# 4. 查看服務狀態
docker-compose ps

# 5. 查看日誌
docker-compose logs -f
```

### 存取服務

| 服務 | URL | 說明 |
|------|-----|------|
| 前端 UI | http://localhost | React 前端界面 |
| API 文檔 | http://localhost:8000/docs | Swagger UI |
| API ReDoc | http://localhost:8000/redoc | ReDoc 文檔 |
| PostgreSQL | localhost:5432 | 資料庫 |
| Redis | localhost:6379 | 快取/訊息佇列 |

### 登入系統

- **帳號**: `admin`
- **密碼**: `admin123`

### 停止服務

```bash
# 停止並保留資料
docker-compose down

# 停止並清除資料
docker-compose down -v
```

---

## 🔧 開發環境啟動

如果需要在本地開發，請按以下步驟啟動：

### 前置要求

```bash
# Python 3.10+
python --version

# Node.js 18+
node --version

# npm 或 pnpm
npm --version
```

### 啟動資料庫服務 (Docker)

```bash
# 只啟動 PostgreSQL 和 Redis
docker-compose -f docker-compose.dev.yml up -d

# 驗證服務運行中
docker-compose -f docker-compose.dev.yml ps
```

### 後端 (Backend)

```bash
# 1. 安裝 Python 依賴
pip install -r requirements.txt

# 2. 複製環境變數
cp .env.example .env

# 3. 初始化資料庫（二擇一）
# 方式 A：全新資料庫（使用 Alembic 遷移，推薦）
psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE iccdds;"
psql -h localhost -p 5433 -U postgres -d iccdds -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -h localhost -p 5433 -U postgres -d iccdds -f app/db/schema.sql
alembic stamp 0001          # 標記 baseline 已套用
alembic upgrade head        # 套用 v3.1 遷移

# 方式 B：已有資料庫（只需套用新遷移）
alembic stamp 0001          # 若 Alembic 尚未追蹤，先標記 baseline
alembic upgrade head        # 套用所有新遷移

# 4. 啟動 Celery Worker（新終端機，Windows 需加 --pool=solo）
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo

# 5. 啟動 FastAPI（另一個新終端機）
python -m uvicorn app.main:app --reload --port 8000

# API 文檔: http://localhost:8000/docs
```

### 前端 (Frontend)

```bash
# 1. 進入前端目錄
cd frontend

# 2. 安裝依賴
npm install

# 3. 啟動開發伺服器
npm run dev

# 前端 UI: http://localhost:3000
```

### 開發環境服務總覽

| 終端機 | 指令 | 服務 |
|--------|------|------|
| 1 | `docker-compose -f docker-compose.dev.yml up -d` | PostgreSQL (port 5433) + Redis |
| - | `alembic upgrade head` | 套用資料庫遷移（首次或更新後執行） |
| 2 | `celery -A app.core.celery_app worker --loglevel=info --pool=solo` | Celery Worker |
| 3 | `uvicorn app.main:app --reload --port 8000` | FastAPI Backend |
| 4 | `cd frontend && npm run dev` | React Frontend |

---

## 🖥️ 前端功能說明

### 登入頁面
- 預設帳號: `admin` / `admin123`
- 支援中文/英文切換

### 儀表板 (Dashboard)
- 車輛總數、訂單總數
- 待配送訂單、今日完成數

### 車輛管理
- 新增/編輯/刪除車輛
- 設定載重、溫度範圍、冷卻速率等

### 訂單管理
- 新增/編輯/刪除訂單
- 設定配送地址、時間窗、優先順序等

### 路線優化
- **Excel 匯入**: 上傳 Excel 批量匯入車輛/訂單
- **優化參數**: 設定倉庫位置、環境溫度等
- **執行優化**: 非同步執行，顯示進度條

### 地圖檢視
- Leaflet 互動式地圖
- 多車輛路線顯示（不同顏色）
- 停靠點標記（溫度狀態）
- 圖層控制（顯示/隱藏特定車輛）

---

# ICCDDS 后端启动指南

## ✅ 目前完成的组件

### 1. **数据库层** (100%)
- ✅ PostgreSQL Schema with PostGIS (`app/db/schema.sql`)
- ✅ SQLAlchemy ORM Models (9个领域模型)
- ✅ 异步数据库连接 (`app/db/database.py`)
- ✅ Pydantic Schemas (8个 API schemas)

### 2. **OR-Tools 优化引擎** (100%)
- ✅ VRP 数据模型转换 (`app/services/solver/data_model.py`)
  - 距离矩阵计算 (Haversine公式)
  - 时间矩阵计算
  - 多时间窗处理

- ✅ 热力学回调函数 (`app/services/solver/callbacks.py`)
  - ΔT_drive 计算: `Time × (T_ambient - T_current) × K`
  - ΔT_door 计算: `Time × C_door × (1 - 0.5 × IsCurtain)`
  - ΔT_cooling 计算: `Time × Rate_cooling`

- ✅ 完整 VRP Solver (`app/services/solver/solver.py`)
  - 距离/时间/容量维度
  - 时间窗约束
  - Disjunction 处理 (STRICT vs STANDARD SLA)
  - 字典序目标 (车数 → 距离)
  - 温度预测和可行性检查

### 3. **Celery 异步任务** (100%)
- ✅ Celery 应用配置 (`app/core/celery_app.py`)
- ✅ 优化任务实现 (`app/services/tasks.py`)
  - 从 DB 加载车辆和订单
  - 构建 VRP 数据模型
  - 运行 OR-Tools 求解
  - 保存结果到 DB
  - 错误处理和重试机制

### 4. **FastAPI REST API** (100%)
- ✅ FastAPI 应用 (`app/main.py`)
- ✅ 车辆管理 (`app/api/v1/endpoints/vehicles.py`)
- ✅ 订单管理 (`app/api/v1/endpoints/shipments.py`)
- ✅ 路线查询 (`app/api/v1/endpoints/routes.py`)
- ✅ **异步优化 API** (`app/api/v1/endpoints/optimization.py`) ⭐

### 5. **配置管理** (100%)
- ✅ Pydantic Settings (`app/core/config.py`)
- ✅ 环境配置 (`.env.example`)

---

## 🚀 快速启动步骤

### 前置要求
```bash
# 1. Python 3.10+
python --version

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动 PostgreSQL 和 Redis
# 选项 A: Docker
docker run -d --name postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgis/postgis:latest
docker run -d --name redis -p 6379:6379 redis:latest

# 选项 B: 本地安装 (需要 PostGIS)
# PostgreSQL: psql 已运行
# Redis: redis-server 已运行
```

### 初始化数据库
```bash
# 1. 创建数据库
psql -h localhost -U postgres -c "CREATE DATABASE iccdds;"

# 2. 启用 PostGIS 扩展
psql -h localhost -U postgres -d iccdds -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 3. 导入 baseline schema
psql -h localhost -U postgres -d iccdds -f app/db/schema.sql

# 4. 套用 Alembic 迁移（v3.1 新表和字段）
alembic stamp 0001          # 标记 baseline 已存在
alembic upgrade head        # 套用后续迁移
```

### 配置环境变量
```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env (如果需要自定义)
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/iccdds
# REDIS_URL=redis://localhost:6379/0
# 等等
```

### 启动 Celery Worker
```bash
# 在单独的终端中启动 Worker
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default
```

### 启动 FastAPI
```bash
# 在另一个终端中启动 API 服务器
uvicorn app.main:app --reload --port 8000

# 访问:
# - API 文档: http://localhost:8000/api/v1/docs
# - ReDoc: http://localhost:8000/api/v1/redoc
# - Health: http://localhost:8000/health
```

---

## 🎯 完整工作流程（推荐）

以下是完整的操作流程，从导入数据到视觉化路线：

### 步骤 1: 使用 Excel 批量导入数据

```bash
# 1.1 生成 Excel 范例档
python generate_excel_template.py

# 1.2 用 Excel 编辑 ICCDDS_Import_Template.xlsx
#     - 修改「订单 (Shipments)」工作表中的订单数据
#     - 修改「车辆 (Vehicles)」工作表中的车辆数据
#     - 参考「使用说明」工作表了解各栏位意义

# 1.3 批量导入数据
python import_from_excel.py ICCDDS_Import_Template.xlsx
```

### 步骤 2: 执行路线优化

```bash
# 2.1 确认数据已导入
curl http://localhost:8000/api/v1/vehicles
curl http://localhost:8000/api/v1/shipments/pending

# 2.2 启动优化任务
curl -X POST http://localhost:8000/api/v1/optimization \
  -H "Content-Type: application/json" \
  -d '{
    "plan_date": "2024-01-30",
    "parameters": {
      "time_limit_seconds": 60,
      "strategy": "MINIMIZE_VEHICLES",
      "ambient_temperature": 30.0,
      "initial_vehicle_temp": -5.0
    }
  }'

# 2.3 查询优化结果（用返回的 job_id）
curl http://localhost:8000/api/v1/optimization/{job_id}
```

### 步骤 3: 视觉化路线地图

```bash
# 3.1 生成互动式地图（含实际道路路线）
python visualize_routes.py 2024-01-30

# 3.2 用浏览器打开生成的 HTML 档案
# Windows:
start routes_map_20240130.html
# macOS:
open routes_map_20240130.html
# Linux:
xdg-open routes_map_20240130.html
```

---

## 📊 Excel 批量导入详解

### 生成范例档
```bash
python generate_excel_template.py
```

会生成 `ICCDDS_Import_Template.xlsx`，包含：
- **使用说明**: 栏位说明和注意事项
- **订单 (Shipments)**: 3 笔范例订单
- **车辆 (Vehicles)**: 3 笔范例车辆

### Excel 栏位说明

**订单重要栏位：**
| 栏位 | 说明 | 范例 |
|------|------|------|
| `order_number` | 订单编号（唯一） | ORD-2024-001 |
| `latitude/longitude` | 经纬度 | 25.0330 / 121.5654 |
| `time_window_1_start/end` | 第一时间窗 (HH:MM) | 08:00 / 10:00 |
| `time_window_2_start/end` | 第二时间窗（选填） | 14:00 / 16:00 |
| `sla_tier` | STRICT 或 STANDARD | STRICT |
| `temp_limit_upper_celsius` | 最高允收温度 | 5.0 |

**车辆重要栏位：**
| 栏位 | 说明 | 范例 |
|------|------|------|
| `license_plate` | 车牌（唯一） | ABC-1234 |
| `capacity_weight_kg` | 载重容量 | 3000.0 |
| `insulation_grade` | PREMIUM/STANDARD/BASIC | STANDARD |
| `door_type` | ROLL 或 SWING | ROLL |
| `has_strip_curtains` | TRUE/FALSE | TRUE |
| `cooling_rate_celsius_per_min` | 制冷速率（负数） | -2.5 |

### 执行导入
```bash
python import_from_excel.py ICCDDS_Import_Template.xlsx
```

详细说明请参考 `EXCEL_IMPORT_GUIDE.md`

---

## 🗺️ 路线地图视觉化详解

### 查看示范地图（无需实际数据）
```bash
# 生成含实际道路路线的示范地图
python demo_map_with_routing.py

# 用浏览器打开
start demo_routes_map_routing.html
```

### 视觉化实际优化结果
```bash
# 含实际道路路线（默认，使用 OSRM 路由服务）
python visualize_routes.py 2024-01-30

# 使用直线路线（速度较快，跳过路由 API）
python visualize_routes.py 2024-01-30 --no-routing
```

### 地图功能
- 🛣️ **实际道路路线**: 路线沿实际道路显示（使用 OSRM）
- 📍 **多车辆颜色**: 不同车辆使用不同颜色
- 🔢 **停靠顺序**: 数字标签显示配送顺序
- 🌡️ **温度状态**: 绿色图标=正常，红色图标=超标
- 📊 **详细资讯**: 点击标记查看订单、温度、时间等
- 🎛️ **图层控制**: 显示/隐藏特定车辆路线
- 📏 **测量工具**: 测量地图上任意两点距离

详细说明请参考 `MAP_VISUALIZATION_GUIDE.md`

---

## 🧪 API 快速测试

### 1. 创建车辆（API 方式）
```bash
curl -X POST http://localhost:8000/api/v1/vehicles \
  -H "Content-Type: application/json" \
  -d '{
    "license_plate": "ABC-1234",
    "capacity_weight": 3000,
    "capacity_volume": 15,
    "insulation_grade": "STANDARD",
    "door_type": "ROLL",
    "has_strip_curtains": true,
    "cooling_rate": -2.5
  }'
```

### 2. 创建订单（API 方式）
```bash
curl -X POST http://localhost:8000/api/v1/shipments \
  -H "Content-Type: application/json" \
  -d '{
    "order_number": "ORD-001",
    "delivery_address": "台北市信義區",
    "latitude": 25.0330,
    "longitude": 121.5654,
    "weight": 100,
    "volume": 5,
    "time_windows": [
      {"start": "08:00", "end": "10:00"},
      {"start": "14:00", "end": "16:00"}
    ],
    "sla_tier": "STANDARD",
    "temp_limit_upper": 5.0,
    "service_duration": 15,
    "priority": 50
  }'
```

### 3. 查看待优化订单
```bash
curl http://localhost:8000/api/v1/shipments/pending
```

### 4. 启动异步优化 ⭐
```bash
curl -X POST http://localhost:8000/api/v1/optimization \
  -H "Content-Type: application/json" \
  -d '{
    "plan_date": "2024-01-30",
    "parameters": {
      "time_limit_seconds": 60,
      "strategy": "MINIMIZE_VEHICLES",
      "ambient_temperature": 30.0,
      "initial_vehicle_temp": -5.0
    }
  }'
```

### 5. 查询优化结果
```bash
curl http://localhost:8000/api/v1/optimization/{job_id}
```

### 6. 查看生成的路线
```bash
curl http://localhost:8000/api/v1/routes?plan_date=2024-01-30
```

### 7. 查看路线温度分析
```bash
curl http://localhost:8000/api/v1/routes/{route_id}/temperature-analysis
```

---

## ⚙️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI (8000)                       │
│  ┌──────────┬──────────┬────────┬──────────────────┐   │
│  │ Vehicles │ Shipments│ Routes │ Optimization API │   │
│  └──────────┴──────────┴────────┴──────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ (AsyncSession)
┌──────────────────────▼──────────────────────────────────┐
│             SQLAlchemy ORM + PostgreSQL                 │
│        (Vehicles, Shipments, Routes, Jobs, etc)        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              Celery Worker (async task)                 │
│  ┌────────────────────────────────────────────────┐    │
│  │  run_optimization (Celery Task)                │    │
│  │  1. Load vehicles & shipments from DB          │    │
│  │  2. Build VRP data model                       │    │
│  │  3. Run OR-Tools Solver                        │    │
│  │     - Distance/Time/Capacity callbacks         │    │
│  │     - Temperature predictions                  │    │
│  │  4. Save routes back to DB                     │    │
│  │  5. Update optimization job status             │    │
│  └────────────────────────────────────────────────┘    │
└──────────────┬──────────────────────────┬──────────────┘
               │ (Sync SQLAlchemy)        │ (Redis)
        ┌──────▼─────────┐        ┌───────▼────────┐
        │  PostgreSQL    │        │     Redis      │
        │   (Primary)    │        │ (Message Broker)
        └────────────────┘        └────────────────┘
```

---

## 📊 数据流示例

### 优化工作流

```
1. 用户 POST /api/v1/optimization
   ↓
2. API 验证: 是否有可用车辆? 是否有待优化订单?
   ↓
3. 创建 OptimizationJob (status: PENDING) 到 DB
   ↓
4. 调用 Celery: run_optimization.delay(job_id, plan_date, ...)
   ↓
5. 立即返回 HTTP 202 + job_id 给用户
   ↓
6. 用户使用 GET /api/v1/optimization/{job_id} 轮询状态
   ↓
7. Celery Worker 处理:
   a. 从 DB 加载 AVAILABLE 车辆
   b. 从 DB 加载 PENDING 订单
   c. 调用 build_vrp_data_model():
      - 构建位置节点
      - 构建车辆数据
      - 计算距离矩阵 (Haversine)
      - 计算时间矩阵
   d. 创建 ColdChainVRPSolver
   e. 调用 solver.solve():
      - 注册所有回调
      - 添加约束
      - 运行 OR-Tools
      - 计算温度预测
      - 返回 SolverResult
   f. 保存 Routes + RouteStops 到 DB
   g. 更新 Shipments 状态为 ASSIGNED
   h. 更新 OptimizationJob (status: COMPLETED, result_summary)
   ↓
8. 用户查询状态 → 获得结果!
```

---

## 🐛 常见问题

### Q: "ModuleNotFoundError: No module named 'ortools'"
```bash
# 解决:
pip install ortools>=9.8
```

### Q: "psycopg2: error (code XXXX) from server"
```bash
# 检查 PostgreSQL 是否运行
# 检查 PostGIS 是否安装: psql -d iccdds -c "SELECT PostGIS_version();"
```

### Q: "redis.exceptions.ConnectionError"
```bash
# 检查 Redis 是否运行
# redis-cli ping
```

### Q: Celery worker 没有执行任务
```bash
# 1. 检查 worker 是否启动
# 2. 查看 worker 日志
# 3. 确认 Broker URL 正确
# 4. 检查任务是否被 route 到正确的队列
```

---

## 📈 性能优化建议 (未来)

1. **数据库**:
   - 添加表分区 (按 plan_date)
   - 为常用查询添加物化视图

2. **Celery**:
   - 使用 Celery Beat 定时任务
   - 监控: Flower
   - 使用多个 worker 处理并发优化

3. **OR-Tools**:
   - 实现启发式初始解加速
   - 支持并行求解 (多个 vehicles)
   - 增量优化 (re-optimization)

4. **API**:
   - 添加缓存 (Redis)
   - 实现速率限制
   - 添加认证/授权

---

## ✅ 已完成功能

- [x] 後端 API (FastAPI + Celery)
- [x] 優化引擎 (OR-Tools VRP + 熱力學)
- [x] 資料庫 (PostgreSQL + PostGIS)
- [x] Excel 批量匯入 (`generate_excel_template.py`, `import_from_excel.py`)
- [x] 地圖視覺化 (`visualize_routes.py`, 含實際道路路線)
- [x] **前端 UI (React + Vite + Tailwind + shadcn/ui)**
  - [x] 登入頁面 (admin/admin123)
  - [x] 儀表板 Dashboard
  - [x] 車輛管理 CRUD
  - [x] 訂單管理 CRUD
  - [x] Excel 上傳功能
  - [x] 路線優化（非同步進度顯示）
  - [x] 地圖視覺化 (Leaflet)
  - [x] 中/英文 i18n 切換
  - [x] RWD 響應式設計
- [x] **Docker 部署配置**
  - [x] Frontend Dockerfile (Nginx)
  - [x] docker-compose.yml (全服務)
  - [x] docker-compose.dev.yml (開發用)

## 📝 下一步工作

- [ ] IoT 溫度資料接收 (WebSocket/MQTT)
- [ ] 即時監控和告警系統
- [ ] 資料庫遷移 (Alembic)
- [ ] 單元測試和整合測試
- [ ] 效能基準測試
- [ ] 後端 JWT 認證整合

---

## 📚 相關文檔

| 文檔 | 說明 |
|------|------|
| `README.md` | 系統總覽和快速入門 |
| `STARTUP_GUIDE.md` | 本文件 - 詳細啟動指南 |
| `AGENT.md` | 系統架構設計文檔 (V3.0) |
| `CLAUDE.md` | Claude Code 開發指南 |
| `EXCEL_IMPORT_GUIDE.md` | Excel 批量匯入詳細說明 |
| `MAP_VISUALIZATION_GUIDE.md` | 地圖視覺化詳細說明 |

---

## 🚀 快速參考卡

### 啟動指令速查

```bash
# === Docker 一鍵部署 ===
docker-compose up -d              # 啟動所有服務
docker-compose down               # 停止服務
docker-compose logs -f            # 查看日誌

# === 開發環境 ===
# 終端機 1: 資料庫
docker-compose -f docker-compose.dev.yml up -d
alembic upgrade head          # 套用資料庫遷移

# 終端機 2: Celery Worker（Windows 需加 --pool=solo）
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo

# 終端機 3: 後端 API
python -m uvicorn app.main:app --reload --port 8000

# 終端機 4: 前端 UI
cd frontend
npm install
npm run dev

# === 工具指令 ===
python generate_excel_template.py           # 產生 Excel 範本
python import_from_excel.py <file.xlsx>     # 匯入 Excel
python visualize_routes.py <date>           # 產生路線地圖
python demo_map_with_routing.py             # 產生示範地圖
```

### 服務 URL

| 環境 | 前端 | API | API 文檔 |
|------|------|-----|----------|
| Docker | http://localhost | http://localhost:8000 | http://localhost:8000/docs |
| 開發 | http://localhost:3000 | http://localhost:8000 | http://localhost:8000/docs |

### 預設帳號

- **帳號**: `admin`
- **密碼**: `admin123`

---

**系統已準備好運行！** 🚀
