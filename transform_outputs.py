import os
import json
import pandas as pd
from src.core.db import get_db_connection
from src.core.config_loader import load_system_settings
from src.core.logger import setup_logger
from src.core.exporters import list_exporters
from loguru import logger

def main():
    setup_logger()
    logger.info("==========================================")
    logger.info("  Run_04_Transform_Outputs: Dynamic Report Export")
    logger.info("==========================================")
    
    settings = load_system_settings()
    domain = "expense_receipt" # default domain
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch documents that are PROCESSED or APPROVED
        cursor.execute("""
            SELECT doc.*, pb.original_pdf_name, pb.storage_path
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE doc.domain_id = ? AND doc.status_code IN ('PROCESSED', 'APPROVED')
        """, (domain,))
        docs_raw = cursor.fetchall()
        
        if not docs_raw:
            logger.info("No processed/approved documents found for transformation.")
            return
            
        logger.info(f"Found {len(docs_raw)} document(s) to transform and export...")
        
        # Parse data_payload and merge with db columns
        docs = []
        for r in docs_raw:
            row_dict = dict(r)
            payload_str = row_dict.get("data_payload")
            payload = {}
            if payload_str:
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    pass
            # Merge columns and payload values
            merged = {**row_dict, **payload}
            docs.append(merged)
            
        # Get list of registered exporters
        exporters_list = list_exporters(domain)
        
        exported_files = []
        total_rows_exported = 0
        
        for exp_meta in exporters_list:
            exporter_id = exp_meta["exporter_id"]
            handler = exp_meta["handler"]
            
            try:
                # Transform all documents using this exporter
                df = handler.transform(docs)
                if df.empty:
                    logger.info(f"Exporter '{exporter_id}' returned empty DataFrame.")
                    continue
                    
                os.makedirs("outputs", exist_ok=True)
                
                # Determine encoding: Express PV uses cp874 for older Thai local software compatibility
                encoding = "cp874" if exporter_id == "express_pv" else "utf-8-sig"
                
                csv_path = os.path.join("outputs", f"{domain}_{exporter_id}_export.csv").replace("\\", "/")
                df.to_csv(csv_path, index=False, encoding=encoding)
                logger.info(f"Exported CSV: {csv_path} ({len(df)} rows) | Encoding: {encoding}")
                exported_files.append(csv_path)
                total_rows_exported += len(df)
                
                json_path = os.path.join("outputs", f"{domain}_{exporter_id}_export.json").replace("\\", "/")
                df.to_json(json_path, orient="records", force_ascii=False, indent=2)
                logger.info(f"Exported JSON: {json_path}")
                exported_files.append(json_path)
            except Exception as e:
                logger.error(f"Failed to export using '{exporter_id}': {e}")
                
        logger.info("==========================================")
        logger.info("  Step 4: Dynamic Report Transformation Summary")
        logger.info("==========================================")
        logger.info(f"Total documents processed: {len(docs)}")
        logger.info(f"Total rows exported: {total_rows_exported}")
        logger.info(f"Exported files: {', '.join(exported_files)}")
        logger.info("==========================================")
    except Exception as e:
        logger.error(f"Error during data transformation execution: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
