#!/usr/bin/env python3
"""
CNES Data Import Script - SQLite Version
=========================================

Import CNES CSV data into a SQLite database.

Usage:
    python import_sqlite.py --table states
    python import_sqlite.py --table all
    python import_sqlite.py --table facilities --force
    python import_sqlite.py --db output/cnes_data.db

Available tables:
    - states, municipalities, facility_types, deactivation_reasons
    - service_specialties, equipment_catalog, professional_councils
    - equipment_categories, service_classifications
    - facilities, professionals, facility_professionals
    - facility_services, facility_equipment, professional_workload
    - all (imports everything in correct order)
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

# Setup logging
LOG_DIR = Path('./logs')
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'import_sqlite.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
CNES_ENCODINGS = ['latin1', 'cp1252', 'utf-8-sig']
BATCH_SIZE = 10000
ERROR_LOG_DIR = Path('./import_errors')
ERROR_LOG_DIR.mkdir(exist_ok=True)


class CNESSQLiteImporter:
    """CNES data importer for SQLite"""
    
    def __init__(self, csv_dir: str, db_path: str, cnes_version: str = '202605'):
        self.csv_dir = Path(csv_dir)
        self.db_path = Path(db_path)
        self.cnes_version = cnes_version
        
        # Create database directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create SQLite engine
        self.engine = create_engine(f'sqlite:///{self.db_path}', 
                                   connect_args={'check_same_thread': False})
        
        logger.info(f"Initialized for CNES version: {cnes_version}")
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
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.fetchone()[0]
                return count > 0
        except:
            return False
    
    def import_batch_with_error_handling(self, table_name: str, batch_df: pd.DataFrame, 
                                         batch_num: int, error_log_file: Path) -> int:
        """Import a batch with error handling"""
        try:
            batch_df.to_sql(table_name, self.engine, if_exists='append', index=False, method='multi')
            return len(batch_df)
        except Exception as e:
            logger.warning(f"Batch {batch_num} failed, trying row-by-row: {str(e)[:100]}")
            success_count = 0
            
            with open(error_log_file, 'a', encoding='utf-8') as f:
                for idx, row in batch_df.iterrows():
                    try:
                        row.to_frame().T.to_sql(table_name, self.engine, if_exists='append', 
                                                index=False, method='multi')
                        success_count += 1
                    except Exception as row_error:
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
        
        df = df.rename(columns={
            'CO_SIGLA': 'state_code',
            'NO_DESCRICAO': 'state_name'
        })
        
        df = df[['state_code', 'state_name']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM states"))
                conn.commit()
        
        df.to_sql('states', self.engine, if_exists='append', index=False, method='multi')
        
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
        
        # Get valid state codes
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT state_code FROM states"))
            valid_states = {row[0] for row in result}
        
        df = df.rename(columns={
            'CO_MUNICIPIO': 'municipality_id',
            'NO_MUNICIPIO': 'municipality_name',
            'CO_SIGLA_ESTADO': 'state_code'
        })
        
        # Filter invalid state codes
        initial_count = len(df)
        df = df[df['state_code'].isin(valid_states)]
        filtered = initial_count - len(df)
        if filtered > 0:
            logger.info(f"  Filtered out {filtered} municipalities with invalid state codes")
        
        df = df[['municipality_id', 'municipality_name', 'state_code']]
        
        if force:
            with self.engine.connect() as conn:
                conn.execute(text("DELETE FROM municipalities"))
                conn.commit()
        
        df.to_sql('municipalities', self.engine, if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Imported {len(df)} municipalities")
        return len(df)
    
    def import_all(self, force: bool = False):
        """Import all tables in correct dependency order"""
        logger.info("=" * 80)
        logger.info("STARTING FULL IMPORT")
        logger.info("=" * 80)
        
        start_time = datetime.now()
        stats = {}
        
        try:
            # Reference tables
            stats['states'] = self.import_states(force)
            stats['municipalities'] = self.import_municipalities(force)
            stats['facility_types'] = self.import_facility_types(force)
            stats['deactivation_reasons'] = self.import_deactivation_reasons(force)
            stats['service_specialties'] = self.import_service_specialties(force)
            stats['equipment_catalog'] = self.import_equipment_catalog(force)
            stats['professional_councils'] = self.import_professional_councils(force)
            stats['equipment_categories'] = self.import_equipment_categories(force)
            stats['service_classifications'] = self.import_service_classifications(force)
            
            # Large tables
            stats['facilities'] = self.import_facilities(force)
            stats['professionals'] = self.import_professionals(force)
            stats['facility_professionals'] = self.import_facility_professionals(force)
            stats['facility_services'] = self.import_facility_services(force)
            stats['facility_equipment'] = self.import_facility_equipment(force)
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
    
    # Placeholder methods for remaining tables (implement similarly to states/municipalities)
    def import_facility_types(self, force: bool = False) -> int:
        # Implementation similar to states...
        pass
    
    def import_deactivation_reasons(self, force: bool = False) -> int:
        pass
    
    def import_service_specialties(self, force: bool = False) -> int:
        pass
    
    def import_equipment_catalog(self, force: bool = False) -> int:
        pass
    
    def import_professional_councils(self, force: bool = False) -> int:
        pass
    
    def import_equipment_categories(self, force: bool = False) -> int:
        pass
    
    def import_service_classifications(self, force: bool = False) -> int:
        pass
    
    def import_facilities(self, force: bool = False) -> int:
        pass
    
    def import_professionals(self, force: bool = False) -> int:
        pass
    
    def import_facility_professionals(self, force: bool = False) -> int:
        pass
    
    def import_facility_services(self, force: bool = False) -> int:
        pass
    
    def import_facility_equipment(self, force: bool = False) -> int:
        pass
    
    def import_professional_workload(self, force: bool = False) -> int:
        pass


def main():
    parser = argparse.ArgumentParser(description='Import CNES data to SQLite')
    parser.add_argument('--csv-dir', default='./BASE_DE_DADOS_CNES_202605', help='CSV directory')
    parser.add_argument('--db', default='./output/cnes_data.db', help='SQLite database path')
    parser.add_argument('--cnes-version', default='202605', help='CNES version')
    parser.add_argument('--table', required=True, help='Table to import (or "all")')
    parser.add_argument('--force', action='store_true', help='Force reimport')
    
    args = parser.parse_args()
    
    importer = CNESSQLiteImporter(
        csv_dir=args.csv_dir,
        db_path=args.db,
        cnes_version=args.cnes_version
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
