#!/usr/bin/env python3
"""
CSV File Analyzer for CNES Database Files
Analyzes CSV files and outputs structure information suitable for database ingestion.
"""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import re


CNES_ENCODINGS = ("latin1", "cp1252", "utf-8-sig")


class DataTypeInferrer:
    """Infers database-appropriate data types from sample data."""
    
    @staticmethod
    def is_integer(value: str) -> bool:
        """Check if value is an integer."""
        if not value or value.strip() == "":
            return False
        try:
            int(value.strip())
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_float(value: str) -> bool:
        """Check if value is a float."""
        if not value or value.strip() == "":
            return False
        try:
            float_val = float(value.strip().replace(',', '.'))
            # If it's actually an integer, don't classify as float
            if float_val.is_integer():
                return False
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_date(value: str) -> bool:
        """Check if value matches common date formats."""
        if not value or value.strip() == "":
            return False
        
        value = value.strip()
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',  # DD/MM/YYYY
            r'^\d{2}-\d{2}-\d{4}$',  # DD-MM-YYYY
            r'^\d{4}/\d{2}/\d{2}$',  # YYYY/MM/DD
            r'^\d{8}$',               # YYYYMMDD
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, value):
                return True
        return False
    
    @staticmethod
    def is_boolean(value: str) -> bool:
        """Check if value is boolean-like."""
        if not value or value.strip() == "":
            return False
        
        value_lower = value.strip().lower()
        boolean_values = {'true', 'false', 'yes', 'no', 'sim', 'não', 'nao', 
                         '0', '1', 't', 'f', 's', 'n'}
        return value_lower in boolean_values
    
    @staticmethod
    def infer_type(values: List[str]) -> str:
        """
        Infer the most appropriate database type from a list of sample values.
        Returns SQL-like type names suitable for database schemas.
        """
        # Filter out empty/null values for type checking
        non_empty_values = [v for v in values if v and v.strip() != ""]
        
        if not non_empty_values:
            return "VARCHAR"
        
        # Check type consistency
        integer_count = sum(1 for v in non_empty_values if DataTypeInferrer.is_integer(v))
        float_count = sum(1 for v in non_empty_values if DataTypeInferrer.is_float(v))
        date_count = sum(1 for v in non_empty_values if DataTypeInferrer.is_date(v))
        boolean_count = sum(1 for v in non_empty_values if DataTypeInferrer.is_boolean(v))
        
        total_count = len(non_empty_values)
        
        # If 80% or more match a type, classify as that type
        threshold = 0.8
        
        if integer_count >= total_count * threshold:
            return "INTEGER"
        elif float_count >= total_count * threshold:
            return "DECIMAL"
        elif date_count >= total_count * threshold:
            return "DATE"
        elif boolean_count >= total_count * threshold:
            return "BOOLEAN"
        else:
            return "VARCHAR"


class CSVAnalyzer:
    """Analyzes CSV files and extracts metadata for database ingestion."""
    
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)
        self.results = []
    
    def read_csv_with_encoding(self, file_path: Path) -> Tuple[Optional[List[List[str]]], Optional[str]]:
        """
        Try to read CSV with multiple encodings and delimiters.
        Returns tuple of (rows, successful_encoding) or (None, None) if all fail.
        """
        delimiters = [';', ',', '\t']  # Try semicolon first (common in CNES files)
        
        for encoding in CNES_ENCODINGS:
            for delimiter in delimiters:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        # Try to detect if this delimiter works
                        sample = f.read(1024)
                        f.seek(0)
                        
                        if delimiter in sample:
                            reader = csv.reader(f, delimiter=delimiter)
                            rows = list(reader)
                            
                            # Check if we got reasonable column separation
                            if rows and len(rows[0]) > 1:
                                # Clean up quoted values
                                cleaned_rows = []
                                for row in rows:
                                    cleaned_row = [cell.strip().strip('"').strip("'") for cell in row]
                                    cleaned_rows.append(cleaned_row)
                                return cleaned_rows, encoding
                except (UnicodeDecodeError, Exception) as e:
                    continue
        
        return None, None
    
    def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze a single CSV file."""
        print(f"Analyzing: {file_path.name}")
        
        rows, encoding = self.read_csv_with_encoding(file_path)
        
        if rows is None:
            return {
                "filename": file_path.name,
                "error": "Could not read file with any supported encoding",
                "columns": [],
                "sample_rows": []
            }
        
        if len(rows) < 1:
            return {
                "filename": file_path.name,
                "error": "File is empty",
                "encoding_used": encoding,
                "columns": [],
                "sample_rows": []
            }
        
        # First row is header
        headers = rows[0]
        data_rows = rows[1:]
        
        # Analyze columns and infer types
        columns_info = []
        for col_idx, col_name in enumerate(headers):
            # Collect sample values from this column (up to 100 rows for type inference)
            sample_size = min(100, len(data_rows))
            column_values = [row[col_idx] if col_idx < len(row) else "" 
                           for row in data_rows[:sample_size]]
            
            inferred_type = DataTypeInferrer.infer_type(column_values)
            
            columns_info.append({
                "column_name": col_name,
                "inferred_type": inferred_type
            })
        
        # Get up to 3 sample rows
        sample_rows = []
        for row in data_rows[:3]:
            # Convert row to dict for better readability
            row_dict = {}
            for idx, header in enumerate(headers):
                value = row[idx] if idx < len(row) else ""
                row_dict[header] = value
            sample_rows.append(row_dict)
        
        return {
            "filename": file_path.name,
            "encoding_used": encoding,
            "row_count": len(data_rows),
            "column_count": len(headers),
            "columns": columns_info,
            "sample_rows": sample_rows,
            "note": f"Successfully parsed {len(headers)} columns from {len(data_rows)} data rows"
        }
    
    def analyze_all_files(self) -> List[Dict[str, Any]]:
        """Analyze all CSV files in the folder."""
        csv_files = sorted(self.folder_path.glob("*.csv"))
        
        print(f"Found {len(csv_files)} CSV files to analyze\n")
        
        for csv_file in csv_files:
            result = self.analyze_file(csv_file)
            self.results.append(result)
        
        return self.results
    
    def save_to_json(self, output_path: str):
        """Save analysis results to JSON file."""
        output_data = {
            "analysis_date": datetime.now().isoformat(),
            "total_files": len(self.results),
            "source_folder": str(self.folder_path),
            "files": self.results
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\nAnalysis complete! Results saved to: {output_path}")
        print(f"Total files analyzed: {len(self.results)}")


def main():
    """Main execution function."""
    # Define paths
    csv_folder = "BASE_DE_DADOS_CNES_202605"
    output_file = "csv_analysis_report.json"
    
    # Check if folder exists
    if not os.path.exists(csv_folder):
        print(f"Error: Folder '{csv_folder}' not found!")
        return
    
    # Create analyzer and run analysis
    analyzer = CSVAnalyzer(csv_folder)
    analyzer.analyze_all_files()
    analyzer.save_to_json(output_file)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    successful = sum(1 for r in analyzer.results if "error" not in r)
    failed = sum(1 for r in analyzer.results if "error" in r)
    
    print(f"Successfully analyzed: {successful}")
    print(f"Failed to analyze: {failed}")
    
    if successful > 0:
        total_columns = sum(r.get("column_count", 0) for r in analyzer.results if "error" not in r)
        total_rows = sum(r.get("row_count", 0) for r in analyzer.results if "error" not in r)
        print(f"Total columns across all files: {total_columns}")
        print(f"Total data rows across all files: {total_rows}")


if __name__ == "__main__":
    main()
