"""Entity and component management for AFSIM MCP server."""

from __future__ import annotations

import logging
from typing import Any

from .models import (
    Component,
    MoverType,
    Platform,
    Position,
    SensorType,
    WeaponType,
)
from .scenario_manager import ScenarioManager

logger = logging.getLogger(__name__)


class EntityManager:
    """Manages AFSIM platforms and their components."""

    def __init__(self, scenario_manager: ScenarioManager) -> None:
        self._sm = scenario_manager

    # ------------------------------------------------------------------
    # Platforms
    # ------------------------------------------------------------------

    def create_platform(
        self,
        scenario_id: str,
        name: str,
        platform_type: str = "wsf_platform",
        latitude: float = 0.0,
        longitude: float = 0.0,
        altitude_m: float = 0.0,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Add a new platform to the scenario."""
        scenario = self._sm.get_scenario(scenario_id)
        self._check_unique_platform(scenario, name)
        platform = Platform(
            name=name,
            platform_type=platform_type,
            position=Position(latitude=latitude, longitude=longitude, altitude_m=altitude_m),
            parameters=parameters or {},
        )
        scenario.platforms.append(platform)
        logger.info("Created platform '%s' in scenario '%s'", name, scenario.name)
        return self._platform_info(platform)

    def delete_platform(self, scenario_id: str, platform_name: str) -> bool:
        """Remove a platform from the scenario by name."""
        scenario = self._sm.get_scenario(scenario_id)
        before = len(scenario.platforms)
        scenario.platforms = [p for p in scenario.platforms if p.name != platform_name]
        removed = len(scenario.platforms) < before
        if removed:
            logger.info("Deleted platform '%s' from scenario '%s'", platform_name, scenario.name)
        return removed

    def modify_platform(
        self,
        scenario_id: str,
        platform_name: str,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_m: float | None = None,
        platform_type: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Modify an existing platform's properties."""
        platform = self._get_platform(scenario_id, platform_name)
        if latitude is not None:
            platform.position.latitude = latitude
        if longitude is not None:
            platform.position.longitude = longitude
        if altitude_m is not None:
            platform.position.altitude_m = altitude_m
        if platform_type is not None:
            platform.platform_type = platform_type
        if parameters is not None:
            platform.parameters.update(parameters)
        logger.info("Modified platform '%s'", platform_name)
        return self._platform_info(platform)

    def list_platforms(self, scenario_id: str) -> list[dict[str, object]]:
        """List all platforms in a scenario."""
        scenario = self._sm.get_scenario(scenario_id)
        return [self._platform_info(p) for p in scenario.platforms]

    def get_platform(self, scenario_id: str, platform_name: str) -> dict[str, object]:
        """Return info about a single platform."""
        return self._platform_info(self._get_platform(scenario_id, platform_name))

    # ------------------------------------------------------------------
    # Movers
    # ------------------------------------------------------------------

    def add_mover(
        self,
        scenario_id: str,
        platform_name: str,
        mover_type: str = MoverType.ROUTE,
        mover_name: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Add a mover component to a platform."""
        platform = self._get_platform(scenario_id, platform_name)
        comp_name = mover_name or f"{platform_name}_mover"
        comp = Component(
            name=comp_name,
            component_type=mover_type,
            parameters=parameters or {},
        )
        platform.components.append(comp)
        logger.info("Added mover '%s' to platform '%s'", comp_name, platform_name)
        return self._component_info(comp)

    # ------------------------------------------------------------------
    # Sensors
    # ------------------------------------------------------------------

    def add_sensor(
        self,
        scenario_id: str,
        platform_name: str,
        sensor_type: str = SensorType.RADAR,
        sensor_name: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Add a sensor component to a platform."""
        platform = self._get_platform(scenario_id, platform_name)
        comp_name = sensor_name or f"{platform_name}_sensor"
        comp = Component(
            name=comp_name,
            component_type=sensor_type,
            parameters=parameters or {},
        )
        platform.components.append(comp)
        logger.info("Added sensor '%s' to platform '%s'", comp_name, platform_name)
        return self._component_info(comp)

    # ------------------------------------------------------------------
    # Weapons
    # ------------------------------------------------------------------

    def add_weapon(
        self,
        scenario_id: str,
        platform_name: str,
        weapon_type: str = WeaponType.MISSILE,
        weapon_name: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Add a weapon component to a platform."""
        platform = self._get_platform(scenario_id, platform_name)
        comp_name = weapon_name or f"{platform_name}_weapon"
        comp = Component(
            name=comp_name,
            component_type=weapon_type,
            parameters=parameters or {},
        )
        platform.components.append(comp)
        logger.info("Added weapon '%s' to platform '%s'", comp_name, platform_name)
        return self._component_info(comp)

    # ------------------------------------------------------------------
    # Generic component management
    # ------------------------------------------------------------------

    def remove_component(
        self, scenario_id: str, platform_name: str, component_name: str
    ) -> bool:
        """Remove a component from a platform by name."""
        platform = self._get_platform(scenario_id, platform_name)
        before = len(platform.components)
        platform.components = [c for c in platform.components if c.name != component_name]
        removed = len(platform.components) < before
        if removed:
            logger.info("Removed component '%s' from platform '%s'", component_name, platform_name)
        return removed

    def list_components(
        self, scenario_id: str, platform_name: str
    ) -> list[dict[str, object]]:
        """List all components on a platform."""
        platform = self._get_platform(scenario_id, platform_name)
        return [self._component_info(c) for c in platform.components]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_platform(self, scenario_id: str, platform_name: str) -> Platform:
        scenario = self._sm.get_scenario(scenario_id)
        for p in scenario.platforms:
            if p.name == platform_name:
                return p
        raise KeyError(f"Platform '{platform_name}' not found in scenario '{scenario_id}'.")

    @staticmethod
    def _check_unique_platform(scenario, name: str) -> None:
        names = {p.name for p in scenario.platforms}
        if name in names:
            raise ValueError(f"Platform '{name}' already exists in scenario '{scenario.name}'.")

    @staticmethod
    def _platform_info(platform: Platform) -> dict[str, object]:
        return {
            "name": platform.name,
            "platform_type": platform.platform_type,
            "position": {
                "latitude": platform.position.latitude,
                "longitude": platform.position.longitude,
                "altitude_m": platform.position.altitude_m,
            },
            "component_count": len(platform.components),
            "parameters": platform.parameters,
        }

    @staticmethod
    def _component_info(component: Component) -> dict[str, object]:
        return {
            "name": component.name,
            "component_type": component.component_type,
            "parameters": component.parameters,
        }
