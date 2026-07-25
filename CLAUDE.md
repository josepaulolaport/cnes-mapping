# CNES Database Agent (Claude Code)

This project connects to the **CNES MCP server** (`cnes-mcp-test`) for Brazilian health establishment data in PostgreSQL schema `mcp_test`.

## Before you query or analyze

**Ask the user clarifying questions** when any of these are unclear — do not guess:

| Topic | Ask |
|-------|-----|
| Geography | Which state, municipality, or all Brazil? |
| Active records | Active facilities only, or include deactivated? |
| Output | Quick chat answer, written report, or Excel/CSV export? |
| Entity type | What counts as "hospital", "clinic", "doctor"? Use `facility_type_name` (legal type), `unit_type_name` (CNES unit), or `occupations.occupation_name` / CBO `occupation_code` |
| Specialty | Dermatology etc.: join `occupations` — `occupation_code = '225135'` or `occupation_name ILIKE '%DERMAT%'` |
| Payment mode | SUS vs private? Use `facility_agreements` + `agreement_types` |
| Equipment | Which equipment type or search term? |

**Defaults** (only if user says "don't care" or "active only"):
- Active facilities: `deactivation_reason_code IS NULL`
- Current staff: `termination_date IS NULL`

## Which tool to use

```
Unclear request?     → Ask user first (no tools)
Need schema info?    → describe_table / search_schema
Small lookup (≤500)? → execute_query
Big analysis/export? → run_analysis
Unsure?              → get_agent_policy (MCP tool)
```

### `execute_query` — quick & small
- Sample rows, one facility lookup, schema checks
- NOT for GROUP BY over millions of rows

### `run_analysis` — deep & exports
- Aggregations, rankings, cross-region comparisons
- Excel/CSV/report output
- **Before running:** state a 2–4 bullet plan; confirm output format if not specified

## Workflow

1. Parse request → list ambiguities → **ask user** if any
2. Confirm filters (active, geography)
3. Pick tool
4. Return summary + file paths (not raw huge tables)

## MCP tools reference

| Tool | Purpose |
|------|---------|
| `get_agent_policy` | Full decision rules (call when unsure) |
| `get_analysis_guide` | Python helpers for `run_analysis` |
| `describe_table` | Schema + sample rows |
| `execute_query` | Small SELECT only (auto LIMIT 500) |
| `run_analysis` | Python pandas analysis + Excel export |

## Analysis Python setup

```bash
cd mcp && python3 -m pip install -r requirements-analysis.txt
```

Output files: `mcp/analysis_runs/{run_id}/`
