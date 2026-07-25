# Quick Reference: Sales App Database Structure

## 🎯 THE BIG PICTURE

Your sales app needs to answer these questions:
1. **WHERE** - Which facilities to target?
2. **WHO** - Who works there? Who decides?
3. **WHAT** - What do they have? What do they need?
4. **HOW** - How to reach them?

---

## 📊 DATA FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    SALES INTELLIGENCE                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────────┐
         │     tbEstabelecimento (Master)          │
         │  • Name, Address, Contact Info          │
         │  • Type, CNPJ, Geo-coordinates         │
         │  • 623,208 facilities                   │
         └────────────────────────────────────────┘
                   │         │         │
        ┌──────────┴────┬────┴────┬───┴──────────┐
        ▼               ▼         ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐
│ LOCATION     │ │ SERVICES │ │EQUIPMENT │ │  DOCTORS    │
│              │ │          │ │          │ │             │
│ tbMunicipio  │ │rlEstab   │ │rlEstab   │ │rlEstab      │
│ tbEstado     │ │ServClass │ │Equipamen │ │EquipeProf   │
│              │ │          │ │          │ │             │
│ Territory    │ │ What     │ │ What     │ │ tbDadosProf │
│ Planning     │ │ they DO  │ │ they HAVE│ │ issionalSus │
└──────────────┘ └──────────┘ └──────────┘ └─────────────┘
```

---

## 🔑 ESSENTIAL TABLES (Start Here)

### 1. **Facility Base** (The Foundation)
```
tbEstabelecimento202605.csv
├─ 623,208 facilities
├─ CO_UNIDADE = Primary Key
├─ CO_MOTIVO_DESAB = Deactivation status (NULL = active) ⚠️
└─ Contains: name, address, phone, email, coordinates, CNPJ
```

### 2. **Deactivation Lookup** (Critical Filter)
```
tbMotivoDesativacao202605.csv
├─ 14 deactivation reasons
├─ CD_MOTIVO_DESAB = Reason code
└─ ~24.5% of establishments are deactivated - FILTER THESE OUT!
```

### 3. **Doctor Registry** (Who's Who)
```
tbDadosProfissionalSus202605.csv
├─ 7.7M professionals
├─ CO_PROFISSIONAL_SUS = Primary Key
└─ Contains: names, CPF, CNS
```

### 3. **The Connector** (Links Facilities ↔ Doctors)
```
rlEstabEquipeProf202605.csv
├─ 870K work relationships
├─ Links: CO_UNIDADE + CO_PROFISSIONAL_SUS
└─ Contains: occupation (CBO), dates, SUS/private
```

### 4. **Geography** (Territory Management)
```
tbMunicipio202605.csv (5,607 cities)
tbEstado202605.csv (27 states)
```

---

## 🎯 TARGETING TABLES

### Find Facilities by Specialty
```
rlEstabServClass → tbServicoEspecializado
Example: Filter for Orthopedics (code 155)
```

### Find Equipment at Facilities
```
rlEstabEquipamento → tbEquipamento
Example: Who has X-ray machines?
```

### Find Facility Type
```
tbTipoEstabelecimento
Example: Hospitals vs Clinics vs Pharmacies
```

---

## 📞 CONTACT INFORMATION

**From tbEstabelecimento:**
- NO_RAZAO_SOCIAL - Legal company name
- NO_FANTASIA - Trade name / "doing business as"
- NO_LOGRADOURO + NU_ENDERECO - Street address
- NO_BAIRRO - Neighborhood
- CO_CEP - ZIP code
- NU_TELEFONE - Phone
- NO_EMAIL - Email
- NO_URL - Website
- NU_LATITUDE, NU_LONGITUDE - GPS coordinates

**Additional Contacts:**
- rlEstabTeleCnes - Phone directory
- rlEstabRepresentante - Official representatives
- rlEstabProfComissao - Committee members (decision makers)

---

## 💼 BUSINESS INTELLIGENCE

### Ownership
```
tbMantenedora - Parent companies/owners
tbNaturezaJuridica - Public/private/nonprofit
```

### Decision Makers
```
rlEstabProfComissao - Committee members
CO_CPFDIRETORCLN - Clinical director (in tbEstabelecimento)
```

### Quality Indicators
```
rlEstabAvaliacao → tbAvaliacao
Accredited facilities = higher purchasing power
```

---

## 🗺️ SAMPLE QUERIES FOR YOUR APP

### 1. "Show me ACTIVE hospitals in São Paulo"
```sql
SELECT * FROM tbEstabelecimento
WHERE CO_TIPO_ESTABELECIMENTO = '006' -- Hospital
  AND CO_MUNICIPIO IN (
    SELECT CO_MUNICIPIO FROM tbMunicipio 
    WHERE NO_MUNICIPIO LIKE 'SÃO PAULO%'
  )
  AND (CO_MOTIVO_DESAB IS NULL OR CO_MOTIVO_DESAB = '')  -- Active only!
