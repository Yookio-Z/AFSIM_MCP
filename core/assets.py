from pathlib import Path


class AssetService:
    def __init__(self, host):
        self.host = host

    GENERATED_AIR_ASSETS_FILE = "platforms/generated_air_assets.txt"
    GENERATED_GROUND_ASSETS_FILE = "platforms/generated_ground_assets.txt"

    def default_icon_for_category(self, category):
        category = str(category).lower()
        if category in ("air_patrol", "strike", "escort", "interceptor"):
            return "fighter"
        if category in ("air_defense", "missile_launcher"):
            return "command_truck"
        if category in ("target", "objective"):
            return "target"
        return "aircraft"

    def resolve_operational_asset_profile(self, scenario_kind):
        project_root = self.host.resolve_project_root()
        local_rich_root = None
        if project_root:
            candidate = Path(project_root) / "iran_israel_regional_escalation"
            if candidate.exists():
                local_rich_root = candidate

        if local_rich_root:
            return {
                "mode": "rich_local_demo",
                "asset_root": str(local_rich_root),
                "entry_includes": [],
                "scenario_includes": ["platforms/iran_israel_assets.txt"],
                "blue_fighter_type": "BLUE_FIGHTER_AIR",
                "red_fighter_type": "RED_FIGHTER_AIR",
                "blue_target_type": "TARGET",
                "red_target_type": "TARGET",
                "blue_air_defense_battery_type": "BLUE_NAVAL_SAM_BATTERY",
                "blue_air_defense_launcher_type": "BLUE_NAVAL_SAM_LAUNCHER",
                "blue_air_defense_ttr_type": "BLUE_ABM_TTR",
                "red_missile_launcher_type": "RED_MRBM_1_LAUNCHER",
                "blue_missile_launcher_type": "ISRAEL_RETALIATORY_MRBM_LAUNCHER",
                "supports_observer": True,
            }

        demos_root = self.host.resolve_demos_root()
        if demos_root:
            air_to_air_root = Path(demos_root) / "air_to_air"
            if air_to_air_root.exists():
                return {
                    "mode": "air_to_air_demo",
                    "asset_root": str(air_to_air_root),
                    "entry_includes": ["_common.txt"],
                    "scenario_includes": ["platforms/lte_fighter.txt"],
                    "blue_fighter_type": "BLUE_FIGHTER",
                    "red_fighter_type": "RED_FIGHTER",
                    "blue_target_type": "TARGET",
                    "red_target_type": "TARGET",
                    "supports_observer": True,
                }

        return {
            "mode": "generated_structured",
            "asset_root": None,
            "entry_includes": [],
            "scenario_includes": [self.GENERATED_AIR_ASSETS_FILE, self.GENERATED_GROUND_ASSETS_FILE],
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

    def default_weapons_for_role(self, role):
        role = str(role).lower()
        if role == "strike":
            return {"fox3": 4, "fox2": 2}
        if role == "escort":
            return {"fox3": 6, "fox2": 2}
        if role == "intercept":
            return {"fox3": 6, "fox2": 2}
        if role == "support":
            return {"fox3": 0, "fox2": 0}
        return {"fox3": 5, "fox2": 2}

    def risk_weapon_for_role(self, role):
        role = str(role).lower()
        if role in ("strike", "escort"):
            return 0.9
        if role == "intercept":
            return 1.0
        if role == "support":
            return 0.3
        return 0.8

    def commit_range_for_role(self, role):
        role = str(role).lower()
        if role == "intercept":
            return 45
        if role == "escort":
            return 40
        if role == "strike":
            return 32
        if role == "support":
            return 25
        return 35

    def select_preferred_target(self, objectives, preferred_side):
        for objective in objectives:
            if objective.get("side") == preferred_side:
                return objective
        return objectives[0] if objectives else None