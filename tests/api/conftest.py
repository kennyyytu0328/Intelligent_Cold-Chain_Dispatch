"""API test fixtures -- helpers for configuring mock session returns."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4


def make_mock_result(scalar_value=None, scalars_list=None):
    """Create a mock SQLAlchemy Result object."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)

    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=scalars_list or [])
    scalars_mock.unique = MagicMock(return_value=scalars_mock)
    result.scalars = MagicMock(return_value=scalars_mock)
    result.first = MagicMock(return_value=None)
    result.rowcount = len(scalars_list) if scalars_list else (1 if scalar_value else 0)

    return result


def make_mock_vehicle(vehicle_id=None, license_plate="TEST-001", status="AVAILABLE"):
    """Create a mock Vehicle ORM object."""
    from app.models.enums import InsulationGrade, DoorType, VehicleStatus

    vehicle = MagicMock()
    vehicle.id = vehicle_id or uuid4()
    vehicle.license_plate = license_plate
    vehicle.driver_id = None
    vehicle.driver_name = "Test Driver"
    vehicle.capacity_weight = Decimal("1000.00")
    vehicle.capacity_volume = Decimal("10.00")
    vehicle.internal_length = None
    vehicle.internal_width = None
    vehicle.internal_height = None
    vehicle.insulation_grade = InsulationGrade.STANDARD
    vehicle.k_value = Decimal("0.05")
    vehicle.door_type = DoorType.ROLL
    vehicle.door_coefficient = Decimal("0.80")
    vehicle.has_strip_curtains = False
    vehicle.cooling_rate = Decimal("-2.50")
    vehicle.min_temp_capability = Decimal("-25.00")
    vehicle.status = VehicleStatus(status)
    vehicle.current_temperature = None
    vehicle.last_telemetry_at = None
    vehicle.created_at = datetime.now()
    vehicle.updated_at = datetime.now()
    return vehicle


def make_mock_shipment(shipment_id=None, order_number="ORD-001", status="PENDING"):
    """Create a mock Shipment ORM object."""
    from app.models.enums import SLATier, ShipmentStatus

    shipment = MagicMock()
    shipment.id = shipment_id or uuid4()
    shipment.order_number = order_number
    shipment.customer_id = None
    shipment.delivery_address = "123 Test St"
    shipment.latitude = Decimal("25.0330")
    shipment.longitude = Decimal("121.5654")
    shipment.time_windows = [{"start": "08:00", "end": "12:00"}]
    shipment.sla_tier = SLATier.STANDARD
    shipment.temp_limit_upper = Decimal("5.00")
    shipment.temp_limit_lower = None
    shipment.service_duration = 15
    shipment.weight = Decimal("50.00")
    shipment.volume = Decimal("0.50")
    shipment.dimensions = None
    shipment.package_count = 1
    shipment.status = ShipmentStatus(status)
    shipment.route_id = None
    shipment.route_sequence = None
    shipment.actual_arrival_at = None
    shipment.actual_temperature = None
    shipment.was_on_time = None
    shipment.was_temp_compliant = None
    shipment.priority = 50
    shipment.special_instructions = None
    shipment.created_at = datetime.now()
    shipment.updated_at = datetime.now()
    shipment.geo_location = None
    return shipment
