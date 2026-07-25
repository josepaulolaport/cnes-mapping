"""
ETL Helper for CNES to Sales App Database Transformation
Uses schema_mapping.json to transform old column names to new ones.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

class CNESSchemaMapper:
    """Helper class to map CNES data to new Sales App schema"""
    
    def __init__(self, mapping_file: str = 'schema_mapping.json'):
        """Load the schema mapping configuration"""
        with open(mapping_file, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)['schema_mapping']
        
        # Create quick lookup dictionaries
        self.table_mappings = self._build_table_mappings()
        
    def _build_table_mappings(self) -> Dict:
        """Build quick lookup for table and column mappings"""
        mappings = {}
        for old_table, config in self.mapping['tables'].items():
            if old_table == 'CONSOLIDATED_LOOKUPS':
                continue
            mappings[old_table] = {
                'new_table_name': config['new_name'],
                'columns': {}
            }
            for old_col, col_config in config.get('columns', {}).items():
                mappings[old_table]['columns'][old_col] = col_config['new_name']
        return mappings
    
    def get_new_table_name(self, old_table_name: str) -> Optional[str]:
        """Get new table name from old CNES table name"""
        return self.table_mappings.get(old_table_name, {}).get('new_table_name')
    
    def get_new_column_name(self, old_table_name: str, old_column_name: str) -> Optional[str]:
        """Get new column name from old CNES table and column name"""
        table_map = self.table_mappings.get(old_table_name, {})
        return table_map.get('columns', {}).get(old_column_name)
    
    def rename_dataframe_columns(self, df: pd.DataFrame, old_table_name: str) -> pd.DataFrame:
        """
        Rename all columns in a DataFrame according to the mapping.
        Only renames columns that exist in the mapping.
        """
        table_map = self.table_mappings.get(old_table_name, {})
        column_map = table_map.get('columns', {})
        
        # Only rename columns that exist in both the DataFrame and the mapping
        rename_dict = {
            old_col: new_col 
            for old_col, new_col in column_map.items() 
            if old_col in df.columns
        }
        
        return df.rename(columns=rename_dict)
    
    def get_column_type(self, old_table_name: str, old_column_name: str) -> Optional[str]:
        """Get the expected data type for a column"""
        table_config = self.mapping['tables'].get(old_table_name, {})
        col_config = table_config.get('columns', {}).get(old_column_name, {})
        return col_config.get('type')
    
    def is_foreign_key(self, old_table_name: str, old_column_name: str) -> bool:
        """Check if a column is a foreign key"""
        table_config = self.mapping['tables'].get(old_table_name, {})
        col_config = table_config.get('columns', {}).get(old_column_name, {})
        return col_config.get('is_foreign_key', False)
    
    def get_foreign_key_reference(self, old_table_name: str, old_column_name: str) -> Optional[str]:
        """Get the foreign key reference if it exists"""
        table_config = self.mapping['tables'].get(old_table_name, {})
        col_config = table_config.get('columns', {}).get(old_column_name, {})
        return col_config.get('references')
    
    def print_mapping_summary(self):
        """Print a summary of all table and column mappings"""
        print("=" * 80)
        print("CNES TO SALES APP SCHEMA MAPPING SUMMARY")
        print("=" * 80)
        
        for old_table, config in self.table_mappings.items():
            new_table = config['new_table_name']
            num_columns = len(config['columns'])
            
            print(f"\n📋 {old_table}")
            print(f"   → {new_table} ({num_columns} mapped columns)")
            print(f"   Columns:")
            
            for old_col, new_col in config['columns'].items():
                print(f"      {old_col:40} → {new_col}")


def example_usage():
    """Example of how to use the schema mapper"""
    
    # Initialize mapper
    mapper = CNESSchemaMapper('schema_mapping.json')
    
    # Example 1: Get new table name
    old_table = 'tbEstabelecimento202605.csv'
    new_table = mapper.get_new_table_name(old_table)
    print(f"Old: {old_table}")
    print(f"New: {new_table}")
    print()
    
    # Example 2: Get new column name
    old_col = 'NO_FANTASIA'
    new_col = mapper.get_new_column_name(old_table, old_col)
    print(f"Column mapping: {old_col} → {new_col}")
    print()
    
    # Example 3: Transform a DataFrame
    # Simulated data (in real use, this would come from reading the CSV)
    sample_data = {
        'CO_UNIDADE': ['001', '002', '003'],
        'NO_FANTASIA': ['Hospital A', 'Clinica B', 'Centro C'],
        'NU_TELEFONE': ['11-1111-1111', '11-2222-2222', '11-3333-3333'],
        'CO_MOTIVO_DESAB': [None, None, '01']  # First two are active
    }
    
    df = pd.DataFrame(sample_data)
    print("Original DataFrame:")
    print(df)
    print()
    
    # Rename columns using the mapping
    df_renamed = mapper.rename_dataframe_columns(df, old_table)
    print("Renamed DataFrame:")
    print(df_renamed)
    print()
    
    # Example 4: Check if column is a foreign key
    is_fk = mapper.is_foreign_key(old_table, 'CO_MOTIVO_DESAB')
    fk_ref = mapper.get_foreign_key_reference(old_table, 'CO_MOTIVO_DESAB')
    print(f"CO_MOTIVO_DESAB is foreign key: {is_fk}")
    print(f"References: {fk_ref}")
    print()
    
    # Example 5: Print full mapping summary
    # mapper.print_mapping_summary()


def create_sql_migration_script(mapper: CNESSchemaMapper, output_file: str = 'migration.sql'):
    """
    Generate SQL migration script to create new tables with renamed columns.
    This is a basic template - you'll need to customize based on your actual DB.
    """
    
    sql_statements = []
    sql_statements.append("-- CNES to Sales App Database Migration Script")
    sql_statements.append("-- Generated automatically from schema_mapping.json")
    sql_statements.append("-- WARNING: Review and customize before running!\n")
    
    for old_table, config in mapper.table_mappings.items():
        new_table = config['new_table_name']
        
        sql_statements.append(f"-- Migrate {old_table} to {new_table}")
        sql_statements.append(f"CREATE TABLE IF NOT EXISTS {new_table} (")
        
        # Get columns from full mapping
        table_config = mapper.mapping['tables'][old_table]
        columns_sql = []
        
        for old_col, col_config in table_config.get('columns', {}).items():
            new_col = col_config['new_name']
            col_type = col_config.get('type', 'VARCHAR(200)')
            nullable = '' if col_config.get('nullable', False) else 'NOT NULL'
            pk = 'PRIMARY KEY' if col_config.get('is_primary_key', False) else ''
            
            columns_sql.append(f"    {new_col} {col_type} {nullable} {pk}".strip())
        
        sql_statements.append(",\n".join(columns_sql))
        sql_statements.append(");\n")
        
        # Add INSERT statement template
        old_cols = list(table_config.get('columns', {}).keys())
        new_cols = [config['columns'][old_col] for old_col in old_cols]
        
        sql_statements.append(f"-- Insert data from {old_table}")
        sql_statements.append(f"INSERT INTO {new_table} (")
        sql_statements.append("    " + ",\n    ".join(new_cols))
        sql_statements.append(")")
        sql_statements.append("SELECT")
        sql_statements.append("    " + ",\n    ".join(old_cols))
        sql_statements.append(f"FROM {old_table.replace('.csv', '')};")
        sql_statements.append("")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(sql_statements))
    
    print(f"SQL migration script written to {output_file}")


# Quick Reference Functions
def quick_lookup(old_table_name: str, old_column_name: str):
    """Quick command-line lookup of mappings"""
    mapper = CNESSchemaMapper()
    new_table = mapper.get_new_table_name(old_table_name)
    new_col = mapper.get_new_column_name(old_table_name, old_column_name)
    col_type = mapper.get_column_type(old_table_name, old_column_name)
    is_fk = mapper.is_foreign_key(old_table_name, old_column_name)
    
    print(f"Table: {old_table_name} → {new_table}")
    print(f"Column: {old_column_name} → {new_col}")
    print(f"Type: {col_type}")
    print(f"Foreign Key: {is_fk}")
    if is_fk:
        print(f"References: {mapper.get_foreign_key_reference(old_table_name, old_column_name)}")


if __name__ == '__main__':
    # Run example usage
    example_usage()
    
    # Optionally generate SQL migration script
    # mapper = CNESSchemaMapper()
    # create_sql_migration_script(mapper, 'migration_script.sql')
