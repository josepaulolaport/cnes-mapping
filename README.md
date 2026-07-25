# CNES Mapping

Brazilian CNES health establishment data → PostgreSQL schema + MCP server for AI-assisted queries.

## Quick setup

```bash
git clone https://github.com/josepaulolaport/cnes-mapping.git
cd cnes-mapping
cp .env.example .env          # edit DATABASE_URL
pip install -r requirements.txt
cd mcp && npm install && npm run build

# Download CNES CSVs from DATASUS into:
# BASE_DE_DADOS_CNES_202605/

# PostgreSQL import
export DATABASE_URL=postgresql://user:pass@localhost:5432/atlasmed_test
psql "$DATABASE_URL" -f sql/create_mcp_test_schema.sql
cd scripts && python3 import_modular.py --table all

# MCP (Claude Desktop / Cursor)
cp .mcp.json.example .mcp.json   # set absolute path + CNES_DATABASE_URL
```

## What's included

| Path | Purpose |
|------|---------|
| `sql/` | PostgreSQL schema, migrations, views, FKs |
| `scripts/import_modular.py` | Modular CNES CSV importer |
| `mcp/` | Read-only MCP server (`cnes-mcp-test`) |
| `mcp/schema_manifest.json` | Schema metadata for the AI agent |
| `docs/` | Import guides, table docs |

## Not in repo (gitignored)

- `BASE_DE_DADOS_CNES_202605/` — download from [DATASUS CNES](ftp://ftp.datasus.gov.br/datasus/dados/cnes/)
- `output/`, `logs/`, `import_errors/` — generated artifacts
- `.env` — credentials

## MCP tools

`list_tables`, `describe_table`, `execute_query`, `run_analysis`, `search_schema`, `get_agent_policy`

See `mcp/README.md` and `CLAUDE.md`.

## Data

CNES May 2026 (`202605`) — ~623k facilities, ~7.7M professionals, reference tables for occupations, agreements, maintainers, etc.

Schema: `mcp_test` on PostgreSQL.
