# Handling Updates with Consolidated Tables

## Key Finding: Lookup Tables Don't Track Updates! ✅

**None of the 6 lookup tables have update tracking fields:**
- No `DT_ATUALIZACAO` (update date)
- No `CO_USUARIO` (user who updated)
- No version numbers
- No timestamps

**What this means:**
These are **static reference data** that rarely change. Perfect for consolidation!

---

## 📊 UPDATE FREQUENCY ANALYSIS

### **Types of Changes in Government Reference Data:**

**1. RARE (Once per year or less) - 90% of tables**
- New establishment types (e.g., new clinic category)
- New equipment types (new medical device category)
- New deactivation reasons (new regulatory reason)

**Examples:**
- tbTipoEstabelecimento: Hasn't changed in years (27 types)
- tbConselhoClasse: Only changes when new profession is regulated

**2. OCCASIONAL (Few times per year) - 9% of tables**
- Equipment catalog updates (new devices)
- Service classifications (new specialties)

**Examples:**
- tbEquipamento: Adds new equipment models
- tbServicoEspecializado: New medical specialties (rare)

**3. FREQUENT (Monthly) - 1% of tables**
- None of these lookup tables change frequently!

---

## ✅ CONSOLIDATED TABLES ARE **EASIER** TO UPDATE

### **Comparison: Separate vs Consolidated**

#### **SEPARATE TABLES (Current - 18 tables)**

**When CNES releases new data (e.g., June 2026 → July 2026):**

```bash
# You need to:
1. Download 6 different CSV files
2. Truncate 6 tables
3. Import 6 files
4. Verify 6 table structures
5. Test 6 different queries
6. Deploy 6 table updates

# Example:
TRUNCATE tbTipoEstabelecimento;
LOAD DATA 'tbTipoEstabelecimento202607.csv' INTO tbTipoEstabelecimento;

TRUNCATE tbMotivoDesativacao;
LOAD DATA 'tbMotivoDesativacao202607.csv' INTO tbMotivoDesativacao;

# ... repeat 4 more times
```

#### **CONSOLIDATED TABLE (Recommended - 12 tables)**

**When CNES releases new data:**

```bash
# You need to:
1. Download 6 CSV files
2. Run ONE update script
3. Verify ONE table
4. Test ONE query pattern
5. Deploy ONE table update

# Example - Single script handles all:
python update_reference_data.py --source-folder CNES_202607/
```

**Update Script:**
```python
def update_reference_data(source_folder):
    """Update all reference data from CNES monthly release"""
    
    # Map of source files to reference types
    mappings = {
        'tbTipoEstabelecimento202607.csv': {
            'type': 'establishment_type',
            'code_col': 'CO_TIPO_ESTABELECIMENTO',
            'desc_col': 'DS_TIPO_ESTABELECIMENTO'
        },
        'tbMotivoDesativacao202607.csv': {
            'type': 'deactivation_reason',
            'code_col': 'CD_MOTIVO_DESAB',
            'desc_col': 'DS_MOTIVO_DESAB'
        },
        # ... 4 more mappings
    }
    
    with transaction():
        # Delete old data by type
        for file, config in mappings.items():
            db.execute(f"DELETE FROM tb_reference_data WHERE ref_type = '{config['type']}'")
            
            # Import new data
            df = pd.read_csv(f"{source_folder}/{file}")
            for _, row in df.iterrows():
                db.execute("""
                    INSERT INTO tb_reference_data (ref_type, code, description, last_updated)
                    VALUES (?, ?, ?, NOW())
                """, config['type'], row[config['code_col']], row[config['desc_col']])
        
        commit()
```

**Advantages:**
✅ Single script handles all updates
✅ One transaction for consistency
✅ One place to test
✅ Easy rollback if needed
✅ Can track update date per type

---

## 🔄 UPDATE STRATEGIES

### **Strategy 1: FULL REPLACEMENT (Recommended)**

