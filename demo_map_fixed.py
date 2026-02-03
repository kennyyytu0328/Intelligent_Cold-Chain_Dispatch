"""
生成示範地圖（修正版）

使用方式:
    python demo_map_fixed.py

會生成 demo_routes_map_fixed.html 檔案，展示地圖視覺化功能
"""
import folium
from folium import plugins
import sys

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

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
                "coords": (25.0418, 121.5654),  # 信義商圈
                "address": "台北市信義區信義路五段7號",
                "temp": 3.5,
                "temp_limit": 5.0,
                "time": "08:30",
            },
            {
                "seq": 2,
                "name": "訂單 #002",
                "coords": (25.0478, 121.5173),  # 大安區
                "address": "台北市大安區忠孝東路四段",
                "temp": 4.2,
                "temp_limit": 5.0,
                "time": "09:15",
            },
            {
                "seq": 3,
                "name": "訂單 #003",
                "coords": (25.0522, 121.5437),  # 南京復興
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
                "coords": (25.0122, 121.4627),  # 板橋
                "address": "新北市板橋區縣民大道二段",
                "temp": 2.8,
                "temp_limit": 5.0,
                "time": "08:45",
            },
            {
                "seq": 2,
                "name": "訂單 #005",
                "coords": (25.0219, 121.4650),  # 板橋新埔
                "address": "新北市板橋區民權路",
                "temp": 5.5,  # 溫度超標
                "temp_limit": 5.0,
                "time": "09:30",
            },
            {
                "seq": 3,
                "name": "訂單 #006",
                "coords": (24.9896, 121.3041),  # 土城
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
                "coords": (25.0800, 121.5800),  # 內湖
                "address": "台北市內湖區民權東路六段",
                "temp": 3.8,
                "temp_limit": 5.0,
                "time": "09:00",
            },
            {
                "seq": 2,
                "name": "訂單 #008",
                "coords": (25.0919, 121.5198),  # 士林
                "address": "台北市士林區中山北路",
                "temp": 6.2,  # 溫度超標
                "temp_limit": 5.0,
                "time": "10:15",
            },
        ],
    },
]


