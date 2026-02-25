"""AFSIM MCP Server – main entry point.

Run with:
    python -m afsim_mcp.server

Or via the installed CLI:
    afsim-mcp

The server exposes tools for:
  1. Scenario management        (create/load/save/validate)
  2. Entity & component mgmt   (platforms, movers, sensors, weapons)
  3. Simulation control         (run/stop/status)
  4. Results handling           (list/query/export)
  5. AFSIM backend integration  (binary paths, Wizard/Mission/Warlock/Mystic)
  6. Natural language generation (generate/refine scenarios from text)
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .afsim_backend import AfsimBackend
from .entity_manager import EntityManager
from .nl_generator import NLGenerator
from .results_handler import ResultsHandler
from .scenario_manager import ScenarioManager
from .simulation_controller import SimulationController

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state (shared singletons)
# ---------------------------------------------------------------------------

_scenario_manager = ScenarioManager()
_entity_manager = EntityManager(_scenario_manager)
_simulation_controller = SimulationController(_scenario_manager)
_results_handler = ResultsHandler()
_afsim_backend = AfsimBackend()
_nl_generator = NLGenerator(_scenario_manager)

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "AFSIM MCP Server",
    instructions=(
        "MCP server for the Advanced Framework for Simulation, Integration, "
        "and Modeling (AFSIM).  Use the available tools to manage scenarios, "
        "entities, run simulations, handle results, and generate scenarios "
        "from natural language descriptions."
    ),
)

# ===========================================================================
# 1. SCENARIO MANAGEMENT
# ===========================================================================


@mcp.tool()
def create_scenario(
    name: str,
    description: str = "",
    duration_s: float = 3600.0,
    time_step_s: float = 1.0,
) -> str:
    """Create a new AFSIM scenario in memory.

    Parameters
    ----------
    name:
        Unique name for the scenario.
    description:
        Optional human-readable description.
    duration_s:
        Simulation duration in seconds (default 3600).
    time_step_s:
        Simulation time step in seconds (default 1.0).

    Returns
    -------
    JSON with scenario_id, name, and metadata.
    """
    scenario = _scenario_manager.create_scenario(
        name=name,
        description=description,
        duration_s=duration_s,
        time_step_s=time_step_s,
    )
    return json.dumps(
        {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "description": scenario.description,
            "duration_s": scenario.duration_s,
            "time_step_s": scenario.time_step_s,
        }
    )


@mcp.tool()
def load_scenario(file_path: str, format: str = "afsim") -> str:
    """Load a scenario from disk.

    Parameters
    ----------
    file_path:
        Path to the scenario file.
    format:
        'afsim' for .afsim files (default), 'json' for JSON files.

    Returns
    -------
    JSON with scenario_id and metadata.
    """
    if format == "json":
        scenario = _scenario_manager.load_scenario_json(file_path)
    else:
        scenario = _scenario_manager.load_scenario_file(file_path)
    return json.dumps(
        {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "file_path": scenario.file_path,
            "platform_count": len(scenario.platforms),
        }
    )


@mcp.tool()
def save_scenario(
    scenario_id: str,
    file_path: str = "",
    format: str = "afsim",
) -> str:
    """Save a scenario to disk.

    Parameters
    ----------
    scenario_id:
        UUID of the scenario to save.
    file_path:
        Destination path.  Defaults to scenarios/<name>.afsim (or .json).
    format:
        'afsim' (default) or 'json'.

    Returns
    -------
    JSON with the saved file path.
    """
    fp = file_path or None
    if format == "json":
        saved = _scenario_manager.save_scenario_json(scenario_id, fp)
    else:
        saved = _scenario_manager.save_scenario(scenario_id, fp)
    return json.dumps({"saved_path": saved})


@mcp.tool()
def validate_scenario(scenario_id: str) -> str:
    """Validate a scenario and return errors/warnings.

    Parameters
    ----------
    scenario_id:
        UUID of the scenario to validate.

    Returns
    -------
    JSON with 'valid', 'errors', and 'warnings' lists.
    """
    result = _scenario_manager.validate_scenario(scenario_id)
    return json.dumps(result)


@mcp.tool()
def list_scenarios() -> str:
    """List all in-memory scenarios.

    Returns
    -------
    JSON array of scenario summaries.
    """
    return json.dumps(_scenario_manager.list_scenarios())


@mcp.tool()
def list_scenario_files() -> str:
    """List scenario files (.afsim and .json) in the scenarios directory.

    Returns
    -------
    JSON array of file paths.
    """
    return json.dumps(_scenario_manager.list_scenario_files())


@mcp.tool()
def delete_scenario(scenario_id: str) -> str:
    """Remove a scenario from memory (does not delete files on disk).

    Parameters
    ----------
    scenario_id:
        UUID of the scenario to remove.

    Returns
    -------
    JSON with 'removed' boolean.
    """
    removed = _scenario_manager.delete_scenario(scenario_id)
    return json.dumps({"removed": removed})


@mcp.tool()
def get_scenario_content(scenario_id: str) -> str:
    """Get the AFSIM text representation of a scenario.

    Parameters
    ----------
    scenario_id:
        UUID of the scenario.

    Returns
    -------
    JSON with 'name' and 'content' (AFSIM scenario text).
    """
    scenario = _scenario_manager.get_scenario(scenario_id)
    return json.dumps({"name": scenario.name, "content": scenario.to_afsim()})


# ===========================================================================
# 2. ENTITY & COMPONENT MANAGEMENT
# ===========================================================================


@mcp.tool()
def create_platform(
    scenario_id: str,
    name: str,
    platform_type: str = "wsf_platform",
    latitude: float = 0.0,
    longitude: float = 0.0,
    altitude_m: float = 0.0,
) -> str:
    """Add a new platform (entity) to a scenario.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    name:
        Unique name for the platform within the scenario.
    platform_type:
        AFSIM platform type (e.g. 'wsf_air_vehicle', 'wsf_ground_vehicle').
    latitude, longitude:
        Initial position in decimal degrees.
    altitude_m:
        Initial altitude in metres.

    Returns
    -------
    JSON with platform metadata.
    """
    result = _entity_manager.create_platform(
        scenario_id=scenario_id,
        name=name,
        platform_type=platform_type,
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
    )
    return json.dumps(result)


@mcp.tool()
def delete_platform(scenario_id: str, platform_name: str) -> str:
    """Remove a platform from a scenario.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the platform to remove.

    Returns
    -------
    JSON with 'removed' boolean.
    """
    removed = _entity_manager.delete_platform(scenario_id, platform_name)
    return json.dumps({"removed": removed})


@mcp.tool()
def modify_platform(
    scenario_id: str,
    platform_name: str,
    latitude: float | None = None,
    longitude: float | None = None,
    altitude_m: float | None = None,
    platform_type: str | None = None,
) -> str:
    """Modify an existing platform's position or type.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the platform to modify.
    latitude, longitude, altitude_m:
        New position values (omit to keep current).
    platform_type:
        New platform type string (omit to keep current).

    Returns
    -------
    JSON with updated platform metadata.
    """
    result = _entity_manager.modify_platform(
        scenario_id=scenario_id,
        platform_name=platform_name,
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        platform_type=platform_type,
    )
    return json.dumps(result)


@mcp.tool()
def list_platforms(scenario_id: str) -> str:
    """List all platforms in a scenario.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.

    Returns
    -------
    JSON array of platform summaries.
    """
    return json.dumps(_entity_manager.list_platforms(scenario_id))


@mcp.tool()
def add_mover(
    scenario_id: str,
    platform_name: str,
    mover_type: str = "wsf_route_mover",
    mover_name: str = "",
) -> str:
    """Add a mover component to a platform.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the target platform.
    mover_type:
        AFSIM mover type (e.g. 'wsf_route_mover', 'wsf_air_mover').
    mover_name:
        Optional name for the mover component.

    Returns
    -------
    JSON with component metadata.
    """
    result = _entity_manager.add_mover(
        scenario_id=scenario_id,
        platform_name=platform_name,
        mover_type=mover_type,
        mover_name=mover_name or None,
    )
    return json.dumps(result)


@mcp.tool()
def add_sensor(
    scenario_id: str,
    platform_name: str,
    sensor_type: str = "wsf_radar_sensor",
    sensor_name: str = "",
) -> str:
    """Add a sensor component to a platform.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the target platform.
    sensor_type:
        AFSIM sensor type (e.g. 'wsf_radar_sensor', 'wsf_eo_sensor').
    sensor_name:
        Optional name for the sensor component.

    Returns
    -------
    JSON with component metadata.
    """
    result = _entity_manager.add_sensor(
        scenario_id=scenario_id,
        platform_name=platform_name,
        sensor_type=sensor_type,
        sensor_name=sensor_name or None,
    )
    return json.dumps(result)


@mcp.tool()
def add_weapon(
    scenario_id: str,
    platform_name: str,
    weapon_type: str = "wsf_missile",
    weapon_name: str = "",
) -> str:
    """Add a weapon component to a platform.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the target platform.
    weapon_type:
        AFSIM weapon type (e.g. 'wsf_missile', 'wsf_bomb').
    weapon_name:
        Optional name for the weapon component.

    Returns
    -------
    JSON with component metadata.
    """
    result = _entity_manager.add_weapon(
        scenario_id=scenario_id,
        platform_name=platform_name,
        weapon_type=weapon_type,
        weapon_name=weapon_name or None,
    )
    return json.dumps(result)


@mcp.tool()
def remove_component(
    scenario_id: str, platform_name: str, component_name: str
) -> str:
    """Remove a component from a platform.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the target platform.
    component_name:
        Name of the component to remove.

    Returns
    -------
    JSON with 'removed' boolean.
    """
    removed = _entity_manager.remove_component(scenario_id, platform_name, component_name)
    return json.dumps({"removed": removed})


@mcp.tool()
def list_components(scenario_id: str, platform_name: str) -> str:
    """List all components on a platform.

    Parameters
    ----------
    scenario_id:
        UUID of the target scenario.
    platform_name:
        Name of the target platform.

    Returns
    -------
    JSON array of component summaries.
    """
    return json.dumps(_entity_manager.list_components(scenario_id, platform_name))


# ===========================================================================
# 3. SIMULATION CONTROL
# ===========================================================================


@mcp.tool()
def run_simulation(
    scenario_id: str,
    dry_run: bool = False,
) -> str:
    """Run an AFSIM simulation for the specified scenario.

    If no AFSIM binary is configured (or dry_run is True), the simulation
    is recorded as completed immediately without executing AFSIM.

    Parameters
    ----------
    scenario_id:
        UUID of the scenario to simulate.
    dry_run:
        If True, skip actual AFSIM execution (useful for testing).

    Returns
    -------
    JSON with run_id, status, and other run metadata.
    """
    run = _simulation_controller.run_simulation(scenario_id, dry_run=dry_run)
    return json.dumps(_simulation_controller.get_run_status(run.run_id))


@mcp.tool()
def stop_simulation(run_id: str) -> str:
    """Stop a running simulation.

    Parameters
    ----------
    run_id:
        UUID of the simulation run to stop.

    Returns
    -------
    JSON with updated run status.
    """
    run = _simulation_controller.stop_simulation(run_id)
    return json.dumps(_simulation_controller.get_run_status(run.run_id))


@mcp.tool()
def get_simulation_status(run_id: str) -> str:
    """Query the current status of a simulation run.

    Parameters
    ----------
    run_id:
        UUID of the simulation run.

    Returns
    -------
    JSON with status, times, PID, output directory, etc.
    """
    return json.dumps(_simulation_controller.get_run_status(run_id))


@mcp.tool()
def list_simulation_runs() -> str:
    """List all known simulation runs and their statuses.

    Returns
    -------
    JSON array of run summaries.
    """
    return json.dumps(_simulation_controller.list_runs())


@mcp.tool()
def set_afsim_binary(binary_path: str) -> str:
    """Configure the path to the AFSIM simulation binary.

    Parameters
    ----------
    binary_path:
        Absolute path to the AFSIM executable.

    Returns
    -------
    JSON confirmation.
    """
    _simulation_controller.set_afsim_binary(binary_path)
    return json.dumps({"binary_path": binary_path, "configured": True})


# ===========================================================================
# 4. RESULTS HANDLING
# ===========================================================================


@mcp.tool()
def list_result_files(
    run_id: str = "",
    directory: str = "",
    formats: str = "",
) -> str:
    """List simulation result files.

    Parameters
    ----------
    run_id:
        Filter to a specific run's output directory (optional).
    directory:
        Directory to scan (overrides default output dir).
    formats:
        Comma-separated list of extensions to include (e.g. '.aer,.csv').

    Returns
    -------
    JSON array of result file metadata.
    """
    fmt_list = [f.strip() for f in formats.split(",") if f.strip()] if formats else None
    results = _results_handler.list_result_files(
        run_id=run_id or None,
        directory=directory or None,
        formats=fmt_list,
    )
    return json.dumps(results)


@mcp.tool()
def query_csv_results(
    file_path: str,
    columns: str = "",
    max_rows: int = 1000,
) -> str:
    """Read and query a CSV result file.

    Parameters
    ----------
    file_path:
        Path to the CSV file.
    columns:
        Comma-separated column names to include (all if empty).
    max_rows:
        Maximum rows to return (default 1000).

    Returns
    -------
    JSON with columns, row_count, and rows.
    """
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
    return json.dumps(_results_handler.query_csv(file_path, col_list, max_rows))


@mcp.tool()
def query_evt_results(file_path: str, max_lines: int = 500) -> str:
    """Read an AFSIM .evt event file.

    Parameters
    ----------
    file_path:
        Path to the .evt file.
    max_lines:
        Maximum lines to return (default 500).

    Returns
    -------
    JSON with line_count and lines array.
    """
    return json.dumps(_results_handler.query_evt(file_path, max_lines))


@mcp.tool()
def query_aer_results(file_path: str, max_lines: int = 500) -> str:
    """Read an AFSIM .aer archive/result file.

    Parameters
    ----------
    file_path:
        Path to the .aer file.
    max_lines:
        Maximum lines to return (default 500).

    Returns
    -------
    JSON with line_count and lines array.
    """
    return json.dumps(_results_handler.query_aer(file_path, max_lines))


@mcp.tool()
def export_results_to_json(file_path: str, output_path: str = "") -> str:
    """Convert a result file (.csv, .evt, .aer) to JSON format.

    Parameters
    ----------
    file_path:
        Path to the source result file.
    output_path:
        Destination JSON path (defaults to same name with .json extension).

    Returns
    -------
    JSON with the output file path.
    """
    out = _results_handler.export_to_json(file_path, output_path or None)
    return json.dumps({"output_path": out})


@mcp.tool()
def get_results_summary(directory: str = "") -> str:
    """Summarise simulation results in a directory.

    Parameters
    ----------
    directory:
        Directory to summarise (defaults to simulation output dir).

    Returns
    -------
    JSON with total_files, by_format counts, and total_size_bytes.
    """
    return json.dumps(_results_handler.get_result_summary(directory or None))


# ===========================================================================
# 5. AFSIM BACKEND INTEGRATION
# ===========================================================================


@mcp.tool()
def set_afsim_home(path: str) -> str:
    """Set the AFSIM installation root directory.

    Parameters
    ----------
    path:
        Path to AFSIM_HOME (the directory containing bin/, data/, etc.).

    Returns
    -------
    JSON confirmation with detected binaries.
    """
    _afsim_backend.set_afsim_home(path)
    detection = _afsim_backend.detect_afsim_installation()
    return json.dumps(detection)


@mcp.tool()
def detect_afsim_installation() -> str:
    """Auto-detect AFSIM installation from environment and file system.

    Returns
    -------
    JSON with afsim_home, binary paths, and all_found flag.
    """
    return json.dumps(_afsim_backend.detect_afsim_installation())


@mcp.tool()
def set_tool_binary_path(tool: str, path: str) -> str:
    """Override the binary path for a specific AFSIM tool.

    Parameters
    ----------
    tool:
        Tool identifier: 'wizard', 'mission', 'warlock', or 'mystic'.
    path:
        Absolute path to the tool binary.

    Returns
    -------
    JSON confirmation.
    """
    _afsim_backend.set_binary_path(tool, path)
    return json.dumps({"tool": tool, "path": path, "configured": True})


@mcp.tool()
def run_wizard(scenario_file: str = "") -> str:
    """Launch the AFSIM Wizard (GUI scenario builder).

    Parameters
    ----------
    scenario_file:
        Optional path to open in Wizard.

    Returns
    -------
    JSON with success flag and PID (if launched).
    """
    return json.dumps(_afsim_backend.run_wizard(scenario_file or None))


@mcp.tool()
def run_mission(scenario_file: str = "") -> str:
    """Launch the AFSIM Mission Planner.

    Parameters
    ----------
    scenario_file:
        Optional path to open in Mission Planner.

    Returns
    -------
    JSON with success flag and PID.
    """
    return json.dumps(_afsim_backend.run_mission(scenario_file or None))


@mcp.tool()
def run_warlock(
    scenario_file: str,
    output_dir: str = ".",
) -> str:
    """Run the AFSIM Warlock batch simulation engine.

    Parameters
    ----------
    scenario_file:
        Path to the AFSIM scenario file.
    output_dir:
        Directory for output files (default current dir).

    Returns
    -------
    JSON with success flag, returncode, stdout/stderr snippets.
    """
    return json.dumps(_afsim_backend.run_warlock(scenario_file, output_dir))


@mcp.tool()
def run_mystic(results_dir: str) -> str:
    """Launch the AFSIM Mystic post-processor.

    Parameters
    ----------
    results_dir:
        Directory containing simulation results to analyse.

    Returns
    -------
    JSON with success flag and PID.
    """
    return json.dumps(_afsim_backend.run_mystic(results_dir))


# ===========================================================================
# 6. NATURAL LANGUAGE SUPPORT
# ===========================================================================


@mcp.tool()
def generate_scenario_from_prompt(prompt: str) -> str:
    """Generate an AFSIM scenario from a natural language description.

    The generator uses keyword matching and heuristics to parse the prompt
    and build a scenario with platforms, movers, sensors, and weapons.

    Examples:
        "Create a scenario with 2 fighters and a ship over 2 hours"
        "Simulate 3 UAVs with radar sensors patrolling for 30 minutes"
        "Air defense scenario: 1 SAM site and 4 attack aircraft, 1 hour"

    Parameters
    ----------
    prompt:
        Natural language description of the desired scenario.

    Returns
    -------
    JSON with scenario_id, name, platform list, warnings, and AFSIM preview.
    """
    return json.dumps(_nl_generator.generate_scenario(prompt))


@mcp.tool()
def refine_scenario_from_prompt(scenario_id: str, refinement_prompt: str) -> str:
    """Apply a natural language refinement to an existing scenario.

    Supports:
      - Adding platforms: "add 2 more fighters"
      - Changing duration: "extend to 3 hours"

    Parameters
    ----------
    scenario_id:
        UUID of the scenario to refine.
    refinement_prompt:
        Natural language description of the changes to make.

    Returns
    -------
    JSON with changes applied and updated platform count.
    """
    return json.dumps(_nl_generator.refine_scenario(scenario_id, refinement_prompt))


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the AFSIM MCP server using stdio transport."""
    logger.info("Starting AFSIM MCP Server …")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
