# CNES SQLite → PostgreSQL (`mcp_test`) Migration & MCP Plan

> **Goal:** Move `output/cnes_data.db` into PostgreSQL under schema **`mcp_test`**, then expose it via a read-only MCP server with rich table descriptions so AI agents can generate precise queries.

**Source of truth:** SQLite schema + data in `output/cnes_data.db` (~2.8 GB)  
**Target:** PostgreSQL schema `mcp_test` on existing instance (`atlasmed_test` or equivalent)  
**Migration method (Phase 2):** pgloader — **schema first, data only**

---

## Overview

```mermaid
flowchart LR
    subgraph phase1 [Phase 1 — Schema]
        A[create_mcp_test_schema.sql] --> B[mcp_test tables + indexes]
        B --> C[COMMENT ON metadata]
        C --> D[mcp_test_reader role]
    end

    subgraph phase2 [Phase 2 — Data]
        E[cnes_data.db] --> F[pgloader data only]
        B --> F
        F --> G[mcp_test populated]
    end

    subgraph phase3 [Phase 3 — Views & verify]
        G --> H[create_mcp_test_views.sql]
        H --> I[row-count validation]
        I --> J[ANALYZE]
    end

    subgraph phase4 [Phase 4 — MCP]
        K[schema manifest JSON] --> L[MCP server]
        C --> L
        G --> L
        L --> M[Cursor mcp.json]
    end

    phase1 --> phase2 --> phase3 --> phase4
```

---

## Inventory

### Source database (`output/cnes_data.db`)

| Type | Count | Notes |
|------|-------|-------|
| Tables | 16 | Reference + main + relationship |
| Views | 5 | Created **after** data load (not in pgloader) |
| Rows (key) | facilities 623k, professionals 7.5M, facility_professionals 864k | Verify post-migration |

### Tables (load order for FK dependencies)

```
1.  states
2.  municipalities
3.  facility_types
4.  deactivation_reasons
5.  service_specialties
6.  equipment_categories
7.  equipment_catalog
8.  professional_councils
9.  service_classifications
10. facility_owners
11. facilities
12. professionals
13. facility_professionals
14. facility_services
15. facility_equipment
16. professional_workload
```

### Views (create in Phase 3, not during pgloader)

```
- professional_search_view
- facility_search_view
- active_facilities
- active_facility_professionals
- facility_equipment_in_use
```

---

## Schema alignment notes

The legacy `sql/create_sales_app_schema.sql` (schema `cnes`) **does not match** the live SQLite DB. The new `mcp_test` schema must be derived from `sql/create_sales_app_schema_sqlite.sql`.

| Area | SQLite (source) | Old PG schema (`cnes`) | `mcp_test` action |
|------|-----------------|------------------------|-------------------|
| Schema name | `main` | `cnes` | **`mcp_test`** |
| `equipment_catalog` PK | `(equipment_code, equipment_type_code)` | `equipment_id SERIAL` | Match SQLite |
| `facility_equipment` PK | `(facility_id, equipment_code, equipment_category_code)` | `(facility_id, equipment_code)` | Match SQLite |
| `professional_workload` PK | includes `employment_type_code` | 3-column PK | Match SQLite |
| `facility_services.classification_code` | nullable | NOT NULL | Match SQLite (nullable) |
| Booleans | `INTEGER 0/1` | `BOOLEAN` | Use `BOOLEAN` in PG |
| Timestamps | `TEXT` / `datetime('now')` | `TIMESTAMP` | Use `TIMESTAMP` in PG |
| View column refs | Some bugs (`reason_code`, `type_name`) | Correct names | Fix in PG views |

---

## Phase 1 — PostgreSQL schema setup

**Duration:** ~1 hour  
**Deliverable:** `sql/create_mcp_test_schema.sql`

### 1.1 Create the schema SQL file

Create `sql/create_mcp_test_schema.sql` by porting `create_sales_app_schema_sqlite.sql` to PostgreSQL:

