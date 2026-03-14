import re


class GenerationService:
    def __init__(self, host):
        self.host = host

    def render_operational_entrypoint_text(self, model):
        scenario_name = model["scenario_name"]
        duration_min = model["duration_min"]
        asset_profile = model.get("asset_profile") or {}
        lines = ["file_path ."]
        if asset_profile.get("asset_root"):
            lines.append(f"file_path {asset_profile['asset_root']}")
        lines.extend(
            [
                f"define_path_variable CASE {scenario_name}",
                "",
                "log_file output/${CASE}.log",
                "",
            ]
        )
        for include_name in asset_profile.get("entry_includes") or []:
            lines.append(f"include_once {include_name}")
        if asset_profile.get("entry_includes"):
            lines.append("")
        if asset_profile.get("supports_observer"):
            lines.append(self.host.build_observer_block_text().rstrip())
            lines.append("")
        lines.extend(
            [
                "include_once scenarios/${CASE}.txt",
                "",
                "random_seed 20260311",
                f"end_time {duration_min} min",
                "",
                "event_pipe",
                "   file output/${CASE}.aer",
                "   enable AIRCOMBAT",
                "   enable TRACK_UPDATE",
                "   enable BEHAVIOR_TOOL",
                "end_event_pipe",
                "",
                "event_output",
                "   file output/${CASE}.evt",
                "   enable PLATFORM_INITIALIZED",
                "   enable PLATFORM_BROKEN",
                "   enable WEAPON_FIRED",
                "   enable WEAPON_HIT",
                "   enable WEAPON_MISSED",
                "   enable SENSOR_TRACK_INITIATED",
                "   enable SENSOR_TRACK_UPDATED",
                "end_event_output",
                "",
            ]
        )
        return "\n".join(lines)

    def render_operational_scenario_text(self, model):
        asset_profile = model.get("asset_profile") or {}
        if asset_profile.get("mode") not in ("basic", "generated_structured"):
            return self.render_operational_scenario_text_with_assets(model)

        center = model["center"]
        lines = [
            f"// {model['mission']['title']}",
            f"// Scenario kind: {model['scenario_kind']}",
            f"// Summary: {model['mission']['summary']}",
            "",
        ]
        for include_name in asset_profile.get("scenario_includes") or []:
            lines.append(f"include_once {include_name}")
        if asset_profile.get("scenario_includes"):
            lines.append("")

        for side in ("blue", "red", "neutral"):
            packages = model["forces"].get(side) or []
            if not packages:
                continue
            lines.append(f"// {side.upper()} FORCE PACKAGES")
            for package_index, package in enumerate(packages):
                category = package["category"]
                count = int(package.get("count") or 1)
                for unit_index in range(count):
                    name = self.slugify(f"{package['name']}_{unit_index + 1}")
                    points = self.build_package_points(
                        side,
                        category,
                        package_index,
                        unit_index,
                        center,
                        route_style=package.get("route_style"),
                        fallback_route_style=package.get("fallback_route_style"),
                    )
                    if category in ("target", "objective"):
                        target_type = asset_profile.get(f"{side}_target_type") or "TARGET"
                        lines.extend(
                            [
                                f"platform {name} {target_type}",
                                f"   side {side}",
                                f"   icon {package['icon']}",
                                f"   position {self.host.format_lat_lon(points[0]['lat'], points[0]['lon'])}",
                                "end_platform",
                                "",
                            ]
                        )
                        continue

                    if category in ("air_defense", "missile_launcher"):
                        lines.extend(
                            [
                                f"platform {name} WSF_PLATFORM",
                                "   spatial_domain land",
                                f"   side {side}",
                                f"   icon {package['icon']}",
                                "   mover WSF_GROUND_MOVER",
                                "      on_ground",
                                "      route",
                                f"         position {self.host.format_lat_lon(points[0]['lat'], points[0]['lon'])} altitude 1 m speed 5 km/hr",
                                f"         position {self.host.format_lat_lon(points[-1]['lat'], points[-1]['lon'])}",
                                "         stop",
                                "      end_route",
                                "   end_mover",
                                "end_platform",
                                "",
                            ]
                        )
                        continue

                    lines.extend(
                        [
                            f"platform {name} WSF_PLATFORM",
                            "   spatial_domain air",
                            f"   side {side}",
                            f"   icon {package['icon']}",
                            "   add mover WSF_AIR_MOVER",
                            "   end_mover",
                            "   route",
                        ]
                    )
                    for point in points:
                        lines.append(
                            "      position "
                            f"{self.host.format_lat_lon(point['lat'], point['lon'])} altitude {point['altitude_ft']} ft speed {point['speed_kts']} kts"
                        )
                    lines.extend(["   end_route", "end_platform", ""])
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def render_operational_scenario_text_with_assets(self, model):
        asset_profile = model.get("asset_profile") or {}
        center = model["center"]
        lines = [
            f"// {model['mission']['title']}",
            f"// Scenario kind: {model['scenario_kind']}",
            f"// Summary: {model['mission']['summary']}",
            "",
        ]
        for include_name in asset_profile.get("scenario_includes") or []:
            lines.append(f"include_once {include_name}")
        if asset_profile.get("scenario_includes"):
            lines.append("")

        route_blocks = []
        objectives = []

        for side in ("blue", "red", "neutral"):
            packages = model["forces"].get(side) or []
            if not packages:
                continue
            lines.append(f"// {side.upper()} FORCE PACKAGES")
            for package_index, package in enumerate(packages):
                category = package["category"]
                count = int(package.get("count") or 1)
                for unit_index in range(count):
                    name = self.slugify(f"{package['name']}_{unit_index + 1}")
                    points = self.build_package_points(
                        side,
                        category,
                        package_index,
                        unit_index,
                        center,
                        route_style=package.get("route_style"),
                        fallback_route_style=package.get("fallback_route_style"),
                    )
                    if category in ("target", "objective"):
                        target_type = asset_profile.get(f"{side}_target_type") or "TARGET"
                        lines.extend(
                            [
                                f"platform {name} {target_type}",
                                f"   side {side}",
                                f"   position {self.host.format_lat_lon(points[0]['lat'], points[0]['lon'])}",
                                "end_platform",
                                "",
                            ]
                        )
                        objectives.append({"name": name, "side": side, "lat": points[0]["lat"], "lon": points[0]["lon"], "category": category, "role": package.get("role")})
                        continue

                    if category == "air_defense":
                        if side == "blue" and all(
                            asset_profile.get(key)
                            for key in ("blue_air_defense_battery_type", "blue_air_defense_launcher_type", "blue_air_defense_ttr_type")
                        ):
                            anchor = objectives[unit_index % len(objectives)] if objectives else {"lat": points[0]["lat"], "lon": points[0]["lon"]}
                            lines.extend(self.render_blue_air_defense_block(name, anchor, asset_profile))
                        else:
                            platform_type = asset_profile.get(f"{side}_air_defense_type") or asset_profile.get("blue_air_defense_battery_type") or "WSF_PLATFORM"
                            lines.extend(self.render_ground_platform_block(name, platform_type, side, points[0]))
                        continue

                    if category == "missile_launcher":
                        target = self.select_target_for_package(package, objectives, preferred_side="blue" if side == "red" else "red")
                        lines.extend(self.render_ballistic_launcher_block(name, side, unit_index, target, points, asset_profile, launch_time_sec=package.get("launch_time_sec")))
                        continue

                    if category == "high_value_asset":
                        route_name = f"route_{name}"
                        route_blocks.extend(self.render_route_block(route_name, points))
                        fighter_type = asset_profile.get(f"{side}_support_type") or asset_profile.get(f"{side}_fighter_type") or "WSF_PLATFORM"
                        lines.extend(
                            self.render_fighter_platform_block(
                                name,
                                fighter_type,
                                side,
                                route_name,
                                points[0],
                                role="support",
                                enemy_type=asset_profile.get("red_fighter_type") if side == "blue" else asset_profile.get("blue_fighter_type"),
                                friendly_type=fighter_type,
                                flight_id=900 + unit_index,
                                id_flag=unit_index + 1,
                                weapons={"fox3": 0, "fox2": 0},
                                mission_task=package.get("mission_task") or "SUPPORT",
                                commit_range_nm=package.get("commit_range_nm"),
                                risk_weapon=package.get("risk_weapon"),
                                target_priority=package.get("target_priority"),
                            )
                        )
                        objectives.append({"name": name, "side": side, "lat": points[0]["lat"], "lon": points[0]["lon"], "category": category, "role": package.get("role")})
                        continue

                    route_name = f"route_{name}"
                    route_blocks.extend(self.render_route_block(route_name, points))
                    fighter_type = asset_profile.get(f"{side}_fighter_type") or "WSF_PLATFORM"
                    enemy_type = asset_profile.get("red_fighter_type") if side == "blue" else asset_profile.get("blue_fighter_type")
                    lines.extend(
                        self.render_fighter_platform_block(
                            name,
                            fighter_type,
                            side,
                            route_name,
                            points[0],
                            role=package.get("role") or category,
                            enemy_type=enemy_type,
                            friendly_type=fighter_type,
                            flight_id=(100 if side == "blue" else 200) + package_index,
                            id_flag=unit_index + 1,
                            weapons=self.host.default_weapons_for_role(package.get("role") or category),
                            mission_task=package.get("mission_task"),
                            commit_range_nm=package.get("commit_range_nm"),
                            risk_weapon=package.get("risk_weapon"),
                            target_priority=package.get("target_priority"),
                        )
                    )
            lines.append("")

        return "\n".join(route_blocks + [""] + lines).rstrip() + "\n"

    def render_route_block(self, route_name, points):
        lines = [f"route {route_name}"]
        for point in points:
            lines.append(
                "   position "
                f"{self.host.format_lat_lon(point['lat'], point['lon'])} altitude {point.get('altitude_ft', 30000)} ft msl speed {point.get('speed_kts', 450) * 1.68781:.0f} ft/s"
            )
        lines.append("end_route")
        lines.append("")
        return lines

    def render_fighter_platform_block(self, name, fighter_type, side, route_name, start_point, *, role, enemy_type, friendly_type, flight_id, id_flag, weapons, mission_task=None, commit_range_nm=None, risk_weapon=None, target_priority=None):
        mission_task = str(mission_task or self.default_mission_task_for_role(role)).upper()
        risk_weapon = risk_weapon if risk_weapon is not None else self.host.risk_weapon_for_role(role)
        commit_range_nm = commit_range_nm if commit_range_nm is not None else self.host.commit_range_for_role(role)
        target_priority = list(target_priority or [])
        engagement_target = target_priority[0] if target_priority else ""
        secondary_target = target_priority[1] if len(target_priority) > 1 else ""
        tertiary_target = target_priority[2] if len(target_priority) > 2 else ""
        lines = [
            f"platform {name} {fighter_type}",
            f"   side {side}",
            "   commander SELF",
            "   command_chain IFLITE SELF",
            "   command_chain ELEMENT SELF",
            f"   heading {90 if side == 'red' else 270} deg",
            f"   position {self.host.format_lat_lon(start_point['lat'], start_point['lon'])} altitude {start_point.get('altitude_ft', 30000):.2f} ft",
            "",
            "   script_variables",
            '      START_TYPE = "route";',
            f"      RISK_WPN = {risk_weapon};",
            f"      DOR = {commit_range_nm}*MATH.M_PER_NM();",
            f'      MISSION_TYPE = "{mission_task}";',
            f'      ENG_TGT = "{engagement_target}";',
            f'      ENG_TGT_2 = "{secondary_target}";',
            f'      ENG_TGT_3 = "{tertiary_target}";',
            "      RPEAK_LOC = {1.0,0.8,0.95,1.0,1.0};",
            f'      ROUTE.Append("{route_name}");',
            "      WINCHESTER = {-1,-1,-1,-1,-1};",
            "   end_script_variables",
            "",
        ]
        for weapon_name, quantity in weapons.items():
            lines.extend(
                [
                    f"   edit weapon {weapon_name}",
                    f"      quantity {quantity}",
                    "   end_weapon",
                ]
            )
        lines.extend(
            [
                "",
                "   edit processor assessment",
                f"      enemy_side    {'red' if side == 'blue' else 'blue'}",
                f"      enemy_type    {enemy_type}",
                f"      friendly_type {friendly_type}",
                f"      flight_id     {flight_id}",
                f"      id_flag       {id_flag}",
                f"      mission_task  {mission_task}",
                f"      target_hint_1 {engagement_target if engagement_target else 'none'}",
                f"      target_hint_2 {secondary_target if secondary_target else 'none'}",
                "   end_processor",
                "end_platform",
                "",
            ]
        )
        return lines

    def default_mission_task_for_role(self, role):
        role_text = str(role or "").lower()
        if role_text in ("escort", "support"):
            return role_text.upper()
        if role_text in ("strike", "raid", "probe"):
            return "STRIKE"
        return "SWEEP"

    def render_blue_air_defense_block(self, name, anchor, asset_profile):
        base_lat = anchor["lat"]
        base_lon = anchor["lon"]
        battery_type = asset_profile.get("blue_air_defense_battery_type") or "BLUE_NAVAL_SAM_BATTERY"
        launcher_type = asset_profile.get("blue_air_defense_launcher_type") or "BLUE_NAVAL_SAM_LAUNCHER"
        ttr_type = asset_profile.get("blue_air_defense_ttr_type") or "BLUE_ABM_TTR"
        return [
            f"platform {name}_battery {battery_type}",
            "   commander SELF",
            "   side blue",
            f"   position {self.host.format_lat_lon(base_lat, base_lon)}",
            "end_platform",
            "",
            f"platform {name}_launcher {launcher_type}",
            f"   commander {name}_battery",
            "   side blue",
            f"   position {self.host.format_lat_lon(base_lat + 0.01, base_lon + 0.01)}",
            "end_platform",
            "",
            f"platform {name}_ttr {ttr_type}",
            f"   commander {name}_battery",
            "   side blue",
            f"   position {self.host.format_lat_lon(base_lat + 0.01, base_lon + 0.01)}",
            "   heading 090 deg",
            "end_platform",
            "",
        ]

    def render_ground_platform_block(self, name, platform_type, side, point):
        return [
            f"platform {name} {platform_type}",
            f"   side {side}",
            f"   position {self.host.format_lat_lon(point['lat'], point['lon'])}",
            "end_platform",
            "",
        ]

    def render_ballistic_launcher_block(self, name, side, unit_index, target, points, asset_profile, launch_time_sec=None):
        launcher_type = asset_profile.get("red_missile_launcher_type") if side == "red" else asset_profile.get("blue_missile_launcher_type")
        if not launcher_type:
            return self.render_ground_platform_block(name, "WSF_PLATFORM", side, points[0])
        launch_time = int(launch_time_sec if launch_time_sec is not None else 600) + unit_index * 180
        primary_target = target.get("name") if target else ""
        primary_role = target.get("role") if target else ""
        lines = [
            f"platform {name} {launcher_type}",
            f"   side {side}",
            f"   position {self.host.format_lat_lon(points[0]['lat'], points[0]['lon'])}",
        ]
        if target:
            lines.extend(
                [
                    "   processor launch_ssm_processor",
                    "      script_variables",
                    f"         TIME_TO_LAUNCH = {launch_time};",
                    f'         PRIMARY_TARGET = "{primary_target}";',
                    f'         PRIMARY_TARGET_ROLE = "{primary_role}";',
                    "      end_script_variables",
                    "   end_processor",
                    "   track",
                    f"      platform {target['name']}",
                    "   end_track",
                ]
            )
        lines.extend(["end_platform", ""])
        return lines

    def select_target_for_package(self, package, objectives, preferred_side):
        priorities = list(package.get("target_priority") or [])
        preferred = [item for item in objectives if item.get("side") == preferred_side]
        candidates = preferred or list(objectives)
        if not candidates:
            return None

        def score(item):
            value = 0
            category = str(item.get("category") or "").lower()
            role = str(item.get("role") or "").lower()
            name = str(item.get("name") or "").lower()
            for index, token in enumerate(priorities):
                weight = max(1, len(priorities) - index)
                if token == "objective" and category in ("objective", "target"):
                    value += 10 * weight
                elif token == "high_value_asset" and category == "high_value_asset":
                    value += 10 * weight
                elif token == "corridor_opener" and ("escort" in role or "support" in role or "hvaa" in name):
                    value += 10 * weight
                elif token == "fighter" and ("fighter" in name or role in ("escort", "defense", "intercept", "barrier")):
                    value += 8 * weight
                elif token == "survival_preserve" and category in ("objective", "target", "high_value_asset"):
                    value += 4 * weight
            return value

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    def build_package_points(self, side, category, package_index, unit_index, center, route_style=None, fallback_route_style=None):
        center_lat = center["lat"]
        center_lon = center["lon"]
        side_factor = -1 if side == "blue" else 1 if side == "red" else 0
        lateral = package_index * 0.18 + unit_index * 0.04
        route_style = str(route_style or "").lower()
        fallback_route_style = str(fallback_route_style or "").lower()
        if category in ("target", "objective"):
            return [{"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.6}]
        if category in ("air_defense", "missile_launcher"):
            points = [
                {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.2},
                {"lat": center_lat + lateral + 0.02, "lon": center_lon + side_factor * 1.0},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "protective_orbit":
            points = [
                {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.35, "altitude_ft": 27000, "speed_kts": 290},
                {"lat": center_lat + lateral + 0.08, "lon": center_lon + side_factor * 1.15, "altitude_ft": 27000, "speed_kts": 290},
                {"lat": center_lat + lateral - 0.04, "lon": center_lon + side_factor * 1.22, "altitude_ft": 27000, "speed_kts": 290},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "orbit":
            points = [
                {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.45, "altitude_ft": 28000, "speed_kts": 300},
                {"lat": center_lat + lateral + 0.15, "lon": center_lon + side_factor * 1.15, "altitude_ft": 28000, "speed_kts": 300},
                {"lat": center_lat + lateral - 0.06, "lon": center_lon + side_factor * 1.3, "altitude_ft": 28000, "speed_kts": 300},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "screen":
            points = [
                {"lat": center_lat + lateral + 0.04, "lon": center_lon + side_factor * 1.58, "altitude_ft": 32000, "speed_kts": 450},
                {"lat": center_lat + lateral + 0.26, "lon": center_lon + side_factor * 0.88, "altitude_ft": 34000, "speed_kts": 485},
                {"lat": center_lat + lateral + 0.16, "lon": center_lon + side_factor * 0.24, "altitude_ft": 33500, "speed_kts": 475},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "barrier":
            points = [
                {"lat": center_lat + lateral - 0.1, "lon": center_lon + side_factor * 1.45, "altitude_ft": 33000, "speed_kts": 460},
                {"lat": center_lat + lateral + 0.22, "lon": center_lon + side_factor * 0.55, "altitude_ft": 35000, "speed_kts": 500},
                {"lat": center_lat + lateral - 0.08, "lon": center_lon + side_factor * 0.35, "altitude_ft": 34000, "speed_kts": 500},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "escort":
            points = [
                {"lat": center_lat + lateral + 0.05, "lon": center_lon + side_factor * 1.55, "altitude_ft": 31000, "speed_kts": 440},
                {"lat": center_lat + lateral + 0.24, "lon": center_lon + side_factor * 0.72, "altitude_ft": 33000, "speed_kts": 470},
                {"lat": center_lat + lateral + 0.1, "lon": center_lon + side_factor * 0.08, "altitude_ft": 32000, "speed_kts": 470},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "timed_ingress":
            points = [
                {"lat": center_lat + lateral - 0.12, "lon": center_lon + side_factor * 1.82, "altitude_ft": 28000, "speed_kts": 415},
                {"lat": center_lat + lateral - 0.04, "lon": center_lon + side_factor * 1.05, "altitude_ft": 29000, "speed_kts": 430},
                {"lat": center_lat + lateral + 0.1, "lon": center_lon + side_factor * 0.72, "altitude_ft": 30000, "speed_kts": 455},
                {"lat": center_lat + lateral + 0.02, "lon": center_lon - side_factor * 0.08, "altitude_ft": 30000, "speed_kts": 460},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if route_style == "ingress":
            points = [
                {"lat": center_lat + lateral - 0.1, "lon": center_lon + side_factor * 1.75, "altitude_ft": 28000, "speed_kts": 430},
                {"lat": center_lat + lateral + 0.12, "lon": center_lon + side_factor * 0.78, "altitude_ft": 29500, "speed_kts": 455},
                {"lat": center_lat + lateral + 0.03, "lon": center_lon - side_factor * 0.12, "altitude_ft": 30000, "speed_kts": 460},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if category == "high_value_asset":
            points = [
                {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.5, "altitude_ft": 26000, "speed_kts": 280},
                {"lat": center_lat + lateral + 0.12, "lon": center_lon + side_factor * 1.1, "altitude_ft": 26000, "speed_kts": 280},
                {"lat": center_lat + lateral - 0.05, "lon": center_lon + side_factor * 1.3, "altitude_ft": 26000, "speed_kts": 280},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if category == "interceptor":
            points = [
                {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.4, "altitude_ft": 32000, "speed_kts": 450},
                {"lat": center_lat + lateral + 0.15, "lon": center_lon + side_factor * 0.5, "altitude_ft": 34000, "speed_kts": 500},
                {"lat": center_lat + lateral + 0.08, "lon": center_lon + side_factor * 0.1, "altitude_ft": 34000, "speed_kts": 500},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if category == "escort":
            points = [
                {"lat": center_lat + lateral + 0.1, "lon": center_lon + side_factor * 1.5, "altitude_ft": 31000, "speed_kts": 440},
                {"lat": center_lat + lateral + 0.2, "lon": center_lon + side_factor * 0.6, "altitude_ft": 33000, "speed_kts": 480},
                {"lat": center_lat + lateral + 0.12, "lon": center_lon + side_factor * 0.15, "altitude_ft": 33000, "speed_kts": 480},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        if category == "strike":
            points = [
                {"lat": center_lat + lateral - 0.08, "lon": center_lon + side_factor * 1.7, "altitude_ft": 28000, "speed_kts": 430},
                {"lat": center_lat + lateral + 0.1, "lon": center_lon + side_factor * 0.7, "altitude_ft": 30000, "speed_kts": 460},
                {"lat": center_lat + lateral + 0.05, "lon": center_lon - side_factor * 0.1, "altitude_ft": 30000, "speed_kts": 460},
            ]
            return self.apply_fallback_route(points, side_factor, fallback_route_style)
        points = [
            {"lat": center_lat + lateral, "lon": center_lon + side_factor * 1.6, "altitude_ft": 30000, "speed_kts": 420},
            {"lat": center_lat + lateral + 0.18, "lon": center_lon + side_factor * 0.5, "altitude_ft": 32000, "speed_kts": 450},
            {"lat": center_lat + lateral + 0.06, "lon": center_lon + side_factor * 0.05, "altitude_ft": 32000, "speed_kts": 450},
        ]
        return self.apply_fallback_route(points, side_factor, fallback_route_style)

    def apply_fallback_route(self, points, side_factor, fallback_route_style):
        if not fallback_route_style:
            return points
        adjusted = list(points)
        last = dict(adjusted[-1])
        if fallback_route_style == "egress":
            adjusted.append(
                {
                    "lat": last["lat"] + 0.14,
                    "lon": last["lon"] - side_factor * 0.8,
                    "altitude_ft": max(26000, int(last.get("altitude_ft", 30000))),
                    "speed_kts": max(430, int(last.get("speed_kts", 450))),
                }
            )
        elif fallback_route_style == "close_protect":
            adjusted.append(
                {
                    "lat": last["lat"] - 0.03,
                    "lon": last["lon"] + side_factor * 0.12,
                    "altitude_ft": max(24000, int(last.get("altitude_ft", 28000)) - 2000),
                    "speed_kts": max(280, int(last.get("speed_kts", 380)) - 40),
                }
            )
        elif fallback_route_style == "hold":
            adjusted.append(dict(last))
        return adjusted

    def slugify(self, text):
        return re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_") or "item"

    def render_operational_briefing(self, model):
        lines = [
            f"# {model['mission']['title']}",
            "",
            model["mission"]["summary"],
            "",
            "## Mission Objectives",
            "",
        ]
        for objective in model["mission"]["objectives"]:
            lines.append(f"- {objective['side']}: {objective['description']}")
        task_plan = model.get("task_plan") or {}
        task_sequence = task_plan.get("task_sequence") or []
        if task_sequence:
            lines.extend(["", "## Task Plan", ""])
            commander_intent = task_plan.get("commander_intent")
            if commander_intent:
                lines.append(f"- commander_intent: {commander_intent}")
            for task in task_sequence:
                lines.append(
                    f"- {task['side']} {task['phase']} {task['name']}: {task['desired_effect']}"
                )
                if task.get("depends_on"):
                    lines.append(f"- depends_on: {', '.join(task.get('depends_on', []))}")
                if task.get("supports"):
                    lines.append(f"- supports: {', '.join(task.get('supports', []))}")
                for trigger in task.get("trigger_conditions", [])[:1]:
                    lines.append(f"- trigger: {trigger}")
                for action in task.get("failure_actions", [])[:1]:
                    lines.append(f"- fallback: {action}")
        lines.extend(["", "## Order Of Battle", ""])
        for side in ("blue", "red", "neutral"):
            packages = model["forces"].get(side) or []
            if not packages:
                continue
            lines.append(f"### {side.title()}")
            lines.append("")
            for package in packages:
                details = [package["role"]]
                if package.get("mission_task"):
                    details.append(package["mission_task"].lower())
                if package.get("route_style"):
                    details.append(package["route_style"])
                if package.get("fallback_route_style"):
                    details.append(f"fallback:{package['fallback_route_style']}")
                if package.get("narrative_role"):
                    details.append(package["narrative_role"])
                lines.append(f"- {package['name']}: {package['count']} x {package['category']} ({', '.join(details)})")
                if package.get("target_priority"):
                    lines.append(f"- target_priority: {', '.join(package.get('target_priority', []))}")
                if package.get("timing_notes"):
                    lines.append(f"- timing: {'; '.join(package.get('timing_notes', [])[:2])}")
                contingency_count = package.get("contingency_count")
                if contingency_count is not None and contingency_count != package.get("count"):
                    lines.append(f"- contingency_count: {contingency_count}")
                if package.get("abort_on_failure_of"):
                    lines.append(f"- abort_on_failure_of: {', '.join(package.get('abort_on_failure_of', []))}")
                if package.get("contingency_phase"):
                    lines.append(f"- contingency_phase: {package.get('contingency_phase')}")
            lines.append("")
        lines.extend(["## Engagement Rules", ""])
        for key, value in model["engagement_rules"].items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines).rstrip() + "\n"

    def render_operational_phases_markdown(self, model):
        lines = ["# Phase Script", ""]
        for phase in model["phases"]:
            lines.append(f"## {phase['name']}")
            lines.append("")
            lines.append(
                f"Window: {phase['start_min']} min to {phase['end_min']} min"
            )
            lines.append("")
            lines.append(phase["summary"])
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"