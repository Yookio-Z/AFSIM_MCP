def specs():
    return [
        {
            "name": "set_afsim_bin",
            "description": "Set AFSIM bin directory path.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "get_afsim_bin",
            "description": "Get AFSIM bin directory path.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "run_wizard",
            "description": "Launch AFSIM Wizard with arguments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "console": {"type": "boolean"},
                    "working_dir": {"type": "string"},
                },
            },
        },
        {
            "name": "run_mission",
            "description": "Run Mission with a scenario file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "working_dir": {"type": "string"},
                },
                "required": ["scenario"],
            },
        },
        {
            "name": "run_mission_with_args",
            "description": "Run Mission with extra arguments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "working_dir": {"type": "string"},
                },
                "required": ["scenario"],
            },
        },
        {
            "name": "run_warlock",
            "description": "Launch Warlock with optional arguments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "working_dir": {"type": "string"},
                },
            },
        },
        {
            "name": "run_mystic",
            "description": "Launch Mystic with optional recording file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "recording": {"type": "string"},
                    "working_dir": {"type": "string"},
                },
            },
        },
        {
            "name": "run_engage",
            "description": "Launch Engage with optional arguments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "working_dir": {"type": "string"},
                },
            },
        },
        {
            "name": "run_sensor_plot",
            "description": "Launch Sensor Plot with optional arguments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "working_dir": {"type": "string"},
                },
            },
        },
        {
            "name": "batch_run_mission",
            "description": "Run Mission for multiple scenarios.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenarios": {"type": "array", "items": {"type": "string"}},
                    "working_dir": {"type": "string"},
                },
                "required": ["scenarios"],
            },
        },
        {
            "name": "run_mission_and_open_mystic",
            "description": "Run Mission then open latest AER in Mystic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "working_dir": {"type": "string"},
                    "open_mystic": {"type": "boolean"},
                },
                "required": ["scenario"],
            },
        },
        {
            "name": "open_latest_aer_in_mystic",
            "description": "Open the latest AER file in Mystic.",
            "inputSchema": {
                "type": "object",
                "properties": {"directory": {"type": "string"}},
                "required": ["directory"],
            },
        },
    ]


def router(server):
    return {
        "set_afsim_bin": server.set_afsim_bin,
        "get_afsim_bin": lambda _: server.get_afsim_bin(),
        "run_wizard": server.run_wizard,
        "run_mission": server.run_mission,
        "run_mission_with_args": server.run_mission_with_args,
        "run_warlock": server.run_warlock,
        "run_mystic": server.run_mystic,
        "run_engage": server.run_engage,
        "run_sensor_plot": server.run_sensor_plot,
        "batch_run_mission": server.batch_run_mission,
        "run_mission_and_open_mystic": server.run_mission_and_open_mystic,
        "open_latest_aer_in_mystic": server.open_latest_aer_in_mystic,
    }
