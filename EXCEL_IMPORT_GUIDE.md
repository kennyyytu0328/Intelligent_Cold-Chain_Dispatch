# Excel 批量導入使用指南

本指南說明如何使用 Excel 範例檔批量導入訂單和車輛資料到 ICCDDS 系統。

## 快速開始

### 1. 安裝必要套件

```bash
# 如果尚未安裝，請執行
pip install pandas openpyxl requests
```

### 2. 生成 Excel 範例檔

```bash
python generate_excel_template.py
```

這會生成 `ICCDDS_Import_Template.xlsx` 檔案，包含：
- **使用說明** 工作表：欄位說明和注意事項
- **訂單 (Shipments)** 工作表：3 筆範例訂單資料
- **車輛 (Vehicles)** 工作表：3 筆範例車輛資料

### 3. 填寫資料

使用 Excel 打開 `ICCDDS_Import_Template.xlsx`：
- 可以修改範例資料
- 可以新增更多行
- 請勿修改欄位名稱（第一行）
- 參考「使用說明」工作表了解每個欄位的含義

### 4. 啟動 API 服務器

在導入資料前，需要先啟動系統：

```bash
# 終端 1: 啟動 FastAPI
uvicorn app.main:app --reload --port 8000

# 終端 2: 啟動 Celery Worker（如果需要執行優化）
celery -A app.core.celery_app worker --loglevel=info
```

### 5. 導入資料

```bash
python import_from_excel.py ICCDDS_Import_Template.xlsx
```

腳本會：
1. 檢查 API 連線
2. 逐筆導入車輛資料
3. 逐筆導入訂單資料
4. 顯示導入結果統計

## Excel 欄位說明

### 訂單 (Shipments) 工作表

| 欄位名稱 | 必填 | 說明 | 範例 |
|---------|------|------|------|
| `order_number` | ✅ | 訂單編號（唯一） | ORD-2024-001 |
| `delivery_address` | ✅ | 送貨地址 | 台北市信義區信義路五段7號 |
| `latitude` | ✅ | 緯度（小數格式） | 25.0330 |
| `longitude` | ✅ | 經度（小數格式） | 121.5654 |
| `weight_kg` | ✅ | 重量（公斤） | 150.0 |
| `volume_m3` | ❌ | 體積（立方米） | 5.0 |
| `time_window_1_start` | ✅ | 第一時間窗開始 (HH:MM) | 08:00 |
| `time_window_1_end` | ✅ | 第一時間窗結束 (HH:MM) | 10:00 |
| `time_window_2_start` | ❌ | 第二時間窗開始（選填） | 14:00 |
| `time_window_2_end` | ❌ | 第二時間窗結束（選填） | 16:00 |
| `sla_tier` | ✅ | SLA 等級：STRICT 或 STANDARD | STRICT |
| `temp_limit_upper_celsius` | ✅ | 最高溫度限制（°C） | 5.0 |
| `temp_limit_lower_celsius` | ❌ | 最低溫度限制（°C） | -2.0 |
| `service_duration_minutes` | ✅ | 卸貨時間（分鐘） | 15 |
| `priority` | ✅ | 優先級（0-100） | 80 |

### 車輛 (Vehicles) 工作表

| 欄位名稱 | 必填 | 說明 | 範例 |
|---------|------|------|------|
| `license_plate` | ✅ | 車牌號碼（唯一） | ABC-1234 |
| `capacity_weight_kg` | ✅ | 載重容量（公斤） | 3000.0 |
| `capacity_volume_m3` | ✅ | 容積容量（立方米） | 15.0 |
| `insulation_grade` | ✅ | 保溫等級：PREMIUM/STANDARD/BASIC | STANDARD |
| `door_type` | ✅ | 門型：ROLL（捲門）或 SWING（對開門） | ROLL |
| `has_strip_curtains` | ✅ | 是否有門簾：TRUE 或 FALSE | TRUE |
| `cooling_rate_celsius_per_min` | ✅ | 製冷速率（°C/分鐘，負數） | -2.5 |
| `driver_name` | ❌ | 駕駛員姓名 | 王大明 |

## 重要注意事項

### 1. 時間格式
- 必須使用 24 小時制
- 格式為 `HH:MM`，例如：`08:00`, `14:30`
- 不要使用 AM/PM

