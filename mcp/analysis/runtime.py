"""
CNES analysis runtime — injected into every run_analysis script.
Provides read-only DB access and safe artifact output helpers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT_DIR = Path(os.environ["ANALYSIS_OUTPUT_DIR"])
DB_URL = os.environ["CNES_DATABASE_URL"]
SCHEMA = os.environ.get("CNES_SCHEMA", "mcp_test")
ARTIFACTS: list[str] = []


def query(sql: str) -> pd.DataFrame:
    """Run a read-only SELECT and return a DataFrame. Schema is mcp_test."""
    normalized = sql.strip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        raise ValueError("Only SELECT queries are allowed in analysis scripts")
    forbidden = (
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "GRANT", "REVOKE", "COPY", "EXECUTE",
    )
    for kw in forbidden:
        if kw in normalized:
            raise ValueError(f"Forbidden SQL keyword: {kw}")

    return pd.read_sql_query(sql, DB_URL)


def _track(path: Path) -> str:
    rel = str(path.relative_to(OUTPUT_DIR))
    ARTIFACTS.append(rel)
    return rel


def save_excel(df: pd.DataFrame, filename: str = "analysis.xlsx", sheet_name: str = "data") -> str:
    """Save DataFrame to Excel (.xlsx) in the run output folder."""
    path = OUTPUT_DIR / filename
    df.to_excel(path, index=False, sheet_name=sheet_name, engine="openpyxl")
    return _track(path)


def save_csv(df: pd.DataFrame, filename: str = "analysis.csv") -> str:
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False)
    return _track(path)


def save_json(data: Any, filename: str = "analysis.json") -> str:
    path = OUTPUT_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return _track(path)


def write_report(text: str, filename: str = "report.md") -> str:
    """Write a markdown/text summary report."""
    path = OUTPUT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return _track(path)


def print_summary(title: str, df: pd.DataFrame, max_rows: int = 20) -> None:
    """Print a compact summary to stdout (returned to the AI)."""
    print(f"\n=== {title} ===")
    print(f"Rows: {len(df):,} | Columns: {len(df.columns)}")
    if len(df) == 0:
        print("(empty)")
        return
    print(df.head(max_rows).to_string(index=False))
    if len(df) > max_rows:
        print(f"... ({len(df) - max_rows:,} more rows not shown)")