```

### 2. "Find ACTIVE orthopedic clinics"
```sql
SELECT e.* FROM tbEstabelecimento e
JOIN rlEstabServClass s ON e.CO_UNIDADE = s.CO_UNIDADE
WHERE s.CO_SERVICO = '155' -- Orthopedics
  AND (e.CO_MOTIVO_DESAB IS NULL OR e.CO_MOTIVO_DESAB = '')  -- Active only!
```

### 3. "Which ACTIVE doctors work at this facility?"
```sql
SELECT p.NO_PROFISSIONAL, r.CO_CBO, r.DT_ENTRADA
FROM rlEstabEquipeProf r
JOIN tbDadosProfissionalSus p 
  ON r.CO_PROFISSIONAL_SUS = p.CO_PROFISSIONAL_SUS
WHERE r.CO_UNIDADE = '1100012369958'
  AND (r.DT_DESLIGAMENTO IS NULL OR r.DT_DESLIGAMENTO = '')  -- Active only!
```

### 4. "Facilities under renovation (opportunity!)"
```sql
SELECT 
  e.NO_FANTASIA,
  e.NU_TELEFONE,
  m.DS_MOTIVO_DESAB
FROM tbEstabelecimento e
JOIN tbMotivoDesativacao m ON e.CO_MOTIVO_DESAB = m.CD_MOTIVO_DESAB
WHERE e.CO_MOTIVO_DESAB = '03'  -- Under renovation
```

### 5. "Facilities WITHOUT MRI (active only)"
```sql
SELECT e.* FROM tbEstabelecimento e
WHERE NOT EXISTS (
  SELECT 1 FROM rlEstabEquipamento eq
  WHERE eq.CO_UNIDADE = e.CO_UNIDADE
    AND eq.CO_EQUIPAMENTO = 'MRI_CODE'
)
AND (e.CO_MOTIVO_DESAB IS NULL OR e.CO_MOTIVO_DESAB = '')  -- Active only!
```

### 6. "My territory map (active facilities)"
```sql
SELECT 
  e.CO_UNIDADE,
  e.NO_FANTASIA,
  e.NU_LATITUDE,
  e.NU_LONGITUDE,
  m.NO_MUNICIPIO
FROM tbEstabelecimento e
JOIN tbMunicipio m ON e.CO_MUNICIPIO = m.CO_MUNICIPIO
WHERE m.CO_MUNICIPIO IN ('355030', '355040', ...)
  AND (e.CO_MOTIVO_DESAB IS NULL OR e.CO_MOTIVO_DESAB = '')  -- Active only!
```

### 7. "Recently departed doctors (opportunity alert)"
```

---

## 📱 APP FEATURES BY TABLE

