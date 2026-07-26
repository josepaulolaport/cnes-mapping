#!/usr/bin/env python3
"""
Enrichment from commercial Excel extracts under ./excels.

- Facilities: match by CNES / CNPJ / CPF. If keyed in the cadastro sheet but missing
  in DB, create the facility (name, tax id, address, phone from the sheet).
  Rows with no CNES/CNPJ/CPF are skipped (cannot key safely).
- Professionals: match by CRM digits (+ UF when ambiguous). If unmatched but CRM is
  present, create the professional and link to the resolved facility.
- Doctor→clinic: tax ids on the doctor row, else same-file establishment name →
  cadastro row (so RJ books that only list the clinic name still resolve via CNPJ).
- Associations: insert missing active facility_professionals links.
- Reps: upsert REP users from filename / CONSULTOR; assign clinics via
  facility_consultant_assignments (reassign default on).
- Potencial / resumo sheets: ignored. Infiltrações clinic/doctor sheets are used.

Usage (from repo root, with DATABASE_URL set — e.g. via apps/api/.env):

  # dry-run (default)
  python apps/api/src/scripts/enrich-from-excels.py

  # apply
  python apps/api/src/scripts/enrich-from-excels.py --apply

  EXCEL_DIR=./excels EXCEL_ENRICH_PASSWORD='...' python ... --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from openpyxl import load_workbook
except ImportError:
    print("Missing openpyxl. Install: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg
except ImportError:
    print("Missing psycopg. Install: pip install 'psycopg[binary]'", file=sys.stderr)
    sys.exit(1)

try:
    from argon2 import PasswordHasher
except ImportError:
    PasswordHasher = None  # type: ignore


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_EXCEL_DIR = ROOT / "excels"
NOTE_TAG = "excel-enrich-20260723"
SOURCE_PROVIDER = "excel-enrich"

# Filename → default consultant display name (RJ territory books).
FILE_DEFAULT_CONSULTANT: dict[str, str | None] = {
    "Adriana_Centro_Zona Sul_Nov_2025 - Copia (1).xlsx": "Adriana",
    "Laudo_Zona Oeste_Tijuca_Vila Isabel_Nov_2025 - Copia.xlsx": "Laudo",
    "Luis Stelet_Litoral_Baixada_Zona Norte_Abr_2026 - Copia.xlsx": "Luis Stelet",
    "Raquel_Norte Fluminense_Região dos Lagos_30_01_2025 - Copia.xlsx": "Raquel",
    "Base de clientes_AC_AM_AP_MA_PA_RO_RR_Set_2024_CRM.xlsx": None,  # per-row CONSULTOR
    "Infiltrações_2022_Espirito Santo_Out_2023.xlsx": None,  # no consultant column
}


def digits(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def norm_header(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", ".", text.strip().lower())
    return text.strip(".") or "rep"


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def split_name(full: str) -> tuple[str, str]:
    parts = [p for p in full.strip().split() if p]
    if not parts:
        return ("Rep", "Excel")
    if len(parts) == 1:
        return (parts[0], "Rep")
    return (parts[0], " ".join(parts[1:]))


def parse_crm_candidates(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    chunks = re.split(r"[/,;|]", text)
    out: list[str] = []
    for chunk in chunks:
        d = digits(chunk)
        if d:
            out.append(d.lstrip("0") or "0")
    # also whole-string digits if nothing split
    if not out:
        d = digits(text)
        if d:
            out.append(d.lstrip("0") or "0")
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def tax_from_cell(raw: Any) -> tuple[str | None, str | None]:
    """Return (cnpj14 | None, cpf11 | None)."""
    if raw is None:
        return (None, None)
    if isinstance(raw, float):
        if raw.is_integer():
            raw = int(raw)
        else:
            return (None, None)
    if isinstance(raw, int):
        d = str(raw)
        if len(d) <= 11:
            return (None, d.zfill(11))
        if len(d) <= 14:
            return (d.zfill(14), None)
        return (d[-14:], None)
    text = str(raw).strip().upper()
    if not text or text in {"PESSOA FISICA", "PF", "N/A", "-"}:
        return (None, None)
    d = digits(text)
    if len(d) == 14:
        return (d, None)
    if len(d) == 11:
        return (None, d)
    if 11 < len(d) < 14:
        # Excel often drops CNPJ leading zeros when stored as number/text.
        return (d.zfill(14), None)
    if len(d) > 14:
        return (d[-14:], None)
    return (None, None)


@dataclass
class FacilityRow:
    source_file: str
    consultant: str | None
    cnes: str | None
    cnpj: str | None
    cpf: str | None
    trade_name: str
    legal_name: str
    uf: str
    city: str
    neighborhood: str = ""
    street: str = ""
    street_number: str = ""
    complement: str = ""
    postal_code: str = ""
    phone: str = ""
    unit_type: str = ""

    def has_key(self) -> bool:
        return bool(self.cnes or self.cnpj or self.cpf)


@dataclass
class DoctorRow:
    source_file: str
    establishment: str
    doctor_name: str
    crm_candidates: list[str]
    uf: str
    city: str
    cnes: str | None
    cnpj: str | None
    specialty: str = ""


@dataclass
class ParsedBook:
    file: str
    default_consultant: str | None
    facilities: list[FacilityRow] = field(default_factory=list)
    doctors: list[DoctorRow] = field(default_factory=list)


def header_map(row: tuple[Any, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, cell in enumerate(row):
        key = norm_header(cell)
        if key and key not in mapping:
            mapping[key] = i
    return mapping


def cell(row: tuple[Any, ...], hmap: dict[str, int], *keys: str) -> Any:
    for key in keys:
        idx = hmap.get(key)
        if idx is not None and idx < len(row):
            return row[idx]
    return None


def is_facility_sheet(hmap: dict[str, int]) -> bool:
    has_est = "ESTABELECIMENTO" in hmap
    has_tax = any(k in hmap for k in ("CNPJ", "CNPJ / CPF", "CNPJ CPF"))
    has_doc = any(k in hmap for k in ("MEDICO", "NOME MEDICO"))
    return has_est and has_tax and not has_doc


def is_doctor_sheet(hmap: dict[str, int]) -> bool:
    has_doc = any(k in hmap for k in ("MEDICO", "NOME MEDICO"))
    has_crm = any(k in hmap for k in ("CRM", "REGISTRO(S)", "REGISTRO(S)", "REGISTROS"))
    # openpyxl may normalize Registro(s)
    has_crm = has_crm or any(k.startswith("REGISTRO") for k in hmap)
    return has_doc and has_crm


def parse_workbook(path: Path) -> ParsedBook:
    default = FILE_DEFAULT_CONSULTANT.get(path.name)
    book = ParsedBook(file=path.name, default_consultant=default)
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet_name in wb.sheetnames:
            upper = sheet_name.upper()
            if any(x in upper for x in ("POTENCIAL", "RESUMO", "INFILT", "REGI")) and "ORTOPED" not in upper and "CLINIC" not in upper and "CADASTRO" not in upper and "BASE_" not in upper and "ES_" not in upper:
                # keep REGIÕES ES city map out; skip potencial/resumo
                if "REGI" in upper and "ORTOPED" not in upper and "CLINIC" not in upper:
                    continue
                if "POTENCIAL" in upper or "RESUMO" in upper:
                    continue
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            hmap = header_map(rows[0])
            if not hmap:
                continue

            if is_facility_sheet(hmap):
                for row in rows[1:]:
                    if not any(row):
                        continue
                    trade = str(cell(row, hmap, "ESTABELECIMENTO") or "").strip()
                    if not trade:
                        continue
                    cnpj, cpf = tax_from_cell(cell(row, hmap, "CNPJ", "CNPJ / CPF", "CNPJ CPF"))
                    cnes_raw = cell(row, hmap, "CNES")
                    cnes = digits(cnes_raw).zfill(7) if digits(cnes_raw) else None
                    if cnes == "0000000":
                        cnes = None
                    consultant = default
                    cons_cell = cell(row, hmap, "CONSULTOR DE NEGOCIOS", "CONSULTOR")
                    if cons_cell and str(cons_cell).strip():
                        consultant = str(cons_cell).strip()
                    book.facilities.append(
                        FacilityRow(
                            source_file=path.name,
                            consultant=consultant,
                            cnes=cnes,
                            cnpj=cnpj,
                            cpf=cpf,
                            trade_name=trade,
                            legal_name=str(cell(row, hmap, "RAZAO SOCIAL") or "").strip(),
                            uf=str(cell(row, hmap, "UF") or "").strip().upper()[:2],
                            city=str(cell(row, hmap, "CIDADE") or "").strip(),
                            neighborhood=str(cell(row, hmap, "BAIRRO") or "").strip(),
                            street=str(cell(row, hmap, "RUA") or "").strip(),
                            street_number=str(cell(row, hmap, "NR", "NUMERO", "NÚMERO") or "").strip(),
                            complement=str(cell(row, hmap, "COMPLEMENTO") or "").strip(),
                            postal_code=digits(cell(row, hmap, "CEP"))[:8] or "",
                            phone=str(cell(row, hmap, "TELEFONE") or "").strip(),
                            unit_type=str(
                                cell(row, hmap, "TIPO", "TIPO DE UNIDADE") or ""
                            ).strip(),
                        )
                    )
                continue

            if is_doctor_sheet(hmap):
                last_est = ""
                last_cnes = None
                last_cnpj = None
                last_city = ""
                last_uf = ""
                for row in rows[1:]:
                    if not any(row):
                        continue
                    doctor = str(cell(row, hmap, "MEDICO", "NOME MEDICO") or "").strip()
                    if not doctor:
                        continue
                    est = str(cell(row, hmap, "ESTABELECIMENTO") or "").strip()
                    if est:
                        last_est = est
                    else:
                        est = last_est
                    cnes_raw = cell(row, hmap, "CNES")
                    if cnes_raw and digits(cnes_raw):
                        last_cnes = digits(cnes_raw).zfill(7)
                    cnpj, _cpf = tax_from_cell(cell(row, hmap, "CNPJ", "CNPJ / CPF", "CNPJ CPF"))
                    if cnpj:
                        last_cnpj = cnpj
                    uf = str(cell(row, hmap, "UF") or "").strip().upper()[:2]
                    city = str(cell(row, hmap, "CIDADE") or "").strip()
                    # ES sheet: "Cidade - UF"
                    cidade_uf = cell(row, hmap, "CIDADE - UF")
                    if cidade_uf and str(cidade_uf).strip():
                        parts = str(cidade_uf).rsplit("-", 1)
                        if len(parts) == 2:
                            city = parts[0].strip() or city
                            uf = parts[1].strip().upper()[:2] or uf
                        last_city = city
                        last_uf = uf
                    if uf:
                        last_uf = uf
                    else:
                        uf = last_uf
                    if city:
                        last_city = city
                    else:
                        city = last_city
                    crm_raw = cell(row, hmap, "CRM")
                    if crm_raw is None:
                        for k, idx in hmap.items():
                            if k.startswith("REGISTRO"):
                                crm_raw = row[idx] if idx < len(row) else None
                                break
                    specialty = str(cell(row, hmap, "ESPECIALIDADE") or "").strip()
                    book.doctors.append(
                        DoctorRow(
                            source_file=path.name,
                            establishment=est,
                            doctor_name=doctor,
                            crm_candidates=parse_crm_candidates(crm_raw),
                            uf=uf,
                            city=city,
                            cnes=last_cnes,
                            cnpj=last_cnpj,
                            specialty=specialty,
                        )
                    )
    finally:
        wb.close()
    return book


def load_db_indexes(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, nullif(trim(cnes_code),''), nullif(trim(cnpj),''), nullif(trim(cpf),'')
            from facilities
            where deactivated_at is null
            order by case source_provider
              when 'CRM_JSON' then 0
              when 'excel-enrich' then 1
              else 2
            end, updated_at desc nulls last
            """
        )
        by_cnes: dict[str, str] = {}
        by_cnpj: dict[str, str] = {}
        by_cpf: dict[str, str] = {}
        for fid, cnes, cnpj, cpf in cur.fetchall():
            # Prefer CRM_JSON / excel-enrich over later CNES inserts (first wins)
            if cnes:
                by_cnes.setdefault(digits(cnes).zfill(7), fid)
            if cnpj:
                by_cnpj.setdefault(digits(cnpj), fid)
            if cpf:
                by_cpf.setdefault(digits(cpf), fid)

        cur.execute("select id from business_verticals where code = 'ORTOPEDIA' limit 1")
        ortho = cur.fetchone()
        if not ortho:
            raise RuntimeError("ORTOPEDIA vertical not found")
        ortho_vertical_id = ortho[0]

        cur.execute(
            """
            select id, nullif(trim(crm_number),''), upper(nullif(trim(crm_state),''))
            from professionals
            where deleted_at is null
            """
        )
        by_crm: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for pid, crm, state in cur.fetchall():
            if not crm:
                continue
            key = digits(crm).lstrip("0") or "0"
            by_crm[key].append((pid, state))

        cur.execute(
            """
            select facility_id, professional_id
            from facility_professionals
            where ended_at is null
            """
        )
        associations = {(r[0], r[1]) for r in cur.fetchall()}

        cur.execute(
            """
            select facility_id, user_id
            from facility_consultant_assignments
            where ended_at is null
            """
        )
        consultants = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("select id from roles where name = 'REP' limit 1")
        rep_role = cur.fetchone()
        if not rep_role:
            raise RuntimeError("REP role not found")

        cur.execute(
            """
            select u.id from users u
            join roles r on r.id = u.role_id
            where r.name = 'ADMIN' and u.deleted_at is null
            order by u.created_at
            limit 1
            """
        )
        admin = cur.fetchone()
        if not admin:
            raise RuntimeError("ADMIN user not found (needed as assigned_by)")

        cur.execute(
            """
            select id, lower(email), lower(username), first_name, last_name
            from users
            where deleted_at is null
            """
        )
        users_by_email = {}
        users_by_username = {}
        for uid, email, username, first, last in cur.fetchall():
            users_by_email[email] = uid
            users_by_username[username] = uid

    return {
        "by_cnes": by_cnes,
        "by_cnpj": by_cnpj,
        "by_cpf": by_cpf,
        "by_crm": by_crm,
        "associations": associations,
        "consultants": consultants,
        "rep_role_id": rep_role[0],
        "admin_id": admin[0],
        "users_by_email": users_by_email,
        "users_by_username": users_by_username,
        "ortho_vertical_id": ortho_vertical_id,
    }


