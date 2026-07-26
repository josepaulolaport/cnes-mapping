#!/usr/bin/env python3
"""
Dermatology ETL → atlasmed-3 public schema (additive, CNES 202605).

Universe: active clinic/hospital units with ≥1 dermatologist (CBO 225135)
in tbCargaHorariaSus. Reuses existing facilities by CNES/CNPJ when found;
otherwise inserts source_provider='cnes'. Adds DERMATOLOGIA vertical profile.

  python import_derm_atlasmed.py --step preflight
  python import_derm_atlasmed.py --step all
  python import_derm_atlasmed.py --step all --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "BASE_DE_DADOS_CNES_202605"
DEFAULT_DB = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:592jphlap@localhost:5432/atlasmed-3"
)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "output"
NOW = datetime.now(timezone.utc).replace(tzinfo=None)

CBO_DERM = "225135"
CBO_PLASTICO = "225235"
CBO_ODONTO_AUX = frozenset(
    {"322405", "322410", "322415", "322420", "322425", "322430"}
)
DERM_LABEL = "MEDICO DERMATOLOGISTA"
VERTICAL_CODE = "DERMATOLOGIA"
VERTICAL_NAME = "Dermatologia"
SOURCE_PROVIDER = "cnes"

# Pure dermatology clinics only (matches prior "somente dermatologia" Excel cut).
IN_SCOPE_TP_UNIDADE = frozenset({"04", "22", "36"})

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
    "NU_CPF",
    "NU_CNPJ",
    "TP_UNIDADE",
    "CO_MUNICIPIO_GESTOR",
    "CO_MOTIVO_DESAB",
    "NO_URL",
    "NU_LATITUDE",
    "NU_LONGITUDE",
    "CO_TIPO_ESTABELECIMENTO",
    "TP_PFPJ",
]


def new_id() -> str:
    return uuid.uuid4().hex


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
            logger.info("Read %s: %s rows", path.name, f"{len(df):,}")
            return df
        except ValueError:
            # usecols mismatch — fall through encodings only on parse errors
            raise
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


def split_name(full: Optional[str]) -> tuple[str, str, Optional[str]]:
    if not full:
        return ("DESCONHECIDO", "DESCONHECIDO", None)
    parts = re.sub(r"\s+", " ", full.strip()).split(" ")
    if len(parts) == 1:
        return (parts[0], parts[0], full.strip())
    return (parts[0], " ".join(parts[1:]), full.strip())


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
    # CNES often packs multiple phones with "/"
    chunk = re.split(r"[/;,]", raw)[0]
    d = digits(chunk)
    if not d or len(d) < 8:
        return None
    return d


def clean_email(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    e = raw.strip().lower()
    if "@" not in e or "." not in e.split("@")[-1]:
        return None
    return e[:320]


def upsert_df(engine, table: str, df: pd.DataFrame, conflict: list[str], updates: list[str]) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    ph = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    conf = ", ".join(conflict)
    if updates:
        upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
        sql = text(
            f"INSERT INTO {table} ({col_list}) VALUES ({ph}) "
            f"ON CONFLICT ({conf}) DO UPDATE SET {upd}, updated_at = EXCLUDED.updated_at"
        )
    else:
        sql = text(
            f"INSERT INTO {table} ({col_list}) VALUES ({ph}) "
            f"ON CONFLICT ({conf}) DO NOTHING"
        )
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    with engine.begin() as conn:
        batch = 2000
        for i in range(0, len(records), batch):
            conn.execute(sql, records[i : i + batch])
    return len(records)


def insert_ignore(engine, table: str, df: pd.DataFrame, conflict: list[str]) -> int:
    return upsert_df(engine, table, df, conflict, updates=[])


class DermETL:
    def __init__(
        self,
        csv_dir: Path,
        db_url: str,
        out_dir: Path,
        cnes_version: str = "202605",
        dry_run: bool = False,
    ):
        self.csv_dir = csv_dir
        self.v = cnes_version
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self._cache: dict[str, Any] = {}

    def f(self, name: str) -> Path:
        return self.csv_dir / f"{name}{self.v}.csv"

    # ------------------------------------------------------------------
    # Universe build
    # ------------------------------------------------------------------
    def odonto_cbos(self) -> set[str]:
        if "odonto_cbos" in self._cache:
            return self._cache["odonto_cbos"]
        cat = read_csv(self.f("tbAtividadeProfissional"))
        codes = set(CBO_ODONTO_AUX)
        for _, row in cat.iterrows():
            code = row.get("CO_CBO")
            if not code or not str(code).startswith("2232"):
                continue
            label = (row.get("DS_ATIVIDADE_PROFISSIONAL") or "").upper()
            if "DENTISTA" in label or "ODONT" in label:
                codes.add(str(code))
        self._cache["odonto_cbos"] = codes
        return codes

    def build_universe(self) -> dict[str, Any]:
        if "universe" in self._cache:
            return self._cache["universe"]

        odonto = self.odonto_cbos()
        target_cbos = odonto | {CBO_DERM, CBO_PLASTICO}

        ch_all = read_csv(
            self.f("tbCargaHorariaSus"),
            usecols=[
                "CO_UNIDADE",
                "CO_PROFISSIONAL_SUS",
                "CO_CBO",
                "IND_VINCULACAO",
                "CO_CONSELHO_CLASSE",
                "NU_REGISTRO",
                "SG_UF_CRM",
            ],
        )
        ch_all = ch_all.dropna(subset=["CO_UNIDADE", "CO_CBO"])

        # Exclusivity among derm / plastic / odonto specialty CBOs only.
        ch_target = ch_all[ch_all["CO_CBO"].isin(target_cbos)]
        by_unit = ch_target.groupby("CO_UNIDADE")["CO_CBO"].apply(set)
        pure_units = {
            uid
            for uid, cbos in by_unit.items()
            if CBO_DERM in cbos
            and CBO_PLASTICO not in cbos
            and not (cbos & odonto)
        }

        ch = ch_all[ch_all["CO_CBO"] == CBO_DERM].copy()
        ch = ch[ch["CO_UNIDADE"].isin(pure_units)]
        ch = ch.dropna(subset=["CO_PROFISSIONAL_SUS"])
        ch = ch.drop_duplicates(["CO_UNIDADE", "CO_PROFISSIONAL_SUS"], keep="last")

        est = read_csv(self.f("tbEstabelecimento"), usecols=ESTAB_COLS)
        est_derm_any = est[est["CO_UNIDADE"].isin(set(ch_all.loc[ch_all["CO_CBO"] == CBO_DERM, "CO_UNIDADE"]))].copy()
        est = est[est["CO_UNIDADE"].isin(pure_units)].copy()
        est["active"] = est["CO_MOTIVO_DESAB"].isna()
        est["in_scope_type"] = est["TP_UNIDADE"].isin(IN_SCOPE_TP_UNIDADE)
        est_ok = est[est["active"] & est["in_scope_type"]].copy()

        mun = read_csv(
            self.f("tbMunicipio"),
            usecols=["CO_MUNICIPIO", "NO_MUNICIPIO", "CO_SIGLA_ESTADO"],
        )
        est_ok = est_ok.merge(
            mun, left_on="CO_MUNICIPIO_GESTOR", right_on="CO_MUNICIPIO", how="left"
        )

        sub = read_csv(
            self.f("rlEstabSubTipo"),
            usecols=["CO_UNIDADE", "CO_TIPO_UNIDADE", "CO_SUB_TIPO_UNIDADE"],
        ).drop_duplicates("CO_UNIDADE", keep="last")
        est_ok = est_ok.merge(sub, on="CO_UNIDADE", how="left")

        unit_ids = set(est_ok["CO_UNIDADE"])
        links = ch[ch["CO_UNIDADE"].isin(unit_ids)].copy()
        est_ok = est_ok[est_ok["CO_UNIDADE"].isin(set(links["CO_UNIDADE"]))].copy()

        prof_ids = set(links["CO_PROFISSIONAL_SUS"])
        prof_rows: list[pd.DataFrame] = []
        usecols = [
            "CO_PROFISSIONAL_SUS",
            "CO_CPF",
            "NO_PROFISSIONAL",
            "NO_SOCIAL",
        ]
        for chunk in pd.read_csv(
            self.f("tbDadosProfissionalSus"),
            sep=";",
            dtype=str,
            encoding="latin1",
            usecols=usecols,
            chunksize=200_000,
        ):
            chunk.columns = chunk.columns.str.strip().str.strip('"')
            for col in chunk.columns:
                chunk[col] = clean_series(chunk[col])
            hit = chunk[chunk["CO_PROFISSIONAL_SUS"].isin(prof_ids)]
            if len(hit):
                prof_rows.append(hit)
        profs = (
            pd.concat(prof_rows, ignore_index=True).drop_duplicates("CO_PROFISSIONAL_SUS")
            if prof_rows
            else pd.DataFrame(columns=usecols)
        )

        crm = (
            links.sort_values("NU_REGISTRO", na_position="last")
            .drop_duplicates("CO_PROFISSIONAL_SUS", keep="first")
            [
                [
                    "CO_PROFISSIONAL_SUS",
                    "CO_CONSELHO_CLASSE",
                    "NU_REGISTRO",
                    "SG_UF_CRM",
                ]
            ]
        )
        profs = profs.merge(crm, on="CO_PROFISSIONAL_SUS", how="left")

        # Stats vs broader derm-any population (for preflight transparency)
        est_derm_any["active"] = est_derm_any["CO_MOTIVO_DESAB"].isna()
        est_derm_any["in_scope_type"] = est_derm_any["TP_UNIDADE"].isin(IN_SCOPE_TP_UNIDADE)

        universe = {
            "establishments": est_ok,
            "links": links,
            "professionals": profs,
            "estab_raw_with_derm_cbo": len(est_derm_any),
            "estab_inactive": int((~est_derm_any["active"]).sum()),
            "estab_wrong_type": int((est_derm_any["active"] & ~est_derm_any["in_scope_type"]).sum()),
            "estab_excluded_not_pure_derm": int(
                est_derm_any["active"].sum() - len(est_ok)
            ),
        }
        self._cache["universe"] = universe
        return universe

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------
    def preflight(self) -> dict[str, Any]:
        logger.info("=== PREFLIGHT ===")
        u = self.build_universe()
        est = u["establishments"]
        links = u["links"]
        profs = u["professionals"]

        with self.engine.connect() as conn:
            existing = pd.read_sql(
                text(
                    """
                    SELECT id, cnes_code, cnpj, source_provider, updated_at
                    FROM facilities
                    WHERE cnes_code IS NOT NULL OR cnpj IS NOT NULL
                    """
                ),
                conn,
            )
            verticals = pd.read_sql(text("SELECT id, code FROM business_verticals"), conn)
            counts = {
                r[0]: int(r[1])
                for r in conn.execute(
                    text(
                        """
                        SELECT 'facilities', COUNT(*) FROM facilities
                        UNION ALL SELECT 'professionals', COUNT(*) FROM professionals
                        UNION ALL SELECT 'facility_professionals', COUNT(*) FROM facility_professionals
                        UNION ALL SELECT 'facility_vertical_profiles', COUNT(*) FROM facility_vertical_profiles
                        UNION ALL SELECT 'facility_services', COUNT(*) FROM facility_services
                        UNION ALL SELECT 'facility_representatives', COUNT(*) FROM facility_representatives
                        """
                    )
                )
            }

        est = est.copy()
        est["cnes_code"] = est["CO_CNES"].map(lambda x: digits(x, 7))
        est["cnpj_n"] = est["NU_CNPJ"].map(lambda x: digits(x, 14))

        by_cnes = existing[existing["cnes_code"].notna()].copy()
        by_cnes["cnes_code"] = by_cnes["cnes_code"].map(lambda x: digits(x, 7))
        # prefer CRM_JSON on duplicate CNES
        by_cnes["_pref"] = (by_cnes["source_provider"] == "CRM_JSON").astype(int)
        by_cnes = by_cnes.sort_values(["_pref", "updated_at"], ascending=[False, False])
        cnes_map = by_cnes.drop_duplicates("cnes_code").set_index("cnes_code")["id"].to_dict()

        existing["cnpj_n"] = existing["cnpj"].map(lambda x: digits(x, 14))
        cnpj_counts = existing.dropna(subset=["cnpj_n"]).groupby("cnpj_n").size()
        unique_cnpjs = set(cnpj_counts[cnpj_counts == 1].index)
        cnpj_map = (
            existing[existing["cnpj_n"].isin(unique_cnpjs)]
            .drop_duplicates("cnpj_n")
            .set_index("cnpj_n")["id"]
            .to_dict()
        )

        reuse_cnes = est["cnes_code"].isin(cnes_map)
        remaining = est[~reuse_cnes]
        reuse_cnpj = remaining["cnpj_n"].isin(cnpj_map) & remaining["cnpj_n"].notna()
        insert_n = int((~reuse_cnes).sum() - reuse_cnpj.sum())

        uf_counts = est["CO_SIGLA_ESTADO"].fillna("??").value_counts().to_dict()

        report = {
            "competence": self.v,
            "cbo": CBO_DERM,
            "unit_types": sorted(IN_SCOPE_TP_UNIDADE),
            "establishments_in_universe": int(len(est)),
            "derm_links": int(len(links)),
            "derm_professionals": int(len(profs)),
            "professionals_with_cpf": int(profs["CO_CPF"].notna().sum()) if len(profs) else 0,
            "professionals_with_crm": int(profs["NU_REGISTRO"].notna().sum()) if len(profs) else 0,
            "filtered_out_inactive": u["estab_inactive"],
            "filtered_out_wrong_unit_type": u["estab_wrong_type"],
            "filtered_out_not_pure_derm_or_hospital": u.get("estab_excluded_not_pure_derm"),
            "scope": "pure_derm_clinics_only",
            "unit_types_note": "04/22/36 only; excludes plastic + odonto co-located",
            "match_reuse_by_cnes": int(reuse_cnes.sum()),
            "match_reuse_by_cnpj": int(reuse_cnpj.sum()),
            "match_insert_new": insert_n,
            "missing_cnpj": int(est["cnpj_n"].isna().sum()),
            "missing_email": int(est["NO_EMAIL"].isna().sum()),
            "missing_phone": int(est["NU_TELEFONE"].map(first_phone).isna().sum()),
            "missing_geo": int(
                est.apply(
                    lambda r: not valid_br_point(
                        parse_coord(r["NU_LATITUDE"]), parse_coord(r["NU_LONGITUDE"])
                    ),
                    axis=1,
                ).sum()
            ),
            "by_uf": uf_counts,
            "existing_verticals": verticals.to_dict(orient="records"),
            "db_counts_before": counts,
            "dry_run": self.dry_run,
        }

        out = self.out_dir / f"derm_etl_preflight_{self.v}.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Preflight written: %s", out)
        logger.info(
            "Universe: %s facilities | %s derm pros | %s links | reuse cnes=%s cnpj=%s insert=%s",
            report["establishments_in_universe"],
            report["derm_professionals"],
            report["derm_links"],
            report["match_reuse_by_cnes"],
            report["match_reuse_by_cnpj"],
            report["match_insert_new"],
        )
        return report

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def load_lookups(self) -> None:
        logger.info("=== LOOKUPS ===")
        if self.dry_run:
            logger.info("dry-run: skip lookup writes")
            return
        ts = NOW

        svc = read_csv(self.f("tbServicoEspecializado")).rename(
            columns={
                "CO_SERVICO_ESPECIALIZADO": "service_code",
                "DS_SERVICO_ESPECIALIZADO": "service_name",
            }
        )[["service_code", "service_name"]].dropna(subset=["service_code"])
        svc["created_at"] = svc["updated_at"] = ts
        logger.info("services upserted: %s", upsert_df(self.engine, "services", svc, ["service_code"], ["service_name"]))

        cls = read_csv(self.f("tbClassificacaoServico")).rename(
            columns={
                "CO_CLASSIFICACAO_SERVICO": "classification_code",
                "CO_SERVICO_ESPECIALIZADO": "service_code",
                "DS_CLASSIFICACAO_SERVICO": "classification_name",
            }
        )[["service_code", "classification_code", "classification_name"]].dropna(
            subset=["service_code", "classification_code"]
        )
        cls["created_at"] = cls["updated_at"] = ts
        logger.info(
            "service_classifications: %s",
            upsert_df(
                self.engine,
                "service_classifications",
                cls,
                ["service_code", "classification_code"],
                ["classification_name"],
            ),
        )

        occ = read_csv(self.f("tbAtividadeProfissional")).rename(
            columns={
                "CO_CBO": "occupation_code",
                "DS_ATIVIDADE_PROFISSIONAL": "occupation_name",
                "TP_CLASSIFICACAO_PROFISSIONAL": "professional_classification",
                "TP_CBO_SAUDE": "is_health_occupation",
                "ST_CBO_REGULAMENTADO": "is_regulated",
                "NO_ANO_CMPT": "reference_year",
            }
        )
        cols = [
            "occupation_code",
            "occupation_name",
            "professional_classification",
            "is_health_occupation",
            "is_regulated",
            "reference_year",
        ]
        occ = occ[cols].drop_duplicates("occupation_code").dropna(subset=["occupation_code", "occupation_name"])
        occ["created_at"] = occ["updated_at"] = ts
        logger.info(
            "occupations: %s",
            upsert_df(
                self.engine,
                "occupations",
                occ,
                ["occupation_code"],
                [
                    "occupation_name",
                    "professional_classification",
                    "is_health_occupation",
                    "is_regulated",
                    "reference_year",
                ],
            ),
        )

        ft = read_csv(self.f("tbTipoEstabelecimento")).rename(
            columns={
                "CO_TIPO_ESTABELECIMENTO": "facility_type_code",
                "DS_TIPO_ESTABELECIMENTO": "facility_type_name",
                "DS_CONCEITO_TIPO": "concept_description",
            }
        )[["facility_type_code", "facility_type_name", "concept_description"]].dropna(
            subset=["facility_type_code"]
        )
        ft["created_at"] = ft["updated_at"] = ts
        logger.info(
            "facility_types: %s",
            upsert_df(
                self.engine,
                "facility_types",
                ft,
                ["facility_type_code"],
                ["facility_type_name", "concept_description"],
            ),
        )

        ut = read_csv(self.f("tbTipoUnidade")).rename(
            columns={"CO_TIPO_UNIDADE": "unit_type_code", "DS_TIPO_UNIDADE": "unit_type_name"}
        )[["unit_type_code", "unit_type_name"]].dropna(subset=["unit_type_code"])
        ut["created_at"] = ut["updated_at"] = ts
        logger.info("unit_types: %s", upsert_df(self.engine, "unit_types", ut, ["unit_type_code"], ["unit_type_name"]))

        st = read_csv(self.f("tbSubTipo")).rename(
            columns={
                "CO_TIPO_UNIDADE": "unit_type_code",
                "CO_SUB_TIPO": "subtype_code",
                "DS_SUB_TIPO": "subtype_name",
            }
        )[["unit_type_code", "subtype_code", "subtype_name"]].dropna(
            subset=["unit_type_code", "subtype_code"]
        )
        st["created_at"] = st["updated_at"] = ts
        logger.info(
            "unit_subtypes: %s",
            upsert_df(
                self.engine,
                "unit_subtypes",
                st,
                ["unit_type_code", "subtype_code"],
                ["subtype_name"],
            ),
        )

        dr = read_csv(self.f("tbMotivoDesativacao")).rename(
            columns={"CD_MOTIVO_DESAB": "deactivation_code", "DS_MOTIVO_DESAB": "deactivation_reason"}
        )[["deactivation_code", "deactivation_reason"]].dropna(subset=["deactivation_code"])
        dr["created_at"] = dr["updated_at"] = ts
        logger.info(
            "deactivation_reasons: %s",
            upsert_df(
                self.engine,
                "deactivation_reasons",
                dr,
                ["deactivation_code"],
                ["deactivation_reason"],
            ),
        )

    # ------------------------------------------------------------------
    # Vertical
    # ------------------------------------------------------------------
    def ensure_vertical(self) -> str:
        logger.info("=== VERTICAL ===")
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM business_verticals WHERE code = :c"),
                {"c": VERTICAL_CODE},
            ).fetchone()
            if row:
                logger.info("Vertical exists: %s", row[0])
                return row[0]
            if self.dry_run:
                logger.info("dry-run: would create DERMATOLOGIA")
                return "dry-run-vertical"
            vid = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO business_verticals (id, code, name, is_active, created_at, updated_at)
                    VALUES (:id, :code, :name, true, :ts, :ts)
                    """
                ),
                {"id": vid, "code": VERTICAL_CODE, "name": VERTICAL_NAME, "ts": NOW},
            )
            logger.info("Created vertical %s", vid)
            return vid

    # ------------------------------------------------------------------
    # Facilities + profiles
    # ------------------------------------------------------------------
    def load_facilities(self, vertical_id: str) -> pd.DataFrame:
        """Return mapping CO_UNIDADE -> facility_id for universe."""
        logger.info("=== FACILITIES ===")
        u = self.build_universe()
        est = u["establishments"].copy()
        est["cnes_code"] = est["CO_CNES"].map(lambda x: digits(x, 7))
        est["cnpj_n"] = est["NU_CNPJ"].map(lambda x: digits(x, 14))
        est["cpf_n"] = est["NU_CPF"].map(lambda x: digits(x, 11))

        with self.engine.connect() as conn:
            existing = pd.read_sql(
                text(
                    """
                    SELECT id, cnes_code, cnpj, source_provider, updated_at,
                           cnes_unit_id
                    FROM facilities
                    """
                ),
                conn,
            )
            valid_ft = {r[0] for r in conn.execute(text("SELECT facility_type_code FROM facility_types"))}
            ut_names = {
                r[0]: r[1]
                for r in conn.execute(text("SELECT unit_type_code, unit_type_name FROM unit_types"))
            }
            sub_names = {
                (r[0], r[1]): r[2]
                for r in conn.execute(
                    text("SELECT unit_type_code, subtype_code, subtype_name FROM unit_subtypes")
                )
            }
            existing_fvp = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT facility_id FROM facility_vertical_profiles WHERE vertical_id = :v"
                    ),
                    {"v": vertical_id} if vertical_id != "dry-run-vertical" else {"v": ""},
                )
            }

        existing["cnes_code_n"] = existing["cnes_code"].map(lambda x: digits(x, 7) if x else None)
        existing["cnpj_n"] = existing["cnpj"].map(lambda x: digits(x, 14) if x else None)

        by_cnes = existing[existing["cnes_code_n"].notna()].copy()
        by_cnes["_pref"] = (by_cnes["source_provider"] == "CRM_JSON").astype(int)
        by_cnes = by_cnes.sort_values(["_pref", "updated_at"], ascending=[False, False])
        cnes_map = by_cnes.drop_duplicates("cnes_code_n").set_index("cnes_code_n")["id"].to_dict()

        cnpj_counts = existing.dropna(subset=["cnpj_n"]).groupby("cnpj_n").size()
        unique_cnpjs = set(cnpj_counts[cnpj_counts == 1].index)
        cnpj_map = (
            existing[existing["cnpj_n"].isin(unique_cnpjs)]
            .drop_duplicates("cnpj_n")
            .set_index("cnpj_n")["id"]
            .to_dict()
        )

        unit_to_fac: dict[str, str] = {}
        reuse_ids: list[tuple[str, str, str]] = []  # facility_id, CO_UNIDADE, cnes_code
        inserts: list[dict[str, Any]] = []
        profiles: list[dict[str, Any]] = []

        for _, row in tqdm(est.iterrows(), total=len(est), desc="resolve facilities"):
            uid = row["CO_UNIDADE"]
            code = row["cnes_code"]
            cnpj = row["cnpj_n"]
            fac_id = None
            method = "insert"
            if code and code in cnes_map:
                fac_id = cnes_map[code]
                method = "cnes"
            elif cnpj and cnpj in cnpj_map:
                fac_id = cnpj_map[cnpj]
                method = "cnpj"
            else:
                fac_id = new_id()
                trade = row.get("NO_FANTASIA")
                legal = row.get("NO_RAZAO_SOCIAL")
                display = trade or legal or f"CNES {code}"
                lat = parse_coord(row.get("NU_LATITUDE"))
                lon = parse_coord(row.get("NU_LONGITUDE"))
                has_geo = valid_br_point(lat, lon)
                ut = row.get("TP_UNIDADE")
                ut_from_sub = row.get("CO_TIPO_UNIDADE")
                unit_type_code = ut_from_sub or ut
                subtype_code = row.get("CO_SUB_TIPO_UNIDADE")
                ft = row.get("CO_TIPO_ESTABELECIMENTO")
                if ft not in valid_ft:
                    ft = None
                if unit_type_code not in ut_names:
                    unit_type_code = ut if ut in ut_names else None
                subtype_name = sub_names.get((unit_type_code, subtype_code)) if unit_type_code and subtype_code else None
                if subtype_name is None:
                    subtype_code = None

                tax_type = "PJ"
                if cnpj:
                    tax_type = "PJ"
                elif row.get("cpf_n"):
                    tax_type = "PF"
                elif str(row.get("TP_PFPJ") or "") == "1":
                    tax_type = "PF"

                inserts.append(
                    {
                        "id": fac_id,
                        "name": display,
                        "legal_name": legal,
                        "trade_name": trade,
                        "cnes_code": code,
                        "cnes_unit_id": uid,
                        "facility_type_code": ft,
                        "is_active_in_registry": True,
                        "registry_deactivation_code": None,
                        "tax_id_type": tax_type,
                        "cnpj": cnpj,
                        "cpf": row.get("cpf_n") if tax_type == "PF" else None,
                        "country": "BR",
                        "state": row.get("CO_SIGLA_ESTADO"),
                        "city": row.get("NO_MUNICIPIO"),
                        "neighborhood": row.get("NO_BAIRRO"),
                        "street_address": row.get("NO_LOGRADOURO"),
                        "street_number": row.get("NU_ENDERECO"),
                        "address_complement": row.get("NO_COMPLEMENTO"),
                        "postal_code": digits(row.get("CO_CEP"), 8),
                        "phone_number": first_phone(row.get("NU_TELEFONE")),
                        "fax_number": first_phone(row.get("NU_FAX")),
                        "email": clean_email(row.get("NO_EMAIL")),
                        "website_url": row.get("NO_URL"),
                        "conformity_status": "INCOMPLETE",
                        "unit_type": ut_names.get(unit_type_code) if unit_type_code else None,
                        "unit_subtype": subtype_name,
                        "unit_type_code": unit_type_code,
                        "unit_subtype_code": subtype_code,
                        "territory_assignment_status": "unassigned",
                        "territory_assignment_source": "geo",
                        "source_provider": SOURCE_PROVIDER,
                        "external_source_id": uid,
                        "source_present": True,
                        "source_tracked": True,
                        "source_first_seen_at": NOW,
                        "source_last_seen_at": NOW,
                        "created_at": NOW,
                        "updated_at": NOW,
                        "_lat": lat if has_geo else None,
                        "_lon": lon if has_geo else None,
                    }
                )

            unit_to_fac[uid] = fac_id
            if method != "insert":
                reuse_ids.append((fac_id, uid, code or ""))

            if fac_id not in existing_fvp:
                profiles.append(
                    {
                        "id": new_id(),
                        "facility_id": fac_id,
                        "vertical_id": vertical_id,
                        "is_active": True,
                        "commercial_status": "INACTIVE",
                        "purchase_status": "NON_BUYER",
                        "created_at": NOW,
                        "updated_at": NOW,
                    }
                )
                existing_fvp.add(fac_id)

        logger.info(
            "Resolved: insert=%s reuse=%s profiles_to_add=%s",
            len(inserts),
            len(reuse_ids),
            len(profiles),
        )

        if self.dry_run:
            logger.info("dry-run: skip facility writes")
            return pd.DataFrame(
                [{"CO_UNIDADE": k, "facility_id": v} for k, v in unit_to_fac.items()]
            )

        # Insert facilities (without geometry first), then set location
        if inserts:
            ins_df = pd.DataFrame(inserts)
            geo = ins_df[["id", "_lat", "_lon"]].copy()
            ins_df = ins_df.drop(columns=["_lat", "_lon"])
            cols = list(ins_df.columns)
            sql = text(
                f"INSERT INTO facilities ({', '.join(cols)}) VALUES ({', '.join(':'+c for c in cols)}) "
                f"ON CONFLICT (source_provider, external_source_id) DO NOTHING"
            )
            records = ins_df.where(pd.notnull(ins_df), None).to_dict(orient="records")
            with self.engine.begin() as conn:
                for i in range(0, len(records), 1000):
                    conn.execute(sql, records[i : i + 1000])
                geo = geo[geo["_lat"].notna() & geo["_lon"].notna()]
                if len(geo):
                    geo.to_sql("_derm_geo_tmp", conn, if_exists="replace", index=False)
                    conn.execute(
                        text(
                            """
                            UPDATE facilities f
                            SET location = ST_SetSRID(ST_MakePoint(t._lon::float8, t._lat::float8), 4326)
                            FROM _derm_geo_tmp t
                            WHERE f.id = t.id AND f.location IS NULL
                            """
                        )
                    )
                    conn.execute(text("DROP TABLE IF EXISTS _derm_geo_tmp"))
            logger.info("Inserted facilities batch: %s", len(inserts))

            # Reconcile IDs in case of conflict (map CO_UNIDADE → actual DB id)
            with self.engine.connect() as conn:
                db_fac = pd.read_sql(
                    text(
                        """
                        SELECT id, external_source_id, cnes_code
                        FROM facilities
                        WHERE source_provider = :sp
                        """
                    ),
                    conn,
                    params={"sp": SOURCE_PROVIDER},
                )
            by_ext = db_fac.dropna(subset=["external_source_id"]).set_index("external_source_id")["id"].to_dict()
            by_code = (
                db_fac.dropna(subset=["cnes_code"])
                .assign(cnes_code=lambda d: d["cnes_code"].map(lambda x: digits(x, 7)))
                .drop_duplicates("cnes_code")
                .set_index("cnes_code")["id"]
                .to_dict()
            )
            for uid in list(unit_to_fac.keys()):
                if uid in by_ext:
                    unit_to_fac[uid] = by_ext[uid]
            # rebuild profiles with reconciled ids for all universe facilities
            profiles = [
                {
                    "id": new_id(),
                    "facility_id": fid,
                    "vertical_id": vertical_id,
                    "is_active": True,
                    "commercial_status": "INACTIVE",
                    "purchase_status": "NON_BUYER",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
                for fid in sorted(set(unit_to_fac.values()))
            ]

        # Null-only CNES identifiers on reused rows
        if reuse_ids:
            reuse_df = pd.DataFrame(reuse_ids, columns=["facility_id", "cnes_unit_id", "cnes_code"])
            with self.engine.begin() as conn:
                reuse_df.to_sql("_derm_reuse_tmp", conn, if_exists="replace", index=False)
                conn.execute(
                    text(
                        """
                        UPDATE facilities f
                        SET cnes_code = COALESCE(f.cnes_code, NULLIF(t.cnes_code, '')),
                            cnes_unit_id = COALESCE(f.cnes_unit_id, t.cnes_unit_id),
                            updated_at = NOW()
                        FROM _derm_reuse_tmp t
                        WHERE f.id = t.facility_id
                        """
                    )
                )
                conn.execute(text("DROP TABLE IF EXISTS _derm_reuse_tmp"))

        if profiles and vertical_id != "dry-run-vertical":
            pdf = pd.DataFrame(profiles).drop_duplicates("facility_id")
            with self.engine.begin() as conn:
                pdf.to_sql("_derm_fvp_tmp", conn, if_exists="replace", index=False)
                conn.execute(
                    text(
                        """
                        INSERT INTO facility_vertical_profiles
                          (id, facility_id, vertical_id, is_active, commercial_status,
                           purchase_status, created_at, updated_at)
                        SELECT id, facility_id, vertical_id, is_active::boolean,
                               commercial_status::commercial_status,
                               purchase_status::purchase_status,
                               created_at::timestamp, updated_at::timestamp
                        FROM _derm_fvp_tmp
                        ON CONFLICT (facility_id, vertical_id) DO NOTHING
                        """
                    )
                )
                conn.execute(text("DROP TABLE IF EXISTS _derm_fvp_tmp"))
            logger.info("Vertical profiles ensured: %s candidates", len(pdf))

        mapping = pd.DataFrame(
            [{"CO_UNIDADE": k, "facility_id": v} for k, v in unit_to_fac.items()]
        )
        mapping.to_csv(self.out_dir / f"derm_facility_map_{self.v}.csv", index=False)
        return mapping

    # ------------------------------------------------------------------
    # Professionals + links
    # ------------------------------------------------------------------
    def load_professionals(self, facility_map: pd.DataFrame) -> pd.DataFrame:
        logger.info("=== PROFESSIONALS ===")
        u = self.build_universe()
        profs = u["professionals"].copy()
        links = u["links"].merge(facility_map, on="CO_UNIDADE", how="inner")

        with self.engine.connect() as conn:
            existing = pd.read_sql(
                text(
                    """
                    SELECT id, source_provider, cnes_professional_id
                    FROM professionals
                    WHERE cnes_professional_id IS NOT NULL
                    """
                ),
                conn,
            )

        existing_key = {
            (r["source_provider"] or "", r["cnes_professional_id"]): r["id"]
            for _, r in existing.iterrows()
        }

        prof_id_map: dict[str, str] = {}
        inserts: list[dict[str, Any]] = []

        for _, row in profs.iterrows():
            cid = row["CO_PROFISSIONAL_SUS"]
            key = (SOURCE_PROVIDER, cid)
            if key in existing_key:
                prof_id_map[cid] = existing_key[key]
                continue
            pid = new_id()
            first, last, full = split_name(row.get("NO_PROFISSIONAL"))
            inserts.append(
                {
                    "id": pid,
                    "first_name": first,
                    "last_name": last,
                    "full_name": full,
                    "social_name": row.get("NO_SOCIAL"),
                    "tax_id": digits(row.get("CO_CPF"), 11),
                    "primary_specialty_label": DERM_LABEL,
                    "primary_occupation_code": CBO_DERM,
                    "crm_council": row.get("CO_CONSELHO_CLASSE"),
                    "crm_number": digits(row.get("NU_REGISTRO")),
                    "crm_state": (str(row["SG_UF_CRM"]).upper() if row.get("SG_UF_CRM") else None),
                    "source_provider": SOURCE_PROVIDER,
                    "external_source_id": cid,
                    "cnes_professional_id": cid,
                    "source_present": True,
                    "source_tracked": True,
                    "source_first_seen_at": NOW,
                    "source_last_seen_at": NOW,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            )
            prof_id_map[cid] = pid
            existing_key[key] = pid

        logger.info("Professionals: insert=%s reuse=%s", len(inserts), len(profs) - len(inserts))

        if not self.dry_run and inserts:
            idf = pd.DataFrame(inserts)
            cols = list(idf.columns)
            sql = text(
                f"INSERT INTO professionals ({', '.join(cols)}) "
                f"VALUES ({', '.join(':'+c for c in cols)}) "
                f"ON CONFLICT (source_provider, external_source_id) DO NOTHING"
            )
            records = idf.where(pd.notnull(idf), None).to_dict(orient="records")
            with self.engine.begin() as conn:
                for i in range(0, len(records), 1000):
                    conn.execute(sql, records[i : i + 1000])
            # reload map for conflicts that already existed
            ids = list(prof_id_map.keys())
            with self.engine.begin() as conn:
                pd.DataFrame({"cnes_professional_id": ids}).to_sql(
                    "_derm_prof_ids", conn, if_exists="replace", index=False
                )
                rows = conn.execute(
                    text(
                        """
                        SELECT p.id, p.cnes_professional_id
                        FROM professionals p
                        JOIN _derm_prof_ids t ON t.cnes_professional_id = p.cnes_professional_id
                        WHERE p.source_provider = :sp
                        """
                    ),
                    {"sp": SOURCE_PROVIDER},
                ).fetchall()
                conn.execute(text("DROP TABLE IF EXISTS _derm_prof_ids"))
            for pid, cid in rows:
                prof_id_map[cid] = pid

        # facility_professionals
        fp_rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        with self.engine.connect() as conn:
            existing_fp = {
                (r[0], r[1], r[2])
                for r in conn.execute(
                    text(
                        """
                        SELECT facility_id, professional_id, occupation_code
                        FROM facility_professionals
                        """
                    )
                )
            }

        for _, row in links.iterrows():
            fac_id = row["facility_id"]
            cid = row["CO_PROFISSIONAL_SUS"]
            pid = prof_id_map.get(cid)
            if not pid:
                continue
            key = (fac_id, pid, CBO_DERM)
            if key in seen or key in existing_fp:
                continue
            seen.add(key)
            fp_rows.append(
                {
                    "id": new_id(),
                    "professional_id": pid,
                    "facility_id": fac_id,
                    "occupation_code": CBO_DERM,
                    "specialty_label": DERM_LABEL,
                    "employment_type_code": row.get("IND_VINCULACAO"),
                    "source_occupation_code": CBO_DERM,
                    "is_prescriber": True,
                    "is_buyer": False,
                    "is_decision_maker": False,
                    "is_partner": False,
                    "source_active": True,
                    "source_first_seen_at": NOW,
                    "source_last_seen_at": NOW,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            )

        logger.info("facility_professionals candidates: %s", len(fp_rows))
        if not self.dry_run and fp_rows:
            fdf = pd.DataFrame(fp_rows)
            with self.engine.begin() as conn:
                fdf.to_sql("_derm_fp_tmp", conn, if_exists="replace", index=False)
                conn.execute(
                    text(
                        """
                        INSERT INTO facility_professionals (
                          id, professional_id, facility_id, occupation_code, specialty_label,
                          employment_type_code, source_occupation_code,
                          is_prescriber, is_buyer, is_decision_maker, is_partner,
                          source_active, source_first_seen_at, source_last_seen_at,
                          created_at, updated_at
                        )
                        SELECT id, professional_id, facility_id, occupation_code, specialty_label,
                               employment_type_code, source_occupation_code,
                               is_prescriber::boolean, is_buyer::boolean,
                               is_decision_maker::boolean, is_partner::boolean,
                               source_active::boolean,
                               source_first_seen_at::timestamp, source_last_seen_at::timestamp,
                               created_at::timestamp, updated_at::timestamp
                        FROM _derm_fp_tmp
                        ON CONFLICT (facility_id, professional_id, occupation_code) DO NOTHING
                        """
                    )
                )
                conn.execute(text("DROP TABLE IF EXISTS _derm_fp_tmp"))

        return pd.DataFrame(
            [{"CO_PROFISSIONAL_SUS": k, "professional_id": v} for k, v in prof_id_map.items()]
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------
    def load_services(self, facility_map: pd.DataFrame) -> None:
        logger.info("=== FACILITY SERVICES ===")
        unit_ids = set(facility_map["CO_UNIDADE"])
        rel = read_csv(
            self.f("rlEstabServClass"),
            usecols=["CO_UNIDADE", "CO_SERVICO", "CO_CLASSIFICACAO", "ST_ATIVO_SN"],
        )
        if "ST_ATIVO_SN" in rel.columns:
            rel = rel[rel["ST_ATIVO_SN"].isna() | (rel["ST_ATIVO_SN"].str.upper() == "S")]
        rel = rel[rel["CO_UNIDADE"].isin(unit_ids)].merge(facility_map, on="CO_UNIDADE")
        rel = rel.rename(
            columns={
                "facility_id": "facility_id",
                "CO_SERVICO": "service_code",
                "CO_CLASSIFICACAO": "classification_code",
            }
        ).dropna(subset=["service_code", "classification_code"])
        rel = rel.drop_duplicates(["facility_id", "service_code", "classification_code"])

        with self.engine.connect() as conn:
            valid = {
                (r[0], r[1])
                for r in conn.execute(
                    text("SELECT service_code, classification_code FROM service_classifications")
                )
            }
        rel = rel[
            rel.apply(lambda r: (r["service_code"], r["classification_code"]) in valid, axis=1)
        ]
        logger.info("facility_services candidates: %s", len(rel))
        if self.dry_run or rel.empty:
            return

        out = pd.DataFrame(
            {
                "id": [new_id() for _ in range(len(rel))],
                "facility_id": rel["facility_id"].values,
                "service_code": rel["service_code"].values,
                "classification_code": rel["classification_code"].values,
                "source_provider": SOURCE_PROVIDER,
                "source_first_seen_at": NOW,
                "source_last_seen_at": NOW,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
        with self.engine.begin() as conn:
            out.to_sql("_derm_fs_tmp", conn, if_exists="replace", index=False)
            conn.execute(
                text(
                    """
                    INSERT INTO facility_services (
                      id, facility_id, service_code, classification_code, source_provider,
                      source_first_seen_at, source_last_seen_at, created_at, updated_at
                    )
                    SELECT id, facility_id, service_code, classification_code, source_provider,
                           source_first_seen_at::timestamp, source_last_seen_at::timestamp,
                           created_at::timestamp, updated_at::timestamp
                    FROM _derm_fs_tmp
                    ON CONFLICT (facility_id, service_code, classification_code) DO NOTHING
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _derm_fs_tmp"))

    # ------------------------------------------------------------------
    # Representatives
    # ------------------------------------------------------------------
    def load_representatives(self, facility_map: pd.DataFrame) -> None:
        logger.info("=== REPRESENTATIVES ===")
        path = self.f("rlEstabRepresentante")
        if not path.exists():
            logger.warning("Representatives file missing: %s", path)
            return
        rep = read_csv(path)
        rep = rep.merge(facility_map, on="CO_UNIDADE", how="inner")
        rep = rep.dropna(subset=["NO_REPRESENTANTE"])
        if rep.empty:
            logger.info("No representatives for derm universe")
            return

        rows: list[dict[str, Any]] = []
        for _, r in rep.iterrows():
            cpf = digits(r.get("CO_CPF"), 11)
            key = f"{r['CO_UNIDADE']}|{cpf or ''}|{r['NO_REPRESENTANTE']}"
            rows.append(
                {
                    "id": new_id(),
                    "facility_id": r["facility_id"],
                    "representative_name": r["NO_REPRESENTANTE"],
                    "role_title": r.get("DS_CARGO"),
                    "email": clean_email(r.get("DS_E_MAIL")),
                    "tax_id": cpf,
                    "contact_type": "PROFESSIONAL",
                    "is_partner": False,
                    "is_administrator": False,
                    "is_decision_maker": False,
                    "is_buyer": False,
                    "is_biller": False,
                    "is_secretary": False,
                    "source_provider": SOURCE_PROVIDER,
                    "external_source_key": key[:240],
                    "source_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            )
        logger.info("representatives candidates: %s", len(rows))
        if self.dry_run or not rows:
            return
        rdf = pd.DataFrame(rows)
        with self.engine.begin() as conn:
            rdf.to_sql("_derm_rep_tmp", conn, if_exists="replace", index=False)
            conn.execute(
                text(
                    """
                    INSERT INTO facility_representatives (
                      id, facility_id, representative_name, role_title, email, tax_id,
                      contact_type, is_partner, is_administrator, is_decision_maker,
                      is_buyer, is_biller, is_secretary, source_provider, external_source_key,
                      source_active, created_at, updated_at
                    )
                    SELECT id, facility_id, representative_name, role_title, email, tax_id,
                           contact_type::contact_type,
                           is_partner::boolean, is_administrator::boolean,
                           is_decision_maker::boolean, is_buyer::boolean,
                           is_biller::boolean, is_secretary::boolean,
                           source_provider, external_source_key, source_active::boolean,
                           created_at::timestamp, updated_at::timestamp
                    FROM _derm_rep_tmp
                    ON CONFLICT (facility_id, external_source_key) DO NOTHING
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _derm_rep_tmp"))

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------
    def prune_to_universe(self) -> dict[str, Any]:
        """Remove DERMATOLOGIA rows outside pure-derm clinic universe. Keeps ORTOPEDIA."""
        logger.info("=== PRUNE TO PURE DERM ===")
        u = self.build_universe()
        keep_units = set(u["establishments"]["CO_UNIDADE"])
        keep_cnes = {
            digits(c, 7)
            for c in u["establishments"]["CO_CNES"].tolist()
            if digits(c, 7)
        }
        logger.info("Keep universe: %s units", len(keep_units))

        if self.dry_run:
            with self.engine.connect() as conn:
                derm_fac = pd.read_sql(
                    text(
                        """
                        SELECT f.id, f.cnes_unit_id, f.cnes_code, f.source_provider
                        FROM facilities f
                        JOIN facility_vertical_profiles fvp ON fvp.facility_id = f.id
                        JOIN business_verticals bv ON bv.id = fvp.vertical_id
                        WHERE bv.code = 'DERMATOLOGIA'
                        """
                    ),
                    conn,
                )
            derm_fac["cnes_code_n"] = derm_fac["cnes_code"].map(lambda x: digits(x, 7) if x else None)
            keep_ids = set(
                derm_fac.loc[
                    derm_fac["cnes_unit_id"].isin(keep_units)
                    | derm_fac["cnes_code_n"].isin(keep_cnes),
                    "id",
                ]
            )
            report = {
                "dry_run": True,
                "keep": len(keep_ids),
                "drop_profiles": int(len(derm_fac) - len(keep_ids)),
            }
            logger.info("dry-run prune: %s", report)
            return report

        with self.engine.begin() as conn:
            pd.DataFrame({"cnes_unit_id": list(keep_units)}).to_sql(
                "_derm_keep_units", conn, if_exists="replace", index=False
            )
            pd.DataFrame({"cnes_code": list(keep_cnes)}).to_sql(
                "_derm_keep_cnes", conn, if_exists="replace", index=False
            )

            keep_ids = [
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT DISTINCT f.id
                        FROM facilities f
                        WHERE f.cnes_unit_id IN (SELECT cnes_unit_id FROM _derm_keep_units)
                           OR f.cnes_code IN (SELECT cnes_code FROM _derm_keep_cnes)
                        """
                    )
                )
            ]
            pd.DataFrame({"facility_id": keep_ids}).to_sql(
                "_derm_keep_fac", conn, if_exists="replace", index=False
            )

            # 1) Drop DERMATOLOGIA profiles not in keep set
            r1 = conn.execute(
                text(
                    """
                    DELETE FROM facility_vertical_profiles fvp
                    USING business_verticals bv
                    WHERE fvp.vertical_id = bv.id
                      AND bv.code = 'DERMATOLOGIA'
                      AND NOT EXISTS (
                        SELECT 1 FROM _derm_keep_fac k WHERE k.facility_id = fvp.facility_id
                      )
                    """
                )
            )
            logger.info("Deleted derm profiles: %s", r1.rowcount)

            # 2) Drop derm professional links outside keep set
            r2 = conn.execute(
                text(
                    """
                    DELETE FROM facility_professionals fp
                    WHERE fp.occupation_code = :cbo
                      AND NOT EXISTS (
                        SELECT 1 FROM _derm_keep_fac k WHERE k.facility_id = fp.facility_id
                      )
                    """
                ),
                {"cbo": CBO_DERM},
            )
            logger.info("Deleted derm facility_professionals: %s", r2.rowcount)

            # 3) Delete cnes-only facilities no longer in derm and not in ORTOPEDIA
            r3 = conn.execute(
                text(
                    """
                    DELETE FROM facilities f
                    WHERE f.source_provider = :sp
                      AND NOT EXISTS (
                        SELECT 1 FROM _derm_keep_fac k WHERE k.facility_id = f.id
                      )
                      AND NOT EXISTS (
                        SELECT 1
                        FROM facility_vertical_profiles fvp
                        JOIN business_verticals bv ON bv.id = fvp.vertical_id
                        WHERE fvp.facility_id = f.id AND bv.code = 'ORTOPEDIA'
                      )
                    """
                ),
                {"sp": SOURCE_PROVIDER},
            )
            logger.info("Deleted orphan cnes facilities: %s", r3.rowcount)

            # 4) Delete cnes professionals with no remaining links
            r4 = conn.execute(
                text(
                    """
                    DELETE FROM professionals p
                    WHERE p.source_provider = :sp
                      AND NOT EXISTS (
                        SELECT 1 FROM facility_professionals fp
                        WHERE fp.professional_id = p.id
                      )
                    """
                ),
                {"sp": SOURCE_PROVIDER},
            )
            logger.info("Deleted orphan cnes professionals: %s", r4.rowcount)

            conn.execute(text("DROP TABLE IF EXISTS _derm_keep_units"))
            conn.execute(text("DROP TABLE IF EXISTS _derm_keep_cnes"))
            conn.execute(text("DROP TABLE IF EXISTS _derm_keep_fac"))

            report = {
                "keep_facilities": len(keep_ids),
                "deleted_derm_profiles": r1.rowcount,
                "deleted_derm_fp": r2.rowcount,
                "deleted_cnes_facilities": r3.rowcount,
                "deleted_orphan_professionals": r4.rowcount,
            }

        out = self.out_dir / f"derm_etl_prune_{self.v}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Prune report: %s", report)
        return report

    def verify(self) -> dict[str, Any]:
        logger.info("=== VERIFY ===")
        with self.engine.connect() as conn:
            vid = conn.execute(
                text("SELECT id FROM business_verticals WHERE code = :c"),
                {"c": VERTICAL_CODE},
            ).fetchone()
            vertical_id = vid[0] if vid else None
            report = {
                r[0]: int(r[1])
                for r in conn.execute(
                    text(
                        """
                        SELECT 'facilities_total', COUNT(*) FROM facilities
                        UNION ALL SELECT 'facilities_cnes_provider', COUNT(*) FROM facilities WHERE source_provider = 'cnes'
                        UNION ALL SELECT 'professionals_cnes', COUNT(*) FROM professionals WHERE source_provider = 'cnes'
                        UNION ALL SELECT 'facility_professionals_derm', COUNT(*) FROM facility_professionals WHERE occupation_code = '225135'
                        UNION ALL SELECT 'facility_services', COUNT(*) FROM facility_services
                        UNION ALL SELECT 'facility_representatives_cnes', COUNT(*) FROM facility_representatives WHERE source_provider = 'cnes'
                        UNION ALL SELECT 'derm_vertical_profiles', COUNT(*) FROM facility_vertical_profiles fvp
                          JOIN business_verticals bv ON bv.id = fvp.vertical_id WHERE bv.code = 'DERMATOLOGIA'
                        UNION ALL SELECT 'ortho_vertical_profiles', COUNT(*) FROM facility_vertical_profiles fvp
                          JOIN business_verticals bv ON bv.id = fvp.vertical_id WHERE bv.code = 'ORTOPEDIA'
                        """
                    )
                )
            }
            sample = []
            if vertical_id:
                sample = [
                    dict(r._mapping)
                    for r in conn.execute(
                        text(
                            """
                            SELECT f.name, f.cnes_code, f.state, f.city, f.source_provider,
                                   (SELECT COUNT(*) FROM facility_professionals fp
                                    WHERE fp.facility_id = f.id AND fp.occupation_code = '225135') AS derm_count
                            FROM facilities f
                            JOIN facility_vertical_profiles fvp ON fvp.facility_id = f.id
                            WHERE fvp.vertical_id = :v
                            ORDER BY derm_count DESC NULLS LAST
                            LIMIT 10
                            """
                        ),
                        {"v": vertical_id},
                    )
                ]
        out = {"counts": report, "sample": sample}
        path = self.out_dir / f"derm_etl_verify_{self.v}.json"
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("Verify: %s", report)
        return out

    def run_all(self) -> None:
        self.preflight()
        self.load_lookups()
        vertical_id = self.ensure_vertical()
        fmap = self.load_facilities(vertical_id)
        self.load_professionals(fmap)
        self.load_services(fmap)
        self.load_representatives(fmap)
        self.prune_to_universe()
        self.verify()


def main() -> None:
    p = argparse.ArgumentParser(description="Dermatology CNES → atlasmed-3 public ETL")
    p.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV)
    p.add_argument("--db-url", default=DEFAULT_DB)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--cnes-version", default="202605")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--step",
        choices=[
            "preflight",
            "lookups",
            "vertical",
            "facilities",
            "professionals",
            "services",
            "representatives",
            "prune",
            "verify",
            "all",
        ],
        default="all",
    )
    args = p.parse_args()
    etl = DermETL(args.csv_dir, args.db_url, args.out_dir, args.cnes_version, args.dry_run)

    if args.step == "preflight":
        etl.preflight()
    elif args.step == "lookups":
        etl.load_lookups()
    elif args.step == "vertical":
        etl.ensure_vertical()
    elif args.step == "facilities":
        vid = etl.ensure_vertical()
        etl.load_facilities(vid)
    elif args.step == "professionals":
        vid = etl.ensure_vertical()
        fmap = etl.load_facilities(vid)
        etl.load_professionals(fmap)
    elif args.step == "services":
        vid = etl.ensure_vertical()
        fmap = etl.load_facilities(vid)
        etl.load_services(fmap)
    elif args.step == "representatives":
        vid = etl.ensure_vertical()
        fmap = etl.load_facilities(vid)
        etl.load_representatives(fmap)
    elif args.step == "prune":
        etl.prune_to_universe()
        etl.verify()
    elif args.step == "verify":
        etl.verify()
    else:
        etl.run_all()
    logger.info("DONE")


if __name__ == "__main__":
    main()
