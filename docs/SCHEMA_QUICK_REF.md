# CNES → Sales App Schema - Quick Reference Cheat Sheet

## 🎯 Most Common Table Names

| Old CNES Name | New Name | Use For |
|---------------|----------|---------|
| `tbEstabelecimento202605` | **facilities** | Health facilities |
| `tbDadosProfissionalSus202605` | **professionals** | Doctors, nurses, etc. |
| `rlEstabEquipeProf202605` | **facility_professionals** | Who works where |
| `rlEstabServClass202605` | **facility_services** | Services offered |
| `rlEstabEquipamento202605` | **facility_equipment** | Equipment inventory |
| `tbCargaHorariaSus202605` | **professional_workload** | Working hours |
| `tbMunicipio202605` | **municipalities** | Cities |
| `tbEstado202605` | **states** | States |
| `tbMotivoDesativacao202605` | **reference_data** | Lookup tables |

---

## 🔤 Most Common Column Renames

### Identifiers (IDs)
| Old | New |
|-----|-----|
| `CO_UNIDADE` | `facility_id` |
| `CO_PROFISSIONAL_SUS` | `professional_id` |
| `CO_MUNICIPIO` | `municipality_id` |
| `CO_SIGLA_ESTADO` | `state_code` |

### Names
| Old | New |
|-----|-----|
| `NO_FANTASIA` | `trade_name` |
| `NO_RAZAO_SOCIAL` | `legal_name` |
| `NO_PROFISSIONAL` | `full_name` |
| `NO_MUNICIPIO` | `municipality_name` |
| `NO_ESTADO` | `state_name` |

### Contact Info
| Old | New |
|-----|-----|
| `NO_LOGRADOURO` | `street_address` |
| `NU_ENDERECO` | `street_number` |
| `NO_BAIRRO` | `neighborhood` |
| `CO_CEP` | `postal_code` |
| `NU_TELEFONE` | `phone_number` |
| `NO_EMAIL` | `email` |
| `NO_URL` | `website_url` |

### Location
| Old | New |
|-----|-----|
| `NU_LATITUDE` | `latitude` |
| `NU_LONGITUDE` | `longitude` |

### Dates (Critical!)
| Old | New | NULL Means |
|-----|-----|------------|
| `DT_ENTRADA` | `start_date` | - |
| `DT_DESLIGAMENTO` | `termination_date` | ✅ **ACTIVE** |
| `CO_MOTIVO_DESAB` | `deactivation_reason_code` | ✅ **ACTIVE** |
| `DT_ATUALIZACAO` | `last_updated_date` | - |

### Equipment/Inventory
| Old | New |
|-----|-----|
| `CO_EQUIPAMENTO` | `equipment_code` |
| `QT_EQUIPAMENTO` | `quantity` |
| `IND_FUNCIONAMENTO` | `operational_status` |

### Boolean Fields
| Old | New |
|-----|-----|
| `ST_ATIVO_SN` | `is_active` |
| `TP_ESTAB_SEMPRE_ABERTO` | `is_24_7` |
| `ST_CONEXAO_INTERNET` | `has_internet` |

### Other Important
| Old | New |
|-----|-----|
| `CO_CBO` | `occupation_code` |
| `NU_CNPJ` | `tax_id_cnpj` |
| `TP_SUS_NAO_SUS` | `service_type` |

---

## 🚨 CRITICAL STATUS FIELDS

### Active vs. Deactivated Facilities
```sql
-- ACTIVE facility
WHERE deactivation_reason_code IS NULL

-- DEACTIVATED facility
WHERE deactivation_reason_code IS NOT NULL
```

### Active vs. Terminated Professionals
```sql
-- ACTIVE professional at facility
WHERE termination_date IS NULL

-- TERMINATED professional
WHERE termination_date IS NOT NULL
```

---

## 📋 Common Patterns

### Old CNES Prefixes (REMOVED)
- `CO_` = Code
- `NO_` = Name
- `NU_` = Number
- `DS_` = Description
- `TP_` = Type
- `ST_` = Status
- `DT_` = Date
- `IND_` = Indicator
- `QT_` = Quantity

### New English Patterns (USE THESE)
- `*_id` = Identifiers
- `*_code` = Reference codes
- `*_name` = Names
- `*_number` = Numbers (phone, license)
- `*_date` = Dates
- `is_*` = Boolean (is_active, is_24_7)
- `has_*` = Boolean possession (has_internet)

---

## 💡 Quick Python Usage

```python
from schema_mapper import CNESSchemaMapper

# Initialize
mapper = CNESSchemaMapper('schema_mapping.json')

# Get new table name
new_table = mapper.get_new_table_name('tbEstabelecimento202605.csv')
# Returns: 'facilities'

# Get new column name
new_col = mapper.get_new_column_name(
    'tbEstabelecimento202605.csv', 
    'NO_FANTASIA'
)
# Returns: 'trade_name'

# Transform a DataFrame
df_renamed = mapper.rename_dataframe_columns(df, 'tbEstabelecimento202605.csv')
```

---

## 🎯 Sales App Priority Tables

### MUST HAVE (Phase 1)
1. `facilities` - The establishments
2. `professionals` - The doctors
3. `facility_professionals` - Who works where
4. `municipalities` - Cities
5. `states` - States
6. `reference_data` - Lookup codes
7. `facility_services` - What services offered

### SHOULD HAVE (Phase 2)
8. `facility_equipment` - Equipment inventory
9. `professional_workload` - Working hours/credentials
10. `service_classifications` - Detailed service info

---

## 📖 Example Query Translations

### Old CNES Query:
```sql
SELECT 
    e.CO_UNIDADE,
    e.NO_FANTASIA,
    e.NU_TELEFONE
FROM tbEstabelecimento202605 e
WHERE e.CO_MOTIVO_DESAB IS NULL;
```

### New Sales App Query:
```sql
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number
FROM facilities f
WHERE f.deactivation_reason_code IS NULL;
```

---

## 📂 Files Created

| File | Purpose |
|------|---------|
| `SCHEMA_RENAMING_GUIDE.md` | Full documentation with examples |
| `schema_mapping.json` | Machine-readable mapping |
| `schema_mapper.py` | Python ETL helper |
| `SCHEMA_QUICK_REF.md` | This cheat sheet |

---

## 🔗 See Also

- Full documentation: `SCHEMA_RENAMING_GUIDE.md`
- Sales app tables: `SALES_APP_TABLES.md`
- JSON mapping: `schema_mapping.json`
- Python helper: `schema_mapper.py`

---

**Last Updated:** 2026-06-18  
**Version:** 1.0