- `CREATE SCHEMA IF NOT EXISTS mcp_test;`
- `SET search_path TO mcp_test, public;`
- Prefix drops with `mcp_test.` or rely on `search_path`
- Map types: `TEXT` → `VARCHAR`, `REAL` → `DOUBLE PRECISION`, `INTEGER` booleans → `BOOLEAN`
- **Do not** include views in this file (pgloader + views after data)
- **Do not** include helper functions yet (optional, Phase 3)
- Add all `COMMENT ON TABLE` / `COMMENT ON COLUMN` statements (see Phase 1.3)
- Enable extension at database level (outside schema):

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### 1.2 Apply schema

```bash
export DATABASE_URL="postgresql://USER:PASS@localhost:5432/atlasmed_test"

psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql "$DATABASE_URL" -f sql/create_mcp_test_schema.sql
```

### 1.3 Add metadata (COMMENT ON)

Port and extend comments from `create_sales_app_schema.sql`. Every table and every non-obvious column should have a comment. Priority columns:

| Table | Critical columns to document |
|-------|------------------------------|
| `facilities` | `deactivation_reason_code` (NULL = active), `facility_id`, `trade_name`, `municipality_id` |
| `facility_professionals` | `termination_date` (NULL = employed), `occupation_code` (CBO) |
| `facility_equipment` | `operational_status` (E/D/M), `quantity` |
| `facility_services` | `is_active` |
| `professional_workload` | `professional_council_code`, `employment_type_code` |

Either embed comments in `create_mcp_test_schema.sql` or add `sql/mcp_test_comments.sql` as a separate apply step.

### 1.4 Create read-only role

```sql
-- Run as superuser / schema owner
CREATE ROLE mcp_test_reader LOGIN PASSWORD '<strong-password>';

GRANT USAGE ON SCHEMA mcp_test TO mcp_test_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mcp_test TO mcp_test_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mcp_test
  GRANT SELECT ON TABLES TO mcp_test_reader;

-- Explicit revoke writes (belt-and-suspenders)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA mcp_test FROM mcp_test_reader;
```

Store credentials in `.env` (gitignored):

```
MCP_TEST_DATABASE_URL=postgresql://mcp_test_reader:PASS@localhost:5432/atlasmed_test?options=-csearch_path%3Dmcp_test
```

---

## Phase 2 — Data migration (pgloader, schema first)

**Duration:** ~30–90 minutes (depends on disk/CPU)  
**Deliverables:** `scripts/migrate_sqlite_to_mcp_test.load`, `scripts/run_mcp_test_migration.sh`

### 2.1 Install pgloader

```bash
# macOS
brew install pgloader

# Verify
pgloader --version
```

### 2.2 pgloader config (data only)

Create `scripts/migrate_sqlite_to_mcp_test.load`:

```lisp
LOAD DATABASE
     FROM sqlite:///Users/josepaulolaport/Documents/projects/cnes_mapping/output/cnes_data.db
     INTO postgresql://USER:PASS@localhost:5432/atlasmed_test

 WITH data only,
      disable triggers,
      reset sequences

  SET maintenance_work_mem to '512MB',
      work_mem to '256MB',
      search_path to 'mcp_test, public'

 CAST type datetime to timestamptz
      drop typemod,
      type text to text
      drop typemod

 ALTER SCHEMA 'main' RENAME TO 'mcp_test';
```

**Important flags:**

| Flag | Why |
|------|-----|
| `data only` | Tables already exist from Phase 1; pgloader only inserts |
| `disable triggers` | Avoid FK violations during bulk load; re-enable after |
| `ALTER SCHEMA 'main' RENAME TO 'mcp_test'` | SQLite `main` → PG `mcp_test` |
| `reset sequences` | Safe even without SERIAL columns |

### 2.3 Pre-migration checklist

- [ ] Phase 1 schema applied successfully
- [ ] All 16 tables exist in `mcp_test` and are **empty**
- [ ] Column names and types match SQLite (run spot-check below)
- [ ] PostgreSQL has enough disk space (~6 GB free recommended)
- [ ] No other process holds locks on `mcp_test` tables

**Spot-check column alignment:**

