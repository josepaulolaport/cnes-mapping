# Sales-Relevant Tables for CNES Database
## Complete Guide for Medical Equipment/Pharma/Supplies Sales App

---

## 🎯 CORE ESTABLISHMENT DATA (Essential)

### **tbEstabelecimento202605.csv** ⭐⭐⭐ CRITICAL
- **623,208 rows | 56 columns**
- **Why**: Master table with ALL establishment data
- **Sales Value**:
  - Company names (NO_RAZAO_SOCIAL, NO_FANTASIA)
  - Full addresses (street, number, complement, neighborhood, ZIP)
  - Contact info (phone, fax, email, website)
  - Tax IDs (CNPJ, CPF)
  - Facility type and classification
  - Operating hours indicator
  - Geo-coordinates (latitude/longitude) for routing
  - Manager/director info (CO_CPFDIRETORCLN)
  - Legal status (CO_NATUREZA_JUR)
- **Primary Key**: CO_UNIDADE

### **tbTipoEstabelecimento202605.csv** ⭐⭐⭐
- **27 rows | 3 columns**
- **Why**: Decode facility types
- **Sales Value**:
  - Know if it's a hospital, clinic, ambulatory, pharmacy, lab, etc.
  - Focus on facility types that buy your products
- **Examples**: Hospital (006), Pharmacy (009), Ambulatory (016)

### **tbMotivoDesativacao202605.csv** ⭐⭐⭐ CRITICAL
- **14 rows | 2 columns**
- **Why**: Deactivation reason lookup table
- **Sales Value**:
  - Filter out closed/inactive facilities
  - Identify temporarily closed facilities (renovation = equipment opportunity)
  - Understand why facility closed (court order, closure, moved, etc.)
  - Avoid wasting time on permanently closed locations
- **Key Codes**:
  - 01-04: Temporary deactivation (potential opportunities)
  - 05, 10: Permanent closure (avoid targeting)
  - 06, 08: Inactive due to no updates (verify status)

---

## 🔴 DEACTIVATION TRACKING (Critical for Sales)

### **ESTABLISHMENT STATUS**
- **Field**: `CO_MOTIVO_DESAB` in `tbEstabelecimento`
- **Active**: NULL or empty string ✅
- **Deactivated**: Contains reason code ❌
- **Statistics**: ~24.5% of establishments are deactivated
- **Lookup**: `tbMotivoDesativacao` for reason descriptions

**Deactivation Categories:**
```
TEMPORARY (Potential Opportunities):
  01 - Deactivated by health surveillance
  02 - Deactivated by court order
  03 - Under renovation ⭐ (equipment needs!)
  04 - Other reasons

PERMANENT (Avoid Targeting):
  05 - Definitively closed by court order
  10 - Business closure

ADMINISTRATIVE (Verify Status):
  06 - No updates for >1 year
  08 - No updates for >6 months
  07 - Registered incorrectly
```

### **PROFESSIONAL STATUS**
- **Field**: `DT_DESLIGAMENTO` in `rlEstabEquipeProf`
- **Active**: NULL or empty ✅
- **Terminated**: Has date value ❌
- **Also Available**: `DT_ENTRADA` (start date)
- **Statistics**: ~0.9% of professional links have termination dates

**Sales Use Cases:**
- Track doctor turnover rate at facilities
- Identify recently departed doctors (transition opportunities)
- Find long-term staff (established decision makers)
- Verify current contacts are still at facility

---

## 👨‍⚕️ DOCTOR & PROFESSIONAL DATA (Essential)

### **tbDadosProfissionalSus202605.csv** ⭐⭐⭐ CRITICAL
- **7,761,583 rows | 11 columns**
- **Why**: Master table of ALL healthcare professionals
- **Sales Value**:
  - Professional names (NO_PROFISSIONAL)
  - CPF (partially masked for privacy)
  - CNS (health card number)
  - Unique identifier (CO_PROFISSIONAL_SUS)
- **Primary Key**: CO_PROFISSIONAL_SUS

