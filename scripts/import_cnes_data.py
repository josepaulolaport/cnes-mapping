#!/usr/bin/env python3
"""
CNES Data Import Script for Sales App Database
===============================================

This script imports CNES CSV files into the Sales App database using the
transformed schema with clear English names.

Features:
- Automatic CSV encoding and delimiter detection
- Column name transformation using schema_mapping.json
- Data type conversion (dates, booleans, decimals)
- Batch processing for large tables
- Progress tracking with progress bars
- Comprehensive error handling and logging
- Respects foreign key dependencies
- Creates consolidated reference_data table

Usage:
    python import_cnes_data.py --csv-dir ./csv_files --db-url postgresql://user:pass@localhost/sales_app

Requirements:
    pip install pandas sqlalchemy psycopg2-binary python-dotenv tqdm
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
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_cnes_data.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
CNES_ENCODINGS = ['latin1', 'cp1252', 'utf-8-sig']
BATCH_SIZE = 10000  # Rows per batch for large tables


class CNESDataImporter:
    """Main class to import CNES data into Sales App database"""
    
    def __init__(self, csv_dir: str, db_url: str, cnes_version: str = None):
        """
        Initialize importer
        
        Args:
            csv_dir: Directory containing CNES CSV files
            db_url: Database connection URL
            cnes_version: CNES version (e.g., '202605'), auto-detected if None
        """
        self.csv_dir = Path(csv_dir)
        self.db_url = db_url
        self.cnes_version = cnes_version or self._detect_cnes_version()
        self.engine = create_engine(db_url, pool_pre_ping=True)
        
        # Load schema mapping
        mapping_file = Path(__file__).parent / 'schema_mapping.json'
        with open(mapping_file, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)['schema_mapping']
        
        logger.info(f"Initialized importer for CNES version: {self.cnes_version}")
        logger.info(f"CSV directory: {self.csv_dir}")
        logger.info(f"Database: {db_url.split('@')[-1]}")  # Hide credentials
    
    def _detect_cnes_version(self) -> str:
        """Auto-detect CNES version from CSV filenames"""
        csv_files = list(self.csv_dir.glob("*.csv"))
        if csv_files:
            # Extract version from filename like "tbEstabelecimento202605.csv"
            filename = csv_files[0].name
            import re
            match = re.search(r'(\d{6})', filename)
            if match:
                return match.group(1)
        return "unknown"
    
    def read_csv_with_encoding(self, file_path: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Read CSV with automatic encoding and delimiter detection
        
        Returns:
            Tuple of (DataFrame, encoding_used) or (None, None) if failed
        """
        delimiters = [';', ',', '\t']
        
        for encoding in CNES_ENCODINGS:
            for delimiter in delimiters:
                try:
                    # Try reading a sample
                    df_sample = pd.read_csv(
                        file_path, 
                        encoding=encoding, 
                        delimiter=delimiter,
                        nrows=5
                    )
                    
                    # Check if we got reasonable column separation
                    if len(df_sample.columns) > 1:
                        # Read full file
                        df = pd.read_csv(
                            file_path,
                            encoding=encoding,
                            delimiter=delimiter,
                            dtype=str,  # Read everything as string first
                            na_values=['', 'NULL', 'null', 'NA'],
                            keep_default_na=True
                        )
                        
                        # Clean column names (strip quotes and whitespace)
                        df.columns = df.columns.str.strip().str.strip('"').str.strip("'")
                        
                        # Clean cell values
                        for col in df.columns:
                            if df[col].dtype == 'object':
                                df[col] = df[col].str.strip().str.strip('"').str.strip("'")
                        
                        logger.info(f"Successfully read {file_path.name} ({encoding}, delimiter='{delimiter}'): {len(df)} rows, {len(df.columns)} columns")
                        return df, encoding
                        
                except Exception as e:
                    continue
        
        logger.error(f"Failed to read {file_path.name} with any encoding/delimiter combination")
        return None, None
    
    def transform_column_names(self, df: pd.DataFrame, old_table_name: str) -> pd.DataFrame:
        """Transform CNES column names to new schema names"""
        table_config = self.mapping['tables'].get(old_table_name, {})
        column_map = table_config.get('columns', {})
        
        rename_dict = {
            old_col: col_config['new_name']
            for old_col, col_config in column_map.items()
            if old_col in df.columns
        }
        
        df_renamed = df.rename(columns=rename_dict)
        logger.debug(f"Renamed {len(rename_dict)} columns for {old_table_name}")
        return df_renamed
    
    def convert_data_types(self, df: pd.DataFrame, old_table_name: str) -> pd.DataFrame:
        """Convert data types according to schema"""
        table_config = self.mapping['tables'].get(old_table_name, {})
        
        for old_col, col_config in table_config.get('columns', {}).items():
            new_col = col_config['new_name']
            if new_col not in df.columns:
                continue
            
            col_type = col_config.get('type', '')
            
            try:
                # Convert booleans
                if col_type == 'BOOLEAN':
                    df[new_col] = df[new_col].map({
                        '1': True, '0': False, 'S': True, 'N': False,
                        'T': True, 'F': False, 'true': True, 'false': False
                    })
                
                # Convert dates
                elif col_type == 'DATE' or col_type == 'TIMESTAMP':
                    df[new_col] = pd.to_datetime(df[new_col], errors='coerce')
                
                # Convert decimals
                elif 'DECIMAL' in col_type:
                    df[new_col] = pd.to_numeric(df[new_col], errors='coerce')
                
                # Convert integers
                elif col_type == 'INT' or col_type == 'INTEGER':
                    df[new_col] = pd.to_numeric(df[new_col], errors='coerce').astype('Int64')
            
            except Exception as e:
                logger.warning(f"Failed to convert {new_col} to {col_type}: {e}")
        
        return df
    
    def import_states(self) -> int:
        """Import states table"""
        logger.info("=" * 80)
        logger.info("Importing states...")
        
        csv_file = self.csv_dir / f"tbEstado{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Manual column mapping for states since actual CSV has different columns
        # Actual: CO_UF, CO_SIGLA, NO_DESCRICAO
        # Expected: CO_SIGLA_ESTADO, NO_ESTADO
        column_mapping = {
            'CO_SIGLA': 'state_code',
            'NO_DESCRICAO': 'state_name'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Select only needed columns
        columns = ['state_code', 'state_name']
        df = df[[col for col in columns if col in df.columns]]
        
        # Insert into database
        df.to_sql('states', self.engine, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} states")
        return len(df)
    
    def import_municipalities(self) -> int:
        """Import municipalities table"""
        logger.info("=" * 80)
        logger.info("Importing municipalities...")
        
        csv_file = self.csv_dir / f"tbMunicipio{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Manual column mapping
        column_mapping = {
            'CO_MUNICIPIO': 'municipality_id',
            'NO_MUNICIPIO': 'municipality_name',
            'CO_SIGLA_ESTADO': 'state_code',
            'TP_CADASTRO': 'registration_type',
            'TP_PACTO': 'pact_type',
            'TP_ENVIA': 'data_submission_type'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Filter out invalid state codes (UF, AZ, TE are not real states)
        # Get valid state codes from database
        with self.engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT state_code FROM states"))
            valid_states = {row[0] for row in result}
        
        original_count = len(df)
        df = df[df['state_code'].isin(valid_states)]
        filtered_count = original_count - len(df)
        if filtered_count > 0:
            logger.info(f"  Filtered out {filtered_count} municipalities with invalid state codes")
        
        # Select columns
        columns = ['municipality_id', 'municipality_name', 'state_code', 
                   'registration_type', 'pact_type', 'data_submission_type']
        df = df[[col for col in columns if col in df.columns]]
        
        df.to_sql('municipalities', self.engine, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} municipalities")
        return len(df)
    
    def import_reference_data(self) -> int:
        """
        Import consolidated reference_data table from multiple source tables
        """
        logger.info("=" * 80)
        logger.info("Importing reference data (consolidated from multiple tables)...")
        
        reference_tables = {
            'facility_type': f"tbTipoEstabelecimento{self.cnes_version}.csv",
            'deactivation_reason': f"tbMotivoDesativacao{self.cnes_version}.csv",
            'service_specialty': f"tbServicoEspecializado{self.cnes_version}.csv",
            'equipment_catalog': f"tbEquipamento{self.cnes_version}.csv",
            'professional_council': f"tbConselhoClasse{self.cnes_version}.csv",
            'equipment_category': f"tbTipoEquipamento{self.cnes_version}.csv",
        }
        
        all_refs = []
        
        for ref_type, csv_filename in reference_tables.items():
            csv_file = self.csv_dir / csv_filename
            
            if not csv_file.exists():
                logger.warning(f"File not found: {csv_file}, skipping {ref_type}")
                continue
            
            df, _ = self.read_csv_with_encoding(csv_file)
            
            if df is None:
                logger.warning(f"Failed to read {csv_file}, skipping {ref_type}")
                continue
            
            # Get code and description columns (pattern: CO_*/CD_* and DS_*/NO_*)
            code_cols = [col for col in df.columns if col.startswith('CO_') or col.startswith('CD_')]
            desc_cols = [col for col in df.columns if col.startswith('DS_') or col.startswith('NO_')]
            
            if not code_cols or not desc_cols:
                logger.warning(f"Skipping {ref_type} - couldn't find code/description columns in {csv_filename}")
                continue
                
            code_col = code_cols[0]
            desc_col = desc_cols[0]
            
            # Get all other columns to store as extra_data
            other_cols = [col for col in df.columns if col not in [code_col, desc_col]]
            
            # Create reference data records with extra_data JSON
            ref_records = []
            for idx, row in df.iterrows():
                extra_data = {col: str(row[col]) if pd.notna(row[col]) else None 
                             for col in other_cols}
                
                ref_records.append({
                    'reference_type': ref_type,
                    'code': str(row[code_col]),
                    'description': str(row[desc_col]),
                    'extra_data': json.dumps(extra_data) if extra_data else None,
                    'cnes_version': self.cnes_version,
                    'is_active': True
                })
            
            ref_df = pd.DataFrame(ref_records)
            all_refs.append(ref_df)
            logger.info(f"  - Loaded {len(ref_df)} {ref_type} records")
        
        # Combine all reference data
        if all_refs:
            combined_df = pd.concat(all_refs, ignore_index=True)
            
            # Remove duplicates (keep first occurrence)
            combined_df = combined_df.drop_duplicates(subset=['reference_type', 'code'], keep='first')
            
            combined_df.to_sql('reference_data', self.engine, if_exists='append', index=False, method='multi')
            logger.info(f"✅ Imported {len(combined_df)} reference records")
            return len(combined_df)
        
        return 0
    
    def import_service_classifications(self) -> int:
        """Import service classifications"""
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
        
        df = self.transform_column_names(df, f"tbClassificacaoServico{self.cnes_version}.csv")
        
        columns = ['classification_id', 'service_specialty_code', 'classification_name']
        df = df[[col for col in columns if col in df.columns]]
        
        df.to_sql('service_classifications', self.engine, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} service classifications")
        return len(df)
    
    def import_facility_owners(self, facilities_df: pd.DataFrame) -> int:
        """
        Import facility owners (extracted from facilities data)
        """
        logger.info("=" * 80)
        logger.info("Importing facility owners...")
        
        # Extract unique owner tax IDs from facilities
        if 'owner_tax_id' in facilities_df.columns:
            owners_df = facilities_df[['owner_tax_id']].dropna().drop_duplicates()
            owners_df.columns = ['tax_id']
            
            owners_df.to_sql('facility_owners', self.engine, if_exists='append', index=False, method='multi')
            
            logger.info(f"✅ Imported {len(owners_df)} facility owners")
            return len(owners_df)
        
        return 0
    
    def import_facilities(self) -> int:
        """Import facilities table (large - uses batching)"""
        logger.info("=" * 80)
        logger.info("Importing facilities (this may take a while)...")
        
        csv_file = self.csv_dir / f"tbEstabelecimento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        # Transform column names first
        df = self.transform_column_names(df, f"tbEstabelecimento{self.cnes_version}.csv")
        
        # Import facility owners first
        self.import_facility_owners(df)
        
        # Convert data types
        df = self.convert_data_types(df, f"tbEstabelecimento{self.cnes_version}.csv")
        
        # Select columns that exist in the DataFrame and are in our schema
        available_columns = [
            'facility_id', 'cnes_code', 'legal_name', 'trade_name',
            'street_address', 'street_number', 'address_complement', 'neighborhood',
            'postal_code', 'municipality_id', 'health_region_id',
            'phone_number', 'fax_number', 'email', 'website_url',
            'latitude', 'longitude',
            'tax_id_cnpj', 'tax_id_cpf', 'owner_tax_id',
            'legal_entity_type_code', 'entity_type',
            'facility_type_code', 'primary_activity_code', 'unit_type_code', 'operating_hours_code',
            'deactivation_reason_code',
            'is_24_7', 'is_philanthropic', 'has_internet', 'has_formal_contract',
            'license_issue_date', 'sanitary_license_expiry', 'last_updated_date',
            'updated_by_user'
        ]
        df = df[[col for col in available_columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Facilities") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('facilities', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} facilities")
        return total_rows
    
    def import_professionals(self) -> int:
        """Import professionals table (VERY large - uses batching)"""
        logger.info("=" * 80)
        logger.info("Importing professionals (this will take several minutes)...")
        
        csv_file = self.csv_dir / f"tbDadosProfissionalSus{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = self.transform_column_names(df, f"tbDadosProfissionalSus{self.cnes_version}.csv")
        df = self.convert_data_types(df, f"tbDadosProfissionalSus{self.cnes_version}.csv")
        
        columns = ['professional_id', 'full_name', 'social_name', 'tax_id', 
                   'health_card_number', 'nationality_code', 'last_updated_date', 'updated_by_user']
        df = df[[col for col in columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Professionals") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('professionals', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} professionals")
        return total_rows
    
    def import_facility_professionals(self) -> int:
        """Import facility-professional relationships"""
        logger.info("=" * 80)
        logger.info("Importing facility-professional relationships...")
        
        csv_file = self.csv_dir / f"rlEstabEquipeProf{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = self.transform_column_names(df, f"rlEstabEquipeProf{self.cnes_version}.csv")
        df = self.convert_data_types(df, f"rlEstabEquipeProf{self.cnes_version}.csv")
        
        columns = ['facility_id', 'professional_id', 'occupation_code', 'municipality_id',
                   'service_area_id', 'team_sequence_number', 'service_type', 'employment_type_code',
                   'start_date', 'termination_date', 'micro_area_code', 'other_team_cnes',
                   'last_updated_date', 'updated_by_user']
        df = df[[col for col in columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Facility-Professionals") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('facility_professionals', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} facility-professional relationships")
        return total_rows
    
    def import_facility_services(self) -> int:
        """Import facility services"""
        logger.info("=" * 80)
        logger.info("Importing facility services...")
        
        csv_file = self.csv_dir / f"rlEstabServClass{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = self.transform_column_names(df, f"rlEstabServClass{self.cnes_version}.csv")
        df = self.convert_data_types(df, f"rlEstabServClass{self.cnes_version}.csv")
        
        columns = ['facility_id', 'service_code', 'classification_code', 'characteristic_type',
                   'ambulatory_capacity', 'ambulatory_capacity_sus', 'hospital_capacity', 
                   'hospital_capacity_sus', 'is_active', 'last_updated_date', 'updated_by_user']
        df = df[[col for col in columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Facility Services") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('facility_services', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} facility services")
        return total_rows
    
    def import_facility_equipment(self) -> int:
        """Import facility equipment"""
        logger.info("=" * 80)
        logger.info("Importing facility equipment...")
        
        csv_file = self.csv_dir / f"rlEstabEquipamento{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            raise Exception(f"Failed to read {csv_file}")
        
        df = self.transform_column_names(df, f"rlEstabEquipamento{self.cnes_version}.csv")
        df = self.convert_data_types(df, f"rlEstabEquipamento{self.cnes_version}.csv")
        
        columns = ['facility_id', 'equipment_code', 'equipment_category_code', 'quantity',
                   'operational_status', 'last_updated_date', 'updated_by_user']
        df = df[[col for col in columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Facility Equipment") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('facility_equipment', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} equipment records")
        return total_rows
    
    def import_professional_workload(self) -> int:
        """Import professional workload"""
        logger.info("=" * 80)
        logger.info("Importing professional workload...")
        
        csv_file = self.csv_dir / f"tbCargaHorariaSus{self.cnes_version}.csv"
        df, _ = self.read_csv_with_encoding(csv_file)
        
        if df is None:
            logger.warning(f"Failed to read {csv_file}")
            return 0
        
        df = self.transform_column_names(df, f"tbCargaHorariaSus{self.cnes_version}.csv")
        df = self.convert_data_types(df, f"tbCargaHorariaSus{self.cnes_version}.csv")
        
        columns = ['facility_id', 'professional_id', 'occupation_code', 'weekly_hours_ambulatory',
                   'service_type', 'employment_type_code', 'professional_council_code', 
                   'license_number', 'license_state', 'is_preceptor', 'is_resident',
                   'last_updated_date', 'updated_by_user']
        df = df[[col for col in columns if col in df.columns]]
        
        # Import in batches
        total_rows = len(df)
        batches = range(0, total_rows, BATCH_SIZE)
        
        with tqdm(total=total_rows, desc="Professional Workload") as pbar:
            for start_idx in batches:
                end_idx = min(start_idx + BATCH_SIZE, total_rows)
                batch = df.iloc[start_idx:end_idx]
                
                batch.to_sql('professional_workload', self.engine, if_exists='append', index=False, method='multi')
                pbar.update(len(batch))
        
        logger.info(f"✅ Imported {total_rows} workload records")
        return total_rows
    
    def run_import(self):
        """Run complete import process"""
        start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("CNES DATA IMPORT STARTED")
        logger.info("=" * 80)
        
        stats = {}
        
        try:
            # Import in dependency order
            stats['states'] = self.import_states()
            stats['municipalities'] = self.import_municipalities()
            stats['reference_data'] = self.import_reference_data()
            stats['service_classifications'] = self.import_service_classifications()
            stats['facilities'] = self.import_facilities()
            stats['professionals'] = self.import_professionals()
            stats['facility_professionals'] = self.import_facility_professionals()
            stats['facility_services'] = self.import_facility_services()
            stats['facility_equipment'] = self.import_facility_equipment()
            stats['professional_workload'] = self.import_professional_workload()
            
            # Summary
            end_time = datetime.now()
            duration = end_time - start_time
            
            logger.info("=" * 80)
            logger.info("IMPORT COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info(f"Total time: {duration}")
            logger.info("\nRecords imported:")
            for table, count in stats.items():
                logger.info(f"  {table:30s}: {count:>10,d}")
            logger.info(f"\nTotal records: {sum(stats.values()):,d}")
            
            # Run validation queries
            self.validate_import()
            
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            raise
    
    def validate_import(self):
        """Validate imported data"""
        logger.info("=" * 80)
        logger.info("Validating import...")
        
        with self.engine.connect() as conn:
            # Count active facilities
            result = conn.execute(text("""
                SELECT COUNT(*) as count 
                FROM facilities 
                WHERE deactivation_reason_code IS NULL
            """))
            active_facilities = result.fetchone()[0]
            logger.info(f"  Active facilities: {active_facilities:,d}")
            
            # Count active professionals
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT professional_id) as count
                FROM facility_professionals 
                WHERE termination_date IS NULL
            """))
            active_professionals = result.fetchone()[0]
            logger.info(f"  Currently employed professionals: {active_professionals:,d}")
            
            # Count facilities with equipment
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT facility_id) as count 
                FROM facility_equipment
                WHERE quantity > 0
            """))
            facilities_with_equipment = result.fetchone()[0]
            logger.info(f"  Facilities with equipment: {facilities_with_equipment:,d}")
        
        logger.info("✅ Validation complete!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Import CNES data into Sales App database')
    parser.add_argument('--csv-dir', required=True, help='Directory containing CNES CSV files')
    parser.add_argument('--db-url', required=True, help='Database URL (e.g., postgresql://user:pass@localhost/dbname)')
    parser.add_argument('--cnes-version', help='CNES version (e.g., 202605), auto-detected if not provided')
    
    args = parser.parse_args()
    
    # Create importer and run
    importer = CNESDataImporter(
        csv_dir=args.csv_dir,
        db_url=args.db_url,
        cnes_version=args.cnes_version
    )
    
    importer.run_import()


if __name__ == '__main__':
    main()