```bash
sqlite3 output/cnes_data.db "PRAGMA table_info(facilities);" > /tmp/sqlite_facilities.txt
psql "$DATABASE_URL" -c "\d mcp_test.facilities" > /tmp/pg_facilities.txt
diff /tmp/sqlite_facilities.txt /tmp/pg_facilities.txt  # manual review
```

### 2.4 Run migration

Create `scripts/run_mcp_test_migration.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${DATABASE_URL:?Set DATABASE_URL}"

echo "==> Phase 1: Apply schema (idempotent — drops/recreates)"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql "$DATABASE_URL" -f sql/create_mcp_test_schema.sql

echo "==> Phase 2: pgloader (data only)"
pgloader scripts/migrate_sqlite_to_mcp_test.load

echo "==> Phase 3: Re-enable triggers + analyze"
psql "$DATABASE_URL" -f sql/post_mcp_test_migration.sql

echo "==> Done. Run validation queries in docs/MCP_POSTGRES_MIGRATION_PLAN.md"
```

Run:

```bash
chmod +x scripts/run_mcp_test_migration.sh
export DATABASE_URL="postgresql://USER:PASS@localhost:5432/atlasmed_test"
./scripts/run_mcp_test_migration.sh 2>&1 | tee logs/mcp_test_migration.log
```

### 2.5 Post-load SQL

Create `sql/post_mcp_test_migration.sql`:

```sql
SET search_path TO mcp_test, public;

-- Re-enable any disabled triggers (pgloader disable triggers)
-- pgloader typically re-enables automatically; this is a safety net

ANALYZE;

-- Quick sanity counts
SELECT 'states' AS t, COUNT(*) FROM mcp_test.states
UNION ALL SELECT 'municipalities', COUNT(*) FROM mcp_test.municipalities
UNION ALL SELECT 'facilities', COUNT(*) FROM mcp_test.facilities
UNION ALL SELECT 'professionals', COUNT(*) FROM mcp_test.professionals
UNION ALL SELECT 'facility_professionals', COUNT(*) FROM mcp_test.facility_professionals;
```

### 2.6 Known pgloader pitfalls & mitigations

| Risk | Mitigation |
|------|------------|
| Column type mismatch | Schema must mirror SQLite exactly; test with `states` (27 rows) first |
| FK load order | `disable triggers` during load |
| Boolean 0/1 → PG boolean | Cast in schema as BOOLEAN; pgloader maps integers |
| Empty strings vs NULL | Accept as-is initially; document for MCP queries |
| Load fails mid-way | Drop schema tables and re-run Phase 1 + 2 (idempotent script) |
| Wrong schema target | Verify `ALTER SCHEMA 'main' RENAME TO 'mcp_test'` in `.load` file |

**Dry-run suggestion:** Temporarily copy only reference tables to a test SQLite file, run pgloader against that, validate, then run full migration.

---

## Phase 3 — Views, validation & performance

**Duration:** ~1 hour  
**Deliverable:** `sql/create_mcp_test_views.sql`

### 3.1 Create views (PostgreSQL-native)

Port views from `create_sales_app_schema_sqlite.sql` but **fix column name bugs**:

| SQLite view bug | Correct PG reference |
|-----------------|----------------------|
| `dr.reason_code` | `dr.deactivation_code` |
| `dr.reason_description` | `dr.deactivation_reason` |
| `ft.type_name` | `ft.facility_type_name` |
| `ss.specialty_code` / `ss.specialty_name` | `ss.service_code` / `ss.service_name` |

Replace SQLite-specific functions:

| SQLite | PostgreSQL |
|--------|------------|
| `GROUP_CONCAT(x, ', ')` | `STRING_AGG(x, ', ')` |
| `INTEGER` boolean checks | native `BOOLEAN` |

Apply:

```bash
psql "$DATABASE_URL" -f sql/create_mcp_test_views.sql
```

Add `COMMENT ON VIEW` for each view.

### 3.2 Full validation checklist

