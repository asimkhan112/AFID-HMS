"""
seed_presets.py
Seed the database with default procedure presets.
Run with: python seed_presets.py
"""

import sys
import os

# Ensure the backend root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

def seed_presets():
    db = SessionLocal()
    try:
        # Check if presets already exist
        existing = db.query(models.ProcedurePreset).first()
        if existing:
            print("Presets already seeded. Skipping...")
            return

        # Define default presets
        presets_data = [
            {
                "name": "Consultation",
                "duration": 15,
                "notes": "Initial specialist consultation conducted. Patient's chief complaints documented and preliminary treatment plan discussed.",
                "materials": [],
                "pharmacy": [],
                "diagnostics": []
            },
            {
                "name": "U/L Bracketing",
                "duration": 45,
                "notes": "Bracket placement completed. Archwire secured. Patient instructed on oral hygiene with fixed appliances.",
                "materials": [
                    {"name": "Brackets", "quantity": 1},
                    {"name": "composite", "quantity": 1},
                    {"name": "etchant", "quantity": 1},
                    {"name": "Primer", "quantity": 1}
                ],
                "pharmacy": [],
                "diagnostics": []
            },
            {
                "name": "Fixed Retainer",
                "duration": 40,
                "notes": "Lingual bonded fixed retainer wire structured and verified. Occlusion checked.",
                "materials": [
                    {"name": "composite", "quantity": 1},
                    {"name": "etchant", "quantity": 1},
                    {"name": "Primer", "quantity": 1},
                    {"name": "retainer wire", "quantity": 1}
                ],
                "pharmacy": [],
                "diagnostics": []
            },
            {
                "name": "Orthodontic Adjustment",
                "duration": 25,
                "notes": "Removed old active archwire. Inspected bracket placements. Replaced upper archwire with 0.016 NiTi wire. Secured active ligatures. Patient instructed on elastic hook placements.",
                "materials": [
                    {"name": "0.016 NiTi Archwire", "quantity": 1},
                    {"name": "Orthodontic Elastics Bag", "quantity": 1},
                    {"name": "Stainless Steel Bracket Kit", "quantity": 1}
                ],
                "pharmacy": [
                    {"medication": "Orthodontic Relief Wax", "dose": "1 Box", "frequency": "Apply as needed"},
                    {"medication": "Paracetamol 500mg", "dose": "500mg", "frequency": "PRN pain"}
                ],
                "diagnostics": []
            },
            {
                "name": "Root Canal Treatment",
                "duration": 60,
                "notes": "Root canal access cavity established under rubber dam isolation. Working length determined via apex locator logs. Prepped up cleanly up to size 30 manual framework files. Irrigation via 2.5% NaOCl layer channels.",
                "materials": [
                    {"name": "0.017x0.025 NiTi Archwire", "quantity": 2},
                    {"name": "AH Plus Sealer (1.5g)", "quantity": 1},
                    {"name": "Gutta-Percha Points (ISO 30)", "quantity": 6},
                    {"name": "Stainless Steel Bracket Kit", "quantity": 1}
                ],
                "pharmacy": [
                    {"medication": "Amoxicillin 500mg", "dose": "140mg", "frequency": "TDS x 5 days"},
                    {"medication": "Chlorhexidine Mouth Wash 0.2%", "dose": "15ml", "frequency": "BD x 7 days"},
                    {"medication": "Ibuprofen 400mg", "dose": "400mg", "frequency": "BD PRN pain"}
                ],
                "diagnostics": [
                    {"test_name": "CBCT", "urgency": "Routine"},
                    {"test_name": "Full Mouth Periapical X-rays", "urgency": "Routine"}
                ]
            },
            {
                "name": "Band cementation / Banding of molars",
                "duration": 30,
                "notes": "Molar band trial fitting completed and cemented cleanly.",
                "materials": [
                    {"name": "cotton rolls", "quantity": 1},
                    {"name": "GIC", "quantity": 1},
                    {"name": "Molar bands", "quantity": 1}
                ],
                "pharmacy": [],
                "diagnostics": []
            }
        ]

        for preset_data in presets_data:
            preset = models.ProcedurePreset(
                name=preset_data["name"],
                duration=preset_data["duration"],
                notes=preset_data["notes"]
            )
            db.add(preset)
            db.flush()

            # Add materials
            for mat in preset_data.get("materials", []):
                pm = models.PresetMaterial(
                    preset_id=preset.id,
                    name=mat["name"],
                    quantity=mat["quantity"]
                )
                db.add(pm)

            # Add pharmacy
            for pharm in preset_data.get("pharmacy", []):
                pp = models.PresetPharmacy(
                    preset_id=preset.id,
                    medication=pharm["medication"],
                    dose=pharm.get("dose"),
                    frequency=pharm.get("frequency")
                )
                db.add(pp)

            # Add diagnostics
            for diag in preset_data.get("diagnostics", []):
                pd = models.PresetDiagnostic(
                    preset_id=preset.id,
                    test_name=diag["test_name"],
                    urgency=diag.get("urgency", "Routine")
                )
                db.add(pd)

        db.commit()
        print(f"Successfully seeded {len(presets_data)} procedure presets.")
    except Exception as e:
        print(f"Error seeding presets: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_presets()