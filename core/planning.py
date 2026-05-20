import json
import re

try:
    from .task_planning import TaskPlanningService
except ImportError:
    from core.task_planning import TaskPlanningService


class PlanningService:
    def __init__(self, host):
        self.host = host
        self.task_planning_service = TaskPlanningService(host)

    def build_operational_model(self, args, scenario_name, prompt, refinement=None):
        raw_model = args.get("operational_model") or {}
        refined_model = (refinement or {}).get("recommended_model") or {}
        if refined_model and not isinstance(refined_model, dict):
            refined_model = {}

        center = args.get("center") or raw_model.get("center") or refined_model.get("center") or {}
        duration_min = float(args.get("duration_min") or raw_model.get("duration_min") or refined_model.get("duration_min") or 45)
        center_lat = float(center.get("lat") or 33.0)
        center_lon = float(center.get("lon") or 44.0)
        scenario_kind = raw_model.get("scenario_kind") or refined_model.get("scenario_kind") or self.classify_operational_prompt(prompt)
        desired_kpis = list((refinement or {}).get("desired_kpis") or refined_model.get("engagement_rules", {}).get("desired_kpis") or self.infer_desired_kpis(prompt, scenario_kind))
        task_plan = raw_model.get("task_plan") or refined_model.get("task_plan")
        task_plan = self.task_planning_service.build_task_plan(
            prompt,
            scenario_kind,
            duration_min,
            {"lat": center_lat, "lon": center_lon},
            desired_kpis,
            raw_model={"task_plan": task_plan} if task_plan else raw_model,
        )

        mission = raw_model.get("mission") if isinstance(raw_model.get("mission"), dict) else {}
        refined_mission = refined_model.get("mission") if isinstance(refined_model.get("mission"), dict) else {}
        title = mission.get("title") or refined_mission.get("title") or scenario_name.replace("_", " ").title()
        summary = mission.get("summary") or refined_mission.get("summary") or self.default_operational_summary(scenario_kind)
        objectives = mission.get("objectives") or refined_mission.get("objectives") or self.task_planning_service.derive_objectives_from_task_plan(task_plan, scenario_kind, desired_kpis)
        phases = raw_model.get("phases") or refined_model.get("phases") or self.task_planning_service.derive_phases_from_task_plan(task_plan, duration_min, scenario_kind)
        engagement_rules = raw_model.get("engagement_rules") or refined_model.get("engagement_rules") or self.task_planning_service.derive_engagement_rules_from_task_plan(task_plan, scenario_kind, desired_kpis)
        forces = self.normalize_force_packages(raw_model.get("forces") or refined_model.get("forces") or self.task_planning_service.derive_force_packages_from_task_plan(task_plan, scenario_kind), scenario_kind)

        return {
            "version": "1.0",
            "scenario_name": scenario_name,
            "scenario_kind": scenario_kind,
            "source_prompt": prompt,
            "prompt_refinement": refinement,
            "task_plan": task_plan,
            "duration_min": duration_min,
            "center": {"lat": center_lat, "lon": center_lon},
            "asset_profile": self.host.resolve_operational_asset_profile(scenario_kind),
            "mission": {
                "title": title,
                "summary": summary,
                "objectives": objectives,
            },
            "forces": forces,
            "phases": phases,
            "engagement_rules": engagement_rules,
        }

    def refine_operational_prompt_payload(self, args, scenario_name, prompt):
        raw_model = args.get("operational_model") or {}
        if raw_model and not isinstance(raw_model, dict):
            raw_model = {}

        scenario_kind = raw_model.get("scenario_kind") or self.classify_operational_prompt(prompt)
        duration_min = self.infer_duration_from_prompt(
            prompt,
            args.get("duration_min") or raw_model.get("duration_min") or 45,
        )
        center = self.infer_center_from_prompt(
            prompt,
            args.get("center") or raw_model.get("center") or None,
        )
        replay_focus = self.infer_replay_focus(prompt, scenario_kind)
        desired_kpis = self.infer_desired_kpis(prompt, scenario_kind)
        task_plan = self.task_planning_service.build_task_plan(prompt, scenario_kind, duration_min, center, desired_kpis, raw_model=raw_model)
        force_packages = self.task_planning_service.derive_force_packages_from_task_plan(task_plan, scenario_kind)
        mission_title = self.infer_mission_title(prompt, scenario_name, scenario_kind)
        mission_summary = self.infer_mission_summary(prompt, scenario_kind, replay_focus)
        objectives = self.task_planning_service.derive_objectives_from_task_plan(task_plan, scenario_kind, desired_kpis)
        engagement_rules = self.task_planning_service.derive_engagement_rules_from_task_plan(task_plan, scenario_kind, desired_kpis)
        engagement_rules["narrative_focus"] = " ".join(replay_focus)
        engagement_rules["desired_kpis"] = desired_kpis
        filled_by_system = self.identify_system_filled_fields(prompt, raw_model)
        confidence = self.assess_refinement_confidence(prompt, raw_model, replay_focus, desired_kpis, filled_by_system)
        low_confidence = confidence["level"] in ("low", "medium")
        questions_needed = self.build_questions_needed(scenario_kind, low_confidence, filled_by_system)

        recommended_model = {
            "scenario_kind": scenario_kind,
            "duration_min": duration_min,
            "center": center,
            "mission": {
                "title": mission_title,
                "summary": mission_summary,
                "objectives": objectives,
            },
            "task_plan": task_plan,
            "forces": force_packages,
            "phases": self.task_planning_service.derive_phases_from_task_plan(task_plan, duration_min, scenario_kind),
            "engagement_rules": engagement_rules,
        }

        return {
            "source_prompt": prompt,
            "scenario_name": scenario_name,
            "scenario_kind": scenario_kind,
            "duration_min": duration_min,
            "center": center,
            "theater": self.describe_theater(center),
            "replay_focus": replay_focus,
            "desired_kpis": desired_kpis,
            "task_plan_summary": self.task_planning_service.summarize_task_plan(task_plan),
            "force_guidance": self.summarize_force_guidance(force_packages),
            "assumptions": self.collect_prompt_assumptions(prompt, raw_model, center, duration_min),
            "filled_by_system": filled_by_system,
            "confidence": confidence,
            "low_confidence": low_confidence,
            "questions_needed": questions_needed,
            "recommended_model": recommended_model,
        }

    def classify_operational_prompt(self, prompt):
        text = (prompt or "").lower()
        if any(word in text for word in ["ballistic", "missile", "反导", "弹道", "防空"]):
            return "integrated_air_missile_defense"
        if any(word in text for word in ["strike", "打击", "突击", "纵深"]):
            return "strike_package"
        return "counter_air"

    def default_operational_summary(self, scenario_kind):
        if scenario_kind == "integrated_air_missile_defense":
            return "Blue force defends critical bases against a red missile and air raid while preserving a counter-strike option."
        if scenario_kind == "strike_package":
            return "Blue force pushes a strike package through contested airspace to destroy a red objective while managing escorts and defensive reactions."
        return "Blue and red air packages contest control of a corridor while protecting a high-value asset and key ground node."

    def infer_mission_title(self, prompt, scenario_name, scenario_kind):
        text = str(prompt or "").strip()
        if text:
            sentence = re.split(r"[。.!?\n]", text)[0].strip()
            if sentence:
                return sentence[:72]
        if scenario_kind == "integrated_air_missile_defense":
            return f"{scenario_name.replace('_', ' ').title()} IAMD Showcase"
        if scenario_kind == "strike_package":
            return f"{scenario_name.replace('_', ' ').title()} Strike Package"
        return scenario_name.replace("_", " ").title()

    def infer_mission_summary(self, prompt, scenario_kind, replay_focus):
        base = self.default_operational_summary(scenario_kind)
        if not prompt:
            return base
        prompt_text = str(prompt).strip()
        if len(prompt_text) <= 180:
            return f"{base} Prompt intent: {prompt_text}."
        return f"{base} Replay emphasis: {'; '.join(replay_focus)}."

    def infer_operational_objectives(self, prompt, scenario_kind, desired_kpis):
        objectives = list(self.default_operational_objectives(scenario_kind))
        kpi_text = ", ".join(desired_kpis[:3])
        objectives.append({
            "side": "both",
            "description": f"Produce a replay and analysis package with clear KPI evidence for {kpi_text}."
        })
        if any(token in str(prompt or "").lower() for token in ["watch", "回放", "展示", "讲解", "showcase"]):
            objectives.append({
                "side": "both",
                "description": "Create a visually legible kill chain that is easy to narrate in Mystic."
            })
        return objectives

    def default_operational_objectives(self, scenario_kind):
        if scenario_kind == "integrated_air_missile_defense":
            return [
                {"side": "blue", "description": "Preserve at least one defended base until scenario end."},
                {"side": "blue", "description": "Intercept the first red missile salvo before terminal impact."},
                {"side": "red", "description": "Land at least one strike on a blue objective."},
            ]
        if scenario_kind == "strike_package":
            return [
                {"side": "blue", "description": "Escort the strike package to weapons release and exit the threat ring."},
                {"side": "blue", "description": "Destroy the designated red objective area."},
                {"side": "red", "description": "Disrupt the strike package before it reaches release conditions."},
            ]
        return [
            {"side": "blue", "description": "Hold the western corridor and protect the blue high-value asset."},
            {"side": "red", "description": "Break into the corridor and attrit blue fighters."},
            {"side": "both", "description": "Generate a clear detect-decide-engage sequence for replay and analysis."},
        ]

    def default_operational_phases(self, scenario_kind, duration_min):
        first = round(duration_min * 0.2, 1)
        second = round(duration_min * 0.55, 1)
        if scenario_kind == "integrated_air_missile_defense":
            return [
                {"name": "Build-Up", "start_min": 0, "end_min": first, "summary": "Blue sensors build tracks while red launchers position for the opening salvo."},
                {"name": "Raid and Intercept", "start_min": first, "end_min": second, "summary": "Red missiles and escorts commit; blue air defense and interceptors react."},
                {"name": "Damage Assessment", "start_min": second, "end_min": duration_min, "summary": "Surviving forces consolidate, and the battle result becomes visible for replay."},
            ]
        if scenario_kind == "strike_package":
            return [
                {"name": "Ingress", "start_min": 0, "end_min": first, "summary": "Blue strike and escort packages enter the corridor and shape the air picture."},
                {"name": "Commit", "start_min": first, "end_min": second, "summary": "Red defenders contest the package and force weapons employment decisions."},
                {"name": "Egress", "start_min": second, "end_min": duration_min, "summary": "Survivors disengage and the outcome becomes easy to narrate in replay."},
            ]
        return [
            {"name": "Detect", "start_min": 0, "end_min": first, "summary": "Both sides establish tracks and expose the first tactical choices."},
            {"name": "Engage", "start_min": first, "end_min": second, "summary": "Air packages merge and the first decisive shots occur."},
            {"name": "Resolve", "start_min": second, "end_min": duration_min, "summary": "Remaining forces withdraw or press, producing a clean replay ending."},
        ]

    def default_engagement_rules(self, scenario_kind):
        if scenario_kind == "integrated_air_missile_defense":
            return {
                "commit_range_nm": 45,
                "max_weapons_per_target": 2,
                "priority_targets": ["ballistic_missile", "strike_fighter", "escort"],
                "narrative_focus": "Show the detection chain from sensor track initiation to intercept or impact.",
            }
        if scenario_kind == "strike_package":
            return {
                "commit_range_nm": 35,
                "max_weapons_per_target": 2,
                "priority_targets": ["sam_battery", "escort", "objective"],
                "narrative_focus": "Highlight ingress timing, escort decisions, and strike release windows.",
            }
        return {
            "commit_range_nm": 30,
            "max_weapons_per_target": 1,
            "priority_targets": ["high_value_asset", "fighter", "target"],
            "narrative_focus": "Keep the replay centered on first detection, first shot, and first kill.",
        }

    def normalize_force_packages(self, raw_forces, scenario_kind):
        if raw_forces is None:
            return self.default_force_packages(scenario_kind)

        grouped = {"blue": [], "red": [], "neutral": []}
        if isinstance(raw_forces, list):
            for package in raw_forces:
                if not isinstance(package, dict):
                    continue
                side = str(package.get("side") or "neutral").lower()
                grouped.setdefault(side, []).append(package)
        elif isinstance(raw_forces, dict):
            for side in grouped:
                values = raw_forces.get(side) or []
                if isinstance(values, list):
                    grouped[side] = [value for value in values if isinstance(value, dict)]
        else:
            return self.default_force_packages(scenario_kind)

        for side, packages in grouped.items():
            normalized = []
            for index, package in enumerate(packages, start=1):
                category = str(package.get("category") or package.get("role") or "fighter")
                normalized_package = {
                    "name": package.get("name") or f"{side}_{category}_{index}",
                    "side": side,
                    "role": package.get("role") or category,
                    "category": category,
                    "count": int(package.get("count") or 1),
                    "icon": package.get("icon") or self.host.default_icon_for_category(category),
                }
                for key in (
                    "task_id",
                    "depends_on",
                    "supports",
                    "trigger_conditions",
                    "failure_actions",
                    "mission_task",
                    "route_style",
                    "fallback_route_style",
                    "narrative_role",
                    "commit_range_nm",
                    "risk_weapon",
                    "target_priority",
                    "launch_time_sec",
                    "base_count",
                    "task_phase",
                    "timing_notes",
                    "contingency_count",
                    "abort_on_failure_of",
                    "contingency_phase",
                ):
                    if key in package and package.get(key) not in (None, [], ""):
                        normalized_package[key] = package.get(key)
                normalized.append(normalized_package)
            grouped[side] = normalized
        return grouped

    def default_force_packages(self, scenario_kind):
        if scenario_kind == "integrated_air_missile_defense":
            return {
                "blue": [
                    {"name": "blue_defended_base", "side": "blue", "role": "objective", "category": "target", "count": 2, "icon": "airbase"},
                    {"name": "blue_air_defense", "side": "blue", "role": "defense", "category": "air_defense", "count": 2, "icon": "command_truck"},
                    {"name": "blue_interceptors", "side": "blue", "role": "intercept", "category": "interceptor", "count": 2, "icon": "F-16"},
                ],
                "red": [
                    {"name": "red_launchers", "side": "red", "role": "salvo", "category": "missile_launcher", "count": 2, "icon": "Scud_Launcher"},
                    {"name": "red_escorts", "side": "red", "role": "escort", "category": "escort", "count": 2, "icon": "fighter"},
                    {"name": "red_strikers", "side": "red", "role": "raid", "category": "strike", "count": 2, "icon": "fighter"},
                ],
                "neutral": [],
            }
        if scenario_kind == "strike_package":
            return {
                "blue": [
                    {"name": "blue_strike", "side": "blue", "role": "strike", "category": "strike", "count": 4, "icon": "fighter"},
                    {"name": "blue_escort", "side": "blue", "role": "escort", "category": "escort", "count": 2, "icon": "fighter"},
                    {"name": "blue_support", "side": "blue", "role": "support", "category": "high_value_asset", "count": 1, "icon": "aircraft"},
                ],
                "red": [
                    {"name": "red_objective", "side": "red", "role": "objective", "category": "target", "count": 1, "icon": "target"},
                    {"name": "red_patrol", "side": "red", "role": "defense", "category": "air_patrol", "count": 2, "icon": "fighter"},
                    {"name": "red_sam", "side": "red", "role": "ground_defense", "category": "air_defense", "count": 1, "icon": "command_truck"},
                ],
                "neutral": [],
            }
        return {
            "blue": [
                {"name": "blue_cap", "side": "blue", "role": "barrier", "category": "air_patrol", "count": 2, "icon": "fighter"},
                {"name": "blue_hvaa", "side": "blue", "role": "support", "category": "high_value_asset", "count": 1, "icon": "aircraft"},
                {"name": "blue_base", "side": "blue", "role": "objective", "category": "target", "count": 1, "icon": "airbase"},
            ],
            "red": [
                {"name": "red_patrol", "side": "red", "role": "contest", "category": "air_patrol", "count": 2, "icon": "fighter"},
                {"name": "red_strike", "side": "red", "role": "probe", "category": "strike", "count": 2, "icon": "fighter"},
                {"name": "red_base", "side": "red", "role": "objective", "category": "target", "count": 1, "icon": "airbase"},
            ],
            "neutral": [],
        }

    def infer_duration_from_prompt(self, prompt, fallback):
        text = str(prompt or "")
        match = re.search(r"(\d+(?:\.\d+)?)\s*(分钟|min|minutes?)", text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
        if any(token in text.lower() for token in ["short", "快节奏", "短时", "速战"]):
            return 30.0
        if any(token in text.lower() for token in ["long", "持久", "持续", "extended"]):
            return 60.0
        return float(fallback)

    def infer_center_from_prompt(self, prompt, fallback_center):
        if isinstance(fallback_center, dict) and fallback_center.get("lat") is not None and fallback_center.get("lon") is not None:
            return {"lat": float(fallback_center.get("lat")), "lon": float(fallback_center.get("lon"))}

        text = str(prompt or "").lower()
        theaters = [
            (("iran", "israel", "middle east", "伊朗", "以色列", "中东"), {"lat": 33.0, "lon": 44.0, "label": "Middle East"}),
            (("taiwan", "strait", "台湾", "台海"), {"lat": 23.8, "lon": 121.0, "label": "Taiwan Strait"}),
            (("ukraine", "russia", "乌克兰", "俄罗斯"), {"lat": 48.5, "lon": 36.0, "label": "Eastern Europe"}),
            (("south china sea", "南海"), {"lat": 12.0, "lon": 114.0, "label": "South China Sea"}),
        ]
        for keywords, center in theaters:
            if any(keyword in text for keyword in keywords):
                return {"lat": center["lat"], "lon": center["lon"]}
        return {"lat": 33.0, "lon": 44.0}

    def describe_theater(self, center):
        lat = round(float(center.get("lat") or 0.0), 3)
        lon = round(float(center.get("lon") or 0.0), 3)
        return f"centered near {lat}, {lon}"

    def infer_replay_focus(self, prompt, scenario_kind):
        text = str(prompt or "").lower()
        focus = []
        if any(token in text for token in ["missile", "导弹", "intercept", "拦截"]):
            focus.append("Show the missile raid, defensive reaction, and intercept geometry.")
        if any(token in text for token in ["detect", "探测", "sensor", "雷达"]):
            focus.append("Make the sensor-to-shooter chain legible from first track to weapon employment.")
        if any(token in text for token in ["escort", "护航", "fighter", "战斗机", "merge"]):
            focus.append("Keep fighter escort interactions visible before and during the merge.")
        if any(token in text for token in ["showcase", "展示", "回放", "讲解", "watch"]):
            focus.append("Favor clean timing windows and camera-friendly decisive moments.")
        if not focus:
            focus.append(self.default_engagement_rules(scenario_kind)["narrative_focus"])
        return focus

    def infer_desired_kpis(self, prompt, scenario_kind):
        text = str(prompt or "").lower()
        kpis = ["first_detection_time", "first_shot_time", "first_hit_time", "kill_chain_closure_score"]
        if scenario_kind in ("integrated_air_missile_defense", "strike_package") or any(token in text for token in ["target", "目标", "base", "基地", "survival", "存活"]):
            kpis.append("objective_survival_rate")
        if any(token in text for token in ["intercept", "拦截", "missile", "导弹"]):
            kpis.append("intercept_success_rate")
        return kpis

    def infer_force_packages_from_prompt(self, prompt, scenario_kind):
        task_plan = self.task_planning_service.build_task_plan(
            prompt,
            scenario_kind,
            self.infer_duration_from_prompt(prompt, 45),
            self.infer_center_from_prompt(prompt, None),
            self.infer_desired_kpis(prompt, scenario_kind),
            raw_model=None,
        )
        return self.task_planning_service.derive_force_packages_from_task_plan(task_plan, scenario_kind)

    def summarize_force_guidance(self, forces):
        guidance = []
        for side in ("blue", "red", "neutral"):
            packages = forces.get(side) or []
            if not packages:
                continue
            items = [f"{package['name']} x{package['count']} ({package['category']})" for package in packages]
            guidance.append(f"{side}: " + ", ".join(items))
        return guidance

    def collect_prompt_assumptions(self, prompt, raw_model, center, duration_min):
        assumptions = []
        text = str(prompt or "").strip()
        if not text:
            assumptions.append("No user prompt was provided, so the system used a default operational template.")
        if not raw_model.get("forces"):
            assumptions.append("Force packages were inferred from the scenario template and prompt keywords.")
        if not raw_model.get("mission"):
            assumptions.append("Mission summary and objectives were expanded from defaults because the prompt did not provide a full task model.")
        if not raw_model.get("center"):
            assumptions.append(f"Theater center was inferred or defaulted to {center['lat']}, {center['lon']}.")
        if not raw_model.get("duration_min"):
            assumptions.append(f"Scenario duration was set to {duration_min} minutes using prompt cues or defaults.")
        return assumptions

    def identify_system_filled_fields(self, prompt, raw_model):
        text = str(prompt or "").strip().lower()
        filled = []
        if not raw_model.get("scenario_kind") and not any(token in text for token in ["ballistic", "missile", "反导", "弹道", "防空", "strike", "打击", "突击", "纵深", "counter air", "空战"]):
            filled.append("scenario_kind")
        if not raw_model.get("center") and not any(token in text for token in ["iran", "israel", "middle east", "伊朗", "以色列", "中东", "taiwan", "strait", "台湾", "台海", "ukraine", "russia", "乌克兰", "俄罗斯", "south china sea", "南海"]):
            filled.append("center")
        if not raw_model.get("duration_min") and not re.search(r"(\d+(?:\.\d+)?)\s*(分钟|min|minutes?)", text, flags=re.IGNORECASE):
            filled.append("duration_min")
        if not raw_model.get("forces"):
            filled.append("force_packages")
        if not raw_model.get("mission"):
            filled.append("mission_summary")
            filled.append("mission_objectives")
        if not any(token in text for token in ["探测", "detect", "发射", "shot", "命中", "hit", "生存", "survival", "闭环", "kpi", "指标"]):
            filled.append("desired_kpis")
        if not any(token in text for token in ["回放", "展示", "showcase", "讲解", "watch", "mystic"]):
            filled.append("replay_focus")
        return filled

    def assess_refinement_confidence(self, prompt, raw_model, replay_focus, desired_kpis, filled_by_system):
        text = str(prompt or "").strip()
        score = 100
        reasons = []
        if not text:
            score -= 40
            reasons.append("No prompt text was provided.")
        elif len(text) < 20:
            score -= 30
            reasons.append("The prompt is very short, so mission intent had to be inferred from defaults.")
        elif len(text) < 50:
            score -= 15
            reasons.append("The prompt is concise and leaves several operational fields implicit.")
        if len(filled_by_system) >= 5:
            score -= 30
            reasons.append("Most operational fields were filled by the system rather than explicitly provided.")
        elif len(filled_by_system) >= 3:
            score -= 15
            reasons.append("Several operational fields were filled by the system.")
        if not raw_model.get("forces"):
            score -= 10
            reasons.append("Force composition was inferred from template defaults and prompt keywords.")
        if not raw_model.get("mission"):
            score -= 5
            reasons.append("Mission summary and objectives were expanded from template defaults.")
        if not replay_focus:
            score -= 5
            reasons.append("Replay focus had to fall back to the scenario template.")
        if not desired_kpis:
            score -= 5
            reasons.append("KPI priorities had to fall back to the scenario template.")
        score = max(score, 10)
        if score >= 80:
            level = "high"
        elif score >= 60:
            level = "medium"
        else:
            level = "low"
        return {
            "level": level,
            "score": score,
            "reasons": reasons,
        }

    def build_questions_needed(self, scenario_kind, low_confidence, filled_by_system):
        if not low_confidence:
            return []

        prompts = []
        if "scenario_kind" in filled_by_system:
            prompts.append(
                {
                    "field": "scenario_kind",
                    "question": "你更想看哪一类对抗？",
                    "why": "场景类型会直接决定资产组合、飞行路线和讲解重点。",
                    "suggestions": [
                        {"label": "防空反导", "value": "integrated_air_missile_defense"},
                        {"label": "空袭打击", "value": "strike_package"},
                        {"label": "制空空战", "value": "counter_air"},
                    ],
                }
            )
        if "center" in filled_by_system:
            prompts.append(
                {
                    "field": "center",
                    "question": "你希望把场景放在哪个方向或战区？",
                    "why": "战区会影响地理背景、资产模板选择和回放叙事。",
                    "suggestions": [
                        {"label": "中东", "value": "middle_east"},
                        {"label": "台海", "value": "taiwan_strait"},
                        {"label": "东欧", "value": "eastern_europe"},
                        {"label": "南海", "value": "south_china_sea"},
                    ],
                }
            )
        if "force_packages" in filled_by_system:
            prompts.append(
                {
                    "field": "forces",
                    "question": "你更在意哪种兵力观感？",
                    "why": "兵力数量和类型决定交战密度、武器齐射和 Mystic 可看性。",
                    "suggestions": [
                        {"label": "少量高质量，对抗清楚", "value": "small_clear_packages"},
                        {"label": "中等规模，兼顾讲解和热闹", "value": "balanced_packages"},
                        {"label": "大规模齐射，视觉冲击强", "value": "dense_salvo_packages"},
                    ],
                }
            )
        if "desired_kpis" in filled_by_system:
            prompts.append(
                {
                    "field": "desired_kpis",
                    "question": "你最想突出哪些评估指标？",
                    "why": "KPI 会决定回放计划如何排序关键镜头。",
                    "suggestions": [
                        {"label": "首探测/首发射/首命中", "value": "tempo_kpis"},
                        {"label": "目标存活率", "value": "objective_survival_rate"},
                        {"label": "拦截成功率", "value": "intercept_success_rate"},
                        {"label": "交战链闭环评分", "value": "kill_chain_closure_score"},
                    ],
                }
            )
        if "replay_focus" in filled_by_system:
            prompts.append(
                {
                    "field": "replay_focus",
                    "question": "你希望回放更偏哪种讲解风格？",
                    "why": "不同风格会影响镜头停留和讲解词组织方式。",
                    "suggestions": [
                        {"label": "先讲探测链，再讲武器链", "value": "sensor_to_shooter_story"},
                        {"label": "重点看导弹飞行和拦截", "value": "missile_intercept_story"},
                        {"label": "重点看战斗机缠斗与护航决策", "value": "fighter_decision_story"},
                    ],
                }
            )
        if "duration_min" in filled_by_system:
            prompts.append(
                {
                    "field": "duration_min",
                    "question": "你希望演示节奏更短更紧，还是更完整？",
                    "why": "时长会改变阶段划分和回放密度。",
                    "suggestions": [
                        {"label": "20-30 分钟，快节奏", "value": "short"},
                        {"label": "40-50 分钟，平衡", "value": "balanced"},
                        {"label": "60 分钟以上，完整过程", "value": "long"},
                    ],
                }
            )
        if not prompts:
            prompts.append(
                {
                    "field": "user_intent",
                    "question": "你更想看清楚的交战链，还是更热闹的火力场面？",
                    "why": "当用户自己也不确定时，这个选择最能帮助系统定调。",
                    "suggestions": [
                        {"label": "交战链清楚，便于讲解", "value": "clear_chain"},
                        {"label": "火力密集，更有视觉冲击", "value": "dense_firepower"},
                        {"label": "两者平衡", "value": "balanced_showcase"},
                    ],
                }
            )
        return prompts

    def render_prompt_refinement_markdown(self, refinement):
        if not refinement:
            return "# Prompt Brief\n\nPrompt refinement was not enabled.\n"
        lines = ["# Prompt Brief", "", "## Normalized Request", ""]
        lines.append(f"- scenario_kind: {refinement.get('scenario_kind')}")
        lines.append(f"- duration_min: {refinement.get('duration_min')}")
        center = refinement.get("center") or {}
        lines.append(f"- center: {center.get('lat')}, {center.get('lon')}")
        lines.append(f"- theater: {refinement.get('theater')}")
        confidence = refinement.get("confidence") or {}
        lines.append(f"- confidence_level: {confidence.get('level')}")
        lines.append(f"- confidence_score: {confidence.get('score')}")
        lines.append(f"- low_confidence: {refinement.get('low_confidence')}")
        lines.extend(["", "## Replay Focus", ""])
        for item in refinement.get("replay_focus", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Desired KPIs", ""])
        for item in refinement.get("desired_kpis", []):
            lines.append(f"- {item}")
        if refinement.get("task_plan_summary"):
            lines.extend(["", "## Task Plan", ""])
            for item in refinement.get("task_plan_summary", []):
                lines.append(f"- {item}")
        dependency_summary = ((refinement.get("recommended_model") or {}).get("task_plan") or {}).get("dependency_summary") or []
        if dependency_summary:
            lines.extend(["", "## Task Dependencies", ""])
            for item in dependency_summary:
                lines.append(f"- {item}")
        lines.extend(["", "## System-Filled Fields", ""])
        for item in refinement.get("filled_by_system", []):
            lines.append(f"- {item}")
        if confidence.get("reasons"):
            lines.extend(["", "## Confidence Notes", ""])
            for item in confidence.get("reasons", []):
                lines.append(f"- {item}")
        lines.extend(["", "## Force Guidance", ""])
        for item in refinement.get("force_guidance", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Assumptions", ""])
        for item in refinement.get("assumptions", []):
            lines.append(f"- {item}")
        if refinement.get("questions_needed"):
            lines.extend(["", "## Questions Needed", ""])
            for item in refinement.get("questions_needed", []):
                lines.append(f"- {item.get('field')}: {item.get('question')}")
                lines.append(f"- why: {item.get('why')}")
                for suggestion in item.get("suggestions", []):
                    lines.append(f"- suggestion: {suggestion.get('label')} -> {suggestion.get('value')}")
        return "\n".join(lines).rstrip() + "\n"

    def render_project_settings_plan_markdown(self, model, refinement=None):
        model = model or {}
        refinement = refinement or {}
        mission = model.get("mission") or {}
        forces = model.get("forces") or {}
        engagement_rules = model.get("engagement_rules") or {}
        asset_profile = model.get("asset_profile") or {}
        center = model.get("center") or {}
        duration_min = model.get("duration_min")
        scenario_kind = model.get("scenario_kind") or refinement.get("scenario_kind") or "counter_air"
        theater_text = refinement.get("theater") or self.describe_theater(center)

        lines = [
            "# Operational Project Brief",
            "",
            "本文件是项目详细介绍，不是技术配置清单。",
            "建议用户优先修改本文件中的“User Editable Brief”文字内容，再让模型按本文件生成场景。",
            "",
            "## Scenario Overview",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Scenario Name | {model.get('scenario_name')} |",
            f"| Scenario Kind | {scenario_kind} |",
            f"| Duration (min) | {duration_min} |",
            f"| Theater Center | {center.get('lat')}, {center.get('lon')} |",
            f"| Theater Description | {theater_text} |",
            "",
            "## Mission Story",
            "",
            f"- Title: {mission.get('title')}",
            f"- Narrative: {mission.get('summary')}",
            "",
            "## Objectives",
            "",
            "| Side | Objective |",
            "| --- | --- |",
        ]
        for obj in mission.get("objectives") or []:
            lines.append(f"| {obj.get('side') or 'unknown'} | {obj.get('description') or ''} |")

        lines.extend(["", "## Task Script", ""])
        for phase in model.get("phases") or []:
            lines.append(f"### {phase.get('name')}")
            lines.append(f"- Time Window: {phase.get('start_min')} -> {phase.get('end_min')} min")
            lines.append(f"- Script Intent: {phase.get('summary')}")
            lines.append("")

        lines.extend(["## Red-Blue Battle Setup", ""])
        for side in ("blue", "red", "neutral"):
            packages = list(forces.get(side) or [])
            lines.append(f"### {side.title()}")
            if not packages:
                lines.append("- none")
                lines.append("")
                continue
            lines.extend([
                "",
                "| Unit | Role | Category | Count | Mission Task | Route Style | Commit Range (nm) |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ])
            for pkg in packages:
                lines.append(
                    "| {name} | {role} | {category} | {count} | {task} | {route} | {commit} |".format(
                        name=pkg.get("name") or "",
                        role=pkg.get("role") or "",
                        category=pkg.get("category") or "",
                        count=pkg.get("count") or "",
                        task=pkg.get("mission_task") or "",
                        route=pkg.get("route_style") or "",
                        commit=pkg.get("commit_range_nm") if pkg.get("commit_range_nm") is not None else "",
                    )
                )
            lines.append("")

        lines.extend([
            "## Rules Of Engagement",
            "",
            "| Rule | Value |",
            "| --- | --- |",
            f"| commit_range_nm | {engagement_rules.get('commit_range_nm')} |",
            f"| max_weapons_per_target | {engagement_rules.get('max_weapons_per_target')} |",
            f"| priority_targets | {engagement_rules.get('priority_targets')} |",
            f"| narrative_focus | {engagement_rules.get('narrative_focus')} |",
            f"| desired_kpis | {engagement_rules.get('desired_kpis')} |",
        ])

        lines.extend([
            "",
            "## Platform / Component Baseline",
            "",
            "| Item | Value |",
            "| --- | --- |",
            f"| Blue Fighter Type | {asset_profile.get('blue_fighter_type')} |",
            f"| Red Fighter Type | {asset_profile.get('red_fighter_type')} |",
            f"| Blue Support Type | {asset_profile.get('blue_support_type')} |",
            f"| Red Support Type | {asset_profile.get('red_support_type')} |",
            f"| Blue Target Type | {asset_profile.get('blue_target_type')} |",
            f"| Red Target Type | {asset_profile.get('red_target_type')} |",
            f"| Blue Air Defense Type | {asset_profile.get('blue_air_defense_type') or asset_profile.get('blue_air_defense_battery_type')} |",
            f"| Red Air Defense Type | {asset_profile.get('red_air_defense_type')} |",
            f"| Blue Missile Launcher Type | {asset_profile.get('blue_missile_launcher_type')} |",
            f"| Red Missile Launcher Type | {asset_profile.get('red_missile_launcher_type')} |",
            "",
            "说明：组件武器传感器的细节参数主要由上述类型定义与 include 资产文件决定。",
        ])

        task_plan = model.get("task_plan") or {}
        if task_plan:
            lines.extend(["", "## Task Graph Summary", ""])
            for item in self.task_planning_service.summarize_task_plan(task_plan):
                lines.append(f"- {item}")
            dependency_summary = task_plan.get("dependency_summary") or []
            if dependency_summary:
                lines.extend(["", "### Task Dependencies", ""])
                for item in dependency_summary:
                    lines.append(f"- {item}")

        lines.extend([
            "",
            "## User Editable Brief",
            "",
            "请直接修改下面文本块（自然语言），生成时会优先读取这里：",
            "",
            "<!-- BRIEF_EDITABLE_START -->",
            "Scenario Theme:",
            "Theater / Territory:",
            "Blue Side Description:",
            "Red Side Description:",
            "Battle Intensity:",
            "Mission Script:",
            "Platform Notes:",
            "Component / Weapon / Sensor Notes:",
            "Victory / End-State Criteria:",
            "<!-- BRIEF_EDITABLE_END -->",
            "",
            "## Review Checklist",
            "",
            "- 作战场景、领地、敌我关系是否清晰",
            "- 任务剧本是否完整可讲",
            "- 平台与组件参数是否满足你的预期",
            "- 回放讲解主线是否明确",
            "",
            "## Edit Notes",
            "",
            "- 推荐优先编辑 User Editable Brief；该部分最适合非技术用户。",
            "- 如需精确控制，再编辑下方 JSON。",
        ])

        editable_model = {
            "scenario_kind": model.get("scenario_kind"),
            "duration_min": model.get("duration_min"),
            "center": model.get("center"),
            "mission": model.get("mission"),
            "forces": model.get("forces"),
            "phases": model.get("phases"),
            "engagement_rules": model.get("engagement_rules"),
            "task_plan": model.get("task_plan"),
        }
        lines.extend([
            "",
            "## Editable Model (JSON)",
            "",
            "修改下面 JSON 后，可直接作为后续生成输入。",
            "",
            "```json",
            json.dumps(editable_model, ensure_ascii=False, indent=2),
            "```",
        ])
        return "\n".join(lines).rstrip() + "\n"

    def extract_project_model_from_plan_text(self, text):
        source = str(text or "")
        if not source.strip():
            return None

        patterns = [
            r"##\s*Editable\s*Model\s*\(JSON\).*?```json\s*(\{.*?\})\s*```",
            r"```json\s*(\{.*?\})\s*```",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            candidate = match.group(1)
            try:
                data = json.loads(candidate)
                return data if isinstance(data, dict) else None
            except Exception:
                continue
        return None

    def extract_prompt_from_project_brief_text(self, text):
        source = str(text or "")
        if not source.strip():
            return None
        block = None
        marker = re.search(
            r"<!--\s*BRIEF_EDITABLE_START\s*-->(.*?)<!--\s*BRIEF_EDITABLE_END\s*-->",
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if marker:
            block = marker.group(1)
        else:
            block = source

        lines = []
        for raw in block.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("<!--"):
                continue
            lines.append(stripped)
        prompt = "\n".join(lines).strip()
        return prompt or None