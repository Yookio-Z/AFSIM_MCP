"""Scenario management for AFSIM MCP server."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .models import Platform, Position, Scenario

logger = logging.getLogger(__name__)


class ScenarioManager:
    """Manages AFSIM scenarios: create, load, save, validate."""

    def __init__(self, scenarios_dir: str = "scenarios") -> None:
        self._scenarios_dir = Path(scenarios_dir)
        self._scenarios_dir.mkdir(parents=True, exist_ok=True)
        self._active_scenarios: dict[str, Scenario] = {}

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_scenario(
        self,
        name: str,
        description: str = "",
        duration_s: float = 3600.0,
        time_step_s: float = 1.0,
    ) -> Scenario:
        """Create a new, empty scenario."""
        if not name:
            raise ValueError("Scenario name must not be empty.")
        scenario = Scenario(
            name=name,
            description=description,
            duration_s=duration_s,
            time_step_s=time_step_s,
        )
        self._active_scenarios[scenario.scenario_id] = scenario
        logger.info("Created scenario '%s' (id=%s)", name, scenario.scenario_id)
        return scenario

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_scenario_file(self, file_path: str) -> Scenario:
        """Load a scenario from an AFSIM .afsim file (basic parser)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {file_path}")

        scenario = Scenario(name=path.stem, file_path=str(path))
        scenario.parameters["raw_content"] = path.read_text(encoding="utf-8")
        self._active_scenarios[scenario.scenario_id] = scenario
        logger.info("Loaded scenario from '%s' (id=%s)", file_path, scenario.scenario_id)
        return scenario

    def load_scenario_json(self, file_path: str) -> Scenario:
        """Load a scenario from a JSON representation."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario JSON file not found: {file_path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        scenario = self._scenario_from_dict(data)
        scenario.file_path = str(path)
        self._active_scenarios[scenario.scenario_id] = scenario
        logger.info("Loaded scenario JSON from '%s' (id=%s)", file_path, scenario.scenario_id)
        return scenario

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_scenario(self, scenario_id: str, file_path: str | None = None) -> str:
        """Save a scenario to an AFSIM .afsim file.  Returns the saved path."""
        scenario = self._get(scenario_id)
        if file_path is None:
            file_path = str(self._scenarios_dir / f"{scenario.name}.afsim")
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scenario.to_afsim(), encoding="utf-8")
        scenario.file_path = str(path)
        logger.info("Saved scenario '%s' to '%s'", scenario.name, path)
        return str(path)

    def save_scenario_json(self, scenario_id: str, file_path: str | None = None) -> str:
        """Save a scenario to a JSON representation.  Returns the saved path."""
        scenario = self._get(scenario_id)
        if file_path is None:
            file_path = str(self._scenarios_dir / f"{scenario.name}.json")
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._scenario_to_dict(scenario), indent=2), encoding="utf-8")
        logger.info("Saved scenario JSON '%s' to '%s'", scenario.name, path)
        return str(path)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate_scenario(self, scenario_id: str) -> dict[str, object]:
        """Validate a scenario and return a validation report."""
        scenario = self._get(scenario_id)
        errors: list[str] = []
        warnings: list[str] = []

        if not scenario.name:
            errors.append("Scenario name is empty.")
        if scenario.duration_s <= 0:
            errors.append(f"Simulation duration must be positive (got {scenario.duration_s}).")
        if scenario.time_step_s <= 0:
            errors.append(f"Time step must be positive (got {scenario.time_step_s}).")
        if scenario.time_step_s > scenario.duration_s:
            warnings.append("Time step is larger than duration.")
        if not scenario.platforms:
            warnings.append("Scenario has no platforms.")

        platform_names = [p.name for p in scenario.platforms]
        if len(platform_names) != len(set(platform_names)):
            errors.append("Duplicate platform names found.")

        valid = len(errors) == 0
        logger.info(
            "Validated scenario '%s': valid=%s errors=%d warnings=%d",
            scenario.name,
            valid,
            len(errors),
            len(warnings),
        )
        return {"valid": valid, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------
    # List / Get
    # ------------------------------------------------------------------

    def list_scenarios(self) -> list[dict[str, object]]:
        """List all active (in-memory) scenarios."""
        return [
            {
                "scenario_id": s.scenario_id,
                "name": s.name,
                "description": s.description,
                "platform_count": len(s.platforms),
                "duration_s": s.duration_s,
                "file_path": s.file_path,
            }
            for s in self._active_scenarios.values()
        ]

    def get_scenario(self, scenario_id: str) -> Scenario:
        """Return a scenario by id."""
        return self._get(scenario_id)

    def delete_scenario(self, scenario_id: str) -> bool:
        """Remove a scenario from memory (does not delete files)."""
        if scenario_id not in self._active_scenarios:
            return False
        del self._active_scenarios[scenario_id]
        return True

    def list_scenario_files(self) -> list[str]:
        """List .afsim and .json scenario files on disk."""
        files: list[str] = []
        for ext in ("*.afsim", "*.json"):
            files.extend(str(p) for p in self._scenarios_dir.glob(ext))
        return sorted(files)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, scenario_id: str) -> Scenario:
        if scenario_id not in self._active_scenarios:
            raise KeyError(f"Scenario '{scenario_id}' not found.")
        return self._active_scenarios[scenario_id]

    @staticmethod
    def _scenario_to_dict(scenario: Scenario) -> dict:
        return {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "description": scenario.description,
            "duration_s": scenario.duration_s,
            "time_step_s": scenario.time_step_s,
            "parameters": scenario.parameters,
            "platforms": [
                {
                    "name": p.name,
                    "platform_type": p.platform_type,
                    "position": {
                        "latitude": p.position.latitude,
                        "longitude": p.position.longitude,
                        "altitude_m": p.position.altitude_m,
                    },
                    "parameters": p.parameters,
                    "components": [
                        {
                            "name": c.name,
                            "component_type": c.component_type,
                            "parameters": c.parameters,
                        }
                        for c in p.components
                    ],
                }
                for p in scenario.platforms
            ],
        }

    @staticmethod
    def _scenario_from_dict(data: dict) -> Scenario:
        platforms = []
        for pd in data.get("platforms", []):
            pos_data = pd.get("position", {})
            pos = Position(
                latitude=pos_data.get("latitude", 0.0),
                longitude=pos_data.get("longitude", 0.0),
                altitude_m=pos_data.get("altitude_m", 0.0),
            )
            from .models import Component  # local import to avoid circularity

            comps = [
                Component(
                    name=cd["name"],
                    component_type=cd["component_type"],
                    parameters=cd.get("parameters", {}),
                )
                for cd in pd.get("components", [])
            ]
            platforms.append(
                Platform(
                    name=pd["name"],
                    platform_type=pd.get("platform_type", "wsf_platform"),
                    position=pos,
                    components=comps,
                    parameters=pd.get("parameters", {}),
                )
            )
        return Scenario(
            name=data["name"],
            scenario_id=data.get("scenario_id", ""),
            description=data.get("description", ""),
            duration_s=data.get("duration_s", 3600.0),
            time_step_s=data.get("time_step_s", 1.0),
            platforms=platforms,
            parameters=data.get("parameters", {}),
        )
