#!/usr/bin/env python3
"""
Enhanced CSV Relationship Analyzer for CNES Database Files
Analyzes nullability, primary keys, and foreign key relationships.
"""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict
import random


CNES_ENCODINGS = ("latin1", "cp1252", "utf-8-sig")


class CSVReader:
    """Handles reading CSV files with proper encoding and delimiter detection."""
    
    @staticmethod
    def read_csv_with_encoding(file_path: Path) -> Tuple[Optional[List[List[str]]], Optional[str]]:
        """
        Try to read CSV with multiple encodings and delimiters.
        Returns tuple of (rows, successful_encoding) or (None, None) if all fail.
        """
        delimiters = [';', ',', '\t']
        
        for encoding in CNES_ENCODINGS:
            for delimiter in delimiters:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        sample = f.read(1024)
                        f.seek(0)
                        
                        if delimiter in sample:
                            reader = csv.reader(f, delimiter=delimiter)
                            rows = list(reader)
                            
                            if rows and len(rows[0]) > 1:
                                cleaned_rows = []
                                for row in rows:
                                    cleaned_row = [cell.strip().strip('"').strip("'") for cell in row]
                                    cleaned_rows.append(cleaned_row)
                                return cleaned_rows, encoding
                except (UnicodeDecodeError, Exception):
                    continue
        
        return None, None


class NullabilityAnalyzer:
    """Analyzes column nullability."""
    
    @staticmethod
    def analyze_nullability(data_rows: List[List[str]], col_idx: int) -> Dict[str, Any]:
        """
        Analyze nullability for a column.
        Empty strings are treated as NULL.
        """
        total_rows = len(data_rows)
        null_count = 0
        
        for row in data_rows:
            if col_idx < len(row):
                value = row[col_idx].strip()
                if value == "":
                    null_count += 1
            else:
                null_count += 1
        
        is_nullable = null_count > 0
        null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0
        
        return {
            "nullable": is_nullable,
            "null_count": null_count,
            "null_percentage": round(null_percentage, 2)
        }


