import os
import uuid
import shutil
from src.core.db import (
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
    get_db_connection
)
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.config_loader import load_system_settings, is_source_active

def main():
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    domain = "expense_receipt" # default domain
    domain_storage = os.path.join(storage_root, domain)
    
    inbox_dir = os.path.join(domain_storage, "01_raw_inbox")
    split_dir = os.path.join(domain_storage, "02_split_pages")
    
    if not os.path.exists(inbox_dir):
        print(f"[-] Inbox directory does not exist: {inbox_dir}")
        return
        
    print(f"[*] Scanning inbox for files to process in: {inbox_dir}")
    processed_count = 0
    
    # Traverse subfolders in 01_raw_inbox/
    for root_dir, _, files in os.walk(inbox_dir):
        for file in files:
            if file.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                file_path = os.path.join(root_dir, file).replace("\\", "/")
                filename = os.path.basename(file_path)
                file_lower = filename.lower()
                
                print(f"\n--- Processing: {filename} ---")
                
                # 1. Calculate Hash & Duplicate check
                try:
                    file_hash = calculate_file_hash(file_path)
                    is_dup, dup_meta = check_duplicate_document(file_hash)
                    if is_dup:
                        print(f"[!] SKIP: Duplicate file detected (hash: {file_hash[:12]}...)")
                        print(f"    Already registered under Batch: {dup_meta['batch_id']} (Status: {dup_meta['status']})")
                        continue
                except Exception as he:
                    print(f"[-] Error checking duplicate for {filename}: {he}")
                    continue
                
                # 2. Determine Source
                parent_dir = os.path.abspath(os.path.dirname(file_path)).replace("\\", "/")
                inbox_abs = os.path.abspath(inbox_dir).replace("\\", "/")
                
                source = "_default"
                if os.path.dirname(parent_dir) == inbox_abs:
                    folder_name = os.path.basename(parent_dir)
                    source = "_default" if folder_name == "_uncategorized" else folder_name
                    print(f"[+] Source (from folder): '{source}'")
                else:
                    # File is at the root of inbox, we need to run matcher
                    # To run matcher, we temporarily split page 1
                    temp_split_dir = os.path.join(split_dir, "temp_split").replace("\\", "/")
                    os.makedirs(temp_split_dir, exist_ok=True)
                    
                    temp_paths = []
                    if file_lower.endswith(".pdf"):
                        try:
                            # Just split page 1
                            temp_paths = split_pdf(file_path, temp_split_dir)
                        except Exception as e:
                            print(f"[-] Failed to split temp page: {e}")
                            continue
                    else:
                        temp_img_name = f"temp_match_{uuid.uuid4().hex[:6]}.png"
                        temp_img_path = os.path.join(temp_split_dir, temp_img_name).replace("\\", "/")
                        shutil.copy(file_path, temp_img_path)
                        temp_paths = [temp_img_path]
                        
                    if temp_paths:
                        source = match_source(file_path, domain, temp_paths[0])
                        print(f"[+] Matched Source (from AI matcher): '{source}'")
                        # Clean up temp folder
                        shutil.rmtree(temp_split_dir, ignore_errors=True)
                    else:
                        print("[-] Failed to generate temp page for matching. Falling back to '_default'")
                        source = "_default"
                
                # Check active status of source
                if not is_source_active(domain, source):
                    print(f"[!] Warning: Source '{source}' is inactive in settings. Falling back to '_default'")
                    source = "_default"
                    
                # 3. Categorize & Move original raw file
                if source == "_default":
                    dest_folder = os.path.join(inbox_dir, "_uncategorized")
                else:
                    dest_folder = os.path.join(inbox_dir, source)
                    
                os.makedirs(dest_folder, exist_ok=True)
                dest_raw_path = os.path.join(dest_folder, filename).replace("\\", "/")
                
                if file_path != dest_raw_path:
                    shutil.move(file_path, dest_raw_path)
                    print(f"    Moved raw file to: {dest_raw_path}")
                    
                # 4. Create Batch ID
                batch_id = f"batch_{uuid.uuid4().hex[:12]}"
                print(f"[+] Batch ID: {batch_id}")
                
                # 5. Split and Rename pages directly to source-specific folders
                source_split_dir = os.path.join(split_dir, source).replace("\\", "/")
                os.makedirs(source_split_dir, exist_ok=True)
                
                # Temporary splitting to source-specific folder
                raw_split_paths = []
                if file_lower.endswith(".pdf"):
                    try:
                        raw_split_paths = split_pdf(dest_raw_path, source_split_dir)
                    except Exception as se:
                        print(f"[-] Failed to split PDF: {se}")
                        continue
                else:
                    temp_img_name = f"temp_{uuid.uuid4().hex[:6]}.png"
                    dest_split_path = os.path.join(source_split_dir, temp_img_name).replace("\\", "/")
                    shutil.copy(dest_raw_path, dest_split_path)
                    raw_split_paths = [dest_split_path]
                
                # Register Batch in database
                create_batch(
                    batch_id=batch_id,
                    original_pdf_name=filename,
                    total_pages=len(raw_split_paths),
                    storage_path=os.path.dirname(dest_raw_path),
                    file_hash=file_hash
                )
                
                # Rename the files systematically and write to database directly as PROCESSED
                archiving_cfg = settings.get("archiving", {})
                filename_pattern = archiving_cfg.get("filename_pattern", "{domain}_{source}_{doc_no}_{page_no}")
                base_filename = os.path.splitext(filename)[0]
                
                for idx, temp_path in enumerate(raw_split_paths):
                    page_num = idx + 1
                    page_id = f"page_{batch_id}_{page_num:03d}"
                    
                    new_filename_base = filename_pattern.replace("{domain}", domain)\
                                                        .replace("{source}", source)\
                                                        .replace("{doc_no}", base_filename)\
                                                        .replace("{page_no}", f"{page_num:03d}")
                    new_filename = f"{new_filename_base}.png"
                    new_img_path = os.path.join(source_split_dir, new_filename).replace("\\", "/")
                    
                    if os.path.exists(temp_path):
                        if os.path.exists(new_img_path):
                            os.remove(new_img_path)
                        os.rename(temp_path, new_img_path)
                        
                    create_page(
                        page_id=page_id,
                        batch_id=batch_id,
                        page_number=page_num,
                        image_path=new_img_path,
                        status_code="PREPROCESSED"
                    )
                    print(f"    -> Registered Page {page_num}: {new_filename}")
                
                processed_count += 1
                
    print(f"\n[SUCCESS] Completed Step 2! Split and matched {processed_count} files successfully.")

if __name__ == "__main__":
    main()
