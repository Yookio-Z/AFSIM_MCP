import json
import re
from pathlib import Path


class ScenarioOpsService:
    def __init__(self, host):
        self.host = host

    def list_project_structure_template(self):
        return self.host.wrap(
            {
                "directories": [
                    {"name": "doc", "description": "文档、说明与参考资料"},
                    {"name": "output", "description": "运行时输出日志、事件与 AER 文件（勿手动编辑）"},
                    {"name": "platforms", "description": "平台与平台类型定义（platform_type）"},
                    {"name": "processors", "description": "处理器与脚本定义"},
                    {"name": "scenarios", "description": "场景平台实例 + 航路定义（被入口文件 include）"},
                    {"name": "sensors", "description": "传感器定义"},
                    {"name": "weapons", "description": "武器定义"},
                ],
                "entry_file_convention": (
                    "<scenario_name>.txt 放在场景根目录（file_path/event_pipe/end_time），"
                    "平台实例文件放在 scenarios/<scenario_name>.txt，"
                    "与官方 air_to_air demo 结构一致"
                ),
                "notes": [
                    "每个场景拥有独立的具名子目录 <project_root>/<scenario_name>/",
                    "write_scenario_text / create_scenario_from_prompt 会自动强制此结构",
                    "入口文件用 file_path . 使所有相对路径从该目录解析",
                ],
            }
        )

    def generate_project_structure_overview(self, args):
        project_name = args.get("project_name") or "scenarioName"
        lines = [
            f"<project_root>/{project_name}/          ← 场景独立根目录",
            f"  {project_name}.txt                    ← 入口文件（file_path/event_pipe/end_time）",
            f"  doc/                                  ← 文档",
            f"  output/                               ← 仿真输出 (.aer/.evt/.log)",
            f"  platforms/                            ← platform_type 定义",
            f"  processors/                           ← 处理器脚本",
            f"  scenarios/",
            f"    {project_name}.txt                  ← 平台实例 + 航路（被入口 include）",
            f"  sensors/                              ← 传感器定义",
            f"  weapons/                              ← 武器定义",
        ]
        return self.host.wrap({"text": "\n".join(lines) + "\n"})

    def init_project_structure(self, args):
        base_dir = args.get("base_dir")
        if not base_dir:
            root = self.host.resolve_project_root()
            if root:
                base_dir = str(root)
        if not base_dir:
            return self.host.wrap({"error": "base_dir is required"})
        project_name = args.get("project_name")
        target = Path(base_dir)
        if project_name:
            target = target / project_name
        target.mkdir(parents=True, exist_ok=True)
        directories = args.get("directories")
        if directories is None:
            directories = list(self.host.STANDARD_PROJECT_DIRS)
        created = []
        for name in directories:
            if not name:
                continue
            path = target / name
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
        return self.host.wrap({"project_dir": str(target), "directories": created})

    def list_demos(self):
        demos = self.host.get_demos_root()
        if not demos:
            return self.host.wrap({"error": "demos folder not found"})
        folders = sorted([path.name for path in demos.iterdir() if path.is_dir()])
        return self.host.wrap({"demos": folders})

    def list_demo_scenarios(self, args):
        demos = self.host.get_demos_root()
        if not demos:
            return self.host.wrap({"error": "demos folder not found"})
        demo = args.get("demo")
        if not demo:
            return self.host.wrap({"error": "demo is required"})
        base = demos / demo
        if not base.exists():
            return self.host.wrap({"error": "demo not found"})
        self.host.assert_path_allowed(base, write=False, purpose="list_demo_scenarios")
        scenarios = sorted([str(path) for path in base.rglob("*.txt")])
        return self.host.wrap({"scenarios": scenarios})

    def suggest_scenario_questions(self, args):
        prompt = args.get("prompt") or ""
        counts = self.parse_prompt_counts(prompt)
        defaults = {
            "aircraft_count": counts.get("aircraft", 2),
            "tank_count": counts.get("tank", 2),
            "side": "blue",
            "duration_min": 30,
            "center": {"lat": 21.325, "lon": -158.51},
        }
        questions = [
            {"key": "scenario_name", "question": "场景名称是什么？"},
            {"key": "mission_goal", "question": "作战目标是什么？"},
            {"key": "area_center", "question": "作战区域中心坐标（纬度/经度）是多少？"},
            {"key": "aircraft_type", "question": "飞机平台类型/型号是什么？"},
            {"key": "tank_type", "question": "坦克平台类型/型号是什么？"},
            {"key": "duration_min", "question": "仿真时长是多少分钟？"},
            {"key": "sides", "question": "各平台所属阵营？"},
        ]
        return self.host.wrap({"defaults": defaults, "questions": questions})

    def create_scenario_from_prompt(self, args):
        prompt = args.get("prompt") or ""
        output_path = self.host.require_str(args, "output_path")
        entry_path, scenario_root, scenario_file_path, _scenario_name = self.resolve_scenario_output_paths(
            output_path,
            args.get("project_dir"),
        )

        self.host.assert_path_allowed(entry_path, write=True, purpose="create_scenario_from_prompt(entry)")
        self.host.assert_path_allowed(scenario_file_path, write=True, purpose="create_scenario_from_prompt(scenarios)")
        self.host.ensure_project_structure(scenario_root)

        counts = self.parse_prompt_counts(prompt)
        aircraft_count = int(args.get("aircraft_count") or counts.get("aircraft") or 3)
        tank_count = int(args.get("tank_count") or counts.get("tank") or 3)
        side = args.get("side") or "blue"
        duration_min = float(args.get("duration_min") or 30)
        center = args.get("center") or {}
        lat = float(center.get("lat") or 21.325)
        lon = float(center.get("lon") or -158.51)

        scenarios_text = self.generate_basic_scenario_entities_text(
            aircraft_count=aircraft_count,
            tank_count=tank_count,
            side=side,
            center_lat=lat,
            center_lon=lon,
        )
        entry_text = self.generate_basic_entrypoint_text(scenario_name=entry_path.stem, duration_min=duration_min)
        self.host.write_text(scenario_file_path, scenarios_text)
        self.host.write_text(entry_path, entry_text)
        return self.host.wrap(
            {
                "path": str(entry_path),
                "entry_path": str(entry_path),
                "scenario_path": str(scenario_file_path),
                "scenario_dir": str(scenario_root),
                "aircraft_count": aircraft_count,
                "tank_count": tank_count,
                "side": side,
                "duration_min": duration_min,
            }
        )

    def create_operational_scenario_package(self, args):
        output_path = self.host.require_str(args, "output_path")
        prompt = str(args.get("prompt") or "")
        entry_path, scenario_root, scenario_file_path, scenario_name = self.resolve_scenario_output_paths(
            output_path,
            args.get("project_dir"),
        )

        self.host.assert_path_allowed(entry_path, write=True, purpose="create_operational_scenario_package(entry)")
        self.host.assert_path_allowed(scenario_file_path, write=True, purpose="create_operational_scenario_package(scenarios)")
        self.host.ensure_project_structure(scenario_root)

        effective_args = dict(args)
        project_brief_path_arg = effective_args.get("project_brief_path") or effective_args.get("project_plan_path")
        if project_brief_path_arg:
            brief_path = Path(project_brief_path_arg)
            self.host.assert_path_allowed(brief_path, write=False, purpose="create_operational_scenario_package(project_brief)")
            if brief_path.exists():
                brief_text = self.host.read_text(brief_path)
                extracted_prompt = self.host.extract_prompt_from_project_brief_text(brief_text)
                if extracted_prompt and not prompt:
                    prompt = extracted_prompt
                elif not extracted_prompt:
                    extracted_model = self.host.extract_project_model_from_plan_text(brief_text)
                    if extracted_model:
                        effective_args["operational_model"] = extracted_model
                        if not prompt:
                            prompt = str((extracted_model.get("mission") or {}).get("summary") or "")

        refinement = None
        if effective_args.get("refine_prompt", True):
            refinement = self.host.refine_operational_prompt_payload(effective_args, scenario_name, prompt)

        model = self.host.build_operational_model(effective_args, scenario_name, prompt, refinement=refinement)
        if bool(effective_args.get("force_generated_assets", False)):
            model["asset_profile"] = self.generated_asset_profile()
        asset_manifest = self.prepare_asset_profile_for_output(scenario_root, model)
        project_brief_text = self.host.render_project_settings_plan_markdown(model, refinement=refinement)
        entry_text = self.host.render_operational_entrypoint_text(model)
        scenario_text = self.host.render_operational_scenario_text(model)
        briefing_text = self.host.render_operational_briefing(model)
        phases_text = self.host.render_operational_phases_markdown(model)
        prompt_brief_text = self.host.render_prompt_refinement_markdown(refinement) if refinement else None

        model_path = scenario_root / "doc" / f"{scenario_name}.model.json"
        briefing_path = scenario_root / "doc" / "SCENARIO.md"
        phases_path = scenario_root / "doc" / "PHASES.md"
        prompt_brief_path = scenario_root / "doc" / "PROMPT_BRIEF.md"
        project_brief_path = scenario_root / "doc" / "PROJECT_BRIEF.md"
        project_plan_legacy_path = scenario_root / "doc" / "PROJECT_PLAN.md"
        asset_manifest_path = scenario_root / "doc" / "ASSET_MANIFEST.json"

        self.host.write_text(entry_path, entry_text)
        self.host.write_text(scenario_file_path, scenario_text)
        self.host.write_json(model_path, model)
        self.host.write_text(briefing_path, briefing_text)
        self.host.write_text(phases_path, phases_text)
        generate_project_brief = bool(effective_args.get("generate_project_brief", effective_args.get("generate_project_plan", True)))
        if generate_project_brief:
            self.host.write_text(project_brief_path, project_brief_text)
            self.host.write_text(project_plan_legacy_path, project_brief_text)
        self.host.write_json(asset_manifest_path, asset_manifest)
        if prompt_brief_text:
            self.host.write_text(prompt_brief_path, prompt_brief_text)

        showcase = None
        if args.get("generate_showcase", True):
            showcase_result = self.host.build_showcase_package(
                {
                    "scenario_dir": str(scenario_root),
                    "model_path": str(model_path),
                    "briefing_title": model["mission"]["title"],
                }
            )
            showcase = json.loads(showcase_result["content"][0]["text"])

        return self.host.wrap(
            {
                "scenario_dir": str(scenario_root),
                "entry_path": str(entry_path),
                "scenario_path": str(scenario_file_path),
                "model_path": str(model_path),
                "briefing_path": str(briefing_path),
                "phases_path": str(phases_path),
                "prompt_brief_path": str(prompt_brief_path) if prompt_brief_text else None,
                "project_brief_path": str(project_brief_path) if generate_project_brief else None,
                "project_plan_path": str(project_brief_path) if generate_project_brief else None,
                "asset_manifest_path": str(asset_manifest_path),
                "operational_model": model,
                "prompt_refinement": refinement,
                "showcase": showcase,
            }
        )

    def prepare_operational_project_plan(self, args):
        output_path = self.host.require_str(args, "output_path")
        prompt = str(args.get("prompt") or "")
        entry_path, scenario_root, _scenario_file_path, scenario_name = self.resolve_scenario_output_paths(
            output_path,
            args.get("project_dir"),
        )

        self.host.assert_path_allowed(entry_path, write=True, purpose="prepare_operational_project_plan(entry)")
        self.host.ensure_project_structure(scenario_root)

        refinement = self.host.refine_operational_prompt_payload(args, scenario_name, prompt)
        model = self.host.build_operational_model(args, scenario_name, prompt, refinement=refinement)
        project_brief_text = self.host.render_project_settings_plan_markdown(model, refinement=refinement)
        prompt_brief_text = self.host.render_prompt_refinement_markdown(refinement)

        model_path = scenario_root / "doc" / f"{scenario_name}.model.json"
        project_brief_path = scenario_root / "doc" / "PROJECT_BRIEF.md"
        project_plan_legacy_path = scenario_root / "doc" / "PROJECT_PLAN.md"
        prompt_brief_path = scenario_root / "doc" / "PROMPT_BRIEF.md"

        self.host.write_json(model_path, model)
        self.host.write_text(project_brief_path, project_brief_text)
        self.host.write_text(project_plan_legacy_path, project_brief_text)
        self.host.write_text(prompt_brief_path, prompt_brief_text)

        return self.host.wrap(
            {
                "scenario_dir": str(scenario_root),
                "project_brief_path": str(project_brief_path),
                "project_plan_path": str(project_brief_path),
                "prompt_brief_path": str(prompt_brief_path),
                "model_path": str(model_path),
                "prompt_refinement": refinement,
                "operational_model": model,
            }
        )

    def create_validated_operational_scenario_package(self, args):
        max_iterations = int(args.get("max_iterations") or 2)
        if max_iterations < 1:
            max_iterations = 1
        if max_iterations > 3:
            max_iterations = 3

        run_after_generate = bool(args.get("run_after_generate", True))
        analyze_after_run = bool(args.get("analyze_after_run", True))
        auto_open_wizard = bool(args.get("auto_open_wizard", True))
        wizard_background = bool(args.get("wizard_background", True))
        wizard_timeout_sec = float(args.get("wizard_timeout_sec") or 30)
        auto_open_mystic = bool(args.get("auto_open_mystic", False))
        auto_repair_on_failure = bool(args.get("auto_repair_on_failure", True))
        max_auto_repairs_per_attempt = int(args.get("max_auto_repairs_per_attempt") or 2)
        if max_auto_repairs_per_attempt < 0:
            max_auto_repairs_per_attempt = 0
        if max_auto_repairs_per_attempt > 3:
            max_auto_repairs_per_attempt = 3
        mission_timeout_sec = float(args.get("mission_timeout_sec") or 180)
        max_output_chars = int(args.get("max_output_chars") or 20000)

        attempts = []
        final_payload = None
        latest_analysis = None
        latest_aer = None
        latest_wizard = None
        success = False
        final_status = "generation_only"

        for index in range(max_iterations):
            attempt_no = index + 1
            fix_strategy = "default" if index == 0 else "force_generated_assets"
            attempt_args = dict(args)
            attempt_args.setdefault("generate_showcase", True)
            if index > 0:
                attempt_args["force_generated_assets"] = True
                attempt_args["generate_showcase"] = False

            attempt_record = {
                "attempt": attempt_no,
                "fix_strategy": fix_strategy,
                "generation": None,
                "mission": None,
                "analysis": None,
                "wizard": None,
                "repairs": [],
                "mission_runs": 0,
                "status": "pending",
                "error": None,
            }

            try:
                generated = self.create_operational_scenario_package(attempt_args)
                payload = json.loads(generated["content"][0]["text"])
                final_payload = payload
                attempt_record["generation"] = {
                    "scenario_dir": payload.get("scenario_dir"),
                    "entry_path": payload.get("entry_path"),
                    "scenario_path": payload.get("scenario_path"),
                    "asset_manifest_path": payload.get("asset_manifest_path"),
                    "project_brief_path": payload.get("project_brief_path"),
                    "project_plan_path": payload.get("project_plan_path"),
                }
            except Exception as exc:
                attempt_record["status"] = "generation_failed"
                attempt_record["error"] = str(exc)
                attempts.append(attempt_record)
                continue

            if not run_after_generate:
                attempt_record["status"] = "generated"
                attempts.append(attempt_record)
                success = False
                final_status = "generated"
                break

            scenario_entry = payload.get("entry_path")
            scenario_dir = payload.get("scenario_dir")
            scenario_path = payload.get("scenario_path")
            try:
                validated_this_attempt = False
                last_mission_payload = None
                for repair_round in range(max_auto_repairs_per_attempt + 1):
                    mission_result = self.host.run_mission(
                        {
                            "scenario": scenario_entry,
                            "working_dir": scenario_dir,
                            "timeout_sec": mission_timeout_sec,
                            "max_output_chars": max_output_chars,
                        }
                    )
                    mission_payload = json.loads(mission_result["content"][0]["text"])
                    last_mission_payload = mission_payload
                    attempt_record["mission_runs"] = int(attempt_record.get("mission_runs") or 0) + 1
                    if int(mission_payload.get("returncode", 1)) == 0:
                        validated_this_attempt = True
                        break
                    if not auto_repair_on_failure or repair_round >= max_auto_repairs_per_attempt:
                        break
                    repair_result = self.apply_mission_auto_repairs(
                        scenario_dir,
                        scenario_entry,
                        scenario_path,
                        mission_payload,
                    )
                    if repair_result.get("changed"):
                        attempt_record["repairs"].append(repair_result)
                    else:
                        attempt_record["repairs"].append(repair_result)
                        break

                attempt_record["mission"] = last_mission_payload
                if validated_this_attempt:
                    success = True
                    final_status = "validated"
                    latest_aer_obj = self.host.find_latest_aer(Path(scenario_dir))
                    latest_aer = str(latest_aer_obj) if latest_aer_obj else None
                    if auto_open_wizard:
                        try:
                            wizard_result = self.host.run_wizard(
                                {
                                    "working_dir": scenario_dir,
                                    "args": [scenario_entry],
                                    "background": wizard_background,
                                    "timeout_sec": wizard_timeout_sec,
                                    "max_output_chars": max_output_chars,
                                }
                            )
                            latest_wizard = json.loads(wizard_result["content"][0]["text"])
                            attempt_record["wizard"] = latest_wizard
                        except Exception as wizard_exc:
                            attempt_record["wizard"] = {"error": str(wizard_exc)}
                            attempt_record["status"] = "validated_wizard_failed"
                            final_status = "validated_wizard_failed"
                    if auto_open_mystic and latest_aer:
                        self.host.run_mystic({"recording": latest_aer, "working_dir": str(Path(latest_aer).parent)})
                    if analyze_after_run:
                        analysis_result = self.host.analyze_scenario_outputs({"scenario_dir": scenario_dir})
                        latest_analysis = json.loads(analysis_result["content"][0]["text"])
                        attempt_record["analysis"] = {
                            "summary_path": latest_analysis.get("output_md_path"),
                            "json_path": latest_analysis.get("output_json_path"),
                        }
                    if attempt_record["status"] == "pending":
                        attempt_record["status"] = "validated"
                    attempts.append(attempt_record)
                    break

                attempt_record["status"] = "mission_failed_after_repairs" if attempt_record["repairs"] else "mission_failed"
            except Exception as exc:
                attempt_record["status"] = "mission_exception"
                attempt_record["error"] = str(exc)

            attempts.append(attempt_record)

        if not attempts:
            final_status = "failed"
        elif not success and final_status == "generation_only":
            final_status = attempts[-1].get("status") or "failed"

        return self.host.wrap(
            {
                "status": final_status,
                "validated": success,
                "attempts": attempts,
                "scenario_dir": final_payload.get("scenario_dir") if final_payload else None,
                "entry_path": final_payload.get("entry_path") if final_payload else None,
                "scenario_path": final_payload.get("scenario_path") if final_payload else None,
                "asset_manifest_path": final_payload.get("asset_manifest_path") if final_payload else None,
                "project_brief_path": final_payload.get("project_brief_path") if final_payload else None,
                "project_plan_path": final_payload.get("project_plan_path") if final_payload else None,
                "latest_aer": latest_aer,
                "wizard": latest_wizard,
                "analysis": latest_analysis,
            }
        )

    def apply_mission_auto_repairs(self, scenario_dir, scenario_entry, scenario_path, mission_payload):
        scenario_root = Path(scenario_dir)
        entry_path = Path(scenario_entry)
        scenario_txt_path = Path(scenario_path) if scenario_path else scenario_root / "scenarios" / f"{scenario_root.name}.txt"
        stderr_text = str((mission_payload or {}).get("stderr") or "")
        stdout_text = str((mission_payload or {}).get("stdout") or "")
        combined = (stderr_text + "\n" + stdout_text).strip()

        actions = []
        changed = False

        missing_includes = self.extract_missing_include_paths_from_error(combined)
        if missing_includes:
            for include_name in missing_includes:
                created = self.ensure_include_placeholder(scenario_root, include_name)
                if created:
                    changed = True
                    actions.append({"action": "create_missing_include", "path": include_name})

        for include_target in [entry_path, scenario_txt_path]:
            include_fixes = self.ensure_existing_includes_present(include_target, scenario_root)
            if include_fixes:
                changed = True
                for item in include_fixes:
                    actions.append({"action": "materialize_include", "path": item})

        missing_types = self.extract_missing_platform_types_from_error(combined)
        if missing_types:
            repaired_types = self.ensure_stub_platform_types(scenario_root, scenario_txt_path, missing_types)
            if repaired_types:
                changed = True
                actions.append({"action": "define_missing_platform_types", "types": repaired_types})

        missing_defs = self.extract_missing_named_definitions_from_error(combined)
        for category in ("sensor", "weapon", "processor"):
            names = missing_defs.get(category) or []
            if not names:
                continue
            repaired_defs = self.ensure_stub_named_definitions(scenario_root, scenario_txt_path, category, names)
            if repaired_defs:
                changed = True
                actions.append(
                    {
                        "action": f"define_missing_{category}s",
                        "category": category,
                        "names": repaired_defs,
                    }
                )

        balanced = self.ensure_balanced_scenario_blocks(scenario_txt_path)
        if balanced:
            changed = True
            actions.append(
                {
                    "action": "balance_scenario_blocks",
                    "path": str(scenario_txt_path),
                    "appended": balanced.get("appended") or [],
                }
            )

        if ("generated_air_assets.txt" in combined or "generated_ground_assets.txt" in combined) and not changed:
            generated = self.write_generated_asset_bundle(scenario_root)
            if generated:
                changed = True
                actions.append({"action": "rewrite_generated_asset_bundle", "files": generated})

        return {
            "changed": changed,
            "actions": actions,
            "error_excerpt": self.host.truncate_text(combined, 1200),
        }

    def extract_missing_include_paths_from_error(self, text):
        candidates = set()
        patterns = [
            r"([A-Za-z0-9_./\\-]+\.txt)\s*(?:not found|missing|cannot open|unable to open)",
            r"(?:cannot|can't|could not|unable to)\s+(?:open|read|find)\s+([A-Za-z0-9_./\\-]+\.txt)",
            r"include(?:_once)?\s+([A-Za-z0-9_./\\-]+\.txt)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
                normalized = self.normalize_include_path(match.group(1))
                if normalized:
                    candidates.add(normalized)
        return sorted(candidates)

    def ensure_include_placeholder(self, scenario_root, include_name):
        include_path = scenario_root / include_name
        if include_path.exists():
            return False
        placeholder = "// auto-repair placeholder include generated by MCP\n"
        self.host.write_text(include_path, placeholder)
        return True

    def ensure_existing_includes_present(self, source_path, scenario_root):
        if not source_path.exists():
            return []
        fixed = []
        source_text = self.host.read_text(source_path)
        for include_name in self.extract_include_paths(source_text):
            target_path = scenario_root / include_name
            if target_path.exists():
                continue
            if include_name in ("platforms/generated_air_assets.txt", "platforms/generated_ground_assets.txt"):
                self.write_generated_asset_bundle(scenario_root)
            else:
                self.host.write_text(target_path, "// auto-repair placeholder include generated by MCP\n")
            fixed.append(include_name)
        return fixed

    def extract_missing_platform_types_from_error(self, text):
        names = set()
        patterns = [
            r"(?:unknown|undefined|unrecognized)\s+(?:platform(?:_type)?|type)\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"platform(?:_type)?\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:not found|is undefined|unknown)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
                names.add(match.group(1))
        return sorted(names)

    def extract_missing_named_definitions_from_error(self, text):
        matches = {"sensor": set(), "weapon": set(), "processor": set()}
        patterns = [
            r"(?:unknown|undefined|unrecognized)\s+(sensor|weapon|processor)(?:_type)?\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
            r"(sensor|weapon|processor)(?:_type)?\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s+(?:not found|is undefined|unknown)",
            r"(?:cannot|can't|could not|unable to)\s+find\s+(sensor|weapon|processor)\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
                kind = str(match.group(1) or "").lower()
                name = str(match.group(2) or "").strip()
                if kind in matches and name:
                    matches[kind].add(name)
        return {key: sorted(value) for key, value in matches.items() if value}

    def ensure_stub_platform_types(self, scenario_root, scenario_txt_path, missing_types):
        if not missing_types:
            return []
        stub_file_rel = "platforms/auto_repair_types.txt"
        stub_file = scenario_root / stub_file_rel
        existing_text = self.host.read_text(stub_file) if stub_file.exists() else ""
        created = []
        blocks = []
        for name in missing_types:
            if re.search(rf"\bplatform_type\s+{re.escape(name)}\b", existing_text, flags=re.IGNORECASE):
                continue
            blocks.extend(self.build_stub_platform_type_block(name))
            created.append(name)

        if blocks:
            merged_text = existing_text.rstrip() + ("\n\n" if existing_text.strip() else "") + "\n".join(blocks) + "\n"
            self.host.write_text(stub_file, merged_text)

        if created and scenario_txt_path.exists():
            scenario_text = self.host.read_text(scenario_txt_path)
            include_line = f"include_once {stub_file_rel}"
            if include_line not in scenario_text:
                scenario_text = include_line + "\n" + scenario_text
                self.host.write_text(scenario_txt_path, scenario_text)
        return created

    def ensure_stub_named_definitions(self, scenario_root, scenario_txt_path, category, missing_names):
        if not missing_names:
            return []

        category = str(category or "").lower().strip()
        file_map = {
            "sensor": ("sensors/auto_repair_sensors.txt", self.build_stub_sensor_block),
            "weapon": ("weapons/auto_repair_weapons.txt", self.build_stub_weapon_block),
            "processor": ("processors/auto_repair_processors.txt", self.build_stub_processor_block),
        }
        config = file_map.get(category)
        if not config:
            return []

        stub_file_rel, builder = config
        stub_file = scenario_root / stub_file_rel
        existing_text = self.host.read_text(stub_file) if stub_file.exists() else ""
        scenario_text = self.host.read_text(scenario_txt_path) if scenario_txt_path.exists() else ""
        created = []
        blocks = []

        for name in missing_names:
            if re.search(rf"\b{re.escape(category)}\s+{re.escape(name)}\b", existing_text, flags=re.IGNORECASE):
                continue
            if re.search(rf"\b{re.escape(category)}\s+{re.escape(name)}\b", scenario_text, flags=re.IGNORECASE):
                continue
            blocks.extend(builder(name))
            created.append(name)

        if blocks:
            merged_text = existing_text.rstrip() + ("\n\n" if existing_text.strip() else "") + "\n".join(blocks) + "\n"
            self.host.write_text(stub_file, merged_text)

        if created and scenario_txt_path.exists():
            include_line = f"include_once {stub_file_rel}"
            if include_line not in scenario_text:
                scenario_text = include_line + "\n" + scenario_text
                self.host.write_text(scenario_txt_path, scenario_text)

        return created

    def ensure_balanced_scenario_blocks(self, scenario_txt_path):
        if not scenario_txt_path.exists():
            return None

        text = self.host.read_text(scenario_txt_path)
        stack = []
        appended = []
        open_to_close = {
            "platform": "end_platform",
            "platform_type": "end_platform_type",
            "route": "end_route",
            "mover": "end_mover",
            "sensor": "end_sensor",
            "weapon": "end_weapon",
            "processor": "end_processor",
        }

        for raw_line in str(text or "").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            token = stripped.split(None, 1)[0].lower()
            if token.startswith("end_"):
                if stack and stack[-1] == token:
                    stack.pop()
                continue

            end_token = open_to_close.get(token)
            if not end_token:
                continue

            if token == "mover" and " end_mover" in stripped.lower():
                continue
            if token == "route" and " end_route" in stripped.lower():
                continue

            stack.append(end_token)

        if not stack:
            return None

        fix_lines = ["", "// auto-repair appended missing block terminators"]
        while stack:
            end_token = stack.pop()
            fix_lines.append(end_token)
            appended.append(end_token)

        updated = text.rstrip() + "\n" + "\n".join(fix_lines) + "\n"
        self.host.write_text(scenario_txt_path, updated)
        return {"appended": appended}

    def build_stub_platform_type_block(self, type_name):
        upper = str(type_name or "").upper()
        is_air = any(token in upper for token in ("AIR", "FIGHTER", "UAV", "JET", "BOMBER", "AWACS", "HVAA"))
        is_ground = any(token in upper for token in ("SAM", "TANK", "LAUNCHER", "TARGET", "GROUND", "RADAR", "BATTERY"))
        lines = [f"platform_type {type_name} WSF_PLATFORM"]
        if is_air:
            lines.append("   icon f15c")
            lines.append("   mover WSF_AIR_MOVER")
            lines.append("   end_mover")
        elif is_ground:
            lines.append("   icon close-sam_cdr")
            lines.append("   mover WSF_GROUND_MOVER end_mover")
        else:
            lines.append("   icon aircraft")
        lines.append("end_platform_type")
        lines.append("")
        return lines

    def build_stub_sensor_block(self, sensor_name):
        return [
            f"sensor {sensor_name} WSF_RADAR_SENSOR",
            "   frame_time 1 sec",
            "end_sensor",
            "",
        ]

    def build_stub_weapon_block(self, weapon_name):
        return [
            f"weapon {weapon_name} WSF_EXPLICIT_WEAPON",
            "end_weapon",
            "",
        ]

    def build_stub_processor_block(self, processor_name):
        return [
            f"processor {processor_name} WSF_TASK_PROCESSOR",
            "end_processor",
            "",
        ]

    def prepare_asset_profile_for_output(self, scenario_root, model):
        asset_profile = dict(model.get("asset_profile") or {})
        manifest = {
            "mode": asset_profile.get("mode") or "basic",
            "source_asset_root": asset_profile.get("asset_root"),
            "entry_includes": list(asset_profile.get("entry_includes") or []),
            "scenario_includes": list(asset_profile.get("scenario_includes") or []),
            "copied_files": [],
            "generated_files": [],
            "fallback_reason": None,
        }

        copied_files = self.materialize_asset_profile_dependencies(scenario_root, asset_profile)
        if copied_files:
            asset_profile["asset_root"] = None
            manifest["copied_files"] = copied_files
            manifest["mode"] = f"{manifest['mode']}_materialized"
        else:
            generated_files = self.write_generated_asset_bundle(scenario_root)
            asset_profile = self.generated_asset_profile()
            manifest["mode"] = "generated_structured"
            manifest["generated_files"] = generated_files
            if manifest["source_asset_root"]:
                manifest["fallback_reason"] = "materialization_failed"
            else:
                manifest["fallback_reason"] = "no_external_asset_root"

        model["asset_profile"] = asset_profile
        return manifest

    def materialize_asset_profile_dependencies(self, scenario_root, asset_profile):
        asset_root = asset_profile.get("asset_root")
        includes = list(asset_profile.get("entry_includes") or []) + list(asset_profile.get("scenario_includes") or [])
        if not asset_root or not includes:
            return []

        source_root = Path(asset_root)
        if not source_root.exists():
            return []

        copied = []
        visited = set()
        pending = list(includes)
        resolved_files = {}

        while pending:
            relative_name = pending.pop(0)
            normalized_name = self.normalize_include_path(relative_name)
            if not normalized_name or normalized_name in visited:
                continue

            source_path = (source_root / normalized_name).resolve()
            try:
                source_path.relative_to(source_root.resolve())
            except ValueError:
                return []
            if not source_path.exists() or not source_path.is_file():
                return []

            text = self.host.read_text(source_path)
            resolved_files[normalized_name] = text
            visited.add(normalized_name)

            for include_name in self.extract_include_paths(text):
                if include_name not in visited:
                    pending.append(include_name)

        for normalized_name, text in resolved_files.items():
            target_path = scenario_root / normalized_name
            self.host.write_text(target_path, text)
            copied.append(str(target_path))

        return copied

    def extract_include_paths(self, text):
        includes = []
        for raw_line in str(text or "").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if not (stripped.startswith("include ") or stripped.startswith("include_once ")):
                continue
            parts = stripped.split(None, 1)
            if len(parts) != 2:
                continue
            include_name = parts[1].split("//", 1)[0].strip().strip('"').strip("'")
            normalized = self.normalize_include_path(include_name)
            if normalized:
                includes.append(normalized)
        return includes

    def normalize_include_path(self, include_name):
        text = str(include_name or "").strip().replace("\\", "/")
        if not text or "${" in text or text.startswith("<"):
            return None
        return text.lstrip("./")

    def write_generated_asset_bundle(self, scenario_root):
        air_assets_path = scenario_root / "platforms" / "generated_air_assets.txt"
        ground_assets_path = scenario_root / "platforms" / "generated_ground_assets.txt"

        air_lines = [
            "platform_type AUTO_BLUE_FIGHTER_AIR WSF_PLATFORM",
            "   icon f15c",
            "   mover WSF_AIR_MOVER",
            "   end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_RED_FIGHTER_AIR WSF_PLATFORM",
            "   icon su27",
            "   mover WSF_AIR_MOVER",
            "   end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_BLUE_SUPPORT_AIR AUTO_BLUE_FIGHTER_AIR",
            "   icon f15c",
            "end_platform_type",
            "",
            "platform_type AUTO_RED_SUPPORT_AIR AUTO_RED_FIGHTER_AIR",
            "   icon su27",
            "end_platform_type",
            "",
        ]
        ground_lines = [
            "platform_type AUTO_BLUE_TARGET WSF_PLATFORM",
            "   icon Bullseye",
            "   mover WSF_GROUND_MOVER end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_RED_TARGET AUTO_BLUE_TARGET",
            "end_platform_type",
            "",
            "platform_type AUTO_BLUE_AIR_DEFENSE WSF_PLATFORM",
            "   icon close-sam_cdr",
            "   mover WSF_GROUND_MOVER end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_RED_AIR_DEFENSE WSF_PLATFORM",
            "   icon close-sam_cdr",
            "   mover WSF_GROUND_MOVER end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_RED_MISSILE_LAUNCHER WSF_PLATFORM",
            "   icon Scud_Launcher",
            "   mover WSF_GROUND_MOVER end_mover",
            "end_platform_type",
            "",
            "platform_type AUTO_BLUE_MISSILE_LAUNCHER AUTO_RED_MISSILE_LAUNCHER",
            "   icon Scud_Launcher",
            "end_platform_type",
            "",
        ]

        self.host.write_text(air_assets_path, "\n".join(air_lines))
        self.host.write_text(ground_assets_path, "\n".join(ground_lines))
        return [str(air_assets_path), str(ground_assets_path)]

    def generated_asset_profile(self):
        return {
            "mode": "generated_structured",
            "asset_root": None,
            "entry_includes": [],
            "scenario_includes": [
                "platforms/generated_air_assets.txt",
                "platforms/generated_ground_assets.txt",
            ],
            "blue_fighter_type": "AUTO_BLUE_FIGHTER_AIR",
            "red_fighter_type": "AUTO_RED_FIGHTER_AIR",
            "blue_support_type": "AUTO_BLUE_SUPPORT_AIR",
            "red_support_type": "AUTO_RED_SUPPORT_AIR",
            "blue_target_type": "AUTO_BLUE_TARGET",
            "red_target_type": "AUTO_RED_TARGET",
            "blue_air_defense_type": "AUTO_BLUE_AIR_DEFENSE",
            "red_air_defense_type": "AUTO_RED_AIR_DEFENSE",
            "red_missile_launcher_type": "AUTO_RED_MISSILE_LAUNCHER",
            "blue_missile_launcher_type": "AUTO_BLUE_MISSILE_LAUNCHER",
            "supports_observer": True,
        }

    def refine_operational_prompt(self, args):
        prompt = str(args.get("prompt") or "")
        scenario_name = str(args.get("scenario_name") or "operational_scenario")
        refinement = self.host.refine_operational_prompt_payload(args, scenario_name, prompt)
        return self.host.wrap(refinement)

    def run_demo(self, args):
        demos = self.host.get_demos_root()
        if not demos:
            return self.host.wrap({"error": "demos folder not found"})
        demo = args.get("demo")
        scenario = args.get("scenario")
        if not demo or not scenario:
            return self.host.wrap({"error": "demo and scenario are required"})
        demo_dir = demos / demo
        if not demo_dir.exists():
            return self.host.wrap({"error": "demo not found"})
        self.host.assert_path_allowed(demo_dir, write=True, purpose="run_demo(demo_dir)")
        scenario_path = Path(scenario)
        if not scenario_path.is_absolute():
            scenario_path = demo_dir / scenario
        self.host.assert_path_allowed(scenario_path, write=False, purpose="run_demo(scenario)")
        mission_exe = self.host.resolve_exe("mission")
        if not mission_exe:
            raise self.host.JsonRpcError(-32002, "mission executable not found", {"tool": "run_demo"})
        mission_result = self.host.run_process([str(mission_exe), str(scenario_path)], str(demo_dir))
        latest_aer = self.host.find_latest_aer(demo_dir)
        mystic_result = None
        if args.get("open_mystic") and latest_aer:
            mystic_result = self.host.run_mystic({"recording": str(latest_aer), "working_dir": str(latest_aer.parent)})
        return self.host.wrap(
            {
                "mission": json.loads(mission_result["content"][0]["text"]),
                "latest_aer": str(latest_aer) if latest_aer else None,
                "mystic": json.loads(mystic_result["content"][0]["text"]) if mystic_result else None,
            }
        )

    def generate_basic_scenario_entities_text(self, aircraft_count, tank_count, side, center_lat, center_lon):
        lines = []
        for idx in range(aircraft_count):
            lat = center_lat + 0.01 * idx
            lon = center_lon + 0.01 * idx
            start_pos = self.host.format_lat_lon(lat, lon)
            end_pos = self.host.format_lat_lon(lat + 0.05, lon + 0.05)
            lines.append(f"platform aircraft_{idx + 1} WSF_PLATFORM")
            lines.append("   spatial_domain air")
            lines.append(f"   side {side}")
            lines.append("   icon F-18")
            lines.append("   add mover WSF_AIR_MOVER")
            lines.append("   end_mover")
            lines.append("   route")
            lines.append(f"      position {start_pos} altitude 6000 ft speed 500 kts")
            lines.append(f"      position {end_pos} altitude 6000 ft speed 500 kts")
            lines.append("   end_route")
            lines.append("end_platform")
            lines.append("")
        for idx in range(tank_count):
            lat = center_lat - 0.02 * idx
            lon = center_lon - 0.02 * idx
            start_pos = self.host.format_lat_lon(lat, lon)
            end_pos = self.host.format_lat_lon(lat + 0.01, lon + 0.01)
            lines.append(f"platform tank_{idx + 1} WSF_PLATFORM")
            lines.append(f"   side {side}")
            lines.append("   icon tank")
            lines.append("   mover WSF_GROUND_MOVER")
            lines.append("      on_ground")
            lines.append("      route")
            lines.append(f"         position {start_pos} altitude 1 m speed 20 km/hr")
            lines.append(f"         position {end_pos}")
            lines.append("         stop")
            lines.append("      end_route")
            lines.append("   end_mover")
            lines.append("end_platform")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def generate_basic_entrypoint_text(self, scenario_name, duration_min):
        lines = [
            "file_path .",
            "realtime",
            f"end_time {duration_min} min",
            "",
            self.host.build_observer_block_text().rstrip(),
            "",
            f"include_once scenarios/{scenario_name}.txt",
            "event_pipe",
            "   enable AIRCOMBAT",
            "end_event_pipe",
            "",
        ]
        return "\n".join(lines).strip() + "\n"

    def parse_prompt_counts(self, prompt):
        text = prompt or ""
        counts = {}
        aircraft = self.extract_count(text, ["飞机", "aircraft", "飞机群"])
        tank = self.extract_count(text, ["坦克", "tank"])
        if aircraft:
            counts["aircraft"] = aircraft
        if tank:
            counts["tank"] = tank
        return counts

    def extract_count(self, text, keywords):
        best_value = None
        best_distance = None
        for key in keywords:
            search_start = 0
            while True:
                idx = text.find(key, search_start)
                if idx == -1:
                    break
                num, distance = self.find_nearest_number(text, key, idx)
                if num is not None and (best_distance is None or distance < best_distance):
                    best_value = num
                    best_distance = distance
                search_start = idx + len(key)
        return best_value

    def find_nearest_number(self, text, key, idx=None):
        idx = text.find(key) if idx is None else idx
        if idx == -1:
            return None, None
        window_start = max(0, idx - 12)
        window_end = idx + len(key) + 12
        window = text[window_start:window_end]

        best_value = None
        best_distance = None
        for match in re.finditer(r"\d+(?:\.\d+)?", window):
            if self.is_time_like_number(window, match.start(), match.end()):
                continue
            value = int(float(match.group(0)))
            distance = min(abs(match.start() - (idx - window_start)), abs(match.end() - (idx - window_start)))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_value = value

        if best_value is not None:
            return best_value, best_distance

        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "两": 2}
        for match in re.finditer(r"[一二三四五六七八九十两]", window):
            distance = min(abs(match.start() - (idx - window_start)), abs(match.end() - (idx - window_start)))
            value = cn_map.get(match.group(0))
            if value is None:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_value = value

        return best_value, best_distance

    def is_time_like_number(self, text, start, end):
        nearby = text[max(0, start - 2):min(len(text), end + 10)].lower()
        return bool(re.search(r"(min|mins|minute|minutes|hour|hours|sec|second|seconds|分钟|小时|秒)", nearby))

    def resolve_scenario_output_paths(self, output_path, project_dir=None):
        output = Path(output_path)
        if project_dir and not output.is_absolute():
            output = Path(project_dir) / output
        if output.suffix == "":
            output = output.with_suffix(".txt")

        scenario_name = output.stem
        project_root_p = Path(project_dir) if project_dir else self.host.resolve_project_root()
        entry_path = output
        scenario_root = output.parent
        state_scenarios_root = self.host.state_dir / "scenarios"

        try:
            state_rel = output.resolve().relative_to(state_scenarios_root.resolve())
        except Exception:
            state_rel = None

        if state_rel is not None:
            root_name = state_rel.parts[0] if state_rel.parts else scenario_name
            scenario_root = state_scenarios_root / root_name
            entry_path = scenario_root / f"{root_name}.txt"
            scenario_name = root_name
            scenario_file_path = scenario_root / "scenarios" / f"{scenario_name}.txt"
            return entry_path, scenario_root, scenario_file_path, scenario_name

        if output.parent.name == "scenarios":
            scenario_root = output.parent.parent
            entry_path = scenario_root / f"{scenario_name}.txt"
        elif output.parent.name in self.host.STANDARD_PROJECT_DIRS:
            scenario_root = output.parent.parent
            entry_path = scenario_root / f"{scenario_name}.txt"

        if project_root_p:
            pr = Path(project_root_p).resolve()
            try:
                rel = entry_path.resolve().relative_to(pr)
            except ValueError:
                rel = None
            if rel is not None and len(rel.parts) == 1:
                scenario_root = pr / scenario_name
                entry_path = scenario_root / f"{scenario_name}.txt"

        scenario_file_path = scenario_root / "scenarios" / f"{scenario_name}.txt"
        return entry_path, scenario_root, scenario_file_path, scenario_name