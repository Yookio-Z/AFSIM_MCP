def specs():
    return [
        {
            "name": "create_entity",
            "description": "Create an entity in a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["scenario_id", "type", "name"],
            },
        },
        {
            "name": "delete_entity",
            "description": "Delete an entity from a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                },
                "required": ["scenario_id", "entity_id"],
            },
        },
        {
            "name": "set_entity_param",
            "description": "Update entity parameters in a scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["scenario_id", "entity_id", "params"],
            },
        },
        {
            "name": "add_component",
            "description": "Add a component to an entity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "component_type": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["scenario_id", "entity_id", "component_type"],
            },
        },
        {
            "name": "update_component",
            "description": "Update a component on an entity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "component_id": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["scenario_id", "entity_id", "component_id", "params"],
            },
        },
    ]


def router(server):
    return {
        "create_entity": server.create_entity,
        "delete_entity": server.delete_entity,
        "set_entity_param": server.set_entity_param,
        "add_component": server.add_component,
        "update_component": server.update_component,
    }
