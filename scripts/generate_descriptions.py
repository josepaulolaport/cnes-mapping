#!/usr/bin/env python3
"""
Table Description Generator for CNES Database
Analyzes table structures and generates human-readable descriptions.
"""

import json
from typing import Dict, List, Any


class TableDescriptionGenerator:
    """Generates descriptions for CNES tables based on their structure."""
    
    # Prefix meanings in CNES
    PREFIX_MEANINGS = {
        'CO_': 'código (code/identifier)',
        'NU_': 'número (number)',
        'NO_': 'nome (name)',
        'DS_': 'descrição (description)',
        'DT_': 'data (date)',
        'TP_': 'tipo (type)',
        'ST_': 'status/situação',
        'TO_CHAR': 'data formatada'
    }
    
    # Common column name patterns and their meanings
    COLUMN_MEANINGS = {
        'CNPJ': 'CNPJ (company tax ID)',
        'CPF': 'CPF (individual tax ID)',
        'CNS': 'Cartão Nacional de Saúde (National Health Card)',
        'CNES': 'Cadastro Nacional de Estabelecimentos de Saúde',
        'UNIDADE': 'health unit/establishment',
        'ESTABELECIMENTO': 'health establishment',
        'PROFISSIONAL': 'healthcare professional',
        'MUNICIPIO': 'municipality',
        'ESTADO': 'state',
        'EQUIPAMENTO': 'equipment',
        'EQUIPE': 'team',
        'LEITO': 'hospital bed',
        'ATIVIDADE': 'activity',
        'SERVICO': 'service',
        'ESPECIALIDADE': 'specialty',
        'AVALIACAO': 'evaluation/assessment',
        'HABILITACAO': 'accreditation/qualification',
        'CONVENIO': 'agreement/covenant',
        'GESTAO': 'management',
        'VINCULO': 'employment link/relationship',
        'CBO': 'Brazilian Occupation Code',
        'VIGENCIA': 'validity period',
        'ATUALIZACAO': 'last updated',
        'USUARIO': 'user who made the change'
    }
    
    def __init__(self, relationships_file: str):
        """Initialize with relationships report."""
        with open(relationships_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        self.tables = self.data['tables']
    
    def _get_table_type(self, filename: str) -> str:
        """Determine if table is main table (tb) or relationship table (rl)."""
        if filename.startswith('tb'):
            return 'main'
        elif filename.startswith('rl'):
            return 'relationship'
        return 'unknown'
    
    def _extract_table_subject(self, filename: str) -> str:
        """Extract the main subject from table name."""
        # Remove prefix and date suffix
        name = filename.replace('.csv', '')
        name = name.replace('202605', '')
        
        if name.startswith('tb'):
            name = name[2:]
        elif name.startswith('rl'):
            name = name[2:]
        
        return name
    
    def _describe_column(self, col_name: str) -> str:
        """Generate a description for a column based on its name."""
        col_upper = col_name.upper()
        
        # Check for known patterns
        for pattern, meaning in self.COLUMN_MEANINGS.items():
            if pattern in col_upper:
                return meaning
        
        # Check prefixes
        for prefix, meaning in self.PREFIX_MEANINGS.items():
            if col_upper.startswith(prefix):
                rest = col_upper[len(prefix):]
                for pattern, pattern_meaning in self.COLUMN_MEANINGS.items():
                    if pattern in rest:
                        return f"{meaning} of {pattern_meaning}"
        
        return "data field"
    
    def _get_key_entities(self, table_info: Dict) -> List[str]:
        """Identify key entities involved in this table."""
        entities = set()
        
        for col in table_info['columns']:
            col_name = col['column_name'].upper()
            
            # Look for entity identifiers
            for entity in ['UNIDADE', 'ESTABELECIMENTO', 'PROFISSIONAL', 'EQUIPE', 
                          'MUNICIPIO', 'ESTADO', 'EQUIPAMENTO', 'LEITO', 'PACIENTE']:
                if entity in col_name:
                    entities.add(entity.lower())
        
        return sorted(list(entities))
    
    def _describe_primary_key(self, pk_info: Dict) -> str:
        """Describe the primary key."""
        if not pk_info:
            return "No primary key detected"
        
        columns = pk_info.get('columns', [])
        if len(columns) == 1:
            return f"uniquely identified by {columns[0]}"
        else:
            return f"uniquely identified by the combination of {', '.join(columns)}"
    
    def _describe_relationships(self, table_info: Dict) -> str:
        """Describe foreign key relationships."""
        fks = table_info.get('foreign_keys', [])
        
        if not fks:
            return "No foreign key relationships detected."
        
        # Group FKs by referenced table
        ref_tables = {}
        for fk in fks:
            ref_table = fk['references_table'].replace('202605.csv', '').replace('tb', '').replace('rl', '')
            if ref_table not in ref_tables:
                ref_tables[ref_table] = []
            ref_tables[ref_table].append(fk['column'])
        
        if len(ref_tables) == 1:
            table_name = list(ref_tables.keys())[0]
            return f"This table references {table_name}."
        elif len(ref_tables) <= 3:
            table_names = ', '.join(ref_tables.keys())
            return f"This table references: {table_names}."
        else:
            return f"This table has relationships with {len(ref_tables)} other tables including {', '.join(list(ref_tables.keys())[:3])}, and others."
    
    def generate_description(self, table_info: Dict) -> str:
        """Generate a comprehensive description for a table."""
        filename = table_info['filename']
        table_type = self._get_table_type(filename)
        subject = self._extract_table_subject(filename)
        
        # Analyze columns to understand purpose
        columns = table_info['columns']
        col_names = [col['column_name'].upper() for col in columns]
        col_names_str = '|'.join(col_names)
        
        # Build description based on specific table patterns
        description = self._get_specific_description(filename, col_names_str, table_type, table_info, subject)
        
        # Add row count context
        row_count = table_info['row_count']
        if row_count > 1000000:
            size_desc = f"This is a large table with {row_count:,} records."
        elif row_count > 100000:
            size_desc = f"Contains {row_count:,} records."
        elif row_count > 1000:
            size_desc = f"Contains {row_count:,} records."
        else:
            size_desc = f"This is a small reference table with {row_count:,} records."
        
        # Primary key information
        pk_desc = self._describe_primary_key(table_info.get('primary_key'))
        
        # Relationships
        rel_desc = self._describe_relationships(table_info)
        
        # Combine all parts
        full_description = f"{description} {size_desc} Each record is {pk_desc}. {rel_desc}"
        
        return full_description
    
    def _get_specific_description(self, filename: str, col_names: str, table_type: str, table_info: Dict, subject: str) -> str:
        """Generate specific descriptions based on table name patterns."""
        fname_upper = filename.upper()
        
        # Main establishment table
        if fname_upper == 'TBESTABLECIMENTO202605.CSV':
            return "Master table containing comprehensive information about all registered health establishments (facilities) in Brazil. Stores administrative details, addresses, contact information, type of facility, legal status, and operational characteristics."
        
        # Professional data
        if 'TBDADOSPROFISSIONAL' in fname_upper:
            return "Master table of healthcare professionals registered in the system. Contains personal information including CPF, CNS (National Health Card), names, and professional identifiers used across the entire CNES database."
        
        if 'TBCARGAHORARIASUS' in fname_upper:
            return "Records the working hours (carga horária) of healthcare professionals in SUS facilities. Tracks how many hours each professional dedicates to public health services."
        
        # Teams
        if fname_upper == 'TBEQUIPE202605.CSV':
            return "Contains information about healthcare teams, including primary care teams (ESF - Family Health Strategy), NASF (Family Health Support Centers), and other team-based care models. Each team has an identification code and operational area."
        
        if 'RLESTABEQUIPEPROF' in fname_upper:
            return "Junction table linking health establishments, teams, and professionals. Maps which professionals work in which teams at which facilities, including their occupation code (CBO) and whether they serve SUS or private patients."
        
        # Geographic tables
        if fname_upper == 'TBMUNICIPIO202605.CSV':
            return "Reference table of all Brazilian municipalities. Contains municipality codes, names, state associations, and administrative configurations for health system management."
        
        if fname_upper == 'TBESTADO202605.CSV':
            return "Reference table of Brazilian states (UF - Unidades Federativas). Simple lookup table with state codes and names."
        
        # Equipment
        if 'RLESTABEQUIPAMENTO' in fname_upper:
            return "Links health establishments to their medical equipment. Records which equipment is available at each facility and its operational status (in use, inactive, etc.)."
        
        if fname_upper == 'TBEQUIPAMENTO202605.CSV':
            return "Reference table defining types of medical equipment tracked in CNES. Each equipment type has a code and description (e.g., X-ray machines, ultrasound, CT scanners)."
        
        # Services
        if 'SERVICO' in fname_upper and 'ESPECIALIZADO' in fname_upper:
            return "Reference table of specialized healthcare services. Defines the types of specialized medical services that can be offered by health facilities."
        
        if 'RLESTABSERVCLASS' in fname_upper:
            return "Maps health establishments to the classification of services they provide. Links facilities to their service offerings and specializations."
        
        # Activities
        if fname_upper == 'TBATIVIDADE202605.CSV':
            return "Reference table of healthcare activities. Defines all types of activities/services that health establishments can perform (e.g., consultations, procedures, diagnostics)."
        
        if 'RLATIVIDADEOBRIGATORIA' in fname_upper:
            return "Defines which activities are mandatory for specific types of health establishments. Ensures establishments register required services based on their classification."
        
        # Generic patterns
        if table_type == 'relationship':
            # Determine entities being linked
            entities = []
            if 'ESTAB' in fname_upper:
                entities.append('establishments')
            if 'EQUIPE' in fname_upper or 'NASF' in fname_upper or 'ESF' in fname_upper:
                entities.append('teams')
            if 'PROF' in fname_upper:
                entities.append('professionals')
            if 'MUNICIPIO' in fname_upper or 'MUN' in fname_upper:
                entities.append('municipalities')
            if 'EQUIPAMENTO' in fname_upper:
                entities.append('equipment')
            if 'LEITO' in fname_upper:
                entities.append('hospital beds')
            if 'SERVICO' in fname_upper:
                entities.append('services')
            
            if len(entities) >= 2:
                return f"Junction/relationship table that links {' and '.join(entities)}. Enables tracking of associations between these entities in the healthcare system."
            else:
                return f"Relationship table managing associations in the CNES database related to {subject}."
        
        # Main table patterns
        if 'TIPO' in fname_upper and table_type == 'main':
            return f"Reference/lookup table defining types or categories for {subject}. Provides standardized classifications used throughout the CNES system."
        
        if 'LEITO' in fname_upper:
            return "Contains information about hospital beds (leitos), including bed types, specializations, and availability across health facilities."
        
        if 'MANTENEDORA' in fname_upper:
            return "Information about entities that maintain/manage health establishments. Contains details about the organizations responsible for facility operations."
        
        if 'AVALIACAO' in fname_upper or 'AVAL' in fname_upper:
            return "Contains evaluation or assessment data, including quality certifications, accreditations, or performance evaluations of health establishments."
        
        if 'HABILITACAO' in fname_upper:
            return "Tracks accreditations and qualifications (habilitações) that authorize health facilities to provide specific high-complexity services."
        
        if 'CONVENIO' in fname_upper:
            return "Information about health insurance agreements (convênios) and partnerships between facilities and insurance providers or healthcare plans."
        
        if 'INCENTIVO' in fname_upper:
            return "Tracks financial incentives and special funding programs that health establishments participate in or receive."
        
        # Default fallback
        if table_type == 'main':
            return f"Main data table storing information about {subject} in the Brazilian healthcare system (CNES)."
        else:
            return f"Relationship table for {subject} that connects related entities in the CNES database."
    
    def generate_all_descriptions(self) -> Dict[str, Any]:
        """Generate descriptions for all tables."""
        descriptions = {}
        
        print(f"Generating descriptions for {len(self.tables)} tables...\n")
        
        for idx, table_info in enumerate(self.tables, 1):
            filename = table_info['filename']
            print(f"[{idx}/{len(self.tables)}] Analyzing {filename}")
            
            description = self.generate_description(table_info)
            
            descriptions[filename] = {
                "table_name": filename,
                "subject": self._extract_table_subject(filename),
                "type": self._get_table_type(filename),
                "row_count": table_info['row_count'],
                "column_count": table_info['column_count'],
                "has_primary_key": table_info.get('primary_key') is not None,
                "foreign_key_count": table_info.get('foreign_key_count', 0),
                "description": description
            }
        
        return descriptions
    
    def save_to_json(self, output_file: str):
        """Save descriptions to JSON file."""
        descriptions = self.generate_all_descriptions()
        
        output_data = {
            "generated_date": self.data['analysis_date'],
            "total_tables": len(descriptions),
            "source": "CNES Database - May 2026",
            "descriptions": descriptions
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print(f"Descriptions saved to: {output_file}")
        print(f"Total tables described: {len(descriptions)}")


def main():
    """Main execution."""
    input_file = "relationships_report.json"
    output_file = "table_descriptions.json"
    
    generator = TableDescriptionGenerator(input_file)
    generator.save_to_json(output_file)


if __name__ == "__main__":
    main()
