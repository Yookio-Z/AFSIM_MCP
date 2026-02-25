from . import backend_tools
from . import demo_tools
from . import entity_tools
from . import scenario_tools
from . import simulation_tools


def build_tool_specs():
    return (
        scenario_tools.specs()
        + entity_tools.specs()
        + simulation_tools.specs()
        + backend_tools.specs()
        + demo_tools.specs()
    )


def build_tool_router(server):
    router = {}
    router.update(scenario_tools.router(server))
    router.update(entity_tools.router(server))
    router.update(simulation_tools.router(server))
    router.update(backend_tools.router(server))
    router.update(demo_tools.router(server))
    return router
