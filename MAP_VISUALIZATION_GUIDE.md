# 配送路線地圖視覺化指南

本指南說明如何將優化後的配送路線視覺化到互動式地圖上。

## 功能特色

- 📍 **清晰的停靠點標記**：顯示每個配送點的順序和詳細資訊
- 🚛 **多車輛支援**：不同車輛使用不同顏色，最多支援 12 台車
- 🌡️ **溫度視覺化**：綠色表示溫度可行，紅色表示溫度超標
- 📊 **詳細資訊彈窗**：點擊標記查看訂單、溫度、時間等完整資訊
- 🎛️ **圖層控制**：可自由顯示/隱藏特定車輛的路線
- 📏 **測量工具**：測量地圖上任意兩點的距離
- 🔍 **全屏模式**：放大查看路線細節
- 🏠 **倉庫標記**：清楚標示配送中心位置

## 快速開始

### 1. 安裝必要套件

```bash
pip install folium requests
```

### 2. 確保已有優化路線

在視覺化之前，需要先透過系統生成配送路線：

```bash
# 啟動 API 服務器
uvicorn app.main:app --reload --port 8000

# 啟動優化任務（透過 API）
curl -X POST http://localhost:8000/api/v1/optimization \
  -H "Content-Type: application/json" \
  -d '{
    "plan_date": "2024-01-30",
    "parameters": {
      "time_limit_seconds": 60,
      "strategy": "MINIMIZE_VEHICLES"
    }
  }'
```

### 3. 生成地圖

```bash
# 視覺化今天的路線
python visualize_routes.py

# 視覺化指定日期的路線
python visualize_routes.py 2024-01-30
```

### 4. 查看地圖

腳本會生成 `routes_map_YYYYMMDD.html` 檔案，使用瀏覽器打開即可查看。

```bash
# Windows
start routes_map_20240130.html

# macOS
open routes_map_20240130.html

# Linux
xdg-open routes_map_20240130.html
```

## 地圖元素說明

### 標記類型

| 圖標 | 說明 |
|------|------|
| 🏭 黑色房屋圖標 | 倉庫/配送中心（起點和終點） |
| ✅ 綠色勾選圖標 | 溫度可行的停靠點 |
| ⚠️ 紅色警告圖標 | 溫度超標的停靠點 |
| 彩色數字圓圈 | 停靠順序編號 |

### 路線顏色

每條路線（車輛）使用不同顏色：
- 紅色、綠色、藍色、橙色、紫色、青色等
- 顏色與左側圖層控制面板中的車輛對應

### 互動功能

1. **點擊標記**：顯示彈出視窗，包含：
   - 訂單編號和送貨地址
   - 預計到達和離開時間
   - 到達溫度和離開溫度
   - 溫度可行性判斷
   - 貨物重量和體積
   - SLA 等級

2. **滑鼠懸停**：顯示簡短提示（停靠點編號和訂單號）

3. **圖層控制**（左上角）：
   - 勾選/取消勾選以顯示/隱藏特定車輛的路線
   - 適合專注查看單一路線

4. **測量工具**（左上角）：
   - 點擊測量圖標
   - 在地圖上點擊兩個點
   - 顯示直線距離（公里）

5. **全屏按鈕**（左上角）：
   - 點擊放大到全屏
   - 再次點擊退出全屏

## 地圖內容詳解

### 倉庫資訊

點擊黑色房屋圖標（倉庫）顯示：
- 倉庫地址
- 分配的車輛車牌
- 駕駛員姓名
- 出發時間和預計返回時間
- 總配送距離和總時長

### 停靠點資訊

點擊停靠點標記顯示：

**基本資訊**
- 停靠點順序編號
- 訂單編號
- 送貨地址

**時間資訊**
- 預計到達時間
- 預計離開時間
- 服務時長（卸貨時間）
- 緩衝時間（餘裕時間）

**溫度資訊**
- 到達溫度（綠色表示正常，紅色表示超標）
- 離開溫度
- 溫度上限
- 可行性判斷（✅ 可行 / ❌ 不可行）

**貨物資訊**
- 重量（公斤）
- 體積（立方米）
- SLA 等級（STRICT 或 STANDARD）

### 路線視覺化

- **實線**：配送路線，連接倉庫→停靠點1→停靠點2→...→倉庫
- **箭頭**：顯示配送方向
- **顏色**：每條路線使用唯一顏色，與左側圖層名稱對應

## 實用技巧

### 1. 比較不同車輛的路線

使用圖層控制取消勾選其他車輛，只顯示要比較的幾條路線：

```
1. 打開左上角圖層控制
2. 取消勾選不需要查看的車輛
3. 只保留要比較的 2-3 條路線
```

### 2. 識別問題路線

紅色警告圖標 (⚠️) 表示該停靠點存在溫度超標問題：

- 點擊查看到達溫度與溫度上限的差距
- 檢查前一個停靠點的距離和行駛時間
- 考慮調整路線順序或更換更高保溫等級的車輛

