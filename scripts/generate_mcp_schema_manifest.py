#!/usr/bin/env python3
"""Generate mcp/schema_manifest.json from live PostgreSQL metadata."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("Install psycopg2-binary: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

CRITICAL_RULES = [
    "Always qualify tables: mcp_test.table_name (or set search_path to mcp_test)",
    "Active facility: deactivation_reason_code IS NULL",
    "Deactivated facility: deactivation_reason_code IS NOT NULL",
    "Active professional at facility: termination_date IS NULL",
    "Terminated professional: termination_date IS NOT NULL",
    "Equipment in use: operational_status = 'E' AND quantity > 0",
    "Prefer facility_search_view for facility discovery with aggregated counts",
    "Prefer professional_search_view for professional discovery",
    "occupation_code is CBO Brazilian occupation/specialty code — join occupations for labels",
    "Find specialists by occupation_name ILIKE (e.g. '%DERMAT%') or occupation_code (e.g. 225135)",
    "service_type: S=SUS/public, N=private",
    "facility_type_code = legal establishment type (HOSPITAL, AMBULATORIO); unit_type_code/unit_type_name = CNES unit classification (CONSULTORIO ISOLADO, CLINICA/CENTRO DE ESPECIALIDADE)",
    "unit_subtype_name is populated for ~21% of facilities (CAPS level, UPA, hospital porte); NULL otherwise",
    "Filter private vs SUS payment via facility_agreements + agreement_types (SUS, PARTICULAR, etc.)",
]

TABLE_BUSINESS_CONTEXT: dict[str, dict[str, Any]] = {
    "states": {
        "description": "Brazilian states (UF). Reference table.",
        "common_filters": [],
        "example_queries": [
            "SELECT state_code, state_name FROM mcp_test.states ORDER BY state_name",
        ],
    },
    "municipalities": {
        "description": "Brazilian municipalities. Join via municipality_id (IBGE code).",
        "joins": {"states": "municipalities.state_code = states.state_code"},
        "example_queries": [
            "SELECT m.municipality_name, s.state_code FROM mcp_test.municipalities m JOIN mcp_test.states s ON m.state_code = s.state_code WHERE s.state_code = 'SP' LIMIT 10",
        ],
    },
    "facilities": {
        "description": "Master health establishments registry — PRIMARY sales target.",
        "common_filters": ["deactivation_reason_code IS NULL"],
        "joins": {
            "municipalities": "facilities.municipality_id = municipalities.municipality_id",
            "facility_types": "facilities.facility_type_code = facility_types.facility_type_code",
            "deactivation_reasons": "facilities.deactivation_reason_code = deactivation_reasons.deactivation_code",
            "maintainers": "facilities.owner_tax_id = maintainers.tax_id",
        },
        "example_queries": [
            "SELECT trade_name, unit_type_name, unit_subtype_name FROM mcp_test.facilities WHERE deactivation_reason_code IS NULL AND unit_type_code = '36' LIMIT 10",
        ],
    },
    "maintainers": {
        "description": "Facility maintainer organizations (mantenedora) — corporate/parent entity.",
        "joins": {"facilities": "facilities.owner_tax_id = maintainers.tax_id"},
    },
    "agreement_types": {
        "description": "Payment agreement lookup (SUS, PARTICULAR, health plans).",
        "joins": {"facility_agreements": "facility_agreements.agreement_code = agreement_types.agreement_code"},
    },
    "care_types": {
        "description": "Care delivery mode lookup (ambulatorial, internacao).",
        "joins": {"facility_agreements": "facility_agreements.care_type_code = care_types.care_type_code"},
    },
    "occupations": {
        "description": "CBO occupation/specialty lookup (~2.7k codes). From tbAtividadeProfissional.",
        "joins": {
            "facility_professionals": "facility_professionals.occupation_code = occupations.occupation_code",
            "professional_workload": "professional_workload.occupation_code = occupations.occupation_code",
        },
        "example_queries": [
            "SELECT occupation_code, occupation_name FROM mcp_test.occupations WHERE occupation_name ILIKE '%DERMAT%' LIMIT 10",
            "SELECT p.full_name, o.occupation_name FROM mcp_test.facility_professionals fp JOIN mcp_test.professionals p ON fp.professional_id = p.professional_id JOIN mcp_test.occupations o ON fp.occupation_code = o.occupation_code WHERE o.occupation_code = '225135' AND fp.termination_date IS NULL LIMIT 10",
        ],
    },
    "facility_agreements": {
        "description": "Payment/care agreements accepted by each facility (~1M rows).",
        "joins": {
            "facilities": "facility_agreements.facility_id = facilities.facility_id",
            "agreement_types": "facility_agreements.agreement_code = agreement_types.agreement_code",
            "care_types": "facility_agreements.care_type_code = care_types.care_type_code",
        },
        "example_queries": [
            "SELECT f.trade_name, at.agreement_name FROM mcp_test.facility_agreements fa JOIN mcp_test.facilities f ON fa.facility_id = f.facility_id JOIN mcp_test.agreement_types at ON fa.agreement_code = at.agreement_code WHERE at.agreement_name = 'PARTICULAR' AND f.deactivation_reason_code IS NULL LIMIT 10",
        ],
    },
    "physical_installations": {
        "description": "Catalog of physical installation types (consulting rooms, specialized clinics).",
        "joins": {"facility_physical_installations": "facility_physical_installations.installation_code = physical_installations.installation_code"},
    },
    "facility_physical_installations": {
        "description": "Physical installations present at each facility (~1.1M rows).",
        "joins": {
            "facilities": "facility_physical_installations.facility_id = facilities.facility_id",
            "physical_installations": "facility_physical_installations.installation_code = physical_installations.installation_code",
        },
    },
    "facility_representatives": {
        "description": "Official legal representatives at facilities (~2.7k rows). From rlEstabRepresentante. One row per facility when registered.",
        "joins": {"facilities": "facility_representatives.facility_id = facilities.facility_id"},
        "example_queries": [
            "SELECT f.trade_name, fr.representative_name, fr.role_title, fr.email FROM mcp_test.facility_representatives fr JOIN mcp_test.facilities f ON fr.facility_id = f.facility_id WHERE f.deactivation_reason_code IS NULL AND fr.email IS NOT NULL LIMIT 10",
            "SELECT representative_name, role_title, email FROM mcp_test.facility_search_view WHERE state_code = 'SP' AND representative_email IS NOT NULL LIMIT 10",
        ],
    },
    "professionals": {
        "description": "Healthcare professionals (doctors, nurses, technicians).",
        "example_queries": [
            "SELECT professional_id, full_name FROM mcp_test.professionals WHERE full_name ILIKE '%SILVA%' LIMIT 10",
        ],
    },
    "facility_professionals": {
        "description": "Employment links: who works where. Filter termination_date IS NULL for current staff.",
        "common_filters": ["termination_date IS NULL"],
        "joins": {
            "facilities": "facility_professionals.facility_id = facilities.facility_id",
            "professionals": "facility_professionals.professional_id = professionals.professional_id",
            "occupations": "facility_professionals.occupation_code = occupations.occupation_code",
        },
        "example_queries": [
            "SELECT fp.facility_id, p.full_name, o.occupation_name FROM mcp_test.facility_professionals fp JOIN mcp_test.professionals p ON fp.professional_id = p.professional_id JOIN mcp_test.occupations o ON fp.occupation_code = o.occupation_code WHERE fp.termination_date IS NULL LIMIT 10",
        ],
    },
    "facility_equipment": {
        "description": "Equipment inventory per facility.",
        "common_filters": ["operational_status = 'E'", "quantity > 0"],
        "joins": {
            "facilities": "facility_equipment.facility_id = facilities.facility_id",
            "equipment_categories": "facility_equipment.equipment_category_code = equipment_categories.category_code",
        },
        "example_queries": [
            "SELECT f.trade_name, fe.equipment_code, fe.quantity FROM mcp_test.facility_equipment fe JOIN mcp_test.facilities f ON fe.facility_id = f.facility_id WHERE fe.operational_status = 'E' AND f.deactivation_reason_code IS NULL LIMIT 10",
        ],
    },
    "facility_services": {
        "description": "Services and specialties offered by each facility. Composite PK includes owner_tax_id and address_complement.",
        "common_filters": ["is_active = 1"],
        "joins": {
            "facilities": "facility_services.facility_id = facilities.facility_id",
            "service_specialties": "facility_services.service_code = service_specialties.service_code",
        },
    },
    "professional_workload": {
        "description": "Working hours, council credentials (CRM, CRO), license numbers. PK includes service_type (S=SUS, N=non-SUS).",
        "joins": {
            "facilities": "professional_workload.facility_id = facilities.facility_id",
            "professionals": "professional_workload.professional_id = professionals.professional_id",
            "occupations": "professional_workload.occupation_code = occupations.occupation_code",
        },
        "example_queries": [
            "SELECT pw.facility_id, pw.professional_id, pw.occupation_code, pw.service_type, pw.weekly_hours_ambulatory FROM mcp_test.professional_workload pw WHERE pw.facility_id = '...' LIMIT 10",
        ],
    },
    "facility_search_view": {
        "description": "Pre-aggregated facility search with staff, service, equipment counts.",
        "use_when": "Discovery queries by state, equipment, staff size",
        "example_queries": [
            "SELECT trade_name, state_code, active_professionals_count FROM mcp_test.facility_search_view WHERE status = 'ACTIVE' AND state_code = 'SP' ORDER BY active_professionals_count DESC LIMIT 20",
        ],
    },
    "professional_search_view": {
        "description": "Pre-aggregated professional search with employment, licenses, and occupation_names.",
        "use_when": "Finding professionals by location or specialty (use occupation_names or join occupations)",
    },
    "active_facilities": {
        "description": "Active facilities with municipality and type names.",
        "use_when": "Simple active facility list without aggregations",
    },
    "active_facility_professionals": {
        "description": "Current staff at active facilities only (includes occupation_name).",
        "use_when": "Current employment relationships",
    },
    "facility_equipment_in_use": {
        "description": "Operational equipment at active facilities.",
        "use_when": "Equipment-based sales targeting",
    },
}

VIEW_NAMES = {
    "professional_search_view",
    "facility_search_view",
    "active_facilities",
    "active_facility_professionals",
    "facility_equipment_in_use",
}


def fetch_tables(cur, schema: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.table_name, c.table_type,
               obj_description((quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass) AS table_comment,
               (SELECT reltuples::bigint FROM pg_class pc
                JOIN pg_namespace pn ON pn.oid = pc.relnamespace
                WHERE pn.nspname = c.table_schema AND pc.relname = c.table_name) AS approx_rows
        FROM information_schema.tables c
        WHERE c.table_schema = %s
          AND c.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY c.table_name
        """,
        (schema,),
    )
    return cur.fetchall()


