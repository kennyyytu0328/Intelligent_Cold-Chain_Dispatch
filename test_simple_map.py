"""
簡單測試地圖
"""
import folium
import sys

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

# 創建地圖（台北 101 為中心）
m = folium.Map(
    location=[25.0330, 121.5654],
    zoom_start=13,
    tiles='OpenStreetMap',
)

# 倉庫位置
depot = (25.0330, 121.5654)

# 添加倉庫標記
folium.Marker(
    location=depot,
    popup="倉庫",
    icon=folium.Icon(color='black', icon='home', prefix='fa'),
    tooltip="倉庫",
).add_to(m)

# 3個停靠點
stops = [
    (25.0418, 121.5654, "停靠點 1"),
    (25.0478, 121.5173, "停靠點 2"),
    (25.0522, 121.5437, "停靠點 3"),
]

# 添加停靠點標記
for idx, (lat, lon, name) in enumerate(stops, 1):
    folium.Marker(
        location=(lat, lon),
        popup=name,
        icon=folium.Icon(color='green', icon='check-circle', prefix='fa'),
        tooltip=name,
    ).add_to(m)

# 繪製路線
route_coords = [depot]
for lat, lon, _ in stops:
    route_coords.append((lat, lon))
route_coords.append(depot)  # 返回倉庫

print(f"路線座標數量: {len(route_coords)}")
print(f"路線座標: {route_coords}")

folium.PolyLine(
    locations=route_coords,
    color='red',
    weight=5,
    opacity=0.8,
    popup="測試路線",
    tooltip="紅色路線",
).add_to(m)

# 儲存地圖
filename = "test_simple_map.html"
m.save(filename)

print(f"✅ 測試地圖已生成: {filename}")
print("請用瀏覽器打開查看")