class PrimaryKeyDetector:
    """Detects potential primary keys in tables."""
    
    @staticmethod
    def check_uniqueness(data_rows: List[List[str]], col_indices: List[int]) -> Tuple[bool, float]:
        """
        Check if a column combination is unique.
        Returns (is_unique, uniqueness_rate).
        """
        if not data_rows:
            return False, 0.0
        
        seen_values = set()
        total_count = 0
        duplicate_count = 0
        
        for row in data_rows:
            # Build composite key
            key_parts = []
            skip_row = False
            
            for col_idx in col_indices:
                if col_idx < len(row):
                    value = row[col_idx].strip()
                    if value == "":  # NULL values can't be part of PK
                        skip_row = True
                        break
                    key_parts.append(value)
                else:
                    skip_row = True
                    break
            
            if skip_row:
                continue
            
            key = tuple(key_parts)
            total_count += 1
            
            if key in seen_values:
                duplicate_count += 1
            else:
                seen_values.add(key)
        
        if total_count == 0:
            return False, 0.0
        
        uniqueness_rate = (total_count - duplicate_count) / total_count
        is_unique = uniqueness_rate == 1.0
        
        return is_unique, uniqueness_rate
    
    @staticmethod
    def get_pk_name_score(column_names: List[str]) -> int:
        """
        Score column names for likelihood of being a primary key.
        Higher score = more likely to be PK.
        """
        score = 0
        combined_name = "_".join(column_names).upper()
        
        # Strong indicators
        if any(name.upper().startswith('CO_') for name in column_names):
            score += 10
        if any(name.upper().startswith('NU_') for name in column_names):
            score += 8
        if 'ID' in combined_name:
            score += 5
        if 'COD' in combined_name or 'CODIGO' in combined_name:
            score += 5
        
        # Prefer shorter combinations
        if len(column_names) == 1:
            score += 3
        elif len(column_names) == 2:
            score += 1
        
        return score
    
    @staticmethod
    def detect_primary_key(headers: List[str], data_rows: List[List[str]], 
                          max_columns: int = 3) -> Optional[Dict[str, Any]]:
        """
        Detect primary key by checking column combinations.
        Returns best candidate PK or None.
        """
        candidates = []
        
        # Check single columns first
        for col_idx, col_name in enumerate(headers):
            is_unique, uniqueness_rate = PrimaryKeyDetector.check_uniqueness(
                data_rows, [col_idx]
            )
            
            if is_unique:
                name_score = PrimaryKeyDetector.get_pk_name_score([col_name])
                candidates.append({
                    "columns": [col_name],
                    "column_indices": [col_idx],
                    "is_composite": False,
                    "uniqueness_rate": uniqueness_rate,
                    "name_score": name_score,
                    "confidence": "high" if name_score > 5 else "medium"
                })
        
        # If we found single-column PKs with good names, prefer those
        if candidates:
            candidates.sort(key=lambda x: (x["uniqueness_rate"], x["name_score"]), reverse=True)
            best = candidates[0]
            if best["name_score"] > 5:
                return best
        
        # Check 2-column combinations
        if max_columns >= 2:
            for i in range(len(headers)):
                for j in range(i + 1, len(headers)):
                    is_unique, uniqueness_rate = PrimaryKeyDetector.check_uniqueness(
                        data_rows, [i, j]
                    )
                    
                    if is_unique:
                        cols = [headers[i], headers[j]]
                        name_score = PrimaryKeyDetector.get_pk_name_score(cols)
                        candidates.append({
                            "columns": cols,
                            "column_indices": [i, j],
                            "is_composite": True,
                            "uniqueness_rate": uniqueness_rate,
                            "name_score": name_score,
                            "confidence": "high" if name_score > 8 else "medium"
                        })
        
        # Check 3-column combinations (only if no good candidates yet)
        if max_columns >= 3 and len(candidates) < 3:
            # Limit to columns with PK-like names to avoid explosion
            pk_like_indices = [
                i for i, name in enumerate(headers)
                if name.upper().startswith('CO_') or name.upper().startswith('NU_') or 'ID' in name.upper()
            ]
            
            for i in range(len(pk_like_indices)):
                for j in range(i + 1, len(pk_like_indices)):
                    for k in range(j + 1, len(pk_like_indices)):
                        idx_i, idx_j, idx_k = pk_like_indices[i], pk_like_indices[j], pk_like_indices[k]
                        is_unique, uniqueness_rate = PrimaryKeyDetector.check_uniqueness(
                            data_rows, [idx_i, idx_j, idx_k]
                        )
                        
                        if is_unique:
                            cols = [headers[idx_i], headers[idx_j], headers[idx_k]]
                            name_score = PrimaryKeyDetector.get_pk_name_score(cols)
                            candidates.append({
                                "columns": cols,
                                "column_indices": [idx_i, idx_j, idx_k],
                                "is_composite": True,
                                "uniqueness_rate": uniqueness_rate,
                                "name_score": name_score,
                                "confidence": "medium"
                            })
        
        # Return best candidate
        if candidates:
            candidates.sort(key=lambda x: (x["uniqueness_rate"], x["name_score"]), reverse=True)
            return candidates[0]
        
        return None


