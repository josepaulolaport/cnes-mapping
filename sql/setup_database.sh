#!/bin/bash

# ============================================================================
# Quick Setup Script for Sales App Database
# ============================================================================
# This script automates the entire setup process:
# 1. Creates the database
# 2. Runs the schema creation SQL
# 3. Imports CNES CSV data
#
# Usage:
#   ./setup_database.sh
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (modify these as needed)
DB_NAME="${DB_NAME:-sales_app_db}"
DB_USER="${DB_USER:-sales_app_user}"
DB_PASSWORD="${DB_PASSWORD:-your_secure_password}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-postgres}"
CSV_DIR="${CSV_DIR:-./csv_files}"
CNES_VERSION="${CNES_VERSION:-}"  # Auto-detect if empty

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Sales App Database Setup${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================================================
# Step 1: Check Prerequisites
# ============================================================================
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"

# Check PostgreSQL
if ! command -v psql &> /dev/null; then
    echo -e "${RED}❌ PostgreSQL (psql) not found. Please install PostgreSQL.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ PostgreSQL found${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.8+.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3 found${NC}"

# Check pip
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo -e "${RED}❌ pip not found. Please install pip.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip found${NC}"

# Check CSV directory
if [ ! -d "$CSV_DIR" ]; then
    echo -e "${RED}❌ CSV directory not found: $CSV_DIR${NC}"
    echo -e "${YELLOW}Please create directory and place CNES CSV files there.${NC}"
    exit 1
fi

CSV_COUNT=$(ls -1 "$CSV_DIR"/*.csv 2>/dev/null | wc -l)
if [ "$CSV_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ No CSV files found in: $CSV_DIR${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Found $CSV_COUNT CSV files in $CSV_DIR${NC}"

echo ""

# ============================================================================
# Step 2: Install Python Dependencies
# ============================================================================
echo -e "${YELLOW}Step 2: Installing Python dependencies...${NC}"

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -q --upgrade pip
pip install -q pandas sqlalchemy psycopg2-binary python-dotenv tqdm

echo -e "${GREEN}✅ Python dependencies installed${NC}"
echo ""

# ============================================================================
# Step 3: Create Database
# ============================================================================
echo -e "${YELLOW}Step 3: Creating database...${NC}"

# Check if database already exists
DB_EXISTS=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null || echo "")

if [ "$DB_EXISTS" == "1" ]; then
    echo -e "${YELLOW}⚠️  Database '$DB_NAME' already exists.${NC}"
    read -p "Do you want to drop and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Dropping existing database..."
        PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"
        echo "Dropping existing user..."
        PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -c "DROP USER IF EXISTS $DB_USER;"
    else
        echo "Keeping existing database. Proceeding to import..."
    fi
fi

# Create user if doesn't exist
USER_EXISTS=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null || echo "")

if [ "$USER_EXISTS" != "1" ]; then
    echo "Creating user: $DB_USER"
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
else
    echo "User $DB_USER already exists"
fi

# Create database if doesn't exist
if [ "$DB_EXISTS" != "1" ]; then
    echo "Creating database: $DB_NAME"
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
fi

# Grant permissions
PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_ADMIN_USER" -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo -e "${GREEN}✅ Database setup complete${NC}"
echo ""

# ============================================================================
# Step 4: Create Schema
# ============================================================================
echo -e "${YELLOW}Step 4: Creating database schema...${NC}"

if [ ! -f "create_sales_app_schema.sql" ]; then
    echo -e "${RED}❌ SQL file not found: create_sales_app_schema.sql${NC}"
    exit 1
fi

echo "Running SQL schema creation..."
PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f create_sales_app_schema.sql > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Schema created successfully${NC}"
else
    echo -e "${RED}❌ Schema creation failed. Check create_sales_app_schema.sql${NC}"
    exit 1
fi

# Verify tables
TABLE_COUNT=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
echo "Created $TABLE_COUNT tables"
echo ""

# ============================================================================
# Step 5: Import CNES Data
# ============================================================================
echo -e "${YELLOW}Step 5: Importing CNES data...${NC}"
echo -e "${YELLOW}⏱️  This will take 40-70 minutes. Please be patient.${NC}"
echo ""

if [ ! -f "import_cnes_data.py" ]; then
    echo -e "${RED}❌ Import script not found: import_cnes_data.py${NC}"
    exit 1
fi

# Build database URL
DB_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

# Run import
if [ -z "$CNES_VERSION" ]; then
    python import_cnes_data.py --csv-dir "$CSV_DIR" --db-url "$DB_URL"
else
    python import_cnes_data.py --csv-dir "$CSV_DIR" --db-url "$DB_URL" --cnes-version "$CNES_VERSION"
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Data import complete!${NC}"
else
    echo ""
    echo -e "${RED}❌ Import failed. Check import_cnes_data.log for details.${NC}"
    exit 1
fi

echo ""

# ============================================================================
# Step 6: Verify Import
# ============================================================================
echo -e "${YELLOW}Step 6: Verifying import...${NC}"

# Get row counts
echo "Table row counts:"
PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 
    schemaname,
    tablename,
    n_live_tup as row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;
"

# Test critical query
echo ""
echo "Testing critical queries..."
ACTIVE_FACILITIES=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM facilities WHERE deactivation_reason_code IS NULL;")
echo "  Active facilities: $ACTIVE_FACILITIES"

ACTIVE_PROFESSIONALS=$(PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT COUNT(DISTINCT professional_id) FROM facility_professionals WHERE termination_date IS NULL;")
echo "  Active professionals: $ACTIVE_PROFESSIONALS"

echo ""
echo -e "${GREEN}✅ Verification complete${NC}"
echo ""

# ============================================================================
# Completion
# ============================================================================
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  🎉 Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Database Details:"
echo "  Host:     $DB_HOST"
echo "  Port:     $DB_PORT"
echo "  Database: $DB_NAME"
echo "  User:     $DB_USER"
echo ""
echo "Connection String:"
echo "  postgresql://$DB_USER:****@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "Next Steps:"
echo "  1. Connect your application to the database"
echo "  2. Test queries using the views (active_facilities, etc.)"
echo "  3. Review import log: import_cnes_data.log"
echo "  4. Set up regular backups"
echo ""
echo "Example connection (psql):"
echo "  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"
echo ""
echo -e "${BLUE}Happy coding! 🚀${NC}"
