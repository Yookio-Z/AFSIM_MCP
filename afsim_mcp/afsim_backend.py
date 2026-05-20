"""AFSIM backend integration for MCP server.

Provides helpers to locate and run AFSIM executables:
  - wsf_wizard  (Wizard / GUI scenario builder)
  - wsf_mission (Mission Planner)
  - wsf_warlock (Warlock batch runner)
  - wsf_mystic  (Mystic post-processor)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical names for the four main AFSIM executables
AFSIM_TOOLS = {
    "wizard": "wsf_wizard",
    "mission": "wsf_mission",
    "warlock": "wsf_warlock",
    "mystic": "wsf_mystic",
}


class AfsimBackend:
    """Manages AFSIM binary paths and tool execution."""

    def __init__(self, afsim_home: str = "") -> None:
        self._afsim_home = Path(afsim_home) if afsim_home else None
        self._binary_paths: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_afsim_home(self, path: str) -> None:
        """Set the root AFSIM installation directory."""
        self._afsim_home = Path(path)
        logger.info("AFSIM_HOME set to '%s'", path)

    def get_afsim_home(self) -> str:
        """Return the configured AFSIM_HOME (or empty string)."""
        return str(self._afsim_home) if self._afsim_home else ""

    def set_binary_path(self, tool: str, path: str) -> None:
        """Override the path for a specific AFSIM tool.

        Parameters
        ----------
        tool:
            Tool key: 'wizard', 'mission', 'warlock', 'mystic', or any binary name.
        path:
            Absolute path to the binary.
        """
        self._binary_paths[tool.lower()] = path
        logger.info("Binary path for '%s' set to '%s'", tool, path)

    def get_binary_path(self, tool: str) -> str | None:
        """Return the resolved path for an AFSIM tool, or None if not found."""
        key = tool.lower()
        # 1. Explicit override
        if key in self._binary_paths:
            return self._binary_paths[key]
        # 2. Look in AFSIM_HOME/bin
        canonical = AFSIM_TOOLS.get(key, key)
        if self._afsim_home:
            candidate = self._afsim_home / "bin" / canonical
            if candidate.exists():
                return str(candidate)
        # 3. System PATH
        found = shutil.which(canonical)
        if found:
            return found
        return None

    def list_binary_paths(self) -> dict[str, str | None]:
        """Return resolved paths for all known AFSIM tools."""
        return {name: self.get_binary_path(name) for name in AFSIM_TOOLS}

    def detect_afsim_installation(self) -> dict[str, object]:
        """Auto-detect AFSIM installation details from the environment."""
        env_home = os.environ.get("AFSIM_HOME", "")
        if env_home and not self._afsim_home:
            self._afsim_home = Path(env_home)
            logger.info("Auto-detected AFSIM_HOME from environment: '%s'", env_home)

        binaries = self.list_binary_paths()
        return {
            "afsim_home": str(self._afsim_home) if self._afsim_home else env_home or None,
            "binaries": binaries,
            "all_found": all(v is not None for v in binaries.values()),
        }

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def run_wizard(
        self,
        scenario_file: str | None = None,
        extra_args: list[str] | None = None,
        detach: bool = True,
    ) -> dict[str, object]:
        """Launch wsf_wizard (GUI scenario builder)."""
        return self._run_tool("wizard", scenario_file, extra_args or [], detach=detach)

    def run_mission(
        self,
        scenario_file: str | None = None,
        extra_args: list[str] | None = None,
        detach: bool = True,
    ) -> dict[str, object]:
        """Launch wsf_mission (Mission Planner)."""
        return self._run_tool("mission", scenario_file, extra_args or [], detach=detach)

    def run_warlock(
        self,
        scenario_file: str,
        output_dir: str = ".",
        extra_args: list[str] | None = None,
    ) -> dict[str, object]:
        """Run wsf_warlock batch simulation.

        Parameters
        ----------
        scenario_file:
            Path to the AFSIM scenario file.
        output_dir:
            Directory to write output files.
        """
        args = ["-o", output_dir] + (extra_args or [])
        return self._run_tool("warlock", scenario_file, args, detach=False)

    def run_mystic(
        self,
        results_dir: str,
        extra_args: list[str] | None = None,
        detach: bool = True,
    ) -> dict[str, object]:
        """Launch wsf_mystic post-processor."""
        return self._run_tool("mystic", results_dir, extra_args or [], detach=detach)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_tool(
        self,
        tool: str,
        primary_arg: str | None,
        extra_args: list[str],
        detach: bool,
    ) -> dict[str, object]:
        binary = self.get_binary_path(tool)
        if not binary:
            msg = (
                f"AFSIM tool '{tool}' not found. "
                "Set AFSIM_HOME or use set_binary_path()."
            )
            logger.error(msg)
            return {"success": False, "error": msg, "tool": tool}

        cmd = [binary]
        if primary_arg:
            cmd.append(primary_arg)
        cmd.extend(extra_args)

        logger.info("Launching AFSIM tool: %s", " ".join(cmd))
        try:
            if detach:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"success": True, "tool": tool, "pid": proc.pid, "cmd": cmd}
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                return {
                    "success": result.returncode == 0,
                    "tool": tool,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-4000:] if result.stdout else "",
                    "stderr": result.stderr[-2000:] if result.stderr else "",
                    "cmd": cmd,
                }
        except FileNotFoundError:
            msg = f"Binary not found at '{binary}'."
            logger.error(msg)
            return {"success": False, "error": msg, "tool": tool}
        except subprocess.TimeoutExpired:
            msg = f"Tool '{tool}' timed out."
            logger.error(msg)
            return {"success": False, "error": msg, "tool": tool}
        except Exception as exc:
            logger.exception("Error running tool '%s': %s", tool, exc)
            return {"success": False, "error": str(exc), "tool": tool}