class ForeignKeyDetector:
    """Detects foreign key relationships between tables."""
    
    def __init__(self, all_tables_data: Dict[str, Dict]):
        """
        Initialize with data from all tables.
        all_tables_data format:
        {
            "filename.csv": {
                "headers": [...],
                "data_rows": [...],
                "primary_key": {...}
            }
        }
        """
        self.all_tables_data = all_tables_data
        self.table_indices = self._build_table_indices()
    
    def _build_table_indices(self) -> Dict[str, Dict[str, Set[str]]]:
        """
        Build indices for efficient FK lookup.
        Returns: {filename: {column_name: set(values)}}
        """
        print("Building table indices for FK detection...")
        indices = {}
        
        for filename, table_data in self.all_tables_data.items():
            indices[filename] = {}
            headers = table_data["headers"]
            data_rows = table_data["data_rows"]
            
            # Index all columns (for potential FK targets)
            for col_idx, col_name in enumerate(headers):
                values = set()
                for row in data_rows:
                    if col_idx < len(row):
                        value = row[col_idx].strip()
                        if value != "":  # Skip NULL
                            values.add(value)
                indices[filename][col_name] = values
        
        return indices
    
    def _sample_column_values(self, data_rows: List[List[str]], col_idx: int, 
                             sample_size: int = 10000) -> List[str]:
        """Sample values from a column for FK checking."""
        values = []
        for row in data_rows:
            if col_idx < len(row):
                value = row[col_idx].strip()
                if value != "":
                    values.append(value)
        
        if len(values) <= sample_size:
            return values
        
        return random.sample(values, sample_size)
    
    def _check_fk_match(self, source_values: List[str], target_values: Set[str]) -> Tuple[float, List[str]]:
        """
        Check how many source values exist in target.
        Returns (match_rate, sample_orphaned_values).
        """
        if not source_values:
            return 0.0, []
        
        matched = 0
        orphaned = []
        
        for value in source_values:
            if value in target_values:
                matched += 1
            else:
                if len(orphaned) < 10:  # Keep first 10 orphaned values
                    orphaned.append(value)
        
        match_rate = matched / len(source_values)
        return match_rate, orphaned
    
    def _get_column_name_similarity(self, col1: str, col2: str) -> float:
        """
        Calculate similarity between column names.
        Returns score 0-1.
        """
        col1_upper = col1.upper()
        col2_upper = col2.upper()
        
        # Exact match
        if col1_upper == col2_upper:
            return 1.0
        
        # Remove common prefixes/suffixes
        prefixes = ['CO_', 'NU_', 'ID_', 'DS_', 'TP_', 'ST_', 'DT_', 'NO_']
        
        col1_clean = col1_upper
        col2_clean = col2_upper
        
        for prefix in prefixes:
            if col1_clean.startswith(prefix):
                col1_clean = col1_clean[len(prefix):]
            if col2_clean.startswith(prefix):
                col2_clean = col2_clean[len(prefix):]
        
        if col1_clean == col2_clean:
            return 0.9
        
        # Partial match
        if col1_clean in col2_clean or col2_clean in col1_clean:
            return 0.7
        
        return 0.0
    
    def detect_foreign_keys(self, filename: str, sample_size: int = 10000) -> List[Dict[str, Any]]:
        """
        Detect foreign keys for a table using hybrid approach.
        """
        table_data = self.all_tables_data[filename]
        headers = table_data["headers"]
        data_rows = table_data["data_rows"]
        
        foreign_keys = []
        
        # For each column in this table
        for col_idx, col_name in enumerate(headers):
            # Note: We DON'T skip PK columns because in relationship tables,
            # the PK is often also a FK (e.g., composite keys in many-to-many tables)
            
            # Phase 1: Name-based matching
            candidates = []
            
            for target_filename, target_data in self.all_tables_data.items():
                # Allow self-references (for hierarchical data like parent_id)
                target_headers = target_data["headers"]
                
                for target_col_idx, target_col_name in enumerate(target_headers):
                    # Skip if it's the same column in the same table
                    if target_filename == filename and target_col_idx == col_idx:
                        continue
                    
                    similarity = self._get_column_name_similarity(col_name, target_col_name)
                    
                    # Only consider if names are similar
                    if similarity >= 0.7:
                        candidates.append({
                            "target_table": target_filename,
                            "target_column": target_col_name,
                            "name_similarity": similarity
                        })
            
            if not candidates:
                continue
            
            # Phase 2: Value sampling
            source_values = self._sample_column_values(data_rows, col_idx, sample_size)
            
            if not source_values:
                continue
            
            for candidate in candidates:
                target_table = candidate["target_table"]
                target_column = candidate["target_column"]
                
                # Get target values from index
                target_values = self.table_indices.get(target_table, {}).get(target_column, set())
                
                if not target_values:
                    continue
                
                # Check match rate
                match_rate, orphaned = self._check_fk_match(source_values, target_values)
                
                # Consider as FK if match rate is reasonable
                if match_rate >= 0.80:  # 80% threshold
                    confidence = "high" if match_rate >= 0.95 else "medium"
                    
                    fk_info = {
                        "column": col_name,
                        "references_table": target_table,
                        "references_column": target_column,
                        "match_rate": round(match_rate, 4),
                        "confidence": confidence,
                        "sample_size": len(source_values)
                    }
                    
                    # Add warning if there are orphaned records
                    if orphaned:
                        orphaned_count = int(len(source_values) * (1 - match_rate))
                        fk_info["orphaned_count"] = orphaned_count
                        fk_info["sample_orphaned_values"] = orphaned[:10]
                    
                    foreign_keys.append(fk_info)
        
        return foreign_keys


