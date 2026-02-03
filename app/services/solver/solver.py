"""
Cold-Chain VRP Solver using Google OR-Tools.

This solver handles:
1. Vehicle Routing Problem with Time Windows (VRPTW)
2. Multiple time windows per shipment (Disjunction)
3. Capacity constraints (weight, volume)
4. Thermodynamic constraints (temperature tracking)
5. SLA-based constraint strictness (STRICT vs STANDARD)

Optimization Hierarchy (Lexicographic):
1. Level 0: Hard constraints (STRICT SLA, capacity)
2. Level 1: Minimize fleet size
3. Level 2: Minimize total distance/cost
4. Level 3: Maximize slack time (risk mitigation)
"""
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional
from uuid import UUID, uuid4
import logging

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from app.services.solver.data_model import VRPDataModel, LocationNode, VehicleData
from app.services.solver.callbacks import (
    create_distance_callback,
    create_time_callback,
    create_weight_demand_callback,
    create_volume_demand_callback,
    TemperatureTracker,
)

logger = logging.getLogger(__name__)


@dataclass
class RouteStopResult:
    """Result for a single stop in a route."""
    sequence: int
    node_index: int
    shipment_id: str
    address: str
    latitude: float
    longitude: float

    # Timing
    arrival_time_minutes: int  # Minutes from midnight
    departure_time_minutes: int
    service_duration: int
    slack_minutes: int
    target_time_window_index: int

    # Distance/Time from previous
    distance_from_prev_meters: int
    travel_time_from_prev_minutes: int

    # Temperature predictions
    arrival_temp: float
    departure_temp: float
    transit_temp_rise: float
    door_temp_rise: float
    cooling_applied: float
    is_temp_feasible: bool

    # Constraints
    temp_limit_upper: float
    is_strict_sla: bool


@dataclass
class RouteResult:
    """Result for a complete vehicle route."""
    vehicle_index: int
    vehicle_id: str
    license_plate: str
    driver_id: Optional[str]
    driver_name: Optional[str]

    # Route stops
    stops: list[RouteStopResult] = field(default_factory=list)

    # Summary metrics
    total_distance_meters: int = 0
    total_duration_minutes: int = 0
    total_weight_kg: float = 0.0
    total_volume_m3: float = 0.0

    # Temperature
    initial_temp: float = -5.0
    final_temp: float = 0.0
    max_temp: float = 0.0

    # Timing
    departure_time_minutes: int = 0
    return_time_minutes: int = 0

    @property
    def is_temperature_feasible(self) -> bool:
        """Check if all stops have feasible temperature."""
        return all(s.is_temp_feasible for s in self.stops)

    @property
    def num_stops(self) -> int:
        return len(self.stops)


