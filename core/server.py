import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# 标准 AFSIM 项目目录结构 —— 每次写出场景文件时强制创建
STANDARD_PROJECT_DIRS = [
    "doc",
    "output",
    "platforms",
    "processors",
    "scenarios",
    "sensors",
    "weapons",
]

try:
    from ..tools import build_tool_router, build_tool_specs
    from .analysis import AnalysisService
    from .assets import AssetService
    from .generation import GenerationService
    from .planning import PlanningService
    from .results import ResultsService
    from .runtime import RuntimeService
    from .scenario_ops import ScenarioOpsService
    from .showcase import ShowcaseService
except ImportError:
    from tools import build_tool_router, build_tool_specs
    from core.analysis import AnalysisService
    from core.assets import AssetService
    from core.generation import GenerationService
    from core.planning import PlanningService
    from core.results import ResultsService
    from core.runtime import RuntimeService
    from core.scenario_ops import ScenarioOpsService
    from core.showcase import ShowcaseService


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data=None):
        super().__init__(message)
        self.code = int(code)
        self.message = str(message)
        self.data = data

    def to_error_obj(self):
        obj = {"code": self.code, "message": self.message}
        if self.data is not None:
            obj["data"] = self.data
        return obj


class MCPServer:
    JsonRpcError = JsonRpcError
    STANDARD_PROJECT_DIRS = STANDARD_PROJECT_DIRS

    def __init__(self):
        self.base_dir = self.resolve_base_dir()
        self.config_dir = self.resolve_config_dir()
        self.config_path = self.config_dir / "config.json"
        self.state_dir = self.resolve_state_dir()
        self.scenarios_dir = self.state_dir / "scenarios"
        self.runs_dir = self.state_dir / "runs"
        self.results_dir = self.state_dir / "results"
        self.processes_dir = self.state_dir / "processes"
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.processes_dir.mkdir(parents=True, exist_ok=True)

        self._tool_specs = build_tool_specs()
        self._tool_router = build_tool_router(self)
        self._processes = {}
        self.analysis_service = AnalysisService(self)
        self.asset_service = AssetService(self)
        self.generation_service = GenerationService(self)
        self.planning_service = PlanningService(self)
        self.results_service = ResultsService(self)
        self.runtime_service = RuntimeService(self)
        self.scenario_ops_service = ScenarioOpsService(self)
        self.showcase_service = ShowcaseService(self)

    def resolve_base_dir(self):
        env_dir = os.environ.get("AFSIM_MCP_BASE_DIR")
        if env_dir:
            return Path(env_dir)
        file_path = Path(__file__).resolve()
        if len(file_path.parents) > 3 and file_path.parents[2].name == "src":
            return file_path.parents[3]
        return file_path.parents[1]

    def resolve_config_dir(self):
        env_dir = os.environ.get("AFSIM_MCP_CONFIG_DIR")
        if env_dir:
            return Path(env_dir)
        legacy_dir = os.environ.get("AFSIM_MCP_STATE_DIR")
        if legacy_dir:
            return Path(legacy_dir)
        return Path.home() / ".afsim_mcp"

    def resolve_state_dir(self):
        env_dir = os.environ.get("AFSIM_MCP_STATE_DIR")
        if env_dir:
            return Path(env_dir)
        config = self.read_config()
        cfg_state = config.get("state_dir")
        if cfg_state and Path(cfg_state).exists():
            return Path(cfg_state)
        env_project = os.environ.get("AFSIM_PROJECT_ROOT")
        if env_project and Path(env_project).exists():
            return Path(env_project) / "mcp_state"
        cfg_root = config.get("project_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root) / "mcp_state"
        return self.config_dir / "state"

    def resolve_afsim_root(self):
        env_root = os.environ.get("AFSIM_ROOT")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("afsim_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        if self.base_dir.parent.exists():
            return self.base_dir.parent
        return None

    def resolve_project_root(self):
        env_root = os.environ.get("AFSIM_PROJECT_ROOT")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("project_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        afsim_root = self.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "project"
            if candidate.exists():
                return candidate
            return afsim_root
        return None

    def resolve_demos_root(self):
        env_root = os.environ.get("AFSIM_DEMOS_DIR")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("demos_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        afsim_root = self.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "demos"
            if candidate.exists():
                return candidate
        return None

    def tools_list(self):
        return self._tool_specs

    def handle_request(self, request):
        if not isinstance(request, dict):
            raise JsonRpcError(-32600, "Invalid Request", {"reason": "request must be an object"})
        method = request.get("method")
        if not method:
            raise JsonRpcError(-32600, "Invalid Request", {"reason": "missing method"})
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "afsim-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        if method == "tools/list":
            return {"tools": self.tools_list()}
        if method == "tools/call":
            params = request.get("params")
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise JsonRpcError(-32602, "Invalid params", {"reason": "params must be an object"})
            name = params.get("name")
            if not name or not isinstance(name, str):
                raise JsonRpcError(-32602, "Invalid params", {"reason": "params.name must be a string"})
            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                raise JsonRpcError(-32602, "Invalid params", {"reason": "params.arguments must be an object"})
            return self.call_tool(name, arguments)
        raise JsonRpcError(-32601, f"Unsupported method: {method}")

    def call_tool(self, name, arguments):
        handler = self._tool_router.get(name)
        if handler:
            try:
                return handler(arguments)
            except JsonRpcError:
                raise
            except Exception as exc:
                raise JsonRpcError(-32000, "Tool execution failed", {"tool": name, "error": str(exc)})
        raise JsonRpcError(-32601, f"Unknown tool: {name}")

    def create_scenario(self, args):
        scenario_id = str(uuid.uuid4())
        name = args.get("name")
        if not name:
            return self.wrap({"error": "name is required"})
        scenario = {
            "id": scenario_id,
            "name": name,
            "template": args.get("base_template"),
            "entities": [],
            "rules": [],
            "metadata": {"created_at": self.now()},
        }
        self.write_json(self.scenario_path(scenario_id), scenario)
        return self.wrap({"scenario_id": scenario_id, "path": str(self.scenario_path(scenario_id))})

    def list_scenarios(self):
        items = []
        for path in sorted(self.scenarios_dir.glob("*.json")):
            data = self.read_json(path)
            items.append({"id": data.get("id"), "name": data.get("name"), "path": str(path)})
        return self.wrap({"scenarios": items})

    def load_scenario(self, args):
        path = args.get("path")
        scenario_id = args.get("scenario_id")
        if path:
            return self.wrap(self.read_json(Path(path)))
        if scenario_id:
            return self.wrap(self.read_json(self.scenario_path(scenario_id)))
        return self.wrap({"error": "path or scenario_id required"})

    def save_scenario(self, args):
        scenario_id = args.get("scenario_id")
        path = args.get("path")
        scenario = self.read_json(self.scenario_path(scenario_id))
        target = Path(path)
        self.write_json(target, scenario)
        return self.wrap({"path": str(target)})

    def create_entity(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        entity_id = str(uuid.uuid4())
        entity = {
            "id": entity_id,
            "type": args["type"],
            "name": args["name"],
            "components": [],
            "metadata": {},
        }
        scenario["entities"].append(entity)
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"entity_id": entity_id})

    def delete_entity(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        before = len(scenario["entities"])
        scenario["entities"] = [e for e in scenario["entities"] if e["id"] != args["entity_id"]]
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"removed": before - len(scenario["entities"])})

    def set_entity_param(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        updated = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                params = args.get("params") or {}
                entity["metadata"].update(params)
                updated = True
                break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"updated": updated})

    def add_component(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        component_id = str(uuid.uuid4())
        created = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                entity["components"].append(
                    {
                        "id": component_id,
                        "type": args["component_type"],
                        "params": args.get("params") or {},
                    }
                )
                created = True
                break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"component_id": component_id, "created": created})

    def update_component(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        updated = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                for component in entity["components"]:
                    if component["id"] == args["component_id"]:
                        component["params"] = args.get("params") or {}
                        updated = True
                        break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"updated": updated})

    def set_rule(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        rule = {"type": args["rule_type"], "params": args.get("params") or {}}
        scenario["rules"].append(rule)
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"rules": len(scenario["rules"])})

    def validate_scenario(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        issues = []
        if not scenario["entities"]:
            issues.append("entities is empty")
        valid = len(issues) == 0
        return self.wrap({"valid": valid, "issues": issues})

    def read_scenario_text(self, args):
        path = Path(self.require_str(args, "path"))
        self.assert_path_allowed(path, write=False, purpose="read_scenario_text")
        text = self.read_text(path)
        return self.wrap({"path": str(path), "text": text})

    def write_scenario_text(self, args):
        path = Path(self.require_str(args, "path"))
        text = args.get("text") or ""

        # ── 强制场景独立子目录规则 ────────────────────────────────────────────────
        # 规则：场景文件必须位于 <project_root>/<scenario_name>/ 下面
        #   · 入口文件  → <scenario_dir>/<name>.txt
        #   · 定义文件  → <scenario_dir>/scenarios/<name>.txt（或其他子目录）
        # 如果调用者把路径直接写成 <project_root>/<name>.txt，
        # 则自动重定向到 <project_root>/<name>/<name>.txt
        project_root = self.resolve_project_root()
        if project_root:
            pr = Path(project_root).resolve()
            try:
                rel = path.resolve().relative_to(pr)
            except ValueError:
                rel = None
            # 路径直接在 project_root 下（只有一级，即 rel 只含一个部分）
            if rel is not None and len(rel.parts) == 1:
                scenario_name = path.stem
                path = pr / scenario_name / path.name

        self.assert_path_allowed(path, write=True, purpose="write_scenario_text")

        # 确定场景根目录：若文件在 scenarios/ 等子目录内，根目录上一级
        scenario_dir = path.parent
        if scenario_dir.name in ("scenarios", "platforms", "sensors", "weapons",
                                   "processors", "doc", "output"):
            scenario_dir = scenario_dir.parent

        self.assert_path_allowed(scenario_dir, write=True, purpose="write_scenario_text(scenario_dir)")

        # 强制初始化标准目录结构
        structure = self.ensure_project_structure(scenario_dir)
        self.write_text(path, text)
        return self.wrap({
            "path": str(path),
            "scenario_dir": str(scenario_dir),
            "structure_enforced": True,
            "directories": structure,
        })

    def insert_scenario_block(self, args):
        path = Path(self.require_str(args, "path"))
        anchor = self.require_str(args, "anchor", allow_empty=True)
        block = self.require_str(args, "block", allow_empty=True)
        position = args.get("position") or "after"
        occurrence = args.get("occurrence") or "first"
        self.assert_path_allowed(path, write=True, purpose="insert_scenario_block")
        text = self.read_text(path)
        idx = text.find(anchor) if occurrence == "first" else text.rfind(anchor)
        if idx == -1:
            raise JsonRpcError(-32602, "anchor not found", {"path": str(path), "anchor": anchor})
        if position == "before":
            new_text = text[:idx] + block + text[idx:]
        elif position == "replace":
            new_text = text[:idx] + block + text[idx + len(anchor) :]
        else:
            new_text = text[: idx + len(anchor)] + block + text[idx + len(anchor) :]
        self.write_text(path, new_text)
        return self.wrap({"path": str(path), "modified": True})

    def extract_includes(self, args):
        path = Path(self.require_str(args, "path"))
        self.assert_path_allowed(path, write=False, purpose="extract_includes")
        lines = self.read_text(path).splitlines()
        includes = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if stripped.startswith("include") or stripped.startswith("include_once"):
                parts = stripped.split()
                if len(parts) >= 2:
                    includes.append(parts[1])
        return self.wrap({"path": str(path), "includes": includes})

    def search_definitions(self, args):
        kind = self.require_str(args, "kind")
        query = (args.get("query") or "").strip()
        max_results = int(args.get("max_results") or 200)
        roots = args.get("roots")
        default_root = self.resolve_afsim_root()
        if not default_root:
            default_root = self.base_dir.parent
        if roots is not None:
            if not isinstance(roots, list) or not all(isinstance(p, str) for p in roots):
                raise JsonRpcError(-32602, "Invalid params", {"reason": "roots must be an array of strings"})
            search_roots = [Path(p) for p in roots]
        else:
            search_roots = [default_root]

        filtered_roots = []
        for root in search_roots:
            try:
                self.assert_path_allowed(root, write=False, purpose="search_definitions")
            except JsonRpcError:
                continue
            filtered_roots.append(root)
        if roots is not None and not filtered_roots:
            raise JsonRpcError(-32602, "No allowed roots", {"roots": roots})
        search_roots = filtered_roots
        kind_map = {
            "signature": [
                "radar_signature",
                "infrared_signature",
                "visual_signature",
                "acoustic_signature",
                "laser_signature",
                "optical_signature",
                "signal_signature",
            ]
        }
        keys = kind_map.get(kind, [kind])
        results = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob("*.txt"):
                try:
                    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                for idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    for key in keys:
                        if stripped.startswith(f"{key} "):
                            parts = stripped.split()
                            if len(parts) < 2:
                                continue
                            name = parts[1]
                            if query and query not in stripped and query not in name:
                                continue
                            results.append(
                                {
                                    "name": name,
                                    "kind": key,
                                    "file": str(path),
                                    "line": idx,
                                }
                            )
                            if len(results) >= max_results:
                                return self.wrap({"matches": results})
        return self.wrap({"matches": results})

    def list_definition_kinds(self):
        return self.wrap(
            {
                "kinds": [
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
                ]
            }
        )

    def generate_platform_type_template(self, args):
        name = args["name"]
        base_type = args.get("base_type") or "WSF_PLATFORM"
        icon = args.get("icon")
        mover_type = args.get("mover_type")
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"platform_type {name} {base_type}"]
        if icon:
            lines.append(f"   icon {icon}")
        if mover_type:
            lines.append(f"   mover {mover_type}")
            lines.append("   end_mover")
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_platform_type")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_platform_instance_template(self, args):
        name = args["name"]
        platform_type = args["platform_type"]
        side = args.get("side")
        position = args.get("position")
        altitude = args.get("altitude")
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"platform {name} {platform_type}"]
        if side:
            lines.append(f"   side {side}")
        if position:
            if altitude:
                lines.append(f"   position {position} altitude {altitude}")
            else:
                lines.append(f"   position {position}")
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_platform")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_sensor_template(self, args):
        name = args["name"]
        sensor_type = args["sensor_type"]
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"sensor {name} {sensor_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_sensor")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_weapon_template(self, args):
        name = args["name"]
        weapon_type = args["weapon_type"]
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"weapon {name} {weapon_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_weapon")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def list_mover_types(self):
        return self.wrap(
            {
                "mover_types": [
                    "WSF_RIGID_BODY_SIX_DOF_MOVER",
                    "WSF_P6DOF_MOVER",
                    "WSF_GUIDED_MOVER",
                    "WSF_AIR_MOVER",
                    "WSF_GROUND_MOVER",
                    "WSF_NAVAL_MOVER",
                ]
            }
        )

    def generate_mover_template(self, args):
        mover_type = args["mover_type"]
        keyword = args.get("keyword") or "mover"
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"{keyword} {mover_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_mover")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def list_project_structure_template(self):
        return self.scenario_ops_service.list_project_structure_template()

    def generate_project_structure_overview(self, args):
        return self.scenario_ops_service.generate_project_structure_overview(args)

    def init_project_structure(self, args):
        return self.scenario_ops_service.init_project_structure(args)

    def run_simulation(self, args):
        return self.results_service.run_simulation(args)

    def stop_simulation(self, args):
        return self.results_service.stop_simulation(args)

    def get_simulation_status(self, args):
        return self.results_service.get_simulation_status(args)

    def list_results(self, args):
        return self.results_service.list_results(args)

    def export_results(self, args):
        return self.results_service.export_results(args)

    def query_results(self, args):
        return self.results_service.query_results(args)

    def set_afsim_bin(self, args):
        return self.runtime_service.set_afsim_bin(args)

    def get_afsim_bin(self):
        return self.runtime_service.get_afsim_bin()

    def set_paths_config(self, args):
        return self.runtime_service.set_paths_config(args)

    def get_paths_config(self, args):
        return self.runtime_service.get_paths_config(args)

    def run_wizard(self, args):
        return self.runtime_service.run_wizard(args)

    def run_mission(self, args):
        return self.runtime_service.run_mission(args)

    def run_mission_with_args(self, args):
        return self.runtime_service.run_mission_with_args(args)

    def run_warlock(self, args):
        return self.runtime_service.run_warlock(args)

    def run_mystic(self, args):
        return self.runtime_service.run_mystic(args)

    def run_engage(self, args):
        return self.runtime_service.run_engage(args)

    def run_sensor_plot(self, args):
        return self.runtime_service.run_sensor_plot(args)

    def batch_run_mission(self, args):
        return self.runtime_service.batch_run_mission(args)

    def run_mission_and_open_mystic(self, args):
        return self.runtime_service.run_mission_and_open_mystic(args)

    def open_latest_aer_in_mystic(self, args):
        return self.runtime_service.open_latest_aer_in_mystic(args)

    def list_demos(self):
        return self.scenario_ops_service.list_demos()

    def list_demo_scenarios(self, args):
        return self.scenario_ops_service.list_demo_scenarios(args)

    def suggest_scenario_questions(self, args):
        return self.scenario_ops_service.suggest_scenario_questions(args)

    def create_scenario_from_prompt(self, args):
        return self.scenario_ops_service.create_scenario_from_prompt(args)

    def create_operational_scenario_package(self, args):
        return self.scenario_ops_service.create_operational_scenario_package(args)

    def prepare_operational_project_plan(self, args):
        return self.scenario_ops_service.prepare_operational_project_plan(args)

    def create_validated_operational_scenario_package(self, args):
        return self.scenario_ops_service.create_validated_operational_scenario_package(args)

    def refine_operational_prompt(self, args):
        return self.scenario_ops_service.refine_operational_prompt(args)

    def run_demo(self, args):
        return self.scenario_ops_service.run_demo(args)

    def list_output_files(self, args):
        directory = Path(self.require_str(args, "directory"))
        self.assert_path_allowed(directory, write=False, purpose="list_output_files")
        if not directory.exists():
            return self.wrap({"error": "directory not found"})
        extensions = args.get("extensions") or ["aer", "evt", "log"]
        exts = set([e.lower().lstrip(".") for e in extensions])
        files = []
        for path in directory.rglob("*"):
            if path.is_file():
                suffix = path.suffix.lower().lstrip(".")
                if suffix in exts:
                    files.append(
                        {
                            "path": str(path),
                            "size": path.stat().st_size,
                            "mtime": path.stat().st_mtime,
                        }
                    )
        files.sort(key=lambda x: x["mtime"], reverse=True)
        return self.wrap({"files": files})

    def find_latest_aer_tool(self, args):
        directory = Path(self.require_str(args, "directory"))
        self.assert_path_allowed(directory, write=False, purpose="find_latest_aer")
        latest_aer = self.find_latest_aer(directory)
        return self.wrap({"path": str(latest_aer) if latest_aer else None})

    def summarize_evt(self, args):
        return self.analysis_service.summarize_evt(args)

    def tail_text_file(self, args):
        path = Path(self.require_str(args, "path"))
        self.assert_path_allowed(path, write=False, purpose="tail_text_file")
        if not path.exists():
            return self.wrap({"error": "file not found"})
        line_count = int(args.get("lines") or 50)
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        tail = lines[-line_count:] if line_count > 0 else []
        return self.wrap({"path": str(path), "lines": tail})

    def analyze_scenario_outputs(self, args):
        return self.analysis_service.analyze_scenario_outputs(args)

    def build_showcase_package(self, args):
        return self.showcase_service.build_showcase_package(args)

    def scenario_path(self, scenario_id):
        return self.scenarios_dir / f"{scenario_id}.json"

    def run_path(self, run_id):
        return self.runs_dir / f"{run_id}.json"

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")

    def ensure_project_structure(self, project_dir: Path) -> list:
        """强制创建标准 AFSIM 项目目录结构。

        无论用户是否指定，每次向项目目录写出场景文件时均会自动调用。
        标准子目录：doc / output / platforms / processors / scenarios / sensors / weapons
        """
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        created = []
        for name in STANDARD_PROJECT_DIRS:
            sub = project_dir / name
            sub.mkdir(exist_ok=True)
            created.append(str(sub))
        return created

    def read_text(self, path):
        return Path(path).read_text(encoding="utf-8", errors="ignore")

    def normalize_body_lines(self, lines):
        if not lines:
            return []
        normalized = []
        for line in lines:
            if line is None:
                continue
            text = str(line).strip()
            if text == "":
                continue
            normalized.append(text)
        return normalized

    def read_json(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def env_truthy(self, value) -> bool:
        if value is None:
            return False
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def require_str(self, args, key: str, *, allow_empty: bool = False) -> str:
        if not isinstance(args, dict):
            raise JsonRpcError(-32602, "Invalid params", {"reason": "arguments must be an object"})
        if key not in args:
            raise JsonRpcError(-32602, "Invalid params", {"reason": f"missing required field: {key}"})
        value = args.get(key)
        if not isinstance(value, str):
            raise JsonRpcError(-32602, "Invalid params", {"reason": f"{key} must be a string"})
        if not allow_empty and value.strip() == "":
            raise JsonRpcError(-32602, "Invalid params", {"reason": f"{key} must be non-empty"})
        return value

    def require_list_of_str(self, args, key: str) -> list:
        if not isinstance(args, dict):
            raise JsonRpcError(-32602, "Invalid params", {"reason": "arguments must be an object"})
        if key not in args:
            raise JsonRpcError(-32602, "Invalid params", {"reason": f"missing required field: {key}"})
        value = args.get(key)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise JsonRpcError(-32602, "Invalid params", {"reason": f"{key} must be an array of strings"})
        return value

    def safe_resolve(self, path: Path) -> Path:
        try:
            return Path(path).expanduser().resolve(strict=False)
        except Exception:
            return Path(path)

    def get_allowed_roots(self, *, write: bool) -> list[Path]:
        if self.env_truthy(os.environ.get("AFSIM_MCP_ALLOW_ANY_PATH")):
            return []

        roots: list[Path] = []
        roots.append(self.state_dir)

        project_root = self.resolve_project_root()
        if project_root:
            roots.append(project_root)

        demos_root = self.resolve_demos_root()
        if demos_root:
            roots.append(demos_root)

        if not write:
            afsim_root = self.resolve_afsim_root()
            if afsim_root:
                roots.append(afsim_root)

        extra = os.environ.get("AFSIM_MCP_EXTRA_PATHS")
        if extra:
            for raw in str(extra).split(";"):
                raw = raw.strip()
                if not raw:
                    continue
                p = Path(raw)
                if p.exists():
                    roots.append(p)

        unique: list[Path] = []
        seen = set()
        for r in roots:
            rr = str(self.safe_resolve(r))
            if rr not in seen:
                unique.append(Path(rr))
                seen.add(rr)
        return unique

    def assert_path_allowed(self, path: Path, *, write: bool, purpose: str):
        if self.env_truthy(os.environ.get("AFSIM_MCP_ALLOW_ANY_PATH")):
            return

        resolved = self.safe_resolve(path)
        roots = self.get_allowed_roots(write=write)
        for root in roots:
            root_resolved = self.safe_resolve(root)
            try:
                if resolved.is_relative_to(root_resolved):
                    return
            except Exception:
                try:
                    resolved.relative_to(root_resolved)
                    return
                except Exception:
                    pass
        raise JsonRpcError(
            -32602,
            "Path not allowed",
            {
                "purpose": purpose,
                "path": str(path),
                "write": write,
                "allowed_roots": [str(r) for r in roots],
                "hint": "Set AFSIM_MCP_ALLOW_ANY_PATH=1 to disable path restrictions (not recommended).",
            },
        )

    def wrap(self, payload):
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}

    def truncate_text(self, text: str, max_chars: int) -> str:
        if text is None:
            return ""
        if max_chars is None or max_chars <= 0:
            return text
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...<truncated>\n"

    def start_background_process(self, cmd, working_dir, *, env=None):
        return self.runtime_service.start_background_process(cmd, working_dir, env=env)

    def get_process_status(self, args):
        return self.runtime_service.get_process_status(args)

    def stop_process(self, args):
        return self.runtime_service.stop_process(args)

    def run_process(self, cmd, working_dir, *, timeout_sec=None, max_output_chars=20000, background=False, env=None):
        return self.runtime_service.run_process(cmd, working_dir, timeout_sec=timeout_sec, max_output_chars=max_output_chars, background=background, env=env)

    def resolve_exe(self, base_name):
        return self.runtime_service.resolve_exe(base_name)

    def resolve_bin_path(self):
        return self.runtime_service.resolve_bin_path()

    def get_demos_root(self):
        return self.runtime_service.get_demos_root()

    def get_observer_block(self):
        """Return the standard Brawler observer script_variables block.

        log_print and iout_print default to false so LOG.N / IOUT.N files
        are NOT generated. Paste into the entry-point scenario file.
        """
        text = self.build_observer_block_text()
        return self.wrap({"text": text})

    def build_observer_block_text(self) -> str:
        return (
            "$define REP 1\n"
            "\n"
            "script_variables\n"
            "   double closest_hostile = 1000*MATH.M_PER_NM();\n"
            "   bool log_print    = false;  // set true to generate LOG output\n"
            "   bool iout_print   = false;  // set true to generate IOUT output\n"
            "   bool sensor_print = false;\n"
            "   WsfGeoPoint origin = WsfGeoPoint.Construct(\"00:00:00.00n 00:00:00.00e\");\n"
            "   int rseed = (int)WsfSimulation.RandomSeed();\n"
            "   Array<string> log_string    = {\"output/\",\"LOG\",\".\",(string)$<REP>$};\n"
            "   Array<string> iout_string   = {\"output/\",\"IOUT\",\".\",(string)$<REP>$};\n"
            "   Array<string> sensor_string = {\"output/\",\"SENSOR\",\".\",(string)$<REP>$};\n"
            "   string log_path    = \"\".Join(log_string);\n"
            "   string iout_path   = \"\".Join(iout_string);\n"
            "   string sensor_path = \"\".Join(sensor_string);\n"
            "   FileIO log      = FileIO();\n"
            "   FileIO iout     = FileIO();\n"
            "   FileIO sensorIO = FileIO();\n"
            "end_script_variables\n"
            "\n"
            "include_once observer.txt\n"
            "include_once sensor_observer.txt\n"
        )

    def generate_basic_scenario_entities_text(
        self, aircraft_count, tank_count, side, center_lat, center_lon
    ):
        return self.scenario_ops_service.generate_basic_scenario_entities_text(aircraft_count, tank_count, side, center_lat, center_lon)

    def generate_basic_entrypoint_text(self, scenario_name: str, duration_min: float) -> str:
        return self.scenario_ops_service.generate_basic_entrypoint_text(scenario_name, duration_min)

    def format_lat_lon(self, lat, lon):
        lat_suffix = "n" if lat >= 0 else "s"
        lon_suffix = "e" if lon >= 0 else "w"
        return f"{abs(lat):.3f}{lat_suffix} {abs(lon):.3f}{lon_suffix}"

    def parse_prompt_counts(self, prompt):
        return self.scenario_ops_service.parse_prompt_counts(prompt)

    def extract_count(self, text, keywords):
        return self.scenario_ops_service.extract_count(text, keywords)

    def find_nearest_number(self, text, key):
        return self.scenario_ops_service.find_nearest_number(text, key)

    def find_latest_aer(self, base_dir):
        return self.runtime_service.find_latest_aer(base_dir)

    def find_latest_matching_file(self, base_dir, pattern):
        if not base_dir:
            return None
        base_dir = Path(base_dir)
        if not base_dir.exists():
            return None
        candidates = list(base_dir.rglob(pattern))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def resolve_scenario_output_paths(self, output_path, project_dir=None):
        return self.scenario_ops_service.resolve_scenario_output_paths(output_path, project_dir=project_dir)

    def build_operational_model(self, args, scenario_name, prompt, refinement=None):
        raw_model = args.get("operational_model") or {}
        if raw_model and not isinstance(raw_model, dict):
            raise JsonRpcError(-32602, "Invalid params", {"reason": "operational_model must be an object"})
        return self.planning_service.build_operational_model(args, scenario_name, prompt, refinement=refinement)

    def refine_operational_prompt_payload(self, args, scenario_name, prompt):
        return self.planning_service.refine_operational_prompt_payload(args, scenario_name, prompt)

    def classify_operational_prompt(self, prompt):
        return self.planning_service.classify_operational_prompt(prompt)

    def default_operational_summary(self, scenario_kind):
        return self.planning_service.default_operational_summary(scenario_kind)

    def infer_mission_title(self, prompt, scenario_name, scenario_kind):
        return self.planning_service.infer_mission_title(prompt, scenario_name, scenario_kind)

    def infer_mission_summary(self, prompt, scenario_kind, replay_focus):
        return self.planning_service.infer_mission_summary(prompt, scenario_kind, replay_focus)

    def infer_operational_objectives(self, prompt, scenario_kind, desired_kpis):
        return self.planning_service.infer_operational_objectives(prompt, scenario_kind, desired_kpis)

    def default_operational_objectives(self, scenario_kind):
        return self.planning_service.default_operational_objectives(scenario_kind)

    def default_operational_phases(self, scenario_kind, duration_min):
        return self.planning_service.default_operational_phases(scenario_kind, duration_min)

    def default_engagement_rules(self, scenario_kind):
        return self.planning_service.default_engagement_rules(scenario_kind)

    def normalize_force_packages(self, raw_forces, scenario_kind):
        return self.planning_service.normalize_force_packages(raw_forces, scenario_kind)

    def default_force_packages(self, scenario_kind):
        return self.planning_service.default_force_packages(scenario_kind)

    def infer_duration_from_prompt(self, prompt, fallback):
        return self.planning_service.infer_duration_from_prompt(prompt, fallback)

    def infer_center_from_prompt(self, prompt, fallback_center):
        return self.planning_service.infer_center_from_prompt(prompt, fallback_center)

    def describe_theater(self, center):
        return self.planning_service.describe_theater(center)

    def infer_replay_focus(self, prompt, scenario_kind):
        return self.planning_service.infer_replay_focus(prompt, scenario_kind)

    def infer_desired_kpis(self, prompt, scenario_kind):
        return self.planning_service.infer_desired_kpis(prompt, scenario_kind)

    def infer_force_packages_from_prompt(self, prompt, scenario_kind):
        return self.planning_service.infer_force_packages_from_prompt(prompt, scenario_kind)

    def summarize_force_guidance(self, forces):
        return self.planning_service.summarize_force_guidance(forces)

    def collect_prompt_assumptions(self, prompt, raw_model, center, duration_min):
        return self.planning_service.collect_prompt_assumptions(prompt, raw_model, center, duration_min)

    def identify_system_filled_fields(self, prompt, raw_model):
        return self.planning_service.identify_system_filled_fields(prompt, raw_model)

    def assess_refinement_confidence(self, prompt, raw_model, replay_focus, desired_kpis, filled_by_system):
        return self.planning_service.assess_refinement_confidence(prompt, raw_model, replay_focus, desired_kpis, filled_by_system)

    def build_questions_needed(self, scenario_kind, low_confidence, filled_by_system):
        return self.planning_service.build_questions_needed(scenario_kind, low_confidence, filled_by_system)

    def render_prompt_refinement_markdown(self, refinement):
        return self.planning_service.render_prompt_refinement_markdown(refinement)

    def render_project_settings_plan_markdown(self, model, refinement=None):
        return self.planning_service.render_project_settings_plan_markdown(model, refinement=refinement)

    def extract_project_model_from_plan_text(self, text):
        return self.planning_service.extract_project_model_from_plan_text(text)

    def extract_prompt_from_project_brief_text(self, text):
        return self.planning_service.extract_prompt_from_project_brief_text(text)

    def default_icon_for_category(self, category):
        return self.asset_service.default_icon_for_category(category)

    def resolve_operational_asset_profile(self, scenario_kind):
        return self.asset_service.resolve_operational_asset_profile(scenario_kind)

    def render_operational_entrypoint_text(self, model):
        return self.generation_service.render_operational_entrypoint_text(model)

    def render_operational_scenario_text(self, model):
        return self.generation_service.render_operational_scenario_text(model)

    def render_operational_scenario_text_with_assets(self, model):
        return self.generation_service.render_operational_scenario_text_with_assets(model)

    def render_route_block(self, route_name, points):
        return self.generation_service.render_route_block(route_name, points)

    def render_fighter_platform_block(self, name, fighter_type, side, route_name, start_point, *, role, enemy_type, friendly_type, flight_id, id_flag, weapons):
        return self.generation_service.render_fighter_platform_block(name, fighter_type, side, route_name, start_point, role=role, enemy_type=enemy_type, friendly_type=friendly_type, flight_id=flight_id, id_flag=id_flag, weapons=weapons)

    def render_blue_air_defense_block(self, name, anchor, asset_profile):
        return self.generation_service.render_blue_air_defense_block(name, anchor, asset_profile)

    def render_ballistic_launcher_block(self, name, side, unit_index, target, points, asset_profile, launch_time_sec=None):
        return self.generation_service.render_ballistic_launcher_block(name, side, unit_index, target, points, asset_profile, launch_time_sec=launch_time_sec)

    def default_weapons_for_role(self, role):
        return self.asset_service.default_weapons_for_role(role)

    def risk_weapon_for_role(self, role):
        return self.asset_service.risk_weapon_for_role(role)

    def commit_range_for_role(self, role):
        return self.asset_service.commit_range_for_role(role)

    def select_preferred_target(self, objectives, preferred_side):
        return self.asset_service.select_preferred_target(objectives, preferred_side)

    def build_package_points(self, side, category, package_index, unit_index, center, route_style=None, fallback_route_style=None):
        return self.generation_service.build_package_points(side, category, package_index, unit_index, center, route_style=route_style, fallback_route_style=fallback_route_style)

    def slugify(self, text):
        return self.generation_service.slugify(text)

    def render_operational_briefing(self, model):
        return self.generation_service.render_operational_briefing(model)

    def render_operational_phases_markdown(self, model):
        return self.generation_service.render_operational_phases_markdown(model)

    def parse_evt_records(self, evt_path):
        return self.analysis_service.parse_evt_records(evt_path)

    def parse_evt_payload_fields(self, payload):
        return self.analysis_service.parse_evt_payload_fields(payload)

    def build_output_analysis(self, records, *, scenario_dir=None, evt_path=None, sensor_path=None, aer_path=None):
        return self.analysis_service.build_output_analysis(records, scenario_dir=scenario_dir, evt_path=evt_path, sensor_path=sensor_path, aer_path=aer_path)

    def event_to_timeline_item(self, record):
        return self.analysis_service.event_to_timeline_item(record)

    def build_recommended_keyframes(self, timeline, chains, aer_path):
        return self.analysis_service.build_recommended_keyframes(timeline, chains, aer_path)

    def load_operational_model_for_scenario(self, scenario_dir):
        return self.analysis_service.load_operational_model_for_scenario(scenario_dir)

    def build_kpi_summary(self, model, first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, broken_platforms, objective_inventory_by_side, losses, chains, timeline):
        return self.analysis_service.build_kpi_summary(model, first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, broken_platforms, objective_inventory_by_side, losses, chains, timeline)

    def compute_objective_survival(self, model, broken_platforms):
        return self.analysis_service.compute_objective_survival(model, broken_platforms)

    def compute_event_objective_survival(self, objective_inventory_by_side, broken_platforms):
        return self.analysis_service.compute_event_objective_survival(objective_inventory_by_side, broken_platforms)

    def compute_kill_chain_closure(self, first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, chains, timeline):
        return self.analysis_service.compute_kill_chain_closure(first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, chains, timeline)

    def update_first_event_time(self, store, side, value):
        return self.analysis_service.update_first_event_time(store, side, value)

    def opposing_side(self, side):
        return self.analysis_service.opposing_side(side)

    def format_optional_time(self, seconds):
        return self.analysis_service.format_optional_time(seconds)

    def infer_side(self, name):
        return self.analysis_service.infer_side(name)

    def looks_like_weapon(self, name):
        return self.analysis_service.looks_like_weapon(name)

    def classify_loss_bucket(self, platform_type, platform_name):
        return self.analysis_service.classify_loss_bucket(platform_type, platform_name)

    def is_objective_platform(self, platform_type, platform_name):
        return self.analysis_service.is_objective_platform(platform_type, platform_name)

    def render_analysis_markdown(self, analysis):
        return self.analysis_service.render_analysis_markdown(analysis)

    def render_showcase_briefing(self, title, model, analysis, scenario_dir, refinement=None):
        return self.showcase_service.render_showcase_briefing(title, model, analysis, scenario_dir, refinement)

    def render_showcase_replay_plan(self, title, model, analysis, scenario_dir, refinement=None):
        return self.showcase_service.render_showcase_replay_plan(title, model, analysis, scenario_dir, refinement)

    def prioritize_replay_keyframes(self, analysis, refinement=None):
        return self.showcase_service.prioritize_replay_keyframes(analysis, refinement)

    def find_kpi_candidate_keyframe(self, kpi, keyframes, timeline):
        return self.showcase_service.find_kpi_candidate_keyframe(kpi, keyframes, timeline)

    def synthetic_kpi_keyframe(self, kpi, timeline):
        return self.showcase_service.synthetic_kpi_keyframe(kpi, timeline)

    def find_first_timeline_time(self, timeline, tokens):
        return self.showcase_service.find_first_timeline_time(timeline, tokens)

    def keyframe_matches_kpi(self, keyframe, kpi):
        return self.showcase_service.keyframe_matches_kpi(keyframe, kpi)

    def timeline_item_to_keyframe(self, item):
        return self.showcase_service.timeline_item_to_keyframe(item)

    def render_showcase_speaker_notes(self, title, model, analysis, refinement=None):
        return self.showcase_service.render_showcase_speaker_notes(title, model, analysis, refinement)

    def format_time_label(self, seconds):
        total_seconds = int(float(seconds or 0))
        minutes = total_seconds // 60
        remain = total_seconds % 60
        return f"{minutes:02d}:{remain:02d}"

    def read_config(self):
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def write_config(self, data):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def resolve_wizard_path(self):
        return self.runtime_service.resolve_wizard_path()

    def get_runs(self, scenario_id):
        return self.results_service.get_runs(scenario_id)

    def get_run_records(self, scenario_id):
        return self.results_service.get_run_records(scenario_id)
