import os
import sys
import random
from datetime import datetime, timedelta, timezone

# Add the root directory to system path to import app modules
sys.path.append(os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.server.schema.asset import Asset
from app.server.schema.category import Category, SubCategory

# --- Configuration ---
DATABASE_URL = "postgresql://postgres:IT%20asset%20management%20system@db.lrglgxjzblkqmwobuphs.supabase.co:5432/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def patch_data():
    db = get_db()
    try:
        assets = db.query(Asset).all()
        print(f"Checking {len(assets)} assets for empty columns...")

        # Vendor and contact mapping
        vendors = {
            "Hardware": ["Dell", "HP", "Cisco", "Logitech", "Apple"],
            "Software": ["Microsoft", "Adobe", "JetBrains", "Cloudflare", "Atlassian"],
            "Furniture": ["Herman Miller", "Steelcase", "IKEA Business"],
        }
        
        contacts = {
            "Dell": "support@dell.com", "HP": "corp@hp.com", "Cisco": "tac@cisco.com",
            "Apple": "enterprise@apple.com", "Microsoft": "licensing@microsoft.com",
            "Adobe": "creative-support@adobe.com", "Herman Miller": "service@hm.com"
        }

        updated_count = 0
        for asset in assets:
            changed = False
            
            # 1. Basic empty fields
            if not asset.brand:
                v_list = vendors.get(asset.category_name, ["Generic"])
                asset.brand = random.choice(v_list)
                changed = True
            
            if not asset.vendor_name:
                asset.vendor_name = asset.brand
                changed = True
                
            if not asset.vendor_contact:
                asset.vendor_contact = contacts.get(asset.vendor_name, f"support@{asset.vendor_name.lower().replace(' ', '')}.com")
                changed = True

            if not asset.invoice_number:
                asset.invoice_number = f"INV-{random.randint(10000, 99999)}-{asset.asset_id[:4]}"
                changed = True

            # 2. Tech / Financial Column Seeding
            if asset.purchase_cost is None or asset.purchase_cost == 0:
                if asset.category_name == "Hardware":
                    asset.purchase_cost = random.randint(45000, 180000)
                elif asset.category_name == "Software":
                    asset.purchase_cost = random.randint(5000, 25000)
                else:
                    asset.purchase_cost = random.randint(8000, 35000)
                changed = True

            if asset.useful_life_years is None:
                asset.useful_life_years = 5 if asset.category_name == "Hardware" else 3 if asset.category_name == "Software" else 10
                changed = True

            if asset.maintenance_total_cost is None:
                asset.maintenance_total_cost = random.randint(500, 5000) if asset.category_name == "Hardware" else 0
                changed = True

            if asset.repair_total_cost is None:
                asset.repair_total_cost = random.choice([0, 0, 0, 1500, 3200]) if asset.category_name == "Hardware" else 0
                changed = True
                if asset.repair_total_cost > 0:
                    asset.repair_count = 1
                else:
                    asset.repair_count = 0

            # 3. Dates
            purchase_dt = asset.purchased_date if asset.purchased_date else datetime.now() - timedelta(days=random.randint(100, 800))
            if not asset.purchased_date:
                asset.purchased_date = purchase_dt.date()
                changed = True

            # Set Warranty/License Expiry if missing
            if asset.category_name == "Software" and not asset.license_expiry:
                asset.license_expiry = (datetime.now() + timedelta(days=random.randint(200, 500))).date()
                changed = True
            elif not asset.warranty_expiry:
                asset.warranty_expiry = (purchase_dt + timedelta(days=365*random.choice([1, 2, 3]))).date()
                changed = True

            # Calculate Depreciation markers
            if asset.purchase_cost and asset.useful_life_years:
                salvage = asset.purchase_cost * 0.1
                asset.salvage_value = salvage
                asset.annual_depreciation = (asset.purchase_cost - salvage) / asset.useful_life_years
                
                # Acc. Depr calculation based on days owned
                days_owned = (datetime.now().date() - asset.purchased_date).days
                years_owned = max(0, days_owned / 365.0)
                asset.accumulated_depreciation = min(asset.purchase_cost - salvage, asset.annual_depreciation * years_owned)
                asset.book_value = asset.purchase_cost - asset.accumulated_depreciation
                changed = True

            if changed:
                updated_count += 1
        
        db.commit()
        print(f"Successfully patched {updated_count} assets with complete enterprise data.")
        
    except Exception as e:
        db.rollback()
        print(f"Patch failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    patch_data()
