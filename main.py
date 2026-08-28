import argparse
import sys
import asyncio
from src.infrastructure.common.config_loader import get_default_company_code
from src.infrastructure.common.healthcheck import run_healthcheck, print_healthcheck_report
from src.application.pipeline import (
    init_system,
    split_and_match,
    extract_documents,
    async_extract_documents,
    validate_documents,
    transform_to_db,
)

def main():
    parser = argparse.ArgumentParser(
        description="AI Multi-Docs Extraction Pipeline — Universal CLI Runner",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--step", "-s",
        choices=["init", "split", "extract", "validate", "transform", "healthcheck"],
        default="split",
        help="Pipeline step to execute:\n"
             "  healthcheck- Verify system readiness, DB WAL mode, permissions & API credentials\n"
             "  init       - System initialization & storage directory verification (Stage 1)\n"
             "  split      - Split inbox PDFs & match merchant sources (Stage 2)\n"
             "  extract    - Run AI extraction on preprocessed images (Stage 3)\n"
             "  validate   - Apply rules, math validation & tax checks (Stage 4)\n"
             "  transform  - Import verified records into SQLite DB (Stage 5)"
    )
    parser.add_argument(
        "--company-code", "-c",
        type=str,
        default=None,
        help="Target client company code (e.g. 'C00000_SAMPLE', 'C00001_TRD'). Defaults to configured default company."
    )
    parser.add_argument(
        "--doc-type", "--domain", "-d",
        type=str,
        default=None,
        help="Target document type (default: configured default active doc_type, e.g., 'expense_receipt')"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Specific PDF file path to process (optional for split step)"
    )
    parser.add_argument(
        "--batch", "-b",
        type=str,
        default=None,
        help="Batch ID to process (required for extract, validate, and transform steps)"
    )
    parser.add_argument(
        "--async-mode", "-a",
        action="store_true",
        help="Run AI extraction in high-performance asynchronous concurrent mode"
    )
    
    args = parser.parse_args()
    step = args.step
    company_code = args.company_code or get_default_company_code()
    doc_type = args.doc_type
    input_file = args.file
    batch_id = args.batch
    use_async = args.async_mode
    
    if step == "healthcheck":
        results = run_healthcheck()
        print_healthcheck_report(results)
        sys.exit(0 if results["healthy"] else 1)
    elif step == "init":
        success = init_system()
        sys.exit(0 if success else 1)
    elif step == "split":
        res = split_and_match(doc_type=doc_type, input_file=input_file, company_code=company_code)
        sys.exit(0)
    elif step == "extract":
        if not batch_id:
            print("Error: --batch is required for extract step.")
            sys.exit(1)
        if use_async:
            res = asyncio.run(async_extract_documents(batch_id=batch_id, doc_type=doc_type, company_code=company_code))
        else:
            res = extract_documents(batch_id=batch_id, doc_type=doc_type, company_code=company_code)
        sys.exit(0 if res.get("success", True) else 1)
    elif step == "validate":
        if not batch_id:
            print("Error: --batch is required for validate step.")
            sys.exit(1)
        res = validate_documents(batch_id=batch_id, doc_type=doc_type, company_code=company_code)
        sys.exit(0)
    elif step == "transform":
        if not batch_id:
            print("Error: --batch is required for transform step.")
            sys.exit(1)
        res = transform_to_db(batch_id=batch_id, doc_type=doc_type, company_code=company_code)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