def create_demo_map():
    """創建示範地圖"""

    # 計算中心點
    center_lat = 25.0330
    center_lon = 121.5654

    # 創建地圖
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles='OpenStreetMap',
    )

    print(f"創建地圖中心點: ({center_lat}, {center_lon})")

    # 為每條路線添加圖層
    for route_idx, route in enumerate(DEMO_ROUTES):
        color = route["color"]
        vehicle = route["vehicle"]
        depot = route["depot"]

        print(f"\n處理路線 {route_idx + 1}: {vehicle}")
        print(f"  倉庫位置: {depot}")
        print(f"  停靠點數量: {len(route['stops'])}")

        # 創建路線圖層
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
                    <p><b>總距離:</b> 約 25.3 km</p>
                    <p><b>總時長:</b> 約 150 分鐘</p>
                </div>
                """,
                max_width=300,
            ),
            icon=folium.Icon(color='black', icon='home', prefix='fa'),
            tooltip="倉庫",
        ).add_to(feature_group)

        # 路線點集合
        route_coords = [depot]

        # 標記每個停靠點
        for stop in route["stops"]:
            coords = stop["coords"]
            route_coords.append(coords)

            print(f"  添加停靠點 {stop['seq']}: {coords}")

            # 判斷溫度是否超標
            is_over_temp = stop["temp"] > stop["temp_limit"]
            icon_color = 'red' if is_over_temp else 'green'
            icon_symbol = 'exclamation-triangle' if is_over_temp else 'check-circle'

            # 彈出視窗
            popup_html = f"""
            <div style="width:300px">
                <h4>📍 停靠點 #{stop['seq']}</h4>
                <hr>
                <p><b>訂單:</b> {stop['name']}</p>
                <p><b>地址:</b> {stop['address']}</p>
                <hr>
                <p><b>預計到達:</b> {stop['time']}</p>
                <p><b>服務時長:</b> 15 分鐘</p>
                <p><b>緩衝時間:</b> 10 分鐘</p>
                <hr>
                <p><b>🌡️ 到達溫度:</b> <span style="color:{'red' if is_over_temp else 'green'}">{stop['temp']:.1f}°C</span></p>
                <p><b>溫度上限:</b> {stop['temp_limit']:.1f}°C</p>
                <p><b>可行性:</b> <span style="color:{'red' if is_over_temp else 'green'}">{'❌ 溫度超標' if is_over_temp else '✅ 溫度正常'}</span></p>
                <hr>
                <p><b>貨物重量:</b> 150.0 kg</p>
                <p><b>貨物體積:</b> 5.0 m³</p>
                <p><b>SLA 等級:</b> STRICT</p>
            </div>
            """

            # 添加標記
            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_html, max_width=350),
                icon=folium.Icon(
                    color=icon_color,
                    icon=icon_symbol,
                    prefix='fa',
                ),
                tooltip=f"停靠點 #{stop['seq']}: {stop['name']}",
            ).add_to(feature_group)

            # 添加序號標籤
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

        # 返回倉庫
        route_coords.append(depot)

        print(f"  路線總共 {len(route_coords)} 個點")

        # 畫路線（使用較粗的線條）
        folium.PolyLine(
            locations=route_coords,
            color=color,
            weight=6,
            opacity=0.8,
            popup=f"路線: {vehicle}",
            tooltip=f"{vehicle} - {len(route['stops'])} 個停靠點",
        ).add_to(feature_group)

        print(f"  路線繪製完成，顏色: {color}")

        # 添加圖層到地圖
        feature_group.add_to(m)
        print(f"  圖層已添加到地圖")

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
    title_html = '''
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
        🗺️ ICCDDS 配送路線圖 - 示範
        <br>
        <span style="font-size: 12px; font-weight: normal;">
            共 3 條路線，8 個停靠點
        </span>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))

    # 添加圖例
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
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#e6194B;"></span> 紅色路線</p>
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#3cb44b;"></span> 綠色路線</p>
        <p><span style="display:inline-block; width:30px; height:3px; background-color:#4363d8;"></span> 藍色路線</p>
        <p><b>點擊標記</b>查看詳細資訊</p>
        <hr>
        <p style="font-size:10px; color:grey;">這是示範資料，用於展示地圖功能</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def main():
    print("🗺️  正在生成示範地圖（修正版）...")
    print()
    print("📍 示範資料包含:")
    print("   - 3 台配送車輛")
    print("   - 8 個配送停靠點")
    print("   - 涵蓋台北市和新北市區域")
    print("   - 包含溫度超標範例（訂單 #005 和 #008）")
    print()

    # 創建地圖
    demo_map = create_demo_map()

    # 儲存地圖
    filename = "demo_routes_map_fixed.html"
    demo_map.save(filename)

    print()
    print(f"✅ 示範地圖已生成: {filename}")
    print()
    print("📂 請用瀏覽器打開此檔案查看互動式地圖")
    print()
    print("🎯 地圖功能展示:")
    print("   • 點擊標記查看訂單詳細資訊")
    print("   • 使用左側圖層控制顯示/隱藏特定車輛")
    print("   • 使用測量工具測量距離")
    print("   • 使用全屏按鈕放大查看")
    print("   • 紅色標記表示溫度超標的停靠點")
    print("   • 路線以粗線條顯示（紅、綠、藍）")
    print()
    print("💡 提示:")
    print("   這是示範資料，實際使用請執行:")
    print("   python visualize_routes.py [plan_date]")


if __name__ == '__main__':
    try:
        main()
    except ImportError as e:
        print("❌ 錯誤: 缺少必要的 Python 套件")
        print()
        print("請先安裝:")
        print("  pip install folium")
        print()
        print(f"詳細錯誤訊息: {e}")
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