```sql
-- Delete all records of specific type
DELETE FROM tb_reference_data WHERE ref_type = 'establishment_type';

-- Insert new data
INSERT INTO tb_reference_data (ref_type, code, description, updated_at)
SELECT 'establishment_type', CO_TIPO_ESTABELECIMENTO, DS_TIPO_ESTABELECIMENTO, NOW()
FROM staging_tipo_estabelecimento;
```

**Pros:**
✅ Clean slate
✅ No orphaned records
✅ Simple to implement

**Cons:**
⚠️ Downtime during update (use transaction)

---

### **Strategy 2: UPSERT (More Complex)**

```sql
-- Insert or update
INSERT INTO tb_reference_data (ref_type, code, description, updated_at)
VALUES ('establishment_type', '006', 'Hospital', NOW())
ON DUPLICATE KEY UPDATE 
    description = VALUES(description),
    updated_at = NOW();
```

**Pros:**
✅ No downtime
✅ Preserves existing data
✅ Tracks what changed

**Cons:**
⚠️ Doesn't detect deletions
⚠️ More complex logic

---

### **Strategy 3: VERSIONED UPDATES (Enterprise)**

```sql
CREATE TABLE tb_reference_data (
  ref_type VARCHAR(50),
  code VARCHAR(20),
  description VARCHAR(500),
  version_date DATE,          -- NEW: Track versions
  active BOOLEAN DEFAULT TRUE, -- NEW: Soft delete
  PRIMARY KEY (ref_type, code, version_date)
);

-- Keep history
INSERT INTO tb_reference_data (ref_type, code, description, version_date, active)
VALUES ('establishment_type', '006', 'Hospital', '2026-07-01', TRUE);

-- Old version marked inactive
UPDATE tb_reference_data 
SET active = FALSE 
WHERE ref_type = 'establishment_type' AND version_date < '2026-07-01';
```

**Pros:**
✅ Full audit trail
✅ Can rollback to any version
✅ See what changed over time

**Cons:**
⚠️ More storage
⚠️ More complex queries
⚠️ Overkill for stable data

---

## 🎯 RECOMMENDED APPROACH

### **For Your Sales App: Strategy 1 (Full Replacement)**

**Why?**
1. **Simple** - Easy to implement and maintain
2. **Fast** - Quick updates (small data)
3. **Clean** - No orphaned records
4. **Sufficient** - Lookup data rarely changes

**Implementation:**

```python
class ReferenceDataUpdater:
    """Handle CNES reference data updates"""
    
    def update_from_cnes_release(self, release_folder: str):
        """Update all reference data from CNES monthly release"""
        
        # Define mappings
        mappings = self._get_mappings()
        
        # Start transaction
        with db.transaction():
            for file_pattern, config in mappings.items():
                # Find file (handles date suffixes)
                file = self._find_file(release_folder, file_pattern)
                
                if file:
                    self._update_reference_type(config['type'], file, config)
                else:
                    logger.warning(f"File not found: {file_pattern}")
            
            # Commit all updates together
            db.commit()
            logger.info("Reference data updated successfully")
    
    def _update_reference_type(self, ref_type: str, file: str, config: dict):
        """Update one reference type"""
        
        # Delete existing
        db.execute("DELETE FROM tb_reference_data WHERE ref_type = ?", ref_type)
        
        # Load new data
        df = pd.read_csv(file, encoding='latin1', delimiter=';')
        
        # Insert new records
        for _, row in df.iterrows():
            db.execute("""
                INSERT INTO tb_reference_data 
                (ref_type, code, description, updated_at, source_file)
                VALUES (?, ?, ?, NOW(), ?)
            """, 
            ref_type,
            row[config['code_col']].strip(),
            row[config['desc_col']].strip(),
            file
            )
        
        logger.info(f"Updated {ref_type}: {len(df)} records")
```

---

## 📋 ENHANCED CONSOLIDATED TABLE STRUCTURE

**With update tracking:**

