#!/bin/bash
# Quick Setup and Import Script for SQLite
# Run this to set up the database and start importing data

set -e  # Exit on error

echo "=========================================="
echo "CNES SQLite Database Setup"
echo "=========================================="
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p output logs import_errors

# Create the database schema
echo ""
echo "Creating database schema..."
if [ -f "output/cnes_data.db" ]; then
    echo "Warning: output/cnes_data.db already exists"
    read -p "Delete and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm output/cnes_data.db
        sqlite3 output/cnes_data.db < sql/create_sales_app_schema_sqlite.sql
        echo "✓ Database recreated"
    else
        echo "Keeping existing database"
    fi
else
    sqlite3 output/cnes_data.db < sql/create_sales_app_schema_sqlite.sql
    echo "✓ Database created"
fi

# Prompt for import
echo ""
echo "=========================================="
echo "Ready to import data"
echo "=========================================="
echo ""
echo "Choose import option:"
echo "1) Import all tables (recommended - takes 45-60 min)"
echo "2) Import only reference tables (quick - takes 1-2 min)"
echo "3) Skip import for now"
echo ""
read -p "Enter choice (1-3): " choice

case $choice in
    1)
        echo ""
        echo "Starting full import..."
        cd scripts
        python import_sqlite_full.py --table all
        cd ..
        ;;
    2)
        echo ""
        echo "Importing reference tables..."
        cd scripts
        python import_sqlite_full.py --table states
        python import_sqlite_full.py --table municipalities
        python import_sqlite_full.py --table facility_types
        python import_sqlite_full.py --table deactivation_reasons
        python import_sqlite_full.py --table service_specialties
        python import_sqlite_full.py --table equipment_catalog
        python import_sqlite_full.py --table professional_councils
        python import_sqlite_full.py --table equipment_categories
        python import_sqlite_full.py --table service_classifications
        cd ..
        ;;
    3)
        echo "Skipping import"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

# Show summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Database location: output/cnes_data.db"
echo "View import logs: logs/import_sqlite.log"
echo "Check errors: import_errors/*.log"
echo ""
echo "Quick test query:"
echo "sqlite3 output/cnes_data.db \"SELECT COUNT(*) FROM states\""
echo ""
echo "To query the database:"
echo "sqlite3 output/cnes_data.db"
echo ""
echo "Read PROJECT_OVERVIEW.md for more information"