```sql
-- Row counts must match SQLite
SELECT 'facilities' AS t, COUNT(*) FROM mcp_test.facilities;          -- expect 623208
SELECT COUNT(*) FROM mcp_test.professionals;                         -- expect ~7540800
SELECT COUNT(*) FROM mcp_test.facility_professionals;                -- expect ~863664
SELECT COUNT(*) FROM mcp_test.states;                                -- expect 27

-- FK integrity (should return 0 rows each)
SELECT COUNT(*) FROM mcp_test.facilities f
  LEFT JOIN mcp_test.municipalities m ON f.municipality_id = m.municipality_id
  WHERE m.municipality_id IS NULL AND f.municipality_id IS NOT NULL;

SELECT COUNT(*) FROM mcp_test.facility_professionals fp
  LEFT JOIN mcp_test.facilities f ON fp.facility_id = f.facility_id
  WHERE f.facility_id IS NULL;

-- Active facility rule
SELECT COUNT(*) FROM mcp_test.facilities WHERE deactivation_reason_code IS NULL;

-- Views work
SELECT COUNT(*) FROM mcp_test.facility_search_view;
SELECT COUNT(*) FROM mcp_test.professional_search_view LIMIT 1;
```

### 3.3 Performance indexes (optional, post-load)

Add pg_trgm indexes for MCP text search (already in old PG schema):

```sql
CREATE INDEX IF NOT EXISTS idx_facilities_trade_name_trgm
  ON mcp_test.facilities USING gin (trade_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_professionals_name_trgm
  ON mcp_test.professionals USING gin (full_name gin_trgm_ops);
```

---

## Phase 4 — Schema manifest for AI

**Duration:** ~2 hours  
**Deliverable:** `mcp/schema_manifest.json`

### 4.1 Generate manifest

Create `scripts/generate_mcp_schema_manifest.py` that outputs:

```json
{
  "schema": "mcp_test",
  "domain": "Brazilian CNES health registry — medical equipment/pharma sales",
  "source": "CNES May 2026, migrated from output/cnes_data.db",
  "critical_rules": [
    "Active facility: deactivation_reason_code IS NULL",
    "Active professional at facility: termination_date IS NULL",
    "Equipment in use: operational_status = 'E' AND quantity > 0",
    "Always qualify tables: mcp_test.facilities (or set search_path)"
  ],
  "tables": { "...": { "description", "row_count", "primary_key", "joins", "example_queries" } },
  "views": { "...": { "description", "use_when" } }
}
```

Sources to merge:

- `pg_catalog` / `information_schema` (live column types)
- `COMMENT ON` from PostgreSQL
- `docs/SCHEMA_QUICK_REF.md`
- `docs/SALES_APP_TABLES.md`
- `sql/sample_queries.sql` (update `reference_data` refs → split lookup tables)

### 4.2 Regenerate after each migration

Add to `run_mcp_test_migration.sh` (after validation):

```bash
python scripts/generate_mcp_schema_manifest.py \
  --schema mcp_test \
  --database-url "$DATABASE_URL" \
  --output mcp/schema_manifest.json
```

---

## Phase 5 — MCP server (read-only)

**Duration:** ~4–6 hours  
**Deliverable:** `mcp/` directory + Cursor config

### 5.1 Directory structure

```
mcp/
├── package.json
├── tsconfig.json
├── schema_manifest.json          # generated
├── src/
│   ├── index.ts                  # MCP server entry
│   ├── db.ts                     # pg Pool (mcp_test_reader)
│   ├── tools/
│   │   ├── list_tables.ts
│   │   ├── describe_table.ts
│   │   ├── get_relationships.ts
│   │   ├── search_schema.ts
│   │   └── execute_query.ts      # SELECT only, auto-LIMIT
│   └── resources/
│       ├── overview.ts
│       └── sample_queries.ts
└── README.md
```

### 5.2 MCP tools

| Tool | Input | Output |
|------|-------|--------|
| `list_tables` | — | All tables + views, row counts, one-line description |
| `describe_table` | `name` | Columns, types, nullable, PK/FK, comments, 3 sample rows |
| `get_relationships` | `name?` | FK graph for one table or full schema |
| `search_schema` | `keyword` | Match tables/columns/descriptions |
| `execute_query` | `sql` | SELECT results (max 500 rows, reject writes) |

