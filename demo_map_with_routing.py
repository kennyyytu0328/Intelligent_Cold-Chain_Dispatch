"""
生成示範地圖（含實際道路路線）

使用 OSRM (Open Source Routing Machine) 取得實際道路路線

使用方式:
    python demo_map_with_routing.py

會生成 demo_routes_map_routing.html 檔案
"""
import folium
from folium import plugins
import requests
import sys
import time

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

# OSRM 公共 API (免費)
OSRM_API_URL = "http://router.project-osrm.org/route/v1/driving"

# 示範資料：台北市區的配送路線
DEMO_ROUTES = [
    {
        "vehicle": "ABC-1234",
        "color": "#e6194B",  # 紅色
        "depot": (25.0330, 121.5654),  # 台北 101
        "stops": [
            {
                "seq": 1,
                "name": "訂單 #001",
                "coords": (25.0418, 121.5654),
                "address": "台北市信義區信義路五段7號",
                "temp": 3.5,
                "temp_limit": 5.0,
                "time": "08:30",
            },
            {
                "seq": 2,
                "name": "訂單 #002",
                "coords": (25.0478, 121.5173),
                "address": "台北市大安區忠孝東路四段",
                "temp": 4.2,
                "temp_limit": 5.0,
                "time": "09:15",
            },
            {
                "seq": 3,
                "name": "訂單 #003",
                "coords": (25.0522, 121.5437),
                "address": "台北市中山區南京東路三段",
                "temp": 4.8,
                "temp_limit": 5.0,
                "time": "10:00",
            },
        ],
    },
    {
        "vehicle": "XYZ-5678",
        "color": "#3cb44b",  # 綠色
        "depot": (25.0330, 121.5654),
        "stops": [
            {
                "seq": 1,
                "name": "訂單 #004",
                "coords": (25.0122, 121.4627),
                "address": "新北市板橋區縣民大道二段",
                "temp": 2.8,
                "temp_limit": 5.0,
                "time": "08:45",
            },
            {
                "seq": 2,
                "name": "訂單 #005",
                "coords": (25.0219, 121.4650),
                "address": "新北市板橋區民權路",
                "temp": 5.5,
                "temp_limit": 5.0,
                "time": "09:30",
            },
            {
                "seq": 3,
                "name": "訂單 #006",
                "coords": (24.9896, 121.3041),
                "address": "新北市土城區中央路",
                "temp": 4.5,
                "temp_limit": 5.0,
                "time": "10:30",
            },
        ],
    },
    {
        "vehicle": "DEF-9012",
        "color": "#4363d8",  # 藍色
        "depot": (25.0330, 121.5654),
        "stops": [
            {
                "seq": 1,
                "name": "訂單 #007",
                "coords": (25.0800, 121.5800),
                "address": "台北市內湖區民權東路六段",
                "temp": 3.8,
                "temp_limit": 5.0,
                "time": "09:00",
            },
            {
                "seq": 2,
                "name": "訂單 #008",
                "coords": (25.0919, 121.5198),
                "address": "台北市士林區中山北路",
                "temp": 6.2,
                "temp_limit": 5.0,
                "time": "10:15",
            },
        ],
    },
]


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
        "overview": "full",  # 完整路線
        "geometries": "geojson",  # GeoJSON 格式
        "steps": "false",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data["code"] == "Ok" and data["routes"]:
            # 取得路線座標 (GeoJSON 格式是 [lon, lat])
            route_coords = data["routes"][0]["geometry"]["coordinates"]
            # 轉換為 [lat, lon] 格式
            return [(coord[1], coord[0]) for coord in route_coords]
        else:
            print(f"  ⚠️ OSRM 無法取得路線: {data.get('code', 'Unknown error')}")
            return coordinates

    except requests.exceptions.RequestException as e:
        print(f"  ⚠️ OSRM API 請求失敗: {e}")
        return coordinates  # 失敗時返回原始直線座標


