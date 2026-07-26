#!/usr/bin/env python3
"""Fill null facility fields from CNES + clean CRM/excel/cnes contact data in atlasmed-3."""

from __future__ import annotations

import argparse
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "BASE_DE_DADOS_CNES_202605"
DEFAULT_DB = "postgresql://postgres:592jphlap@localhost:5432/atlasmed-3"
NOW = datetime.now(timezone.utc).replace(tzinfo=None)
ORTHO_CBO = "225270"
ORTHO_LABEL = "MEDICO ORTOPEDISTA E TRAUMATOLOGISTA"

ESTAB_COLS = [
    "CO_UNIDADE",
    "CO_CNES",
    "NO_RAZAO_SOCIAL",
    "NO_FANTASIA",
    "NO_LOGRADOURO",
    "NU_ENDERECO",
    "NO_COMPLEMENTO",
    "NO_BAIRRO",
    "CO_CEP",
    "NU_TELEFONE",
    "NU_FAX",
    "NO_EMAIL",
    "NO_URL",
    "NU_CNPJ",
    "NU_LATITUDE",
    "NU_LONGITUDE",
]


def clean_series(s: pd.Series) -> pd.Series:
    out = s.astype(str).str.strip().str.strip('"')
    return out.replace({"": None, "nan": None, "None": None, "NULL": None, "<NA>": None})


def read_csv(path: Path, usecols: Optional[list[str]] = None) -> pd.DataFrame:
    for encoding in ("latin1", "cp1252", "utf-8-sig"):
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding=encoding, usecols=usecols)
            df.columns = df.columns.str.strip().str.strip('"')
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = clean_series(df[col])
            return df
        except Exception:
            continue
    raise RuntimeError(f"Failed to read {path}")


def digits(s: Any, width: Optional[int] = None) -> Optional[str]:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    d = re.sub(r"\D", "", str(s))
    if not d:
        return None
    if width is not None:
        if len(d) > width:
            d = d[-width:]
        d = d.zfill(width)
    return d


