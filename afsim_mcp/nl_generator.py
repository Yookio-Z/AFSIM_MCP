"""Natural language scenario generation for AFSIM MCP server."""

from __future__ import annotations

import logging
import re

from .models import Component, MoverType, Platform, Position, SensorType, WeaponType
from .scenario_manager import ScenarioManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword look-up tables
# ---------------------------------------------------------------------------

_PLATFORM_KEYWORDS: dict[str, str] = {
    # Aircraft
    "aircraft": "wsf_air_vehicle",
    "fighter": "wsf_air_vehicle",
    "bomber": "wsf_air_vehicle",
    "drone": "wsf_air_vehicle",
    "uav": "wsf_air_vehicle",
    "helicopter": "wsf_air_vehicle",
    # Ground
    "tank": "wsf_ground_vehicle",
    "vehicle": "wsf_ground_vehicle",
    "truck": "wsf_ground_vehicle",
    "artillery": "wsf_ground_vehicle",
    # Naval
    "ship": "wsf_surface_ship",
    "destroyer": "wsf_surface_ship",
    "carrier": "wsf_surface_ship",
    "frigate": "wsf_surface_ship",
    "submarine": "wsf_subsurface_vehicle",
    # Missile / munition
    "missile": "wsf_missile",
    "sam": "wsf_ground_vehicle",
    # Generic
    "satellite": "wsf_satellite",
    "station": "wsf_ground_station",
}

_MOVER_KEYWORDS: dict[str, str] = {
    "fixed": MoverType.FIXED,
    "stationary": MoverType.FIXED,
    "route": MoverType.ROUTE,
    "patrol": MoverType.ROUTE,
    "air": MoverType.AIR,
    "fly": MoverType.AIR,
    "ground": MoverType.GROUND,
    "drive": MoverType.GROUND,
    "surface": MoverType.SURFACE,
    "sail": MoverType.SURFACE,
    "subsurface": MoverType.SUBSURFACE,
    "dive": MoverType.SUBSURFACE,
    "orbit": MoverType.ORBIT,
}

_SENSOR_KEYWORDS: dict[str, str] = {
    "radar": SensorType.RADAR,
    "ew": SensorType.RADAR,
    "eo": SensorType.EO,
    "camera": SensorType.EO,
    "optical": SensorType.EO,
    "ir": SensorType.IR,
    "infrared": SensorType.IR,
    "comm": SensorType.COMM,
    "comms": SensorType.COMM,
    "communications": SensorType.COMM,
}

_WEAPON_KEYWORDS: dict[str, str] = {
    "missile": WeaponType.MISSILE,
    "sam": WeaponType.MISSILE,
    "aam": WeaponType.MISSILE,
    "bomb": WeaponType.BOMB,
    "gun": WeaponType.BULLET,
    "cannon": WeaponType.BULLET,
    "bullet": WeaponType.BULLET,
}


def _find_keyword(text: str, table: dict[str, str]) -> str | None:
    lower = text.lower()
    for kw, val in table.items():
        if kw in lower:
            return val
    return None


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]


def _extract_duration(text: str) -> float:
    """Return simulation duration in seconds from a natural language string."""
    lower = text.lower()
    # Match "N hour(s)", "N minute(s)/min", "N second(s)/sec" explicitly
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*hours?", lower)
    if hour_match:
        return float(hour_match.group(1)) * 3600
    min_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|min\b)", lower)
    if min_match:
        return float(min_match.group(1)) * 60
    sec_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:seconds?|sec\b)", lower)
    if sec_match:
        return float(sec_match.group(1))
    return 3600.0


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


