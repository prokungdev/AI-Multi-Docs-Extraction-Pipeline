"""
End-to-End (E2E) Pipeline Manual Test Runner.
Executes the document extraction pipeline from Ingestion (Stage 1) to Database (Stage 5).

Usage:
  # Fast Mock AI Mode (0 Token, 100% Offline):
  python tests/manual/run_e2e_pipeline.py

  # Live AI Mode (Uses real Gemini/OpenAI API tokens):
  python tests/manual/run_e2e_pipeline.py --live
"""

import os
import sys
import shutil
import argparse
from unittest.mock import patch

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from src.infrastructure.core.logger import logger
from src.infrastructure.external.storage.storage_manager import storage_manager
from src.application.pipeline import (
    init_system,
    split_and_match,
    extract_documents,
    validate_documents,
    transform_to_db,
    reset_pipeline_data,
    release_pending_merchant_files,
)
from src.infrastructure.database import (
    get_pending_merchants,
    approve_merchant,
    get_db_session,
    ExpenseReceipt,
    ExpenseReceiptItem,
)
from sqlalchemy import select, func


def ensure_test_fixture(comp_code: str = "C00000_SAMPLE", doc_type: str = "expense_receipt") -> str:
    """Ensures that Grab_Sample_3Pages.pdf exists in the Test_E2E drop zone."""
    master_fixture = os.path.join(PROJECT_ROOT, "tests", "fixtures", "sample_docs", "Grab_Sample_3Pages.pdf")
    drop_zone_e2e = storage_manager.get_drop_zone_dir(comp_code, doc_type, "Test_E2E")
    os.makedirs(drop_zone_e2e, exist_ok=True)
    target_file = os.path.join(drop_zone_e2e, "Grab_Sample_3Pages.pdf").replace("\\", "/")

    if not os.path.exists(target_file):
        if os.path.exists(master_fixture):
            shutil.copy(master_fixture, target_file)
            logger.info(f"Copied test fixture to: {target_file}")
        else:
            raise FileNotFoundError(f"Master fixture not found at {master_fixture}")
    return target_file


def mock_ai_extraction_data(**kwargs):
    """
    Mock AI extraction payload representing extracted Grab receipts.
    Allows running the full pipeline with 0 tokens spent.
    """
    chunk_index = kwargs.get("chunk_index", 1)
    return {
        "documents": [
            {
                "doc_type": "expense_receipt",
                "doc_number": f"GB-202606-{chunk_index:04d}",
                "doc_date": "2026-06-15",
                "merchant_name": "Grab Taxi (Thailand) Co., Ltd.",
                "merchant_tax_id": "0105556091219",
                "branch_no": "00000",
                "subtotal": 120.00,
                "vat_amount": 8.40,
                "grand_total": 128.40,
                "items": [
                    {
                        "item_name": "GrabTransport Ride Service",
                        "quantity": 1,
                        "unit_price": 120.00,
                        "amount": 120.00,
                    }
                ],
            }
        ]
    }