### 2. 多時間窗
- 每個訂單最多支援 2 個時間窗
- 滿足任一時間窗即可配送
- 若只需要一個時間窗，將 `time_window_2_start` 和 `time_window_2_end` 留空

### 3. SLA 等級
- **STRICT**: 嚴格約束，必須在時間窗內送達，否則不派送
- **STANDARD**: 標準約束，可延遲但會有罰分

### 4. 溫度限制
- `temp_limit_upper`: 到貨時的最高溫度，超過此溫度客戶可能拒收
- `temp_limit_lower`: 最低溫度（選填），用於防止凍傷

### 5. 保溫等級對應的 K 值
- **PREMIUM**: K = 0.02（最佳保溫）
- **STANDARD**: K = 0.05（標準保溫）
- **BASIC**: K = 0.10（基礎保溫）

K 值越小，保溫效果越好，溫度上升越慢。

### 6. 門型對應的係數
- **ROLL** (捲門): C = 0.8（熱損較低）
- **SWING** (對開門): C = 1.2（熱損較高）

### 7. 門簾效果
- 有門簾 (`has_strip_curtains = TRUE`): 開門熱損減少 50%
- 無門簾 (`has_strip_curtains = FALSE`): 正常熱損

## 常見問題

### Q1: 導入時出現 "無法連線到 API 服務器" 錯誤

**A:** 請確認 FastAPI 服務器已啟動：
```bash
uvicorn app.main:app --reload --port 8000
```

在瀏覽器訪問 http://localhost:8000/health 確認服務運行正常。

### Q2: 某些資料導入失敗

**A:** 檢查錯誤訊息，常見原因：
- 必填欄位為空
- 資料格式不正確（如時間格式錯誤）
- 唯一性約束違反（如訂單編號或車牌號碼重複）
- SLA 等級或保溫等級拼寫錯誤（必須大寫）

### Q3: 如何取得經緯度座標？

**A:** 可以使用以下方式：
- Google Maps：右鍵點擊地圖上的位置，選擇座標
- 地圖 API：使用地理編碼服務將地址轉換為座標
- 線上工具：搜尋 "地址轉經緯度" 工具

### Q4: 可以導入多少筆資料？

**A:** 理論上無限制，但建議：
- 一次導入不超過 500 筆訂單
- 大批量資料可分多次導入
- 導入完成後檢查結果統計

### Q5: 導入後如何查看資料？

**A:** 有幾種方式：
1. 使用 Swagger UI：http://localhost:8000/api/v1/docs
2. 直接查詢 API：
   ```bash
   # 查看所有車輛
   curl http://localhost:8000/api/v1/vehicles

   # 查看待派送訂單
   curl http://localhost:8000/api/v1/shipments/pending
   ```
3. 使用資料庫客戶端連接 PostgreSQL 查詢

## 進階用法

### 批次處理多個 Excel 檔案

如果有多個 Excel 檔案需要導入：

```bash
# Windows
for %f in (*.xlsx) do python import_from_excel.py "%f"

# Linux/Mac
for file in *.xlsx; do python import_from_excel.py "$file"; done
```

### 自訂 API 地址

修改 `import_from_excel.py` 中的 `API_BASE_URL`：

```python
API_BASE_URL = "http://your-server:8000/api/v1"
```

### 匯出現有資料為 Excel

可以編寫反向腳本，從 API 匯出資料到 Excel：

```python
import pandas as pd
import requests

response = requests.get("http://localhost:8000/api/v1/vehicles")
vehicles = response.json()

df = pd.DataFrame(vehicles)
df.to_excel("exported_vehicles.xlsx", index=False)
```

## 下一步

資料導入完成後，可以：

1. **啟動優化任務**：
   ```bash
   curl -X POST http://localhost:8000/api/v1/optimization \
     -H "Content-Type: application/json" \
     -d '{
       "plan_date": "2024-01-30",
       "parameters": {
         "time_limit_seconds": 60,
         "strategy": "MINIMIZE_VEHICLES",
         "ambient_temperature": 30.0
       }
     }'
   ```

2. **查看 API 文件**：http://localhost:8000/api/v1/docs

3. **監控 Celery 任務**：http://localhost:5555 (需先啟動 Flower)

## 支援

如有問題，請參考：
- `README.md` - 系統總覽
- `STARTUP_GUIDE.md` - 啟動指南
- `CLAUDE.md` - 開發指南
- API 文件：http://localhost:8000/api/v1/docs