class NLGenerator:
    """Generate AFSIM scenarios from natural language prompts."""

    def __init__(self, scenario_manager: ScenarioManager) -> None:
        self._sm = scenario_manager

    def generate_scenario(self, prompt: str) -> dict[str, object]:
        """Parse a free-text prompt and build an AFSIM scenario.

        The parser uses keyword matching and heuristics.  It is designed
        to be useful for rapid prototyping; more sophisticated NLP can be
        added later.

        Parameters
        ----------
        prompt:
            Natural language description of the desired scenario.

        Returns
        -------
        dict
            Contains ``scenario_id``, ``name``, ``warnings``, and
            ``afsim_preview`` (the generated scenario text).
        """
        warnings: list[str] = []
        lower = prompt.lower()

        # -- Scenario name (use first noun-phrase up to 40 chars) -----------
        name_match = re.match(r"[a-z0-9 _-]{3,40}", lower)
        name = (name_match.group(0).strip().replace(" ", "_") if name_match else "generated_scenario")
        name = re.sub(r"[^a-z0-9_-]", "", name) or "generated_scenario"

        # -- Duration -------------------------------------------------------
        duration_s = _extract_duration(prompt)

        # -- Create scenario ------------------------------------------------
        scenario = self._sm.create_scenario(
            name=name,
            description=f"Auto-generated from prompt: {prompt[:200]}",
            duration_s=duration_s,
            time_step_s=1.0,
        )

        # -- Parse platforms ------------------------------------------------
        # Look for patterns like "2 fighters", "a ship", "three tanks"
        word_to_num = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        # Replace word numbers
        normalized = lower
        for word, num in word_to_num.items():
            normalized = normalized.replace(word, str(num))

        platform_patterns = re.finditer(
            r"(\d+)?\s*(aircraft|fighter|bomber|drone|uav|helicopter|"
            r"tank|vehicle|truck|artillery|ship|destroyer|carrier|frigate|"
            r"submarine|satellite|station|sam)",
            normalized,
        )
        entity_counts: dict[str, int] = {}
        for match in platform_patterns:
            count_str, entity_word = match.group(1), match.group(2)
            count = int(count_str) if count_str else 1
            entity_counts[entity_word] = entity_counts.get(entity_word, 0) + count

        if not entity_counts:
            warnings.append(
                "No recognisable platform types found in prompt; "
                "creating a default scenario with one generic platform."
            )
            entity_counts["platform"] = 1

        created_platforms: list[str] = []
        for entity_word, count in entity_counts.items():
            platform_type = _PLATFORM_KEYWORDS.get(entity_word, "wsf_platform")
            mover_type = _infer_mover(entity_word, prompt)
            sensor_type = _find_keyword(prompt, _SENSOR_KEYWORDS)
            weapon_type = _find_keyword(prompt, _WEAPON_KEYWORDS)

            for i in range(1, count + 1):
                pname = f"{entity_word}_{i}" if count > 1 else entity_word
                pname = pname.replace(" ", "_")
                platform = Platform(
                    name=pname,
                    platform_type=platform_type,
                    position=Position(
                        latitude=35.0 + i * 0.1,
                        longitude=-80.0 + i * 0.1,
                        altitude_m=_infer_altitude(entity_word),
                    ),
                )
                # Add mover
                platform.components.append(
                    Component(
                        name=f"{pname}_mover",
                        component_type=mover_type,
                    )
                )
                # Add sensor if mentioned
                if sensor_type:
                    platform.components.append(
                        Component(
                            name=f"{pname}_sensor",
                            component_type=sensor_type,
                        )
                    )
                # Add weapon if mentioned
                if weapon_type and entity_word not in ("station", "satellite"):
                    platform.components.append(
                        Component(
                            name=f"{pname}_weapon",
                            component_type=weapon_type,
                        )
                    )
                scenario.platforms.append(platform)
                created_platforms.append(pname)

        afsim_text = scenario.to_afsim()
        logger.info(
            "Generated scenario '%s' with %d platforms from prompt.",
            scenario.name,
            len(scenario.platforms),
        )
        return {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "platform_count": len(scenario.platforms),
            "platforms": created_platforms,
            "duration_s": scenario.duration_s,
            "warnings": warnings,
            "afsim_preview": afsim_text,
        }

    def refine_scenario(self, scenario_id: str, refinement_prompt: str) -> dict[str, object]:
        """Apply a refinement prompt to an existing scenario.

        Currently supports:
        - Adding more platforms ("add 2 more fighters")
        - Changing duration ("extend to 2 hours")
        """
        scenario = self._sm.get_scenario(scenario_id)
        lower = refinement_prompt.lower()
        changes: list[str] = []

        # Check for duration change
        if any(kw in lower for kw in ("extend", "duration", "last", "run for")):
            new_dur = _extract_duration(refinement_prompt)
            if new_dur != scenario.duration_s:
                scenario.duration_s = new_dur
                changes.append(f"Duration updated to {new_dur}s")

        # Check for add platforms
        add_match = re.search(r"add\s+(\d+)?\s*(\w+)", lower)
        if add_match:
            count_str, entity_word = add_match.group(1), add_match.group(2)
            count = int(count_str) if count_str else 1
            platform_type = _PLATFORM_KEYWORDS.get(entity_word, "wsf_platform")
            mover_type = _infer_mover(entity_word, refinement_prompt)
            existing = {p.name for p in scenario.platforms}
            for i in range(1, count + 1):
                pname = f"{entity_word}_{len(existing) + i}"
                platform = Platform(
                    name=pname,
                    platform_type=platform_type,
                    position=Position(latitude=36.0 + i * 0.1, longitude=-80.0),
                )
                platform.components.append(
                    Component(name=f"{pname}_mover", component_type=mover_type)
                )
                scenario.platforms.append(platform)
                changes.append(f"Added platform '{pname}'")

        if not changes:
            changes.append("No changes applied (prompt not recognised).")

        return {
            "scenario_id": scenario_id,
            "changes": changes,
            "platform_count": len(scenario.platforms),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_mover(entity_word: str, prompt: str) -> str:
    """Infer mover type from entity word and full prompt."""
    combined = (entity_word + " " + prompt).lower()
    mover = _find_keyword(combined, _MOVER_KEYWORDS)
    if mover:
        return mover
    # Defaults by entity
    defaults: dict[str, str] = {
        "aircraft": MoverType.AIR,
        "fighter": MoverType.AIR,
        "bomber": MoverType.AIR,
        "drone": MoverType.AIR,
        "uav": MoverType.AIR,
        "helicopter": MoverType.AIR,
        "ship": MoverType.SURFACE,
        "destroyer": MoverType.SURFACE,
        "carrier": MoverType.SURFACE,
        "frigate": MoverType.SURFACE,
        "submarine": MoverType.SUBSURFACE,
        "satellite": MoverType.ORBIT,
    }
    return defaults.get(entity_word, MoverType.ROUTE)


def _infer_altitude(entity_word: str) -> float:
    """Infer default altitude in metres from entity type."""
    altitudes: dict[str, float] = {
        "aircraft": 10000.0,
        "fighter": 10000.0,
        "bomber": 12000.0,
        "drone": 3000.0,
        "uav": 3000.0,
        "helicopter": 1000.0,
        "satellite": 400000.0,
    }
    return altitudes.get(entity_word, 0.0)
