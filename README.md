# AFSIM MCP Server

MCP (Model Context Protocol) server for the **Advanced Framework for Simulation, Integration, and Modeling (AFSIM)**. Enables LLMs and AI agents to interact with AFSIM through standardized tools.

## Features

| Category | Tools |
|---|---|
| **Scenario Management** | `create_scenario`, `load_scenario`, `save_scenario`, `validate_scenario`, `list_scenarios`, `delete_scenario`, `get_scenario_content`, `list_scenario_files` |
| **Entity & Component Management** | `create_platform`, `delete_platform`, `modify_platform`, `list_platforms`, `add_mover`, `add_sensor`, `add_weapon`, `remove_component`, `list_components` |
| **Simulation Control** | `run_simulation`, `stop_simulation`, `get_simulation_status`, `list_simulation_runs`, `set_afsim_binary` |
| **Results Handling** | `list_result_files`, `query_csv_results`, `query_evt_results`, `query_aer_results`, `export_results_to_json`, `get_results_summary` |
| **AFSIM Backend** | `set_afsim_home`, `detect_afsim_installation`, `set_tool_binary_path`, `run_wizard`, `run_mission`, `run_warlock`, `run_mystic` |
| **Natural Language** | `generate_scenario_from_prompt`, `refine_scenario_from_prompt` |

## Installation

```bash
pip install -e .
```

Or install dependencies directly:

```bash
pip install mcp
```

## Usage

### Running the server

```bash
# Via installed CLI
afsim-mcp

# Via Python module
python -m afsim_mcp.server
```

The server uses **stdio transport** and is compatible with any MCP client (Claude Desktop, VS Code MCP extension, etc.).

### Claude Desktop configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "afsim": {
      "command": "afsim-mcp"
    }
  }
}
```

Or if not installed:

```json
{
  "mcpServers": {
    "afsim": {
      "command": "python",
      "args": ["-m", "afsim_mcp.server"],
      "cwd": "/path/to/AFSIM_MCP"
    }
  }
}
```

## Example Workflows

### 1. Generate a scenario from natural language

```
generate_scenario_from_prompt("Create an air defense scenario with 2 fighters
and a SAM site, radar sensors, over 2 hours")
```

### 2. Manual scenario construction

```
# Create scenario
create_scenario(name="red_blue", duration_s=7200)

# Add platforms
create_platform(scenario_id="...", name="alpha_fighter",
                platform_type="wsf_air_vehicle",
                latitude=35.5, longitude=-80.2, altitude_m=10000)

# Add components
add_mover(scenario_id="...", platform_name="alpha_fighter",
          mover_type="wsf_air_mover")
add_sensor(scenario_id="...", platform_name="alpha_fighter",
           sensor_type="wsf_radar_sensor")

# Validate and save
validate_scenario(scenario_id="...")
save_scenario(scenario_id="...", file_path="scenarios/red_blue.afsim")
```

### 3. Run and monitor a simulation

```
# Configure AFSIM binary (if available)
set_afsim_home("/opt/afsim")

# Run simulation (dry_run=True if no AFSIM installed)
run_simulation(scenario_id="...", dry_run=True)

# Check status
get_simulation_status(run_id="...")
```

### 4. Query results

```
list_result_files(directory="simulation_output")
query_csv_results(file_path="simulation_output/run1/tracks.csv", max_rows=100)
export_results_to_json(file_path="simulation_output/run1/events.evt")
```

## Architecture

```
afsim_mcp/
├── __init__.py
├── server.py              # FastMCP server + tool definitions
├── models.py              # Data models (Scenario, Platform, SimulationRun, …)
├── scenario_manager.py    # Create/load/save/validate scenarios
├── entity_manager.py      # Platform & component management
├── simulation_controller.py  # Run/stop/query simulations
├── results_handler.py     # List/query/export result files
├── afsim_backend.py       # Binary path management & tool launching
└── nl_generator.py        # Natural language → scenario generation
```

## Testing

```bash
pip install pytest
pytest tests/
```

## License

MIT