| Feature | Tables Needed |
|---------|---------------|
| **Facility Search** | tbEstabelecimento, **tbMotivoDesativacao**, tbMunicipio, tbEstado |
| **Contact Info** | tbEstabelecimento, rlEstabTeleCnes, **check CO_MOTIVO_DESAB** |
| **Map View** | tbEstabelecimento (lat/lng), tbMunicipio, **filter active only** |
| **Find Doctors** | rlEstabEquipeProf, tbDadosProfissionalSus, **check DT_DESLIGAMENTO** |
| **Filter by Specialty** | rlEstabServClass, tbServicoEspecializado, **+ active status** |
| **Equipment List** | rlEstabEquipamento, tbEquipamento, **+ active facilities** |
| **Facility Profile** | tbEstabelecimento + all relationship tables + **deactivation info** |
| **Decision Makers** | rlEstabProfComissao, rlEstabRepresentante, **+ employment status** |
| **Territory Planning** | tbMunicipio, tbEstado, tbEstabelecimento, **active filter** |
| **Lead Scoring** | tbNaturezaJuridica, rlEstabAvaliacao, rlEstabEquipamento, **turnover rate** |
| **Renovation Opportunities** | tbEstabelecimento, **tbMotivoDesativacao (code 03)** ⭐ NEW |

---

## ⚡ PERFORMANCE TIPS

1. **Index These Columns**:
   - CO_UNIDADE (everywhere)
   - CO_PROFISSIONAL_SUS
   - CO_MUNICIPIO
   - CO_ESTADO
   - CO_TIPO_ESTABELECIMENTO
   - CO_SERVICO (in rlEstabServClass)

2. **Pre-join Common Queries**:
   - Create a view joining: Establishment + Municipality + State
   - Cache service/equipment lookups

3. **Materialized Views**:
   - Facility summary (with doctor count, equipment count)
   - Service offerings per facility
   - Territory summary

---

## 📦 IMPLEMENTATION CHECKLIST

### Phase 1 - MVP (Week 1-2)
- [ ] Import tbEstabelecimento
- [ ] Import tbMotivoDesativacao ⭐ CRITICAL
- [ ] Import tbMunicipio, tbEstado
- [ ] Import tbDadosProfissionalSus
- [ ] Import rlEstabEquipeProf
- [ ] Build: Search + Map + Basic Profile
- [ ] **Implement: Active/Deactivated status filtering**

### Phase 2 - Intelligence (Week 3-4)
- [ ] Import rlEstabServClass, tbServicoEspecializado
- [ ] Import rlEstabEquipamento, tbEquipamento
- [ ] Import tbCargaHorariaSus
- [ ] Build: Filters + Equipment Inventory + Doctor Details

### Phase 3 - Business (Week 5-6)
- [ ] Import tbMantenedora, tbNaturezaJuridica
- [ ] Import rlEstabProfComissao
- [ ] Import quality/accreditation tables
- [ ] Build: Decision Makers + Lead Scoring + Account Hierarchy

---

## 🚨 IMPORTANT NOTES

1. **Privacy**: CPF data is masked (XXX.XXX.XXX-XX)
2. **Updates**: Data is from May 2026, will need refresh strategy
3. **Encoding**: Files use Latin1/CP1252 encoding
4. **Size**: Total ~27.8M rows across all tables
5. **Primary Keys**: Use CO_UNIDADE for facilities, CO_PROFISSIONAL_SUS for doctors
6. **⚠️ CRITICAL**: **24.5% of establishments are deactivated** - ALWAYS filter by active status!
7. **⚠️ CRITICAL**: Check DT_DESLIGAMENTO to verify doctors are still employed
8. **Opportunity**: Facilities with code '03' (renovation) = equipment purchase opportunity

---

## 🆘 QUICK LOOKUPS

### Facility Types (Most Common)
- 001 = Basic Health Unit
- 006 = Hospital
- 008 = Emergency Care
- 009 = Pharmacy
- 016 = Ambulatory

### Service Codes (Examples)
- 155 = Orthopedics/Traumatology
- 106 = STD/HIV/AIDS Care
- 124 = Endocrinology
- 135 = Physical Rehabilitation

### Need the full list?
Check the reference tables:
- tbTipoEstabelecimento202605.csv (27 types)
- tbServicoEspecializado202605.csv (73 services)
- tbClassificacaoServico202605.csv (459 detailed classifications)
