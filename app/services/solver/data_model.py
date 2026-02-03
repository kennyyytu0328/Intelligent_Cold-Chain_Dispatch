"""
Data model for OR-Tools VRP Solver.

Converts domain models (Vehicle, Shipment) into a format suitable for OR-Tools.
This includes distance/time matrices and node information.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from math import radians, sin, cos, sqrt, atan2


@dataclass
class LocationNode:
    """Represents a location (depot or delivery point) in the VRP model."""
    index: int  # OR-Tools node index
    latitude: float
    longitude: float
    address: str

    # For shipment nodes only
    shipment_id: Optional[str] = None
    customer_id: Optional[str] = None

    # Time windows (in minutes from midnight)
    # List of (start, end) tuples for multiple windows
    time_windows: list[tuple[int, int]] = field(default_factory=list)

    # Service duration in minutes
    service_duration: int = 15

    # Demand (weight in kg, volume in m3)
    demand_weight: float = 0.0
    demand_volume: float = 0.0

    # Temperature constraint
    temp_limit_upper: float = 5.0
    temp_limit_lower: Optional[float] = None

    # SLA
    is_strict_sla: bool = False

    # Priority (higher = more important)
    priority: int = 0

    @property
    def is_depot(self) -> bool:
        """Check if this is the depot node."""
        return self.shipment_id is None


@dataclass
class VehicleData:
    """Represents a vehicle in the VRP model with thermodynamic properties."""
    index: int  # OR-Tools vehicle index
    vehicle_id: str
    license_plate: str

    # Capacity
    capacity_weight: float  # kg
    capacity_volume: float  # m3

    # Thermodynamic properties
    k_value: float  # Heat transfer coefficient
    door_coefficient: float  # Door type coefficient
    has_strip_curtains: bool  # Reduces door heat loss by 50%
    cooling_rate: float  # °C per minute (negative = cooling)

    # Starting temperature
    initial_temp: float = -5.0

    # Driver info
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None

    def calculate_transit_temp_rise(
        self,
        travel_time_minutes: float,
        ambient_temp: float,
        current_temp: float,
    ) -> float:
        """
        Calculate temperature rise during transit.

        Formula: ΔT_drive = Time_travel_hours × (T_ambient - T_current) × K_insulation
        Note: K-values (0.02-0.10) are calibrated for time in hours.
        """
        travel_time_hours = travel_time_minutes / 60.0
        return travel_time_hours * (ambient_temp - current_temp) * self.k_value

    def calculate_door_temp_rise(self, service_time_minutes: float) -> float:
        """
        Calculate temperature rise during door-open operations.

        Formula: ΔT_door = Time_service_hours × C_door_type × (1 - 0.5 × IsCurtain)
        Note: Door coefficients (0.8-1.2) are calibrated for time in hours.
        """
        service_time_hours = service_time_minutes / 60.0
        curtain_factor = 0.5 if self.has_strip_curtains else 1.0
        return service_time_hours * self.door_coefficient * curtain_factor

    def calculate_cooling_effect(self, time_minutes: float) -> float:
        """
        Calculate cooling effect from refrigeration.

        Formula: ΔT_cooling = Time_hours × Rate_cooling
        Note: Cooling rate (e.g., -2.5) is °C per hour.
        """
        time_hours = time_minutes / 60.0
        return time_hours * self.cooling_rate


@dataclass
class VRPDataModel:
    """
    Complete data model for OR-Tools VRP solver.

    Contains all information needed to set up the optimization problem:
    - Locations (depot + delivery nodes)
    - Vehicles with thermodynamic properties
    - Distance and time matrices
    - Constraints and parameters
    """
    # Nodes (index 0 is always depot)
    nodes: list[LocationNode] = field(default_factory=list)

    # Vehicles
    vehicles: list[VehicleData] = field(default_factory=list)

    # Distance matrix (in meters)
    distance_matrix: list[list[int]] = field(default_factory=list)

    # Time matrix (in minutes)
    time_matrix: list[list[int]] = field(default_factory=list)

    # Environmental parameters
    ambient_temperature: float = 30.0

    # Optimization parameters
    time_limit_seconds: int = 300
    strategy: str = "MINIMIZE_VEHICLES"

    # Earliest departure time (minutes from midnight)
    # Vehicles cannot depart before this time
    earliest_departure_minutes: int = 360  # Default 06:00

    # Penalty weights
    temp_violation_penalty: int = 100000
    late_delivery_penalty: int = 1000
    vehicle_fixed_cost: int = 50000
    distance_cost_per_km: int = 10
    infeasible_cost: int = 10000000  # Cost for dropping a shipment

    @property
    def num_locations(self) -> int:
        """Number of locations (depot + deliveries)."""
        return len(self.nodes)

    @property
    def num_vehicles(self) -> int:
        """Number of available vehicles."""
        return len(self.vehicles)

    @property
    def depot_index(self) -> int:
        """Index of depot node (always 0)."""
        return 0

    def get_shipment_nodes(self) -> list[LocationNode]:
        """Get all shipment nodes (excluding depot)."""
        return [n for n in self.nodes if not n.is_depot]

    def get_node_by_shipment_id(self, shipment_id: str) -> Optional[LocationNode]:
        """Find node by shipment ID."""
        for node in self.nodes:
            if node.shipment_id == shipment_id:
                return node
        return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points in kilometers.

    Uses the Haversine formula.
    """
    R = 6371.0  # Earth's radius in kilometers

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def compute_distance_matrix(nodes: list[LocationNode]) -> list[list[int]]:
    """
    Compute distance matrix between all nodes.

    Returns distances in METERS (OR-Tools prefers integers).
    """
    n = len(nodes)
    matrix = [[0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i != j:
                dist_km = haversine_distance(
                    nodes[i].latitude, nodes[i].longitude,
                    nodes[j].latitude, nodes[j].longitude,
                )
                # Convert to meters and round to integer
                matrix[i][j] = int(dist_km * 1000)

    return matrix


def compute_time_matrix(
    nodes: list[LocationNode],
    distance_matrix: list[list[int]],
    average_speed_kmh: int = 30,
) -> list[list[int]]:
    """
    Compute time matrix between all nodes.

    Returns travel times in MINUTES (rounded).
    """
    n = len(nodes)
    matrix = [[0] * n for _ in range(n)]

    # Convert speed to m/min
    speed_m_per_min = (average_speed_kmh * 1000) / 60

    for i in range(n):
        for j in range(n):
            if i != j:
                # Time = distance / speed
                dist_meters = distance_matrix[i][j]
                time_minutes = dist_meters / speed_m_per_min
                matrix[i][j] = int(round(time_minutes))

    return matrix


def time_str_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string to minutes from midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def build_vrp_data_model(
    vehicles: list[dict],
    shipments: list[dict],
    depot_lat: float,
    depot_lon: float,
    depot_address: str,
    ambient_temperature: float = 30.0,
    initial_vehicle_temp: float = -5.0,
    average_speed_kmh: int = 30,
    time_limit_seconds: int = 300,
    strategy: str = "MINIMIZE_VEHICLES",
    planned_departure_time: str = "06:00",
) -> VRPDataModel:
    """
    Build VRP data model from domain objects.

    Args:
        vehicles: List of vehicle dictionaries from database
        shipments: List of shipment dictionaries from database
        depot_lat: Depot latitude
        depot_lon: Depot longitude
        depot_address: Depot address string
        ambient_temperature: Outside temperature (°C)
        initial_vehicle_temp: Starting vehicle compartment temp (°C)
        average_speed_kmh: Average speed for time estimation
        time_limit_seconds: Solver time limit
        strategy: Optimization strategy
        planned_departure_time: Earliest departure time in HH:MM format (e.g., "08:00")

    Returns:
        VRPDataModel ready for OR-Tools solver
    """
    # Convert planned departure time to minutes from midnight
    earliest_departure = time_str_to_minutes(planned_departure_time)

    model = VRPDataModel(
        ambient_temperature=ambient_temperature,
        time_limit_seconds=time_limit_seconds,
        strategy=strategy,
        earliest_departure_minutes=earliest_departure,
    )

    # Create depot node (index 0)
    depot = LocationNode(
        index=0,
        latitude=depot_lat,
        longitude=depot_lon,
        address=depot_address,
        time_windows=[(0, 24 * 60)],  # Depot open all day
        service_duration=0,
    )
    model.nodes.append(depot)

    # Create shipment nodes
    for idx, shipment in enumerate(shipments, start=1):
        # Parse time windows
        time_windows = []
        for tw in shipment.get("time_windows", []):
            start = time_str_to_minutes(tw["start"])
            end = time_str_to_minutes(tw["end"])
            time_windows.append((start, end))

        node = LocationNode(
            index=idx,
            latitude=float(shipment["latitude"]),
            longitude=float(shipment["longitude"]),
            address=shipment["delivery_address"],
            shipment_id=str(shipment["id"]),
            customer_id=str(shipment.get("customer_id", "")),
            time_windows=time_windows if time_windows else [(0, 24 * 60)],
            service_duration=shipment.get("service_duration", 15),
            demand_weight=float(shipment.get("weight", 0)),
            demand_volume=float(shipment.get("volume", 0) or 0),
            temp_limit_upper=float(shipment.get("temp_limit_upper", 5.0)),
            temp_limit_lower=float(shipment["temp_limit_lower"]) if shipment.get("temp_limit_lower") else None,
            is_strict_sla=shipment.get("sla_tier") == "STRICT",
            priority=shipment.get("priority", 0),
        )
        model.nodes.append(node)

    # Create vehicle data
    for idx, vehicle in enumerate(vehicles):
        vd = VehicleData(
            index=idx,
            vehicle_id=str(vehicle["id"]),
            license_plate=vehicle["license_plate"],
            capacity_weight=float(vehicle["capacity_weight"]),
            capacity_volume=float(vehicle["capacity_volume"]),
            k_value=float(vehicle.get("k_value", 0.05)),
            door_coefficient=float(vehicle.get("door_coefficient", 0.8)),
            has_strip_curtains=vehicle.get("has_strip_curtains", False),
            cooling_rate=float(vehicle.get("cooling_rate", -2.5)),
            initial_temp=initial_vehicle_temp,
            driver_id=str(vehicle["driver_id"]) if vehicle.get("driver_id") else None,
            driver_name=vehicle.get("driver_name"),
        )
        model.vehicles.append(vd)

    # Compute matrices
    model.distance_matrix = compute_distance_matrix(model.nodes)
    model.time_matrix = compute_time_matrix(
        model.nodes,
        model.distance_matrix,
        average_speed_kmh,
    )

    return model