```sql
CREATE TABLE tb_reference_data (
  ref_type VARCHAR(50) NOT NULL,
  code VARCHAR(20) NOT NULL,
  description VARCHAR(500) NOT NULL,
  extra_data JSON,                    -- For type-specific fields
  
  -- UPDATE TRACKING
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW() ON UPDATE NOW(),
  source_file VARCHAR(100),           -- Which CNES file it came from
  cnes_version VARCHAR(20),           -- e.g., '202607' for July 2026
  
  -- METADATA
  display_order INT,
  active BOOLEAN DEFAULT TRUE,
  notes TEXT,
  
  PRIMARY KEY (ref_type, code),
  INDEX idx_type (ref_type),
  INDEX idx_version (cnes_version),
  INDEX idx_updated (updated_at)
);
```

**Benefits:**
- Track when each type was last updated
- Know which CNES version you're running
- Can identify stale data
- Audit trail for changes

---

## 🔍 DETECTING CHANGES

### **After Update, Check What Changed:**

```sql
-- What's new in latest version?
SELECT ref_type, code, description
FROM tb_reference_data
WHERE cnes_version = '202607'
  AND code NOT IN (
    SELECT code FROM tb_reference_data 
    WHERE cnes_version = '202606' AND ref_type = tb_reference_data.ref_type
  );

-- What was removed?
SELECT ref_type, code, description  
FROM tb_reference_data
WHERE cnes_version = '202606'
  AND code NOT IN (
    SELECT code FROM tb_reference_data
    WHERE cnes_version = '202607' AND ref_type = tb_reference_data.ref_type
  );

-- What descriptions changed?
SELECT 
  old.ref_type,
  old.code,
  old.description as old_description,
  new.description as new_description
FROM tb_reference_data old
JOIN tb_reference_data new 
  ON old.ref_type = new.ref_type AND old.code = new.code
WHERE old.cnes_version = '202606'
  AND new.cnes_version = '202607'
  AND old.description != new.description;
```

---

## ⚡ PERFORMANCE DURING UPDATES

### **Zero-Downtime Updates:**

```python
def zero_downtime_update():
    """Update reference data without downtime"""
    
    # 1. Create temp table
    db.execute("CREATE TABLE tb_reference_data_new LIKE tb_reference_data")
    
    # 2. Load new data into temp table
    load_data_into('tb_reference_data_new')
    
    # 3. Atomic swap (milliseconds of downtime)
    with db.transaction():
        db.execute("RENAME TABLE tb_reference_data TO tb_reference_data_old")
        db.execute("RENAME TABLE tb_reference_data_new TO tb_reference_data")
    
    # 4. Drop old table
    db.execute("DROP TABLE tb_reference_data_old")
```

**Downtime:** < 100ms (just the RENAME)

---

## 🆚 FINAL COMPARISON

| Aspect | Separate Tables | Consolidated Table |
|--------|----------------|-------------------|
| **Update Complexity** | 6 separate operations | 1 unified operation |
| **Update Script** | 6 scripts or complex script | 1 simple script |
| **Transaction Safety** | 6 transactions or complex logic | 1 transaction |
| **Testing** | Test 6 table updates | Test 1 table update |
| **Rollback** | Restore 6 tables | Restore 1 table |
| **Version Tracking** | 6 places to track | 1 place to track |
| **Audit Trail** | Complex across tables | Simple in one table |
| **Downtime** | 6x potential issues | 1x potential issue |
| **Debug Updates** | Check 6 tables | Check 1 table |

---

## ✅ CONCLUSION

**Updates are EASIER with consolidated tables because:**

1. **Single point of management** - one table to update
2. **Atomic updates** - all or nothing in one transaction
3. **Simpler scripts** - one update pattern for all types
4. **Better tracking** - know when each type was updated
5. **Easier rollback** - restore one table instead of six
6. **Less error-prone** - fewer moving parts

**The fact that these tables don't have update tracking in CNES means:**
- They're stable reference data
- They don't change frequently
- You'll update them monthly (when CNES releases new data)
- Perfect candidates for consolidation!

**Recommendation:** Go with consolidation - it makes updates **simpler**, not harder!
