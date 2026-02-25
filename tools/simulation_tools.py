def specs():
    return [
        {
            "name": "run_simulation",
            "description": "Run a simulation for a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "run_config": {"type": "object"},
                },
                "required": ["scenario_id"],
            },
        },
        {
            "name": "stop_simulation",
            "description": "Stop a running simulation.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "get_simulation_status",
            "description": "Get status of a simulation run.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "list_results",
            "description": "List results for a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {"scenario_id": {"type": "string"}},
                "required": ["scenario_id"],
            },
        },
        {
            "name": "export_results",
            "description": "Export results for a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "format": {"type": "string", "enum": ["csv", "json"]},
                    "path": {"type": "string"},
                },
                "required": ["scenario_id", "format"],
            },
        },
        {
            "name": "query_results",
            "description": "Search results by keyword.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["scenario_id", "query"],
            },
        },
        {
            "name": "list_output_files",
            "description": "List output files in a directory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "extensions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["directory"],
            },
        },
        {
            "name": "find_latest_aer",
            "description": "Find latest AER file under a directory.",
            "inputSchema": {
                "type": "object",
                "properties": {"directory": {"type": "string"}},
                "required": ["directory"],
            },
        },
        {
            "name": "summarize_evt",
            "description": "Summarize an EVT text file.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "tail_text_file",
            "description": "Read the last N lines of a text file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "lines": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    ]


def router(server):
    return {
        "run_simulation": server.run_simulation,
        "stop_simulation": server.stop_simulation,
        "get_simulation_status": server.get_simulation_status,
        "list_results": server.list_results,
        "export_results": server.export_results,
        "query_results": server.query_results,
        "list_output_files": server.list_output_files,
        "find_latest_aer": server.find_latest_aer_tool,
        "summarize_evt": server.summarize_evt,
        "tail_text_file": server.tail_text_file,
    }