def run_e2e_test(is_live: bool = False, comp_code: str = "C00000_SAMPLE", doc_type: str = "expense_receipt"):
    print("=" * 70)
    print(f"🚀 RUNNING END-TO-END (E2E) PIPELINE TEST")
    print(f"   Mode: {'🔴 LIVE AI (Consumes API Tokens)' if is_live else '🟢 MOCK AI (0 Token, Fast Offline)'}")
    print(f"   Company: {comp_code} | Doc Type: {doc_type}")
    print("=" * 70)

    # 1. Reset pipeline data for clean isolated test
    print("\n🧹 Step 0: Cleaning pipeline temporary storage and DB...")
    reset_res = reset_pipeline_data(doc_type=doc_type, clear_storage_temp=True, clear_database=True)
    print(f"   Reset completed: {reset_res}")

    # 2. Ensure test fixture is placed in drop zone
    test_pdf = ensure_test_fixture(comp_code, doc_type)
    print(f"   Test Fixture ready: {test_pdf}")

    # 3. Step 1: System Initialization
    print("\n⚙️ Step 1: Initializing system and database schema...")
    init_ok = init_system(drop_and_recreate=False)
    if not init_ok:
        print("❌ System initialization failed.")
        sys.exit(1)
    print("   ✅ System initialized successfully.")

    # 4. Step 2: Ingestion & Splitting
    print("\n📄 Step 2: Ingesting and splitting documents from drop zone...")
    split_res = split_and_match(doc_type=doc_type, input_file=test_pdf, company_code=comp_code)
    print(f"   ✅ Ingested {len(split_res)} batch(es).")
    for r in split_res:
        print(f"      - Batch: {r.get('batch_id')} | Merchant: {r.get('matched_source')} | Pages: {r.get('total_pages')}")

    # 5. Step 2.1: Check & Approve Pending Merchants
    print("\n🔍 Step 2.1: Checking pending merchants...")
    released_batches = []
    pending = get_pending_merchants()
    if pending:
        print(f"   Found {len(pending)} pending merchant(s):")
        for p in pending:
            merchant_id = p.get("merchant_id")
            tax_id = p.get("tax_id")
            short_name = p.get("short_name") or "grab"
            print(f"   Approving merchant: {p.get('merchant_name')} (ID: {merchant_id}, Tax ID: {tax_id})...")
            ok, msg = approve_merchant(merchant_id=merchant_id, approved_by="usr_system_auto", short_name=short_name)
            print(f"   Approval status: {ok} ({msg if not ok else 'Success'})")
            rel = release_pending_merchant_files(doc_type=doc_type, tax_id=tax_id, short_name=short_name, company_code=comp_code)
            print(f"   Released {len(rel)} files for {tax_id}.")
            released_batches.extend(rel)
    else:
        print("   ℹ️ No merchants pending approval.")

    active_batches = split_res or released_batches
    if not active_batches:
        print("❌ No active batches available for processing.")
        sys.exit(1)

    for b in active_batches:
        b_id = b["batch_id"]
        print(f"\n⚡ --- Processing Batch: {b_id} ---")

        # 6. Step 3: AI Document Extraction
        print(f"\n🤖 Step 3: Extracting document data ({'Live AI' if is_live else 'Mock AI'}) [Batch: {b_id}]...")
        if is_live:
            extract_res = extract_documents(batch_id=b_id, doc_type=doc_type, company_code=comp_code)
        else:
            with patch("src.application.pipeline.stage_2_extraction.extract_document_data", side_effect=mock_ai_extraction_data):
                extract_res = extract_documents(batch_id=b_id, doc_type=doc_type, company_code=comp_code)
        print(f"   ✅ Extraction Summary: {extract_res}")

        # 7. Step 4: Validate Documents
        print(f"\n🛡️ Step 4: Validating rules and financial amounts [Batch: {b_id}]...")
        val_res = validate_documents(batch_id=b_id, doc_type=doc_type, company_code=comp_code)
        print(f"   ✅ Validation Summary: {val_res}")

        # 8. Step 5: Transform to SQLite Database
        print(f"\n💾 Step 5: Transforming records to SQLite Relational DB [Batch: {b_id}]...")
        db_res = transform_to_db(batch_id=b_id, doc_type=doc_type, company_code=comp_code)
        print(f"   ✅ Database Transformation Summary: {db_res}")

    # 9. Verification & Database Records Count
    print("\n📊 --- DATABASE VERIFICATION SUMMARY ---")
    with get_db_session() as session:
        receipt_count = session.scalar(select(func.count()).select_from(ExpenseReceipt))
        item_count = session.scalar(select(func.count()).select_from(ExpenseReceiptItem))
        receipts = session.scalars(select(ExpenseReceipt).limit(5)).all()

        print(f"   Total Receipts in DB: {receipt_count}")
        print(f"   Total Line Items in DB: {item_count}")
        print("\n   [Sample DB Records]")
        for rc in receipts:
            print(f"   - Receipt ID: {rc.receipt_id} | Merchant: {rc.merchant_name} | Net: {rc.net_amount} THB | Date: {rc.transaction_date}")

    print("\n" + "=" * 70)
    print("🎉 END-TO-END PIPELINE TEST COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run End-to-End Pipeline Manual Test")
    parser.add_argument("--live", action="store_true", help="Run with Live AI API calls (consumes tokens)")
    parser.add_argument("--company", default="C00000_SAMPLE", help="Company code (default: C00000_SAMPLE)")
    parser.add_argument("--doc-type", default="expense_receipt", help="Document type (default: expense_receipt)")
    args = parser.parse_args()

    run_e2e_test(is_live=args.live, comp_code=args.company, doc_type=args.doc_type)
