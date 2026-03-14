class TaskPlanningService:
    def __init__(self, host):
        self.host = host

    def build_task_plan(self, prompt, scenario_kind, duration_min, center, desired_kpis, raw_model=None):
        raw_model = raw_model if isinstance(raw_model, dict) else {}
        raw_task_plan = raw_model.get("task_plan")
        if isinstance(raw_task_plan, dict) and raw_task_plan:
            return self.normalize_task_plan(raw_task_plan, scenario_kind, duration_min)
        return self.infer_task_plan_from_prompt(prompt, scenario_kind, duration_min, center, desired_kpis)

    def normalize_task_plan(self, task_plan, scenario_kind, duration_min):
        normalized = {
            "scenario_kind": task_plan.get("scenario_kind") or scenario_kind,
            "commander_intent": task_plan.get("commander_intent") or self.default_commander_intent(scenario_kind),
            "planning_assumptions": list(task_plan.get("planning_assumptions") or []),
            "blue_tasks": self._normalize_task_list(task_plan.get("blue_tasks"), "blue", duration_min),
            "red_tasks": self._normalize_task_list(task_plan.get("red_tasks"), "red", duration_min),
            "neutral_tasks": self._normalize_task_list(task_plan.get("neutral_tasks"), "neutral", duration_min),
        }
        self.apply_default_dependencies(normalized, scenario_kind)
        self.apply_task_timing_constraints(normalized, duration_min)
        normalized["task_sequence"] = self.build_task_sequence(normalized)
        normalized["support_matrix"] = self.build_support_matrix(normalized)
        normalized["dependency_summary"] = self.build_dependency_summary(normalized)
        return normalized

    def infer_task_plan_from_prompt(self, prompt, scenario_kind, duration_min, center, desired_kpis):
        text = str(prompt or "")
        defaults = self.default_tasks_for_scenario(scenario_kind, duration_min)
        tasks = {
            "blue_tasks": [dict(item) for item in defaults["blue_tasks"]],
            "red_tasks": [dict(item) for item in defaults["red_tasks"]],
            "neutral_tasks": [dict(item) for item in defaults.get("neutral_tasks", [])],
        }

        if scenario_kind == "integrated_air_missile_defense":
            self.apply_task_count(tasks["blue_tasks"], "blue_intercept_barrier", self.host.extract_count(text, ["interceptor", "fighter", "拦截机", "战斗机"]))
            self.apply_task_count(tasks["blue_tasks"], "blue_area_defense", self.host.extract_count(text, ["sam", "battery", "防空", "地空导弹"]))
            self.apply_task_count(tasks["red_tasks"], "red_ballistic_raid", self.host.extract_count(text, ["launcher", "missile launcher", "发射车", "弹道导弹"]))
            self.apply_task_count(tasks["red_tasks"], "red_escort_sweep", self.host.extract_count(text, ["escort", "护航"]))
            self.apply_task_count(tasks["red_tasks"], "red_air_raid", self.host.extract_count(text, ["strike", "raid", "突击"]))
        elif scenario_kind == "strike_package":
            self.apply_task_count(tasks["blue_tasks"], "blue_strike_push", self.host.extract_count(text, ["strike", "attacker", "打击"]))
            self.apply_task_count(tasks["blue_tasks"], "blue_escort_cover", self.host.extract_count(text, ["escort", "护航"]))
            self.apply_task_count(tasks["red_tasks"], "red_cap_defense", self.host.extract_count(text, ["patrol", "fighter", "巡逻", "战斗机"]))
        else:
            self.apply_task_count(tasks["blue_tasks"], "blue_barrier_cap", self.host.extract_count(text, ["blue fighter", "blue interceptors", "蓝方战斗机"]))
            self.apply_task_count(tasks["red_tasks"], "red_probe_push", self.host.extract_count(text, ["red fighter", "red patrol", "红方战斗机"]))

        plan = {
            "scenario_kind": scenario_kind,
            "commander_intent": self.infer_commander_intent(prompt, scenario_kind, desired_kpis),
            "planning_assumptions": self.collect_task_assumptions(prompt, center, desired_kpis, scenario_kind),
            "blue_tasks": tasks["blue_tasks"],
            "red_tasks": tasks["red_tasks"],
            "neutral_tasks": tasks["neutral_tasks"],
        }
        self.apply_default_dependencies(plan, scenario_kind)
        self.apply_task_timing_constraints(plan, duration_min)
        plan["task_sequence"] = self.build_task_sequence(plan)
        plan["support_matrix"] = self.build_support_matrix(plan)
        plan["dependency_summary"] = self.build_dependency_summary(plan)
        return plan

    def derive_force_packages_from_task_plan(self, task_plan, scenario_kind):
        grouped = {"blue": [], "red": [], "neutral": []}
        for side in grouped:
            for task in task_plan.get(f"{side}_tasks", []):
                grouped[side].append(
                    {
                        "name": task["package_name"],
                        "side": side,
                        "role": task["role"],
                        "category": task["category"],
                        "count": self.compute_package_count(task),
                        "base_count": int(task.get("count") or 1),
                        "icon": task.get("icon") or self.host.default_icon_for_category(task["category"]),
                        "task_id": task.get("task_id"),
                        "depends_on": list(task.get("depends_on") or []),
                        "supports": list(task.get("supports") or []),
                        "trigger_conditions": list(task.get("trigger_conditions") or []),
                        "failure_actions": list(task.get("failure_actions") or []),
                        "mission_task": self.infer_package_mission_task(task),
                        "route_style": self.infer_route_style(task),
                        "fallback_route_style": self.infer_fallback_route_style(task),
                        "narrative_role": self.infer_narrative_role(task),
                        "commit_range_nm": self.infer_commit_range_nm(task),
                        "risk_weapon": self.infer_risk_weapon(task),
                        "target_priority": self.infer_target_priority(task, scenario_kind),
                        "launch_time_sec": self.infer_launch_time_sec(task),
                        "task_phase": task.get("phase"),
                        "timing_notes": list(task.get("timing_notes") or []),
                        "contingency_count": self.infer_contingency_count(task),
                        "abort_on_failure_of": self.infer_abort_on_failure_of(task),
                        "contingency_phase": self.infer_contingency_phase(task),
                    }
                )
        if not any(grouped.values()):
            return self.host.default_force_packages(scenario_kind)
        return grouped

    def derive_objectives_from_task_plan(self, task_plan, scenario_kind, desired_kpis):
        objectives = []
        for side in ("blue", "red"):
            for task in task_plan.get(f"{side}_tasks", []):
                effect = task.get("desired_effect") or task.get("objective")
                if not effect:
                    continue
                objectives.append({"side": side, "description": effect})
        if desired_kpis:
            objectives.append(
                {
                    "side": "both",
                    "description": "Produce a replay and analysis package with clear KPI evidence for " + ", ".join(desired_kpis[:3]) + ".",
                }
            )
        if not objectives:
            return self.host.default_operational_objectives(scenario_kind)
        return objectives

    def derive_phases_from_task_plan(self, task_plan, duration_min, scenario_kind):
        sequence = list(task_plan.get("task_sequence") or [])
        if not sequence:
            return self.host.default_operational_phases(scenario_kind, duration_min)

        phase_map = {}
        phase_order = []
        for task in sequence:
            phase_name = task.get("phase") or "Operate"
            if phase_name not in phase_map:
                phase_map[phase_name] = {
                    "name": phase_name,
                    "start_min": float(task.get("start_min") or 0.0),
                    "end_min": float(task.get("end_min") or duration_min),
                    "task_names": [],
                }
                phase_order.append(phase_name)
            phase = phase_map[phase_name]
            phase["start_min"] = min(phase["start_min"], float(task.get("start_min") or 0.0))
            phase["end_min"] = max(phase["end_min"], float(task.get("end_min") or duration_min))
            phase["task_names"].append(task.get("name") or task.get("task_id"))

        phases = []
        for name in phase_order:
            phase = phase_map[name]
            phases.append(
                {
                    "name": phase["name"],
                    "start_min": round(phase["start_min"], 1),
                    "end_min": round(phase["end_min"], 1),
                    "summary": "; ".join(phase["task_names"][:3]),
                }
            )
        return phases

    def derive_engagement_rules_from_task_plan(self, task_plan, scenario_kind, desired_kpis):
        rules = dict(self.host.default_engagement_rules(scenario_kind))
        categories = []
        blue_priority_targets = []
        red_priority_targets = []
        coordination_windows = []
        fallback_postures = []
        for side in ("blue", "red"):
            for task in task_plan.get(f"{side}_tasks", []):
                category = task.get("category")
                if category:
                    categories.append(category)
                for target in self.infer_target_priority(task, scenario_kind):
                    target_list = blue_priority_targets if side == "blue" else red_priority_targets
                    if target not in target_list:
                        target_list.append(target)
                if task.get("depends_on"):
                    coordination_windows.append(
                        {
                            "task_id": task.get("task_id"),
                            "depends_on": list(task.get("depends_on") or []),
                            "trigger": list(task.get("trigger_conditions") or [])[:1],
                        }
                    )
                if task.get("failure_actions"):
                    fallback_postures.append(
                        {
                            "task_id": task.get("task_id"),
                            "route_style": self.infer_fallback_route_style(task),
                            "action": list(task.get("failure_actions") or [])[:1],
                        }
                    )
        if any(category == "missile_launcher" for category in categories):
            rules["priority_targets"] = ["ballistic_missile", "strike_fighter", "escort"]
        elif any(category == "air_defense" for category in categories):
            rules["priority_targets"] = ["sam_battery", "fighter", "objective"]
        if desired_kpis:
            rules["desired_kpis"] = desired_kpis
        if blue_priority_targets:
            rules["blue_priority_targets"] = blue_priority_targets
        if red_priority_targets:
            rules["red_priority_targets"] = red_priority_targets
        if coordination_windows:
            rules["coordination_rule"] = "Dependent packages delay commit until supporter tasks establish a viable corridor or trigger condition."
            rules["coordination_windows"] = coordination_windows
        if fallback_postures:
            rules["fallback_posture"] = "Task failures force surviving packages into defensive or egress geometry rather than continuing the original push."
            rules["fallback_routes"] = fallback_postures
        contingency_actions = self.build_contingency_actions(task_plan)
        if contingency_actions:
            rules["contingency_actions"] = contingency_actions
        rules["task_plan_priority"] = self.summarize_task_priorities(task_plan)
        return rules

    def summarize_task_plan(self, task_plan):
        summary = []
        for side in ("blue", "red", "neutral"):
            tasks = task_plan.get(f"{side}_tasks", [])
            if not tasks:
                continue
            entries = []
            for task in tasks:
                support_text = ""
                if task.get("supports"):
                    support_text = f" supports {', '.join(task.get('supports', []))}"
                entries.append(
                    f"{task['name']} [{task['phase']}] x{task.get('count', 1)} -> {task.get('desired_effect')}{support_text}"
                )
            summary.append(f"{side}: " + "; ".join(entries))
        return summary

    def summarize_task_priorities(self, task_plan):
        priorities = []
        for task in task_plan.get("blue_tasks", [])[:2] + task_plan.get("red_tasks", [])[:2]:
            priorities.append(task.get("name"))
        return priorities

    def apply_task_timing_constraints(self, task_plan, duration_min):
        all_tasks = {}
        for side in ("blue", "red", "neutral"):
            for task in task_plan.get(f"{side}_tasks", []):
                task["base_start_min"] = round(float(task.get("start_min") or 0.0), 1)
                task["base_end_min"] = round(float(task.get("end_min") or duration_min), 1)
                task.setdefault("timing_notes", [])
                all_tasks[task["task_id"]] = task

        support_lead = max(1.0, round(duration_min * 0.05, 1))
        dependency_delay = max(2.0, round(duration_min * 0.08, 1))
        fallback_shift = max(2.0, round(duration_min * 0.1, 1))

        for task in all_tasks.values():
            start_min = float(task.get("base_start_min") or 0.0)
            end_min = float(task.get("base_end_min") or duration_min)

            if task.get("supports"):
                adjusted_start = max(0.0, start_min - support_lead)
                if adjusted_start != start_min:
                    task["timing_notes"].append("support task starts earlier to establish corridor or coverage")
                start_min = adjusted_start
                end_min = min(float(duration_min), end_min + support_lead)

            dependency_tasks = [all_tasks.get(item) for item in task.get("depends_on") or []]
            dependency_tasks = [item for item in dependency_tasks if item]
            if dependency_tasks:
                dependency_ready = max(float(dep.get("base_start_min") or 0.0) + dependency_delay for dep in dependency_tasks)
                if dependency_ready > start_min:
                    task["timing_notes"].append("dependent task delayed until supporter task establishes conditions")
                start_min = max(start_min, dependency_ready)

            if task.get("failure_actions"):
                category = str(task.get("category") or "").lower()
                if category in ("strike", "escort", "interceptor", "air_patrol"):
                    adjusted_end = max(start_min + 1.0, end_min - fallback_shift)
                    if adjusted_end != end_min:
                        task["timing_notes"].append("failure fallback shortens on-station time and drives egress")
                    end_min = adjusted_end
                else:
                    adjusted_end = min(float(duration_min), end_min + fallback_shift)
                    if adjusted_end != end_min:
                        task["timing_notes"].append("failure fallback extends defensive hold window")
                    end_min = adjusted_end

            if end_min <= start_min:
                end_min = min(float(duration_min), start_min + max(1.0, round(duration_min * 0.08, 1)))

            task["start_min"] = round(start_min, 1)
            task["end_min"] = round(end_min, 1)

    def compute_package_count(self, task):
        base = int(task.get("count") or 1)
        category = str(task.get("category") or "").lower()
        adjustment = 0
        if task.get("supports") and category in ("escort", "interceptor", "air_patrol", "air_defense"):
            adjustment += 1
        if task.get("failure_actions") and category in ("escort", "air_defense", "high_value_asset"):
            adjustment += 1
        if task.get("depends_on") and category == "missile_launcher":
            adjustment += 1
        return max(1, base + adjustment)

    def infer_package_mission_task(self, task):
        role = str(task.get("role") or "").lower()
        category = str(task.get("category") or "").lower()
        phase = str(task.get("phase") or "").lower()
        if category in ("interceptor", "air_patrol") or role in ("intercept", "barrier", "contest", "defense"):
            return "SWEEP"
        if category == "escort" or role == "escort":
            return "ESCORT"
        if category == "strike" or role in ("strike", "raid", "probe"):
            return "STRIKE"
        if category == "high_value_asset" or role == "support":
            return "SUPPORT"
        if "resolve" in phase:
            return "HOLD"
        return "SWEEP"

    def infer_route_style(self, task):
        category = str(task.get("category") or "").lower()
        role = str(task.get("role") or "").lower()
        if task.get("depends_on") and category == "strike":
            return "timed_ingress"
        if task.get("supports") and category in ("escort", "interceptor", "air_patrol"):
            return "screen"
        if task.get("supports") and category == "high_value_asset":
            return "protective_orbit"
        if category == "high_value_asset":
            return "orbit"
        if category == "interceptor" or role in ("intercept", "barrier"):
            return "barrier"
        if category == "escort" or role == "escort":
            return "escort"
        if category == "strike" or role in ("strike", "raid", "probe"):
            return "ingress"
        if category in ("air_defense", "target", "objective", "missile_launcher"):
            return "anchor"
        return "direct"

    def infer_fallback_route_style(self, task):
        category = str(task.get("category") or "").lower()
        if not task.get("failure_actions"):
            return None
        if category in ("strike", "escort", "interceptor", "air_patrol"):
            return "egress"
        if category in ("high_value_asset", "air_defense", "target", "objective"):
            return "close_protect"
        return "hold"

    def infer_narrative_role(self, task):
        if task.get("supports"):
            return "supporting_effort"
        if task.get("depends_on"):
            return "dependent_effort"
        if str(task.get("category") or "").lower() in ("target", "objective", "high_value_asset"):
            return "anchor"
        return "main_effort"

    def infer_commit_range_nm(self, task):
        role = str(task.get("role") or "").lower()
        category = str(task.get("category") or "").lower()
        base = int(self.host.commit_range_for_role(role or category))
        if task.get("supports"):
            return max(25, base + 10)
        if task.get("depends_on"):
            return max(20, base - 5)
        if category == "strike":
            return max(20, base - 10)
        return base

    def infer_risk_weapon(self, task):
        role = str(task.get("role") or task.get("category") or "")
        if task.get("failure_actions"):
            return min(1.0, float(self.host.risk_weapon_for_role(role)) + 0.1)
        if task.get("supports"):
            return max(0.3, float(self.host.risk_weapon_for_role(role)) - 0.1)
        return self.host.risk_weapon_for_role(role)

    def infer_launch_time_sec(self, task):
        base = max(0, int(float(task.get("start_min") or 0.0) * 60))
        category = str(task.get("category") or "").lower()
        if task.get("supports") and category in ("escort", "interceptor", "air_patrol"):
            base = max(0, base - 60)
        if task.get("depends_on"):
            base += 120
        if task.get("failure_actions") and category in ("missile_launcher", "strike"):
            base += 60
        return base

    def infer_target_priority(self, task, scenario_kind):
        category = str(task.get("category") or "").lower()
        role = str(task.get("role") or "").lower()
        priorities = []

        if scenario_kind == "integrated_air_missile_defense":
            if category in ("air_defense", "interceptor"):
                priorities.extend(["ballistic_missile", "strike_fighter"])
            elif category in ("escort", "strike"):
                priorities.extend(["interceptor", "air_defense"])
        elif scenario_kind == "strike_package":
            if category == "strike":
                priorities.extend(["sam_battery", "objective"])
            elif category == "escort":
                priorities.extend(["fighter", "escort"])
            elif category in ("air_patrol", "air_defense"):
                priorities.extend(["strike", "escort"])
        else:
            if category in ("air_patrol", "interceptor"):
                priorities.extend(["fighter", "high_value_asset"])

        if task.get("depends_on"):
            priorities.insert(0, "corridor_opener")
        if task.get("supports") and "fighter" not in priorities:
            priorities.append("fighter")
        if task.get("failure_actions"):
            priorities.append("survival_preserve")

        seen = []
        for item in priorities:
            if item and item not in seen:
                seen.append(item)
        return seen

    def infer_contingency_count(self, task):
        base = int(task.get("count") or 1)
        category = str(task.get("category") or "").lower()
        if not task.get("failure_actions"):
            return base
        if task.get("depends_on") and category == "strike":
            return max(1, base - 2)
        if task.get("depends_on") and category == "missile_launcher":
            return max(1, base - 1)
        if category in ("escort", "interceptor", "air_patrol"):
            return max(1, base - 1)
        return base

    def infer_abort_on_failure_of(self, task):
        if task.get("depends_on") and task.get("failure_actions"):
            return list(task.get("depends_on") or [])
        return []

    def infer_contingency_phase(self, task):
        if not task.get("failure_actions"):
            return None
        category = str(task.get("category") or "").lower()
        if category in ("strike", "escort", "interceptor", "air_patrol"):
            return "Egress"
        if category in ("air_defense", "target", "objective", "high_value_asset"):
            return "Close Defense"
        return "Hold"

    def build_contingency_actions(self, task_plan):
        actions = []
        for side in ("blue", "red", "neutral"):
            for task in task_plan.get(f"{side}_tasks", []):
                abort_on = self.infer_abort_on_failure_of(task)
                contingency_count = self.infer_contingency_count(task)
                if not abort_on and contingency_count == int(task.get("count") or 1):
                    continue
                actions.append(
                    {
                        "task_id": task.get("task_id"),
                        "abort_on_failure_of": abort_on,
                        "contingency_count": contingency_count,
                        "contingency_phase": self.infer_contingency_phase(task),
                    }
                )
        return actions

    def default_tasks_for_scenario(self, scenario_kind, duration_min):
        if scenario_kind == "integrated_air_missile_defense":
            return {
                "blue_tasks": [
                    self.make_task("blue", "blue_area_defense", "Defend bases", "Shape", 0, duration_min * 0.75, "air_defense", "defense", 2, "Preserve defended bases against the opening salvo."),
                    self.make_task("blue", "blue_intercept_barrier", "Intercept raid", "Raid and Intercept", duration_min * 0.15, duration_min * 0.8, "interceptor", "intercept", 2, "Disrupt the red raid before weapons reach terminal conditions."),
                    self.make_task("blue", "blue_defended_assets", "Protect assets", "Build-Up", 0, duration_min, "target", "objective", 2, "Keep at least one defended objective alive until scenario end."),
                ],
                "red_tasks": [
                    self.make_task("red", "red_ballistic_raid", "Launch missile salvo", "Raid and Intercept", duration_min * 0.2, duration_min * 0.65, "missile_launcher", "salvo", 2, "Force blue defenders into an early intercept decision."),
                    self.make_task("red", "red_escort_sweep", "Escort raid", "Raid and Intercept", duration_min * 0.15, duration_min * 0.7, "escort", "escort", 2, "Protect the raid axis and occupy blue interceptors."),
                    self.make_task("red", "red_air_raid", "Press defended zone", "Raid and Intercept", duration_min * 0.25, duration_min * 0.8, "strike", "raid", 2, "Threaten blue defended objectives and create a visible kill chain."),
                ],
                "neutral_tasks": [],
            }
        if scenario_kind == "strike_package":
            return {
                "blue_tasks": [
                    self.make_task("blue", "blue_strike_push", "Push strike package", "Ingress", 0, duration_min * 0.7, "strike", "strike", 4, "Reach weapons release conditions on the designated objective."),
                    self.make_task("blue", "blue_escort_cover", "Escort strike", "Ingress", 0, duration_min * 0.75, "escort", "escort", 2, "Hold the corridor open for the strike package."),
                    self.make_task("blue", "blue_support_orbit", "Support package", "Ingress", 0, duration_min, "high_value_asset", "support", 1, "Provide a visible anchor for the blue package narrative."),
                ],
                "red_tasks": [
                    self.make_task("red", "red_cap_defense", "Defend objective", "Commit", duration_min * 0.15, duration_min * 0.8, "air_patrol", "defense", 2, "Contest the strike package before release."),
                    self.make_task("red", "red_sam_hold", "Hold SAM ring", "Commit", duration_min * 0.1, duration_min, "air_defense", "ground_defense", 1, "Threaten the blue ingress corridor."),
                    self.make_task("red", "red_objective_hold", "Preserve objective", "Egress", 0, duration_min, "target", "objective", 1, "Keep the designated objective alive."),
                ],
                "neutral_tasks": [],
            }
        return {
            "blue_tasks": [
                self.make_task("blue", "blue_barrier_cap", "Hold corridor", "Detect", 0, duration_min * 0.75, "air_patrol", "barrier", 2, "Deny red entry into the western corridor."),
                self.make_task("blue", "blue_hvaa_cover", "Protect HVAA", "Detect", 0, duration_min, "high_value_asset", "support", 1, "Keep the blue HVAA alive and visible in replay."),
                self.make_task("blue", "blue_base_hold", "Preserve base", "Resolve", 0, duration_min, "target", "objective", 1, "Preserve the defended base."),
            ],
            "red_tasks": [
                self.make_task("red", "red_probe_push", "Probe corridor", "Engage", duration_min * 0.15, duration_min * 0.75, "air_patrol", "contest", 2, "Force blue fighters into a clear first-shot decision."),
                self.make_task("red", "red_strike_probe", "Threaten objective", "Engage", duration_min * 0.2, duration_min * 0.8, "strike", "probe", 2, "Pressure the blue objective and expose the escort chain."),
                self.make_task("red", "red_base_hold", "Preserve base", "Resolve", 0, duration_min, "target", "objective", 1, "Keep one red objective alive for outcome clarity."),
            ],
            "neutral_tasks": [],
        }

    def make_task(self, side, task_id, name, phase, start_min, end_min, category, role, count, desired_effect):
        package_name = task_id
        return {
            "task_id": task_id,
            "name": name,
            "phase": phase,
            "side": side,
            "category": category,
            "role": role,
            "count": int(count),
            "start_min": round(float(start_min), 1),
            "end_min": round(float(end_min), 1),
            "desired_effect": desired_effect,
            "objective": desired_effect,
            "package_name": package_name,
            "icon": self.host.default_icon_for_category(category),
            "depends_on": [],
            "supports": [],
            "trigger_conditions": [],
            "success_criteria": [desired_effect],
            "failure_actions": [],
        }

    def _normalize_task_list(self, tasks, side, duration_min):
        normalized = []
        if not isinstance(tasks, list):
            return normalized
        for index, task in enumerate(tasks, start=1):
            if not isinstance(task, dict):
                continue
            category = str(task.get("category") or task.get("role") or "air_patrol")
            role = str(task.get("role") or category)
            task_id = task.get("task_id") or f"{side}_{role}_{index}"
            normalized.append(
                {
                    "task_id": task_id,
                    "name": task.get("name") or task_id.replace("_", " ").title(),
                    "phase": task.get("phase") or "Operate",
                    "side": side,
                    "category": category,
                    "role": role,
                    "count": int(task.get("count") or 1),
                    "start_min": round(float(task.get("start_min") or 0.0), 1),
                    "end_min": round(float(task.get("end_min") or duration_min), 1),
                    "desired_effect": task.get("desired_effect") or task.get("objective") or "Support scenario objectives.",
                    "objective": task.get("objective") or task.get("desired_effect") or "Support scenario objectives.",
                    "package_name": task.get("package_name") or task_id,
                    "icon": task.get("icon") or self.host.default_icon_for_category(category),
                    "depends_on": list(task.get("depends_on") or []),
                    "supports": list(task.get("supports") or []),
                    "trigger_conditions": list(task.get("trigger_conditions") or []),
                    "success_criteria": list(task.get("success_criteria") or [task.get("desired_effect") or task.get("objective") or "Support scenario objectives."]),
                    "failure_actions": list(task.get("failure_actions") or []),
                    "timing_notes": list(task.get("timing_notes") or []),
                }
            )
        return normalized

    def build_task_sequence(self, task_plan):
        sequence = []
        for side in ("blue", "red", "neutral"):
            sequence.extend(task_plan.get(f"{side}_tasks", []))
        sequence.sort(key=lambda item: (float(item.get("start_min") or 0.0), float(item.get("end_min") or 0.0), item.get("side") or ""))
        return [
            {
                "task_id": item.get("task_id"),
                "name": item.get("name"),
                "phase": item.get("phase"),
                "side": item.get("side"),
                "start_min": item.get("start_min"),
                "end_min": item.get("end_min"),
                "category": item.get("category"),
                "desired_effect": item.get("desired_effect"),
                "timing_notes": list(item.get("timing_notes") or []),
                "depends_on": list(item.get("depends_on") or []),
                "supports": list(item.get("supports") or []),
                "trigger_conditions": list(item.get("trigger_conditions") or []),
                "failure_actions": list(item.get("failure_actions") or []),
            }
            for item in sequence
        ]

    def apply_task_count(self, tasks, package_name, count):
        if not count:
            return
        for task in tasks:
            if task.get("package_name") == package_name:
                task["count"] = int(count)
                return

    def default_commander_intent(self, scenario_kind):
        if scenario_kind == "integrated_air_missile_defense":
            return "Blue must absorb the opening raid, preserve a defended objective, and make the defensive kill chain easy to narrate."
        if scenario_kind == "strike_package":
            return "Blue must escort the strike package to release while red tries to break the corridor before the objective is hit."
        return "Both sides should create a legible detect-decide-engage sequence around a protected objective and a contested corridor."

    def infer_commander_intent(self, prompt, scenario_kind, desired_kpis):
        text = str(prompt or "").strip()
        base = self.default_commander_intent(scenario_kind)
        if not text:
            return base
        if desired_kpis:
            return f"{base} KPI emphasis: {', '.join(desired_kpis[:3])}."
        return base

    def collect_task_assumptions(self, prompt, center, desired_kpis, scenario_kind):
        assumptions = []
        if not str(prompt or "").strip():
            assumptions.append("Task plan was built from the scenario template because no prompt text was provided.")
        assumptions.append(f"Task plan is centered near {center.get('lat')}, {center.get('lon')} for a {scenario_kind} vignette.")
        if desired_kpis:
            assumptions.append("Task sequencing was biased toward KPI visibility: " + ", ".join(desired_kpis[:4]) + ".")
        return assumptions

    def apply_default_dependencies(self, task_plan, scenario_kind):
        blue_tasks = {task["task_id"]: task for task in task_plan.get("blue_tasks", [])}
        red_tasks = {task["task_id"]: task for task in task_plan.get("red_tasks", [])}

        if scenario_kind == "integrated_air_missile_defense":
            self.link_support(blue_tasks, "blue_area_defense", ["blue_intercept_barrier", "blue_defended_assets"])
            self.link_dependency(blue_tasks, "blue_intercept_barrier", ["blue_area_defense"])
            self.add_trigger(blue_tasks, "blue_intercept_barrier", "Activate when the first red raid track or missile salvo is detected.")
            self.add_failure_action(blue_tasks, "blue_intercept_barrier", "Fall back to close protection of defended assets if the barrier line is penetrated.")
            self.add_failure_action(blue_tasks, "blue_area_defense", "Reprioritize surviving launchers to terminal defense of the nearest defended asset.")

            self.link_support(red_tasks, "red_escort_sweep", ["red_air_raid", "red_ballistic_raid"])
            self.link_dependency(red_tasks, "red_air_raid", ["red_escort_sweep"])
            self.link_dependency(red_tasks, "red_ballistic_raid", ["red_escort_sweep"])
            self.add_trigger(red_tasks, "red_ballistic_raid", "Launch after escort sweep commits or blue barrier fighters are fixed.")
            self.add_failure_action(red_tasks, "red_air_raid", "Abort deep press and hold standoff pressure if escort attrition becomes severe.")
        elif scenario_kind == "strike_package":
            self.link_support(blue_tasks, "blue_escort_cover", ["blue_strike_push", "blue_support_orbit"])
            self.link_dependency(blue_tasks, "blue_strike_push", ["blue_escort_cover"])
            self.add_trigger(blue_tasks, "blue_strike_push", "Commit once escort cover has established corridor control or a viable gap in red defense appears.")
            self.add_failure_action(blue_tasks, "blue_strike_push", "Egress early if escort cover collapses before weapons release.")

            self.link_support(red_tasks, "red_cap_defense", ["red_sam_hold", "red_objective_hold"])
            self.link_dependency(red_tasks, "red_objective_hold", ["red_cap_defense", "red_sam_hold"])
            self.add_trigger(red_tasks, "red_cap_defense", "Commit when blue ingress is confirmed or support assets enter the threat ring.")
            self.add_failure_action(red_tasks, "red_cap_defense", "Collapse back toward the objective if forward defense loses local parity.")
        else:
            self.link_support(blue_tasks, "blue_barrier_cap", ["blue_hvaa_cover", "blue_base_hold"])
            self.link_dependency(red_tasks, "red_strike_probe", ["red_probe_push"])
            self.add_trigger(red_tasks, "red_strike_probe", "Push once blue barrier fighters are committed away from the objective axis.")
            self.add_failure_action(red_tasks, "red_probe_push", "Disengage to preserve force if blue retains barrier control and first-shot advantage.")

    def build_support_matrix(self, task_plan):
        matrix = []
        for side in ("blue", "red", "neutral"):
            for task in task_plan.get(f"{side}_tasks", []):
                if not task.get("supports"):
                    continue
                matrix.append(
                    {
                        "source_task": task.get("task_id"),
                        "source_name": task.get("name"),
                        "supports": list(task.get("supports") or []),
                    }
                )
        return matrix

    def build_dependency_summary(self, task_plan):
        summary = []
        for task in task_plan.get("task_sequence", []):
            parts = [f"{task['task_id']}"]
            if task.get("depends_on"):
                parts.append("depends on " + ", ".join(task.get("depends_on", [])))
            if task.get("supports"):
                parts.append("supports " + ", ".join(task.get("supports", [])))
            if task.get("trigger_conditions"):
                parts.append("triggered by " + "; ".join(task.get("trigger_conditions", [])[:1]))
            if task.get("failure_actions"):
                parts.append("fallback " + "; ".join(task.get("failure_actions", [])[:1]))
            summary.append(" | ".join(parts))
        return summary

    def link_dependency(self, task_map, task_id, depends_on):
        task = task_map.get(task_id)
        if not task:
            return
        for item in depends_on:
            if item and item not in task["depends_on"]:
                task["depends_on"].append(item)

    def link_support(self, task_map, source_task_id, supported_ids):
        task = task_map.get(source_task_id)
        if not task:
            return
        for item in supported_ids:
            if item and item not in task["supports"]:
                task["supports"].append(item)

    def add_trigger(self, task_map, task_id, text):
        task = task_map.get(task_id)
        if task and text and text not in task["trigger_conditions"]:
            task["trigger_conditions"].append(text)

    def add_failure_action(self, task_map, task_id, text):
        task = task_map.get(task_id)
        if task and text and text not in task["failure_actions"]:
            task["failure_actions"].append(text)