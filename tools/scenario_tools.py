def specs():
    return [
        {
            "name": "create_scenario",
            "description": "Create a new AFSIM scenario container.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "base_template": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        {
            "name": "load_scenario",
            "description": "Load a scenario by id or path.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        },
        {
            "name": "save_scenario",
            "description": "Save scenario to a target path.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["scenario_id", "path"],
            },
        },
        {
            "name": "list_scenarios",
            "description": "List available scenarios.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "set_rule",
            "description": "Attach a rule to a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "rule_type": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["scenario_id", "rule_type", "params"],
            },
        },
        {
            "name": "validate_scenario",
            "description": "Validate scenario completeness.",
            "inputSchema": {
                "type": "object",
                "properties": {"scenario_id": {"type": "string"}},
                "required": ["scenario_id"],
            },
        },
        {
            "name": "read_scenario_text",
            "description": "Read a scenario text file.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "write_scenario_text",
            "description": "Write a scenario text file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["path", "text"],
            },
        },
        {
            "name": "insert_scenario_block",
            "description": "Insert or replace a text block in a scenario file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "anchor": {"type": "string"},
                    "block": {"type": "string"},
                    "position": {
                        "type": "string",
                        "enum": ["before", "after", "replace"],
                    },
                    "occurrence": {"type": "string", "enum": ["first", "last"]},
                },
                "required": ["path", "anchor", "block"],
            },
        },
        {
            "name": "extract_includes",
            "description": "Extract include statements from a scenario text file.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "search_definitions",
            "description": "Search AFSIM definition declarations in text files.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "platform_type",
                            "platform",
                            "weapon",
                            "sensor",
                            "processor",
                            "comm",
                            "router",
                            "aero",
                            "signature",
                            "weapon_effects",
                        ],
                    },
                    "query": {"type": "string"},
                    "roots": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer"},
                },
                "required": ["kind"],
            },
        },
        {
            "name": "list_definition_kinds",
            "description": "List supported AFSIM definition kinds.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "generate_platform_type_template",
            "description": "Generate a platform_type template block.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "base_type": {"type": "string"},
                    "icon": {"type": "string"},
                    "mover_type": {"type": "string"},
                    "body_lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        {
            "name": "generate_platform_instance_template",
            "description": "Generate a platform instance template block.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "platform_type": {"type": "string"},
                    "side": {"type": "string"},
                    "position": {"type": "string"},
                    "altitude": {"type": "string"},
                    "body_lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "platform_type"],
            },
        },
        {
            "name": "generate_sensor_template",
            "description": "Generate a sensor template block.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "sensor_type": {"type": "string"},
                    "body_lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "sensor_type"],
            },
        },
        {
            "name": "generate_weapon_template",
            "description": "Generate a weapon template block.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "weapon_type": {"type": "string"},
                    "body_lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "weapon_type"],
            },
        },
        {
            "name": "list_mover_types",
            "description": "List supported mover types.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "generate_mover_template",
            "description": "Generate a mover template block.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "mover_type": {"type": "string"},
                    "keyword": {"type": "string", "enum": ["mover", "add mover"]},
                    "body_lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["mover_type"],
            },
        },
        {
            "name": "list_project_structure_template",
            "description": "List recommended AFSIM project structure template.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "generate_project_structure_overview",
            "description": "Generate a text overview of a recommended project structure.",
            "inputSchema": {
                "type": "object",
                "properties": {"project_name": {"type": "string"}},
            },
        },
        {
            "name": "init_project_structure",
            "description": "Initialize a standard project folder structure.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "base_dir": {"type": "string"},
                    "project_name": {"type": "string"},
                    "directories": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        {
            "name": "set_paths_config",
            "description": "Set AFSIM and project paths in MCP config.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "afsim_root": {"type": "string"},
                    "project_root": {"type": "string"},
                    "demos_root": {"type": "string"},
                    "afsim_bin": {"type": "string"},
                },
            },
        },
        {
            "name": "get_paths_config",
            "description": "Get MCP config paths and resolved locations.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def router(server):
    return {
        "create_scenario": server.create_scenario,
        "load_scenario": server.load_scenario,
        "save_scenario": server.save_scenario,
        "list_scenarios": lambda _: server.list_scenarios(),
        "set_rule": server.set_rule,
        "validate_scenario": server.validate_scenario,
        "read_scenario_text": server.read_scenario_text,
        "write_scenario_text": server.write_scenario_text,
        "insert_scenario_block": server.insert_scenario_block,
        "extract_includes": server.extract_includes,
        "search_definitions": server.search_definitions,
        "list_definition_kinds": lambda _: server.list_definition_kinds(),
        "generate_platform_type_template": server.generate_platform_type_template,
        "generate_platform_instance_template": server.generate_platform_instance_template,
        "generate_sensor_template": server.generate_sensor_template,
        "generate_weapon_template": server.generate_weapon_template,
        "list_mover_types": lambda _: server.list_mover_types(),
        "generate_mover_template": server.generate_mover_template,
        "list_project_structure_template": lambda _: server.list_project_structure_template(),
        "generate_project_structure_overview": server.generate_project_structure_overview,
        "init_project_structure": server.init_project_structure,
        "set_paths_config": server.set_paths_config,
        "get_paths_config": server.get_paths_config,
    }
