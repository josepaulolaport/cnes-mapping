#!/usr/bin/env python3
"""Restore facility graph from atlasmed-2 into wiped atlasmed-3 via COPY."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

import psycopg2
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SRC_DSN = "host=localhost port=5432 dbname=atlasmed-2 user=postgres password=592jphlap"
DST_DSN = "host=localhost port=5432 dbname=atlasmed-3 user=postgres password=592jphlap"
DST_URL = "postgresql://postgres:592jphlap@localhost:5432/atlasmed-3"
NOW = datetime.now(timezone.utc).replace(tzinfo=None)

ORPHAN_TABLES = [
    "facility_consultant_assignments",
    "facility_notes",
    "facility_professionals",
    "facility_representatives",
    "facility_healthcare_provider_shares",
    "facility_competitor_product_standards",
    "facility_services",
    "facility_vertical_profiles",
    "order_items",
    "orders",
]


def copy_select(src_cur, dst_cur, select_sql: str, dest_table: str, dest_cols: list[str]) -> int:
    buf = io.StringIO()
    src_cur.copy_expert(f"COPY ({select_sql}) TO STDOUT WITH CSV", buf)
    data = buf.getvalue()
    if not data.strip():
        logger.info("%s: no rows", dest_table)
        return 0
    buf.seek(0)
    cols = ", ".join(dest_cols)
    dst_cur.copy_expert(f"COPY {dest_table} ({cols}) FROM STDIN WITH CSV", buf)
    n = data.count("\n")
    logger.info("Copied %s (~%s rows)", dest_table, n)
    return n


def main() -> None:
    src = psycopg2.connect(SRC_DSN)
    dst = psycopg2.connect(DST_DSN)
    sc, dc = src.cursor(), dst.cursor()

    dc.execute("SELECT COUNT(*) FROM facilities")
    if dc.fetchone()[0] > 0:
        raise SystemExit("atlasmed-3 already has facilities — abort")

    dc.execute("SELECT id FROM business_verticals WHERE code='ORTOPEDIA'")
    ortho_vid = dc.fetchone()
    if not ortho_vid:
        raise SystemExit("ORTOPEDIA missing")
    ortho_vid = ortho_vid[0]

    # Clear orphan facility children left from prior wipe
    for t in ORPHAN_TABLES:
        dc.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name=%s
            """,
            (t,),
        )
        if not dc.fetchone():
            continue
        dc.execute(f"DELETE FROM {t}")
        logger.info("Cleared %s (%s)", t, dc.rowcount)

    # Copy users missing in dest (needed for consultant assignments / notes)
    sc.execute("SELECT id FROM users")
    src_users = {r[0] for r in sc.fetchall()}
    dc.execute("SELECT id FROM users")
    dst_users = {r[0] for r in dc.fetchall()}
    missing_users = sorted(src_users - dst_users)
    if missing_users:
        user_cols = [
            "id", "email", "username", "phone_number", "email_verified", "phone_verified",
            "email_verified_at", "phone_verified_at", "password_hash", "password_history",
            "first_name", "last_name", "avatar_url", "status", "token_version",
            "last_login_at", "password_changed_at", "deactivated_at", "suspended_at",
            "two_factor_enabled", "two_factor_secret", "deleted_at", "metadata",
            "role_id", "manager_id", "created_at", "updated_at", "birth_date",
        ]
        # manager_id may point to another missing user — null it for safety
        sc.execute(
            """
            SELECT id, email, username, phone_number, email_verified, phone_verified,
                   email_verified_at, phone_verified_at, password_hash, password_history,
                   first_name, last_name, avatar_url, status, token_version,
                   last_login_at, password_changed_at, deactivated_at, suspended_at,
                   two_factor_enabled, two_factor_secret, deleted_at, metadata,
                   role_id,
                   CASE WHEN manager_id = ANY(%s) THEN NULL ELSE manager_id END,
                   created_at, updated_at, birth_date
            FROM users
            WHERE id = ANY(%s)
            """,
            (missing_users, missing_users),
        )
        rows = sc.fetchall()
        # role_id must exist in dest
        dc.execute("SELECT id FROM roles")
        role_ids = {r[0] for r in dc.fetchall()}
        dc.execute("SELECT id FROM roles ORDER BY id LIMIT 1")
        fallback_role = dc.fetchone()[0]
        fixed = []
        for r in rows:
            r = list(r)
            if r[23] not in role_ids:
                r[23] = fallback_role
            fixed.append(tuple(r))
        dc.executemany(
            f"INSERT INTO users ({', '.join(user_cols)}) VALUES ({', '.join(['%s'] * len(user_cols))}) "
            "ON CONFLICT (id) DO NOTHING",
            fixed,
        )
        logger.info("Copied missing users: %s", len(fixed))

    fac_cols = [
        "id", "name", "legal_name", "trade_name", "cnes_code", "facility_type_code",
        "is_active_in_registry", "registry_deactivation_code", "tax_id_type",
        "cnpj", "cpf", "country", "state", "city", "neighborhood", "street_address",
        "street_number", "address_complement", "postal_code", "location",
        "phone_number", "fax_number", "email", "website_url", "conformity_status",
        "image_url", "unit_type", "unit_subtype",
        "territory_assignment_status", "territory_assignment_source",
        "source_provider", "external_source_id", "source_content_hash",
        "source_first_seen_at", "source_last_seen_at", "source_present", "source_tracked",
        "manually_edited_at", "deactivated_at", "created_at", "updated_at",
        "whatsapp_number", "responsible_name", "opening_hours", "billing_email",
    ]
    select_fac = """
        SELECT
          id, name, legal_name, trade_name, cnes_code, facility_type_code,
          is_active_in_registry, registry_deactivation_code, tax_id_type,
          cnpj, cpf, country, state, city, neighborhood, street_address,
          street_number, address_complement, postal_code, location,
          phone_number, fax_number, email, website_url, conformity_status,
          image_url, unit_type, unit_subtype,
          territory_assignment_status::text, territory_assignment_source::text,
          source_provider, external_source_id, source_content_hash,
          source_first_seen_at, source_last_seen_at, source_present, source_tracked,
          manually_edited_at, deactivated_at, created_at, updated_at,
          whatsapp_number, responsible_name, opening_hours, billing_email
        FROM facilities
    """
    copy_select(sc, dc, select_fac, "facilities", fac_cols)

    # ORTOPEDIA profiles from a2 commercial/purchase on facilities
    sc.execute("SELECT id, commercial_status::text, purchase_status::text FROM facilities")
    profiles = []
    for fid, commercial, purchase in sc.fetchall():
        profiles.append((uuid.uuid4().hex, fid, ortho_vid, True, commercial, purchase, NOW, NOW))
    dc.executemany(
        """
        INSERT INTO facility_vertical_profiles
          (id, facility_id, vertical_id, is_active, commercial_status, purchase_status, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s::commercial_status,%s::purchase_status,%s,%s)
        ON CONFLICT (facility_id, vertical_id) DO NOTHING
        """,
        profiles,
    )
    logger.info("ORTOPEDIA profiles: %s", len(profiles))

    copy_select(
        sc, dc,
        """
        SELECT id, professional_id, facility_id, occupation_code, specialty_label,
               employment_type_code, source_occupation_code, is_prescriber, is_buyer,
               is_decision_maker, is_partner, notes, source_active, source_first_seen_at,
               source_last_seen_at, confirmed_at, confirmed_by_user_id, ended_at,
               ended_by_user_id, end_reason, created_at, updated_at
        FROM facility_professionals
        """,
        "facility_professionals",
        [
            "id", "professional_id", "facility_id", "occupation_code", "specialty_label",
            "employment_type_code", "source_occupation_code", "is_prescriber", "is_buyer",
            "is_decision_maker", "is_partner", "notes", "source_active", "source_first_seen_at",
            "source_last_seen_at", "confirmed_at", "confirmed_by_user_id", "ended_at",
            "ended_by_user_id", "end_reason", "created_at", "updated_at",
        ],
    )

    copy_select(
        sc, dc,
        """
        SELECT id, facility_id, representative_name, role_title, email, tax_id, contact_type,
               phone, notes, source_provider, external_source_key, source_active,
               confirmed_at, confirmed_by_user_id, ended_at, manually_edited_at,
               created_at, updated_at, is_partner, is_administrator, is_decision_maker,
               is_buyer, is_biller, is_secretary
        FROM facility_representatives
        """,
        "facility_representatives",
        [
            "id", "facility_id", "representative_name", "role_title", "email", "tax_id",
            "contact_type", "phone", "notes", "source_provider", "external_source_key",
            "source_active", "confirmed_at", "confirmed_by_user_id", "ended_at",
            "manually_edited_at", "created_at", "updated_at", "is_partner", "is_administrator",
            "is_decision_maker", "is_buyer", "is_biller", "is_secretary",
        ],
    )

    sc.execute("SELECT id, name, type::text, is_active, created_at, updated_at FROM healthcare_providers")
    for prow in sc.fetchall():
        dc.execute(
            """
            INSERT INTO healthcare_providers (id, name, type, is_active, created_at, updated_at)
            VALUES (%s,%s,%s::healthcare_provider_type,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            prow,
        )
    copy_select(
        sc, dc,
        """
        SELECT id, facility_id, healthcare_provider_id, share_percent, source,
               source_first_seen_at, source_last_seen_at, manually_edited_at, created_at, updated_at
        FROM facility_healthcare_provider_shares
        """,
        "facility_healthcare_provider_shares",
        [
            "id", "facility_id", "healthcare_provider_id", "share_percent", "source",
            "source_first_seen_at", "source_last_seen_at", "manually_edited_at",
            "created_at", "updated_at",
        ],
    )

    copy_select(
        sc, dc,
        """
        SELECT id, facility_id, competitor_product_id, standardized_quantity, source,
               source_first_seen_at, source_last_seen_at, created_at, updated_at
        FROM facility_competitor_product_standards
        """,
        "facility_competitor_product_standards",
        [
            "id", "facility_id", "competitor_product_id", "standardized_quantity", "source",
            "source_first_seen_at", "source_last_seen_at", "created_at", "updated_at",
        ],
    )

    # a3 unique: one active assignment per (facility_id, vertical_id)
    sc.execute(
        """
        SELECT DISTINCT ON (facility_id)
               id, facility_id, user_id, started_at, ended_at, assigned_by_user_id,
               end_reason, created_at, updated_at
        FROM facility_consultant_assignments
        ORDER BY facility_id, started_at DESC NULLS LAST, created_at DESC
        """
    )
    ca = sc.fetchall()
    for r in ca:
        dc.execute(
            """
            INSERT INTO facility_consultant_assignments
              (id, facility_id, user_id, started_at, ended_at, assigned_by_user_id,
               end_reason, created_at, updated_at, vertical_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (*r, ortho_vid),
        )
    logger.info("consultant assignments: %s (deduped from a2)", len(ca))

    sc.execute("SELECT COUNT(*) FROM facility_notes")
    if sc.fetchone()[0]:
        copy_select(
            sc, dc,
            "SELECT id, user_id, facility_id, note, created_at, updated_at FROM facility_notes",
            "facility_notes",
            ["id", "user_id", "facility_id", "note", "created_at", "updated_at"],
        )

    copy_select(
        sc, dc,
        """
        SELECT id, legacy_id, facility_id, seller_id, professional_id, status, type,
               surgery_type, surgery_subtype, ordered_at, notes, freight, gross_weight,
               net_weight, currency, usd_exchange_rate, finalized_by_id, finalized_at,
               rejected_by_id, rejection_reason, no_billing_by_id, no_billing_at,
               no_billing_notes, expense_authorized_by_id, expense_authorized_at,
               created_at, updated_at
        FROM orders
        """,
        "orders",
        [
            "id", "legacy_id", "facility_id", "seller_id", "professional_id", "status", "type",
            "surgery_type", "surgery_subtype", "ordered_at", "notes", "freight", "gross_weight",
            "net_weight", "currency", "usd_exchange_rate", "finalized_by_id", "finalized_at",
            "rejected_by_id", "rejection_reason", "no_billing_by_id", "no_billing_at",
            "no_billing_notes", "expense_authorized_by_id", "expense_authorized_at",
            "created_at", "updated_at",
        ],
    )
    copy_select(
        sc, dc,
        """
        SELECT id, legacy_id, order_id, product_id, legacy_product_id, line_number,
               quantity, unit_price, usd_price, batch_number, written_off, created_at, updated_at
        FROM order_items
        """,
        "order_items",
        [
            "id", "legacy_id", "order_id", "product_id", "legacy_product_id", "line_number",
            "quantity", "unit_price", "usd_price", "batch_number", "written_off",
            "created_at", "updated_at",
        ],
    )

    dst.commit()
    src.commit()

    eng = create_engine(DST_URL)
    with eng.connect() as conn:
        summary = {
            r[0]: int(r[1])
            for r in conn.execute(
                text(
                    """
                    SELECT 'facilities', COUNT(*)::text FROM facilities
                    UNION ALL SELECT 'fvp_ortho', COUNT(*)::text FROM facility_vertical_profiles fvp
                      JOIN business_verticals bv ON bv.id=fvp.vertical_id WHERE bv.code='ORTOPEDIA'
                    UNION ALL SELECT 'facility_professionals', COUNT(*)::text FROM facility_professionals
                    UNION ALL SELECT 'facility_representatives', COUNT(*)::text FROM facility_representatives
                    UNION ALL SELECT 'orders', COUNT(*)::text FROM orders
                    UNION ALL SELECT 'order_items', COUNT(*)::text FROM order_items
                    UNION ALL SELECT 'consultant_assignments', COUNT(*)::text FROM facility_consultant_assignments
                    UNION ALL SELECT 'users', COUNT(*)::text FROM users
                    """
                )
            )
        }
    logger.info("RESTORE SUMMARY: %s", summary)
    sc.close()
    dc.close()
    src.close()
    dst.close()


if __name__ == "__main__":
    main()
