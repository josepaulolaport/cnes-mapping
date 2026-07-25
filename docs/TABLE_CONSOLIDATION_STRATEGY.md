# Table Consolidation Strategy for Sales App

## Executive Summary

**Can we reduce tables? YES - from 18 essential to ~12-13 core tables**

**How? Through strategic consolidation of lookup tables**

---

## 📊 CURRENT STATE

**Essential tables for sales app:** 18
- 6 large data tables (>100K rows)
- 12 small-medium reference/lookup tables (<100K rows)

---

## ✅ CONSOLIDATION STRATEGY

### **Option 1: AGGRESSIVE (Recommended for MVP)**
**Result: 12 core tables** (33% reduction)

**Consolidate these 6 small lookups into 1 "Reference Data" table:**

```sql
CREATE TABLE tb_reference_data (
  reference_type VARCHAR(50),  -- 'establishment_type', 'deactivation_reason', etc.
  code VARCHAR(20),
  description VARCHAR(500),
  extra_field_1 VARCHAR(200),  -- flexible for different types
  extra_field_2 VARCHAR(200),
  PRIMARY KEY (reference_type, code)
);
```

**Tables to merge:**
1. `tbTipoEstabelecimento` (27 rows) → type = 'establishment_type'
2. `tbMotivoDesativacao` (14 rows) → type = 'deactivation_reason'
3. `tbServicoEspecializado` (73 rows) → type = 'specialized_service'
4. `tbEquipamento` (144 rows) → type = 'equipment_type'
5. `tbConselhoClasse` (12 rows) → type = 'professional_council'
6. `tbTipoEquipamento` (12 rows) → type = 'equipment_category'

**Savings:** 6 tables → 1 table

---

### **Option 2: MODERATE**
**Result: 15 core tables** (17% reduction)

**Keep frequently joined tables separate, merge rarely used:**

**Create "lookup_codes" table for these 3:**
- `tbMotivoDesativacao` → merged
- `tbConselhoClasse` → merged  
- `tbTipoEquipamento` → merged

**Keep separate (frequently used):**
- `tbTipoEstabelecimento` (used in every facility query)
- `tbServicoEspecializado` (used in specialty filtering)
- `tbEquipamento` (larger table, complex relationships)

**Savings:** 3 tables consolidated

---

### **Option 3: CONSERVATIVE (NOT Recommended)**
**Keep all 18 tables separate**

**Why NOT recommended:**
- More tables to maintain
- More complex queries
- Larger database schema
- No real benefit for a sales app

---

## 🚫 TABLES THAT **CANNOT** BE MERGED

### **1. Large Data Tables** (Must stay separate)
```
✗ tbEstabelecimento (623K rows) - Core facility data
✗ tbDadosProfissionalSus (7.7M rows) - Core professional data
✗ rlEstabEquipeProf (870K rows) - Critical relationships
✗ tbCargaHorariaSus (6.6M rows) - Working hours
✗ rlEstabServClass (1.4M rows) - Services mapping
✗ rlEstabEquipamento (1.3M rows) - Equipment mapping
```

**Why?** 
- Too large to merge efficiently
- Different update frequencies
- Different access patterns
- Core entity tables (normalized design)

### **2. Geographic Tables** (Should stay separate)
```
✗ tbMunicipio (5,607 rows)
✗ tbEstado (27 rows)
```

**Why?**
- Frequently joined in queries
- Standard geographic reference
- Used for indexing/filtering
- Better query performance when separate

### **3. Classification Tables with Complex Relationships**
```
✗ tbClassificacaoServico (459 rows)
  - Has composite keys
  - Links services to classifications
  - Complex many-to-many relationships
```

---

## 📋 PRACTICAL IMPLEMENTATION

### **Phase 1: Quick Wins (Immediate)**
Merge these 3 small tables into `lookup_codes`:

```sql
CREATE TABLE lookup_codes (
  lookup_type VARCHAR(30) PRIMARY KEY,
  code VARCHAR(10) PRIMARY KEY,
  description VARCHAR(300),
  active BOOLEAN DEFAULT TRUE
);

-- Insert from multiple sources
INSERT INTO lookup_codes 
  SELECT 'deactivation_reason', CD_MOTIVO_DESAB, DS_MOTIVO_DESAB, TRUE
  FROM tbMotivoDesativacao;

INSERT INTO lookup_codes
  SELECT 'professional_council', CO_CONSELHO_CLASSE, DS_CONSELHO_CLASSE, TRUE  
  FROM tbConselhoClasse;

INSERT INTO lookup_codes
  SELECT 'equipment_type', CO_TIPO_EQUIPAMENTO, DS_TIPO_EQUIPAMENTO, TRUE
  FROM tbTipoEquipamento;
```

**Result:** 18 tables → 16 tables

**Impact:** Minimal risk, easy rollback, immediate simplification

---

### **Phase 2: Extended Consolidation (After testing)**
Add more lookups to the consolidated table:

```sql
-- Add more types
INSERT INTO lookup_codes
  SELECT 'establishment_type', CO_TIPO_ESTABELECIMENTO, DS_TIPO_ESTABELECIMENTO, TRUE
  FROM tbTipoEstabelecimento;

INSERT INTO lookup_codes  
  SELECT 'service_type', CO_SERVICO_ESPECIALIZADO, DS_SERVICO_ESPECIALIZADO, TRUE
  FROM tbServicoEspecializado;
```

**Result:** 16 tables → 13 tables

---

## ⚖️ PROS & CONS

### **Consolidation PROS:**
✅ Fewer tables to manage
✅ Simpler database schema
✅ Easier deployment
✅ Single place for lookup data
✅ Easier to add new lookup types
✅ Less JOIN complexity for simple lookups

