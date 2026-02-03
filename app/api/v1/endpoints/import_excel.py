"""
Excel import API endpoints for vehicles and shipments.
"""
import io
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models import Vehicle, Shipment
from app.models.enums import InsulationGrade, DoorType, SLATier

router = APIRouter()


def parse_decimal(value, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Safely parse a value to Decimal."""
    if pd.isna(value) or value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def parse_bool(value, default: bool = False) -> bool:
    """Safely parse a value to boolean."""
    if pd.isna(value) or value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in ("TRUE", "YES", "1", "Y")
    return bool(value)


def parse_insulation_grade(value) -> InsulationGrade:
    """Parse insulation grade from string."""
    if pd.isna(value) or value is None:
        return InsulationGrade.STANDARD
    val = str(value).strip().upper()
    if val in ("PREMIUM", "P"):
        return InsulationGrade.PREMIUM
    if val in ("BASIC", "B"):
        return InsulationGrade.BASIC
    return InsulationGrade.STANDARD


def parse_door_type(value) -> DoorType:
    """Parse door type from string."""
    if pd.isna(value) or value is None:
        return DoorType.ROLL
    val = str(value).strip().upper()
    if val in ("SWING", "S"):
        return DoorType.SWING
    return DoorType.ROLL


def parse_sla_tier(value) -> SLATier:
    """Parse SLA tier from string."""
    if pd.isna(value) or value is None:
        return SLATier.STANDARD
    val = str(value).strip().upper()
    if val in ("STRICT", "S"):
        return SLATier.STRICT
    return SLATier.STANDARD


def parse_time(value) -> Optional[str]:
    """Parse time value to HH:MM format."""
    if pd.isna(value) or value is None or value == "":
        return None
    val = str(value).strip()
    # Handle datetime objects from Excel
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    # Handle "HH:MM:SS" format
    if len(val) == 8 and val[2] == ":" and val[5] == ":":
        return val[:5]
    # Handle "HH:MM" format
    if len(val) == 5 and val[2] == ":":
        return val
    # Handle numeric (Excel time as fraction of day)
    try:
        hours = float(val) * 24
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return None


@router.post("/vehicles")
async def import_vehicles(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Import vehicles from Excel file.

    Expected columns:
    - license_plate (required): Vehicle license plate
    - capacity_weight (required): Max weight capacity in kg
    - capacity_volume (required): Max volume capacity in m³
    - driver_name: Driver name
    - insulation_grade: PREMIUM, STANDARD, or BASIC
    - door_type: ROLL or SWING
    - has_strip_curtains: TRUE/FALSE
    - cooling_rate: Cooling rate in °C/min (negative value)
    - min_temp_capability: Minimum achievable temperature
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {str(e)}")

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Check required columns
    required_cols = ["license_plate", "capacity_weight", "capacity_volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}"
        )

    created = []
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed + header)

        try:
            license_plate = str(row["license_plate"]).strip()
            if not license_plate or license_plate == "nan":
                errors.append({"row": row_num, "error": "Missing license_plate"})
                continue

            # Check for duplicate
            existing = await session.execute(
                select(Vehicle).where(Vehicle.license_plate == license_plate)
            )
            if existing.scalar_one_or_none():
                errors.append({"row": row_num, "error": f"Duplicate license_plate: {license_plate}"})
                continue

            capacity_weight = parse_decimal(row.get("capacity_weight"))
            capacity_volume = parse_decimal(row.get("capacity_volume"))

            if capacity_weight is None or capacity_weight <= 0:
                errors.append({"row": row_num, "error": "Invalid capacity_weight"})
                continue
            if capacity_volume is None or capacity_volume <= 0:
                errors.append({"row": row_num, "error": "Invalid capacity_volume"})
                continue

            insulation_grade = parse_insulation_grade(row.get("insulation_grade"))
            door_type = parse_door_type(row.get("door_type"))

            vehicle = Vehicle(
                license_plate=license_plate,
                driver_name=str(row.get("driver_name", "")).strip() if pd.notna(row.get("driver_name")) else None,
                capacity_weight=capacity_weight,
                capacity_volume=capacity_volume,
                internal_length=parse_decimal(row.get("internal_length")),
                internal_width=parse_decimal(row.get("internal_width")),
                internal_height=parse_decimal(row.get("internal_height")),
                insulation_grade=insulation_grade,
                k_value=Decimal(str(insulation_grade.k_value)),
                door_type=door_type,
                door_coefficient=Decimal(str(door_type.coefficient)),
                has_strip_curtains=parse_bool(row.get("has_strip_curtains")),
                cooling_rate=parse_decimal(row.get("cooling_rate"), Decimal("-2.5")),
                min_temp_capability=parse_decimal(row.get("min_temp_capability"), Decimal("-25.0")),
            )

            session.add(vehicle)
            created.append(license_plate)

        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    await session.flush()

    return {
        "imported": len(created),
        "errors": len(errors),
        "created_vehicles": created[:20],  # Limit response size
        "error_details": errors[:20] if errors else [],
    }


@router.post("/shipments")
async def import_shipments(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Import shipments from Excel file.

    Expected columns:
    - order_number (required): Unique order identifier
    - delivery_address (required): Delivery address
    - latitude (required): Delivery latitude
    - longitude (required): Delivery longitude
    - weight (required): Weight in kg
    - time_window_1_start: First time window start (HH:MM)
    - time_window_1_end: First time window end (HH:MM)
    - time_window_2_start: Second time window start (optional)
    - time_window_2_end: Second time window end (optional)
    - sla_tier: STRICT or STANDARD
    - temp_limit_upper: Maximum temperature limit (°C)
    - temp_limit_lower: Minimum temperature limit (°C)
    - service_duration: Service time in minutes
    - volume: Volume in m³
    - priority: Priority (0-100)
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {str(e)}")

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Check required columns
    required_cols = ["order_number", "delivery_address", "latitude", "longitude", "weight"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}"
        )

    created = []
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2

        try:
            order_number = str(row["order_number"]).strip()
            if not order_number or order_number == "nan":
                errors.append({"row": row_num, "error": "Missing order_number"})
                continue

            # Check for duplicate
            existing = await session.execute(
                select(Shipment).where(Shipment.order_number == order_number)
            )
            if existing.scalar_one_or_none():
                errors.append({"row": row_num, "error": f"Duplicate order_number: {order_number}"})
                continue

            delivery_address = str(row["delivery_address"]).strip()
            if not delivery_address or delivery_address == "nan":
                errors.append({"row": row_num, "error": "Missing delivery_address"})
                continue

            latitude = parse_decimal(row.get("latitude"))
            longitude = parse_decimal(row.get("longitude"))
            weight = parse_decimal(row.get("weight"))

            if latitude is None or not (-90 <= latitude <= 90):
                errors.append({"row": row_num, "error": "Invalid latitude"})
                continue
            if longitude is None or not (-180 <= longitude <= 180):
                errors.append({"row": row_num, "error": "Invalid longitude"})
                continue
            if weight is None or weight <= 0:
                errors.append({"row": row_num, "error": "Invalid weight"})
                continue

            # Parse time windows
            time_windows = []
            tw1_start = parse_time(row.get("time_window_1_start"))
            tw1_end = parse_time(row.get("time_window_1_end"))
            if tw1_start and tw1_end:
                time_windows.append({"start": tw1_start, "end": tw1_end})

            tw2_start = parse_time(row.get("time_window_2_start"))
            tw2_end = parse_time(row.get("time_window_2_end"))
            if tw2_start and tw2_end:
                time_windows.append({"start": tw2_start, "end": tw2_end})

            # Default time window if none provided
            if not time_windows:
                time_windows = [{"start": "08:00", "end": "18:00"}]

            geo_location = WKTElement(
                f"POINT({float(longitude)} {float(latitude)})",
                srid=4326,
            )

            shipment = Shipment(
                order_number=order_number,
                delivery_address=delivery_address,
                geo_location=geo_location,
                latitude=latitude,
                longitude=longitude,
                weight=weight,
                volume=parse_decimal(row.get("volume")),
                time_windows=time_windows,
                sla_tier=parse_sla_tier(row.get("sla_tier")),
                temp_limit_upper=parse_decimal(row.get("temp_limit_upper"), Decimal("5.0")),
                temp_limit_lower=parse_decimal(row.get("temp_limit_lower")),
                service_duration=int(parse_decimal(row.get("service_duration"), Decimal("15"))),
                priority=int(parse_decimal(row.get("priority"), Decimal("0"))),
                special_instructions=str(row.get("special_instructions", "")).strip() if pd.notna(row.get("special_instructions")) else None,
            )

            session.add(shipment)
            created.append(order_number)

        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    await session.flush()

    return {
        "imported": len(created),
        "errors": len(errors),
        "created_shipments": created[:20],
        "error_details": errors[:20] if errors else [],
    }


@router.get("/template/vehicles")
async def download_vehicle_template():
    """
    Download Excel template for vehicle import.
    """
    # Create sample data
    data = {
        "license_plate": ["ABC-1234", "XYZ-5678"],
        "capacity_weight": [1000, 1500],
        "capacity_volume": [10, 15],
        "driver_name": ["Driver A", "Driver B"],
        "insulation_grade": ["STANDARD", "PREMIUM"],
        "door_type": ["ROLL", "SWING"],
        "has_strip_curtains": ["TRUE", "FALSE"],
        "cooling_rate": [-2.5, -3.0],
        "min_temp_capability": [-25, -30],
        "internal_length": [4.0, 5.0],
        "internal_width": [2.0, 2.2],
        "internal_height": [2.0, 2.5],
    }

    df = pd.DataFrame(data)

    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Vehicles")

        # Add instructions sheet
        instructions = pd.DataFrame({
            "Column": [
                "license_plate", "capacity_weight", "capacity_volume",
                "driver_name", "insulation_grade", "door_type",
                "has_strip_curtains", "cooling_rate", "min_temp_capability",
                "internal_length", "internal_width", "internal_height"
            ],
            "Required": [
                "Yes", "Yes", "Yes",
                "No", "No", "No",
                "No", "No", "No",
                "No", "No", "No"
            ],
            "Description": [
                "Vehicle license plate (unique)",
                "Maximum weight capacity in kg",
                "Maximum volume capacity in m³",
                "Driver name",
                "PREMIUM (K=0.02), STANDARD (K=0.05), or BASIC (K=0.10)",
                "ROLL (C=0.8) or SWING (C=1.2)",
                "TRUE or FALSE - reduces heat loss by 50%",
                "Cooling rate in °C/min (negative value, e.g., -2.5)",
                "Minimum achievable temperature in °C",
                "Internal cargo length in meters",
                "Internal cargo width in meters",
                "Internal cargo height in meters"
            ],
            "Example": [
                "ABC-1234", "1000", "10",
                "John Smith", "STANDARD", "ROLL",
                "TRUE", "-2.5", "-25",
                "4.0", "2.0", "2.0"
            ]
        })
        instructions.to_excel(writer, index=False, sheet_name="Instructions")

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=vehicle_import_template.xlsx"}
    )


@router.get("/template/shipments")
async def download_shipment_template():
    """
    Download Excel template for shipment import.
    """
    # Create sample data
    data = {
        "order_number": ["ORD-001", "ORD-002"],
        "delivery_address": ["123 Main St, Taipei", "456 Oak Ave, Taipei"],
        "latitude": [25.0330, 25.0478],
        "longitude": [121.5654, 121.5170],
        "weight": [50, 75],
        "volume": [0.5, 0.8],
        "time_window_1_start": ["08:00", "09:00"],
        "time_window_1_end": ["12:00", "13:00"],
        "time_window_2_start": ["14:00", ""],
        "time_window_2_end": ["18:00", ""],
        "sla_tier": ["STRICT", "STANDARD"],
        "temp_limit_upper": [5, 8],
        "temp_limit_lower": [0, -2],
        "service_duration": [15, 20],
        "priority": [100, 50],
        "special_instructions": ["Handle with care", ""],
    }

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Shipments")

        # Add instructions sheet
        instructions = pd.DataFrame({
            "Column": [
                "order_number", "delivery_address", "latitude", "longitude", "weight",
                "volume", "time_window_1_start", "time_window_1_end",
                "time_window_2_start", "time_window_2_end",
                "sla_tier", "temp_limit_upper", "temp_limit_lower",
                "service_duration", "priority", "special_instructions"
            ],
            "Required": [
                "Yes", "Yes", "Yes", "Yes", "Yes",
                "No", "No", "No",
                "No", "No",
                "No", "No", "No",
                "No", "No", "No"
            ],
            "Description": [
                "Unique order identifier",
                "Full delivery address",
                "Delivery latitude (-90 to 90)",
                "Delivery longitude (-180 to 180)",
                "Weight in kg",
                "Volume in cubic meters",
                "First time window start (HH:MM)",
                "First time window end (HH:MM)",
                "Second time window start (optional)",
                "Second time window end (optional)",
                "STRICT (hard constraint) or STANDARD (soft constraint)",
                "Maximum acceptable temperature in °C",
                "Minimum acceptable temperature in °C",
                "Service/unloading time in minutes",
                "Priority 0-100 (higher = more important)",
                "Special handling instructions"
            ],
            "Example": [
                "ORD-001", "123 Main St, Taipei", "25.0330", "121.5654", "50",
                "0.5", "08:00", "12:00",
                "14:00", "18:00",
                "STRICT", "5", "0",
                "15", "100", "Handle with care"
            ]
        })
        instructions.to_excel(writer, index=False, sheet_name="Instructions")

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=shipment_import_template.xlsx"}
    )