def match_facility(row: FacilityRow | DoctorRow, idx: dict[str, Any]) -> str | None:
    cnes = getattr(row, "cnes", None)
    if cnes and cnes in idx["by_cnes"]:
        return idx["by_cnes"][cnes]
    cnpj = getattr(row, "cnpj", None)
    if cnpj and cnpj in idx["by_cnpj"]:
        return idx["by_cnpj"][cnpj]
    cpf = getattr(row, "cpf", None) if isinstance(row, FacilityRow) else None
    if cpf and cpf in idx["by_cpf"]:
        return idx["by_cpf"][cpf]
    return None


def match_professional(row: DoctorRow, idx: dict[str, Any]) -> str | None:
    for crm in row.crm_candidates:
        hits = idx["by_crm"].get(crm, [])
        if not hits:
            continue
        if len(hits) == 1:
            return hits[0][0]
        if row.uf:
            state_hits = [h for h in hits if h[1] == row.uf]
            if len(state_hits) == 1:
                return state_hits[0][0]
            if len(state_hits) > 1:
                return None  # ambiguous
        # ambiguous across states
        return None
    return None


def resolve_doctor_facility(
    doc: DoctorRow,
    book_file: str,
    idx: dict[str, Any],
    facility_id_by_name: dict[tuple[str, str], str],
    facility_row_by_name: dict[tuple[str, str], FacilityRow],
) -> tuple[str | None, FacilityRow | None]:
    """Return (facility_id, facility_row_for_create)."""
    fid = match_facility(doc, idx)
    if fid:
        return fid, None
    name_key = norm_name(doc.establishment)
    if name_key:
        fid = facility_id_by_name.get((book_file, name_key))
        if fid:
            return fid, None
        fac_row = facility_row_by_name.get((book_file, name_key))
        if fac_row:
            fid = match_facility(fac_row, idx)
            if fid:
                return fid, None
            if fac_row.has_key():
                return None, fac_row
    return None, None