def parse_coord(val: Any) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def valid_br_point(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return -34.0 <= lat <= 6.0 and -74.0 <= lon <= -28.0


def first_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    chunk = re.split(r"[/;,|]", str(raw))[0]
    d = digits(chunk)
    if not d:
        return None
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    d = d.lstrip("0")
    if not d or len(d) < 10 or len(d) > 11:
        return None
    if len(set(d)) == 1:
        return None
    return d


def clean_email(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    blob = str(raw).strip().lower()
    parts = re.split(r"[\s;,/|]+|(?:\s+-\s+)", blob)
    for part in parts:
        e = part.strip().strip(".,;:")
        if not e or "@" not in e:
            continue
        local, _, domain = e.partition("@")
        if not local or "." not in domain or " " in e:
            continue
        if re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", e):
            return e[:320]
    m = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", blob)
    return m.group(0)[:320] if m else None


def clean_person_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = re.sub(r"\s+", " ", str(raw).strip())
    return s or None


def clean_website(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip().split()[0].strip(".,;:")
    if not s or "@" in s:
        return None
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s[:500]
    if low.startswith("www.") or re.match(r"^[a-z0-9.\-]+\.[a-z]{2,}", low):
        return ("https://" + s.lstrip("/"))[:500]
    return None


def clean_uf(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = re.sub(r"[^A-Za-z]", "", str(raw)).upper()
    return s if len(s) == 2 else None


def clean_crm_number(raw: Optional[str]) -> Optional[str]:
    d = digits(raw)
    if not d:
        return None
    return (d.lstrip("0") or "0")[:20]


def split_name(full: Optional[str]) -> tuple[str, str]:
    if not full:
        return ("DESCONHECIDO", "DESCONHECIDO")
    parts = re.sub(r"\s+", " ", full.strip()).split(" ")
    if len(parts) == 1:
        return (parts[0], parts[0])
    return (parts[0], " ".join(parts[1:]))


class Filler:
    def __init__(self, csv_dir: Path, db_url: str, cnes_version: str = "202605"):
        self.csv_dir = csv_dir
        self.v = cnes_version
        self.engine = create_engine(db_url, pool_pre_ping=True)

    def f(self, name: str) -> Path:
        return self.csv_dir / f"{name}{self.v}.csv"

    def fix_legacy_occupation(self) -> int:
        with self.engine.begin() as conn:
            r = conn.execute(
                text(
                    """
                    UPDATE facility_professionals
                    SET occupation_code = :cbo,
                        specialty_label = COALESCE(NULLIF(btrim(specialty_label), ''), :label),
                        source_occupation_code = COALESCE(source_occupation_code, 'LEGACY'),
                        updated_at = NOW()
                    WHERE occupation_code = 'LEGACY'
                    """
                ),
                {"cbo": ORTHO_CBO, "label": ORTHO_LABEL},
            )
            n = r.rowcount or 0
        logger.info("Fixed LEGACY occupation → %s: %s", ORTHO_CBO, n)
        return n

    def fill_from_cnes(self) -> dict[str, int]:
        logger.info("=== FILL FROM CNES (null-only) ===")
        usecols = [c for c in ESTAB_COLS]
        # NU_ENDERECO / NU_FAX / NO_URL may be absent in some dumps
        try:
            est = read_csv(self.f("tbEstabelecimento"), usecols=usecols)
        except ValueError:
            usecols = [c for c in ESTAB_COLS if c not in ("NU_ENDERECO", "NU_FAX", "NO_URL")]
            est = read_csv(self.f("tbEstabelecimento"), usecols=usecols)
        for col in ("NU_ENDERECO", "NU_FAX", "NO_URL"):
            if col not in est.columns:
                est[col] = None

        src_cols = [
            "_lat",
            "_lon",
            "_phone",
            "_fax",
            "_email",
            "_web",
            "_cnpj",
            "_cep",
            "_legal",
            "_trade",
            "_street",
            "_num",
            "_comp",
            "_bairro",
        ]
        est["cnes_key"] = est["CO_CNES"].map(lambda x: digits(x, 7))
        est["unit_key"] = est["CO_UNIDADE"]
        est["cnpj_key"] = est["NU_CNPJ"].map(lambda x: digits(x, 14))
        est["_lat"] = est["NU_LATITUDE"].map(parse_coord)
        est["_lon"] = est["NU_LONGITUDE"].map(parse_coord)
        est["_phone"] = est["NU_TELEFONE"].map(first_phone)
        est["_fax"] = est["NU_FAX"].map(first_phone)
        est["_email"] = est["NO_EMAIL"].map(clean_email)
        est["_web"] = est["NO_URL"].map(clean_website)
        est["_cnpj"] = est["NU_CNPJ"].map(lambda x: digits(x, 14))
        est["_cep"] = est["CO_CEP"].map(lambda x: digits(x, 8))
        est["_legal"] = est["NO_RAZAO_SOCIAL"].map(clean_person_name)
        est["_trade"] = est["NO_FANTASIA"].map(clean_person_name)
        est["_street"] = est["NO_LOGRADOURO"].map(clean_person_name)
        est["_num"] = est["NU_ENDERECO"].map(clean_person_name)
        est["_comp"] = est["NO_COMPLEMENTO"].map(clean_person_name)
        est["_bairro"] = est["NO_BAIRRO"].map(clean_person_name)

        by_unit = {
            r["unit_key"]: r
            for r in est.dropna(subset=["unit_key"])
            .drop_duplicates("unit_key", keep="last")[["unit_key", *src_cols]]
            .to_dict(orient="records")
        }
        by_cnes = {
            r["cnes_key"]: r
            for r in est.dropna(subset=["cnes_key"])
            .drop_duplicates("cnes_key", keep="last")[["cnes_key", *src_cols]]
            .to_dict(orient="records")
        }
        cnpj_counts = est.dropna(subset=["cnpj_key"]).groupby("cnpj_key").size()
        unique_cnpj = set(cnpj_counts[cnpj_counts == 1].index)
        by_cnpj = {
            r["cnpj_key"]: r
            for r in est[est["cnpj_key"].isin(unique_cnpj)]
            .drop_duplicates("cnpj_key", keep="last")[["cnpj_key", *src_cols]]
            .to_dict(orient="records")
        }

        with self.engine.connect() as conn:
            fac = pd.read_sql(
                text(
                    """
                    SELECT id, cnes_code, cnes_unit_id, cnpj,
                           phone_number, fax_number, email, website_url,
                           legal_name, street_address, street_number,
                           address_complement, neighborhood, postal_code,
                           (location IS NOT NULL) AS has_location
                    FROM facilities
                    WHERE deactivated_at IS NULL
                    """
                ),
                conn,
            )

        rows = []
        for r in fac.itertuples(index=False):
            src = None
            if r.cnes_unit_id and r.cnes_unit_id in by_unit:
                src = by_unit[r.cnes_unit_id]
            else:
                ck = digits(r.cnes_code, 7)
                if ck and ck in by_cnes:
                    src = by_cnes[ck]
                else:
                    jk = digits(r.cnpj, 14)
                    if jk and jk in by_cnpj:
                        src = by_cnpj[jk]
            if not src:
                continue

            lat, lon = src.get("_lat"), src.get("_lon")
            geo_ok = valid_br_point(lat, lon) and not bool(r.has_location)

            def pick(cur, key):
                if cur is not None and not (isinstance(cur, float) and pd.isna(cur)) and str(cur).strip():
                    return None
                val = src.get(key)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return None
                return val

            patch = {
                "id": r.id,
                "phone_number": pick(r.phone_number, "_phone"),
                "fax_number": pick(r.fax_number, "_fax"),
                "email": pick(r.email, "_email"),
                "website_url": pick(r.website_url, "_web"),
                "cnpj": pick(r.cnpj, "_cnpj"),
                "legal_name": pick(r.legal_name, "_legal"),
                "street_address": pick(r.street_address, "_street"),
                "street_number": pick(r.street_number, "_num"),
                "address_complement": pick(r.address_complement, "_comp"),
                "neighborhood": pick(r.neighborhood, "_bairro"),
                "postal_code": pick(r.postal_code, "_cep"),
                "_lat": lat if geo_ok else None,
                "_lon": lon if geo_ok else None,
            }
            if any(patch[k] is not None for k in patch if k != "id"):
                rows.append(patch)

        report = {
            "candidates": len(rows),
            "phone_filled": 0,
            "email_filled": 0,
            "geo_filled": 0,
            "cnpj_filled": 0,
            "address_filled": 0,
        }
        if not rows:
            logger.info("Nothing to fill from CNES")
            return report

        tmp = pd.DataFrame(rows)
        with self.engine.begin() as conn:
            tmp.to_sql("_fill_cnes_tmp", conn, if_exists="replace", index=False)
            r = conn.execute(
                text(
                    """
                    UPDATE facilities f SET
                      phone_number = COALESCE(f.phone_number, NULLIF(t.phone_number, '')),
                      fax_number = COALESCE(f.fax_number, NULLIF(t.fax_number, '')),
                      email = COALESCE(f.email, NULLIF(t.email, '')),
                      website_url = COALESCE(f.website_url, NULLIF(t.website_url, '')),
                      cnpj = COALESCE(f.cnpj, NULLIF(t.cnpj, '')),
                      legal_name = COALESCE(f.legal_name, NULLIF(t.legal_name, '')),
                      street_address = COALESCE(f.street_address, NULLIF(t.street_address, '')),
                      street_number = COALESCE(f.street_number, NULLIF(t.street_number, '')),
                      address_complement = COALESCE(f.address_complement, NULLIF(t.address_complement, '')),
                      neighborhood = COALESCE(f.neighborhood, NULLIF(t.neighborhood, '')),
                      postal_code = COALESCE(f.postal_code, NULLIF(t.postal_code, '')),
                      updated_at = NOW()
                    FROM _fill_cnes_tmp t
                    WHERE f.id = t.id
                    """
                )
            )
            report["rows_updated"] = r.rowcount or 0
            geo = conn.execute(
                text(
                    """
                    UPDATE facilities f
                    SET location = ST_SetSRID(ST_MakePoint(t._lon::float8, t._lat::float8), 4326),
                        updated_at = NOW()
                    FROM _fill_cnes_tmp t
                    WHERE f.id = t.id
                      AND f.location IS NULL
                      AND t._lat IS NOT NULL AND t._lon IS NOT NULL
                    """
                )
            )
            report["geo_filled"] = geo.rowcount or 0
            conn.execute(text("DROP TABLE IF EXISTS _fill_cnes_tmp"))

        report["phone_filled"] = int(tmp["phone_number"].notna().sum())
        report["email_filled"] = int(tmp["email"].notna().sum())
        report["cnpj_filled"] = int(tmp["cnpj"].notna().sum())
        report["address_filled"] = int(tmp["street_address"].notna().sum())
        logger.info("CNES fill report: %s", report)
        return report

    def clean_non_cnes(self) -> dict[str, int]:
        """Clean excel-enrich + CRM_JSON facilities and excel-enrich professionals."""
        logger.info("=== CLEAN CRM + EXCEL ===")
        report: dict[str, int] = {}
        with self.engine.begin() as conn:
            fac = pd.read_sql(
                text(
                    """
                    SELECT id, name, legal_name, trade_name, state, city, neighborhood,
                           street_address, street_number, address_complement,
                           phone_number, fax_number, email, website_url,
                           cnpj, cpf, cnes_code, postal_code, responsible_name, source_provider
                    FROM facilities
                    WHERE source_provider IN ('CRM_JSON', 'excel-enrich')
                    """
                ),
                conn,
            )
        if fac.empty:
            return report

        cleaned = fac.copy()
        for col in [
            "name",
            "legal_name",
            "trade_name",
            "city",
            "neighborhood",
            "street_address",
            "street_number",
            "address_complement",
            "responsible_name",
        ]:
            cleaned[col] = cleaned[col].map(clean_person_name)
        cleaned["state"] = cleaned["state"].map(clean_uf)
        cleaned["phone_number"] = cleaned["phone_number"].map(first_phone)
        cleaned["fax_number"] = cleaned["fax_number"].map(first_phone)
        cleaned["email"] = cleaned["email"].map(clean_email)
        cleaned["website_url"] = cleaned["website_url"].map(clean_website)
        cleaned["cnpj"] = cleaned["cnpj"].map(lambda x: digits(x, 14))
        cleaned["cpf"] = cleaned["cpf"].map(lambda x: digits(x, 11))
        cleaned["cnes_code"] = cleaned["cnes_code"].map(lambda x: digits(x, 7))
        cleaned["postal_code"] = cleaned["postal_code"].map(lambda x: digits(x, 8))
        cleaned.loc[cleaned["cnpj"].notna(), "cpf"] = None

        with self.engine.begin() as conn:
            cleaned.drop(columns=["source_provider"]).to_sql(
                "_clean_fac2", conn, if_exists="replace", index=False
            )
            r = conn.execute(
                text(
                    """
                    UPDATE facilities f SET
                      name = t.name,
                      legal_name = t.legal_name,
                      trade_name = t.trade_name,
                      state = t.state,
                      city = t.city,
                      neighborhood = t.neighborhood,
                      street_address = t.street_address,
                      street_number = t.street_number,
                      address_complement = t.address_complement,
                      phone_number = t.phone_number,
                      fax_number = t.fax_number,
                      email = t.email,
                      website_url = t.website_url,
                      cnpj = t.cnpj,
                      cpf = t.cpf,
                      cnes_code = t.cnes_code,
                      postal_code = t.postal_code,
                      responsible_name = t.responsible_name,
                      updated_at = NOW()
                    FROM _clean_fac2 t
                    WHERE f.id = t.id
                    """
                )
            )
            report["facilities_cleaned"] = r.rowcount or 0
            conn.execute(text("DROP TABLE IF EXISTS _clean_fac2"))

            pros = pd.read_sql(
                text(
                    """
                    SELECT id, first_name, last_name, full_name, social_name,
                           crm_number, crm_state, primary_specialty_label, tax_id
                    FROM professionals
                    WHERE source_provider = 'excel-enrich'
                    """
                ),
                conn,
            )
        if len(pros):
            p2 = pros.copy()
            p2["full_name"] = p2["full_name"].map(clean_person_name)
            p2["social_name"] = p2["social_name"].map(clean_person_name)
            p2["primary_specialty_label"] = p2["primary_specialty_label"].map(clean_person_name)
            rebuilt = p2["full_name"].map(lambda n: split_name(n) if n else ("DESCONHECIDO", "DESCONHECIDO"))
            p2["first_name"] = rebuilt.map(lambda x: x[0])
            p2["last_name"] = rebuilt.map(lambda x: x[1])
            p2["crm_number"] = p2["crm_number"].map(clean_crm_number)
            p2["crm_state"] = p2["crm_state"].map(clean_uf)
            # drop masked tax ids
            p2["tax_id"] = p2["tax_id"].map(
                lambda x: None
                if x is None or (isinstance(x, str) and ("*" in x or "X" in x.upper()))
                else digits(x, 11)
            )
            with self.engine.begin() as conn:
                p2.to_sql("_clean_pro2", conn, if_exists="replace", index=False)
                r = conn.execute(
                    text(
                        """
                        UPDATE professionals p SET
                          first_name = t.first_name,
                          last_name = t.last_name,
                          full_name = t.full_name,
                          social_name = t.social_name,
                          crm_number = t.crm_number,
                          crm_state = t.crm_state,
                          primary_specialty_label = t.primary_specialty_label,
                          tax_id = t.tax_id,
                          updated_at = NOW()
                        FROM _clean_pro2 t
                        WHERE p.id = t.id
                        """
                    )
                )
                report["professionals_cleaned"] = r.rowcount or 0
                conn.execute(text("DROP TABLE IF EXISTS _clean_pro2"))

        logger.info("Clean report: %s", report)
        return report

    def audit(self) -> dict[str, Any]:
        logger.info("=== AUDIT ===")
        q = text(
            """
            WITH fac AS (
              SELECT source_provider,
                     count(*) AS n,
                     count(*) FILTER (WHERE cnes_code IS NOT NULL) AS cnes_code,
                     count(*) FILTER (WHERE cnpj IS NOT NULL AND length(regexp_replace(cnpj,'\\D','','g'))=14) AS cnpj_ok,
                     count(*) FILTER (WHERE phone_number IS NOT NULL AND length(regexp_replace(coalesce(phone_number,''),'\\D','','g')) BETWEEN 10 AND 11) AS phone_ok,
                     count(*) FILTER (WHERE email IS NOT NULL AND position('@' in email)>1) AS email_ok,
                     count(*) FILTER (WHERE website_url IS NOT NULL) AS website,
                     count(*) FILTER (WHERE postal_code IS NOT NULL AND length(regexp_replace(postal_code,'\\D','','g'))=8) AS cep_ok,
                     count(*) FILTER (WHERE street_address IS NOT NULL) AS street,
                     count(*) FILTER (WHERE city IS NOT NULL) AS city,
                     count(*) FILTER (WHERE state IS NOT NULL) AS state,
                     count(*) FILTER (WHERE responsible_name IS NOT NULL AND btrim(responsible_name)<>'') AS responsible,
                     count(*) FILTER (WHERE location IS NOT NULL) AS geo,
                     count(*) FILTER (WHERE unit_type IS NOT NULL OR unit_type_code IS NOT NULL) AS unit_type,
                     count(*) FILTER (WHERE facility_type_code IS NOT NULL) AS facility_type
              FROM facilities
              GROUP BY 1
            )
            SELECT * FROM fac ORDER BY n DESC
            """
        )
        with self.engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(q)]
            counts = {
                r[0]: int(r[1])
                for r in conn.execute(
                    text(
                        """
                        SELECT 'facilities', count(*) FROM facilities
                        UNION ALL SELECT 'fvp_ortho', count(*) FROM facility_vertical_profiles fvp
                          JOIN business_verticals bv ON bv.id=fvp.vertical_id WHERE bv.code='ORTOPEDIA'
                        UNION ALL SELECT 'fvp_derm', count(*) FROM facility_vertical_profiles fvp
                          JOIN business_verticals bv ON bv.id=fvp.vertical_id WHERE bv.code='DERMATOLOGIA'
                        UNION ALL SELECT 'facility_professionals', count(*) FROM facility_professionals
                        UNION ALL SELECT 'fp_legacy', count(*) FROM facility_professionals WHERE occupation_code='LEGACY'
                        UNION ALL SELECT 'fp_ortho_cbo', count(*) FROM facility_professionals WHERE occupation_code='225270'
                        UNION ALL SELECT 'facility_services', count(*) FROM facility_services
                        UNION ALL SELECT 'facility_representatives', count(*) FROM facility_representatives
                        UNION ALL SELECT 'orders', count(*) FROM orders
                        UNION ALL SELECT 'pros_excel', count(*) FROM professionals WHERE source_provider='excel-enrich'
                        UNION ALL SELECT 'pros_cnes', count(*) FROM professionals WHERE source_provider='cnes'
                        UNION ALL SELECT 'pros_crm', count(*) FROM professionals WHERE source_provider='CRM_JSON'
                        UNION ALL SELECT 'bad_phones', count(*) FROM facilities
                          WHERE phone_number IS NOT NULL
                            AND length(regexp_replace(phone_number,'\\D','','g')) NOT BETWEEN 10 AND 11
                        UNION ALL SELECT 'masked_cpf', count(*) FROM professionals
                          WHERE tax_id IS NOT NULL AND tax_id ~ '[*Xx]'
                        """
                    )
                )
            }
        out = {"fill_by_source": rows, "counts": counts}
        path = Path(__file__).resolve().parent.parent / "output" / "atlasmed3_fill_audit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        logger.info("Audit written: %s", path)
        logger.info("Counts: %s", counts)
        for row in rows:
            logger.info("Fill %s: %s", row["source_provider"], {k: row[k] for k in row if k != "source_provider"})
        return out

    def run(self) -> None:
        self.fix_legacy_occupation()
        self.fill_from_cnes()
        self.clean_non_cnes()
        # re-clean cnes via derm helpers already done; normalize phones that fill introduced
        self.clean_all_phones_emails()
        self.audit()

    def clean_all_phones_emails(self) -> None:
        """Final pass: normalize phones/emails on every facility."""
        with self.engine.begin() as conn:
            fac = pd.read_sql(
                text("SELECT id, phone_number, fax_number, email, website_url FROM facilities"),
                conn,
            )
        fac["phone_number"] = fac["phone_number"].map(first_phone)
        fac["fax_number"] = fac["fax_number"].map(first_phone)
        fac["email"] = fac["email"].map(clean_email)
        fac["website_url"] = fac["website_url"].map(clean_website)
        with self.engine.begin() as conn:
            fac.to_sql("_clean_contact", conn, if_exists="replace", index=False)
            conn.execute(
                text(
                    """
                    UPDATE facilities f SET
                      phone_number = t.phone_number,
                      fax_number = t.fax_number,
                      email = t.email,
                      website_url = t.website_url,
                      updated_at = NOW()
                    FROM _clean_contact t
                    WHERE f.id = t.id
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _clean_contact"))
        logger.info("Global phone/email/website normalize done")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db-url", default=DEFAULT_DB)
    p.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV)
    p.add_argument("--cnes-version", default="202605")
    p.add_argument("--audit-only", action="store_true")
    args = p.parse_args()
    filler = Filler(args.csv_dir, args.db_url, args.cnes_version)
    if args.audit_only:
        filler.audit()
    else:
        filler.run()


if __name__ == "__main__":
    main()
