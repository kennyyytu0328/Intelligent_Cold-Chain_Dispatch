這是一份融合了 **V1.0 的業務邏輯深度** 與 **V2.0 的 Python 技術實作細節** 的 **完整版系統架構設計書 (V3.0)**。

這份文件可以直接作為 **Master Design Document** 提供給 Claude (或其他 AI 編碼助手)，讓它完全理解從「物理熱力學」到「資料庫欄位」的所有需求。

---

# 系統架構設計書 (V3.0)：智慧冷鏈物流動態排派車系統

# System Architecture Design Document: Intelligent Cold-Chain Dynamic Dispatch System (ICCDDS)

## 1. 系統願景與核心目標 (System Vision & Objectives)

本系統旨在解決 **VRPTW (Vehicle Routing Problem with Time Windows)** 與 **冷鏈熱力學約束** 的多目標最佳化問題。

### 1.1 核心優化目標 (Optimization Hierarchies)

演算法必須遵循以下 **字典序 (Lexicographic)** 優先級：

1. **Level 0 (Hard Constraint - Feasibility):**
* **絕對 SLA:** 嚴格客戶 (Strict SLA) 的時間窗與溫度限制不可違反。
* **物理限制:** 車輛載重、容積、軸重不可超標。


2. **Level 1 (Minimize Fleet Size):** 優先減少總使用車輛數（固定成本最大）。
3. **Level 2 (Minimize Operational Cost):** 在車數相同下，最小化總里程與行駛時間（變動成本）。
4. **Level 3 (Risk Mitigation):** 最大化剩餘緩衝時間，降低突發路況導致違約的風險。

---

## 2. 系統架構與技術堆疊 (System Architecture & Tech Stack)

### 2.1 後端架構 (Backend Infrastructure)

採用 **Microservices-ready** 的分層架構，確保運算與 I/O 分離。

* **API Gateway / Core Service:** **Python FastAPI**
* *理由：* 高效能非同步 (Async/Await) 處理高併發請求，自動生成 OpenAPI 文件。


* **Optimization Engine (The Brain):** **Google OR-Tools (Python)**
* *理由：* 支援高度客製化的 Python Callback (用於熱力學計算) 與 Disjunction Constraint (用於多重時間窗)。


* **Asynchronous Task Queue:** **Celery + Redis**
* *理由 (重要):* 排程運算耗時 (30s~5min)，**嚴禁**在 FastAPI 主執行緒中執行。API 接收請求後僅回傳 `job_id`，由 Celery Worker 在背景執行 OR-Tools 運算。


* **Message Broker:** **RabbitMQ** or **Redis**
* *理由：* 用於解耦 IoT 設備的高頻數據寫入，以及 Worker 運算完成後的狀態推播。


* **Database:** **PostgreSQL + PostGIS**
* *理由：* 處理地理空間資料 (Geo-fencing, Lat/Lon) 與複雜關聯查詢。



---

## 3. 領域模型與資料庫設計 (Domain Modeling & Schema)

請指示 Claude 建立以下實體，特別注意 **冷鏈物理參數** 與 **多重時間窗** 的設計。

### 3.1 Vehicle (車輛資源)

不僅是運輸工具，更是具備熱力學特性的移動倉庫。

| 欄位名稱 | 類型 | 說明 | 設計考量 |
| --- | --- | --- | --- |
| `id` | UUID | Primary Key |  |
| `license_plate` | String | 車牌號碼 | 識別用 (e.g., "ABC-1234") |
| `driver_id` | UUID | 駕駛員關聯 | 當班司機 |
| `driver_name` | String | 駕駛員姓名 | 顯示用 (避免頻繁 Join) |
| `capacity_weight` | Float | 載重 (kg) | 限制條件 |
| `capacity_volume` | Float | 容積 (m3) | 限制條件 |
| `internal_l/w/h` | Float | 內部尺寸 | **3D 裝箱模擬 (Bin Packing) 基礎數據** |
| `insulation_grade` | Enum | 保溫等級 | 影響熱傳導係數 (K-value) |
| `door_type` | Enum | 門型 (Roll/Swing) | 捲門 vs 對開門，影響開門熱損耗 |
| `has_strip_curtains` | Bool | 是否有門簾 | **若為 True，開門熱損耗計算減半** |
| `cooling_rate` | Float | 降溫效率 | 車廂每分鐘可降溫多少度 (°C/min) |

### 3.2 Shipment (貨運訂單)

支援複雜的收貨規則與SLA等級。

| 欄位名稱 | 類型 | 說明 | 設計考量 |
| --- | --- | --- | --- |
| `id` | UUID | Primary Key |  |
| `delivery_address` | String | 地址文本 |  |
| `geo_location` | Point | 經緯度 | PostGIS Geometry |
| `time_windows` | JSONB | **多重時間窗** | `[{"start": "08:00", "end": "10:00"}, {"start": "13:00", "end": "15:00"}]` |
| `sla_tier` | Enum | SLA 等級 | **STRICT (嚴格/不可違約)** vs STANDARD |
| `temp_limit_upper` | Float | 最高允收溫度 | **Hard Constraint (超過即拒收)** |
| `service_duration` | Int | 卸貨時間 (min) | 影響開門熱損耗計算 |
| `dimensions` | JSONB | 貨品尺寸 | `{"l": 10, "w": 20, "h": 30}` 用于裝箱演算 |

---

## 4. 核心演算法邏輯 (Core Algorithm Logic)

這是系統最核心的部分，請 Claude 務必實作以下邏輯。

### 4.1 熱力學預測模型 (Thermodynamic Predictive Model)