class RelationshipAnalyzer:
    """Main analyzer that coordinates all analysis."""
    
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)
        self.results = []
        self.all_tables_data = {}
    
    def load_all_tables(self):
        """Load all CSV files into memory."""
        csv_files = sorted(self.folder_path.glob("*.csv"))
        print(f"Loading {len(csv_files)} CSV files...")
        
        for idx, csv_file in enumerate(csv_files, 1):
            print(f"  [{idx}/{len(csv_files)}] Loading {csv_file.name}")
            
            rows, encoding = CSVReader.read_csv_with_encoding(csv_file)
            
            if rows is None or len(rows) < 1:
                continue
            
            headers = rows[0]
            data_rows = rows[1:]
            
            self.all_tables_data[csv_file.name] = {
                "headers": headers,
                "data_rows": data_rows,
                "encoding": encoding
            }
        
        print(f"Loaded {len(self.all_tables_data)} tables successfully.\n")
    
    def analyze_table(self, filename: str, table_data: Dict) -> Dict[str, Any]:
        """Analyze a single table for nullability, PK, and structure."""
        print(f"Analyzing {filename}...")
        
        headers = table_data["headers"]
        data_rows = table_data["data_rows"]
        encoding = table_data["encoding"]
        
        # Analyze columns
        columns_info = []
        
        for col_idx, col_name in enumerate(headers):
            # Nullability
            null_info = NullabilityAnalyzer.analyze_nullability(data_rows, col_idx)
            
            column_info = {
                "column_name": col_name,
                "nullable": null_info["nullable"],
                "null_count": null_info["null_count"],
                "null_percentage": null_info["null_percentage"]
            }
            
            columns_info.append(column_info)
        
        # Detect primary key
        primary_key = PrimaryKeyDetector.detect_primary_key(headers, data_rows, max_columns=3)
        
        # Mark PK columns
        if primary_key:
            pk_columns = primary_key["columns"]
            for col_info in columns_info:
                if col_info["column_name"] in pk_columns:
                    col_info["is_primary_key"] = True
        
        result = {
            "filename": filename,
            "encoding_used": encoding,
            "row_count": len(data_rows),
            "column_count": len(headers),
            "primary_key": primary_key,
            "columns": columns_info
        }
        
        return result
    
    def detect_all_foreign_keys(self, sample_size: int = 10000):
        """Detect foreign keys for all tables."""
        print("\n" + "="*60)
        print("FOREIGN KEY DETECTION")
        print("="*60 + "\n")
        
        fk_detector = ForeignKeyDetector(self.all_tables_data)
        
        for idx, filename in enumerate(self.all_tables_data.keys(), 1):
            print(f"[{idx}/{len(self.all_tables_data)}] Detecting FKs in {filename}...")
            
            foreign_keys = fk_detector.detect_foreign_keys(filename, sample_size)
            
            # Find the result and add FK info
            for result in self.results:
                if result["filename"] == filename:
                    result["foreign_keys"] = foreign_keys
                    result["foreign_key_count"] = len(foreign_keys)
                    
                    # Add FK info to individual columns
                    for fk in foreign_keys:
                        for col in result["columns"]:
                            if col["column_name"] == fk["column"]:
                                col["is_foreign_key"] = True
                                # Support multiple FK references (column could reference multiple tables)
                                if "foreign_key_references" not in col:
                                    col["foreign_key_references"] = []
                                col["foreign_key_references"].append({
                                    "table": fk["references_table"],
                                    "column": fk["references_column"],
                                    "match_rate": fk["match_rate"],
                                    "confidence": fk["confidence"]
                                })
                    break
            
            if foreign_keys:
                print(f"  Found {len(foreign_keys)} foreign key(s)")
    
    def analyze_all(self):
        """Run complete analysis."""
        print("="*60)
        print("PHASE 1: LOADING DATA")
        print("="*60 + "\n")
        
        self.load_all_tables()
        
        print("="*60)
        print("PHASE 2: ANALYZING STRUCTURE (Nullability & Primary Keys)")
        print("="*60 + "\n")
        
        for idx, (filename, table_data) in enumerate(self.all_tables_data.items(), 1):
            print(f"[{idx}/{len(self.all_tables_data)}] ", end="")
            result = self.analyze_table(filename, table_data)
            self.results.append(result)
            
            # Store PK info back for FK detection
            table_data["primary_key"] = result.get("primary_key")
        
        print("\n" + "="*60)
        print("PHASE 3: DETECTING FOREIGN KEYS")
        print("="*60)
        
        self.detect_all_foreign_keys(sample_size=10000)
    
    def generate_warnings(self) -> List[Dict[str, Any]]:
        """Generate warnings for data quality issues."""
        warnings = []
        
        for result in self.results:
            filename = result["filename"]
            
            # Warning: No PK detected
            if not result.get("primary_key"):
                warnings.append({
                    "table": filename,
                    "severity": "high",
                    "issue": "No primary key detected",
                    "recommendation": "Review table structure - tables should have a unique identifier"
                })
            
            # Warning: Orphaned FK records
            for fk in result.get("foreign_keys", []):
                if fk.get("orphaned_count", 0) > 0:
                    orphaned_count = fk["orphaned_count"]
                    total_sampled = fk["sample_size"]
                    orphan_pct = (orphaned_count / total_sampled * 100) if total_sampled > 0 else 0
                    
                    warnings.append({
                        "table": filename,
                        "column": fk["column"],
                        "severity": "medium" if orphan_pct < 5 else "high",
                        "issue": f"Foreign key has {orphaned_count} orphaned records ({orphan_pct:.2f}% of sampled data)",
                        "references": f"{fk['references_table']}.{fk['references_column']}",
                        "sample_orphaned_values": fk.get("sample_orphaned_values", [])
                    })
        
        return warnings
    
    def save_to_json(self, output_path: str):
        """Save analysis results to JSON file."""
        warnings = self.generate_warnings()
        
        # Generate summary statistics
        total_pks = sum(1 for r in self.results if r.get("primary_key"))
        total_fks = sum(r.get("foreign_key_count", 0) for r in self.results)
        total_columns = sum(r["column_count"] for r in self.results)
        total_nullable = sum(
            sum(1 for col in r["columns"] if col["nullable"])
            for r in self.results
        )
        
        output_data = {
            "analysis_date": datetime.now().isoformat(),
            "source_folder": str(self.folder_path),
            "summary": {
                "total_tables": len(self.results),
                "total_columns": total_columns,
                "tables_with_primary_keys": total_pks,
                "total_foreign_keys_detected": total_fks,
                "total_nullable_columns": total_nullable,
                "warnings_count": len(warnings)
            },
            "tables": self.results,
            "warnings": warnings
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print("ANALYSIS COMPLETE")
        print("="*60)
        print(f"Results saved to: {output_path}")
        print(f"\nSummary:")
        print(f"  Tables analyzed: {len(self.results)}")
        print(f"  Primary keys detected: {total_pks}")
        print(f"  Foreign keys detected: {total_fks}")
        print(f"  Warnings generated: {len(warnings)}")


def main():
    """Main execution function."""
    csv_folder = "BASE_DE_DADOS_CNES_202605"
    output_file = "relationships_report.json"
    
    if not os.path.exists(csv_folder):
        print(f"Error: Folder '{csv_folder}' not found!")
        return
    
    analyzer = RelationshipAnalyzer(csv_folder)
    analyzer.analyze_all()
    analyzer.save_to_json(output_file)


if __name__ == "__main__":
    main()