### **rlEstabEquipeProf202605.csv** ⭐⭐⭐ CRITICAL
- **870,453 rows | 21 columns**
- **Why**: Links doctors to establishments
- **Sales Value**:
  - Which doctors work at which facilities
  - Occupation code (CO_CBO) - tells you specialty
  - Employment dates (DT_ENTRADA, DT_DESLIGAMENTO)
  - SUS vs private practice indicator
  - Team associations
- **Keys**: CO_UNIDADE + CO_PROFISSIONAL_SUS + CO_CBO

### **tbCargaHorariaSus202605.csv** ⭐⭐
- **6,653,255 rows | 18 columns**
- **Why**: Working hours and professional details
- **Sales Value**:
  - How many hours doctor works at facility
  - Professional council registration (CRM, CRO, etc.)
  - Registration number (NU_REGISTRO)
  - State of registration (SG_UF_CRM)
  - Multiple work locations per doctor
- **Keys**: CO_UNIDADE + CO_PROFISSIONAL_SUS + CO_CBO

### **tbConselhoClasse202605.csv** ⭐⭐
- **Small reference table**
- **Why**: Decode professional councils
- **Sales Value**: Know if it's CRM (medical), CRO (dental), CRF (pharmacy), etc.

---

## 🏥 FACILITY CAPABILITIES (High Priority)

### **rlEstabServClass202605.csv** ⭐⭐⭐ CRITICAL
- **1,442,080 rows | 13 columns**
- **Why**: All services/specialties offered by each facility
- **Sales Value**:
  - Know if facility does orthopedics, cardiology, oncology, etc.
  - Target facilities based on specialty needs
  - Understand service portfolio
  - Ambulatory vs hospital service indicators
- **Keys**: CO_UNIDADE + CO_SERVICO + CO_CLASSIFICACAO

### **tbServicoEspecializado202605.csv** ⭐⭐⭐
- **73 rows | 2 columns**
- **Why**: Master list of specialized services
- **Sales Value**: 
  - Filter facilities by service type
  - Examples: Orthopedics (155), Cardiology, Oncology, etc.

### **tbClassificacaoServico202605.csv** ⭐⭐⭐
- **459 rows | 3 columns**
- **Why**: Detailed service classifications
- **Sales Value**: More granular service filtering (pediatric orthopedics vs adult)

### **rlEstabEquipamento202605.csv** ⭐⭐⭐ CRITICAL
- **1,348,380 rows | 10 columns**
- **Why**: ALL equipment at each facility
- **Sales Value**:
  - Know what equipment they already have
  - Identify upgrade/replacement opportunities
  - Equipment status (in use, inactive, maintenance)
  - Quantity of each equipment type
- **Keys**: CO_UNIDADE + CO_EQUIPAMENTO + CO_TIPO_EQUIPAMENTO

### **tbEquipamento202605.csv** ⭐⭐⭐
- **Small reference table**
- **Why**: Decode equipment types
- **Sales Value**: 
  - Know exact equipment models/types
  - Cross-reference with your product catalog

### **tbLeito202605.csv** ⭐⭐
- **69 rows | 3 columns**
- **Why**: Hospital bed types
- **Sales Value**: 
  - Facility size indicator
  - Type of beds (ICU, surgical, pediatric) = types of equipment needed

### **rlEstabInstFisiAssist202605.csv** ⭐⭐
- **Large table**
- **Why**: Physical infrastructure for patient care
- **Sales Value**: Understand facility infrastructure capacity

---

## 📍 GEOGRAPHIC & TERRITORY DATA (High Priority)

### **tbMunicipio202605.csv** ⭐⭐⭐ CRITICAL
- **5,607 rows | 13 columns**
- **Why**: All Brazilian municipalities
- **Sales Value**:
  - Territory assignment
  - Filter establishments by municipality
  - Route planning
- **Primary Key**: CO_MUNICIPIO

### **tbEstado202605.csv** ⭐⭐⭐ CRITICAL
- **27 rows | 2 columns**
- **Why**: Brazilian states
- **Sales Value**:
  - Regional territory management
  - State-level filtering
