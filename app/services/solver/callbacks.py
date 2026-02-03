"""
OR-Tools callback functions for VRP solver.

Includes:
- Distance callback
- Time callback
- Demand callbacks (weight, volume)
- Temperature tracking callback (thermodynamic model)
"""
from typing import Callable

from app.services.solver.data_model import VRPDataModel, VehicleData


def create_distance_callback(
    data: VRPDataModel,
    manager,  # RoutingIndexManager
) -> Callable[[int, int], int]:
    """
    Create distance callback for OR-Tools.

    Returns distance in meters between two nodes.
    """
    def distance_callback(from_index: int, to_index: int) -> int:
        """Returns the distance between two nodes."""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data.distance_matrix[from_node][to_node]

    return distance_callback


def create_time_callback(
    data: VRPDataModel,
    manager,  # RoutingIndexManager
) -> Callable[[int, int], int]:
    """
    Create time callback for OR-Tools.

    Returns travel time in minutes between two nodes.
    This is used for the time dimension (scheduling).
    """
    def time_callback(from_index: int, to_index: int) -> int:
        """Returns travel time + service time at from_node."""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        # Travel time
        travel_time = data.time_matrix[from_node][to_node]

        # Add service time at from_node (except depot)
        if from_node != data.depot_index:
            travel_time += data.nodes[from_node].service_duration

        return travel_time

    return time_callback


def create_weight_demand_callback(
    data: VRPDataModel,
    manager,  # RoutingIndexManager
) -> Callable[[int], int]:
    """
    Create weight demand callback for OR-Tools.

    Returns weight demand in grams (converted from kg for integer precision).
    """
    def demand_callback(from_index: int) -> int:
        """Returns weight demand at the node."""
        from_node = manager.IndexToNode(from_index)
        if from_node == data.depot_index:
            return 0
        # Convert kg to grams for integer precision
        return int(data.nodes[from_node].demand_weight * 1000)

    return demand_callback


def create_volume_demand_callback(
    data: VRPDataModel,
    manager,  # RoutingIndexManager
) -> Callable[[int], int]:
    """
    Create volume demand callback for OR-Tools.

    Returns volume demand in liters (converted from m3 for integer precision).
    """
    def demand_callback(from_index: int) -> int:
        """Returns volume demand at the node."""
        from_node = manager.IndexToNode(from_index)
        if from_node == data.depot_index:
            return 0
        # Convert m3 to liters for integer precision
        return int(data.nodes[from_node].demand_volume * 1000)

    return demand_callback


