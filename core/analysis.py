import re
from collections import defaultdict
from pathlib import Path


class AnalysisService:
    def __init__(self, host):
        self.host = host

    def summarize_evt(self, args):
        path = Path(self.host.require_str(args, "path"))
        self.host.assert_path_allowed(path, write=False, purpose="summarize_evt")
        if not path.exists():
            return self.host.wrap({"error": "file not found"})
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        counts = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            parts = stripped.split()
            if not parts:
                continue
            key = parts[1] if parts[0].upper() == "EVENT" and len(parts) > 1 else parts[0]
            counts[key] = counts.get(key, 0) + 1
        top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return self.host.wrap(
            {
                "path": str(path),
                "line_count": len(lines),
                "event_counts": [{"event": key, "count": value} for key, value in top],
            }
        )

    def analyze_scenario_outputs(self, args):
        scenario_dir_arg = args.get("scenario_dir")
        evt_arg = args.get("evt_path")
        sensor_arg = args.get("sensor_path")
        aer_arg = args.get("aer_path")

        if not scenario_dir_arg and not evt_arg:
            raise self.host.JsonRpcError(
                -32602,
                "Invalid params",
                {"reason": "scenario_dir or evt_path is required"},
            )

        scenario_dir = Path(scenario_dir_arg) if scenario_dir_arg else None
        if scenario_dir:
            self.host.assert_path_allowed(scenario_dir, write=True, purpose="analyze_scenario_outputs(scenario_dir)")

        evt_path = Path(evt_arg) if evt_arg else self.host.find_latest_matching_file(scenario_dir, "*.evt")
        if not evt_path or not evt_path.exists():
            return self.host.wrap({"error": "evt file not found"})
        self.host.assert_path_allowed(evt_path, write=False, purpose="analyze_scenario_outputs(evt)")

        sensor_path = Path(sensor_arg) if sensor_arg else self.host.find_latest_matching_file(scenario_dir, "SENSOR*")
        if sensor_path and sensor_path.exists():
            self.host.assert_path_allowed(sensor_path, write=False, purpose="analyze_scenario_outputs(sensor)")
        else:
            sensor_path = None

        aer_path = Path(aer_arg) if aer_arg else self.host.find_latest_matching_file(scenario_dir, "*.aer")
        if aer_path and aer_path.exists():
            self.host.assert_path_allowed(aer_path, write=False, purpose="analyze_scenario_outputs(aer)")
        else:
            aer_path = None

        records = self.parse_evt_records(evt_path)
        analysis = self.build_output_analysis(
            records,
            scenario_dir=scenario_dir,
            evt_path=evt_path,
            sensor_path=sensor_path,
            aer_path=aer_path,
        )

        output_path = args.get("output_path")
        if output_path:
            output_json_path = Path(output_path)
        elif scenario_dir:
            output_json_path = scenario_dir / "doc" / "ANALYSIS.json"
        else:
            output_json_path = None

        output_md_path = None
        if output_json_path:
            self.host.assert_path_allowed(output_json_path, write=True, purpose="analyze_scenario_outputs(output_json)")
            self.host.write_json(output_json_path, analysis)
            output_md_path = output_json_path.with_suffix(".md")
            self.host.assert_path_allowed(output_md_path, write=True, purpose="analyze_scenario_outputs(output_md)")
            self.host.write_text(output_md_path, self.render_analysis_markdown(analysis))

        return self.host.wrap(
            {
                "analysis": analysis,
                "analysis_path": str(output_json_path) if output_json_path else None,
                "analysis_markdown_path": str(output_md_path) if output_md_path else None,
            }
        )

    def parse_evt_records(self, evt_path):
        raw_lines = Path(evt_path).read_text(encoding="utf-8", errors="ignore").splitlines()
        combined = []
        buffer = ""
        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if buffer:
                buffer = f"{buffer} {stripped}"
            else:
                buffer = stripped
            if stripped.endswith("\\"):
                buffer = buffer[:-1].rstrip()
                continue
            combined.append(buffer)
            buffer = ""
        if buffer:
            combined.append(buffer)

        records = []
        for record in combined:
            match = re.match(r"^(\d+(?:\.\d+)?)\s+([A-Z_]+)\s*(.*)$", record)
            if not match:
                continue
            time_sec = float(match.group(1))
            event_type = match.group(2)
            payload = match.group(3).strip()
            prefix, fields = self.parse_evt_payload_fields(payload)
            tokens = prefix.split() if prefix else []
            records.append(
                {
                    "time_sec": time_sec,
                    "event_type": event_type,
                    "prefix": prefix,
                    "tokens": tokens,
                    "fields": fields,
                    "raw": record,
                }
            )
        return records

    def parse_evt_payload_fields(self, payload):
        first_field = re.search(r"\b[A-Za-z_][A-Za-z0-9_]*:\s", payload)
        if not first_field:
            return payload.strip(), {}
        prefix = payload[: first_field.start()].strip()
        field_text = payload[first_field.start() :]
        fields = {}
        for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)(?=\s+[A-Za-z_][A-Za-z0-9_]*:\s|$)", field_text):
            fields[key] = value.strip()
        return prefix, fields

    def build_output_analysis(self, records, *, scenario_dir=None, evt_path=None, sensor_path=None, aer_path=None):
        event_counts = defaultdict(int)
        timeline = []
        model = self.load_operational_model_for_scenario(scenario_dir)
        losses = {
            "blue": {"platforms_lost": 0, "aircraft": 0, "ground": 0, "targets": 0, "weapons_expended": 0},
            "red": {"platforms_lost": 0, "aircraft": 0, "ground": 0, "targets": 0, "weapons_expended": 0},
            "unknown": {"platforms_lost": 0, "aircraft": 0, "ground": 0, "targets": 0, "weapons_expended": 0},
        }
        weapon_stats = defaultdict(lambda: {"resolved_engagements": 0, "hits": 0, "misses": 0, "top_shooters": defaultdict(int)})
        intercept_stats = defaultdict(lambda: {"attempted_intercepts": 0, "successful_intercepts": 0})
        sensor_chains = {}
        first_detection_by_side = {}
        first_shot_by_side = {}
        first_hit_by_side = {}
        first_kill_by_side = {}
        broken_platforms = set()
        objective_inventory_by_side = defaultdict(set)

        for record in records:
            event_type = record["event_type"]
            event_counts[event_type] += 1
            timeline_item = self.event_to_timeline_item(record)
            if timeline_item:
                timeline.append(timeline_item)

            if event_type == "WEAPON_FIRED":
                shooter = record["tokens"][0] if len(record["tokens"]) > 0 else None
                side = self.infer_side(shooter)
                self.update_first_event_time(first_shot_by_side, side, record["time_sec"])

            if event_type in ("WEAPON_HIT", "WEAPON_MISSED"):
                shooter = record["tokens"][0] if len(record["tokens"]) > 0 else None
                target = record["tokens"][1] if len(record["tokens"]) > 1 else None
                side = self.infer_side(shooter)
                stats = weapon_stats[side]
                stats["resolved_engagements"] += 1
                stats["hits" if event_type == "WEAPON_HIT" else "misses"] += 1
                self.update_first_event_time(first_shot_by_side, side, record["time_sec"])
                if shooter:
                    stats["top_shooters"][shooter] += 1
                if self.looks_like_weapon(target):
                    intercept = intercept_stats[side]
                    intercept["attempted_intercepts"] += 1
                    if event_type == "WEAPON_HIT":
                        intercept["successful_intercepts"] += 1
                if event_type == "WEAPON_HIT":
                    self.update_first_event_time(first_hit_by_side, side, record["time_sec"])

            if event_type == "PLATFORM_BROKEN":
                platform = record["tokens"][0] if record["tokens"] else "unknown"
                side = str(record["fields"].get("Side") or self.infer_side(platform))
                bucket = self.classify_loss_bucket(record["fields"].get("Type"), platform)
                broken_platforms.add(platform)
                losses.setdefault(side, {"platforms_lost": 0, "aircraft": 0, "ground": 0, "targets": 0, "weapons_expended": 0})
                if bucket == "weapons_expended":
                    losses[side][bucket] += 1
                else:
                    losses[side]["platforms_lost"] += 1
                    losses[side][bucket] += 1
                    self.update_first_event_time(first_kill_by_side, self.opposing_side(side), record["time_sec"])

            if event_type == "PLATFORM_INITIALIZED":
                platform = record["tokens"][0] if record["tokens"] else "unknown"
                side = str(record["fields"].get("Side") or self.infer_side(platform))
                platform_type = record["fields"].get("Type")
                if self.is_objective_platform(platform_type, platform):
                    objective_inventory_by_side[side].add(platform)

            if event_type in ("SENSOR_TRACK_INITIATED", "SENSOR_TRACK_UPDATED"):
                observer = record["tokens"][0] if len(record["tokens"]) > 0 else "unknown"
                target = record["tokens"][1] if len(record["tokens"]) > 1 else "unknown"
                sensor = record["fields"].get("Sensor") or "unknown"
                track_id = record["fields"].get("TrackId") or f"{observer}:{target}:{sensor}"
                self.update_first_event_time(first_detection_by_side, self.infer_side(observer), record["time_sec"])
                chain = sensor_chains.setdefault(
                    track_id,
                    {
                        "track_id": track_id,
                        "observer": observer,
                        "target": target,
                        "sensor": sensor,
                        "side": self.infer_side(observer),
                        "first_detected_sec": record["time_sec"],
                        "last_update_sec": record["time_sec"],
                        "update_count": 0,
                    },
                )
                chain["last_update_sec"] = record["time_sec"]
                if event_type == "SENSOR_TRACK_UPDATED":
                    chain["update_count"] += 1

        weapon_summary = {}
        for side, stats in weapon_stats.items():
            resolved = stats["resolved_engagements"]
            weapon_summary[side] = {
                "resolved_engagements": resolved,
                "hits": stats["hits"],
                "misses": stats["misses"],
                "hit_rate": round(stats["hits"] / resolved, 3) if resolved else 0.0,
                "top_shooters": [
                    {"shooter": shooter, "engagements": count}
                    for shooter, count in sorted(stats["top_shooters"].items(), key=lambda item: item[1], reverse=True)[:5]
                ],
            }

        intercept_summary = {}
        for side, stats in intercept_stats.items():
            attempted = stats["attempted_intercepts"]
            intercept_summary[side] = {
                "attempted_intercepts": attempted,
                "successful_intercepts": stats["successful_intercepts"],
                "interception_rate": round(stats["successful_intercepts"] / attempted, 3) if attempted else 0.0,
            }

        chains = sorted(sensor_chains.values(), key=lambda item: item["first_detected_sec"])
        keyframes = self.build_recommended_keyframes(timeline, chains, aer_path)
        kpi_summary = self.build_kpi_summary(
            model,
            first_detection_by_side,
            first_shot_by_side,
            first_hit_by_side,
            first_kill_by_side,
            broken_platforms,
            objective_inventory_by_side,
            losses,
            chains,
            timeline,
        )

        highlights = []
        if chains:
            first_chain = chains[0]
            highlights.append(
                f"First sensor chain started at {self.host.format_time_label(first_chain['first_detected_sec'])} by {first_chain['observer']} tracking {first_chain['target']}."
            )
        for side in ("blue", "red"):
            if side in weapon_summary and weapon_summary[side]["resolved_engagements"]:
                highlights.append(
                    f"{side.title()} resolved {weapon_summary[side]['resolved_engagements']} engagements with a hit rate of {weapon_summary[side]['hit_rate']}."
                )
        for side in ("blue", "red"):
            if losses.get(side, {}).get("platforms_lost"):
                highlights.append(
                    f"{side.title()} lost {losses[side]['platforms_lost']} non-weapon platforms."
                )
        if kpi_summary.get("kill_chain_closure"):
            highlights.append(
                f"Kill-chain closure score: {kpi_summary['kill_chain_closure']['score']} / 100."
            )

        return {
            "scenario_dir": str(scenario_dir) if scenario_dir else None,
            "evt_path": str(evt_path) if evt_path else None,
            "sensor_path": str(sensor_path) if sensor_path else None,
            "aer_path": str(aer_path) if aer_path else None,
            "model_path": str((Path(scenario_dir) / 'doc') / f"{Path(scenario_dir).name}.model.json") if scenario_dir and model else None,
            "event_counts": dict(sorted(event_counts.items(), key=lambda item: item[1], reverse=True)),
            "timeline": timeline[:40],
            "red_blue_losses": losses,
            "weapon_statistics": weapon_summary,
            "interception_statistics": intercept_summary,
            "sensor_detection_chains": chains[:20],
            "kpis": kpi_summary,
            "recommended_keyframes": keyframes,
            "highlights": highlights,
        }

    def event_to_timeline_item(self, record):
        event_type = record["event_type"]
        time_sec = record["time_sec"]
        if event_type == "WEAPON_FIRED":
            shooter = record["tokens"][0] if len(record["tokens"]) > 0 else "unknown"
            target = record["tokens"][1] if len(record["tokens"]) > 1 else "unknown"
            weapon = record["tokens"][2] if len(record["tokens"]) > 2 else "unknown_weapon"
            return {
                "time_sec": time_sec,
                "time_label": self.host.format_time_label(time_sec),
                "event_type": event_type,
                "title": f"{weapon} fired at {target}",
                "detail": f"{shooter} launched {weapon} against {target}.",
            }
        if event_type in ("WEAPON_HIT", "WEAPON_MISSED"):
            shooter = record["tokens"][0] if len(record["tokens"]) > 0 else "unknown"
            target = record["tokens"][1] if len(record["tokens"]) > 1 else "unknown"
            weapon = record["tokens"][2] if len(record["tokens"]) > 2 else "unknown_weapon"
            outcome = "hit" if event_type == "WEAPON_HIT" else "missed"
            return {
                "time_sec": time_sec,
                "time_label": self.host.format_time_label(time_sec),
                "event_type": event_type,
                "title": f"{weapon} {outcome} {target}",
                "detail": f"{shooter} engaged {target} using {weapon}.",
            }
        if event_type == "PLATFORM_BROKEN":
            platform = record["tokens"][0] if record["tokens"] else "unknown"
            return {
                "time_sec": time_sec,
                "time_label": self.host.format_time_label(time_sec),
                "event_type": event_type,
                "title": f"{platform} broken",
                "detail": f"{platform} left the fight.",
            }
        if event_type == "SENSOR_TRACK_INITIATED":
            observer = record["tokens"][0] if len(record["tokens"]) > 0 else "unknown"
            target = record["tokens"][1] if len(record["tokens"]) > 1 else "unknown"
            sensor = record["fields"].get("Sensor") or "sensor"
            return {
                "time_sec": time_sec,
                "time_label": self.host.format_time_label(time_sec),
                "event_type": event_type,
                "title": f"Track initiated on {target}",
                "detail": f"{observer} detected {target} with {sensor}.",
            }
        return None

    def build_recommended_keyframes(self, timeline, chains, aer_path):
        keyframes = []
        seen_titles = set()
        if chains:
            first_chain = chains[0]
            keyframes.append(
                {
                    "time_sec": first_chain["first_detected_sec"],
                    "time_label": self.host.format_time_label(first_chain["first_detected_sec"]),
                    "title": f"First detection: {first_chain['target']}",
                    "focus": f"Observer {first_chain['observer']} and target {first_chain['target']}",
                    "recommended_view": "Start wide, then anchor on the detecting unit and its target.",
                    "aer_path": str(aer_path) if aer_path else None,
                }
            )
            seen_titles.add(keyframes[-1]["title"])
        for item in timeline:
            if len(keyframes) >= 8:
                break
            if item["title"] in seen_titles:
                continue
            keyframes.append(
                {
                    "time_sec": item["time_sec"],
                    "time_label": item["time_label"],
                    "title": item["title"],
                    "focus": item["detail"],
                    "recommended_view": "Center the camera on the engaged pair and hold for 10-15 seconds.",
                    "aer_path": str(aer_path) if aer_path else None,
                }
            )
            seen_titles.add(item["title"])
        return keyframes

    def load_operational_model_for_scenario(self, scenario_dir):
        if not scenario_dir:
            return None
        doc_dir = Path(scenario_dir) / "doc"
        if not doc_dir.exists():
            return None
        model_path = self.host.find_latest_matching_file(doc_dir, "*.model.json")
        if model_path and model_path.exists():
            return self.host.read_json(model_path)
        return None

    def build_kpi_summary(self, model, first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, broken_platforms, objective_inventory_by_side, losses, chains, timeline):
        side_kpis = {}
        for side in ("blue", "red"):
            side_kpis[side] = {
                "first_detection_sec": first_detection_by_side.get(side),
                "first_detection_label": self.format_optional_time(first_detection_by_side.get(side)),
                "first_shot_sec": first_shot_by_side.get(side),
                "first_shot_label": self.format_optional_time(first_shot_by_side.get(side)),
                "first_hit_sec": first_hit_by_side.get(side),
                "first_hit_label": self.format_optional_time(first_hit_by_side.get(side)),
                "first_kill_sec": first_kill_by_side.get(side),
                "first_kill_label": self.format_optional_time(first_kill_by_side.get(side)),
                "platforms_lost": losses.get(side, {}).get("platforms_lost", 0),
            }

        objective_survival = self.compute_objective_survival(model, broken_platforms)
        if not objective_survival:
            objective_survival = self.compute_event_objective_survival(objective_inventory_by_side, broken_platforms)
        if not objective_survival:
            objective_survival = {
                "status": "unavailable",
                "reason": "No operational model or objective initialization events were available to establish the target inventory.",
            }
        kill_chain = self.compute_kill_chain_closure(first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, chains, timeline)

        return {
            "side_kpis": side_kpis,
            "objective_survival": objective_survival,
            "kill_chain_closure": kill_chain,
        }

    def compute_objective_survival(self, model, broken_platforms):
        summary = {}
        if not model:
            return summary
        for side in ("blue", "red"):
            total = 0
            for package in model.get("forces", {}).get(side, []):
                if package.get("category") in ("target", "objective", "high_value_asset"):
                    total += int(package.get("count") or 1)
            if total == 0:
                continue
            broken = 0
            for package in model.get("forces", {}).get(side, []):
                if package.get("category") not in ("target", "objective", "high_value_asset"):
                    continue
                for unit_index in range(int(package.get("count") or 1)):
                    platform_name = self.host.slugify(f"{package['name']}_{unit_index + 1}")
                    if platform_name in broken_platforms:
                        broken += 1
            summary[side] = {
                "total_objectives": total,
                "surviving_objectives": max(total - broken, 0),
                "survival_rate": round(max(total - broken, 0) / total, 3) if total else 0.0,
            }
        return summary

    def compute_event_objective_survival(self, objective_inventory_by_side, broken_platforms):
        summary = {}
        for side, platforms in objective_inventory_by_side.items():
            total = len(platforms)
            if total == 0:
                continue
            broken = sum(1 for name in platforms if name in broken_platforms)
            summary[side] = {
                "total_objectives": total,
                "surviving_objectives": max(total - broken, 0),
                "survival_rate": round(max(total - broken, 0) / total, 3) if total else 0.0,
            }
        return summary

    def compute_kill_chain_closure(self, first_detection_by_side, first_shot_by_side, first_hit_by_side, first_kill_by_side, chains, timeline):
        first_detection = min(first_detection_by_side.values()) if first_detection_by_side else None
        first_shot = min(first_shot_by_side.values()) if first_shot_by_side else None
        first_hit = min(first_hit_by_side.values()) if first_hit_by_side else None
        first_kill = min(first_kill_by_side.values()) if first_kill_by_side else None

        components = {
            "detection_observed": first_detection is not None,
            "weapon_employed": first_shot is not None and (first_detection is None or first_shot >= first_detection),
            "weapon_effect_observed": first_hit is not None and (first_shot is None or first_hit >= first_shot),
            "kill_or_break_observed": first_kill is not None and (first_hit is None or first_kill >= first_hit),
            "sensor_to_shooter_link": bool(chains) and any(item["event_type"] in ("WEAPON_FIRED", "WEAPON_HIT", "WEAPON_MISSED") for item in timeline),
        }
        score = sum(20 for value in components.values() if value)
        return {
            "score": score,
            "components": components,
            "first_detection_label": self.format_optional_time(first_detection),
            "first_shot_label": self.format_optional_time(first_shot),
            "first_hit_label": self.format_optional_time(first_hit),
            "first_kill_label": self.format_optional_time(first_kill),
        }

    def update_first_event_time(self, store, side, value):
        if side not in store or value < store[side]:
            store[side] = value

    def opposing_side(self, side):
        if side == "blue":
            return "red"
        if side == "red":
            return "blue"
        return "unknown"

    def format_optional_time(self, seconds):
        if seconds is None:
            return None
        return self.host.format_time_label(seconds)

    def infer_side(self, name):
        text = str(name or "").lower()
        if any(token in text for token in ["blue", "israel", "us", "friendly"]):
            return "blue"
        if any(token in text for token in ["red", "iran", "hostile"]):
            return "red"
        return "unknown"

    def looks_like_weapon(self, name):
        text = str(name or "").lower()
        return any(token in text for token in ["missile", "mrbm", "sam", "fox", "weapon", "aim", "amraam"])

    def classify_loss_bucket(self, platform_type, platform_name):
        text = f"{platform_type or ''} {platform_name or ''}".lower()
        if self.looks_like_weapon(text):
            return "weapons_expended"
        if any(token in text for token in ["fighter", "air", "aircraft"]):
            return "aircraft"
        if self.is_objective_platform(platform_type, platform_name):
            return "targets"
        return "ground"

    def is_objective_platform(self, platform_type, platform_name):
        text = f"{platform_type or ''} {platform_name or ''}".lower()
        return any(token in text for token in ["target", "airbase", "base", "hvaa", "command", "c2", "hq", "depot"])

    def render_analysis_markdown(self, analysis):
        lines = [
            "# Output Analysis",
            "",
            "## Highlights",
            "",
        ]
        for highlight in analysis.get("highlights", []):
            lines.append(f"- {highlight}")
        kpis = analysis.get("kpis") or {}
        if kpis:
            lines.extend(["", "## KPI Summary", ""])
            kill_chain = kpis.get("kill_chain_closure") or {}
            if kill_chain:
                lines.append(f"- kill_chain_closure_score: {kill_chain.get('score')}")
                for name, value in (kill_chain.get("components") or {}).items():
                    lines.append(f"- {name}: {value}")
            for side, stats in (kpis.get("side_kpis") or {}).items():
                lines.append(f"### {side.title()} Tempo")
                lines.append("")
                lines.append(f"- first_detection: {stats.get('first_detection_label') or 'n/a'}")
                lines.append(f"- first_shot: {stats.get('first_shot_label') or 'n/a'}")
                lines.append(f"- first_hit: {stats.get('first_hit_label') or 'n/a'}")
                lines.append(f"- first_kill: {stats.get('first_kill_label') or 'n/a'}")
                lines.append(f"- platforms_lost: {stats.get('platforms_lost', 0)}")
                lines.append("")
            objective_survival = kpis.get("objective_survival") or {}
            if objective_survival:
                lines.append("## Objective Survival")
                lines.append("")
                if objective_survival.get("status") == "unavailable":
                    lines.append(f"- status: {objective_survival.get('status')}")
                    lines.append(f"- reason: {objective_survival.get('reason')}")
                    lines.append("")
                else:
                    for side, stats in objective_survival.items():
                        lines.append(f"### {side.title()}")
                        lines.append("")
                        lines.append(f"- total_objectives: {stats.get('total_objectives', 0)}")
                        lines.append(f"- surviving_objectives: {stats.get('surviving_objectives', 0)}")
                        lines.append(f"- survival_rate: {stats.get('survival_rate', 0.0)}")
                        lines.append("")
        lines.extend(["", "## Red-Blue Losses", ""])
        for side, stats in analysis.get("red_blue_losses", {}).items():
            lines.append(f"### {side.title()}")
            lines.append("")
            for key, value in stats.items():
                lines.append(f"- {key}: {value}")
            lines.append("")
        lines.extend(["## Weapon Statistics", ""])
        for side, stats in analysis.get("weapon_statistics", {}).items():
            lines.append(f"### {side.title()}")
            lines.append("")
            lines.append(f"- resolved_engagements: {stats['resolved_engagements']}")
            lines.append(f"- hits: {stats['hits']}")
            lines.append(f"- misses: {stats['misses']}")
            lines.append(f"- hit_rate: {stats['hit_rate']}")
            for shooter in stats.get("top_shooters", []):
                lines.append(f"- top_shooter {shooter['shooter']}: {shooter['engagements']}")
            lines.append("")
        lines.extend(["## Recommended Keyframes", ""])
        for keyframe in analysis.get("recommended_keyframes", []):
            lines.append(f"- {keyframe['time_label']} {keyframe['title']}: {keyframe['focus']}")
        return "\n".join(lines).rstrip() + "\n"