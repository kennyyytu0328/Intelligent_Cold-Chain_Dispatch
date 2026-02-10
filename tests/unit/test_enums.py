"""Tests for app.models.enums -- thermodynamic constants and domain enums."""
import pytest

from app.models.enums import (
    InsulationGrade,
    DoorType,
    SLATier,
    ShipmentStatus,
    RouteStatus,
    VehicleStatus,
    OptimizationStatus,
)


class TestInsulationGrade:

    def test_premium_k_value(self):
        assert InsulationGrade.PREMIUM.k_value == 0.02

    def test_standard_k_value(self):
        assert InsulationGrade.STANDARD.k_value == 0.05

    def test_basic_k_value(self):
        assert InsulationGrade.BASIC.k_value == 0.10

    def test_k_values_ordered_premium_best(self):
        assert InsulationGrade.PREMIUM.k_value < InsulationGrade.STANDARD.k_value
        assert InsulationGrade.STANDARD.k_value < InsulationGrade.BASIC.k_value


class TestDoorType:

    def test_roll_coefficient(self):
        assert DoorType.ROLL.coefficient == 0.8

    def test_swing_coefficient(self):
        assert DoorType.SWING.coefficient == 1.2

    def test_roll_less_heat_loss(self):
        assert DoorType.ROLL.coefficient < DoorType.SWING.coefficient


class TestSLATier:

    def test_strict_is_hard_constraint(self):
        assert SLATier.STRICT.is_hard_constraint is True

    def test_standard_is_soft_constraint(self):
        assert SLATier.STANDARD.is_hard_constraint is False


class TestShipmentStatus:

    def test_all_statuses(self):
        expected = {"PENDING", "ASSIGNED", "IN_TRANSIT", "DELIVERED", "FAILED", "CANCELLED"}
        assert {s.value for s in ShipmentStatus} == expected


class TestRouteStatus:

    def test_all_statuses(self):
        expected = {"PLANNING", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "ABORTED"}
        assert {s.value for s in RouteStatus} == expected


class TestVehicleStatus:

    def test_all_statuses(self):
        expected = {"AVAILABLE", "IN_USE", "MAINTENANCE", "OFFLINE"}
        assert {s.value for s in VehicleStatus} == expected


class TestOptimizationStatus:

    def test_all_statuses(self):
        expected = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
        assert {s.value for s in OptimizationStatus} == expected