### **Consolidation CONS:**
⚠️ Slightly more complex queries (need WHERE type = 'X')
⚠️ Mixing different domains in one table
⚠️ Harder to add type-specific columns
⚠️ May need application-level caching
⚠️ Foreign key constraints more complex

---

## 💡 RECOMMENDED APPROACH FOR YOUR SALES APP

### **Start with Option 1 (Aggressive - 12 tables)**

**Why?**
1. **Sales app = read-heavy** - lookups are cached anyway
2. **Simpler deployment** - fewer tables to create/maintain
3. **Easier updates** - single table for all codes
4. **Modern pattern** - microservices use key-value stores
5. **Future-proof** - easy to add new lookup types

### **Core 12 Tables Structure:**

**1. MAIN ENTITIES (6 tables)**
```
1. tbEstabelecimento - Facilities
2. tbDadosProfissionalSus - Professionals  
3. tbMunicipio - Municipalities
4. tbEstado - States
5. tbClassificacaoServico - Service classifications (complex relationships)
6. tb_reference_data - ALL LOOKUPS CONSOLIDATED ⭐
```

**2. RELATIONSHIPS (6 tables)**
```
7. rlEstabEquipeProf - Professionals at facilities
8. rlEstabServClass - Services at facilities
9. rlEstabEquipamento - Equipment at facilities
10. tbCargaHorariaSus - Professional working hours (optional for MVP)
11. rlEstabProfComissao - Decision makers (optional for MVP)
12. tbMantenedora - Facility owners (optional for MVP)
```

---

## 🎯 MIGRATION STRATEGY

### **Step 1: Create Consolidated Table**
```sql
CREATE TABLE tb_reference_data (
  ref_type VARCHAR(50) NOT NULL,
  code VARCHAR(20) NOT NULL,
  description VARCHAR(500),
  extra_info JSON,  -- For type-specific data
  display_order INT,
  active BOOLEAN DEFAULT TRUE,
  PRIMARY KEY (ref_type, code),
  INDEX idx_type (ref_type),
  INDEX idx_active (active)
);
```

### **Step 2: Migrate Data**
```sql
-- Migrate all lookup tables
INSERT INTO tb_reference_data (ref_type, code, description)
SELECT 'establishment_type', CO_TIPO_ESTABELECIMENTO, DS_TIPO_ESTABELECIMENTO
FROM tbTipoEstabelecimento;

-- Repeat for each lookup table...
```

### **Step 3: Update Application Queries**
```sql
-- OLD:
SELECT e.*, t.DS_TIPO_ESTABELECIMENTO
FROM tbEstabelecimento e
JOIN tbTipoEstabelecimento t ON e.CO_TIPO_ESTABELECIMENTO = t.CO_TIPO_ESTABELECIMENTO;

-- NEW:
SELECT e.*, r.description as tipo_estabelecimento
FROM tbEstabelecimento e  
JOIN tb_reference_data r ON r.ref_type = 'establishment_type'
  AND r.code = e.CO_TIPO_ESTABELECIMENTO;
```

### **Step 4: Cache in Application**
```python
# Load all reference data once at startup
reference_cache = {
  'establishment_type': {},
  'deactivation_reason': {},
  # ... etc
}

# Use in-memory lookups
facility_type_name = reference_cache['establishment_type'][facility.type_code]
```

---

## 📊 COMPARISON TABLE

| Aspect | 18 Separate Tables | 12 Consolidated Tables |
|--------|-------------------|----------------------|
| **Total Tables** | 18 | 12 (-33%) |
| **Schema Complexity** | High | Medium |
| **Query Complexity** | Simple JOINs | Need type filter |
| **Maintenance** | 18 tables to manage | 12 tables to manage |
| **Deployment** | More DDL scripts | Fewer DDL scripts |
| **Code Changes** | Direct table refs | Type + code refs |
| **Performance** | Slightly better | Slightly worse (negligible with caching) |
| **Flexibility** | Add new table | Add new type (easier!) |
| **Best For** | Traditional RDBMS apps | Modern microservices |

---

## ✅ FINAL RECOMMENDATION

**For your sales app MVP:** Go with **12 core tables** (Option 1)

**Consolidate these 6:**
1. tbTipoEstabelecimento
2. tbMotivoDesativacao  
3. tbServicoEspecializado
4. tbEquipamento
5. tbConselhoClasse
6. tbTipoEquipamento

**Into: `tb_reference_data`**

**Keep separate:**
- All large data tables (>10K rows)
- Geographic tables (performance)
- Complex relationship tables

**Benefits:**
- ✅ 33% fewer tables
- ✅ Simpler codebase
- ✅ Easier to add new lookup types
- ✅ Standard microservices pattern
- ✅ Better for API/mobile apps

**Trade-offs:**
- ⚠️ Slightly more complex queries
- ⚠️ Need application-level caching
- ⚠️ Mixed domains in one table

**Mitigations:**
- Use Redis/memory cache for lookups
- Create views for common queries
- Index on (ref_type, code) for performance

---

## 🚀 IMPLEMENTATION TIME

**Consolidation effort:** 4-6 hours
- Create consolidated table: 30 min
- Migrate data: 1 hour
- Update queries: 2-3 hours
- Testing: 1-2 hours

**Worth it?** YES - saves ongoing maintenance time

---

## 📝 CONCLUSION

**YES, you can reduce from 18 to 12 tables** without losing functionality.

The small lookup tables are perfect candidates for consolidation because:
- They're small (fast to query)
- They're rarely updated
- They're used for display/filtering only
- They have similar structure (code + description)

The large data and relationship tables **must stay separate** due to:
- Size (millions of rows)
- Complex relationships
- Different access patterns
- Performance requirements

**Recommended action:** Start with aggressive consolidation for MVP, can always split later if needed.
