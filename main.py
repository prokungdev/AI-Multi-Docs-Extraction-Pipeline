import argparse
import sys
import asyncio
from src.core.pipeline import (
    run_init,
    run_split_and_match,
    run_extract,
    async_run_extract,
    run_validate,
    run_transform_to_db,
    run_export_outputs,
    run_pipeline_all,
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
        choices=["init", "split", "extract", "validate", "transform", "export", "all", "healthcheck"],
        default="all",
        help="Pipeline step to execute:\n"
             "  healthcheck- Verify system readiness, DB WAL mode, permissions & API credentials\n"
             "  init       - System initialization & storage directory verification (Stage 1)\n"
             "  split      - Split inbox PDFs & match merchant sources (Stage 2)\n"
             "  extract    - Run AI extraction on preprocessed images (Stage 3)\n"
             "  validate   - Apply rules, math validation & tax checks (Stage 4)\n"
             "  transform  - Import verified records into SQLite DB (Stage 5)\n"
             "  export     - Generate output reports in CSV/Excel/PV formats (Stage 6)\n"
             "  all        - Run all pipeline stages end-to-end"
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
        help="Specific PDF file path to process (optional for split / all steps)"
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
        success = run_init()
        sys.exit(0 if success else 1)
    elif step == "split":
        res = run_split_and_match(domain=domain, input_file=input_file)
        sys.exit(0)
    elif step == "extract":
        if use_async:
            res = asyncio.run(async_run_extract(domain=domain))
        else:
            res = run_extract(domain=domain)
        sys.exit(0 if res.get("success", True) else 1)
    elif step == "validate":
        res = run_validate(domain=domain)
        sys.exit(0)
    elif step == "transform":
        res = run_transform_to_db(domain=domain)
        sys.exit(0)
    elif step == "export":
        res = run_export_outputs(domain=domain)
        sys.exit(0)
    elif step == "all":
        res = run_pipeline_all(domain=domain, input_pdf=input_file)
        sys.exit(0 if res.get("success", False) else 1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
