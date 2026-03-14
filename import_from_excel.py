"""
從 Excel 檔案批量導入訂單和車輛到 ICCDDS 系統

使用方式:
    python import_from_excel.py ICCDDS_Import_Template.xlsx

需要先啟動 FastAPI 服務器:
    uvicorn app.main:app --reload --port 8000
"""
import sys
import pandas as pd
import requests
from typing import Optional

# 設置 Windows 控制台編碼
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

API_BASE_URL = "http://localhost:8000/api/v1"


def import_vehicles(df: pd.DataFrame, verbose: bool = True) -> dict:
    """
    從 DataFrame 導入車輛資料

    Returns:
        {"success": count, "failed": count, "errors": [...]}
    """
    result = {"success": 0, "failed": 0, "errors": []}

    for idx, row in df.iterrows():
        try:
            # 跳過空行
            if pd.isna(row.get('license_plate')):
                continue

            # 構建請求資料
            vehicle_data = {
                "license_plate": str(row['license_plate']).strip(),
                "capacity_weight": float(row['capacity_weight_kg']),
                "capacity_volume": float(row['capacity_volume_m3']),
                "insulation_grade": str(row['insulation_grade']).strip().upper(),
                "door_type": str(row['door_type']).strip().upper(),
                "has_strip_curtains": str(row['has_strip_curtains']).strip().upper() == 'TRUE',
                "cooling_rate": float(row['cooling_rate_celsius_per_min']),
            }

            # 可選欄位
            if not pd.isna(row.get('driver_name')):
                vehicle_data['driver_name'] = str(row['driver_name']).strip()

            # 發送 API 請求
            response = requests.post(
                f"{API_BASE_URL}/vehicles",
                json=vehicle_data,
                timeout=10,
            )

            if response.status_code in (200, 201):
                result["success"] += 1
                if verbose:
                    print(f"  ✅ 車輛 {vehicle_data['license_plate']} 導入成功")
            else:
                result["failed"] += 1
                error_msg = f"行 {idx + 2}: {response.status_code} - {response.text}"
                result["errors"].append(error_msg)
                if verbose:
                    print(f"  ❌ 車輛 {vehicle_data['license_plate']} 導入失敗: {response.text}")

        except Exception as e:
            result["failed"] += 1
            error_msg = f"行 {idx + 2}: {str(e)}"
            result["errors"].append(error_msg)
            if verbose:
                print(f"  ❌ 處理行 {idx + 2} 時發生錯誤: {e}")

    return result


def import_shipments(df: pd.DataFrame, verbose: bool = True) -> dict:
    """
    從 DataFrame 導入訂單資料

    Returns:
        {"success": count, "failed": count, "errors": [...]}
    """
    result = {"success": 0, "failed": 0, "errors": []}

    for idx, row in df.iterrows():
        try:
            # 跳過空行
            if pd.isna(row.get('order_number')):
                continue

            # 構建時間窗（選填 — 空白表示不限時間）
            time_windows = []

            # 第一個時間窗（選填）
            if not pd.isna(row.get('time_window_1_start')) and not pd.isna(row.get('time_window_1_end')):
                time_windows.append({
                    "start": str(row['time_window_1_start']).strip(),
                    "end": str(row['time_window_1_end']).strip(),
                })

            # 第二個時間窗（選填）
            if not pd.isna(row.get('time_window_2_start')) and not pd.isna(row.get('time_window_2_end')):
                tw2_start = str(row['time_window_2_start']).strip()
                tw2_end = str(row['time_window_2_end']).strip()
                if tw2_start and tw2_end:
                    time_windows.append({
                        "start": tw2_start,
                        "end": tw2_end,
                    })

            # 構建請求資料
            shipment_data = {
                "order_number": str(row['order_number']).strip(),
                "delivery_address": str(row['delivery_address']).strip(),
                "latitude": float(row['latitude']),
                "longitude": float(row['longitude']),
                "weight": float(row['weight_kg']),
                "time_windows": time_windows,
                "sla_tier": str(row['sla_tier']).strip().upper(),
                "temp_limit_upper": float(row['temp_limit_upper_celsius']),
                "service_duration": int(row['service_duration_minutes']),
                "priority": int(row['priority']),
            }

            # 可選欄位
            if not pd.isna(row.get('volume_m3')):
                shipment_data['volume'] = float(row['volume_m3'])

            if not pd.isna(row.get('temp_limit_lower_celsius')):
                shipment_data['temp_limit_lower'] = float(row['temp_limit_lower_celsius'])

            # 發送 API 請求
            response = requests.post(
                f"{API_BASE_URL}/shipments",
                json=shipment_data,
                timeout=10,
            )

            if response.status_code in (200, 201):
                result["success"] += 1
                if verbose:
                    print(f"  ✅ 訂單 {shipment_data['order_number']} 導入成功")
            else:
                result["failed"] += 1
                error_msg = f"行 {idx + 2}: {response.status_code} - {response.text}"
                result["errors"].append(error_msg)
                if verbose:
                    print(f"  ❌ 訂單 {shipment_data['order_number']} 導入失敗: {response.text}")

        except Exception as e:
            result["failed"] += 1
            error_msg = f"行 {idx + 2}: {str(e)}"
            result["errors"].append(error_msg)
            if verbose:
                print(f"  ❌ 處理行 {idx + 2} 時發生錯誤: {e}")

    return result


