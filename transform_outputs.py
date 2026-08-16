import os
import json
import pandas as pd
from src.core.db import get_db_connection
from src.core.transformer import transform_data
from src.core.config_loader import load_system_settings

def main():
    settings = load_system_settings()
    domain = "expense_receipt" # default domain
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch documents that are PROCESSED or APPROVED
        cursor.execute("""
            SELECT document_id, original_pdf_name, data_payload, status_code
            FROM documents doc
            JOIN processed_batches pb ON doc.batch_id = pb.batch_id
            WHERE doc.domain_id = ? AND doc.status_code IN ('PROCESSED', 'APPROVED')
        """, (domain,))
        docs = cursor.fetchall()
        
        if not docs:
            print("[*] No processed/approved documents found for transformation.")
            return
            
        print(f"[*] Found {len(docs)} document(s) to transform and export...")
        
        # Scan templates for output
        templates_dir = f"configs/domains/{domain}/outputs"
        if not os.path.exists(templates_dir):
            print(f"[-] Error: Templates directory does not exist: {templates_dir}")
            return
            
        templates = [f for f in os.listdir(templates_dir) if f.endswith(".json")]
        
        for tpl_file in templates:
            template_name = os.path.splitext(tpl_file)[0]
            template_path = os.path.join(templates_dir, tpl_file)
            
            # Read template granularity to see structure
            with open(template_path, "r", encoding="utf-8") as tf:
                tpl_cfg = json.load(tf)
            granularity = tpl_cfg.get("granularity", "summary")
            
            all_rows = []
            
            for doc in docs:
                payload_str = doc["data_payload"]
                if not payload_str:
                    continue
                try:
                    payload = json.loads(payload_str)
                    rows = transform_data(payload, template_path)
                    all_rows.extend(rows)
                except Exception as e:
                    print(f"[-] Failed to transform document {doc['document_id']}: {e}")
                    
            if all_rows:
                os.makedirs("outputs", exist_ok=True)
                df = pd.DataFrame(all_rows)
                
                csv_path = os.path.join("outputs", f"{domain}_{template_name}_export.csv")
                df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                print(f"[+] Exported CSV: {csv_path} ({len(all_rows)} rows)")
                
                json_path = os.path.join("outputs", f"{domain}_{template_name}_export.json")
                df.to_json(json_path, orient="records", force_ascii=False, indent=2)
                print(f"[+] Exported JSON: {json_path}")
                
        print("\n[SUCCESS] Completed Step 5! Flat report transformation and export finished.")
    except Exception as e:
        print(f"[-] Error during data transformation execution: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