- **Primary Key**: CO_SIGLA_ESTADO

### **tbArea202605.csv** ⭐
- **Health service areas**
- **Sales Value**: Sub-municipality territory divisions

---

## 💼 BUSINESS & ADMINISTRATIVE INFO (Medium-High Priority)

### **tbMantenedora202605.csv** ⭐⭐⭐
- **Why**: Organizations that own/manage facilities
- **Sales Value**:
  - Identify corporate groups/chains
  - Target decision makers at parent company
  - Understand ownership structure
  - CNPJ of maintainer organization

### **tbNaturezaJuridica202605.csv** ⭐⭐
- **Small reference table**
- **Why**: Legal entity type
- **Sales Value**:
  - Public vs private vs nonprofit
  - Different sales approaches/pricing
  - Purchasing authority differs by type

### **tbGestao202605.csv** ⭐⭐
- **Management types**
- **Sales Value**: 
  - Understand governance model
  - Know who makes purchasing decisions

### **rlEstabProfComissao202605.csv** ⭐⭐
- **64,958 rows | 10 columns**
- **Why**: Professionals in committees/commissions
- **Sales Value**:
  - Decision makers and influencers
  - Committee members who approve purchases
  - Clinical directors, administrators

### **rlEstabRepresentante202605.csv** ⭐⭐
- **Why**: Official representatives at facilities
- **Sales Value**: 
  - Key contacts
  - Authorized decision makers

---

## ⏰ OPERATIONAL DETAILS (Medium Priority)

### **tbEstabHorarioAtend202605.csv** ⭐⭐
- **Operating hours**
- **Sales Value**:
  - Best times to visit
  - 24/7 facilities = higher volume/needs
  - Plan sales calls during off-peak hours

### **tbTurnoAtendimento202605.csv** ⭐
- **Service shift types**
- **Sales Value**: Operating schedule reference

### **tbEstabContrato202605.csv** ⭐
- **Contracts and agreements**
- **Sales Value**: 
  - Existing vendor relationships
  - Contract expiration dates (opportunity timing)

---

## 🏆 QUALITY & ACCREDITATION (Medium Priority)

### **tbAvaliacao202605.csv** ⭐⭐
- **Quality evaluations**
- **Sales Value**:
  - Accredited facilities = higher standards = premium products
  - Quality certifications indicate purchasing power

### **tbClassificacaoAval202605.csv** ⭐⭐
- **Evaluation classifications**
- **Sales Value**: Decode accreditation levels

### **tbInstituicaoAvaliadora202605.csv** ⭐
- **Accrediting organizations**
- **Sales Value**: Know certification types (ONA, CBA, etc.)

### **rlEstabAvaliacao202605.csv** ⭐⭐
- **Links facilities to their accreditations**
- **Sales Value**: Filter by certified facilities

---

## 💊 PHARMACY & MEDICATION (If selling pharma)

### **tbConvenio202605.csv** ⭐⭐
- **Insurance/health plan agreements**
- **Sales Value**:
  - Which plans facility accepts
  - Formulary implications
  - Reimbursement relationships

### **tbBanco202605.csv** ⭐
- **Bank information**
- **Sales Value**: Financial relationships for payment processing

---

## 🔗 IMPORTANT RELATIONSHIP TABLES

### **rlEstabComplementar202605.csv** ⭐
- **Additional establishment data**
- **Sales Value**: Extra operational details

### **rlEstabEndCompl202605.csv** ⭐
- **Additional address information**
- **Sales Value**: More detailed location data

### **rlEstabTeleCnes202605.csv** ⭐⭐
- **Telephone directory**
- **Sales Value**: Contact numbers for different departments/purposes

### **rlEstabOrgParc202605.csv** ⭐
- **Partner organizations**
- **Sales Value**: Business relationships and network

### **tbEstabAtivSecundaria202605.csv** ⭐⭐
- **Secondary activities**
- **Sales Value**: Additional services beyond primary classification

---

