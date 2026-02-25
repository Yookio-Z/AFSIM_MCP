def specs():
    return [
        {
            "name": "list_demos",
            "description": "List available demo folders.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_demo_scenarios",
            "description": "List scenario files in a demo folder.",
            "inputSchema": {
                "type": "object",
                "properties": {"demo": {"type": "string"}},
                "required": ["demo"],
            },
        },
        {
            "name": "suggest_scenario_questions",
            "description": "Suggest questions and defaults for a natural language scenario request.",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
            },
        },
        {
            "name": "create_scenario_from_prompt",
            "description": "Generate a basic AFSIM scenario text file from a natural language prompt.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "output_path": {"type": "string"},
                    "project_dir": {"type": "string"},
                    "aircraft_count": {"type": "integer"},
                    "tank_count": {"type": "integer"},
                    "side": {"type": "string"},
                    "duration_min": {"type": "number"},
                    "center": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                        },
                    },
                },
                "required": ["prompt", "output_path"],
            },
        },
        {
            "name": "run_demo",
            "description": "Run a demo scenario and optionally open Mystic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "demo": {"type": "string"},
                    "scenario": {"type": "string"},
                    "open_mystic": {"type": "boolean"},
                },
                "required": ["demo", "scenario"],
            },
        },
    ]


def router(server):
    return {
        "list_demos": lambda _: server.list_demos(),
        "list_demo_scenarios": server.list_demo_scenarios,
        "suggest_scenario_questions": server.suggest_scenario_questions,
        "create_scenario_from_prompt": server.create_scenario_from_prompt,
        "run_demo": server.run_demo,
    }
