import argparse
import sys
import asyncio
from src.core.pipeline import (
    init_system,
    split_and_match,
    extract_documents,
    async_extract_documents,
    validate_documents,
    transform_to_db,
    run_healthcheck,
    print_healthcheck_report
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
        "--domain", "-d",
        type=str,
        default=None,
        help="Target document domain (default: configured default active domain, e.g., 'expense_receipt')"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Specific PDF file path to process (optional for split step)"
    )
    parser.add_argument(
        "--async-mode", "-a",
        action="store_true",
        help="Run AI extraction in high-performance asynchronous concurrent mode"
    )
    
    args = parser.parse_args()
    step = args.step
    domain = args.domain
    input_file = args.file
    use_async = args.async_mode
    
    if step == "healthcheck":
        results = run_healthcheck()
        print_healthcheck_report(results)
        sys.exit(0 if results["healthy"] else 1)
    elif step == "init":
        success = init_system()
        sys.exit(0 if success else 1)
    elif step == "split":
        res = split_and_match(domain=domain, input_file=input_file)
        sys.exit(0)
    elif step == "extract":
        if use_async:
            res = asyncio.run(async_extract_documents(domain=domain))
        else:
            res = extract_documents(domain=domain)
        sys.exit(0 if res.get("success", True) else 1)
    elif step == "validate":
        res = validate_documents(domain=domain)
        sys.exit(0)
    elif step == "transform":
        res = transform_to_db(domain=domain)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
