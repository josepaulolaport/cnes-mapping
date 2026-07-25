#!/usr/bin/env python3
"""
Load CNES CSV data into atlasmed-3 public schema.

  python import_atlasmed_cnes.py --step all
  python import_atlasmed_cnes.py --step lookups
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "BASE_DE_DADOS_CNES_202605"
DEFAULT_DB = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/atlasmed_test")
NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def read_csv(path: Path, usecols: Optional[list[str]] = None) -> pd.DataFrame:
    for encoding in ("latin1", "cp1252", "utf-8-sig"):
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding=encoding, usecols=usecols)
            df.columns = df.columns.str.strip().str.strip('"')
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.strip().str.strip('"')
                    df.loc[df[col].isin(["", "nan", "None", "NULL"]), col] = None
            logger.info("Read %s: %s rows", path.name, f"{len(df):,}")
            return df
        except Exception:
            continue
    raise RuntimeError(f"Failed to read {path}")


def norm_crm(s) -> str:
    s = re.sub(r"[^0-9]", "", str(s or "").strip())
    return s.lstrip("0") or "0"


def norm_name(s) -> str:
    s = str(s or "").upper().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def norm_facility_name(s) -> str:
    """Normalize facility names for matching; strip common legal suffixes."""
    s = norm_name(s)
    for w in ("LTDA", "EIRELI", "ME", "EPP", "SA", "SS", "CIA"):
        s = re.sub(rf"\b{w}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def upsert(engine, table: str, df: pd.DataFrame, conflict: list[str], updates: list[str]) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    ph = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    conf = ", ".join(conflict)
    upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
    sql = text(
        f"INSERT INTO {table} ({col_list}) VALUES ({ph}) "
        f"ON CONFLICT ({conf}) DO UPDATE SET {upd}, updated_at = EXCLUDED.updated_at"
    )
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    with engine.begin() as conn:
        # batch to avoid huge payloads
        batch = 2000
        for i in range(0, len(records), batch):
            conn.execute(sql, records[i : i + batch])
    return len(records)


class AtlasMedCNESImporter:
    def __init__(self, csv_dir: Path, db_url: str, cnes_version: str = "202605"):
        self.csv_dir = csv_dir
        self.v = cnes_version
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self._fac_map: Optional[pd.DataFrame] = None

    def f(self, name: str) -> Path:
        return self.csv_dir / f"{name}{self.v}.csv"

    def load_lookups(self) -> None:
        logger.info("=== LOOKUPS ===")
        ts = NOW

        svc = read_csv(self.f("tbServicoEspecializado")).rename(
            columns={"CO_SERVICO_ESPECIALIZADO": "service_code", "DS_SERVICO_ESPECIALIZADO": "service_name"}
        )[["service_code", "service_name"]].dropna(subset=["service_code"])
        svc["created_at"] = svc["updated_at"] = ts
        n = upsert(self.engine, "services", svc, ["service_code"], ["service_name"])
        logger.info("services: %s", n)

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
        n = upsert(
            self.engine,
            "service_classifications",
            cls,
            ["service_code", "classification_code"],
            ["classification_name"],
        )
        logger.info("service_classifications: %s", n)

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
        n = upsert(
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
        )
        logger.info("occupations: %s", n)

        ft = read_csv(self.f("tbTipoEstabelecimento")).rename(
            columns={
                "CO_TIPO_ESTABELECIMENTO": "facility_type_code",
                "DS_TIPO_ESTABELECIMENTO": "facility_type_name",
                "DS_CONCEITO_TIPO": "concept_description",
            }
        )[["facility_type_code", "facility_type_name", "concept_description"]].dropna(subset=["facility_type_code"])
        ft["created_at"] = ft["updated_at"] = ts
        n = upsert(
            self.engine,
            "facility_types",
            ft,
            ["facility_type_code"],
            ["facility_type_name", "concept_description"],
        )
        logger.info("facility_types: %s", n)

        ut = read_csv(self.f("tbTipoUnidade")).rename(
            columns={"CO_TIPO_UNIDADE": "unit_type_code", "DS_TIPO_UNIDADE": "unit_type_name"}
        )[["unit_type_code", "unit_type_name"]].dropna(subset=["unit_type_code"])
        ut["created_at"] = ut["updated_at"] = ts
        n = upsert(self.engine, "unit_types", ut, ["unit_type_code"], ["unit_type_name"])
        logger.info("unit_types: %s", n)

        st = read_csv(self.f("tbSubTipo")).rename(
            columns={
                "CO_TIPO_UNIDADE": "unit_type_code",
                "CO_SUB_TIPO": "subtype_code",
                "DS_SUB_TIPO": "subtype_name",
            }
        )[["unit_type_code", "subtype_code", "subtype_name"]].dropna(subset=["unit_type_code", "subtype_code"])
        st["created_at"] = st["updated_at"] = ts
        n = upsert(
            self.engine,
            "unit_subtypes",
            st,
            ["unit_type_code", "subtype_code"],
            ["subtype_name"],
        )
        logger.info("unit_subtypes: %s", n)

        dr = read_csv(self.f("tbMotivoDesativacao")).rename(
            columns={"CD_MOTIVO_DESAB": "deactivation_code", "DS_MOTIVO_DESAB": "deactivation_reason"}
        )[["deactivation_code", "deactivation_reason"]].dropna(subset=["deactivation_code"])
        dr["created_at"] = dr["updated_at"] = ts
        n = upsert(self.engine, "deactivation_reasons", dr, ["deactivation_code"], ["deactivation_reason"])
        logger.info("deactivation_reasons: %s", n)

    def facility_map(self, force_reload: bool = False) -> pd.DataFrame:
        """Match CRM facilities → CNES by cnes_code, unique CNPJ, then unique name+geo."""
        if self._fac_map is not None and not force_reload:
            return self._fac_map

        est = read_csv(
            self.f("tbEstabelecimento"),
            usecols=[
                "CO_CNES",
                "CO_UNIDADE",
                "CO_TIPO_ESTABELECIMENTO",
                "TP_UNIDADE",
                "CO_MOTIVO_DESAB",
                "NU_CNPJ",
                "NO_FANTASIA",
                "NO_RAZAO_SOCIAL",
                "CO_MUNICIPIO_GESTOR",
            ],
        )

        def norm_cnpj(s):
            if s is None or (isinstance(s, float) and pd.isna(s)):
                return None
            d = "".join(ch for ch in str(s) if ch.isdigit())
            return d.zfill(14) if d else None

        mun = read_csv(
            self.f("tbMunicipio"),
            usecols=["CO_MUNICIPIO", "NO_MUNICIPIO", "CO_SIGLA_ESTADO"],
        )
        mun["city_n"] = mun["NO_MUNICIPIO"].map(norm_facility_name)
        mun["state_n"] = mun["CO_SIGLA_ESTADO"].astype(str).str.strip().str.upper()

        est["cnpj_n"] = est["NU_CNPJ"].map(norm_cnpj)
        est["fant_n"] = est["NO_FANTASIA"].map(norm_facility_name)
        est["raz_n"] = est["NO_RAZAO_SOCIAL"].map(norm_facility_name)
        est = est.merge(
            mun[["CO_MUNICIPIO", "city_n", "state_n"]],
            left_on="CO_MUNICIPIO_GESTOR",
            right_on="CO_MUNICIPIO",
            how="left",
        )

        fac = pd.read_sql(
            text(
                "SELECT id, cnes_code, cnpj, name, legal_name, trade_name, "
                "state, city, source_provider FROM facilities"
            ),
            self.engine,
        )
        fac["cnes_code"] = fac["cnes_code"].astype(str).str.strip()
        fac.loc[fac["cnes_code"].isin(["", "None", "nan"]), "cnes_code"] = None
        fac["cnpj_n"] = fac["cnpj"].map(norm_cnpj)
        fac["state_n"] = fac["state"].astype(str).str.strip().str.upper()
        fac["city_n"] = fac["city"].map(norm_facility_name)
        fac["name_n"] = fac["name"].map(norm_facility_name)
        fac["legal_n"] = fac["legal_name"].map(norm_facility_name)
        fac["trade_n"] = fac["trade_name"].map(norm_facility_name)

        # 1) Direct CNES code match
        by_code = fac[fac["cnes_code"].notna()].merge(
            est, left_on="cnes_code", right_on="CO_CNES", how="inner"
        )
        by_code["match_method"] = "cnes_code"
        matched_ids = set(by_code["id"])

        # 2) Unique CNPJ → single CNES unit (high confidence)
        cnpj_nunique = est.dropna(subset=["cnpj_n"]).groupby("cnpj_n").size()
        unique_cnpjs = set(cnpj_nunique[cnpj_nunique == 1].index)
        est_unique = est[est["cnpj_n"].isin(unique_cnpjs)].drop_duplicates("cnpj_n")

        remaining = fac[~fac["id"].isin(matched_ids) & fac["cnpj_n"].notna()]
        by_cnpj = remaining.merge(est_unique, on="cnpj_n", how="inner")
        by_cnpj["match_method"] = "cnpj_unique"
        # Fill cnes_code from match for later writes
        by_cnpj["cnes_code"] = by_cnpj["CO_CNES"]

        # Avoid assigning same CNES code to two CRM facilities under same source_provider
        taken = set(
            zip(
                by_code["source_provider"].fillna(""),
                by_code["CO_CNES"],
            )
        )
        keep = []
        for _, row in by_cnpj.iterrows():
            key = (row["source_provider"] or "", row["CO_CNES"])
            if key in taken:
                continue
            taken.add(key)
            keep.append(row)
        by_cnpj = pd.DataFrame(keep) if keep else by_cnpj.iloc[0:0]
        matched_ids.update(by_cnpj["id"].tolist())

        # 3) Unique normalized name + geography (only when CNES key is unique)
        est_cols = [
            "CO_CNES",
            "CO_UNIDADE",
            "CO_TIPO_ESTABELECIMENTO",
            "TP_UNIDADE",
            "CO_MOTIVO_DESAB",
            "fant_n",
            "raz_n",
            "state_n",
            "city_n",
        ]

        def unique_name_match(
            rem: pd.DataFrame,
            fac_col: str,
            est_col: str,
            *,
            with_city: bool,
            min_len: int,
            method: str,
        ) -> pd.DataFrame:
            if rem.empty:
                return rem.iloc[0:0]
            ekeys = [est_col, "state_n"] + (["city_n"] if with_city else [])
            fkeys = [fac_col, "state_n"] + (["city_n"] if with_city else [])
            e = est[est[est_col].notna() & (est[est_col] != "")].copy()
            cnt = e.groupby(ekeys).size().reset_index(name="n")
            e_u = e.merge(cnt[cnt["n"] == 1][ekeys], on=ekeys)[est_cols]
            f = rem[rem[fac_col].notna() & (rem[fac_col].str.len() >= min_len)]
            m = f.merge(e_u, left_on=fkeys, right_on=ekeys, how="inner")
            rows = []
            for _, row in m.drop_duplicates("id").iterrows():
                key = (row["source_provider"] or "", row["CO_CNES"])
                if key in taken or row["id"] in matched_ids:
                    continue
                taken.add(key)
                matched_ids.add(row["id"])
                rows.append(row)
            if not rows:
                return rem.iloc[0:0]
            out = pd.DataFrame(rows)
            out["match_method"] = method
            out["cnes_code"] = out["CO_CNES"]
            return out

        by_name_parts: list[pd.DataFrame] = []
        name_strategies = [
            ("trade_n", "fant_n", True, 8, "name_trade_fant_city"),
            ("name_n", "fant_n", True, 8, "name_name_fant_city"),
            ("legal_n", "raz_n", True, 8, "name_legal_raz_city"),
            ("trade_n", "raz_n", True, 8, "name_trade_raz_city"),
            ("name_n", "raz_n", True, 8, "name_name_raz_city"),
            ("legal_n", "fant_n", True, 8, "name_legal_fant_city"),
            ("trade_n", "fant_n", False, 15, "name_trade_fant_state"),
            ("name_n", "fant_n", False, 15, "name_name_fant_state"),
            ("legal_n", "raz_n", False, 15, "name_legal_raz_state"),
        ]
        for fac_col, est_col, with_city, min_len, method in name_strategies:
            rem = fac[~fac["id"].isin(matched_ids)]
            part = unique_name_match(
                rem, fac_col, est_col, with_city=with_city, min_len=min_len, method=method
            )
            if len(part):
                by_name_parts.append(part)

        by_name = (
            pd.concat(by_name_parts, ignore_index=True).drop_duplicates("id")
            if by_name_parts
            else fac.iloc[0:0]
        )

        merged = pd.concat([by_code, by_cnpj, by_name], ignore_index=True)
        logger.info(
            "Facility map: %s total (%s by cnes_code, %s by unique CNPJ, %s by name)",
            len(merged),
            len(by_code),
            len(by_cnpj),
            len(by_name),
        )
        self._fac_map = merged
        return merged

    def enrich_facilities(self) -> None:
        logger.info("=== FACILITIES ===")
        m = self.facility_map().copy()
        sub = read_csv(
            self.f("rlEstabSubTipo"),
            usecols=["CO_UNIDADE", "CO_TIPO_UNIDADE", "CO_SUB_TIPO_UNIDADE"],
        ).drop_duplicates("CO_UNIDADE", keep="last")
        m = m.merge(sub, on="CO_UNIDADE", how="left")

        # CNES: TP_UNIDADE is populated; prefer subtype's unit type when present
        m["unit_type_code"] = m["CO_TIPO_UNIDADE"].fillna(m["TP_UNIDADE"])
        m["unit_subtype_code"] = m["CO_SUB_TIPO_UNIDADE"]
        m["facility_type_code"] = m["CO_TIPO_ESTABELECIMENTO"]
        m["registry_deactivation_code"] = m["CO_MOTIVO_DESAB"]
        m["is_active_in_registry"] = m["registry_deactivation_code"].isna()

        with self.engine.connect() as conn:
            valid_ft = {r[0] for r in conn.execute(text("SELECT facility_type_code FROM facility_types"))}
            valid_ut = {r[0] for r in conn.execute(text("SELECT unit_type_code FROM unit_types"))}
            valid_sub = {
                (r[0], r[1])
                for r in conn.execute(text("SELECT unit_type_code, subtype_code FROM unit_subtypes"))
            }
            valid_dr = {r[0] for r in conn.execute(text("SELECT deactivation_code FROM deactivation_reasons"))}
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

        m.loc[~m["facility_type_code"].isin(valid_ft), "facility_type_code"] = None
        m.loc[~m["unit_type_code"].isin(valid_ut), "unit_type_code"] = None
        m["unit_subtype_code"] = [
            sc if (ut, sc) in valid_sub else None
            for ut, sc in zip(m["unit_type_code"], m["unit_subtype_code"])
        ]
        m.loc[
            m["registry_deactivation_code"].notna() & ~m["registry_deactivation_code"].isin(valid_dr),
            "registry_deactivation_code",
        ] = None

        # Also refresh display text from CNES names when we have codes
        m["unit_type"] = m["unit_type_code"].map(ut_names)
        m["unit_subtype"] = [
            sub_names.get((ut, sc)) for ut, sc in zip(m["unit_type_code"], m["unit_subtype_code"])
        ]

        upd = m[
            [
                "id",
                "CO_CNES",
                "CO_UNIDADE",
                "facility_type_code",
                "unit_type_code",
                "unit_subtype_code",
                "unit_type",
                "unit_subtype",
                "registry_deactivation_code",
                "is_active_in_registry",
            ]
        ].rename(
            columns={
                "id": "facility_id",
                "CO_CNES": "cnes_code",
                "CO_UNIDADE": "cnes_unit_id",
            }
        )

        with self.engine.begin() as conn:
            upd.to_sql("_fac_enrich_tmp", conn, if_exists="replace", index=False)
            result = conn.execute(
                text(
                    """
                    UPDATE facilities f
                    SET cnes_code = COALESCE(f.cnes_code, t.cnes_code),
                        cnes_unit_id = t.cnes_unit_id,
                        facility_type_code = t.facility_type_code,
                        unit_type_code = t.unit_type_code,
                        unit_subtype_code = t.unit_subtype_code,
                        unit_type = COALESCE(t.unit_type, f.unit_type),
                        unit_subtype = COALESCE(t.unit_subtype, f.unit_subtype),
                        registry_deactivation_code = t.registry_deactivation_code,
                        is_active_in_registry = t.is_active_in_registry,
                        updated_at = NOW()
                    FROM _fac_enrich_tmp t
                    WHERE f.id = t.facility_id
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _fac_enrich_tmp"))
            logger.info("Updated %s facilities", result.rowcount)
            # Invalidate cache so services/professionals see newly linked facilities
            self._fac_map = None

    def load_facility_services(self) -> None:
        logger.info("=== FACILITY SERVICES ===")
        fac = self.facility_map()[["id", "CO_UNIDADE"]]
        unit_ids = set(fac["CO_UNIDADE"])
        rel = read_csv(
            self.f("rlEstabServClass"),
            usecols=["CO_UNIDADE", "CO_SERVICO", "CO_CLASSIFICACAO"],
        )
        rel = rel[rel["CO_UNIDADE"].isin(unit_ids)].merge(fac, on="CO_UNIDADE")
        rel = rel.rename(
            columns={
                "id": "facility_id",
                "CO_SERVICO": "service_code",
                "CO_CLASSIFICACAO": "classification_code",
            }
        ).drop_duplicates(["facility_id", "service_code", "classification_code"])

        rel["id"] = [str(uuid.uuid4()) for _ in range(len(rel))]
        rel["source_provider"] = "cnes"
        rel["source_first_seen_at"] = rel["source_last_seen_at"] = NOW
        rel["created_at"] = rel["updated_at"] = NOW
        out = rel[
            [
                "id",
                "facility_id",
                "service_code",
                "classification_code",
                "source_provider",
                "source_first_seen_at",
                "source_last_seen_at",
                "created_at",
                "updated_at",
            ]
        ]

        with self.engine.begin() as conn:
            out.to_sql("_fs_tmp", conn, if_exists="replace", index=False)
            result = conn.execute(
                text(
                    """
                    INSERT INTO facility_services (
                        id, facility_id, service_code, classification_code,
                        source_provider, source_first_seen_at, source_last_seen_at,
                        created_at, updated_at
                    )
                    SELECT id, facility_id, service_code, classification_code,
                           source_provider, source_first_seen_at, source_last_seen_at,
                           created_at, updated_at
                    FROM _fs_tmp
                    ON CONFLICT (facility_id, service_code, classification_code)
                    DO UPDATE SET
                        source_last_seen_at = EXCLUDED.source_last_seen_at,
                        updated_at = EXCLUDED.updated_at
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _fs_tmp"))
            logger.info("Upserted %s facility_services", result.rowcount)

    def enrich_professionals(self) -> None:
        logger.info("=== PROFESSIONALS ===")
        fac = self.facility_map()[["id", "CO_UNIDADE"]]
        unit_ids = set(fac["CO_UNIDADE"])

        # Build CRM index + workload at our units (chunked)
        crm_chunks = []
        our_chunks = []
        for chunk in pd.read_csv(
            self.f("tbCargaHorariaSus"),
            sep=";",
            dtype=str,
            encoding="latin1",
            usecols=["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO", "NU_REGISTRO", "SG_UF_CRM"],
            chunksize=500_000,
        ):
            for c in chunk.columns:
                chunk[c] = chunk[c].astype(str).str.strip()
            chunk["uf"] = chunk["SG_UF_CRM"].str.upper()
            chunk["crm_n"] = chunk["NU_REGISTRO"].map(norm_crm)
            chunk = chunk[(chunk["NU_REGISTRO"] != "") & (chunk["NU_REGISTRO"] != "nan")]
            crm_chunks.append(chunk[["crm_n", "uf", "CO_PROFISSIONAL_SUS", "CO_CBO"]].drop_duplicates())
            our = chunk[chunk["CO_UNIDADE"].isin(unit_ids)][
                ["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO", "crm_n", "uf", "NU_REGISTRO"]
            ]
            if len(our):
                our_chunks.append(our)

        wh_crm = pd.concat(crm_chunks).drop_duplicates(["crm_n", "uf"], keep="last")
        wh_our = pd.concat(our_chunks).drop_duplicates() if our_chunks else pd.DataFrame()
        logger.info("CRM index %s; workload at our units %s", f"{len(wh_crm):,}", f"{len(wh_our):,}")

        occ = pd.read_sql(text("SELECT occupation_code, occupation_name FROM occupations"), self.engine)
        occ_name = dict(zip(occ["occupation_code"], occ["occupation_name"]))

        # Primary CBO per CNES professional (most common at our units, else from CRM index)
        primary = (
            wh_our.dropna(subset=["CO_PROFISSIONAL_SUS", "CO_CBO"])
            .groupby(["CO_PROFISSIONAL_SUS", "CO_CBO"])
            .size()
            .reset_index(name="n")
            .sort_values(["CO_PROFISSIONAL_SUS", "n"], ascending=[True, False])
            .drop_duplicates("CO_PROFISSIONAL_SUS")
            .rename(columns={"CO_CBO": "primary_occupation_code"})
        )

        fp = pd.read_sql(
            text(
                """
                SELECT fp.id AS fp_id, fp.facility_id, p.id AS professional_id,
                       p.full_name, p.crm_number, p.crm_state, p.primary_specialty_label,
                       p.source_provider
                FROM facility_professionals fp
                JOIN facilities f ON f.id = fp.facility_id
                JOIN professionals p ON p.id = fp.professional_id
                WHERE f.cnes_code IS NOT NULL
                """
            ),
            self.engine,
        )
        fp = fp.merge(fac, left_on="facility_id", right_on="id", suffixes=("", "_fac"))
        fp["crm_n"] = fp["crm_number"].map(norm_crm)
        fp["uf"] = fp["crm_state"].astype(str).str.strip().str.upper()
        fp["name_n"] = fp["full_name"].map(norm_name)

        # 1) CRM+UF anywhere
        m = fp.merge(wh_crm, on=["crm_n", "uf"], how="left", suffixes=("", "_crm"))
        matched = m["CO_PROFISSIONAL_SUS"].notna()
        logger.info("Match CRM+UF: %s", matched.sum())

        # 2) Unique CRM-only among miss
        miss_mask = ~matched
        crm_uf_n = wh_crm.groupby("crm_n")["uf"].nunique()
        unique_crm = set(crm_uf_n[crm_uf_n == 1].index)
        miss = m[miss_mask].copy()
        miss_u = miss[miss["crm_n"].isin(unique_crm)].drop(columns=["CO_PROFISSIONAL_SUS", "CO_CBO"], errors="ignore")
        miss_u = miss_u.merge(wh_crm, on="crm_n", how="left", suffixes=("", "_x"))
        # pick first
        miss_u = miss_u.drop_duplicates("fp_id")
        for idx, row in miss_u.iterrows():
            if pd.notna(row.get("CO_PROFISSIONAL_SUS")):
                m.loc[m["fp_id"] == row["fp_id"], "CO_PROFISSIONAL_SUS"] = row["CO_PROFISSIONAL_SUS"]
                m.loc[m["fp_id"] == row["fp_id"], "CO_CBO"] = row["CO_CBO"]
        matched = m["CO_PROFISSIONAL_SUS"].notna()
        logger.info("After unique CRM-only: %s", matched.sum())

        # 3) Name at same facility
        miss = m[~matched].copy()
        if len(miss) and len(wh_our):
            pids = set(wh_our["CO_PROFISSIONAL_SUS"])
            name_chunks = []
            for chunk in pd.read_csv(
                self.f("tbDadosProfissionalSus"),
                sep=";",
                dtype=str,
                encoding="latin1",
                usecols=["CO_PROFISSIONAL_SUS", "NO_PROFISSIONAL"],
                chunksize=500_000,
            ):
                chunk = chunk[chunk["CO_PROFISSIONAL_SUS"].isin(pids)]
                if len(chunk):
                    name_chunks.append(chunk)
            if name_chunks:
                prof = pd.concat(name_chunks)
                for c in prof.columns:
                    prof[c] = prof[c].astype(str).str.strip()
                prof["name_n"] = prof["NO_PROFISSIONAL"].map(norm_name)
                wh_named = wh_our.merge(prof, on="CO_PROFISSIONAL_SUS")
                wh_named["first"] = wh_named["name_n"].str.split().str[0]
                wh_named["last"] = wh_named["name_n"].str.split().str[-1]
                miss["first"] = miss["name_n"].str.split().str[0]
                miss["last"] = miss["name_n"].str.split().str[-1]

                exact = miss.merge(wh_named, on=["CO_UNIDADE", "name_n"], how="inner", suffixes=("", "_c"))
                exact = exact.drop_duplicates("fp_id")
                for _, row in exact.iterrows():
                    m.loc[m["fp_id"] == row["fp_id"], "CO_PROFISSIONAL_SUS"] = row["CO_PROFISSIONAL_SUS"]
                    m.loc[m["fp_id"] == row["fp_id"], "CO_CBO"] = row["CO_CBO"]

                matched = m["CO_PROFISSIONAL_SUS"].notna()
                miss2 = m[~matched].copy()
                miss2["first"] = miss2["name_n"].str.split().str[0]
                miss2["last"] = miss2["name_n"].str.split().str[-1]
                fuzzy = miss2.merge(
                    wh_named, on=["CO_UNIDADE", "first", "last"], how="inner", suffixes=("", "_c")
                ).drop_duplicates("fp_id")
                for _, row in fuzzy.iterrows():
                    m.loc[m["fp_id"] == row["fp_id"], "CO_PROFISSIONAL_SUS"] = row["CO_PROFISSIONAL_SUS"]
                    m.loc[m["fp_id"] == row["fp_id"], "CO_CBO"] = row["CO_CBO"]
                matched = m["CO_PROFISSIONAL_SUS"].notna()
                logger.info("After name match: %s", matched.sum())

        # Same-facility CBO preferred
        if len(wh_our):
            same_key = (
                wh_our[["CO_UNIDADE", "crm_n", "uf", "CO_CBO"]]
                .dropna(subset=["CO_CBO"])
                .drop_duplicates(["CO_UNIDADE", "crm_n", "uf"], keep="last")
                .rename(columns={"CO_CBO": "cbo_same"})
            )
            m = m.merge(same_key, on=["CO_UNIDADE", "crm_n", "uf"], how="left")
            m["cbo_link"] = m["cbo_same"].fillna(m["CO_CBO"])
        else:
            m["cbo_link"] = m["CO_CBO"]

        # Attach primary occupation
        m = m.merge(primary[["CO_PROFISSIONAL_SUS", "primary_occupation_code"]], on="CO_PROFISSIONAL_SUS", how="left")
        m["primary_occupation_code"] = m["primary_occupation_code"].fillna(m["CO_CBO"]).fillna(m["cbo_link"])

        # CRM text → CBO fallback for remaining
        def infer_cbo(label: str) -> Optional[str]:
            if not label:
                return None
            t = norm_name(label)
            rules = [
                ("ORTOPED", "225270"),
                ("TRAUMAT", "225270"),
                ("DERMAT", "225135"),
                ("CARDIOLOG", "225120"),
                ("CIRURGIAO GERAL", "225225"),
                ("ANESTES", "225151"),
                ("PEDIATR", "225124"),
                ("GINECO", "225250"),
                ("OFTALM", "225265"),
                ("NEUROLOG", "225260"),
                ("PSIQUIATR", "225133"),
                ("RADIOLOG", "225320"),
                ("MEDICO", "225125"),  # generic clinical physician last
            ]
            for needle, code in rules:
                if needle in t:
                    return code
            return None

        still = m["primary_occupation_code"].isna()
        m.loc[still, "primary_occupation_code"] = m.loc[still, "primary_specialty_label"].map(infer_cbo)
        m.loc[m["cbo_link"].isna(), "cbo_link"] = m.loc[m["cbo_link"].isna(), "primary_occupation_code"]

        m["primary_specialty_from_cbo"] = m["primary_occupation_code"].map(occ_name)
        m["specialty_label"] = m["cbo_link"].map(occ_name)
        # Prefer CNES name; keep CRM label if already set and no CBO name
        m["primary_specialty_out"] = m["primary_specialty_from_cbo"].fillna(m["primary_specialty_label"])

        # Update professionals (unique by professional_id; prefer rows with CNES id)
        pro = (
            m.sort_values("CO_PROFISSIONAL_SUS", na_position="last")
            .drop_duplicates("professional_id")
            [
                [
                    "professional_id",
                    "CO_PROFISSIONAL_SUS",
                    "primary_occupation_code",
                    "primary_specialty_out",
                    "source_provider",
                ]
            ]
            .rename(
                columns={
                    "professional_id": "id",
                    "CO_PROFISSIONAL_SUS": "cnes_professional_id",
                    "primary_specialty_out": "primary_specialty_label",
                }
            )
        )
        # Avoid unique violation on (source_provider, cnes_professional_id)
        with self.engine.begin() as conn:
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
        owner_by_key = {
            (r["source_provider"] or "", r["cnes_professional_id"]): r["id"]
            for _, r in existing.iterrows()
        }

        def safe_cnes(row):
            cid = row["cnes_professional_id"]
            if not cid or (isinstance(cid, float) and pd.isna(cid)):
                return None
            key = (row["source_provider"] or "", cid)
            owner = owner_by_key.get(key)
            if owner is not None and owner != row["id"]:
                return None  # already owned by someone else
            return cid

        pro["cnes_professional_id"] = pro.apply(safe_cnes, axis=1)
        # Unique within batch: first row keeps the CNES id
        pro = pro.sort_values("cnes_professional_id", na_position="last")
        claimed: set[tuple[str, str]] = set()
        safe_ids = []
        for _, row in pro.iterrows():
            cid = row["cnes_professional_id"]
            if cid and not (isinstance(cid, float) and pd.isna(cid)):
                key = (row["source_provider"] or "", cid)
                if key in claimed:
                    safe_ids.append(None)
                    continue
                claimed.add(key)
                owner_by_key[key] = row["id"]
            safe_ids.append(cid if cid and not (isinstance(cid, float) and pd.isna(cid)) else None)
        pro["cnes_professional_id"] = safe_ids

        with self.engine.begin() as conn:
            pro[["id", "cnes_professional_id", "primary_occupation_code", "primary_specialty_label"]].to_sql(
                "_pro_tmp", conn, if_exists="replace", index=False
            )
            # Only set cnes_professional_id when free (or already ours)
            result = conn.execute(
                text(
                    """
                    UPDATE professionals p
                    SET cnes_professional_id = CASE
                            WHEN t.cnes_professional_id IS NULL THEN p.cnes_professional_id
                            WHEN p.cnes_professional_id IS NOT DISTINCT FROM t.cnes_professional_id
                                THEN p.cnes_professional_id
                            WHEN EXISTS (
                                SELECT 1 FROM professionals x
                                WHERE x.source_provider = p.source_provider
                                  AND x.cnes_professional_id = t.cnes_professional_id
                                  AND x.id <> p.id
                            ) THEN p.cnes_professional_id
                            ELSE t.cnes_professional_id
                        END,
                        primary_occupation_code = COALESCE(t.primary_occupation_code, p.primary_occupation_code),
                        primary_specialty_label = COALESCE(t.primary_specialty_label, p.primary_specialty_label),
                        updated_at = NOW()
                    FROM _pro_tmp t
                    WHERE p.id = t.id
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _pro_tmp"))
            logger.info("Updated %s professionals", result.rowcount)

        # Update facility_professionals
        fp_upd = m[["fp_id", "cbo_link", "specialty_label"]].rename(
            columns={"fp_id": "id", "cbo_link": "source_occupation_code"}
        )
        fp_upd = fp_upd[fp_upd["source_occupation_code"].notna()].drop_duplicates("id")

        with self.engine.begin() as conn:
            fp_upd.to_sql("_fp_tmp", conn, if_exists="replace", index=False)
            result = conn.execute(
                text(
                    """
                    UPDATE facility_professionals fp
                    SET source_occupation_code = t.source_occupation_code,
                        specialty_label = COALESCE(t.specialty_label, fp.specialty_label),
                        source_active = true,
                        source_last_seen_at = NOW(),
                        updated_at = NOW()
                    FROM _fp_tmp t
                    WHERE fp.id = t.id
                    """
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _fp_tmp"))
            logger.info("Updated %s facility_professionals", result.rowcount)

        logger.info(
            "Coverage: CNES id set on links %s / %s; CBO on links %s / %s",
            m["CO_PROFISSIONAL_SUS"].notna().sum(),
            len(m),
            m["cbo_link"].notna().sum(),
            len(m),
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV)
    p.add_argument("--db-url", default=DEFAULT_DB)
    p.add_argument("--cnes-version", default="202605")
    p.add_argument(
        "--step",
        choices=["lookups", "facilities", "facility_services", "professionals", "all"],
        default="all",
    )
    args = p.parse_args()
    imp = AtlasMedCNESImporter(args.csv_dir, args.db_url, args.cnes_version)
    steps = {
        "lookups": imp.load_lookups,
        "facilities": imp.enrich_facilities,
        "facility_services": imp.load_facility_services,
        "professionals": imp.enrich_professionals,
    }
    if args.step == "all":
        for fn in steps.values():
            fn()
    else:
        steps[args.step]()
    logger.info("DONE")


if __name__ == "__main__":
    main()