## 📊 REFERENCE/LOOKUP TABLES (Support)

### **tbAtividade202605.csv** ⭐
- **Healthcare activities catalog**
- **Sales Value**: Understand service offerings

### **tbTipoUnidade202605.csv** ⭐
- **Unit types**
- **Sales Value**: Facility classification

### **tbSegmento202605.csv** ⭐
- **Market segments**
- **Sales Value**: Business categorization

### **tbTipoAbrangencia202605.csv** ⭐
- **Coverage type/scope**
- **Sales Value**: Service area reach

---

## 🎯 PRIORITY MATRIX FOR SALES APP

### **MUST HAVE (Implementation Priority 1)**
1. `tbEstabelecimento` - Core facility data
2. `tbMotivoDesativacao` - Deactivation reasons ⭐ NEW
3. `tbDadosProfissionalSus` - Doctor names and IDs
4. `rlEstabEquipeProf` - Link doctors to facilities
5. `tbMunicipio` - Territory management
6. `tbEstado` - Regional filtering
7. `rlEstabServClass` - Facility specialties
8. `rlEstabEquipamento` - Equipment inventory
9. `tbServicoEspecializado` - Service types
10. `tbTipoEstabelecimento` - Facility types

### **SHOULD HAVE (Implementation Priority 2)**
11. `tbCargaHorariaSus` - Professional details & hours
11. `tbClassificacaoServico` - Detailed service classification
12. `tbEquipamento` - Equipment catalog
13. `tbMantenedora` - Ownership/management
14. `tbNaturezaJuridica` - Legal entity type
15. `rlEstabProfComissao` - Decision makers
16. `tbEstabHorarioAtend` - Operating hours
17. `tbConselhoClasse` - Professional councils

### **NICE TO HAVE (Implementation Priority 3)**
18. `tbMotivoDesativEquipe` - Team deactivation reasons
19. `tbAvaliacao` - Quality certifications
19. `rlEstabAvaliacao` - Accreditation links
20. `tbConvenio` - Insurance agreements
21. `rlEstabRepresentante` - Representatives
22. `tbLeito` - Bed capacity
23. All other reference/lookup tables

---

## 💡 KEY INSIGHTS FOR YOUR APP

### **Core Data Model**
```
tbEstabelecimento (facility)
    ├── Contact info, address, geo-coordinates
    ├── Facility type and classification
    └── Links to:
        ├── rlEstabServClass (what specialties?)
        ├── rlEstabEquipamento (what equipment?)
        ├── rlEstabEquipeProf → tbDadosProfissionalSus (which doctors?)
        ├── tbMantenedora (who owns it?)
        └── tbMunicipio → tbEstado (where is it?)
```

### **Sales Workflow Features**

**1. Lead Generation**
- Filter by: municipality, state, facility type, specialty, equipment, **active status**
- Find: **active** orthopedic clinics in São Paulo with existing X-ray equipment
- Exclude: permanently closed facilities
- Target: temporarily closed facilities under renovation (equipment needs)

**2. Contact Discovery**
- Facility: address, phone, email, website, manager, **deactivation status**
- Doctors: names, specialties, registration numbers, working hours, **employment status**
- Verify: contacts are still active at facility (check termination date)

**3. Intelligence**
- What equipment do they have?
- What services do they offer?
- Who owns/manages the facility?
- Quality certifications?
- How many **active** doctors work there?
- Doctor turnover rate (stability indicator)
- Facility operational status and history

**4. Territory Management**
- Group by municipality/state
- Map view with geo-coordinates
- Route optimization

**5. Targeting**
- Find **active** orthopedists at **operating** hospitals in Region X
- Identify **active** facilities without specific equipment
- Target recently accredited facilities
- Focus on large, **stable** facilities (multiple doctors/low turnover)
- Opportunity: facilities under renovation (temporarily closed for upgrades)
- Alert: recently departed doctors = potential equipment changes

---

## 📋 TOTAL TABLE COUNT

**Essential Tables**: 18 (added deactivation tracking)
**Recommended Tables**: 24  
**Total Relevant Tables**: ~41 out of 109

