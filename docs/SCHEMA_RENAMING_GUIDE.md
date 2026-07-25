# Database Schema Renaming Strategy
# CNES Database → Sales App Database

## Current Problems with CNES Naming:
- Portuguese abbreviations (CO_, NO_, NU_, DS_, TP_, ST_)
- Date suffixes (202605) in table names
- Unclear meanings (what's CO_UNIDADE?)
- Inconsistent patterns

## New Naming Principles:
- Clear English names
- No prefixes/suffixes
- Self-documenting
- Consistent patterns

---

## 📋 TABLE NAME MAPPINGS

### Core Entity Tables

| Old CNES Name | New Name | Purpose |
|---------------|----------|---------|
| `tbEstabelecimento202605.csv` | **`facilities`** | Health facilities/establishments |
| `tbDadosProfissionalSus202605.csv` | **`professionals`** | Healthcare professionals (doctors, nurses, etc.) |
| `tbMunicipio202605.csv` | **`municipalities`** | Brazilian cities/municipalities |
| `tbEstado202605.csv` | **`states`** | Brazilian states |
| `tbMantenedora202605.csv` | **`facility_owners`** | Organizations that own/manage facilities |

### Relationship Tables

| Old CNES Name | New Name | Purpose |
|---------------|----------|---------|
| `rlEstabEquipeProf202605.csv` | **`facility_professionals`** | Links professionals to facilities |
| `rlEstabServClass202605.csv` | **`facility_services`** | Services offered by each facility |
| `rlEstabEquipamento202605.csv` | **`facility_equipment`** | Equipment inventory at facilities |
| `tbCargaHorariaSus202605.csv` | **`professional_workload`** | Working hours and credentials |
| `rlEstabProfComissao202605.csv` | **`facility_decision_makers`** | Committee members and administrators |

### Reference/Lookup Tables

| Old CNES Name | New Name | Purpose |
|---------------|----------|---------|
| `tbTipoEstabelecimento202605.csv` | **`reference_data`** (type: facility_type) | Facility type lookup |
| `tbMotivoDesativacao202605.csv` | **`reference_data`** (type: deactivation_reason) | Deactivation reason lookup |
| `tbServicoEspecializado202605.csv` | **`reference_data`** (type: service_specialty) | Medical specialty lookup |
| `tbEquipamento202605.csv` | **`reference_data`** (type: equipment_catalog) | Equipment type catalog |
| `tbConselhoClasse202605.csv` | **`reference_data`** (type: professional_council) | Professional council lookup |
| `tbTipoEquipamento202605.csv` | **`reference_data`** (type: equipment_category) | Equipment category lookup |
| `tbClassificacaoServico202605.csv` | **`service_classifications`** | Detailed service classifications |

---

## 🔤 COLUMN NAME MAPPINGS

### 1. FACILITIES Table (tbEstabelecimento)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_UNIDADE` | **`facility_id`** | VARCHAR(20) PK | Unique facility identifier |
| `CO_CNES` | **`cnes_code`** | VARCHAR(20) | Official CNES registration code |
| `NO_RAZAO_SOCIAL` | **`legal_name`** | VARCHAR(200) | Legal company name |
| `NO_FANTASIA` | **`trade_name`** | VARCHAR(200) | Doing-business-as name |
| `NO_LOGRADOURO` | **`street_address`** | VARCHAR(200) | Street name |
| `NU_ENDERECO` | **`street_number`** | VARCHAR(20) | Street number |
| `NO_COMPLEMENTO` | **`address_complement`** | VARCHAR(100) | Apt, suite, etc. |
| `NO_BAIRRO` | **`neighborhood`** | VARCHAR(100) | Neighborhood/district |
| `CO_CEP` | **`postal_code`** | VARCHAR(10) | ZIP/postal code |
| `CO_MUNICIPIO` | **`municipality_id`** | VARCHAR(10) FK | City ID |
| `CO_REGIAO_SAUDE` | **`health_region_id`** | VARCHAR(10) | Health region ID |
| `NU_TELEFONE` | **`phone_number`** | VARCHAR(20) | Primary phone |
| `NU_FAX` | **`fax_number`** | VARCHAR(20) | Fax number |
| `NO_EMAIL` | **`email`** | VARCHAR(100) | Email address |
| `NO_URL` | **`website_url`** | VARCHAR(200) | Website URL |
| `NU_LATITUDE` | **`latitude`** | DECIMAL(10,7) | GPS latitude |
| `NU_LONGITUDE` | **`longitude`** | DECIMAL(10,7) | GPS longitude |
| `NU_CNPJ` | **`tax_id_cnpj`** | VARCHAR(20) | Company tax ID (CNPJ) |
| `NU_CPF` | **`tax_id_cpf`** | VARCHAR(20) | Individual tax ID (CPF) |
| `NU_CNPJ_MANTENEDORA` | **`owner_tax_id`** | VARCHAR(20) FK | Owner's tax ID |
| `CO_TIPO_ESTABELECIMENTO` | **`facility_type_code`** | VARCHAR(10) FK | Type code (hospital, clinic, etc.) |
| `CO_NATUREZA_JUR` | **`legal_entity_type_code`** | VARCHAR(10) FK | Legal entity type |
| `CO_ATIVIDADE` | **`primary_activity_code`** | VARCHAR(10) FK | Primary activity |
| `CO_TURNO_ATENDIMENTO` | **`operating_hours_code`** | VARCHAR(10) FK | Operating schedule |
| `CO_MOTIVO_DESAB` | **`deactivation_reason_code`** | VARCHAR(10) FK | Why facility is closed (NULL=active) |
| `TP_PFPJ` | **`entity_type`** | CHAR(1) | Person type (P=individual, J=company) |
| `TP_UNIDADE` | **`unit_type_code`** | VARCHAR(10) | Unit type classification |
| `TP_ESTAB_SEMPRE_ABERTO` | **`is_24_7`** | BOOLEAN | Open 24/7? |
| `ST_ADESAO_FILANTROP` | **`is_philanthropic`** | BOOLEAN | Philanthropic status |
| `ST_CONEXAO_INTERNET` | **`has_internet`** | BOOLEAN | Has internet connection? |
| `ST_CONTRATO_FORMALIZADO` | **`has_formal_contract`** | BOOLEAN | Has formalized contract? |
| `DT_EXPEDICAO` | **`license_issue_date`** | DATE | License issued date |
| `DT_VAL_LIC_SANI` | **`sanitary_license_expiry`** | DATE | Sanitary license expires |
| `TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update date |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 2. PROFESSIONALS Table (tbDadosProfissionalSus)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_PROFISSIONAL_SUS` | **`professional_id`** | VARCHAR(20) PK | Unique professional identifier |
| `NO_PROFISSIONAL` | **`full_name`** | VARCHAR(200) | Professional's full name |
| `NO_SOCIAL` | **`social_name`** | VARCHAR(200) | Social/preferred name |
| `CO_CPF` | **`tax_id`** | VARCHAR(20) | Tax ID (partially masked) |
| `CO_CNS` | **`health_card_number`** | VARCHAR(20) | National health card number |
| `CO_NACIONALIDADE` | **`nationality_code`** | VARCHAR(10) | Nationality code |
| `TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 3. FACILITY_PROFESSIONALS Table (rlEstabEquipeProf)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_UNIDADE` | **`facility_id`** | VARCHAR(20) FK | Facility identifier |
| `CO_PROFISSIONAL_SUS` | **`professional_id`** | VARCHAR(20) FK | Professional identifier |
| `CO_CBO` | **`occupation_code`** | VARCHAR(10) FK | Brazilian Occupation Code (specialty) |
| `CO_MUNICIPIO` | **`municipality_id`** | VARCHAR(10) FK | Municipality ID |
| `CO_AREA` | **`service_area_id`** | VARCHAR(10) FK | Service area ID |
| `SEQ_EQUIPE` | **`team_sequence_number`** | INT | Team sequence |
| `TP_SUS_NAO_SUS` | **`service_type`** | CHAR(1) | S=SUS/public, N=private |
| `IND_VINCULACAO` | **`employment_type_code`** | VARCHAR(10) FK | Employment type/link |
| `DT_ENTRADA` | **`start_date`** | DATE | Employment start date |
| `DT_DESLIGAMENTO` | **`termination_date`** | DATE | Employment end date (NULL=active) |
| `CO_MICROAREA` | **`micro_area_code`** | VARCHAR(10) | Micro service area |
| `CO_CNES_OUTRAEQUIPE` | **`other_team_cnes`** | VARCHAR(20) | Other team CNES code |
| `TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 4. FACILITY_SERVICES Table (rlEstabServClass)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_UNIDADE` | **`facility_id`** | VARCHAR(20) FK | Facility identifier |
| `CO_SERVICO` | **`service_code`** | VARCHAR(10) FK | Service specialty code |
| `CO_CLASSIFICACAO` | **`classification_code`** | VARCHAR(10) FK | Service classification |
| `TP_CARACTERISTICA` | **`characteristic_type`** | VARCHAR(10) | Characteristic type |
| `CO_AMBULATORIAL` | **`ambulatory_capacity`** | INT | Ambulatory capacity |
| `CO_AMBULATORIAL_SUS` | **`ambulatory_capacity_sus`** | INT | SUS ambulatory capacity |
| `CO_HOSPITALAR` | **`hospital_capacity`** | INT | Hospital capacity |
| `CO_HOSPITALAR_SUS` | **`hospital_capacity_sus`** | INT | SUS hospital capacity |
| `ST_ATIVO_SN` | **`is_active`** | BOOLEAN | Service is active? |
| `TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 5. FACILITY_EQUIPMENT Table (rlEstabEquipamento)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_UNIDADE` | **`facility_id`** | VARCHAR(20) FK | Facility identifier |
| `CO_EQUIPAMENTO` | **`equipment_code`** | VARCHAR(10) FK | Equipment type code |
| `CO_TIPO_EQUIPAMENTO` | **`equipment_category_code`** | VARCHAR(10) FK | Equipment category |
| `QT_EQUIPAMENTO` | **`quantity`** | INT | Number of units |
| `IND_FUNCIONAMENTO` | **`operational_status`** | VARCHAR(10) | E=In use, D=Inactive, M=Maintenance |
| `TO_CHAR(DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 6. PROFESSIONAL_WORKLOAD Table (tbCargaHorariaSus)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_UNIDADE` | **`facility_id`** | VARCHAR(20) FK | Facility identifier |
| `CO_PROFISSIONAL_SUS` | **`professional_id`** | VARCHAR(20) FK | Professional identifier |
| `CO_CBO` | **`occupation_code`** | VARCHAR(10) FK | Occupation/specialty code |
| `QT_CARGA_HORARIA_AMBULATORIAL` | **`weekly_hours_ambulatory`** | INT | Weekly ambulatory hours |
| `TP_SUS_NAO_SUS` | **`service_type`** | CHAR(1) | S=SUS, N=private |
| `IND_VINCULACAO` | **`employment_type_code`** | VARCHAR(10) | Employment type |
| `CO_CONSELHO_CLASSE` | **`professional_council_code`** | VARCHAR(10) FK | Council (CRM, CRO, etc.) |
| `NU_REGISTRO` | **`license_number`** | VARCHAR(20) | Professional license number |
| `SG_UF_CRM` | **`license_state`** | CHAR(2) | State where licensed |
| `TP_PRECEPTOR` | **`is_preceptor`** | BOOLEAN | Is teaching/supervising? |
| `TP_RESIDENTE` | **`is_resident`** | BOOLEAN | Is medical resident? |
| `TO_CHAR(A.DT_ATUALIZACAO,'DD/MM/YYYY')` | **`last_updated_date`** | DATE | Last update |
| `CO_USUARIO` | **`updated_by_user`** | VARCHAR(50) | User who updated |

### 7. MUNICIPALITIES Table (tbMunicipio)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_MUNICIPIO` | **`municipality_id`** | VARCHAR(10) PK | Municipality code |
| `NO_MUNICIPIO` | **`municipality_name`** | VARCHAR(100) | Municipality name |
| `CO_SIGLA_ESTADO` | **`state_code`** | CHAR(2) FK | State abbreviation (SP, RJ, etc.) |
| `TP_CADASTRO` | **`registration_type`** | VARCHAR(10) | Registration type |
| `TP_PACTO` | **`pact_type`** | VARCHAR(10) | Management pact type |
| `TP_ENVIA` | **`data_submission_type`** | VARCHAR(10) | Data submission type |

### 8. STATES Table (tbEstado)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_SIGLA_ESTADO` | **`state_code`** | CHAR(2) PK | State abbreviation |
| `NO_ESTADO` | **`state_name`** | VARCHAR(100) | State full name |

### 9. REFERENCE_DATA Table (Consolidated)

| Column Name | Type | Description |
|-------------|------|-------------|
| **`reference_type`** | VARCHAR(50) PK | Type of reference (facility_type, deactivation_reason, etc.) |
| **`code`** | VARCHAR(20) PK | Reference code |
| **`description`** | VARCHAR(500) | Description/name |
| **`extra_data`** | JSON | Type-specific additional fields |
| **`display_order`** | INT | Sort order for display |
| **`is_active`** | BOOLEAN | Active status |
| **`created_at`** | TIMESTAMP | When record was created |
| **`updated_at`** | TIMESTAMP | Last update |
| **`cnes_version`** | VARCHAR(10) | CNES data version (e.g., '202607') |

### 10. SERVICE_CLASSIFICATIONS Table (tbClassificacaoServico)

| Old Column Name | New Column Name | Type | Description |
|----------------|-----------------|------|-------------|
| `CO_CLASSIFICACAO_SERVICO` | **`classification_id`** | VARCHAR(10) PK | Classification identifier |
| `CO_SERVICO_ESPECIALIZADO` | **`service_specialty_code`** | VARCHAR(10) PK/FK | Service specialty code |
| `DS_CLASSIFICACAO_SERVICO` | **`classification_name`** | VARCHAR(200) | Classification description |

---

## 🎨 PREFIX/SUFFIX PATTERNS

### Old CNES Prefixes (Removed in new schema):
- `CO_` = Código (Code)
- `NO_` = Nome (Name)
- `NU_` = Número (Number)
- `DS_` = Descrição (Description)
- `TP_` = Tipo (Type)
- `ST_` = Status/Situação
- `DT_` = Data (Date)
- `IND_` = Indicador (Indicator)
- `QT_` = Quantidade (Quantity)
- `SG_` = Sigla (Abbreviation)

### New English Patterns (Consistent & Clear):
- `*_id` = Identifiers
- `*_code` = Reference/lookup codes
- `*_name` = Names
- `*_number` = Numbers (phone, license, etc.)
- `*_date` = Dates
- `is_*` = Boolean flags
- `has_*` = Boolean possession
- `*_type` = Type classifiers
- `*_status` = Status indicators

---

## 📊 DATA TYPE STANDARDIZATION

### String Fields:
- IDs: `VARCHAR(20)`
- Codes: `VARCHAR(10)`
- Names: `VARCHAR(200)`
- Descriptions: `VARCHAR(500)`
- URLs/Emails: `VARCHAR(200)`
- Phone numbers: `VARCHAR(20)`
- State codes: `CHAR(2)`

### Numeric Fields:
- Integers: `INT`
- Coordinates: `DECIMAL(10,7)`

### Dates:
- All dates: `DATE` or `TIMESTAMP`

### Booleans:
- All yes/no: `BOOLEAN` (not CHAR(1))

---

## 🔄 MIGRATION EXAMPLES

### Creating New Tables with New Names:

```sql
-- Old:
CREATE TABLE tbEstabelecimento202605 (
    CO_UNIDADE VARCHAR(20) PRIMARY KEY,
    NO_FANTASIA VARCHAR(200),
    NU_TELEFONE VARCHAR(20)
);

-- New:
CREATE TABLE facilities (
    facility_id VARCHAR(20) PRIMARY KEY,
    trade_name VARCHAR(200),
    phone_number VARCHAR(20)
);
```

### Migration Script:

```sql
-- Migrate data from old to new
INSERT INTO facilities (
    facility_id,
    trade_name,
    legal_name,
    phone_number,
    email,
    latitude,
    longitude,
    facility_type_code,
    deactivation_reason_code
)
SELECT 
    CO_UNIDADE,
    NO_FANTASIA,
    NO_RAZAO_SOCIAL,
    NU_TELEFONE,
    NO_EMAIL,
    NU_LATITUDE,
    NU_LONGITUDE,
    CO_TIPO_ESTABELECIMENTO,
    CO_MOTIVO_DESAB
FROM tbEstabelecimento202605;
```

---

## 📖 USAGE EXAMPLES

### Old Query:
```sql
SELECT 
    e.CO_UNIDADE,
    e.NO_FANTASIA,
    e.NU_TELEFONE,
    t.DS_TIPO_ESTABELECIMENTO
FROM tbEstabelecimento202605 e
JOIN tbTipoEstabelecimento202605 t 
    ON e.CO_TIPO_ESTABELECIMENTO = t.CO_TIPO_ESTABELECIMENTO
WHERE e.CO_MOTIVO_DESAB IS NULL;
```

### New Query (Much Clearer!):
```sql
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    r.description as facility_type
FROM facilities f
JOIN reference_data r 
    ON r.reference_type = 'facility_type'
    AND r.code = f.facility_type_code
WHERE f.deactivation_reason_code IS NULL;
```

---

## ✅ BENEFITS OF NEW NAMING

1. **Self-Documenting** - Names explain themselves
2. **No Learning Curve** - Developers understand immediately
3. **English** - International team friendly
4. **Consistent** - Same patterns throughout
5. **IDE Friendly** - Better autocomplete
6. **Maintainable** - Easier to understand 6 months later
7. **Professional** - Modern naming standards

---

## 📋 QUICK REFERENCE CHEAT SHEET

| Old Cryptic | New Clear |
|-------------|-----------|
| CO_UNIDADE | facility_id |
| NO_FANTASIA | trade_name |
| NO_RAZAO_SOCIAL | legal_name |
| NU_TELEFONE | phone_number |
| CO_MOTIVO_DESAB | deactivation_reason_code |
| DT_DESLIGAMENTO | termination_date |
| CO_PROFISSIONAL_SUS | professional_id |
| NO_PROFISSIONAL | full_name |
| TP_SUS_NAO_SUS | service_type |
| ST_ATIVO_SN | is_active |
| QT_EQUIPAMENTO | quantity |

---

## 🎯 RECOMMENDATION

**Use new names for your sales app database** - much clearer and maintainable!

Keep a mapping file for ETL/import processes that read from CNES CSVs.