在 OR-Tools 的 `DistanceCallback` 或 `TransitCallback` 中，除了計算距離，還必須計算 **溫度累積**。

1. **行駛升溫 ():**
* 公式：![Delta T_drive](https://latex.codecogs.com/svg.image?\Delta&space;T_{drive}=Time_{travel}\times(T_{ambient}-T_{current})\times&space;K_{insulation})
* *邏輯：* 外部越熱、車體保溫越差、跑越久，溫度升越高。


2. **開門升溫 ():**
* 公式：![Delta T_door](https://latex.codecogs.com/svg.image?\Delta&space;T_{door}=Time_{service}\times&space;C_{door\_type}\times(1-0.5\times&space;IsCurtain))
* *邏輯：* 卸貨越久升溫越快；有門簾可減少 50% 流失。


3. **主動製冷 ():**
* 公式：![Delta T_cooling](https://latex.codecogs.com/svg.image?\Delta&space;T_{cooling}=Time_{drive}\times&space;Rate_{cooling}) (若車輛行駛中開啟冷凍機)



**判定規則：**
若 ，則回傳 **Infeasible (無限大成本)**，迫使演算法放棄該路徑。

### 4.2 多重時間窗處理 (Multi-Time Window Logic)

利用 OR-Tools 的 **Disjunction (析取)** 機制：

* 針對單一訂單的多個時間窗 (例如 08-10, 13-15)，演算法視為「或 (OR)」的關係。
* 必須滿足其中一個區間，否則視為違約。
* 針對 **Strict SLA** 客戶，設定 `AllowPenalty = False` (強制滿足)。
* 針對 **Standard** 客戶，設定 `AllowPenalty = True` (可遲到但要罰分)。

---

## 5. 系統流程 (System Process Flow)

### Phase 1: 訂單攝取與預處理

1. API 接收批次訂單。
2. 驗證地址並轉換為經緯度 (Geocoding)。
3. 將訂單寫入 DB，狀態為 `PENDING`。

### Phase 2: 非同步排程 (Async Dispatch)

1. 使用者觸發「開始排程」。
2. FastAPI 發送 Task 到 **Celery Queue**。
3. **Worker 執行緒：**
* 從 DB 撈取可用車輛 (考慮載重、門簾屬性) 與訂單。
* 呼叫 Google OR-Tools 進行運算。
* 套用熱力學 Callback 與 多時間窗約束。
* 產生最佳路徑 (Routes)。


4. 將結果存回 DB，透過 **Redis Pub/Sub** 通知前端。

### Phase 3: 動態監控 (Real-time Monitoring)

1. 車輛 IoT 回傳即時溫度與 GPS。
2. 若 `CurrentTemp > Limit` 或 `ETA > Deadline`：
* 觸發 **Alert**。
* (進階) 觸發 **Re-optimization**，尋找附近是否有空車可支援。



---

## 6. 給 Claude 的 Master Prompts (可直接使用)

為了確保產出符合上述架構，請使用以下 Prompts：

### Prompt 1: 資料庫與領域模型 (Database & Domain)

> "Act as a Senior System Architect. Design a **PostgreSQL schema** for a Cold-Chain VRP system using Python/FastAPI.
> **Requirements:**
> 1. **`vehicles` table:** Include `license_plate`, `driver_id`, and specific thermodynamic fields: `insulation_grade` (Enum), `door_type` (Enum), `has_strip_curtains` (Boolean), and `cooling_rate`.
> 2. **`shipments` table:** Must support **Multiple Time Windows** (use JSONB to store a list of start/end times), `strict_sla` (Boolean), and `temp_limit_upper`. Include `dimensions` (L/W/H) for future 3D bin packing.
> 3. **`routes` table:** Store the optimized sequence, expected arrival times, and **predicted temperature** at each stop."
> 
> 

### Prompt 2: 核心演算法 (Optimization Engine)

> "Act as an OR-Tools Expert. Implement a specific VRP solver class in Python.
> **Key Logic:**
> 1. **Cost Function:** Hierarchical. First minimize vehicle count, then minimize total distance.
> 2. **Thermodynamic Constraint (Crucial):** Create a custom callback.
> * Calculate temp rise based on travel time and `insulation_grade`.
> * Calculate huge temp rise during service time, but **reduce it by 50% if `vehicle.has_strip_curtains` is True**.
> * If predicted temp > `shipment.temp_limit`, return a massive penalty (Soft) or mark Infeasible (Hard).
> 
> 
> 3. **Multi-Time Windows:** Use OR-Tools `AddDimension` and logic to handle shipments that have multiple valid delivery slots (e.g., 8-10 OR 14-16).
> 
> 
> Provide the Python code structure for this Solver class."

### Prompt 3: 非同步架構 (Async Architecture)

> "Act as a Backend Lead. Explain how to structure this **FastAPI** application to handle the long-running OR-Tools process.
> 1. Show how to use **Celery** with **Redis** to offload the solving task.
> 2. Design the API endpoint `/api/v1/optimize` that returns a `task_id` immediately.
> 3. Explain why we use a Message Queue here (Decoupling & Throttling)."
> 
> 

---

### 架構師總結 (Architect's Summary)

這份 V3.0 設計書完整補足了 V2.0 缺失的業務深度。它確保了：

1. **物理真實性：** 考慮了門簾、保溫等級、開門次數對溫度的影響。
2. **商業彈性：** 支援多重時間窗與 SLA 分級。
3. **技術可行性：** 明確定義了 Python/FastAPI/Celery 的職責邊界，避免系統在大規模運算時崩潰。

你可以將此文件視為專案的「憲法」，隨時用來檢核 Claude 產出的程式碼是否符合規範。