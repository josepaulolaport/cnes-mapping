#!/usr/bin/env python3
"""
CNES Data Import Script - SQLite Version
=========================================

Import CNES CSV data into a SQLite database.

Usage:
    python import_sqlite_full.py --table states
    python import_sqlite_full.py --table all
    python import_sqlite_full.py --table facilities --force
    python import_sqlite_full.py --db ../output/cnes_data.db

Available tables:
    - states, municipalities, facility_types, deactivation_reasons
    - service_specialties, equipment_catalog, professional_councils
    - equipment_categories, service_classifications, facility_owners
    - facilities, professionals, facility_professionals
    - facility_services, facility_equipment, professional_workload
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
LOG_DIR = Path('../logs')
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'import_sqlite_full.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
CNES_ENCODINGS = ['latin1', 'cp1252', 'utf-8-sig']
BATCH_SIZE = 100  # SQLite has a 999 variable limit per statement
ERROR_LOG_DIR = Path('../import_errors_sqlite')

# Create error log directory
ERROR_LOG_DIR.mkdir(exist_ok=True)


class CNESSQLiteImporter:
    """CNES data importer for SQLite"""
    
    def __init__(self, csv_dir: str, db_path: str, cnes_version: str = '202605', row_limit: int = None):
        self.csv_dir = Path(csv_dir)
        self.db_path = Path(db_path)
        self.cnes_version = cnes_version
        self.row_limit = row_limit
        
        # Create database directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create SQLite engine
        self.engine = create_engine(f'sqlite:///{self.db_path}',
                                   connect_args={'check_same_thread': False})
        
        logger.info(f"Initialized for CNES version: {cnes_version}")
        if row_limit:
            logger.info(f"⚠️ ROW LIMIT ACTIVE: {row_limit:,} rows per table (TEST MODE)")
        logger.info(f"CSV directory: {self.csv_dir}")
        logger.info(f"SQLite database: {self.db_path}")
    
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
                        read_params = {
                            'encoding': encoding,
                            'delimiter': delimiter,
                            'dtype': str,
                            'na_values': ['', 'NULL', 'null', 'NA'],
                            'keep_default_na': True
                        }
                        if self.row_limit:
                            read_params['nrows'] = self.row_limit
                        
                        df = pd.read_csv(file_path, **read_params)
                        
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
    
    def import_batch_with_error_handling(self, table_name: str, batch_df: pd.DataFrame, 
                                         batch_num: int, error_log_file: Path) -> int:
        """
        Import a batch with error handling. Returns number of successfully imported records.
        Failed records are logged to error_log_file.
        """
        try:
            batch_df.to_sql(table_name, self.engine, 
                          if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
            return len(batch_df)
        except Exception as e:
            # If batch fails, try row-by-row
            logger.warning(f"Batch {batch_num} failed, trying row-by-row: {str(e)[:100]}")
            success_count = 0
            
            with open(error_log_file, 'a', encoding='utf-8') as f:
                for idx, row in batch_df.iterrows():
                    try:
                        row.to_frame().T.to_sql(table_name, self.engine,
                                                if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
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
        
        df = df[['state_code', 'state_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM states"))
                conn.commit()
        
        df.to_sql('states', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text(f"DELETE FROM municipalities"))
                conn.commit()
        
        df.to_sql('municipalities', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text(f"DELETE FROM facility_types"))
                conn.commit()
        
        df.to_sql('facility_types', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text("DELETE FROM deactivation_reasons"))
                conn.commit()
        
        df.to_sql('deactivation_reasons', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text("DELETE FROM service_specialties"))
                conn.commit()
        
        df.to_sql('service_specialties', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text("DELETE FROM equipment_catalog"))
                conn.commit()
        
        df.to_sql('equipment_catalog', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text("DELETE FROM professional_councils"))
                conn.commit()
        
        df.to_sql('professional_councils', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
        
        df = df[['category_code', 'category_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM equipment_categories"))
                conn.commit()
        
        df.to_sql('equipment_categories', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
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
                conn.execute(text("DELETE FROM service_classifications"))
                conn.commit()
        
        df.to_sql('service_classifications', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
        
        logger.info(f"✅ Imported {len(df)} service classifications")
        return len(df)
    
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
        
        # First, extract and import facility owners
        if 'NU_CNPJ_MANTENEDORA' in df.columns:
            owners_df = df[['NU_CNPJ_MANTENEDORA']].dropna().drop_duplicates()
            owners_df.columns = ['tax_id']
            
            if force or not self.table_exists_and_has_data('facility_owners'):
                if force:
                    with self.engine.connect() as conn:
                        conn.execute(text("DELETE FROM facility_owners"))
                        conn.commit()
                owners_df.to_sql('facility_owners', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                logger.info(f"  ✓ Imported {len(owners_df)} facility owners")
        
        # Map columns
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
            'CO_MUNICIPIO': 'municipality_id',
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
        
        # Convert boolean fields
        for bool_col in ['is_24_7', 'is_philanthropic', 'has_internet', 'has_formal_contract']:
            if bool_col in df.columns:
                df[bool_col] = df[bool_col].map({'1': True, '0': False, 'S': True, 'N': False, 'T': True, 'F': False})
        
        # Convert numeric fields
        for num_col in ['latitude', 'longitude']:
            if num_col in df.columns:
                df[num_col] = pd.to_numeric(df[num_col], errors='coerce')
        
        # Convert date fields from DD/MM/YYYY format
        for date_col in ['license_issue_date', 'sanitary_license_expiry', 'last_updated_date']:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], format='%d/%m/%Y', errors='coerce')
        
        # Select available columns
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM facilities"))
                conn.commit()
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} facilities in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Facilities") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('facilities', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} facilities")
        return total_rows
    
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
                conn.execute(text("DELETE FROM professionals"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} professionals in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Professionals") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('professionals', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} professionals")
        return total_rows
    
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
                conn.execute(text("DELETE FROM facility_professionals"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Facility-Professionals") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('facility_professionals', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} facility-professional relationships")
        return total_rows
    
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
            'CO_AMBULATORIAL': 'ambulatory_capacity',
            'CO_AMBULATORIAL_SUS': 'ambulatory_capacity_sus',
            'CO_HOSPITALAR': 'hospital_capacity',
            'CO_HOSPITALAR_SUS': 'hospital_capacity_sus',
            'ST_ATIVO_SN': 'is_active',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Convert booleans
        if 'is_active' in df.columns:
            df['is_active'] = df['is_active'].map({'1': True, '0': False, 'S': True, 'N': False})
        
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
                conn.execute(text("DELETE FROM facility_services"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Facility Services") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('facility_services', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} facility services")
        return total_rows
    
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
            'QT_EQUIPAMENTO': 'quantity',
            'IND_FUNCIONAMENTO': 'operational_status',
            'TO_CHAR(DT_ATUALIZACAO,\'DD/MM/YYYY\')': 'last_updated_date',
            'CO_USUARIO': 'updated_by_user'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Convert integers
        if 'quantity' in df.columns:
            df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').astype('Int64')
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM facility_equipment"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Facility Equipment") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('facility_equipment', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} equipment records")
        return total_rows
    
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
        
        # Convert integers
        if 'weekly_hours_ambulatory' in df.columns:
            df['weekly_hours_ambulatory'] = pd.to_numeric(df['weekly_hours_ambulatory'], errors='coerce').astype('Int64')
        
        # Convert booleans
        for bool_col in ['is_preceptor', 'is_resident']:
            if bool_col in df.columns:
                df[bool_col] = df[bool_col].map({'1': True, '0': False, 'S': True, 'N': False})
        
        # Convert date fields
        if 'last_updated_date' in df.columns:
            df['last_updated_date'] = pd.to_datetime(df['last_updated_date'], format='%d/%m/%Y', errors='coerce')
        
        available_columns = [col for col in column_mapping.values() if col in df.columns]
        df = df[available_columns]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM professional_workload"))
                conn.commit()
        
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Professional Workload") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('professional_workload', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows:,} workload records")
        return total_rows

    def import_facility_representatives(self, force: bool = False) -> int:
        """Import official facility representatives from rlEstabRepresentante"""
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
            valid_facilities = {r[0] for r in conn.execute(text("SELECT facility_id FROM facilities"))}
        initial = len(df)
        df = df[df['facility_id'].isin(valid_facilities)]
        if initial - len(df) > 0:
            logger.info(f"  Filtered out {initial - len(df):,} representative rows with orphan facility_id")

        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM facility_representatives"))
                conn.commit()

        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        logger.info(f"  Importing {total_rows:,} records in batches of {BATCH_SIZE:,}...")
        with tqdm(total=total_rows, desc="Facility Representatives") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                batch.to_sql('facility_representatives', self.engine, if_exists='append', index=False, method='multi', chunksize=BATCH_SIZE)
                pbar.update(len(batch))

        logger.info(f"✅ Imported {total_rows:,} facility representatives")
        return total_rows
    
    def import_all(self, force: bool = False):
        """Import all tables in the correct order"""
        logger.info("=" * 80)
        logger.info("IMPORTING ALL TABLES")
        logger.info("=" * 80)
        
        stats = {}
        start_time = datetime.now()
        
        try:
            # Import in dependency order
            stats['states'] = self.import_states(force)
            stats['municipalities'] = self.import_municipalities(force)
            stats['facility_types'] = self.import_facility_types(force)
            stats['deactivation_reasons'] = self.import_deactivation_reasons(force)
            stats['service_specialties'] = self.import_service_specialties(force)
            stats['equipment_catalog'] = self.import_equipment_catalog(force)
            stats['professional_councils'] = self.import_professional_councils(force)
            stats['equipment_categories'] = self.import_equipment_categories(force)
            stats['service_classifications'] = self.import_service_classifications(force)
            
            # Large tables (with progress bars)
            stats['facilities'] = self.import_facilities(force)
            stats['professionals'] = self.import_professionals(force)
            stats['facility_professionals'] = self.import_facility_professionals(force)
            stats['facility_services'] = self.import_facility_services(force)
            stats['facility_equipment'] = self.import_facility_equipment(force)
            stats['facility_representatives'] = self.import_facility_representatives(force)
            stats['professional_workload'] = self.import_professional_workload(force)
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            logger.info("=" * 80)
            logger.info("✅ IMPORT COMPLETED!")
            logger.info("=" * 80)
            logger.info(f"Total time: {duration}")
            logger.info("\nRecords imported:")
            for table, count in stats.items():
                logger.info(f"  {table:30s}: {count:>10,d}")
            
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            raise


def main():
    parser = argparse.ArgumentParser(description='CNES SQLite data importer')
    parser.add_argument('--csv-dir', default='../BASE_DE_DADOS_CNES_202605', help='CSV directory')
    parser.add_argument('--db', default='../output/cnes_data.db', help='SQLite database path')
    parser.add_argument('--cnes-version', default='202605', help='CNES version')
    parser.add_argument('--table', required=True, help='Table to import (or "all")')
    parser.add_argument('--force', action='store_true', help='Force reimport even if table has data')
    parser.add_argument('--limit', type=int, default=None, help='Limit rows for testing (e.g., 10000)')
    
    args = parser.parse_args()
    
    importer = CNESSQLiteImporter(
        csv_dir=args.csv_dir,
        db_path=args.db,
        cnes_version=args.cnes_version,
        row_limit=args.limit
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
        'facilities': importer.import_facilities,
        'professionals': importer.import_professionals,
        'facility_professionals': importer.import_facility_professionals,
        'facility_services': importer.import_facility_services,
        'facility_equipment': importer.import_facility_equipment,
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