def create_demo_map():
    """創建含實際道路路線的示範地圖"""

    center_lat = 25.0330
    center_lon = 121.5654

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles='OpenStreetMap',
    )

    print(f"創建地圖中心點: ({center_lat}, {center_lon})")

    for route_idx, route in enumerate(DEMO_ROUTES):
        color = route["color"]
        vehicle = route["vehicle"]
        depot = route["depot"]

        print(f"\n處理路線 {route_idx + 1}: {vehicle}")

        feature_group = folium.FeatureGroup(
            name=f'🚛 {vehicle}',
            show=True,
        )

        # 標記倉庫
        folium.Marker(
            location=depot,
            popup=folium.Popup(
                f"""
                <div style="width:250px">
                    <h4>🏭 倉庫/配送中心</h4>
                    <p><b>地址:</b> 台北市信義區信義路五段7號</p>
                    <p><b>車輛:</b> {vehicle}</p>
                    <p><b>司機:</b> 王大明</p>
                    <p><b>總停靠點:</b> {len(route['stops'])} 個</p>
                </div>
                """,
                max_width=300,
            ),
            icon=folium.Icon(color='black', icon='home', prefix='fa'),
            tooltip="倉庫",
        ).add_to(feature_group)

        # 收集所有路線點
        waypoints = [depot]
        for stop in route["stops"]:
            waypoints.append(stop["coords"])
        waypoints.append(depot)  # 返回倉庫

        print(f"  取得 {len(waypoints)} 個路線點的實際道路路線...")

        # 使用 OSRM 取得實際道路路線
        road_route = get_osrm_route(waypoints)

        print(f"  實際道路路線包含 {len(road_route)} 個座標點")

        # 標記每個停靠點
        for stop in route["stops"]:
            coords = stop["coords"]
            is_over_temp = stop["temp"] > stop["temp_limit"]
            icon_color = 'red' if is_over_temp else 'green'
            icon_symbol = 'exclamation-triangle' if is_over_temp else 'check-circle'

            popup_html = f"""
            <div style="width:300px">
                <h4>📍 停靠點 #{stop['seq']}</h4>
                <hr>
                <p><b>訂單:</b> {stop['name']}</p>
                <p><b>地址:</b> {stop['address']}</p>
                <hr>
                <p><b>預計到達:</b> {stop['time']}</p>
                <p><b>服務時長:</b> 15 分鐘</p>
                <hr>
                <p><b>🌡️ 到達溫度:</b> <span style="color:{'red' if is_over_temp else 'green'}">{stop['temp']:.1f}°C</span></p>
                <p><b>溫度上限:</b> {stop['temp_limit']:.1f}°C</p>
                <p><b>可行性:</b> <span style="color:{'red' if is_over_temp else 'green'}">{'❌ 溫度超標' if is_over_temp else '✅ 溫度正常'}</span></p>
            </div>
            """

            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_html, max_width=350),
                icon=folium.Icon(color=icon_color, icon=icon_symbol, prefix='fa'),
                tooltip=f"停靠點 #{stop['seq']}: {stop['name']}",
            ).add_to(feature_group)

            # 序號標籤
            folium.Marker(
                location=coords,
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                        background-color: {color};
                        color: white;
                        font-weight: bold;
                        font-size: 14px;
                        border-radius: 50%;
                        width: 28px;
                        height: 28px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        border: 3px solid white;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.5);
                    ">{stop['seq']}</div>
                    """
                ),
            ).add_to(feature_group)

        # 畫實際道路路線
        if len(road_route) >= 2:
            folium.PolyLine(
                locations=road_route,
                color=color,
                weight=5,
                opacity=0.8,
                popup=f"路線: {vehicle}",
                tooltip=f"{vehicle} - {len(route['stops'])} 個停靠點 (實際道路路線)",
            ).add_to(feature_group)

        feature_group.add_to(m)

        # 避免 API 請求過快
        time.sleep(0.5)

    # 添加圖層控制
    folium.LayerControl(collapsed=False).add_to(m)
    plugins.Fullscreen().add_to(m)
    plugins.MeasureControl(position='topleft', primary_length_unit='kilometers').add_to(m)

    # 標題
    title_html = '''
    <div style="position: fixed;
                top: 10px;
                left: 50%;
                transform: translateX(-50%);
                background-color: white;
                border: 2px solid grey;
                border-radius: 5px;
                padding: 10px;
                font-family: Arial;
                font-size: 16px;
                font-weight: bold;
                z-index: 9999;
                box-shadow: 0 0 10px rgba(0,0,0,0.3);">
        🗺️ ICCDDS 配送路線圖 - 實際道路路線
        <br>
        <span style="font-size: 12px; font-weight: normal;">
            共 3 條路線，8 個停靠點 (使用 OSRM 路由)
        </span>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))

    # 圖例
    legend_html = '''
    <div style="position: fixed;
                bottom: 50px;
                right: 10px;
                width: 220px;
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
        <p><i class="fa fa-check-circle" style="color:green;"></i> 溫度正常</p>
        <p><i class="fa fa-exclamation-triangle" style="color:red;"></i> 溫度超標</p>
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#e6194B;"></span> ABC-1234</p>
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#3cb44b;"></span> XYZ-5678</p>
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#4363d8;"></span> DEF-9012</p>
        <hr>
        <p style="font-size:10px; color:grey;">路線沿實際道路顯示<br>(Powered by OSRM)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def main():
    print("🗺️  正在生成含實際道路路線的示範地圖...")
    print()
    print("📍 使用 OSRM (Open Source Routing Machine) 取得實際道路路線")
    print("   這可能需要幾秒鐘...")
    print()

    demo_map = create_demo_map()

    filename = "demo_routes_map_routing.html"
    demo_map.save(filename)

    print()
    print(f"✅ 地圖已生成: {filename}")
    print()
    print("📂 請用瀏覽器打開此檔案查看")
    print()
    print("🎯 地圖功能:")
    print("   • 路線沿實際道路顯示（不是直線）")
    print("   • 點擊標記查看詳細資訊")
    print("   • 圖層控制顯示/隱藏特定車輛")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