def fetch_columns(cur, schema: str, table: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
               col_description((quote_ident(%s)||'.'||quote_ident(%s))::regclass, c.ordinal_position) AS column_comment
        FROM information_schema.columns c
        WHERE c.table_schema = %s AND c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (schema, table, schema, table),
    )
    return cur.fetchall()


def fetch_primary_key(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE i.indisprimary AND n.nspname = %s AND c.relname = %s
        ORDER BY array_position(i.indkey, a.attnum)
        """,
        (schema, table),
    )
    return [r["attname"] for r in cur.fetchall()]


def fetch_foreign_keys(cur, schema: str, table: str) -> list[dict[str, str]]:
    cur.execute(
        """
        SELECT
            kcu.column_name,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s AND tc.table_name = %s
        """,
        (schema, table),
    )
    return [
        {"column": r["column_name"], "references": f"{r['foreign_table']}.{r['foreign_column']}"}
        for r in cur.fetchall()
    ]


def fetch_exact_count(cur, schema: str, table: str) -> int | None:
    try:
        cur.execute(f'SELECT COUNT(*) AS count FROM "{schema}"."{table}"')
        return int(cur.fetchone()["count"])
    except Exception:
        return None


def build_manifest(schema: str, database_url: str) -> dict[str, Any]:
    conn = psycopg2.connect(database_url)
    conn.set_session(readonly=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tables_section: dict[str, Any] = {}
    views_section: dict[str, Any] = {}

    for row in fetch_tables(cur, schema):
        name = row["table_name"]
        is_view = name in VIEW_NAMES or row["table_type"] == "VIEW"
        ctx = TABLE_BUSINESS_CONTEXT.get(name, {})
        pk = fetch_primary_key(cur, schema, name) if not is_view else []
        fks = fetch_foreign_keys(cur, schema, name) if not is_view else []
        columns = fetch_columns(cur, schema, name)
        # Views: avoid full COUNT(*) on heavy aggregations; use planner estimate.
        if is_view:
            row_count = int(row["approx_rows"]) if row["approx_rows"] is not None else None
        else:
            row_count = fetch_exact_count(cur, schema, name)

        entry = {
            "type": "view" if is_view else "table",
            "description": row["table_comment"] or ctx.get("description", ""),
            "row_count": row_count,
            "primary_key": pk,
            "foreign_keys": fks,
            "columns": [
                {
                    "name": c["column_name"],
                    "type": c["data_type"],
                    "nullable": c["is_nullable"] == "YES",
                    "comment": c["column_comment"] or "",
                }
                for c in columns
            ],
        }
        for key in ("joins", "common_filters", "example_queries", "use_when"):
            if key in ctx:
                entry[key] = ctx[key]

        if is_view:
            views_section[name] = entry
        else:
            tables_section[name] = entry

    cur.close()
    conn.close()

    return {
        "schema": schema,
        "domain": "Brazilian CNES health registry — medical equipment/pharma sales",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "critical_rules": CRITICAL_RULES,
        "tables": tables_section,
        "views": views_section,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MCP schema manifest from PostgreSQL")
    parser.add_argument("--schema", default="mcp_test")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", default="mcp/schema_manifest.json")
    args = parser.parse_args()

    manifest = build_manifest(args.schema, args.database_url)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.output} ({len(manifest['tables'])} tables, {len(manifest['views'])} views)")


if __name__ == "__main__":
    main()
