import json
from pathlib import Path


class ShowcaseService:
    def __init__(self, host):
        self.host = host

    def build_showcase_package(self, args):
        scenario_dir = Path(self.host.require_str(args, "scenario_dir"))
        self.host.assert_path_allowed(scenario_dir, write=True, purpose="build_showcase_package(scenario_dir)")
        if not scenario_dir.exists():
            return self.host.wrap({"error": "scenario_dir not found"})

        model_path = Path(args["model_path"]) if args.get("model_path") else self.host.find_latest_matching_file(
            scenario_dir / "doc",
            "*.model.json",
        )
        analysis_path = Path(args["analysis_path"]) if args.get("analysis_path") else scenario_dir / "doc" / "ANALYSIS.json"

        model = self.host.read_json(model_path) if model_path and model_path.exists() else None
        prompt_refinement = None
        if isinstance(args.get("prompt_refinement"), dict):
            prompt_refinement = args.get("prompt_refinement")
        elif model:
            prompt_refinement = model.get("prompt_refinement")

        analysis = None
        if analysis_path and analysis_path.exists():
            self.host.assert_path_allowed(analysis_path, write=False, purpose="build_showcase_package(analysis)")
            analysis = self.host.read_json(analysis_path)
        else:
            evt_path = self.host.find_latest_matching_file(scenario_dir, "*.evt")
            if evt_path:
                analysis_result = self.host.analyze_scenario_outputs({"scenario_dir": str(scenario_dir)})
                analysis = json.loads(analysis_result["content"][0]["text"])["analysis"]
                analysis_path = scenario_dir / "doc" / "ANALYSIS.json"

        title = args.get("briefing_title")
        if not title:
            if model:
                title = model.get("mission", {}).get("title")
            if not title:
                title = scenario_dir.name

        doc_dir = scenario_dir / "doc"
        doc_dir.mkdir(parents=True, exist_ok=True)
        briefing_path = doc_dir / "BRIEFING.md"
        replay_plan_path = doc_dir / "REPLAY_PLAN.md"
        speaker_notes_path = doc_dir / "SPEAKER_NOTES.md"
        manifest_path = doc_dir / "SHOWCASE_PACKAGE.json"

        briefing_text = self.render_showcase_briefing(title, model, analysis, scenario_dir, prompt_refinement)
        replay_text = self.render_showcase_replay_plan(title, model, analysis, scenario_dir, prompt_refinement)
        speaker_text = self.render_showcase_speaker_notes(title, model, analysis, prompt_refinement)
        manifest = {
            "title": title,
            "scenario_dir": str(scenario_dir),
            "model_path": str(model_path) if model_path and model_path.exists() else None,
            "analysis_path": str(analysis_path) if analysis_path and Path(analysis_path).exists() else None,
            "briefing_path": str(briefing_path),
            "replay_plan_path": str(replay_plan_path),
            "speaker_notes_path": str(speaker_notes_path),
            "prompt_refinement": prompt_refinement,
            "keyframes": (analysis or {}).get("recommended_keyframes", []),
        }

        self.host.write_text(briefing_path, briefing_text)
        self.host.write_text(replay_plan_path, replay_text)
        self.host.write_text(speaker_notes_path, speaker_text)
        self.host.write_json(manifest_path, manifest)

        return self.host.wrap(
            {
                "title": title,
                "briefing_path": str(briefing_path),
                "replay_plan_path": str(replay_plan_path),
                "speaker_notes_path": str(speaker_notes_path),
                "manifest_path": str(manifest_path),
                "analysis_path": str(analysis_path) if analysis_path and Path(analysis_path).exists() else None,
            }
        )

    def render_showcase_briefing(self, title, model, analysis, scenario_dir, refinement=None):
        lines = [f"# {title}", ""]
        if model:
            lines.append(model.get("mission", {}).get("summary") or "Operational scenario package.")
            if refinement:
                confidence = refinement.get("confidence") or {}
                lines.extend(["", "## Prompt Intent", ""])
                lines.append(f"- scenario_kind: {refinement.get('scenario_kind')}")
                lines.append(f"- intended_theater: {refinement.get('theater')}")
                lines.append(f"- confidence: {confidence.get('level')} ({confidence.get('score')})")
                for item in refinement.get("replay_focus", [])[:3]:
                    lines.append(f"- replay_focus: {item}")
                for item in refinement.get("desired_kpis", [])[:4]:
                    lines.append(f"- kpi_focus: {item}")
                if refinement.get("low_confidence"):
                    lines.extend(["", "## Low-Confidence Items", ""])
                    for item in refinement.get("filled_by_system", []):
                        lines.append(f"- system_filled: {item}")
            lines.extend(["", "## Mission Objectives", ""])
            for objective in model.get("mission", {}).get("objectives", []):
                lines.append(f"- {objective['side']}: {objective['description']}")
            lines.extend(["", "## Force Packages", ""])
            for side in ("blue", "red", "neutral"):
                packages = model.get("forces", {}).get(side) or []
                if not packages:
                    continue
                lines.append(f"### {side.title()}")
                lines.append("")
                for package in packages:
                    lines.append(f"- {package['name']}: {package['count']} x {package['category']} ({package['role']})")
                lines.append("")
        if analysis:
            lines.extend(["## Expected Replay Highlights", ""])
            for highlight in analysis.get("highlights", []):
                lines.append(f"- {highlight}")
            lines.append("")
        lines.append(f"Scenario directory: {scenario_dir}")
        return "\n".join(lines).rstrip() + "\n"

    def render_showcase_replay_plan(self, title, model, analysis, scenario_dir, refinement=None):
        lines = [f"# Replay Plan: {title}", "", "## Mystic Playback Guidance", ""]
        lines.append("- Start in a wide theater view for 10-15 seconds to establish the geometry.")
        lines.append("- Transition to unit-pair views at each keyframe and hold long enough to narrate the action.")
        lines.append("- Re-center on surviving objectives after each major hit to show consequence, not just weapon travel.")
        prioritized_keyframes = self.prioritize_replay_keyframes(analysis, refinement)
        if refinement:
            lines.extend(["", "## KPI Playback Priorities", ""])
            for kpi in refinement.get("desired_kpis", [])[:5]:
                lines.append(f"- {kpi}")
        lines.extend(["", "## Key Moments", ""])
        for keyframe in prioritized_keyframes:
            lines.append(
                f"- {keyframe['time_label']} {keyframe['title']}: {keyframe['recommended_view']}"
            )
        if model:
            lines.extend(["", "## Phase Windows", ""])
            for phase in model.get("phases", []):
                lines.append(
                    f"- {phase['name']} ({phase['start_min']} to {phase['end_min']} min): {phase['summary']}"
                )
        lines.extend(["", f"Scenario directory: {scenario_dir}"])
        return "\n".join(lines).rstrip() + "\n"

    def prioritize_replay_keyframes(self, analysis, refinement=None):
        keyframes = list((analysis or {}).get("recommended_keyframes", []))
        timeline = list((analysis or {}).get("timeline", []))
        if not keyframes and not timeline:
            return keyframes
        desired_kpis = list((refinement or {}).get("desired_kpis") or [])
        if not desired_kpis:
            return keyframes

        selected = []
        seen = set()

        for kpi in desired_kpis:
            candidate = self.find_kpi_candidate_keyframe(kpi, keyframes, timeline)
            if not candidate:
                continue
            marker = (candidate.get("time_sec"), candidate.get("title"))
            if marker in seen:
                continue
            selected.append(candidate)
            seen.add(marker)

        def match_score(keyframe):
            text = f"{keyframe.get('title', '')} {keyframe.get('focus', '')}".lower()
            score = 0
            for index, kpi in enumerate(desired_kpis):
                weight = max(20 - index * 3, 5)
                if kpi == "first_detection_time" and any(token in text for token in ["first detection", "track initiated", "detected"]):
                    score += weight
                elif kpi == "first_shot_time" and any(token in text for token in [" fired ", "launched", "weapon fired"]):
                    score += weight
                elif kpi == "first_hit_time" and any(token in text for token in [" hit ", "weapon hit"]):
                    score += weight
                elif kpi == "objective_survival_rate" and any(token in text for token in ["broken", "target", "base", "hvaa", "objective"]):
                    score += weight
                elif kpi == "intercept_success_rate" and any(token in text for token in ["missile", "intercept", "hit"]):
                    score += weight
                elif kpi == "kill_chain_closure_score" and any(token in text for token in ["first detection", "fired", "hit", "broken"]):
                    score += weight
            return score

        ranked = sorted(
            keyframes,
            key=lambda keyframe: (-match_score(keyframe), float(keyframe.get("time_sec") or 0.0)),
        )
        for keyframe in ranked:
            marker = (keyframe.get("time_sec"), keyframe.get("title"))
            if marker in seen:
                continue
            selected.append(keyframe)
            seen.add(marker)
        return selected

    def find_kpi_candidate_keyframe(self, kpi, keyframes, timeline):
        for keyframe in keyframes:
            if self.keyframe_matches_kpi(keyframe, kpi):
                return keyframe
        for item in timeline:
            synthetic = self.timeline_item_to_keyframe(item)
            if synthetic and self.keyframe_matches_kpi(synthetic, kpi):
                return synthetic
        return self.synthetic_kpi_keyframe(kpi, timeline)

    def synthetic_kpi_keyframe(self, kpi, timeline):
        if kpi == "first_shot_time":
            timestamp = self.find_first_timeline_time(timeline, ["hit", "missed", "fired", "launched"])
            if timestamp is not None:
                return {
                    "time_sec": timestamp,
                    "time_label": self.host.format_time_label(timestamp),
                    "title": "First shot window",
                    "focus": "No explicit WEAPON_FIRED event was recorded, so the first weapon-employment window is inferred from the earliest weapon effect event.",
                    "recommended_view": "Anchor on the shooter-target pair just before the first weapon effect becomes visible.",
                    "aer_path": None,
                }
        if kpi == "first_hit_time":
            timestamp = self.find_first_timeline_time(timeline, [" hit ", "weapon hit"])
            if timestamp is not None:
                return {
                    "time_sec": timestamp,
                    "time_label": self.host.format_time_label(timestamp),
                    "title": "First hit window",
                    "focus": "Use this moment to explain the first observed successful weapon effect.",
                    "recommended_view": "Center on the target impact and hold the camera long enough to explain the outcome.",
                    "aer_path": None,
                }
        return None

    def find_first_timeline_time(self, timeline, tokens):
        for item in timeline:
            text = f" {item.get('title', '')} {item.get('detail', '')} ".lower()
            if any(token in text for token in tokens):
                value = item.get("time_sec")
                if value is not None:
                    return float(value)
        return None

    def keyframe_matches_kpi(self, keyframe, kpi):
        text = f"{keyframe.get('title', '')} {keyframe.get('focus', '')}".lower()
        if kpi == "first_detection_time":
            return any(token in text for token in ["first detection", "track initiated", "detected"])
        if kpi == "first_shot_time":
            return any(token in text for token in [" fired ", "launched", "weapon fired"])
        if kpi == "first_hit_time":
            return any(token in text for token in [" hit ", "weapon hit"])
        if kpi == "objective_survival_rate":
            return any(token in text for token in ["broken", "target", "base", "hvaa", "objective"])
        if kpi == "intercept_success_rate":
            return any(token in text for token in ["missile", "intercept", "hit"])
        if kpi == "kill_chain_closure_score":
            return any(token in text for token in ["first detection", "track initiated", "fired", "hit", "broken"])
        return False

    def timeline_item_to_keyframe(self, item):
        if not item:
            return None
        return {
            "time_sec": item.get("time_sec"),
            "time_label": item.get("time_label"),
            "title": item.get("title"),
            "focus": item.get("detail"),
            "recommended_view": "Center the camera on the engaged pair and hold for 10-15 seconds.",
            "aer_path": None,
        }

    def render_showcase_speaker_notes(self, title, model, analysis, refinement=None):
        lines = [f"# Speaker Notes: {title}", "", "## Commentary Script", ""]
        if model:
            lines.append(f"- Opening: {model.get('mission', {}).get('summary')}")
        if refinement:
            lines.append(f"- Intent framing: This scenario was generated as a {refinement.get('scenario_kind')} vignette {refinement.get('theater')}.")
            if refinement.get("desired_kpis"):
                lines.append(f"- KPI framing: Call out {', '.join(refinement.get('desired_kpis', [])[:4])}.")
            if refinement.get("low_confidence"):
                lines.append("- Caveat: Several scenario fields were inferred by the system because the user prompt was underspecified.")
        for keyframe in (analysis or {}).get("recommended_keyframes", []):
            lines.append(
                f"- {keyframe['time_label']}: Call out {keyframe['title']}. Emphasize {keyframe['focus'].lower()}."
            )
        if analysis and analysis.get("highlights"):
            lines.extend(["", "## Closing Points", ""])
            for highlight in analysis["highlights"]:
                lines.append(f"- {highlight}")
        return "\n".join(lines).rstrip() + "\n"