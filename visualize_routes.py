"""
視覺化 ICCDDS 配送路線到互動式地圖

使用方式:
    python visualize_routes.py [plan_date] [--no-routing]

範例:
    python visualize_routes.py 2024-01-30
    python visualize_routes.py 2024-01-30 --no-routing  # 使用直線，不呼叫路由 API

會生成 routes_map_[date].html 檔案，可在瀏覽器中打開查看
"""
import sys
import requests
from datetime import date, datetime
from typing import List, Dict, Any
import folium
from folium import plugins
import json
import time

# OSRM 公共路由 API (免費)
OSRM_API_URL = "http://router.project-osrm.org/route/v1/driving"

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

API_BASE_URL = "http://localhost:8000/api/v1"

# 車輛顏色配色方案（最多支援 12 台車）
VEHICLE_COLORS = [
    '#e6194B',  # 紅色
    '#3cb44b',  # 綠色
    '#4363d8',  # 藍色
    '#f58231',  # 橙色
    '#911eb4',  # 紫色
    '#42d4f4',  # 青色
    '#f032e6',  # 洋紅色
    '#bfef45',  # 萊姆綠
    '#fabed4',  # 粉色
    '#469990',  # 青綠色
    '#dcbeff',  # 薰衣草色
    '#9A6324',  # 棕色
]


def get_routes_by_date(plan_date: str) -> List[Dict[str, Any]]:
    """從 API 取得指定日期的所有路線"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/routes",
            params={"plan_date": plan_date},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ 無法取得路線資料: {e}")
        return []


def get_route_stops(route_id: str) -> List[Dict[str, Any]]:
    """取得路線的所有停靠點"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/routes/{route_id}",
            timeout=10,
        )
        response.raise_for_status()
        route_data = response.json()
        return route_data.get("stops", [])
    except Exception as e:
        print(f"❌ 無法取得路線停靠點: {e}")
        return []