**Not Needed**: Indigenous health (Aldeia, Dsei, Etnia), very specialized programs, internal CNES administration tables

---

## 🎯 CRITICAL SALES QUERIES

### **1. Find Only ACTIVE Facilities**
```sql
SELECT * FROM tbEstabelecimento
WHERE (CO_MOTIVO_DESAB IS NULL OR CO_MOTIVO_DESAB = '')
  -- This ensures you only target operating facilities
```

### **2. Find Only ACTIVE Doctors at Facility**
```sql
SELECT 
  p.NO_PROFISSIONAL,
  p.CO_CPF,
  r.CO_CBO,
  r.DT_ENTRADA
FROM rlEstabEquipeProf r
JOIN tbDadosProfissionalSus p 
  ON r.CO_PROFISSIONAL_SUS = p.CO_PROFISSIONAL_SUS
WHERE r.CO_UNIDADE = 'FACILITY_ID'
  AND (r.DT_DESLIGAMENTO IS NULL OR r.DT_DESLIGAMENTO = '')
  -- Only currently employed doctors
```

### **3. Renovation Opportunities (Temporarily Closed)**
```sql
SELECT 
  e.NO_FANTASIA,
  e.NU_TELEFONE,
  e.NO_EMAIL,
  m.DS_MOTIVO_DESAB
FROM tbEstabelecimento e
JOIN tbMotivoDesativacao m ON e.CO_MOTIVO_DESAB = m.CD_MOTIVO_DESAB
WHERE e.CO_MOTIVO_DESAB = '03'  -- Under renovation
  -- These facilities may need equipment upgrades!
```

### **4. High Turnover Facilities (Potential Instability)**
```sql
SELECT 
  e.NO_FANTASIA,
  COUNT(CASE WHEN r.DT_DESLIGAMENTO IS NOT NULL THEN 1 END) as departed_count,
  COUNT(*) as total_professionals,
  ROUND(COUNT(CASE WHEN r.DT_DESLIGAMENTO IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 2) as turnover_rate
FROM tbEstabelecimento e
JOIN rlEstabEquipeProf r ON e.CO_UNIDADE = r.CO_UNIDADE
WHERE (e.CO_MOTIVO_DESAB IS NULL OR e.CO_MOTIVO_DESAB = '')
GROUP BY e.CO_UNIDADE, e.NO_FANTASIA
HAVING COUNT(*) > 10  -- Only facilities with 10+ professionals
ORDER BY turnover_rate DESC
```

### **5. Recently Departed Doctors (Transition Opportunity)**
```sql
SELECT 
  e.NO_FANTASIA as facility,
  p.NO_PROFISSIONAL as doctor_name,
  r.DT_DESLIGAMENTO as departure_date,
  r.CO_CBO as occupation
FROM rlEstabEquipeProf r
JOIN tbEstabelecimento e ON r.CO_UNIDADE = e.CO_UNIDADE
JOIN tbDadosProfissionalSus p ON r.CO_PROFISSIONAL_SUS = p.CO_PROFISSIONAL_SUS
WHERE r.DT_DESLIGAMENTO >= '01/12/2025'  -- Last 6 months
  AND (e.CO_MOTIVO_DESAB IS NULL OR e.CO_MOTIVO_DESAB = '')
ORDER BY r.DT_DESLIGAMENTO DESC
```

---

## ⚠️ DATA QUALITY NOTES

### **Deactivation Status**
- **24.5% of establishments are deactivated** - Always filter by active status
- Deactivation codes indicate temporary vs permanent closure
- Some "deactivated" facilities may still have active professional records (data lag)

### **Professional Turnover**
- **0.9% of professional links have termination dates** - Most records are current
- Missing termination date = currently employed (or data not updated)
- Check both facility AND professional status for accurate contact info

### **Data Freshness**
- Data from May 2026
- Some deactivated facilities may have reopened
- Some "active" facilities may have recently closed
- Implement regular data refresh strategy

---
