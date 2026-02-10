"""Tests for Pydantic schema validation."""
import pytest
from decimal import Decimal
from pydantic import ValidationError

from app.schemas.shipment import TimeWindowSchema, ShipmentCreate, DimensionsSchema


class TestTimeWindowSchema:

    def test_valid_time_window(self):
        tw = TimeWindowSchema(start="08:00", end="12:00")
        assert tw.start == "08:00"
        assert tw.end == "12:00"

    def test_invalid_format_rejected(self):
        with pytest.raises(ValidationError):
            TimeWindowSchema(start="8:00", end="12:00")

    def test_start_after_end_rejected(self):
        with pytest.raises(ValidationError):
            TimeWindowSchema(start="14:00", end="08:00")

    def test_same_start_and_end_rejected(self):
        with pytest.raises(ValidationError):
            TimeWindowSchema(start="10:00", end="10:00")

    def test_invalid_hour_rejected(self):
        with pytest.raises(ValidationError):
            TimeWindowSchema(start="25:00", end="26:00")


class TestDimensionsSchema:

    def test_volume_cm3(self):
        dims = DimensionsSchema(l=100, w=80, h=60)
        assert dims.volume_cm3 == 480000

    def test_volume_m3(self):
        dims = DimensionsSchema(l=100, w=80, h=60)
        assert abs(dims.volume_m3 - 0.48) < 0.001


class TestShipmentCreate:

    def test_valid_shipment(self):
        shipment = ShipmentCreate(
            order_number="ORD-001",
            delivery_address="123 Test St",
            latitude=Decimal("25.033"),
            longitude=Decimal("121.565"),
            weight=Decimal("50.0"),
            time_windows=[TimeWindowSchema(start="08:00", end="12:00")],
        )
        assert shipment.order_number == "ORD-001"

    def test_empty_time_windows_rejected(self):
        with pytest.raises(ValidationError):
            ShipmentCreate(
                order_number="ORD-001",
                delivery_address="123 Test St",
                latitude=Decimal("25.033"),
                longitude=Decimal("121.565"),
                weight=Decimal("50.0"),
                time_windows=[],
            )

    def test_temp_lower_gte_upper_rejected(self):
        with pytest.raises(ValidationError):
            ShipmentCreate(
                order_number="ORD-001",
                delivery_address="123 Test St",
                latitude=Decimal("25.033"),
                longitude=Decimal("121.565"),
                weight=Decimal("50.0"),
                time_windows=[TimeWindowSchema(start="08:00", end="12:00")],
                temp_limit_upper=Decimal("5.0"),
                temp_limit_lower=Decimal("5.0"),
            )

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError):
            ShipmentCreate(
                order_number="ORD-001",
                delivery_address="123 Test St",
                latitude=Decimal("25.033"),
                longitude=Decimal("121.565"),
                weight=Decimal("-1.0"),
                time_windows=[TimeWindowSchema(start="08:00", end="12:00")],
            )

    def test_latitude_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            ShipmentCreate(
                order_number="ORD-001",
                delivery_address="123 Test St",
                latitude=Decimal("91.0"),
                longitude=Decimal("121.565"),
                weight=Decimal("50.0"),
                time_windows=[TimeWindowSchema(start="08:00", end="12:00")],
            )