### 5.3 Safety rules in `execute_query`

1. Reject anything not starting with `SELECT` (after strip/comments)
2. Block `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `COPY`
3. Append `LIMIT 500` if none present
4. Set `statement_timeout` (e.g. 30s) on connection
5. Connect as `mcp_test_reader` only

### 5.4 Cursor MCP config

Add to `.cursor/mcp.json` (project-level):

```json
{
  "mcpServers": {
    "cnes-mcp-test": {
      "command": "node",
      "args": ["mcp/dist/index.js"],
      "env": {
        "CNES_DATABASE_URL": "postgresql://mcp_test_reader:PASS@localhost:5432/atlasmed_test?options=-csearch_path%3Dmcp_test"
      }
    }
  }
}
```

### 5.5 MCP resources (static context for AI)

| URI | Content |
|-----|---------|
| `schema://overview` | Domain summary + critical rules + ER diagram (text) |
| `schema://table/{name}` | Full manifest entry for one table |
| `schema://sample-queries` | Curated queries from `sample_queries.sql` |

---

## File checklist (artifacts to create)

| File | Phase | Status |
|------|-------|--------|
| `sql/create_mcp_test_schema.sql` | 1 | **TODO** — port from SQLite schema |
| `sql/mcp_test_comments.sql` | 1 | **TODO** — optional, or inline in schema |
| `sql/create_mcp_test_views.sql` | 3 | **TODO** — PG views with fixed column names |
| `sql/post_mcp_test_migration.sql` | 2 | **TODO** — ANALYZE + sanity counts |
| `scripts/migrate_sqlite_to_mcp_test.load` | 2 | **TODO** — pgloader config |
| `scripts/run_mcp_test_migration.sh` | 2 | **TODO** — orchestration script |
| `scripts/generate_mcp_schema_manifest.py` | 4 | **TODO** |
| `mcp/` server | 5 | **TODO** |
| `.env.example` | 1 | **TODO** — document `DATABASE_URL`, `MCP_TEST_DATABASE_URL` |

---

## Execution timeline

| Step | Phase | Est. time | Depends on |
|------|-------|-----------|------------|
| Write `create_mcp_test_schema.sql` | 1 | 2h | — |
| Apply schema + create role | 1 | 15m | schema SQL |
| Write pgloader `.load` file | 2 | 30m | schema applied |
| Run pgloader full migration | 2 | 30–90m | pgloader installed |
| Write + apply views | 3 | 1h | data loaded |
| Validate row counts + FKs | 3 | 30m | views applied |
| Generate schema manifest | 4 | 2h | validated DB |
| Build MCP server | 5 | 4–6h | manifest + reader role |
| End-to-end AI query test | 5 | 1h | MCP running |

**Total:** ~2–3 days of focused work

---

## Rollback

To wipe and start over:

```sql
DROP SCHEMA IF EXISTS mcp_test CASCADE;
```

Then re-run Phase 1 → 2 → 3. The `mcp_test` schema is isolated — no impact on `cnes` or `public`.

---

## Success criteria

- [ ] All 16 tables in `mcp_test` with row counts matching SQLite
- [ ] All 5 views query without error
- [ ] `mcp_test_reader` can SELECT but cannot INSERT/UPDATE/DELETE
- [ ] Every table has `COMMENT ON TABLE`; critical columns documented
- [ ] `schema_manifest.json` generated and matches live schema
- [ ] MCP `describe_table('facilities')` returns comments + sample rows
- [ ] MCP `execute_query` runs sample sales queries from `sample_queries.sql`
- [ ] AI can answer: *"Active hospitals in SP with ultrasound equipment"* without schema confusion

---

## Next action

Start with **Phase 1**: create `sql/create_mcp_test_schema.sql` by porting the SQLite schema to PostgreSQL under `mcp_test`. Once that file exists, the rest of the pipeline is mechanical.
