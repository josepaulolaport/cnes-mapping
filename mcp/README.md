# CNES MCP Test Server

Read-only MCP server for the `mcp_test` PostgreSQL schema.

## Prerequisites

- PostgreSQL with `mcp_test` schema populated (`../scripts/run_mcp_test_migration.sh`)
- Node.js 18+
- Python 3.9+ with analysis dependencies

## Setup

```bash
cd mcp
npm install
npm run build

# Python helpers for run_analysis
pip install -r requirements-analysis.txt
```

## Environment

```bash
export CNES_DATABASE_URL="postgresql://mcp_test_reader:PASS@localhost:5432/atlasmed_test?options=-csearch_path%3Dmcp_test"
```

## Tools

| Tool | Description |
|------|-------------|
| `list_tables` | All tables/views with row counts |
| `describe_table` | Column metadata, PK/FK, sample rows |
| `get_relationships` | FK graph |
| `search_schema` | Keyword search |
| `execute_query` | Read-only SELECT (auto-LIMIT 500) — small lookups only |
| `run_analysis` | **Execute Python** for aggregations, deep dives, Excel/CSV export |
| `list_analysis_runs` | Recent analysis output files |
| `get_analysis_guide` | Docs + examples for writing analysis code |

## Deep analysis workflow

For questions over millions of rows, the AI should use `run_analysis` instead of `execute_query`:

1. Call `get_analysis_guide` for helper API
2. Write Python using `query()`, `save_excel()`, `write_report()`
3. Script runs locally, returns stdout summary + file paths
4. Excel files land in `mcp/analysis_runs/{run_id}/`

Example user prompts:

- *"Export active facilities by state to Excel"*
- *"Analyze equipment distribution across regions — give me a written summary"*
- *"Deep dive: top 50 municipalities by active hospital count"*

## Cursor config

See `.cursor/mcp.json` in project root.