def main():
    if len(sys.argv) < 2:
        print("❌ 使用方式: python import_from_excel.py <excel_file_path>")
        print()
        print("範例:")
        print("  python import_from_excel.py ICCDDS_Import_Template.xlsx")
        sys.exit(1)

    excel_file = sys.argv[1]

    print(f"📂 讀取 Excel 檔案: {excel_file}")
    print()

    try:
        # 讀取 Excel
        xl_file = pd.ExcelFile(excel_file)

        # 檢查 API 連線
        print("🔌 檢查 API 連線...")
        try:
            response = requests.get(f"{API_BASE_URL.replace('/api/v1', '')}/health", timeout=5)
            if response.status_code == 200:
                print("  ✅ API 服務器運行中")
            else:
                print(f"  ⚠️  API 服務器回應異常: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"  ❌ 無法連線到 API 服務器: {e}")
            print()
            print("請確認 FastAPI 服務器已啟動:")
            print("  uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

        print()

        # 導入車輛
        if '車輛 (Vehicles)' in xl_file.sheet_names or 'Vehicles' in xl_file.sheet_names:
            sheet_name = '車輛 (Vehicles)' if '車輛 (Vehicles)' in xl_file.sheet_names else 'Vehicles'
            print(f"🚛 開始導入車輛資料 (工作表: {sheet_name})...")
            df_vehicles = pd.read_excel(excel_file, sheet_name=sheet_name)
            vehicle_result = import_vehicles(df_vehicles)
            print()
            print(f"  車輛導入結果: ✅ 成功 {vehicle_result['success']} 筆, ❌ 失敗 {vehicle_result['failed']} 筆")
            if vehicle_result['errors']:
                print("  錯誤詳情:")
                for error in vehicle_result['errors'][:5]:  # 只顯示前5個錯誤
                    print(f"    - {error}")
            print()
        else:
            print("⚠️  找不到車輛工作表，跳過車輛導入")
            print()

        # 導入訂單
        if '訂單 (Shipments)' in xl_file.sheet_names or 'Shipments' in xl_file.sheet_names:
            sheet_name = '訂單 (Shipments)' if '訂單 (Shipments)' in xl_file.sheet_names else 'Shipments'
            print(f"📦 開始導入訂單資料 (工作表: {sheet_name})...")
            df_shipments = pd.read_excel(excel_file, sheet_name=sheet_name)
            shipment_result = import_shipments(df_shipments)
            print()
            print(f"  訂單導入結果: ✅ 成功 {shipment_result['success']} 筆, ❌ 失敗 {shipment_result['failed']} 筆")
            if shipment_result['errors']:
                print("  錯誤詳情:")
                for error in shipment_result['errors'][:5]:  # 只顯示前5個錯誤
                    print(f"    - {error}")
            print()
        else:
            print("⚠️  找不到訂單工作表，跳過訂單導入")
            print()

        print("=" * 60)
        print("✅ 導入完成！")
        print()
        print("下一步:")
        print("  1. 查看導入的資料:")
        print("     http://localhost:8000/api/v1/docs")
        print("  2. 啟動優化任務:")
        print("     POST http://localhost:8000/api/v1/optimization")

    except FileNotFoundError:
        print(f"❌ 找不到檔案: {excel_file}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