def get_temperature_analysis(route_id: str) -> Dict[str, Any]:
    """取得路線的溫度分析"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/routes/{route_id}/temperature-analysis",
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️  無法取得溫度分析: {e}")
        return {}


def get_osrm_route(coordinates: list) -> list:
    """
    使用 OSRM API 取得實際道路路線

    Args:
        coordinates: [(lat, lon), (lat, lon), ...] 路線點列表

    Returns:
        實際道路路線座標列表 [(lat, lon), ...]
    """
    if len(coordinates) < 2:
        return coordinates

    # OSRM 使用 lon,lat 格式
    coords_str = ";".join([f"{lon},{lat}" for lat, lon in coordinates])

    url = f"{OSRM_API_URL}/{coords_str}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data["code"] == "Ok" and data["routes"]:
            route_coords = data["routes"][0]["geometry"]["coordinates"]
            # 轉換為 [lat, lon] 格式
            return [(coord[1], coord[0]) for coord in route_coords]
        else:
            return coordinates

    except requests.exceptions.RequestException:
        return coordinates  # 失敗時返回原始座標


def create_route_map(routes: List[Dict[str, Any]], plan_date: str, use_routing: bool = True) -> folium.Map:
    """
    創建包含所有路線的地圖

    Args:
        routes: 路線資料列表
        plan_date: 計劃日期
        use_routing: 是否使用 OSRM 取得實際道路路線（預設 True）
    """

    # 計算地圖中心點（所有點的平均位置）
    all_lats = []
    all_lons = []

    for route in routes:
        stops = get_route_stops(route["id"])
        for stop in stops:
            # 從 location 字串解析經緯度 (格式: "POINT(121.5654 25.0330)")
            location_str = stop.get("location", "")
            if "POINT" in location_str:
                coords = location_str.replace("POINT(", "").replace(")", "").split()
                if len(coords) == 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    all_lats.append(lat)
                    all_lons.append(lon)

    if not all_lats:
        # 預設中心點（台北）
        center_lat, center_lon = 25.0330, 121.5654
    else:
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)

    # 創建地圖
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap',
    )

    # 為每條路線添加圖層
    for idx, route in enumerate(routes):
        color = VEHICLE_COLORS[idx % len(VEHICLE_COLORS)]

        # 取得停靠點和溫度分析
        stops = get_route_stops(route["id"])
        temp_analysis = get_temperature_analysis(route["id"])
        temp_stops = {s["sequence"]: s for s in temp_analysis.get("stops", [])}

        if not stops:
            continue

        # 創建路線圖層
        feature_group = folium.FeatureGroup(
            name=f'🚛 {route["route_code"]} ({route["vehicle"]["license_plate"]})',
            show=True,
        )

        # 取得倉庫位置
        depot_location_str = route.get("depot_location", "")
        depot_coords = None
        if "POINT" in depot_location_str:
            coords = depot_location_str.replace("POINT(", "").replace(")", "").split()
            if len(coords) == 2:
                depot_coords = (float(coords[1]), float(coords[0]))  # (lat, lon)

        # 標記倉庫（起點和終點）
        if depot_coords:
            folium.Marker(
                location=depot_coords,
                popup=folium.Popup(
                    f"""
                    <div style="width:250px">
                        <h4>🏭 倉庫/配送中心</h4>
                        <p><b>地址:</b> {route.get('depot_address', 'N/A')}</p>
                        <p><b>車輛:</b> {route['vehicle']['license_plate']}</p>
                        <p><b>司機:</b> {route.get('driver_name', 'N/A')}</p>
                        <p><b>出發時間:</b> {route.get('planned_departure_at', 'N/A')}</p>
                        <p><b>預計返回:</b> {route.get('planned_return_at', 'N/A')}</p>
                        <p><b>總距離:</b> {route.get('total_distance', 0):.1f} km</p>
                        <p><b>總時長:</b> {route.get('total_duration', 0)} 分鐘</p>
                    </div>
                    """,
                    max_width=300,
                ),
                icon=folium.Icon(color='black', icon='home', prefix='fa'),
                tooltip="倉庫",
            ).add_to(feature_group)

        # 路線點集合（用於畫線）
        route_coords = []
        if depot_coords:
            route_coords.append(depot_coords)

        # 標記每個停靠點
        for stop in sorted(stops, key=lambda x: x["sequence_number"]):
            # 解析經緯度
            location_str = stop.get("location", "")
            if "POINT" not in location_str:
                continue

            coords = location_str.replace("POINT(", "").replace(")", "").split()
            if len(coords) != 2:
                continue

            lon, lat = float(coords[0]), float(coords[1])
            route_coords.append((lat, lon))

            # 取得溫度資訊
            temp_info = temp_stops.get(stop["sequence_number"], {})
            temp_data = temp_info.get("temperature", {})

            arrival_temp = temp_data.get("arrival_temp", "N/A")
            departure_temp = temp_data.get("departure_temp", "N/A")
            is_feasible = temp_info.get("constraints", {}).get("is_feasible", True)

            # 根據溫度可行性決定圖標顏色
            if not is_feasible:
                icon_color = 'red'
                icon_symbol = 'exclamation-triangle'
            else:
                icon_color = 'green'
                icon_symbol = 'check-circle'

            # 建立彈出視窗內容
            popup_html = f"""
            <div style="width:300px">
                <h4>📍 停靠點 #{stop['sequence_number']}</h4>
                <hr>
                <p><b>訂單編號:</b> {stop.get('shipment', {}).get('order_number', 'N/A')}</p>
                <p><b>送貨地址:</b> {stop.get('address', 'N/A')}</p>
                <hr>
                <p><b>預計到達:</b> {stop.get('expected_arrival_at', 'N/A')}</p>
                <p><b>預計離開:</b> {stop.get('expected_departure_at', 'N/A')}</p>
                <p><b>服務時長:</b> {stop.get('shipment', {}).get('service_duration', 'N/A')} 分鐘</p>
                <p><b>緩衝時間:</b> {stop.get('slack_minutes', 0)} 分鐘</p>
                <hr>
                <p><b>🌡️ 到達溫度:</b> <span style="color:{'red' if not is_feasible else 'green'}">{arrival_temp}°C</span></p>
                <p><b>🌡️ 離開溫度:</b> {departure_temp}°C</p>
                <p><b>溫度上限:</b> {stop.get('shipment', {}).get('temp_limit_upper', 'N/A')}°C</p>
                <p><b>可行性:</b> <span style="color:{'red' if not is_feasible else 'green'}">{'❌ 不可行' if not is_feasible else '✅ 可行'}</span></p>
                <hr>
                <p><b>貨物重量:</b> {stop.get('shipment', {}).get('weight', 0):.1f} kg</p>
                <p><b>貨物體積:</b> {stop.get('shipment', {}).get('volume', 0):.1f} m³</p>
                <p><b>SLA 等級:</b> {stop.get('shipment', {}).get('sla_tier', 'N/A')}</p>
            </div>
            """

            # 添加標記
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=350),
                icon=folium.Icon(
                    color=icon_color,
                    icon=icon_symbol,
                    prefix='fa',
                ),
                tooltip=f"停靠點 #{stop['sequence_number']}: {stop.get('shipment', {}).get('order_number', 'N/A')}",
            ).add_to(feature_group)

            # 添加序號標籤
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                        background-color: {color};
                        color: white;
                        font-weight: bold;
                        font-size: 12px;
                        border-radius: 50%;
                        width: 24px;
                        height: 24px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        border: 2px solid white;
                        box-shadow: 0 0 4px rgba(0,0,0,0.5);
                    ">{stop['sequence_number']}</div>
                    """
                ),
            ).add_to(feature_group)

        # 添加返回倉庫的路線
        if depot_coords:
            route_coords.append(depot_coords)

        # 畫路線
        if len(route_coords) >= 2:
            # 決定是否使用實際道路路線
            if use_routing:
                print(f"  🗺️  取得 {route['vehicle']['license_plate']} 的實際道路路線...")
                actual_route = get_osrm_route(route_coords)
                time.sleep(0.3)  # 避免 API 請求過快
            else:
                actual_route = route_coords

            folium.PolyLine(
                locations=actual_route,
                color=color,
                weight=5,
                opacity=0.8,
                popup=f"路線: {route['route_code']}",
                tooltip=f"{route['vehicle']['license_plate']} - {len(stops)} 個停靠點",
            ).add_to(feature_group)

        # 添加圖層到地圖
        feature_group.add_to(m)

    # 添加圖層控制
    folium.LayerControl(collapsed=False).add_to(m)

    # 添加全屏按鈕
    plugins.Fullscreen().add_to(m)

    # 添加測量工具
    plugins.MeasureControl(
        position='topleft',
        primary_length_unit='kilometers',
        secondary_length_unit='miles',
    ).add_to(m)

    # 添加標題
    title_html = f'''
    <div style="position: fixed;
                top: 10px;
                left: 50%;
                transform: translateX(-50%);
                width: auto;
                height: auto;
                background-color: white;
                border: 2px solid grey;
                border-radius: 5px;
                padding: 10px;
                font-family: Arial;
                font-size: 16px;
                font-weight: bold;
                z-index: 9999;
                box-shadow: 0 0 10px rgba(0,0,0,0.3);">
        🗺️ ICCDDS 配送路線圖 - {plan_date}
        <br>
        <span style="font-size: 12px; font-weight: normal;">
            共 {len(routes)} 條路線
        </span>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))

    # 添加圖例
    legend_html = '''
    <div style="position: fixed;
                bottom: 50px;
                right: 10px;
                width: 200px;
                background-color: white;
                border: 2px solid grey;
                border-radius: 5px;
                padding: 10px;
                font-family: Arial;
                font-size: 12px;
                z-index: 9999;
                box-shadow: 0 0 10px rgba(0,0,0,0.3);">
        <h4 style="margin-top: 0;">圖例說明</h4>
        <p><i class="fa fa-home" style="color:black;"></i> 倉庫/配送中心</p>
        <p><i class="fa fa-check-circle" style="color:green;"></i> 溫度可行</p>
        <p><i class="fa fa-exclamation-triangle" style="color:red;"></i> 溫度超標</p>
        <p><span style="color:blue;">━━━</span> 配送路線</p>
        <p><b>點擊標記</b>查看詳細資訊</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def main():
    # 解析命令列參數
    args = sys.argv[1:]
    use_routing = True
    plan_date = date.today().strftime("%Y-%m-%d")

    for arg in args:
        if arg == "--no-routing":
            use_routing = False
        elif not arg.startswith("-"):
            plan_date = arg

    print(f"📅 取得 {plan_date} 的配送路線...")
    if use_routing:
        print("🗺️  將使用 OSRM 取得實際道路路線（如需跳過，加上 --no-routing）")

    # 檢查 API 連線
    try:
        response = requests.get(f"{API_BASE_URL.replace('/api/v1', '')}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API 服務器回應異常")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ 無法連線到 API 服務器: {e}")
        print("\n請確認 FastAPI 服務器已啟動:")
        print("  uvicorn app.main:app --reload --port 8000")
        sys.exit(1)

    # 取得路線資料
    routes = get_routes_by_date(plan_date)

    if not routes:
        print(f"⚠️  找不到 {plan_date} 的路線資料")
        print("\n提示:")
        print("  1. 確認日期格式正確 (YYYY-MM-DD)")
        print("  2. 確認該日期已執行過優化")
        print("  3. 使用 POST /api/v1/optimization 建立路線")
        sys.exit(0)

    print(f"✅ 找到 {len(routes)} 條路線")

    for route in routes:
        print(f"   - {route['route_code']}: {route['vehicle']['license_plate']} ({route['total_stops']} 個停靠點)")

    print("\n🗺️  正在生成地圖...")

    # 創建地圖
    route_map = create_route_map(routes, plan_date, use_routing=use_routing)

    # 儲存地圖
    filename = f"routes_map_{plan_date.replace('-', '')}.html"
    route_map.save(filename)

    print(f"✅ 地圖已生成: {filename}")
    print(f"\n📂 請用瀏覽器打開此檔案查看互動式地圖")
    print(f"\n功能說明:")
    print(f"  • 點擊標記查看詳細資訊（訂單、溫度、時間等）")
    print(f"  • 使用左側圖層控制顯示/隱藏特定路線")
    print(f"  • 使用測量工具測量距離")
    print(f"  • 使用全屏按鈕放大查看")
    print(f"  • 不同顏色代表不同車輛的路線")
    print(f"  • 數字標籤顯示停靠順序")
    print(f"  • 綠色圖標表示溫度可行，紅色表示溫度超標")


if __name__ == '__main__':
    main()