class TemperatureTracker:
    """
    Tracks temperature changes along routes using thermodynamic formulas.

    This class is used to:
    1. Calculate temperature at each stop
    2. Determine if a route is feasible (temperature within limits)
    3. Calculate penalties for temperature violations

    Formulas:
    - ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation
    - ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)
    - ΔT_cooling = Time_drive × Rate_cooling
    """

    def __init__(
        self,
        data: VRPDataModel,
        manager,  # RoutingIndexManager
        temp_violation_penalty: int = 100000,
        infeasible_cost: int = 10000000,
    ):
        self.data = data
        self.manager = manager
        self.temp_violation_penalty = temp_violation_penalty
        self.infeasible_cost = infeasible_cost

        # Cache for computed temperatures per vehicle
        # Key: (vehicle_index, node_sequence_tuple) -> temperature at each node
        self._temp_cache: dict[tuple, list[float]] = {}

    def calculate_route_temperatures(
        self,
        vehicle_index: int,
        route_nodes: list[int],
    ) -> list[dict]:
        """
        Calculate temperature at each stop for a vehicle route.

        Args:
            vehicle_index: Index of the vehicle
            route_nodes: List of node indices in visit order (excluding depot)

        Returns:
            List of dicts with temperature info at each stop:
            {
                'node_index': int,
                'arrival_temp': float,
                'departure_temp': float,
                'transit_rise': float,
                'door_rise': float,
                'cooling_effect': float,
                'is_feasible': bool,
                'violation_amount': float,
            }
        """
        vehicle = self.data.vehicles[vehicle_index]
        ambient = self.data.ambient_temperature
        results = []

        # Start with initial vehicle temperature
        current_temp = vehicle.initial_temp
        prev_node = self.data.depot_index

        for node_idx in route_nodes:
            if node_idx == self.data.depot_index:
                continue

            node = self.data.nodes[node_idx]

            # Get travel time from previous node
            travel_time = self.data.time_matrix[prev_node][node_idx]

            # Calculate temperature changes
            # 1. Transit temperature rise
            transit_rise = vehicle.calculate_transit_temp_rise(
                travel_time, ambient, current_temp
            )

            # 2. Cooling during transit (refrigeration active)
            cooling_effect = vehicle.calculate_cooling_effect(travel_time)

            # Temperature upon arrival
            arrival_temp = current_temp + transit_rise + cooling_effect

            # 3. Door temperature rise during service
            door_rise = vehicle.calculate_door_temp_rise(node.service_duration)

            # Temperature after service (departure temp)
            departure_temp = arrival_temp + door_rise

            # Check feasibility
            is_feasible = arrival_temp <= node.temp_limit_upper
            violation_amount = max(0, arrival_temp - node.temp_limit_upper)

            # Also check lower limit if specified
            if node.temp_limit_lower is not None:
                if arrival_temp < node.temp_limit_lower:
                    is_feasible = False
                    violation_amount = max(
                        violation_amount,
                        node.temp_limit_lower - arrival_temp
                    )

            results.append({
                'node_index': node_idx,
                'arrival_temp': arrival_temp,
                'departure_temp': departure_temp,
                'transit_rise': transit_rise,
                'door_rise': door_rise,
                'cooling_effect': cooling_effect,
                'is_feasible': is_feasible,
                'violation_amount': violation_amount,
            })

            # Update for next iteration
            current_temp = departure_temp
            prev_node = node_idx

        return results

    def get_temperature_penalty(
        self,
        vehicle_index: int,
        route_nodes: list[int],
    ) -> int:
        """
        Calculate total temperature penalty for a route.

        For STRICT SLA shipments, any violation returns infeasible cost.
        For STANDARD SLA, penalty is proportional to violation amount.

        Returns:
            Total penalty (0 if no violations)
        """
        temps = self.calculate_route_temperatures(vehicle_index, route_nodes)
        total_penalty = 0

        for temp_info in temps:
            node_idx = temp_info['node_index']
            node = self.data.nodes[node_idx]

            if not temp_info['is_feasible']:
                if node.is_strict_sla:
                    # Strict SLA: route is infeasible
                    return self.infeasible_cost
                else:
                    # Standard SLA: add penalty
                    violation = temp_info['violation_amount']
                    total_penalty += int(violation * self.temp_violation_penalty)

        return total_penalty

    def is_route_feasible(
        self,
        vehicle_index: int,
        route_nodes: list[int],
    ) -> bool:
        """
        Check if a route is feasible regarding temperature constraints.

        A route is infeasible if any STRICT SLA shipment has temperature violation.
        """
        temps = self.calculate_route_temperatures(vehicle_index, route_nodes)

        for temp_info in temps:
            node_idx = temp_info['node_index']
            node = self.data.nodes[node_idx]

            if not temp_info['is_feasible'] and node.is_strict_sla:
                return False

        return True


def create_temperature_transit_callback(
    data: VRPDataModel,
    manager,  # RoutingIndexManager
    routing,  # RoutingModel
    temp_tracker: TemperatureTracker,
) -> Callable[[int, int], int]:
    """
    Create temperature-aware transit callback.

    This callback adds temperature penalty to the arc cost.
    It's used to discourage routes that cause temperature violations.

    Note: This is a simplified version. Full temperature tracking
    requires post-processing the solution since OR-Tools callbacks
    don't have full route context during search.
    """
    def temp_transit_callback(from_index: int, to_index: int) -> int:
        """
        Returns additional cost for temperature impact.

        This is an approximation - actual temperature depends on full route.
        We estimate based on single arc.
        """
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        if to_node == data.depot_index:
            return 0

        # Get travel time
        travel_time = data.time_matrix[from_node][to_node]

        # Estimate temperature rise for this arc
        # Use average vehicle parameters for estimation
        avg_k = sum(v.k_value for v in data.vehicles) / len(data.vehicles)

        # Estimate temp rise (simplified)
        estimated_rise = travel_time * data.ambient_temperature * avg_k * 0.1

        # Get node temperature limit
        node = data.nodes[to_node]

        # If estimated rise is significant, add small penalty
        # This helps guide the solver toward shorter routes
        if estimated_rise > 1.0:
            return int(estimated_rise * 100)

        return 0

    return temp_transit_callback