### 3. 測量實際距離

系統計算的距離是直線距離（Haversine 公式），實際道路距離會更長：

```
1. 點擊左上角測量工具
2. 點擊起點
3. 點擊終點
4. 查看顯示的距離（公里）
```

一般來說，實際道路距離約為直線距離的 1.2-1.5 倍。

### 4. 截圖分享

使用瀏覽器的截圖功能保存地圖：

- **Windows**: `Win + Shift + S`
- **macOS**: `Cmd + Shift + 4`
- 或使用全屏模式後按 `F12` 開啟開發者工具截圖

### 5. 列印路線圖

瀏覽器 → 列印 (Ctrl+P / Cmd+P)：
- 建議先使用圖層控制只顯示單一路線
- 調整為橫向列印
- 可儲存為 PDF 檔案

## 進階功能

### 自訂地圖樣式

修改 `visualize_routes.py` 中的 `tiles` 參數：

```python
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=12,
    tiles='CartoDB positron',  # 簡潔黑白風格
    # tiles='CartoDB dark_matter',  # 深色模式
    # tiles='Stamen Terrain',  # 地形圖
)
```

### 自訂車輛顏色

修改 `VEHICLE_COLORS` 列表：

```python
VEHICLE_COLORS = [
    '#FF0000',  # 紅色
    '#00FF00',  # 綠色
    # ... 添加更多顏色
]
```

### 添加更多圖層

可以添加其他資訊圖層，例如：

```python
# 添加交通擁堵圖層
folium.TileLayer(
    tiles='https://tile.thunderforest.com/transport/{z}/{x}/{y}.png',
    attr='Thunderforest',
    name='交通路線',
    overlay=True,
).add_to(m)

# 添加熱力圖（顯示配送密度）
from folium.plugins import HeatMap
heat_data = [[lat, lon] for lat, lon in all_coords]
HeatMap(heat_data).add_to(m)
```

## 故障排除

### Q1: 無法連線到 API 服務器

**A:** 確認 FastAPI 服務器已啟動：

```bash
uvicorn app.main:app --reload --port 8000
```

檢查連線：
```bash
curl http://localhost:8000/health
```

### Q2: 找不到指定日期的路線

**A:** 確認該日期已執行過優化：

```bash
# 查看所有路線
curl http://localhost:8000/api/v1/routes

# 查看指定日期的路線
curl http://localhost:8000/api/v1/routes?plan_date=2024-01-30
```

### Q3: 地圖上的點位置不準確

**A:** 檢查資料庫中的經緯度是否正確：

- 確認經度範圍：台灣約 120-122
- 確認緯度範圍：台灣約 22-25
- 確認沒有經緯度顛倒（常見錯誤）

### Q4: 地圖載入緩慢

**A:** 如果路線很多，可以：

1. 分批視覺化（一次只查看幾條路線）
2. 減少停靠點資訊的詳細程度
3. 使用更簡潔的地圖底圖（如 CartoDB positron）

### Q5: 某些車輛路線沒有顯示

**A:** 檢查：

1. 路線是否有停靠點（空路線不會顯示）
2. 停靠點是否有有效的經緯度座標
3. 查看終端輸出的錯誤訊息

## 範例工作流程

### 完整的視覺化流程

```bash
# 1. 匯入訂單和車輛
python import_from_excel.py ICCDDS_Import_Template.xlsx

# 2. 啟動優化任務
curl -X POST http://localhost:8000/api/v1/optimization \
  -H "Content-Type: application/json" \
  -d '{"plan_date": "2024-01-30", "parameters": {"time_limit_seconds": 60}}'

# 3. 等待優化完成（查詢 job_id）
curl http://localhost:8000/api/v1/optimization/{job_id}

# 4. 視覺化結果
python visualize_routes.py 2024-01-30

# 5. 在瀏覽器中打開地圖
start routes_map_20240130.html
```

## 相關文件

- `README.md` - 系統總覽
- `STARTUP_GUIDE.md` - 系統啟動指南
- `EXCEL_IMPORT_GUIDE.md` - Excel 批量導入指南
- API 文件：http://localhost:8000/api/v1/docs

## 技術說明

### 使用的套件

- **Folium**：Python 地圖視覺化套件，基於 Leaflet.js
- **OpenStreetMap**：免費的地圖底圖，無需 API key
- **Requests**：用於從 API 取得路線資料

### 座標系統

- 使用 WGS84 座標系統（GPS 標準）
- 經緯度格式：(latitude, longitude)
- PostGIS POINT 格式：POINT(longitude latitude)

### 地圖投影

- Web Mercator 投影（EPSG:3857）
- 適合網頁顯示，但在高緯度地區有失真

### 性能考量

- 地圖為靜態 HTML，無需即時資料連線
- 建議單次視覺化不超過 20 條路線
- 大型路線可考慮分區視覺化
