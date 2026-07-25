#!/usr/bin/env python3
"""
Modular CNES Data Import Script
================================

Import specific tables or all tables from CNES CSV files.

Usage:
    python import_modular.py --table states
    python import_modular.py --table all
    python import_modular.py --table facilities --force

Available tables:
    - states
    - municipalities
    - facility_types
    - deactivation_reasons
    - service_specialties
    - equipment_catalog
    - professional_councils
    - equipment_categories
    - service_classifications
    - agreement_types
    - care_types
    - installation_subtypes
    - physical_installation_types
    - physical_installations
    - maintainers
    - facilities
    - enrich_facilities (unit type/subtype names on existing facilities)
    - professionals
    - facility_professionals
    - facility_services
    - facility_equipment
    - facility_agreements
    - facility_physical_installations
    - facility_representatives
    - professional_workload
    - all (imports everything in correct order)
"""

import os
import sys
import csv
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/import_modular.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
CNES_ENCODINGS = ['latin1', 'cp1252', 'utf-8-sig']
BATCH_SIZE = 10000
ERROR_LOG_DIR = Path('../import_errors')

# Create error log directory
ERROR_LOG_DIR.mkdir(exist_ok=True)


class ModularCNESImporter:
    """Modular CNES data importer - import one table at a time"""
    
    def __init__(self, csv_dir: str, db_url: str, cnes_version: str = '202605', schema: str = 'cnes'):
        self.csv_dir = Path(csv_dir)
        self.db_url = db_url
        self.cnes_version = cnes_version
        self.schema = schema
        self.engine = create_engine(db_url, pool_pre_ping=True, 
                                   connect_args={'options': f'-csearch_path={schema},public'})
        
        logger.info(f"Initialized for CNES version: {cnes_version}")
        logger.info(f"CSV directory: {self.csv_dir}")
        logger.info(f"Database: {db_url.split('@')[-1]}")
        logger.info(f"Schema: {schema}")
    
    def read_csv_with_encoding(self, file_path: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Read CSV with automatic encoding and delimiter detection"""
        delimiters = [';', ',', '\t']
        
        for encoding in CNES_ENCODINGS:
            for delimiter in delimiters:
                try:
                    df_sample = pd.read_csv(
                        file_path, 
                        encoding=encoding, 
                        delimiter=delimiter,
                        nrows=5
                    )
                    
                    if len(df_sample.columns) > 1:
                        df = pd.read_csv(
                            file_path,
                            encoding=encoding,
                            delimiter=delimiter,
                            dtype=str,
                            na_values=['', 'NULL', 'null', 'NA'],
                            keep_default_na=True
                        )
                        
                        # Clean column names and cell values
                        df.columns = df.columns.str.strip().str.strip('"').str.strip("'")
                        for col in df.columns:
                            if df[col].dtype == 'object':
                                df[col] = df[col].str.strip().str.strip('"').str.strip("'")
                        
                        logger.info(f"✓ Read {file_path.name}: {len(df)} rows, {len(df.columns)} columns")
                        return df, encoding
                        
                except Exception as e:
                    continue
        
        logger.error(f"✗ Failed to read {file_path.name}")
        return None, None
    
    def table_exists_and_has_data(self, table_name: str) -> bool:
        """Check if table exists and has data"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {self.schema}.{table_name}"))
                count = result.fetchone()[0]
                return count > 0
        except:
            return False
    
    def _map_to_int_flag(self, series: pd.Series) -> pd.Series:
        """Map CNES S/N/1/0 flags to nullable integer for PostgreSQL INTEGER columns."""
        mapped = series.map({'1': 1, '0': 0, 'S': 1, 'N': 0, 'T': 1, 'F': 0, True: 1, False: 0})
        return pd.to_numeric(mapped, errors='coerce').astype('Int64')
    
    def import_batch_with_error_handling(self, table_name: str, batch_df: pd.DataFrame, 
                                         batch_num: int, error_log_file: Path) -> int:
        """
        Import a batch with error handling. Returns number of successfully imported records.
        Failed records are logged to error_log_file.
        """
        try:
            batch_df.to_sql(table_name, self.engine, schema=self.schema, 
                          if_exists='append', index=False, method='multi')
            return len(batch_df)
        except Exception as e:
            # If batch fails, try row-by-row
            logger.warning(f"Batch {batch_num} failed, trying row-by-row: {str(e)[:100]}")
            success_count = 0
            
            with open(error_log_file, 'a', encoding='utf-8') as f:
                for idx, row in batch_df.iterrows():
                    try:
                        row.to_frame().T.to_sql(table_name, self.engine, schema=self.schema,
                                                if_exists='append', index=False, method='multi')
                        success_count += 1
                    except Exception as row_error:
                        # Log the failed row
                        f.write(f"\n{'='*80}\n")
                        f.write(f"Batch: {batch_num}, Row Index: {idx}\n")
                        f.write(f"Error: {str(row_error)}\n")
                        f.write(f"Data: {row.to_dict()}\n")
            
            if success_count < len(batch_df):
                failed_count = len(batch_df) - success_count
                logger.warning(f"  {failed_count} records failed in batch {batch_num}")
            
            return success_count
    
    # =========================================================================
    # INDIVIDUAL TABLE IMPORT METHODS
    # =========================================================================
    
    def import_states(self, force: bool = False) -> int:
        """Import states table"""
        if not force and self.table_exists_and_has_data('states'):
            logger.info("✓ states already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing states...")
        
        csv_file = self.csv_dir / f"tbEstado{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Map columns
        df = df.rename(columns={
            'CO_SIGLA': 'state_code',
            'NO_DESCRICAO': 'state_name'
        })
        
        df = df[['state_code', 'state_name']].drop_duplicates(subset=['state_code'], keep='first')
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.states"))
                conn.commit()
        
        df.to_sql('states', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} states")
        return len(df)
    
    def import_municipalities(self, force: bool = False) -> int:
        """Import municipalities table"""
        if not force and self.table_exists_and_has_data('municipalities'):
            logger.info("✓ municipalities already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing municipalities...")
        
        csv_file = self.csv_dir / f"tbMunicipio{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Map columns
        df = df.rename(columns={
            'CO_MUNICIPIO': 'municipality_id',
            'NO_MUNICIPIO': 'municipality_name',
            'CO_SIGLA_ESTADO': 'state_code',
            'TP_CADASTRO': 'registration_type',
            'TP_PACTO': 'pact_type',
            'TP_ENVIA': 'data_submission_type'
        })
        
        # Filter out invalid state codes
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT state_code FROM states"))
            valid_states = {row[0] for row in result}
        
        original_count = len(df)
        df = df[df['state_code'].isin(valid_states)]
        if original_count > len(df):
            logger.info(f"  Filtered out {original_count - len(df)} municipalities with invalid state codes")
        
        df = df[['municipality_id', 'municipality_name', 'state_code', 
                 'registration_type', 'pact_type', 'data_submission_type']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.municipalities"))
                conn.commit()
        
        df.to_sql('municipalities', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} municipalities")
        return len(df)
    
    def import_facility_types(self, force: bool = False) -> int:
        """Import facility types table"""
        if not force and self.table_exists_and_has_data('facility_types'):
            logger.info("✓ facility_types already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing facility types...")
        
        csv_file = self.csv_dir / f"tbTipoEstabelecimento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CO_TIPO_ESTABELECIMENTO': 'facility_type_code',
            'DS_TIPO_ESTABELECIMENTO': 'facility_type_name'
        })
        
        df = df[['facility_type_code', 'facility_type_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_types"))
                conn.commit()
        
        df.to_sql('facility_types', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} facility types")
        return len(df)
    
    def import_deactivation_reasons(self, force: bool = False) -> int:
        """Import deactivation reasons table"""
        if not force and self.table_exists_and_has_data('deactivation_reasons'):
            logger.info("✓ deactivation_reasons already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing deactivation reasons...")
        
        csv_file = self.csv_dir / f"tbMotivoDesativacao{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CD_MOTIVO_DESAB': 'deactivation_code',
            'DS_MOTIVO_DESAB': 'deactivation_reason'
        })
        
        df = df[['deactivation_code', 'deactivation_reason']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.deactivation_reasons"))
                conn.commit()
        
        df.to_sql('deactivation_reasons', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} deactivation reasons")
        return len(df)
    
    def import_service_specialties(self, force: bool = False) -> int:
        """Import service specialties table"""
        if not force and self.table_exists_and_has_data('service_specialties'):
            logger.info("✓ service_specialties already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing service specialties...")
        
        csv_file = self.csv_dir / f"tbServicoEspecializado{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CO_SERVICO_ESPECIALIZADO': 'service_code',
            'DS_SERVICO_ESPECIALIZADO': 'service_name'
        })
        
        df = df[['service_code', 'service_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.service_specialties"))
                conn.commit()
        
        df.to_sql('service_specialties', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} service specialties")
        return len(df)
    
    def import_equipment_catalog(self, force: bool = False) -> int:
        """Import equipment catalog table"""
        if not force and self.table_exists_and_has_data('equipment_catalog'):
            logger.info("✓ equipment_catalog already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing equipment catalog...")
        
        csv_file = self.csv_dir / f"tbEquipamento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CO_EQUIPAMENTO': 'equipment_code',
            'CO_TIPO_EQUIPAMENTO': 'equipment_type_code',
            'DS_EQUIPAMENTO': 'equipment_name',
            'NU_RENEM': 'renem_code'
        })
        
        df = df[['equipment_code', 'equipment_type_code', 'equipment_name', 'renem_code']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.equipment_catalog"))
                conn.commit()
        
        df.to_sql('equipment_catalog', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} equipment entries")
        return len(df)
    
    def import_professional_councils(self, force: bool = False) -> int:
        """Import professional councils table"""
        if not force and self.table_exists_and_has_data('professional_councils'):
            logger.info("✓ professional_councils already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing professional councils...")
        
        csv_file = self.csv_dir / f"tbConselhoClasse{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CO_CONSELHO_CLASSE': 'council_code',
            'DS_CONSELHO_CLASSE': 'council_name'
        })
        
        df = df[['council_code', 'council_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.professional_councils"))
                conn.commit()
        
        df.to_sql('professional_councils', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} professional councils")
        return len(df)
    
    def import_equipment_categories(self, force: bool = False) -> int:
        """Import equipment categories table"""
        if not force and self.table_exists_and_has_data('equipment_categories'):
            logger.info("✓ equipment_categories already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing equipment categories...")
        
        csv_file = self.csv_dir / f"tbTipoEquipamento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = df.rename(columns={
            'CO_TIPO_EQUIPAMENTO': 'category_code',
            'DS_TIPO_EQUIPAMENTO': 'category_name'
        })
        
        df['category_code'] = df['category_code'].astype(str).str.strip()
        df = df[['category_code', 'category_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.equipment_categories"))
                conn.commit()
        
        df.to_sql('equipment_categories', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} equipment categories")
        return len(df)
    
    def import_service_classifications(self, force: bool = False) -> int:
        """Import service classifications table"""
        if not force and self.table_exists_and_has_data('service_classifications'):
            logger.info("✓ service_classifications already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing service classifications...")
        
        csv_file = self.csv_dir / f"tbClassificacaoServico{self.cnes_version}.csv"
        
        if not csv_file.exists():
            logger.warning(f"File not found: {csv_file}, skipping")
            return 0
        
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            logger.warning(f"Failed to read {csv_file}")
            return 0
        
        df = df.rename(columns={
            'CO_CLASSIFICACAO_SERVICO': 'classification_id',
            'CO_SERVICO_ESPECIALIZADO': 'service_specialty_code',
            'DS_CLASSIFICACAO_SERVICO': 'classification_name'
        })
        
        df = df[['classification_id', 'service_specialty_code', 'classification_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.service_classifications"))
                conn.commit()
        
        df.to_sql('service_classifications', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} service classifications")
        return len(df)

    def _build_unit_type_name_map(self) -> Dict[str, str]:
        """Map unit_type_code -> name from tbTipoUnidade."""
        csv_file = self.csv_dir / f"tbTipoUnidade{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            return {}
        df = df.rename(columns={
            'CO_TIPO_UNIDADE': 'unit_type_code',
            'DS_TIPO_UNIDADE': 'unit_type_name',
        })
        df['unit_type_code'] = df['unit_type_code'].astype(str).str.strip()
        return dict(zip(df['unit_type_code'], df['unit_type_name']))

    def _build_unit_subtype_name_map(self) -> Dict[str, str]:
        """Map facility_id -> subtype name via rlEstabSubTipo + tbSubTipo."""
        subtypes_file = self.csv_dir / f"tbSubTipo{self.cnes_version}.csv"
        rel_file = self.csv_dir / f"rlEstabSubTipo{self.cnes_version}.csv"
        sub_df, _ = self.read_csv_with_encoding(subtypes_file)
        rel_df, _ = self.read_csv_with_encoding(rel_file)
        if sub_df is None or rel_df is None:
            return {}
        sub_df = sub_df.rename(columns={
            'CO_TIPO_UNIDADE': 'unit_type_code',
            'CO_SUB_TIPO': 'subtype_code',
            'DS_SUB_TIPO': 'subtype_name',
        })
        for col in ('unit_type_code', 'subtype_code', 'subtype_name'):
            sub_df[col] = sub_df[col].astype(str).str.strip()
        sub_lookup = sub_df.set_index(['unit_type_code', 'subtype_code'])['subtype_name'].to_dict()

        rel_df = rel_df.rename(columns={
            'CO_UNIDADE': 'facility_id',
            'CO_TIPO_UNIDADE': 'unit_type_code',
            'CO_SUB_TIPO_UNIDADE': 'subtype_code',
        })
        for col in ('facility_id', 'unit_type_code', 'subtype_code'):
            rel_df[col] = rel_df[col].astype(str).str.strip()
        rel_df = rel_df.drop_duplicates(subset=['facility_id'], keep='last')

        result: Dict[str, str] = {}
        for _, row in rel_df.iterrows():
            name = sub_lookup.get((row['unit_type_code'], row['subtype_code']))
            if name:
                result[row['facility_id']] = name
        return result

    def import_agreement_types(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('agreement_types'):
            logger.info("✓ agreement_types already populated (use --force to reimport)")
            return 0
        logger.info("Importing agreement types...")
        csv_file = self.csv_dir / f"tbConvenio{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={'CO_CONVENIO': 'agreement_code', 'DS_CONVENIO': 'agreement_name'})
        df = df[['agreement_code', 'agreement_name']]
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.agreement_types"))
                conn.commit()
        df.to_sql('agreement_types', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} agreement types")
        return len(df)

    def import_care_types(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('care_types'):
            logger.info("✓ care_types already populated (use --force to reimport)")
            return 0
        logger.info("Importing care types...")
        csv_file = self.csv_dir / f"tbAtendimentoPrestado{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={
            'CO_ATENDIMENTO_PRESTADO': 'care_type_code',
            'DS_ATENDIMENTO_PRESTADO': 'care_type_name',
        })
        df = df[['care_type_code', 'care_type_name']]
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.care_types"))
                conn.commit()
        df.to_sql('care_types', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} care types")
        return len(df)

    def import_occupations(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('occupations'):
            logger.info("✓ occupations already populated (use --force to reimport)")
            return 0
        logger.info("Importing occupations (CBO)...")
        csv_file = self.csv_dir / f"tbAtividadeProfissional{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={
            'CO_CBO': 'occupation_code',
            'DS_ATIVIDADE_PROFISSIONAL': 'occupation_name',
            'TP_CLASSIFICACAO_PROFISSIONAL': 'professional_classification',
            'TP_CBO_SAUDE': 'is_health_occupation',
            'ST_CBO_REGULAMENTADO': 'is_regulated',
            'NO_ANO_CMPT': 'reference_year',
        })
        for col in ('occupation_code', 'occupation_name', 'professional_classification',
                    'is_health_occupation', 'is_regulated', 'reference_year'):
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df.loc[df[col] == '', col] = None
        df = df[['occupation_code', 'occupation_name', 'professional_classification',
                 'is_health_occupation', 'is_regulated', 'reference_year']]
        df = df.drop_duplicates(subset=['occupation_code'], keep='last')
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.occupations"))
                conn.commit()
        df.to_sql('occupations', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} occupations")
        return len(df)

    def import_installation_subtypes(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('installation_subtypes'):
            logger.info("✓ installation_subtypes already populated (use --force to reimport)")
            return 0
        logger.info("Importing installation subtypes...")
        csv_file = self.csv_dir / f"tbSubtipoInstalacao{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={
            'CO_SUBTIPO_INSTALACAO': 'installation_subtype_code',
            'DS_SUBTIPO_INSTALACAO': 'installation_subtype_name',
        })
        df = df[['installation_subtype_code', 'installation_subtype_name']]
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.installation_subtypes"))
                conn.commit()
        df.to_sql('installation_subtypes', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} installation subtypes")
        return len(df)

    def import_physical_installation_types(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('physical_installation_types'):
            logger.info("✓ physical_installation_types already populated (use --force to reimport)")
            return 0
        logger.info("Importing physical installation types...")
        csv_file = self.csv_dir / f"tbTipoInstalacaoFisica{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={
            'CO_TIPO_INSTALACAO_FISICA': 'installation_type_code',
            'DS_TIPO_INSTALACAO_FISICA': 'installation_type_name',
        })
        df = df[['installation_type_code', 'installation_type_name']]
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.physical_installation_types"))
                conn.commit()
        df.to_sql('physical_installation_types', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} physical installation types")
        return len(df)

    def import_physical_installations(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('physical_installations'):
            logger.info("✓ physical_installations already populated (use --force to reimport)")
            return 0
        logger.info("Importing physical installations catalog...")
        csv_file = self.csv_dir / f"tbInstalFisicaParaAssist{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        df = df.rename(columns={
            'CO_INSTALACAO': 'installation_code',
            'CO_SUBTIPO_INSTALACAO': 'installation_subtype_code',
            'DS_INSTALACAO': 'installation_name',
            'TP_INSTALACAO': 'installation_type_code',
        })
        df = df[['installation_code', 'installation_subtype_code', 'installation_name', 'installation_type_code']]
        with self.engine.connect() as conn:
            valid_subtypes = {r[0] for r in conn.execute(text(f"SELECT installation_subtype_code FROM {self.schema}.installation_subtypes"))}
            valid_types = {r[0] for r in conn.execute(text(f"SELECT installation_type_code FROM {self.schema}.physical_installation_types"))}
        if 'installation_subtype_code' in df.columns:
            df.loc[~df['installation_subtype_code'].isin(valid_subtypes), 'installation_subtype_code'] = None
        if 'installation_type_code' in df.columns:
            df.loc[~df['installation_type_code'].isin(valid_types), 'installation_type_code'] = None
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.physical_installations"))
                conn.commit()
        df.to_sql('physical_installations', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} physical installations")
        return len(df)

    def import_maintainers(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('maintainers'):
            logger.info("✓ maintainers already populated (use --force to reimport)")
            return 0
        logger.info("Importing maintainers (mantenedora)...")
        csv_file = self.csv_dir / f"tbMantenedora{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        column_mapping = {
            'NU_CNPJ_MANTENEDORA': 'tax_id',
            'CO_BANCO': 'bank_code',
            'NU_AGENCIA': 'branch_number',
            'NU_CONTA_CORRENTE': 'account_number',
            'NO_RAZAO_SOCIAL': 'legal_name',
            'NO_LOGRADOURO': 'street_address',
            'NU_ENDERECO': 'street_number',
            'NO_COMPLEMENTO': 'address_complement',
            'NO_BAIRRO': 'neighborhood',
            'CO_CEP': 'postal_code',
            'CO_MUNICIPIO': 'municipality_id',
            'CO_REGIAO_SAUDE': 'health_region_id',
            'NU_TELEFONE': 'phone_number',
            "TO_CHAR(DT_PREENCHIMENTO,'DD/MM/YYYY')": 'form_filled_date',
            'ST_FMS_FES': 'fms_fes_status',
            'NU_CNPJ_FMS_FES': 'fms_fes_tax_id',
            'CO_NATUREZA_JUR': 'legal_entity_type_code',
            "TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')": 'last_updated_date',
            'CO_USUARIO': 'updated_by_user',
            'CO_GESTOR': 'manager_code',
            'CO_MUNICIPIO_MANT': 'manager_municipality_id',
            "TO_CHAR(DT_ATUALIZACAO_ORIGEM,'DD/MM/YYYY')": 'origin_updated_date',
        }
        df = df.rename(columns=column_mapping)
        for date_col in ('form_filled_date', 'last_updated_date', 'origin_updated_date'):
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.maintainers"))
                conn.commit()
        df.to_sql('maintainers', self.engine, schema=self.schema, if_exists='append', index=False, method='multi')
        logger.info(f"✅ Imported {len(df)} maintainers")
        return len(df)

    def enrich_facilities(self, force: bool = False) -> int:
        """Update unit_type_name and unit_subtype_name on existing facilities rows."""
        logger.info("=" * 80)
        logger.info("Enriching facilities with unit type/subtype names...")
        unit_type_map = self._build_unit_type_name_map()
        subtype_map = self._build_unit_subtype_name_map()
        if not unit_type_map:
            logger.warning("No unit type map loaded; skipping enrichment")
            return 0

        with self.engine.connect() as conn:
            facilities = pd.read_sql(
                text(f"SELECT facility_id, unit_type_code FROM {self.schema}.facilities"),
                conn,
            )
        facilities['unit_type_code'] = facilities['unit_type_code'].astype(str).str.strip()
        facilities['unit_type_name'] = facilities['unit_type_code'].map(unit_type_map)
        facilities['unit_subtype_name'] = facilities['facility_id'].map(subtype_map)

        orphan_codes = facilities['unit_type_name'].isna() & facilities['unit_type_code'].notna() & (facilities['unit_type_code'] != '')
        if orphan_codes.any():
            logger.warning(f"  {orphan_codes.sum()} facilities with unknown unit_type_code")

        tmp_table = 'facilities_unit_enrich_tmp'
        with self.engine.begin() as conn:
            facilities[['facility_id', 'unit_type_name', 'unit_subtype_name']].to_sql(
                tmp_table, conn, schema=self.schema, if_exists='replace', index=False, method='multi',
            )
            result = conn.execute(text(f"""
                UPDATE {self.schema}.facilities f
                SET unit_type_name = t.unit_type_name,
                    unit_subtype_name = t.unit_subtype_name
                FROM {self.schema}.{tmp_table} t
                WHERE f.facility_id = t.facility_id
            """))
            conn.execute(text(f"DROP TABLE {self.schema}.{tmp_table}"))
            updated = result.rowcount
        logger.info(f"✅ Enriched {updated:,} facilities ({len(subtype_map):,} with subtype names)")
        return updated
    
    def import_facilities(self, force: bool = False) -> int:
        """Import facilities table (large - uses batching)"""
        if not force and self.table_exists_and_has_data('facilities'):
            logger.info("✓ facilities already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing facilities (this may take a while)...")
        
        csv_file = self.csv_dir / f"tbEstabelecimento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Municipality column name varies by CNES export version
        if 'CO_MUNICIPIO_GESTOR' in df.columns:
            df = df.rename(columns={'CO_MUNICIPIO_GESTOR': 'municipality_id'})
        elif 'CO_MUNICIPIO' in df.columns:
            df = df.rename(columns={'CO_MUNICIPIO': 'municipality_id'})
        
        if force:
            with self.engine.connect() as conn:
                # Child tables must be cleared before facilities (FK constraints)
                for child_table in ('professional_workload', 'facility_representatives',
                                    'facility_physical_installations',
                                    'facility_agreements', 'facility_equipment',
                                    'facility_services', 'facility_professionals'):
                    conn.execute(text(f"DELETE FROM {self.schema}.{child_table}"))
                conn.execute(text(f"DELETE FROM {self.schema}.facilities"))
                conn.commit()

        unit_type_map = self._build_unit_type_name_map()
        subtype_map = self._build_unit_subtype_name_map()
        
        # Map columns (CNES 202605 uses CO_MUNICIPIO_GESTOR for facility municipality)
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_CNES': 'cnes_code',
            'NO_RAZAO_SOCIAL': 'legal_name',
            'NO_FANTASIA': 'trade_name',
            'NO_LOGRADOURO': 'street_address',
            'NU_ENDERECO': 'street_number',
            'NO_COMPLEMENTO': 'address_complement',
            'NO_BAIRRO': 'neighborhood',
            'CO_CEP': 'postal_code',
            'CO_REGIAO_SAUDE': 'health_region_id',
            'NU_TELEFONE': 'phone_number',
            'NU_FAX': 'fax_number',
            'NO_EMAIL': 'email',
            'NO_URL': 'website_url',
            'NU_LATITUDE': 'latitude',
            'NU_LONGITUDE': 'longitude',
            'NU_CNPJ': 'tax_id_cnpj',
            'NU_CPF': 'tax_id_cpf',
            'NU_CNPJ_MANTENEDORA': 'owner_tax_id',
            'CO_NATUREZA_JUR': 'legal_entity_type_code',
            'TP_PFPJ': 'entity_type',
            'CO_TIPO_ESTABELECIMENTO': 'facility_type_code',
            'CO_ATIVIDADE': 'primary_activity_code',
            'TP_UNIDADE': 'unit_type_code',
            'CO_TURNO_ATENDIMENTO': 'operating_hours_code',
            'CO_MOTIVO_DESAB': 'deactivation_reason_code',
            'TP_ESTAB_SEMPRE_ABERTO': 'is_24_7',
            'ST_ADESAO_FILANTROP': 'is_philanthropic',
            'ST_CONEXAO_INTERNET': 'has_internet',
            'ST_CONTRATO_FORMALIZADO': 'has_formal_contract',
            'DT_EXPEDICAO': 'license_issue_date',
            'DT_VAL_LIC_SANI': 'sanitary_license_expiry',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Convert boolean fields to integers (schema uses INTEGER, not BOOLEAN)
        for bool_col in ['is_24_7', 'is_philanthropic', 'has_internet', 'has_formal_contract']:
            if bool_col in df.columns:
                df[bool_col] = self._map_to_int_flag(df[bool_col])
        
        # Convert numeric fields
        for num_col in ['latitude', 'longitude']:
            if num_col in df.columns:
                df[num_col] = pd.to_numeric(df[num_col], errors='coerce')
        
        # Convert date fields from DD/MM/YYYY format
        for date_col in ['license_issue_date', 'sanitary_license_expiry', 'last_updated_date']:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        
        # Select available columns (municipality_id mapped separately above)
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        if 'municipality_id' in df.columns:
            available_columns.append('municipality_id')
        df = df[available_columns]

        if 'unit_type_code' in df.columns:
            df['unit_type_code'] = df['unit_type_code'].astype(str).str.strip()
            df['unit_type_name'] = df['unit_type_code'].map(unit_type_map)
        if 'facility_id' in df.columns:
            df['unit_subtype_name'] = df['facility_id'].map(subtype_map)
        
        # Null out orphan FK references so batches don't fail entirely
        with self.engine.connect() as conn:
            valid_municipalities = {r[0] for r in conn.execute(text(f"SELECT municipality_id FROM {self.schema}.municipalities"))}
            maintainer_table = 'maintainers' if self.table_exists_and_has_data('maintainers') else None
            valid_owners = set()
            if maintainer_table:
                valid_owners = {r[0] for r in conn.execute(text(f"SELECT tax_id FROM {self.schema}.maintainers"))}
            valid_types = {r[0] for r in conn.execute(text(f"SELECT facility_type_code FROM {self.schema}.facility_types"))}
            valid_deactivation = {r[0] for r in conn.execute(text(f"SELECT deactivation_code FROM {self.schema}.deactivation_reasons"))}
        if 'municipality_id' in df.columns:
            df.loc[~df['municipality_id'].isin(valid_municipalities), 'municipality_id'] = None
        if 'owner_tax_id' in df.columns:
            if valid_owners:
                df.loc[~df['owner_tax_id'].isin(valid_owners), 'owner_tax_id'] = None
        if 'facility_type_code' in df.columns:
            df.loc[~df['facility_type_code'].isin(valid_types), 'facility_type_code'] = None
        if 'deactivation_reason_code' in df.columns:
            df.loc[~df['deactivation_reason_code'].isin(valid_deactivation), 'deactivation_reason_code'] = None
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facilities.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} facilities in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facilities") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facilities', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} facilities ({total_rows - imported:,} failed)")
        return imported
    
    def import_professionals(self, force: bool = False) -> int:
        """Import professionals table (VERY large - uses batching)"""
        if not force and self.table_exists_and_has_data('professionals'):
            logger.info("✓ professionals already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing professionals (this will take several minutes)...")
        
        csv_file = self.csv_dir / f"tbDadosProfissionalSus{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        column_mapping = {
            'CO_PROFISSIONAL_SUS': 'professional_id',
            'NO_PROFISSIONAL': 'full_name',
            'NO_SOCIAL': 'social_name',
            'CO_CPF': 'tax_id',
            'CO_CNS': 'health_card_number',
            'CO_NACIONALIDADE': 'nationality_code',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        # Filter out professionals without names (required field)
        if 'full_name' in df.columns:
            initial_count = len(df)
            df = df[df['full_name'].notna() & (df['full_name'] != '')]
            filtered_count = initial_count - len(df)
            if filtered_count > 0:
                logger.info(f"  Filtered out {filtered_count:,} professionals without names")
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.professionals"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'professionals.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} professionals in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Professionals") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'professionals', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} professionals ({total_rows - imported:,} failed)")
        return imported
    
    def import_facility_professionals(self, force: bool = False) -> int:
        """Import facility-professional relationships"""
        if not force and self.table_exists_and_has_data('facility_professionals'):
            logger.info("✓ facility_professionals already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing facility-professional relationships...")
        
        csv_file = self.csv_dir / f"rlEstabEquipeProf{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_PROFISSIONAL_SUS': 'professional_id',
            'CO_CBO': 'occupation_code',
            'CO_MUNICIPIO': 'municipality_id',
            'CO_AREA': 'service_area_id',
            'SEQ_EQUIPE': 'team_sequence_number',
            'TP_SUS_NAO_SUS': 'service_type',
            'IND_VINCULACAO': 'employment_type_code',
            'DT_ENTRADA': 'start_date',
            'DT_DESLIGAMENTO': 'termination_date',
            'CO_MICROAREA': 'micro_area_code',
            'CO_CNES_OUTRAEQUIPE': 'other_team_cnes',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Convert integers
        if 'team_sequence_number' in df.columns:
            df['team_sequence_number'] = pd.to_numeric(df['team_sequence_number'], errors='coerce').astype('Int64')
        
        # Convert date fields
        for date_col in ['start_date', 'termination_date', 'last_updated_date']:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        # Remove duplicates based on primary key (facility_id, professional_id, occupation_code)
        # Keep the last occurrence (most recent update)
        initial_count = len(df)
        df = df.drop_duplicates(subset=['facility_id', 'professional_id', 'occupation_code'], keep='last')
        dup_count = initial_count - len(df)
        if dup_count > 0:
            logger.info(f"  Removed {dup_count:,} duplicate facility-professional records")
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_professionals"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_professionals.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility-Professionals") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_professionals', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} facility-professional relationships ({total_rows - imported:,} failed)")
        return imported
    
    def import_facility_services(self, force: bool = False) -> int:
        """Import facility services"""
        if not force and self.table_exists_and_has_data('facility_services'):
            logger.info("✓ facility_services already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing facility services...")
        
        csv_file = self.csv_dir / f"rlEstabServClass{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_SERVICO': 'service_code',
            'CO_CLASSIFICACAO': 'classification_code',
            'TP_CARACTERISTICA': 'characteristic_type',
            'CO_CNPJCPF': 'owner_tax_id',
            'CO_END_COMPL': 'address_complement',
            'CO_AMBULATORIAL': 'ambulatory_capacity',
            'CO_AMBULATORIAL_SUS': 'ambulatory_capacity_sus',
            'CO_HOSPITALAR': 'hospital_capacity',
            'CO_HOSPITALAR_SUS': 'hospital_capacity_sus',
            'ST_ATIVO_SN': 'is_active',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # PK columns must not be null
        for pk_col in ['classification_code', 'characteristic_type', 'owner_tax_id', 'address_complement']:
            if pk_col in df.columns:
                df[pk_col] = df[pk_col].fillna('').astype(str).str.strip()
                df[pk_col] = df[pk_col].replace('', 'NAO INFORMADO')
        
        # Convert booleans
        if 'is_active' in df.columns:
            df['is_active'] = self._map_to_int_flag(df['is_active'])
        
        # Convert integers
        for int_col in ['ambulatory_capacity', 'ambulatory_capacity_sus', 'hospital_capacity', 'hospital_capacity_sus']:
            if int_col in df.columns:
                df[int_col] = pd.to_numeric(df[int_col], errors='coerce').astype('Int64')
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_services"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_services.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility Services") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_services', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} facility services ({total_rows - imported:,} failed)")
        return imported
    
    def import_facility_equipment(self, force: bool = False) -> int:
        """Import facility equipment"""
        if not force and self.table_exists_and_has_data('facility_equipment'):
            logger.info("✓ facility_equipment already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing facility equipment...")
        
        csv_file = self.csv_dir / f"rlEstabEquipamento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_EQUIPAMENTO': 'equipment_code',
            'CO_TIPO_EQUIPAMENTO': 'equipment_category_code',
            'QT_EXISTENTE': 'quantity',
            'QT_USO': 'operational_status',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        if 'equipment_category_code' in df.columns:
            df['equipment_category_code'] = df['equipment_category_code'].astype(str).str.strip()
        
        # Convert integers
        if 'quantity' in df.columns:
            df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').astype('Int64')
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        # Drop rows with orphan FK references (category_code is NOT NULL PK)
        with self.engine.connect() as conn:
            valid_facilities = {r[0] for r in conn.execute(text(f"SELECT facility_id FROM {self.schema}.facilities"))}
            valid_categories = {str(r[0]).strip() for r in conn.execute(text(f"SELECT category_code FROM {self.schema}.equipment_categories"))}
        initial_count = len(df)
        if 'facility_id' in df.columns:
            df = df[df['facility_id'].isin(valid_facilities)]
        if 'equipment_category_code' in df.columns:
            df = df[df['equipment_category_code'].isin(valid_categories)]
        filtered = initial_count - len(df)
        if filtered > 0:
            logger.info(f"  Filtered out {filtered:,} equipment records with orphan FK references")
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_equipment"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_equipment.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility Equipment") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_equipment', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} equipment records ({total_rows - imported:,} failed)")
        return imported
    
    def import_professional_workload(self, force: bool = False) -> int:
        """Import professional workload"""
        if not force and self.table_exists_and_has_data('professional_workload'):
            logger.info("✓ professional_workload already populated (use --force to reimport)")
            return 0
        
        logger.info("=" * 80)
        logger.info("Importing professional workload...")
        
        csv_file = self.csv_dir / f"tbCargaHorariaSus{self.cnes_version}.csv"
        
        if not csv_file.exists():
            logger.warning(f"File not found: {csv_file}, skipping")
            return 0
        
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            logger.warning(f"Failed to read {csv_file}")
            return 0
        
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_PROFISSIONAL_SUS': 'professional_id',
            'CO_CBO': 'occupation_code',
            'QT_CARGA_HORARIA_AMBULATORIAL': 'weekly_hours_ambulatory',
            'TP_SUS_NAO_SUS': 'service_type',
            'IND_VINCULACAO': 'employment_type_code',
            'CO_CONSELHO_CLASSE': 'professional_council_code',
            'NU_REGISTRO': 'license_number',
            'SG_UF_CRM': 'license_state',
            'TP_PRECEPTOR': 'is_preceptor',
            'TP_RESIDENTE': 'is_resident',
            'TO_CHAR(A.DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # service_type is part of the composite PK (SUS vs non-SUS are separate workload rows)
        if 'service_type' in df.columns:
            df['service_type'] = df['service_type'].astype(str).str.strip().str.upper()
            df.loc[df['service_type'] == '', 'service_type'] = 'N'
        
        # Council codes use CNES regional CRM codes (60-83) not in tbConselhoClasse — store as-is, no FK
        if 'professional_council_code' in df.columns:
            df['professional_council_code'] = df['professional_council_code'].astype(str).str.strip()
            df.loc[df['professional_council_code'].isin(['', 'nan', 'None', 'NULL']), 'professional_council_code'] = None
            numeric_mask = df['professional_council_code'].notna() & df['professional_council_code'].str.match(r'^\d+$')
            df.loc[numeric_mask, 'professional_council_code'] = df.loc[numeric_mask, 'professional_council_code'].str.zfill(2)
        
        # Convert integers
        if 'weekly_hours_ambulatory' in df.columns:
            df['weekly_hours_ambulatory'] = pd.to_numeric(df['weekly_hours_ambulatory'], errors='coerce').astype('Int64')
        
        # Convert booleans
        for bool_col in ['is_preceptor', 'is_resident']:
            if bool_col in df.columns:
                df[bool_col] = self._map_to_int_flag(df[bool_col])
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        if 'employment_type_code' in df.columns:
            df['employment_type_code'] = df['employment_type_code'].fillna('000000').astype(str).str.strip()
            df.loc[df['employment_type_code'] == '', 'employment_type_code'] = '000000'
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.professional_workload"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'professional_workload.log'
        if force and error_log.exists():
            error_log.unlink()
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Professional Workload") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'professional_workload', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {imported:,} workload records ({total_rows - imported:,} failed)")
        return imported

    def import_facility_agreements(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('facility_agreements'):
            logger.info("✓ facility_agreements already populated (use --force to reimport)")
            return 0
        logger.info("=" * 80)
        logger.info("Importing facility agreements...")
        csv_file = self.csv_dir / f"rlEstabAtendPrestConv{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_ATENDIMENTO_PRESTADO': 'care_type_code',
            'CO_CONVENIO': 'agreement_code',
            'CO_USUARIO': 'updated_by_user',
            "TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')": 'last_updated_date',
            "TO_CHAR(DT_ATUALIZACAO_ORIGEM,'DD/MM/YYYY')": 'origin_updated_date',
        }
        df = df.rename(columns=column_mapping)
        for date_col in ('last_updated_date', 'origin_updated_date'):
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        with self.engine.connect() as conn:
            valid_facilities = {r[0] for r in conn.execute(text(f"SELECT facility_id FROM {self.schema}.facilities"))}
            valid_care = {r[0] for r in conn.execute(text(f"SELECT care_type_code FROM {self.schema}.care_types"))}
            valid_agreements = {r[0] for r in conn.execute(text(f"SELECT agreement_code FROM {self.schema}.agreement_types"))}
        initial = len(df)
        df = df[df['facility_id'].isin(valid_facilities) & df['care_type_code'].isin(valid_care) & df['agreement_code'].isin(valid_agreements)]
        if initial - len(df) > 0:
            logger.info(f"  Filtered out {initial - len(df):,} agreement rows with orphan FK references")
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_agreements"))
                conn.commit()
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_agreements.log'
        if force and error_log.exists():
            error_log.unlink()
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility Agreements") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_agreements', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        logger.info(f"✅ Imported {imported:,} facility agreements ({total_rows - imported:,} failed)")
        return imported

    def import_facility_physical_installations(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('facility_physical_installations'):
            logger.info("✓ facility_physical_installations already populated (use --force to reimport)")
            return 0
        logger.info("=" * 80)
        logger.info("Importing facility physical installations...")
        csv_file = self.csv_dir / f"rlEstabInstFisiAssist{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_INSTALACAO': 'installation_code',
            'QT_INSTALACAO': 'quantity',
            'NU_LEITOS': 'bed_count',
            "TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')": 'last_updated_date',
            'CO_USUARIO': 'updated_by_user',
            "TO_CHAR(DT_ATUALIZACAO_ORIGEM,'DD/MM/YYYY')": 'origin_updated_date',
        }
        df = df.rename(columns=column_mapping)
        for int_col in ('quantity', 'bed_count'):
            if int_col in df.columns:
                df[int_col] = pd.to_numeric(df[int_col], errors='coerce').astype('Int64')
        for date_col in ('last_updated_date', 'origin_updated_date'):
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        df = df.drop_duplicates(subset=['facility_id', 'installation_code'], keep='last')
        with self.engine.connect() as conn:
            valid_facilities = {r[0] for r in conn.execute(text(f"SELECT facility_id FROM {self.schema}.facilities"))}
            valid_installations = {r[0] for r in conn.execute(text(f"SELECT installation_code FROM {self.schema}.physical_installations"))}
        initial = len(df)
        df = df[df['facility_id'].isin(valid_facilities) & df['installation_code'].isin(valid_installations)]
        if initial - len(df) > 0:
            logger.info(f"  Filtered out {initial - len(df):,} installation rows with orphan FK references")
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_physical_installations"))
                conn.commit()
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_physical_installations.log'
        if force and error_log.exists():
            error_log.unlink()
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility Installations") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_physical_installations', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        logger.info(f"✅ Imported {imported:,} facility physical installations ({total_rows - imported:,} failed)")
        return imported

    def import_facility_representatives(self, force: bool = False) -> int:
        if not force and self.table_exists_and_has_data('facility_representatives'):
            logger.info("✓ facility_representatives already populated (use --force to reimport)")
            return 0
        logger.info("=" * 80)
        logger.info("Importing facility representatives...")
        csv_file = self.csv_dir / f"rlEstabRepresentante{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        column_mapping = {
            'CO_UNIDADE': 'facility_id',
            'CO_CPF': 'tax_id',
            'NO_REPRESENTANTE': 'representative_name',
            'DS_CARGO': 'role_title',
            'DS_E_MAIL': 'email',
            'CO_USUARIO': 'updated_by_user',
            "TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')": 'last_updated_date',
            "TO_CHAR(DT_ATUALIZACAO_ORIGEM,'DD/MM/YYYY')": 'origin_updated_date',
        }
        df = df.rename(columns=column_mapping)
        if 'tax_id' in df.columns:
            df['tax_id'] = df['tax_id'].replace({'CO_CPF': None, '': None})
        for text_col in ('representative_name', 'role_title', 'email', 'updated_by_user'):
            if text_col in df.columns:
                df[text_col] = df[text_col].replace({'': None}).str.strip()
        for date_col in ('last_updated_date', 'origin_updated_date'):
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        df = df.dropna(subset=['facility_id', 'representative_name'])
        df = df.drop_duplicates(subset=['facility_id'], keep='last')
        with self.engine.connect() as conn:
            valid_facilities = {r[0] for r in conn.execute(text(f"SELECT facility_id FROM {self.schema}.facilities"))}
        initial = len(df)
        df = df[df['facility_id'].isin(valid_facilities)]
        if initial - len(df) > 0:
            logger.info(f"  Filtered out {initial - len(df):,} representative rows with orphan facility_id")
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM {self.schema}.facility_representatives"))
                conn.commit()
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        error_log = ERROR_LOG_DIR / 'facility_representatives.log'
        if force and error_log.exists():
            error_log.unlink()
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        imported = 0
        with tqdm(total=total_rows, desc="Facility Representatives") as pbar:
            for batch_num, start_idx in enumerate(batches):
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                imported += self.import_batch_with_error_handling(
                    'facility_representatives', batch, batch_num, error_log
                )
                pbar.update(len(batch))
        logger.info(f"✅ Imported {imported:,} facility representatives ({total_rows - imported:,} failed)")
        return imported
    
    def import_all(self, force: bool = False) -> None:
        """Import all tables in the correct order"""
        logger.info("=" * 80)
        logger.info("IMPORTING ALL TABLES")
        logger.info("=" * 80)
        
        stats = {}
        start_time = datetime.now()
        
        import_steps = [
            ('states', self.import_states),
            ('municipalities', self.import_municipalities),
            ('facility_types', self.import_facility_types),
            ('deactivation_reasons', self.import_deactivation_reasons),
            ('service_specialties', self.import_service_specialties),
            ('equipment_catalog', self.import_equipment_catalog),
            ('professional_councils', self.import_professional_councils),
            ('equipment_categories', self.import_equipment_categories),
            ('service_classifications', self.import_service_classifications),
            ('agreement_types', self.import_agreement_types),
            ('care_types', self.import_care_types),
            ('occupations', self.import_occupations),
            ('installation_subtypes', self.import_installation_subtypes),
            ('physical_installation_types', self.import_physical_installation_types),
            ('physical_installations', self.import_physical_installations),
            ('maintainers', self.import_maintainers),
            ('facilities', self.import_facilities),
            ('enrich_facilities', self.enrich_facilities),
            ('professionals', self.import_professionals),
            ('facility_professionals', self.import_facility_professionals),
            ('facility_services', self.import_facility_services),
            ('facility_equipment', self.import_facility_equipment),
            ('facility_agreements', self.import_facility_agreements),
            ('facility_physical_installations', self.import_facility_physical_installations),
            ('facility_representatives', self.import_facility_representatives),
            ('professional_workload', self.import_professional_workload),
        ]
        
        for table_name, import_fn in import_steps:
            try:
                stats[table_name] = import_fn(force)
            except Exception as e:
                logger.error(f"Import failed for {table_name}: {e}", exc_info=True)
                stats[table_name] = -1
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("=" * 80)
        logger.info("✅ IMPORT COMPLETED!")
        logger.info("=" * 80)
        logger.info(f"Total time: {duration}")
        logger.info("\nRecords imported:")
        for table, count in stats.items():
            logger.info(f"  {table:30s}: {count:>10,d}")


