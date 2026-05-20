"""Data models for the AFSIM MCP server."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SimulationStatus(str, Enum):
    """Status of a simulation run."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class EntityType(str, Enum):
    """Types of AFSIM entities."""

    PLATFORM = "platform"
    ROUTE = "route"
    COMM_LINK = "comm_link"
    SENSOR = "sensor"
    WEAPON = "weapon"
    MOVER = "mover"


class MoverType(str, Enum):
    """AFSIM mover types."""

    FIXED = "wsf_fixed_mover"
    ROUTE = "wsf_route_mover"
    AIR = "wsf_air_mover"
    GROUND = "wsf_ground_mover"
    SURFACE = "wsf_surface_mover"
    SUBSURFACE = "wsf_subsurface_mover"
    ORBIT = "wsf_orbit_mover"


class SensorType(str, Enum):
    """AFSIM sensor types."""

    RADAR = "wsf_radar_sensor"
    EO = "wsf_eo_sensor"
    IR = "wsf_ir_sensor"
    COMM = "wsf_comm_sensor"
    GENERIC = "wsf_sensor"


class WeaponType(str, Enum):
    """AFSIM weapon types."""

    MISSILE = "wsf_missile"
    BOMB = "wsf_bomb"
    BULLET = "wsf_bullet"
    GENERIC = "wsf_weapon"


class ResultFormat(str, Enum):
    """Result file formats."""

    AER = "aer"
    EVT = "evt"
    CSV = "csv"
    JSON = "json"


@dataclass
class Position:
    """Geographic position."""

    latitude: float = 0.0
    longitude: float = 0.0
    altitude_m: float = 0.0

    def to_afsim(self) -> str:
        """Return AFSIM-formatted position string."""
        return f"{self.latitude}deg {self.longitude}deg {self.altitude_m}m"


@dataclass
class Component:
    """A component attached to a platform (mover, sensor, weapon)."""

    name: str
    component_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_afsim_block(self) -> str:
        """Render component as an AFSIM block."""
        # Support both plain strings and str-enum values
        comp_type = (
            self.component_type.value
            if hasattr(self.component_type, "value")
            else str(self.component_type)
        )
        lines = [f"  {comp_type} {self.name}"]
        for k, v in self.parameters.items():
            lines.append(f"    {k} {v}")
        lines.append("  end_" + comp_type.split("_", 1)[-1])
        return "\n".join(lines)


@dataclass
class Platform:
    """An AFSIM platform (entity)."""

    name: str
    platform_type: str = "wsf_platform"
    position: Position = field(default_factory=Position)
    components: list[Component] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_afsim_block(self) -> str:
        """Render platform as an AFSIM scenario block."""
        lines = [
            f"platform {self.name}",
            f"  platform_type {self.platform_type}",
            f"  position {self.position.to_afsim()}",
        ]
        for k, v in self.parameters.items():
            lines.append(f"  {k} {v}")
        for comp in self.components:
            lines.append(comp.to_afsim_block())
        lines.append("end_platform")
        return "\n".join(lines)


@dataclass
class Scenario:
    """An AFSIM scenario."""

    name: str
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    duration_s: float = 3600.0
    time_step_s: float = 1.0
    platforms: list[Platform] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    file_path: str | None = None

    def to_afsim(self) -> str:
        """Render the scenario as AFSIM scenario text."""
        lines = [
            f"# Scenario: {self.name}",
            f"# {self.description}",
            "",
            f"simulation_duration {self.duration_s}s",
            f"time_step {self.time_step_s}s",
            "",
        ]
        for k, v in self.parameters.items():
            lines.append(f"{k} {v}")
        if self.parameters:
            lines.append("")
        for platform in self.platforms:
            lines.append(platform.to_afsim_block())
            lines.append("")
        return "\n".join(lines)


@dataclass
class SimulationRun:
    """Tracks a simulation run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str = ""
    scenario_file: str = ""
    status: SimulationStatus = SimulationStatus.IDLE
    start_time: str | None = None
    end_time: str | None = None
    pid: int | None = None
    output_dir: str = ""
    log_file: str = ""
    error_message: str = ""
    result_files: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """A simulation result file."""

    file_path: str
    format: ResultFormat
    run_id: str = ""
    size_bytes: int = 0
    created_at: str = ""
