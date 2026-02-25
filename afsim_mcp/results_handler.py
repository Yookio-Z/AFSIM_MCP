"""Results handling for AFSIM MCP server."""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

from .models import ResultFormat, SimulationResult

logger = logging.getLogger(__name__)


class ResultsHandler:
    """Handles AFSIM simulation results (.aer, .evt, .csv, .json)."""

    SUPPORTED_EXTENSIONS = {
        ".aer": ResultFormat.AER,
        ".evt": ResultFormat.EVT,
        ".csv": ResultFormat.CSV,
        ".json": ResultFormat.JSON,
    }

    def __init__(self, results_dir: str = "simulation_output") -> None:
        self._results_dir = Path(results_dir)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_result_files(
        self,
        run_id: str | None = None,
        directory: str | None = None,
        formats: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """List available result files.

        Parameters
        ----------
        run_id:
            Filter to a specific run output sub-directory (optional).
        directory:
            Explicit directory to scan (overrides default).
        formats:
            List of format extensions to include (e.g. ['.aer', '.csv']).
        """
        search_dir = Path(directory) if directory else self._results_dir
        if run_id:
            # Scan all sub-directories for the run_id prefix
            matching: list[Path] = []
            for d in search_dir.iterdir():
                if d.is_dir() and run_id in d.name:
                    matching.append(d)
            search_dir = matching[0] if matching else search_dir / run_id

        exts = set(formats) if formats else set(self.SUPPORTED_EXTENSIONS)
        results: list[dict[str, object]] = []
        if not search_dir.exists():
            return results

        for path in search_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in exts:
                stat = path.stat()
                fmt = self.SUPPORTED_EXTENSIONS.get(path.suffix.lower(), ResultFormat.CSV)
                results.append(
                    {
                        "file_path": str(path),
                        "format": fmt,
                        "size_bytes": stat.st_size,
                        "created_at": _mtime_iso(stat),
                    }
                )
        logger.info("Found %d result files in '%s'", len(results), search_dir)
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_csv(
        self,
        file_path: str,
        columns: list[str] | None = None,
        max_rows: int = 1000,
    ) -> dict[str, Any]:
        """Read a CSV result file and return rows.

        Parameters
        ----------
        file_path:
            Path to the CSV file.
        columns:
            Subset of column names to include.  All columns if None.
        max_rows:
            Maximum number of data rows to return.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {file_path}")
        if path.suffix.lower() != ".csv":
            raise ValueError(f"Expected .csv file, got: {path.suffix}")

        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            all_columns = reader.fieldnames or []
            selected = columns if columns else list(all_columns)
            rows: list[dict] = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append({k: row[k] for k in selected if k in row})

        return {
            "file_path": str(path),
            "columns": selected,
            "row_count": len(rows),
            "rows": rows,
        }

    def query_evt(self, file_path: str, max_lines: int = 500) -> dict[str, Any]:
        """Read an AFSIM .evt event file and return lines."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {file_path}")

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
        return {
            "file_path": str(path),
            "line_count": len(lines),
            "lines": lines,
        }

    def query_aer(self, file_path: str, max_lines: int = 500) -> dict[str, Any]:
        """Read an AFSIM .aer archive/result file and return lines."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {file_path}")

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
        return {
            "file_path": str(path),
            "line_count": len(lines),
            "lines": lines,
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_to_json(self, file_path: str, output_path: str | None = None) -> str:
        """Convert a CSV result file to JSON.  Returns output path."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {file_path}")

        if path.suffix.lower() == ".csv":
            data = self.query_csv(file_path, max_rows=100_000)
            rows = data["rows"]
        else:
            # For .evt/.aer treat each line as a record
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            rows = [{"line": i + 1, "content": line} for i, line in enumerate(lines)]

        out_path = Path(output_path) if output_path else path.with_suffix(".json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        logger.info("Exported '%s' → '%s'", file_path, out_path)
        return str(out_path)

    def get_result_summary(self, directory: str | None = None) -> dict[str, Any]:
        """Return a summary of all results in a directory."""
        search_dir = Path(directory) if directory else self._results_dir
        files = self.list_result_files(directory=str(search_dir))
        by_format: dict[str, int] = {}
        total_bytes = 0
        for f in files:
            fmt = f["format"]
            fmt_key = fmt.value if hasattr(fmt, "value") else str(fmt)
            by_format[fmt_key] = by_format.get(fmt_key, 0) + 1
            total_bytes += int(f["size_bytes"])
        return {
            "directory": str(search_dir),
            "total_files": len(files),
            "by_format": by_format,
            "total_size_bytes": total_bytes,
        }


def _mtime_iso(stat: os.stat_result) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