def main():
    parser = argparse.ArgumentParser(description='Modular CNES data importer (PostgreSQL)')
    parser.add_argument('--csv-dir', default='../BASE_DE_DADOS_CNES_202605', help='CSV directory')
    parser.add_argument(
        '--db-url',
        default=os.environ.get('DATABASE_URL', 'postgresql://localhost:5432/atlasmed_test'),
        help='Database URL (or set DATABASE_URL env var)',
    )
    parser.add_argument('--schema', default='mcp_test', help='PostgreSQL schema (default: mcp_test)')
    parser.add_argument('--cnes-version', default='202605', help='CNES version')
    parser.add_argument('--table', required=True, help='Table to import (or "all")')
    parser.add_argument('--force', action='store_true', help='Force reimport even if table has data')
    
    args = parser.parse_args()
    
    importer = ModularCNESImporter(
        csv_dir=args.csv_dir,
        db_url=args.db_url,
        cnes_version=args.cnes_version,
        schema=args.schema
    )
    
    table_methods = {
        'states': importer.import_states,
        'municipalities': importer.import_municipalities,
        'facility_types': importer.import_facility_types,
        'deactivation_reasons': importer.import_deactivation_reasons,
        'service_specialties': importer.import_service_specialties,
        'equipment_catalog': importer.import_equipment_catalog,
        'professional_councils': importer.import_professional_councils,
        'equipment_categories': importer.import_equipment_categories,
        'service_classifications': importer.import_service_classifications,
        'agreement_types': importer.import_agreement_types,
        'care_types': importer.import_care_types,
        'occupations': importer.import_occupations,
        'installation_subtypes': importer.import_installation_subtypes,
        'physical_installation_types': importer.import_physical_installation_types,
        'physical_installations': importer.import_physical_installations,
        'maintainers': importer.import_maintainers,
        'facilities': importer.import_facilities,
        'enrich_facilities': importer.enrich_facilities,
        'professionals': importer.import_professionals,
        'facility_professionals': importer.import_facility_professionals,
        'facility_services': importer.import_facility_services,
        'facility_equipment': importer.import_facility_equipment,
        'facility_agreements': importer.import_facility_agreements,
        'facility_physical_installations': importer.import_facility_physical_installations,
        'facility_representatives': importer.import_facility_representatives,
        'professional_workload': importer.import_professional_workload,
        'all': importer.import_all,
    }
    
    if args.table not in table_methods:
        logger.error(f"Unknown table: {args.table}")
        logger.error(f"Available tables: {', '.join(table_methods.keys())}")
        sys.exit(1)
    
    table_methods[args.table](force=args.force)


if __name__ == '__main__':
    main()
