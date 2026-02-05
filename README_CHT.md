# ICCDDS - 智慧冷鏈動態調度系統

**具熱力學限制的 VRPTW 車輛路由最佳化系統**

## 目錄

- [系統特色](#-系統特色)
- [系統架構](#️-系統架構)
- [資料庫設計](#-資料庫設計)
- [快速開始](#-快速開始)
- [Excel 批次匯入](#-excel-批次匯入)
- [路線地圖視覺化](#️-路線地圖視覺化)
- [API 範例](#-api-範例)
- [完整性檢查](#-完整性檢查)
- [檔案清單](#-檔案清單)
- [疑難排解](#-疑難排解)
- [效能指標](#-效能指標)
- [學習資源](#-學習資源)
- [支援](#-支援)
- [授權](#-授權)

---

## 🎯 系統特色

### 核心最佳化能力
- ✅ **VRPTW 求解器**：具時間窗的車輛路由問題（Vehicle Routing Problem with Time Windows）
- ✅ **多重時間窗**：單筆貨運可設定多個配送時段（OR 關係）
- ✅ **熱力學模型**：即時溫度追蹤（3 個關鍵公式）
- ✅ **SLA 分級**：STRICT（硬限制） vs STANDARD（軟限制）
- ✅ **容量限制**：重量與體積雙重限制
- ✅ **非同步最佳化**：Celery + Redis 長任務處理
- ✅ **Web UI**：React 儀表板，最佳化進度即時監控
- ✅ **Docker 部署**：docker-compose 一鍵部署

### 熱力學公式
```text
ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation
ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)
ΔT_cooling = Time_drive × Rate_cooling
```

### 最佳化目標（字典序）
1. **Level 0**：滿足硬限制（STRICT SLA 時間窗、溫度上限）
2. **Level 1**：最小化車隊數量
3. **Level 2**：最小化總距離與總時間
4. **Level 3**：最大化緩衝時間（降低緊急風險）

---

## 🏗️ 系統架構

### 技術棧
```text
┌─────────────────────────────────────┐
│  Frontend: React + Vite + Tailwind  │
│  (Leaflet Maps + shadcn/ui)        │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Backend: FastAPI + SQLAlchemy      │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Database: PostgreSQL + PostGIS     │
│  Cache/Queue: Redis                 │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Optimizer: Google OR-Tools (VRP)   │
│  Task Queue: Celery Workers         │
└─────────────────────────────────────┘
```

### 核心模組

| 模組 | 檔案 | 說明 |
|------|------|------|
| **Frontend UI** | `frontend/` | React + Vite + Tailwind CSS + shadcn/ui |
| **ORM Models** | `app/models/` | 9 個領域模型（Vehicle, Shipment, Route 等） |
| **API Schemas** | `app/schemas/` | 8 個 Pydantic 請求/回應 Schema |
| **OR-Tools** | `app/services/solver/` | VRP 求解器 + 熱力學計算 |
| **API Endpoints** | `app/api/v1/endpoints/` | 7 個 REST API 模組 |
| **Async Tasks** | `app/services/tasks.py` | Celery 最佳化任務 |
| **Configuration** | `app/core/` | 應用設定與 Celery 設定 |

---

## 📊 資料庫設計

### 主要資料表
- **vehicles**：車輛（含熱力學參數）
- **shipments**：貨運（支援多重時間窗）
- **routes**：最佳化路線
- **route_stops**：路線停靠點（含溫度預測）
- **optimization_jobs**：非同步任務追蹤
- **temperature_logs**：IoT 感測器資料
- **alerts**：警示紀錄（溫度/SLA 違規）

### 重要欄位
```sql
-- Vehicle: 熱力學參數
k_value              -- 隔熱係數
door_coefficient     -- 車門係數
has_strip_curtains   -- 防風條簾（可降低 50% 熱量流失）
cooling_rate         -- 冷卻速率（°C/min）

-- Shipment: 多重時間窗 + 溫度
time_windows         -- JSONB: [{"start":"08:00","end":"10:00"}, ...]
temp_limit_upper     -- 最高允許溫度（硬限制）
sla_tier             -- STRICT 或 STANDARD

-- RouteStop: 溫度預測
predicted_arrival_temp    -- 關鍵限制點
transit_temp_rise         -- ΔT_drive
service_temp_rise         -- ΔT_door
cooling_applied           -- ΔT_cooling
```

---

## 🚀 快速開始

### 方案 1：Docker 部署（建議）

**先決條件：** Docker Desktop 或 Docker Engine + Docker Compose

```bash
# 1. 複製專案並進入目錄
cd Intelligent_Cold-Chain_Dispatch

# 2. 複製環境變數
cp .env.example .env

# 3. 啟動所有服務（Frontend + Backend + Database + Redis + Celery）
docker-compose up -d

# 4. 查看服務狀態
docker-compose ps

# 5. 查看日誌
docker-compose logs -f
```

**服務入口：**
- 🌐 前端 UI：http://localhost
- 📡 API 文件：http://localhost:8000/docs
- 🔐 登入：`admin` / `admin123`

**停止服務：**
```bash
# 停止並保留資料
docker-compose down

# 停止並移除所有資料
docker-compose down -v
```

### 方案 2：開發環境

**先決條件：** Python 3.10+、Node.js 18+、PostgreSQL、Redis

```bash
# Terminal 1：只啟動資料庫
docker-compose -f docker-compose.dev.yml up -d

# Terminal 2：後端 API
pip install -r requirements.txt
cp .env.example .env
psql -h localhost -U postgres -c "CREATE DATABASE iccdds;"
psql -h localhost -U postgres -d iccdds -f app/db/schema.sql
uvicorn app.main:app --reload --port 8000

# Terminal 3：Celery Worker
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default

# Terminal 4：前端
cd frontend
npm install
npm run dev
```

**服務入口：**
- 🌐 前端：http://localhost:3000
- 📡 API 文件：http://localhost:8000/docs

---

## 📊 Excel 批次匯入

系統提供 Excel 批次匯入功能，方便快速建立貨運與車輛資料。

### 快速開始
```bash
# 1. 產生 Excel 範本
python generate_excel_template.py

# 2. 使用 Excel 編輯 ICCDDS_Import_Template.xlsx（新增或修改資料）

# 3. 啟動 API 伺服器
uvicorn app.main:app --reload --port 8000

# 4. 執行批次匯入
python import_from_excel.py ICCDDS_Import_Template.xlsx
```

### Excel 範本內容
`ICCDDS_Import_Template.xlsx` 內含 3 個工作表：

| 工作表 | 說明 |
|--------|------|
| **Instructions** | 欄位說明與注意事項 |
| **Shipments** | 貨運範例：地址、座標、時間窗、溫度上限、SLA 分級等 |
| **Vehicles** | 車輛範例：載重、體積、隔熱等級、車門類型、冷卻速率等 |

### 關鍵欄位說明

**Shipment 欄位：**
- `time_window_1_start/end`：第一個時間窗（HH:MM）
- `time_window_2_start/end`：第二個時間窗（選填，支援多重時間窗）
- `sla_tier`：STRICT（必須滿足）或 STANDARD（可延遲）
- `temp_limit_upper_celsius`：最高允許溫度

**Vehicle 欄位：**
- `insulation_grade`：PREMIUM (K=0.02) / STANDARD (K=0.05) / BASIC (K=0.10)
- `door_type`：ROLL（捲門）或 SWING（對開門）
- `has_strip_curtains`：TRUE/FALSE（防風條簾可降低 50% 熱量流失）
- `cooling_rate_celsius_per_min`：冷卻速率（負值，例如 -2.5）

詳細操作說明請參考 `EXCEL_IMPORT_GUIDE.md`

---

## 🗺️ 路線地圖視覺化

系統支援在互動式地圖上呈現最佳化配送路線，**並可顯示真實道路路徑**。

### 快速開始
```bash
# 觀看示範地圖（含真實道路路徑）
python demo_map_with_routing.py
# 以瀏覽器開啟 demo_routes_map_routing.html

# 視覺化實際最佳化結果（需先完成最佳化）
python visualize_routes.py 2024-01-30

# 使用直線路徑（不呼叫路由 API、速度更快）
python visualize_routes.py 2024-01-30 --no-routing
```

### 地圖功能
| 功能 | 說明 |
|------|------|
| 🛣️ **真實道路路由** | 使用 OSRM 路由服務，路線依實際道路生成 |
| 📍 **多車輛配色** | 不同車輛使用不同顏色（最多 12 輛） |
| 🔢 **停靠順序** | 數字標籤顯示配送順序 |
| 🌡️ **溫度狀態** | 綠色＝正常、紅色＝超標 |
| 📊 **詳細資訊** | 點擊標記可查看貨運、溫度、時間等資訊 |
| 🎛️ **圖層控制** | 顯示/隱藏指定車輛路線 |
| 📏 **測距工具** | 量測任意兩點距離 |
| 🔍 **全螢幕模式** | 放大查看路線細節 |

### 示範地圖
系統提供多個示範地圖供測試：

| 檔案 | 說明 |
|------|------|
| `demo_routes_map_routing.html` | 真實道路路由（建議） |
| `demo_routes_map_fixed.html` | 直線路徑 |

詳細操作說明請參考 `MAP_VISUALIZATION_GUIDE.md`

---

## 🖥️ Web UI 功能

系統包含完整的 React 前端介面：

### 儀表板
- 即時統計（車輛數、貨運數、待配送）
- 關鍵操作快捷按鈕
- 系統狀態總覽

### 車輛管理
- ✅ 新增、編輯、刪除車輛
- ✅ 設定熱力學參數（隔熱等級、車門類型、冷卻速率）
- ✅ 設定容量限制（重量、體積）
- ✅ 管理車輛可用狀態

### 貨運管理
- ✅ 新增、編輯、刪除貨運
- ✅ 設定多重時間窗（OR 關係）
- ✅ 設定溫度上限與 SLA 分級
- ✅ 支援批次操作

### 路線最佳化
- ✅ **Excel 匯入**：上傳 XLSX 進行批次資料匯入
- ✅ **最佳化參數**：設定倉庫位置、環境溫度、時間限制
- ✅ **非同步執行**：即時進度追蹤與狀態更新
- ✅ **結果視覺化**：在互動式地圖上檢視路線

### 互動式地圖
- 🗺️ **Leaflet 整合**：縮放與拖曳
- 🚗 **多車輛路線**：每台車輛不同顏色（最多 12）
- 📍 **停靠點標記**：顯示配送順序
- 🌡️ **溫度指標**：顏色顯示溫度狀態（綠色=OK、紅色=違規）
- 🎛️ **圖層控制**：切換指定車輛路線顯示
- 📊 **資訊彈窗**：點擊標記查看詳細貨運資訊

### 國際化
- 🌍 英文（en）/ 繁體中文（zh-TW）切換
- UI 標籤與訊息完整在地化

### 響應式設計
- 📱 行動裝置友善
- 💻 桌面最佳化
- 🎨 Tailwind CSS 現代風格

---

## 📡 API 範例

### 1. 啟動最佳化任務
```http
POST /api/v1/optimization
```

**Request Body:**
```json
{
  "plan_date": "2024-01-30",
  "parameters": {
    "time_limit_seconds": 60,
    "strategy": "MINIMIZE_VEHICLES",
    "ambient_temperature": 30.0
  }
}
```

**Response (HTTP 202):**
```json
{
  "job_id": "abc123...",
  "status": "PENDING",
  "celery_task_id": "xyz789...",
  "shipment_count": 10,
  "vehicle_count": 4
}
```

### 2. 查詢最佳化結果
```http
GET /api/v1/optimization/{job_id}
```

**Response:**
```json
{
  "status": "COMPLETED",
  "result_summary": {
    "routes_created": 2,
    "shipments_assigned": 10,
    "total_distance_km": 45.2,
    "solver_time_seconds": 35.5
  },
  "route_ids": ["uuid1", "uuid2"],
  "unassigned_shipment_ids": []
}
```

### 3. 查看路線溫度分析
```http
GET /api/v1/routes/{route_id}/temperature-analysis
```

**Response:**
```json
{
  "route_code": "R-20240130-ABC-1234",
  "initial_temperature": -5.0,
  "final_temperature": 3.2,
  "max_temperature": 4.8,
  "is_feasible": true,
  "stops": [
    {
      "sequence": 1,
      "shipment_id": "...",
      "temperature": {
        "arrival_temp": 0.5,
        "transit_rise": 5.5,
        "cooling_applied": -5.0,
        "departure_temp": 2.1
      },
      "constraints": {
        "temp_limit_upper": 5.0,
        "is_feasible": true
      }
    }
  ]
}
```

---

## 🧪 完整性檢查

### 所有元件皆已實作 ✅

```text
Frontend UI (React)
  ├── Dashboard with statistics     ✅
  ├── Vehicle management (CRUD)     ✅
  ├── Shipment management (CRUD)    ✅
  ├── Excel import interface        ✅
  ├── Optimization control panel    ✅
  ├── Interactive map (Leaflet)     ✅
  ├── Internationalization (i18n)   ✅
  └── Responsive design (RWD)       ✅

Database Layer
  ├── PostgreSQL Schema             ✅
  ├── SQLAlchemy ORM Models (9)     ✅
  ├── Pydantic Schemas (8)          ✅
  └── Async connection config       ✅

Optimization Engine (Solver)
  ├── VRP data model conversion     ✅
  ├── Distance/time matrix calc     ✅
  ├── Thermodynamic callbacks       ✅
  └── Complete VRP Solver           ✅

Async Tasks (Celery)
  ├── Celery app configuration      ✅
  ├── Optimization task impl        ✅
  ├── DB read/write operations      ✅
  └── Error handling and retry      ✅

API Endpoints (REST)
  ├── Vehicle management (CRUD)     ✅
  ├── Shipment management (CRUD + Batch) ✅
  ├── Route queries (+ temp analysis) ✅
  ├── Optimization API (async)      ✅
  ├── Depot management              ✅
  ├── Geocoding service             ✅
  └── Excel import endpoint         ✅

Deployment & Configuration
  ├── Docker Compose (production)   ✅
  ├── Docker Compose (development)  ✅
  ├── Frontend Dockerfile (Nginx)   ✅
  ├── Pydantic Settings             ✅
  ├── Environment variables         ✅
  └── .env.example                  ✅
```

---

## 📝 檔案清單

```text
frontend/                     # React 前端
├── src/
│   ├── components/          # React 元件
│   │   ├── Layout/          # MainLayout, navigation
│   │   ├── Map/             # Leaflet 地圖元件
│   │   └── ui/              # shadcn/ui 元件
│   ├── pages/               # 頁面元件
│   │   ├── DashboardPage.tsx
│   │   ├── VehiclesPage.tsx
│   │   ├── ShipmentsPage.tsx
│   │   ├── OptimizationPage.tsx
│   │   ├── MapPage.tsx
│   │   ├── ImportPage.tsx
│   │   └── LoginPage.tsx
│   ├── services/            # API 用戶端
│   │   └── api.ts
│   ├── stores/              # 狀態管理
│   │   ├── authStore.ts
│   │   └── optimizationStore.ts
│   ├── i18n/                # 國際化
│   │   ├── en.json
│   │   ├── zh-TW.json
│   │   └── index.ts
│   └── App.tsx              # 主應用元件
├── index.html
├── package.json
├── vite.config.ts
└── Dockerfile               # 前端容器

app/                         # 後端
├── main.py                  # FastAPI 入口
├── __init__.py
│
├── core/
│   ├── config.py           # Pydantic Settings
│   ├── celery_app.py       # Celery 設定
│   └── __init__.py
│
├── db/
│   ├── database.py         # SQLAlchemy 非同步連線
│   ├── schema.sql          # PostgreSQL DDL + PostGIS
│   └── __init__.py
│
├── models/                 # ORM 模型（9 個）
│   ├── base.py
│   ├── enums.py
│   ├── driver.py
│   ├── vehicle.py
│   ├── customer.py
│   ├── shipment.py
│   ├── route.py
│   ├── optimization.py
│   ├── telemetry.py
│   └── depot.py
│
├── schemas/                # Pydantic Schemas（8 個）
│   ├── base.py
│   ├── driver.py
│   ├── vehicle.py
│   ├── customer.py
│   ├── shipment.py
│   ├── route.py
│   ├── optimization.py
│   └── depot.py
│
├── services/
│   ├── tasks.py            # Celery 最佳化任務
│   ├── depot_import.py     # 倉庫資料匯入
│   ├── geocoding.py        # 地理編碼服務
│   └── solver/             # OR-Tools 求解器
│       ├── solver.py
│       ├── data_model.py
│       └── callbacks.py
│
└── api/v1/
    └── endpoints/          # API 端點（7 個模組）
        ├── vehicles.py
        ├── shipments.py
        ├── routes.py
        ├── optimization.py
        ├── depots.py
        ├── geocoding.py
        └── import_excel.py

Configuration & Documentation:
├── requirements.txt          # Python 相依套件
├── .env.example              # 環境變數範本
├── docker-compose.yml        # 正式環境部署
├── docker-compose.dev.yml    # 開發環境
├── README.md                 # 本檔（總覽）
├── STARTUP_GUIDE.md          # 詳細啟動指南
├── AGENT.md                  # 架構設計（V3.0）
├── CLAUDE.md                 # 開發指南
├── EXCEL_IMPORT_GUIDE.md     # Excel 匯入教學
└── MAP_VISUALIZATION_GUIDE.md # 地圖視覺化教學

Utility Scripts:
├── generate_excel_template.py    # 產生 Excel 範本
├── import_from_excel.py          # Excel 批次匯入
├── visualize_routes.py           # 視覺化最佳化路線（真實道路）
├── demo_map_with_routing.py      # 產生示範地圖（含路由）
└── demo_map_fixed.py             # 產生示範地圖（直線）
```

---

## 🔧 疑難排解

### Docker 問題

**服務無法啟動：**
```bash
# 確認 Docker 正常運作
docker --version
docker-compose --version

# 查看服務日誌
docker-compose logs -f [service-name]

# 重啟指定服務
docker-compose restart [service-name]

# 重新建置容器
docker-compose up -d --build
```

**連接埠衝突：**
```bash
# 檢查連接埠是否被佔用
# Windows PowerShell:
Get-NetTCPConnection -LocalPort 80,8000,5432,6379

# Linux/Mac:
netstat -tuln | grep -E '(80|8000|5432|6379)'

# 解法：修改 docker-compose.yml 連接埠或停止衝突服務
```

**無法存取前端（http://localhost）：**
```bash
# 檢查前端容器狀態
docker-compose ps frontend

# 查看前端日誌
docker-compose logs frontend

# 重啟前端
docker-compose restart frontend
```

### 「ModuleNotFoundError」
```bash
pip install -r requirements.txt
```

### 「PostgreSQL 連線失敗」
```bash
# 確認 PostgreSQL 正常運作
psql -h localhost -U postgres -c "SELECT version();"

# 檢查 PostGIS
psql -h localhost -U postgres -d iccdds -c "SELECT PostGIS_version();"
```

### 「Redis 連線失敗」
```bash
# 確認 Redis 正常運作
redis-cli ping
# 應回傳：PONG
```

### Celery Worker 未執行任務
```bash
# 以完整日誌啟動 Worker
celery -A app.core.celery_app worker --loglevel=debug

# 使用 Flower 監控（選用）
pip install flower
flower -A app.core.celery_app --port=5555
# 入口：http://localhost:5555
```

---

## 📈 效能指標

### 求解時間
- **小規模**（10 單貨運、3 輛車）：約 5 秒
- **中規模**（50 單貨運、10 輛車）：約 30 秒
- **大規模**（100+ 單貨運）：視 `time_limit_seconds` 參數而定

### 準確性
- **STRICT SLA**：100% 滿足或標記為不可行
- **溫度預測**：基於精準熱力學模型，與實測結果相近

### 擴充性
- 支援數百筆貨運與數十台車輛
- Celery 可平行處理多個最佳化任務
- PostgreSQL + PostGIS 支援地理空間查詢最佳化

---

## 🎓 學習資源

### 主要程式位置
- **熱力學計算**：`app/services/solver/callbacks.py` → `TemperatureTracker`
- **VRP 求解器**：`app/services/solver/solver.py` → `ColdChainVRPSolver`
- **多重時間窗**：`app/models/shipment.py` → `TimeWindow` 類別
- **非同步任務**：`app/services/tasks.py` → `run_optimization` 任務

### 公式與推導
請參考 `AGENT.md` 中的「核心演算法邏輯」章節

---

## 📞 支援

- 📖 **完整文件**：詳細設定與啟動請參考 `STARTUP_GUIDE.md`
- 🐛 **疑難排解**：請參考本 README 的疑難排解章節
- 🐳 **Docker 問題**：檢查 `docker-compose.yml` 與服務日誌
- 🌐 **前端問題**：使用 `docker-compose logs frontend` 檢視前端日誌
- 🔍 **程式探索**：可使用 IDE 搜尋功能定位關鍵實作
- 💬 **預設帳號**：帳號：`admin`，密碼：`admin123`

---

## 📄 授權

本專案設計用於學術研究與商業應用。

---

**準備好最佳化你的冷鏈物流了嗎？🚀**
