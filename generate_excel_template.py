"""
生成 ICCDDS 批量導入用的 Excel 範例檔

使用方式:
    python generate_excel_template.py

會生成 ICCDDS_Import_Template.xlsx 檔案，包含訂單和車輛兩個工作表
"""
import pandas as pd
from datetime import datetime
import sys

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

def generate_template():
    """生成 Excel 範例檔"""

    # ==================== 訂單(Shipments)工作表 ====================
    shipments_data = {
        'order_number': [
            'ORD-2024-001',
            'ORD-2024-002',
            'ORD-2024-003',
        ],
        'delivery_address': [
            '台北市信義區信義路五段7號',
            '台北市中山區南京東路三段219號',
            '新北市板橋區縣民大道二段7號',
        ],
        'latitude': [
            25.0330,
            25.0522,
            25.0122,
        ],
        'longitude': [
            121.5654,
            121.5437,
            121.4627,
        ],
        'weight_kg': [
            150.0,
            80.5,
            200.0,
        ],
        'volume_m3': [
            5.0,
            3.2,
            6.5,
        ],
        'time_window_1_start': [
            '08:00',
            '09:00',
            '13:00',
        ],
        'time_window_1_end': [
            '10:00',
            '11:00',
            '15:00',
        ],
        'time_window_2_start': [
            '14:00',
            '',
            '17:00',
        ],
        'time_window_2_end': [
            '16:00',
            '',
            '19:00',
        ],
        'sla_tier': [
            'STRICT',
            'STANDARD',
            'STRICT',
        ],
        'temp_limit_upper_celsius': [
            5.0,
            8.0,
            4.0,
        ],
        'temp_limit_lower_celsius': [
            -2.0,
            '',
            0.0,
        ],
        'service_duration_minutes': [
            15,
            10,
            20,
        ],
        'priority': [
            80,
            50,
            90,
        ],
    }

    df_shipments = pd.DataFrame(shipments_data)

    # ==================== 車輛(Vehicles)工作表 ====================
    vehicles_data = {
        'license_plate': [
            'ABC-1234',
            'XYZ-5678',
            'DEF-9012',
        ],
        'capacity_weight_kg': [
            3000.0,
            2500.0,
            3500.0,
        ],
        'capacity_volume_m3': [
            15.0,
            12.0,
            18.0,
        ],
        'insulation_grade': [
            'STANDARD',
            'PREMIUM',
            'STANDARD',
        ],
        'door_type': [
            'ROLL',
            'ROLL',
            'SWING',
        ],
        'has_strip_curtains': [
            'TRUE',
            'TRUE',
            'FALSE',
        ],
        'cooling_rate_celsius_per_min': [
            -2.5,
            -3.0,
            -2.0,
        ],
        'driver_name': [
            '王大明',
            '李小華',
            '張志強',
        ],
    }

    df_vehicles = pd.DataFrame(vehicles_data)

    # ==================== 說明(Instructions)工作表 ====================
    instructions_data = {
        '欄位說明': [
            '',
            '【訂單工作表 (Shipments)】',
            'order_number',
            'delivery_address',
            'latitude',
            'longitude',
            'weight_kg',
            'volume_m3',
            'time_window_1_start/end',
            'time_window_2_start/end',
            'sla_tier',
            'temp_limit_upper_celsius',
            'temp_limit_lower_celsius',
            'service_duration_minutes',
            'priority',
            '',
            '【車輛工作表 (Vehicles)】',
            'license_plate',
            'capacity_weight_kg',
            'capacity_volume_m3',
            'insulation_grade',
            'door_type',
            'has_strip_curtains',
            'cooling_rate_celsius_per_min',
            'driver_name',
            '',
            '【注意事項】',
            '1. 時間格式',
            '2. 多時間窗',
            '3. SLA 等級',
            '4. 溫度限制',
            '5. 保溫等級',
            '6. 門型',
        ],
        '說明': [
            '',
            '',
            '訂單編號（必填，唯一）',
            '送貨地址（必填）',
            '緯度（必填，小數格式如 25.0330）',
            '經度（必填，小數格式如 121.5654）',
            '貨物重量，單位：公斤（必填）',
            '貨物體積，單位：立方米（選填，可留空）',
            '第一個時間窗的開始/結束時間，格式 HH:MM（必填）',
            '第二個時間窗（選填，可留空表示只有一個時間窗）',
            'STRICT（嚴格）或 STANDARD（標準），必填',
            '最高允收溫度，單位：攝氏度（必填）',
            '最低允收溫度（選填，可留空）',
            '卸貨時間，單位：分鐘（必填，通常 10-30）',
            '優先級 0-100，數字越大越優先（必填）',
            '',
            '',
            '車牌號碼（必填，唯一，如 ABC-1234）',
            '載重容量，單位：公斤（必填）',
            '容積容量，單位：立方米（必填）',
            'PREMIUM（優質）/STANDARD（標準）/BASIC（基礎）',
            'ROLL（捲門）或 SWING（對開門）',
            'TRUE（有門簾）或 FALSE（無門簾）',
            '製冷速率，單位：°C/分鐘（負數表示降溫，如 -2.5）',
            '駕駛員姓名（選填）',
            '',
            '',
            '時間必須使用 24 小時制，格式為 HH:MM（如 08:00, 14:30）',
            '每個訂單最多支援 2 個時間窗，滿足任一即可。若只有一個時間窗，time_window_2 留空',
            'STRICT 表示必須滿足時間窗，否則不派送；STANDARD 表示可延遲但有罰分',
            'temp_limit_upper 為到貨時的最高溫度。若超過此溫度，客戶可能拒收',
            'PREMIUM（K=0.02，保溫最佳）> STANDARD（K=0.05）> BASIC（K=0.10，保溫較差）',
            'ROLL 捲門熱損較低（C=0.8），SWING 對開門熱損較高（C=1.2）',
        ],
        '範例': [
            '',
            '',
            'ORD-2024-001',
            '台北市信義區信義路五段7號',
            '25.0330',
            '121.5654',
            '150.0',
            '5.0',
            '08:00 ~ 10:00',
            '（選填）14:00 ~ 16:00',
            'STRICT 或 STANDARD',
            '5.0',
            '-2.0（選填）',
            '15',
            '80',
            '',
            '',
            'ABC-1234',
            '3000.0',
            '15.0',
            'STANDARD',
            'ROLL',
            'TRUE',
            '-2.5',
            '王大明',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
        ],
    }

    df_instructions = pd.DataFrame(instructions_data)

    # ==================== 寫入 Excel ====================
    filename = 'ICCDDS_Import_Template.xlsx'

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 寫入工作表
        df_instructions.to_excel(writer, sheet_name='使用說明', index=False)
        df_shipments.to_excel(writer, sheet_name='訂單 (Shipments)', index=False)
        df_vehicles.to_excel(writer, sheet_name='車輛 (Vehicles)', index=False)

        # 調整欄寬
        workbook = writer.book

        # 說明工作表
        ws_instructions = workbook['使用說明']
        ws_instructions.column_dimensions['A'].width = 35
        ws_instructions.column_dimensions['B'].width = 70
        ws_instructions.column_dimensions['C'].width = 35

        # 訂單工作表
        ws_shipments = workbook['訂單 (Shipments)']
        for col in ws_shipments.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 40)
            ws_shipments.column_dimensions[column].width = adjusted_width

        # 車輛工作表
        ws_vehicles = workbook['車輛 (Vehicles)']
        for col in ws_vehicles.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            ws_vehicles.column_dimensions[column].width = adjusted_width

    print(f"✅ Excel 範例檔已生成: {filename}")
    print(f"   - 包含 3 個工作表:")
    print(f"     1. 使用說明 (欄位說明和注意事項)")
    print(f"     2. 訂單 (Shipments) - 3 筆範例資料")
    print(f"     3. 車輛 (Vehicles) - 3 筆範例資料")
    print()
    print("📋 使用步驟:")
    print("   1. 打開此 Excel 檔案")
    print("   2. 在「訂單」和「車輛」工作表中填寫或修改資料")
    print("   3. 使用 import_from_excel.py 腳本導入資料到系統")


if __name__ == '__main__':
    try:
        generate_template()
    except ImportError as e:
        print("❌ 錯誤: 缺少必要的 Python 套件")
        print()
        print("請先安裝以下套件:")
        print("  pip install pandas openpyxl")
        print()
        print(f"詳細錯誤訊息: {e}")