def ensure_facility(
    conn: psycopg.Connection,
    idx: dict[str, Any],
    fac: FacilityRow,
    apply: bool,
) -> str:
    existing = match_facility(fac, idx)
    if existing:
        return existing

    if fac.cnpj:
        external_id = f"cnpj:{fac.cnpj}"
    elif fac.cnes:
        external_id = f"cnes:{fac.cnes}"
    elif fac.cpf:
        external_id = f"cpf:{fac.cpf}"
    else:
        raise ValueError(f"facility without key: {fac.trade_name}")

    if not apply:
        fake = f"dryrun:fac:{external_id}"
        if fac.cnes:
            idx["by_cnes"][fac.cnes] = fake
        if fac.cnpj:
            idx["by_cnpj"][fac.cnpj] = fake
        if fac.cpf:
            idx["by_cpf"][fac.cpf] = fake
        return fake

    tax_id_type = "PF" if fac.cpf and not fac.cnpj else "PJ"
    facility_id = str(uuid4()).replace("-", "")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into facilities (
              id, name, legal_name, trade_name,
              cnes_code, tax_id_type, cnpj, cpf,
              country, state, city, neighborhood,
              street_address, street_number, address_complement, postal_code,
              phone_number, unit_type,
              source_provider, external_source_id, source_present, source_tracked,
              conformity_status
            ) values (
              %s, %s, %s, %s,
              %s, %s, %s, %s,
              'BR', %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s,
              %s, %s, true, true,
              'INCOMPLETE'
            )
            on conflict (source_provider, external_source_id) do update
              set updated_at = now()
            returning id
            """,
            (
                facility_id,
                fac.trade_name,
                fac.legal_name or None,
                fac.trade_name,
                fac.cnes,
                tax_id_type,
                fac.cnpj,
                fac.cpf,
                fac.uf or None,
                fac.city or None,
                fac.neighborhood or None,
                fac.street or None,
                fac.street_number or None,
                fac.complement or None,
                fac.postal_code or None,
                fac.phone or None,
                fac.unit_type or None,
                SOURCE_PROVIDER,
                external_id,
            ),
        )
        fid = cur.fetchone()[0]
        # atlasmed-3: commercial status lives on vertical profiles
        cur.execute(
            """
            insert into facility_vertical_profiles (
              id, facility_id, vertical_id, is_active,
              commercial_status, purchase_status, created_at, updated_at
            ) values (
              %s, %s, %s, true,
              'INACTIVE', 'NON_BUYER', now(), now()
            )
            on conflict (facility_id, vertical_id) do nothing
            """,
            (str(uuid4()).replace("-", ""), fid, idx["ortho_vertical_id"]),
        )
    if fac.cnes:
        idx["by_cnes"][fac.cnes] = fid
    if fac.cnpj:
        idx["by_cnpj"][fac.cnpj] = fid
    if fac.cpf:
        idx["by_cpf"][fac.cpf] = fid
    return fid


def ensure_professional(
    conn: psycopg.Connection,
    idx: dict[str, Any],
    doc: DoctorRow,
    apply: bool,
) -> str | None:
    existing = match_professional(doc, idx)
    if existing:
        return existing
    if not doc.crm_candidates:
        return None
    # Ambiguous CRM in DB → do not create a duplicate
    for crm in doc.crm_candidates:
        hits = idx["by_crm"].get(crm, [])
        if hits:
            return None

    crm = doc.crm_candidates[0]
    first, last = split_name(doc.doctor_name)
    external_id = f"crm:{(doc.uf or 'XX')}:{crm}"

    if not apply:
        fake = f"dryrun:doc:{external_id}"
        idx["by_crm"][crm].append((fake, doc.uf or None))
        return fake

    professional_id = str(uuid4()).replace("-", "")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into professionals (
              id, first_name, last_name, full_name,
              crm_council, crm_number, crm_state,
              primary_specialty_label,
              source_provider, external_source_id, source_present, source_tracked,
              notes
            ) values (
              %s, %s, %s, %s,
              'CRM', %s, %s,
              %s,
              %s, %s, true, true,
              %s
            )
            on conflict (source_provider, external_source_id) do update
              set updated_at = now()
            returning id
            """,
            (
                professional_id,
                first,
                last,
                doc.doctor_name.strip(),
                crm,
                doc.uf or None,
                doc.specialty or None,
                SOURCE_PROVIDER,
                external_id,
                f"{NOTE_TAG}:{doc.source_file}",
            ),
        )
        pid = cur.fetchone()[0]
    idx["by_crm"][crm].append((pid, doc.uf or None))
    return pid