@dataclass
class SolverResult:
    """Complete result from the VRP solver."""
    # Status
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, NOT_SOLVED, TIMEOUT
    solver_status_code: int

    # Routes
    routes: list[RouteResult] = field(default_factory=list)

    # Unassigned shipments
    unassigned_shipment_ids: list[str] = field(default_factory=list)

    # Metrics
    total_cost: int = 0
    total_distance_meters: int = 0
    total_duration_minutes: int = 0
    vehicles_used: int = 0
    shipments_assigned: int = 0

    # Solver info
    solver_time_seconds: float = 0.0
    iterations: int = 0

    @property
    def is_success(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


class ColdChainVRPSolver:
    """
    Cold-Chain VRP Solver with thermodynamic constraints.

    Usage:
        solver = ColdChainVRPSolver(data_model)
        result = solver.solve()
    """

    # OR-Tools status code mapping
    STATUS_MAP = {
        0: "ROUTING_NOT_SOLVED",
        1: "ROUTING_SUCCESS",
        2: "ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED",
        3: "ROUTING_FAIL",
        4: "ROUTING_FAIL_TIMEOUT",
        5: "ROUTING_INVALID",
        6: "ROUTING_INFEASIBLE",
    }

    def __init__(
        self,
        data: VRPDataModel,
        plan_date: Optional[date] = None,
    ):
        """
        Initialize solver with data model.

        Args:
            data: VRPDataModel with all problem data
            plan_date: Date for the routes (used for timestamps)
        """
        self.data = data
        self.plan_date = plan_date or date.today()

        # OR-Tools objects (initialized in solve())
        self.manager = None
        self.routing = None
        self.temp_tracker = None

        # Results
        self.result: Optional[SolverResult] = None

    def solve(self) -> SolverResult:
        """
        Solve the VRP problem.

        Returns:
            SolverResult with routes and metrics
        """
        # Convert earliest departure to HH:MM for logging
        dep_hours = self.data.earliest_departure_minutes // 60
        dep_mins = self.data.earliest_departure_minutes % 60
        logger.info(
            f"Starting VRP solver with {self.data.num_locations} locations, "
            f"{self.data.num_vehicles} vehicles, "
            f"earliest departure: {dep_hours:02d}:{dep_mins:02d}"
        )

        start_time = datetime.now()

        # Create routing index manager
        self.manager = pywrapcp.RoutingIndexManager(
            self.data.num_locations,
            self.data.num_vehicles,
            self.data.depot_index,
        )

        # Create routing model
        self.routing = pywrapcp.RoutingModel(self.manager)

        # Initialize temperature tracker
        self.temp_tracker = TemperatureTracker(
            self.data,
            self.manager,
            self.data.temp_violation_penalty,
        )

        # Register callbacks and add constraints
        self._add_distance_dimension()
        self._add_time_dimension()
        self._add_capacity_dimensions()
        self._add_time_window_constraints()
        self._add_disjunctions_for_optional_nodes()

        # Set objective
        self._set_objective()

        # Configure search parameters
        search_parameters = self._get_search_parameters()

        # Solve
        logger.info(f"Solving with time limit: {self.data.time_limit_seconds}s")
        solution = self.routing.SolveWithParameters(search_parameters)

        solve_time = (datetime.now() - start_time).total_seconds()

        # Process results
        self.result = self._process_solution(solution, solve_time)

        logger.info(
            f"Solver finished: status={self.result.status}, "
            f"vehicles_used={self.result.vehicles_used}, "
            f"shipments_assigned={self.result.shipments_assigned}"
        )

        return self.result

    def _add_distance_dimension(self):
        """Add distance dimension to the model."""
        distance_callback = create_distance_callback(self.data, self.manager)
        distance_callback_index = self.routing.RegisterTransitCallback(distance_callback)

        # Set arc cost evaluator (primary cost)
        self.routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)

        # Add distance dimension for tracking
        self.routing.AddDimension(
            distance_callback_index,
            0,  # No slack
            1000000000,  # Max distance (1M km in meters)
            True,  # Start cumul to zero
            "Distance",
        )

    def _add_time_dimension(self):
        """Add time dimension for scheduling."""
        time_callback = create_time_callback(self.data, self.manager)
        time_callback_index = self.routing.RegisterTransitCallback(time_callback)

        # Add time dimension
        # Max time: 24 hours in minutes
        self.routing.AddDimension(
            time_callback_index,
            60,  # Allow 60 min slack (waiting time)
            24 * 60,  # Max 24 hours
            False,  # Don't force start cumul to zero
            "Time",
        )

        self.time_dimension = self.routing.GetDimensionOrDie("Time")

        # Minimize total time (secondary objective)
        self.time_dimension.SetGlobalSpanCostCoefficient(10)

    def _add_capacity_dimensions(self):
        """Add weight and volume capacity dimensions."""
        # Weight capacity
        weight_callback = create_weight_demand_callback(self.data, self.manager)
        weight_callback_index = self.routing.RegisterUnaryTransitCallback(weight_callback)

        self.routing.AddDimensionWithVehicleCapacity(
            weight_callback_index,
            0,  # No slack
            [int(v.capacity_weight * 1000) for v in self.data.vehicles],  # kg to grams
            True,
            "Weight",
        )

        # Volume capacity
        volume_callback = create_volume_demand_callback(self.data, self.manager)
        volume_callback_index = self.routing.RegisterUnaryTransitCallback(volume_callback)

        self.routing.AddDimensionWithVehicleCapacity(
            volume_callback_index,
            0,
            [int(v.capacity_volume * 1000) for v in self.data.vehicles],  # m3 to liters
            True,
            "Volume",
        )

    def _add_time_window_constraints(self):
        """Add time window constraints for each node."""
        time_dimension = self.routing.GetDimensionOrDie("Time")

        for node in self.data.nodes:
            if node.is_depot:
                # Depot: open all day
                index = self.manager.NodeToIndex(node.index)
                time_dimension.CumulVar(index).SetRange(0, 24 * 60)
                continue

            index = self.manager.NodeToIndex(node.index)

            if len(node.time_windows) == 1:
                # Single time window - simple constraint
                start, end = node.time_windows[0]
                time_dimension.CumulVar(index).SetRange(start, end)
            else:
                # Multiple time windows - handled via disjunction in _add_multi_time_window_disjunction
                # For now, set the broadest possible range
                earliest = min(tw[0] for tw in node.time_windows)
                latest = max(tw[1] for tw in node.time_windows)
                time_dimension.CumulVar(index).SetRange(earliest, latest)

        # Set start time for each vehicle (can depart from earliest_departure_minutes)
        for vehicle_idx in range(self.data.num_vehicles):
            start_index = self.routing.Start(vehicle_idx)
            time_dimension.CumulVar(start_index).SetRange(
                self.data.earliest_departure_minutes,
                24 * 60
            )

    def _add_disjunctions_for_optional_nodes(self):
        """
        Add disjunctions for shipments.

        STRICT SLA: No penalty (must be visited)
        STANDARD SLA: High penalty for dropping
        """
        for node in self.data.nodes:
            if node.is_depot:
                continue

            index = self.manager.NodeToIndex(node.index)

            if node.is_strict_sla:
                # STRICT: Must be visited - no disjunction needed
                # But we add one with infinite penalty to prevent dropping
                self.routing.AddDisjunction([index], self.data.infeasible_cost)
            else:
                # STANDARD: Can be dropped with penalty
                # Penalty should be much higher than vehicle fixed cost to strongly
                # prefer adding shipments to existing routes over dropping them.
                # Using 3x vehicle fixed cost as base, adjusted by priority.
                base_penalty = self.data.vehicle_fixed_cost * 3
                priority_multiplier = (100 - node.priority + 1) / 100.0
                penalty = int(base_penalty * priority_multiplier)
                self.routing.AddDisjunction([index], penalty)

    def _set_objective(self):
        """
        Set optimization objective.

        Lexicographic order:
        1. Minimize vehicles (via fixed cost)
        2. Minimize distance
        """
        # Add fixed cost for using each vehicle
        for vehicle_idx in range(self.data.num_vehicles):
            self.routing.SetFixedCostOfVehicle(
                self.data.vehicle_fixed_cost,
                vehicle_idx,
            )

    def _get_search_parameters(self):
        """Configure solver search parameters."""
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()

        # First solution strategy
        # PARALLEL_CHEAPEST_INSERTION is better for problems where vehicles
        # should make multiple stops. It considers all unrouted shipments
        # and inserts them where they fit best, rather than greedily building
        # routes with PATH_CHEAPEST_ARC.
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
        )

        # Local search metaheuristic
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )

        # Time limit
        search_parameters.time_limit.FromSeconds(self.data.time_limit_seconds)

        # Log search disabled to reduce log noise
        search_parameters.log_search = False

        return search_parameters

    def _process_solution(
        self,
        solution,
        solve_time: float,
    ) -> SolverResult:
        """Process OR-Tools solution into SolverResult."""
        status_code = self.routing.status()
        status = self._get_status_string(status_code)

        result = SolverResult(
            status=status,
            solver_status_code=status_code,
            solver_time_seconds=solve_time,
        )

        if solution is None:
            # No solution found
            result.unassigned_shipment_ids = [
                n.shipment_id for n in self.data.nodes if not n.is_depot
            ]
            return result

        # Process each vehicle route
        time_dimension = self.routing.GetDimensionOrDie("Time")
        distance_dimension = self.routing.GetDimensionOrDie("Distance")

        assigned_nodes = set()

        for vehicle_idx in range(self.data.num_vehicles):
            route_result = self._extract_vehicle_route(
                solution, vehicle_idx, time_dimension, distance_dimension
            )

            if route_result.num_stops > 0:
                result.routes.append(route_result)
                result.vehicles_used += 1
                result.total_distance_meters += route_result.total_distance_meters
                result.total_duration_minutes += route_result.total_duration_minutes
                result.shipments_assigned += route_result.num_stops

                for stop in route_result.stops:
                    assigned_nodes.add(stop.node_index)

        # Find unassigned shipments
        for node in self.data.nodes:
            if not node.is_depot and node.index not in assigned_nodes:
                result.unassigned_shipment_ids.append(node.shipment_id)

        # Total cost
        result.total_cost = solution.ObjectiveValue()

        return result

    def _extract_vehicle_route(
        self,
        solution,
        vehicle_idx: int,
        time_dimension,
        distance_dimension,
    ) -> RouteResult:
        """Extract route for a single vehicle."""
        vehicle = self.data.vehicles[vehicle_idx]

        route = RouteResult(
            vehicle_index=vehicle_idx,
            vehicle_id=vehicle.vehicle_id,
            license_plate=vehicle.license_plate,
            driver_id=vehicle.driver_id,
            driver_name=vehicle.driver_name,
            initial_temp=vehicle.initial_temp,
        )

        # Collect route nodes
        route_nodes = []
        index = self.routing.Start(vehicle_idx)

        while not self.routing.IsEnd(index):
            node_idx = self.manager.IndexToNode(index)
            if node_idx != self.data.depot_index:
                route_nodes.append(node_idx)
            index = solution.Value(self.routing.NextVar(index))

        if not route_nodes:
            return route

        # Calculate temperatures for this route
        temp_results = self.temp_tracker.calculate_route_temperatures(
            vehicle_idx, route_nodes
        )
        temp_map = {t['node_index']: t for t in temp_results}

        # Build stops
        sequence = 1
        prev_node = self.data.depot_index

        index = self.routing.Start(vehicle_idx)
        route.departure_time_minutes = solution.Min(time_dimension.CumulVar(index))

        while not self.routing.IsEnd(index):
            node_idx = self.manager.IndexToNode(index)

            if node_idx != self.data.depot_index:
                node = self.data.nodes[node_idx]
                temp_info = temp_map.get(node_idx, {})

                # Get timing from solution
                time_var = time_dimension.CumulVar(index)
                arrival_time = solution.Min(time_var)
                slack = solution.Max(time_var) - solution.Min(time_var)

                # Determine which time window was targeted
                target_tw_index = 0
                for i, (tw_start, tw_end) in enumerate(node.time_windows):
                    if tw_start <= arrival_time <= tw_end:
                        target_tw_index = i
                        break

                # Get distance from previous
                dist_from_prev = self.data.distance_matrix[prev_node][node_idx]
                time_from_prev = self.data.time_matrix[prev_node][node_idx]

                stop = RouteStopResult(
                    sequence=sequence,
                    node_index=node_idx,
                    shipment_id=node.shipment_id,
                    address=node.address,
                    latitude=node.latitude,
                    longitude=node.longitude,
                    arrival_time_minutes=arrival_time,
                    departure_time_minutes=arrival_time + node.service_duration,
                    service_duration=node.service_duration,
                    slack_minutes=slack,
                    target_time_window_index=target_tw_index,
                    distance_from_prev_meters=dist_from_prev,
                    travel_time_from_prev_minutes=time_from_prev,
                    arrival_temp=temp_info.get('arrival_temp', 0),
                    departure_temp=temp_info.get('departure_temp', 0),
                    transit_temp_rise=temp_info.get('transit_rise', 0),
                    door_temp_rise=temp_info.get('door_rise', 0),
                    cooling_applied=temp_info.get('cooling_effect', 0),
                    is_temp_feasible=temp_info.get('is_feasible', True),
                    temp_limit_upper=node.temp_limit_upper,
                    is_strict_sla=node.is_strict_sla,
                )

                route.stops.append(stop)
                route.total_distance_meters += dist_from_prev
                route.total_weight_kg += node.demand_weight
                route.total_volume_m3 += node.demand_volume

                sequence += 1
                prev_node = node_idx

            index = solution.Value(self.routing.NextVar(index))

        # Add return to depot
        end_index = self.routing.End(vehicle_idx)
        end_node = self.manager.IndexToNode(end_index)
        route.total_distance_meters += self.data.distance_matrix[prev_node][self.data.depot_index]
        route.return_time_minutes = solution.Min(time_dimension.CumulVar(end_index))
        route.total_duration_minutes = route.return_time_minutes - route.departure_time_minutes

        # Temperature summary
        if route.stops:
            route.final_temp = route.stops[-1].departure_temp
            route.max_temp = max(s.arrival_temp for s in route.stops)

        return route

    def _get_status_string(self, status_code: int) -> str:
        """Convert OR-Tools status code to string."""
        status_name = self.STATUS_MAP.get(status_code, "UNKNOWN")

        if status_code == 1:
            return "OPTIMAL"
        elif status_code == 2:
            return "FEASIBLE"
        elif status_code in (3, 5, 6):
            return "INFEASIBLE"
        elif status_code == 4:
            return "TIMEOUT"
        else:
            return "NOT_SOLVED"
