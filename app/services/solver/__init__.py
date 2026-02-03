"""
Cold-Chain VRP Solver package.

Provides OR-Tools based vehicle routing optimization with thermodynamic constraints.
"""

from app.services.solver.data_model import (
    VRPDataModel,
    LocationNode,
    VehicleData,
    build_vrp_data_model,
    compute_distance_matrix,
    compute_time_matrix,
)
from app.services.solver.callbacks import (
    TemperatureTracker,
    create_distance_callback,
    create_time_callback,
    create_weight_demand_callback,
    create_volume_demand_callback,
)
from app.services.solver.solver import (
    ColdChainVRPSolver,
    SolverResult,
    RouteResult,
    RouteStopResult,
)

__all__ = [
    # Data model
    "VRPDataModel",
    "LocationNode",
    "VehicleData",
    "build_vrp_data_model",
    "compute_distance_matrix",
    "compute_time_matrix",
    # Callbacks
    "TemperatureTracker",
    "create_distance_callback",
    "create_time_callback",
    "create_weight_demand_callback",
    "create_volume_demand_callback",
    # Solver
    "ColdChainVRPSolver",
    "SolverResult",
    "RouteResult",
    "RouteStopResult",
]