def ensure_rep_user(
    conn: psycopg.Connection,
    idx: dict[str, Any],
    display_name: str,
    password: str,
    apply: bool,
) -> str:
    first, last = split_name(display_name)
    slug = slugify(display_name)
    email = f"{slug}@atlasmed.com.br"
    username = slug
    existing = idx["users_by_email"].get(email) or idx["users_by_username"].get(username)
    if existing:
        return existing

    if not apply:
        # synthetic id for dry-run accounting
        fake = f"dryrun:{username}"
        idx["users_by_email"][email] = fake
        idx["users_by_username"][username] = fake
        return fake

    if PasswordHasher is None:
        raise RuntimeError("argon2-cffi required for --apply (pip install argon2-cffi)")

    user_id = str(uuid4()).replace("-", "")
    password_hash = PasswordHasher().hash(password)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into users (
              id, email, username, password_hash, first_name, last_name,
              status, email_verified, role_id, metadata
            ) values (
              %s, %s, %s, %s, %s, %s,
              'ACTIVE', true, %s, %s::jsonb
            )
            on conflict (email) do update set updated_at = now()
            returning id
            """,
            (
                user_id,
                email,
                username,
                password_hash,
                first,
                last,
                idx["rep_role_id"],
                psycopg.types.json.Json({"source": NOTE_TAG, "displayName": display_name}),
            ),
        )
        uid = cur.fetchone()[0]
    idx["users_by_email"][email] = uid
    idx["users_by_username"][username] = uid
    return uid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument(
        "--reassign-consultants",
        action="store_true",
        default=True,
        help="End existing consultant assignments on excel-matched clinics and assign the sheet rep (default: on)",
    )
    parser.add_argument(
        "--no-reassign-consultants",
        action="store_false",
        dest="reassign_consultants",
        help="Only assign clinics that have no active consultant",
    )
    parser.add_argument(
        "--excel-dir",
        default=os.environ.get("EXCEL_DIR", str(DEFAULT_EXCEL_DIR)),
        help="Directory with .xlsx files",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("EXCEL_ENRICH_PASSWORD", "Atlasmed@2026"),
        help="Password for newly created REP users",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1

    excel_dir = Path(args.excel_dir)
    if not excel_dir.is_dir():
        print(f"Excel dir not found: {excel_dir}", file=sys.stderr)
        return 1

    paths = sorted(excel_dir.glob("*.xlsx"))
    if not paths:
        print(f"No .xlsx files in {excel_dir}", file=sys.stderr)
        return 1

    books = [parse_workbook(p) for p in paths]
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== enrich-from-excels [{mode}] ===")
    print(f"files: {len(books)}")

    stats = defaultdict(int)
    new_associations: list[tuple[str, str, str]] = []  # facility, professional, source
    consultant_targets: dict[str, set[str]] = defaultdict(set)  # consultant name -> facility ids
    unmatched_facilities: list[str] = []
    unmatched_doctors: list[str] = []

    with psycopg.connect(database_url) as conn:
        idx = load_db_indexes(conn)
        print(
            f"db indexes: cnes={len(idx['by_cnes'])} cnpj={len(idx['by_cnpj'])} "
            f"cpf={len(idx['by_cpf'])} crm_keys={len(idx['by_crm'])} "
            f"assoc={len(idx['associations'])} active_consultants={len(idx['consultants'])}"
        )

        # Facilities: match or create (keyed cadastro rows), index names for doctor joins
        facility_id_by_name: dict[tuple[str, str], str] = {}
        facility_row_by_name: dict[tuple[str, str], FacilityRow] = {}
        for book in books:
            for fac in book.facilities:
                stats["facility_rows"] += 1
                name_key = norm_name(fac.trade_name)
                if name_key:
                    facility_row_by_name[(book.file, name_key)] = fac
                if fac.legal_name:
                    legal_key = norm_name(fac.legal_name)
                    if legal_key:
                        facility_row_by_name[(book.file, legal_key)] = fac

                fid = match_facility(fac, idx)
                if fid:
                    stats["facility_matched"] += 1
                elif fac.has_key():
                    fid = ensure_facility(conn, idx, fac, apply=args.apply)
                    stats["facility_created" if args.apply else "facility_would_create"] += 1
                else:
                    stats["facility_skipped_no_key"] += 1
                    if len(unmatched_facilities) < 15:
                        unmatched_facilities.append(
                            f"{fac.trade_name} (no CNPJ/CNES/CPF) ({fac.source_file})"
                        )
                    continue

                if name_key:
                    facility_id_by_name[(book.file, name_key)] = fid
                if fac.legal_name:
                    legal_key = norm_name(fac.legal_name)
                    if legal_key:
                        facility_id_by_name[(book.file, legal_key)] = fid
                if fac.consultant:
                    consultant_targets[fac.consultant].add(fid)

        # Doctors: match or create, resolve clinic via tax or same-file cadastro name
        for book in books:
            for doc in book.doctors:
                stats["doctor_rows"] += 1
                prior = match_professional(doc, idx)
                pid = ensure_professional(conn, idx, doc, apply=args.apply)
                if not pid:
                    stats["doctor_unmatched"] += 1
                    if len(unmatched_doctors) < 15:
                        unmatched_doctors.append(
                            f"{doc.doctor_name} crm={doc.crm_candidates} uf={doc.uf}"
                        )
                    continue
                if prior is None:
                    stats["doctor_created" if args.apply else "doctor_would_create"] += 1
                elif str(prior).startswith("dryrun:"):
                    stats["doctor_reuse_created"] += 1
                else:
                    stats["doctor_matched"] += 1

                fid, fac_for_create = resolve_doctor_facility(
                    doc, book.file, idx, facility_id_by_name, facility_row_by_name
                )
                if not fid and fac_for_create is not None:
                    fid = ensure_facility(conn, idx, fac_for_create, apply=args.apply)
                    stats["facility_created" if args.apply else "facility_would_create"] += 1
                    name_key = norm_name(fac_for_create.trade_name)
                    if name_key:
                        facility_id_by_name[(book.file, name_key)] = fid
                    if fac_for_create.consultant:
                        consultant_targets[fac_for_create.consultant].add(fid)

                if not fid:
                    stats["assoc_skipped_no_facility"] += 1
                    continue

                key = (fid, pid)
                if key in idx["associations"]:
                    stats["assoc_already"] += 1
                    continue
                stats["assoc_to_create"] += 1
                new_associations.append((fid, pid, book.file))
                idx["associations"].add(key)

        # Ensure REP users + consultant assignments (skip if clinic already has a consultant)
        assignments_to_create: list[tuple[str, str, str]] = []
        for consultant_name in sorted(consultant_targets.keys()):
            email = f"{slugify(consultant_name)}@atlasmed.com.br"
            already = (
                email in idx["users_by_email"]
                or slugify(consultant_name) in idx["users_by_username"]
            )
            uid = ensure_rep_user(
                conn, idx, consultant_name, args.password, apply=args.apply
            )
            if not already:
                stats["rep_users_created" if args.apply else "rep_users_would_create"] += 1
            else:
                stats["rep_users_existing"] += 1

            for fid in consultant_targets[consultant_name]:
                current = idx["consultants"].get(fid)
                if current == uid:
                    stats["consultant_already"] += 1
                    continue
                if current and current != uid and not args.reassign_consultants:
                    stats["consultant_skipped_other_owner"] += 1
                    continue
                if current and current != uid and args.reassign_consultants:
                    stats["consultant_reassign"] += 1
                else:
                    stats["consultant_to_assign"] += 1
                assignments_to_create.append((fid, uid, consultant_name))
                idx["consultants"][fid] = uid

        if args.apply:
            with conn.cursor() as cur:
                for fid, pid, source in new_associations:
                    cur.execute(
                        """
                        insert into facility_professionals (
                          id, professional_id, facility_id, occupation_code,
                          source_active, notes, confirmed_at
                        ) values (
                          %s, %s, %s, 'LEGACY',
                          true, %s, null
                        )
                        on conflict (facility_id, professional_id, occupation_code) do nothing
                        """,
                        (
                            str(uuid4()).replace("-", ""),
                            pid,
                            fid,
                            f"{NOTE_TAG}:{source}",
                        ),
                    )
                    stats["assoc_created"] += 1

                for fid, uid, _consultant_name in assignments_to_create:
                    if str(uid).startswith("dryrun:"):
                        continue
                    # Ensure ORTOPEDIA profile exists (matched CNES/CRM clinics too)
                    cur.execute(
                        """
                        insert into facility_vertical_profiles (
                          id, facility_id, vertical_id, is_active,
                          commercial_status, purchase_status, created_at, updated_at
                        ) values (
                          %s, %s, %s, true,
                          'INACTIVE', 'NON_BUYER', now(), now()
                        )
                        on conflict (facility_id, vertical_id) do nothing
                        """,
                        (
                            str(uuid4()).replace("-", ""),
                            fid,
                            idx["ortho_vertical_id"],
                        ),
                    )
                    cur.execute(
                        """
                        update facility_consultant_assignments
                        set ended_at = now(), end_reason = %s, updated_at = now()
                        where facility_id = %s and vertical_id = %s and ended_at is null
                        """,
                        (f"reassigned:{NOTE_TAG}", fid, idx["ortho_vertical_id"]),
                    )
                    cur.execute(
                        """
                        insert into facility_consultant_assignments (
                          id, facility_id, user_id, assigned_by_user_id, vertical_id
                        ) values (%s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid4()).replace("-", ""),
                            fid,
                            uid,
                            idx["admin_id"],
                            idx["ortho_vertical_id"],
                        ),
                    )
                    stats["consultant_assigned"] += 1
            conn.commit()
            print(f"\nREP users password (shared for newly created): {args.password}")
            print("Login: email <name>@atlasmed.com.br  username <name>")

    print("\n--- stats ---")
    for key in sorted(stats.keys()):
        print(f"  {key}: {stats[key]}")

    if unmatched_facilities:
        print("\n--- sample unmatched facilities ---")
        for line in unmatched_facilities:
            print(f"  - {line}")
    if unmatched_doctors:
        print("\n--- sample unmatched doctors ---")
        for line in unmatched_doctors:
            print(f"  - {line}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    # Ignore openpyxl header/footer warnings
    import warnings

    warnings.filterwarnings("ignore")
    raise SystemExit(main())
