import os
import sys

# Append the project root directory to sys.path to resolve imports when running via Streamlit
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import shutil
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
from datetime import datetime
from dotenv import load_dotenv

# Import core pipeline modules
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.extractor import extract_receipt_data
from src.core.transformer import transform_data
from main import init_storage
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    validate_environment,
    initialize_storage_directories
)
from src.core.logger import setup_logger
from loguru import logger
from src.core.database import (
    calculate_file_hash,
    check_duplicate_document,
    insert_pending_document,
    update_document_to_archived
)


# Page configuration
st.set_page_config(
    page_title="AI Multi-Docs Extraction Pipeline",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load settings and environment variables
load_dotenv()
settings = init_storage("configs/settings.json")
storage_root = settings.get("storage_root", "pipeline_storage")

def ensure_mock_data(domain: str):
    """
    Auto-generates dummy/mock receipt data (image + JSON) if the queue is empty,
    allowing the user to inspect the UI and test the pipeline immediately.
    """
    domain_storage = os.path.join(storage_root, domain)
    split_dir = os.path.join(domain_storage, "02_split_pages")
    queue_dir = os.path.join(domain_storage, "03_processing_queue")
    
    os.makedirs(split_dir, exist_ok=True)
    os.makedirs(queue_dir, exist_ok=True)
    
    # Check if the queue already has files
    queue_files = [f for f in os.listdir(queue_dir) if f.endswith(".json")]
    if queue_files:
        return
        
    # Read settings to find pattern
    try:
        with open("configs/settings.json", "r", encoding="utf-8") as f:
            settings_mock = json.load(f)
        archiving_cfg = settings_mock.get("archiving", {})
        filename_pattern = archiving_cfg.get("filename_pattern", "{domain}_{source}_{doc_no}_{page_no}")
    except Exception:
        filename_pattern = "{domain}_{source}_{doc_no}_{page_no}"
        
    mock_base = filename_pattern.replace("{domain}", domain)\
                                .replace("{source}", "spx_express")\
                                .replace("{doc_no}", "mock_spx_receipt")\
                                .replace("{page_no}", "001")
        
    # 1. Create a dummy receipt image using PIL
    mock_img_path = os.path.join(split_dir, f"{mock_base}.png").replace("\\", "/")
    if not os.path.exists(mock_img_path):
        img = Image.new('RGB', (600, 850), color=(245, 245, 245))
        d = ImageDraw.Draw(img)
        
        # Draw mock receipt headers and text
        d.text((50, 40), "SPX Express Tax Invoice / Receipt (MOCK)", fill=(0, 0, 0))
        d.text((50, 80), "SPX Express (Thailand) Co., Ltd. (สำนักงานใหญ่)", fill=(0, 0, 0))
        d.text((50, 110), "Tax ID: 0105561164871", fill=(0, 0, 0))
        d.text((50, 140), "Date: 2026-08-15", fill=(0, 0, 0))
        d.line([(50, 180), (550, 180)], fill=(0, 0, 0), width=2)
        
        d.text((50, 200), "Items:", fill=(0, 0, 0))
        d.text((70, 230), "1. Shipping Fee - SPXTH987654321    Qty: 1   Price: 100.00", fill=(0, 0, 0))
        d.text((70, 260), "2. Bubble Wrap Packaging Material   Qty: 2   Price: 10.00", fill=(0, 0, 0))
        d.line([(50, 310), (550, 310)], fill=(0, 0, 0), width=1)
        
        d.text((320, 330), "Subtotal:        120.00 THB", fill=(0, 0, 0))
        d.text((320, 360), "Discount:          0.00 THB", fill=(0, 0, 0))
        d.text((320, 390), "VAT (7% Included):  0.00 THB", fill=(0, 0, 0))
        d.text((320, 420), "Net Amount:      120.00 THB", fill=(0, 0, 0))
        
        d.line([(50, 460), (550, 460)], fill=(0, 0, 0), width=2)
        d.text((50, 480), "Payment Method: ShopeePay", fill=(0, 0, 0))
        img.save(mock_img_path)
        
    # 2. Create the corresponding JSON file
    mock_json_path = os.path.join(queue_dir, f"{mock_base}.json").replace("\\", "/")
    if not os.path.exists(mock_json_path):
        mock_data = {
            "transaction_date": "2026-08-15",
            "merchant_name": "SPX Express (Thailand) Co., Ltd.",
            "tax_id": "0105561164871",
            "expense_category": "Delivery",
            "items": [
                {"name": "Shipping Fee - SPXTH987654321", "qty": 1, "unit_price": 100.0, "total_price": 100.0},
                {"name": "Bubble Wrap Packaging Material", "qty": 2, "unit_price": 10.0, "total_price": 20.0}
            ],
            "financial_summary": {
                "subtotal": 120.0,
                "discount": 0.0,
                "vat_amount": 0.0,
                "net_amount": 120.0
            },
            "payment_method": "ShopeePay"
        }
        with open(mock_json_path, "w", encoding="utf-8") as f:
            json.dump(mock_data, f, ensure_ascii=False, indent=2)

def main_app():
    # Initialize logger
    setup_logger()
    
    # 1. Run system-wide configuration validation
    settings_valid, settings_errors = validate_settings_config()
    if not settings_valid:
        st.title("❌ ระบบขัดข้อง: ตั้งค่าระบบไม่ถูกต้อง")
        st.error("พบข้อผิดพลาดรุนแรงในไฟล์ `configs/settings.json`:")
        for err in settings_errors:
            st.markdown(f"- {err}")
        st.info("💡 กรุณาตรวจสอบและแก้ไขไฟล์ตั้งค่าให้ถูกต้องเพื่อให้ระบบสามารถเปิดบริการได้")
        return
        
    # 2. Check environment & critical packages
    env_warnings = validate_environment()
    env_errors = [msg for msg in env_warnings if "[ERROR]" in msg]
    if env_errors:
        st.title("❌ ระบบขัดข้อง: ขาดไลบรารีในระบบ")
        st.error("โฮสต์ของเซิร์ฟเวอร์ยังไม่พร้อมใช้งานเนื่องจากขาดแพ็คเกจที่สำคัญ:")
        for err in env_errors:
            st.markdown(f"- {err}")
        st.info("💡 กรุณารันคำสั่ง `pip install -r requirements.txt` ใน Terminal")
        return
        
    # 3. Ensure storage folders exist
    initialize_storage_directories()
    
    # Load configuration
    try:
        with open("configs/settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        st.title("❌ ระบบขัดข้อง: โหลดตั้งค่าล้มเหลว")
        st.error(f"เกิดข้อผิดพลาดระหว่างโหลดไฟล์ตั้งค่า: {e}")
        return

    st.title("📄 ระบบตรวจสอบและยืนยันข้อมูลใบเสร็จรับเงิน (Review & Confirm)")
    
    # Sidebar
    st.sidebar.header("⚙️ ตั้งค่าระบบ (Settings)")
    
    # Check Gemini API Key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.sidebar.warning("⚠️ ไม่พบ GEMINI_API_KEY ในไฟล์ .env โปรดกรอกคีย์เพื่อรันการวิเคราะห์เอกสารใหม่ด้วย AI")
    else:
        st.sidebar.success("🔑 ตรวจพบ Gemini API Key เรียบร้อย")
        
    # 1. Select Active Domain
    active_domains = settings.get("active_domains", ["expense_receipt"])
    selected_domain = st.sidebar.selectbox("เลือกโดเมนเอกสาร (Domain)", active_domains)
    
    # 4. Validate selected domain configuration
    domain_valid, domain_errors = validate_domain_config(selected_domain)
    if not domain_valid:
        st.error(f"❌ โดเมน '{selected_domain}' มีข้อผิดพลาดในไฟล์ตั้งค่า:")
        for err in domain_errors:
            st.markdown(f"- {err}")
        st.info("💡 กรุณาแก้ไขโครงสร้างไฟล์ Schema, Prompt หรือ Rules ของโดเมนนี้ให้เรียบร้อย")
        return
    
    domain_storage = os.path.join(storage_root, selected_domain)
    
    # Auto-generate mock data to allow immediate previewing
    ensure_mock_data(selected_domain)
    
    # 2. File Uploading section
    st.sidebar.subheader("📥 อัปโหลดเอกสารใหม่ (Upload Document)")
    uploaded_file = st.sidebar.file_uploader(
        "อัปโหลดไฟล์ PDF หรือรูปภาพใบเสร็จ", 
        type=["pdf", "png", "jpg", "jpeg"]
    )
    
    if uploaded_file is not None:
        if st.sidebar.button("🚀 ประมวลผลเอกสารด้วย AI"):
            # Ensure directories exist
            inbox_uncat = os.path.join(domain_storage, "01_raw_inbox", "uncategorized")
            os.makedirs(inbox_uncat, exist_ok=True)
            
            # Save file to uncategorized inbox
            temp_path = os.path.join(inbox_uncat, uploaded_file.name).replace("\\", "/")
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            # Process E2E using main.py flow
            with st.spinner("กำลังประมวลผลไฟล์ (แยกหน้า -> จับคู่ -> สกัดข้อมูลด้วย AI)..."):
                try:
                    split_dir = os.path.join(domain_storage, "02_split_pages")
                    queue_dir = os.path.join(domain_storage, "03_processing_queue")
                    
                    # Split pages
                    first_page_image = None
                    if uploaded_file.name.lower().endswith(".pdf"):
                        image_paths = split_pdf(temp_path, split_dir)
                        if image_paths:
                            first_page_image = image_paths[0]
                    else:
                        image_paths = [temp_path]
                        
                    # Calculate SHA-256 and check duplicate document
                    file_hash = calculate_file_hash(temp_path)
                    is_dup, dup_meta = check_duplicate_document(file_hash)
                    if is_dup:
                        if dup_meta['status'] == 'archived':
                            st.sidebar.error(f"❌ ตรวจพบไฟล์ซ้ำ: ไฟล์นี้เคยถูกประมวลผลและจัดเก็บแล้ว (ในโดเมน: {dup_meta['domain']} เมื่อ {dup_meta['processed_at']})")
                        else:
                            st.sidebar.error(f"❌ ตรวจพบไฟล์ซ้ำ: ไฟล์นี้มีอยู่ในคิวประมวลผลแล้ว (สถานะ: {dup_meta['status']})")
                        # Clean up temp upload file
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        # Clean up split images
                        if image_paths:
                            for img in image_paths:
                                if os.path.exists(img) and img != temp_path:
                                    os.remove(img)
                        return
                        
                    # Source matching
                    source = match_source(temp_path, selected_domain, first_page_image)
                    
                    # Move to flat inbox folder
                    inbox_dir = os.path.join(domain_storage, "01_raw_inbox")
                    if source == "_default":
                        dest_folder = os.path.join(inbox_dir, "_uncategorized")
                    else:
                        dest_folder = os.path.join(inbox_dir, source)
                        
                    os.makedirs(dest_folder, exist_ok=True)
                    dest_path = os.path.join(dest_folder, uploaded_file.name).replace("\\", "/")
                    shutil.move(temp_path, dest_path)
                    
                    # Record document state in SQLite DB
                    try:
                        insert_pending_document(file_hash, selected_domain, uploaded_file.name, source)
                    except Exception as ie:
                        logger.warning(f"Failed to record pending document state in database: {ie}")
                    
                    # Rename split images to systematic naming format
                    base_filename = os.path.splitext(uploaded_file.name)[0]
                    archiving_cfg = settings.get("archiving", {})
                    filename_pattern = archiving_cfg.get("filename_pattern", "{domain}_{source}_{doc_no}_{page_no}")
                    
                    renamed_image_paths = []
                    for i, old_path in enumerate(image_paths):
                        page_num = i + 1
                        new_filename_base = filename_pattern.replace("{domain}", selected_domain)\
                                                            .replace("{source}", source)\
                                                            .replace("{doc_no}", base_filename)\
                                                            .replace("{page_no}", f"{page_num:03d}")
                        new_filename = f"{new_filename_base}.png"
                        new_path = os.path.join(split_dir, new_filename).replace("\\", "/")
                        
                        if uploaded_file.name.lower().endswith(".pdf"):
                            if os.path.exists(old_path):
                                if os.path.exists(new_path):
                                    os.remove(new_path)
                                os.rename(old_path, new_path)
                            renamed_image_paths.append(new_path)
                        else:
                            shutil.copy(old_path, new_path)
                            renamed_image_paths.append(new_path)
                            
                    image_paths = renamed_image_paths
                    
                    # Extract for each page
                    for i, img_path in enumerate(image_paths):
                        page_num = i + 1
                        page_data = extract_receipt_data(img_path, source, selected_domain)
                        
                        new_json_base = filename_pattern.replace("{domain}", selected_domain)\
                                                        .replace("{source}", source)\
                                                        .replace("{doc_no}", base_filename)\
                                                        .replace("{page_no}", f"{page_num:03d}")
                        json_filename = f"{new_json_base}.json"
                        queue_json_path = os.path.join(queue_dir, json_filename)
                        
                        with open(queue_json_path, "w", encoding="utf-8") as f:
                            json.dump(page_data, f, ensure_ascii=False, indent=2)
                            
                    st.sidebar.success("🎉 ประมวลผลสำเร็จและเพิ่มเข้าคิวตรวจแก้เรียบร้อยแล้ว!")
                    # Force rerun to update queue
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ เกิดข้อผิดพลาดในการประมวลผล: {e}")
                    
    # Read the queue
    queue_dir = os.path.join(domain_storage, "03_processing_queue")
    queue_files = sorted([f for f in os.listdir(queue_dir) if f.endswith(".json")])
    
    if not queue_files:
        st.info("ℹ️ ไม่มีเอกสารค้างอยู่ในคิวตรวจสอบในขณะนี้ คุณสามารถอัปโหลดไฟล์ใหม่ได้ในแถบเมนูด้านซ้าย")
        return
        
    st.subheader(f"📋 คิวรอการตรวจสอบและยืนยัน ({len(queue_files)} รายการ)")
    selected_json_file = st.selectbox("เลือกเอกสารที่ต้องการตรวจสอบ", queue_files)
    
    if selected_json_file:
        json_path = os.path.join(queue_dir, selected_json_file).replace("\\", "/")
        
        # Load the extracted data JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        base_name = os.path.splitext(selected_json_file)[0]
        
        # Check corresponding split image
        split_dir = os.path.join(domain_storage, "02_split_pages")
        
        # Logic to find the matching page image
        img_filename = f"{base_name}.png"
        image_path = os.path.join(split_dir, img_filename).replace("\\", "/")
        
        # Fallback if page name has slight variation
        if not os.path.exists(image_path):
            # Check for pattern base_name_page_X.png
            candidates = [f for f in os.listdir(split_dir) if f.startswith(base_name) and f.endswith(".png")]
            if candidates:
                image_path = os.path.join(split_dir, candidates[0]).replace("\\", "/")
                
        # Draw the layout: 2 columns
        col1, col2 = st.columns([1.2, 1.0])
        
        # Column 1: Document View
        with col1:
            st.markdown("### 🖼️ ภาพเอกสารต้นฉบับ")
            if os.path.exists(image_path):
                st.image(image_path, use_container_width=True)
            else:
                st.warning("⚠️ ไม่พบรูปภาพของหน้าเอกสารต้นฉบับ")
                
        # Column 2: Data Review Form
        with col2:
            st.markdown("### ✍️ แบบฟอร์มตรวจแก้ไขข้อมูล")
            
            # General Info Form
            st.markdown("##### 📌 ข้อมูลทั่วไป")
            
            col_date, col_merchant = st.columns(2)
            with col_date:
                raw_date = data.get("transaction_date", "")
                try:
                    # Convert string to date object for st.date_input
                    default_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError:
                    default_date = datetime.today().date()
                
                date_val = st.date_input("วันที่ทำรายการ (Transaction Date)", default_date)
                transaction_date = date_val.strftime("%Y-%m-%d")
                
            with col_merchant:
                merchant_name = st.text_input("ชื่อร้านค้า (Merchant Name)", data.get("merchant_name", ""))
                
            col_tax, col_category = st.columns(2)
            with col_tax:
                tax_id = st.text_input("เลขผู้เสียภาษี (Tax ID)", data.get("tax_id", ""))
            with col_category:
                expense_category = st.selectbox(
                    "หมวดหมู่ค่าใช้จ่าย (Expense Category)",
                    ["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"],
                    index=["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"].index(
                        data.get("expense_category", "Other") if data.get("expense_category", "Other") in 
                        ["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"] else "Other"
                    )
                )
                
            # Items table
            st.markdown("##### 🛍️ รายการสินค้าและบริการ (Items)")
            items_list = data.get("items", [])
            df_items = pd.DataFrame(items_list)
            
            if df_items.empty:
                df_items = pd.DataFrame(columns=["name", "qty", "unit_price", "total_price"])
                
            # Make columns editable
            edited_df = st.data_editor(
                df_items, 
                num_rows="dynamic",
                column_config={
                    "name": st.column_config.TextColumn("ชื่อสินค้า / บริการ", width="medium", required=True),
                    "qty": st.column_config.NumberColumn("จำนวน", min_value=1, step=1, required=True),
                    "unit_price": st.column_config.NumberColumn("ราคาต่อหน่วย", min_value=0.0, format="%.2f", required=True),
                    "total_price": st.column_config.NumberColumn("ราคารวม", min_value=0.0, format="%.2f", required=True),
                },
                use_container_width=True
            )
            
            # Financial Summary
            st.markdown("##### 💰 ยอดรวมเงิน (Financial Summary)")
            summary = data.get("financial_summary", {})
            
            col_sub, col_disc = st.columns(2)
            with col_sub:
                subtotal = st.number_input("ยอดรวมก่อนหักส่วนลด (Subtotal)", min_value=0.0, value=float(summary.get("subtotal", 0.0)), format="%.2f")
            with col_disc:
                discount = st.number_input("ส่วนลด (Discount)", min_value=0.0, value=float(summary.get("discount", 0.0)), format="%.2f")
                
            col_vat, col_net = st.columns(2)
            with col_vat:
                vat_amount = st.number_input("ภาษีมูลค่าเพิ่ม (VAT Amount)", min_value=0.0, value=float(summary.get("vat_amount", 0.0)), format="%.2f")
            with col_net:
                net_amount = st.number_input("ยอดเงินสุทธิ (Net Amount)", min_value=0.0, value=float(summary.get("net_amount", 0.0)), format="%.2f")
                
            payment_method = st.text_input("ช่องทางการชำระเงิน (Payment Method)", data.get("payment_method", ""))
            
            st.markdown("---")
            
            # Export Settings inside Col 2
            st.markdown("##### 📤 รูปแบบการส่งออกข้อมูล")
            
            col_temp, col_fmt = st.columns(2)
            with col_temp:
                templates_dir = f"configs/domains/{selected_domain}/outputs"
                templates = sorted([os.path.splitext(f)[0] for f in os.listdir(templates_dir) if f.endswith(".json")])
                selected_template = st.selectbox("เลือกเทมเพลตสำหรับเขียนคอลัมน์", templates)
            with col_fmt:
                export_fmt = st.radio("เลือกฟอร์แมตไฟล์ปลายทาง", ["CSV", "JSON"], horizontal=True)
                
            # Submit/Confirm Button
            if st.button("✅ ยืนยันข้อมูลและส่งออกรายงาน (Confirm & Export)", type="primary", use_container_width=True):
                # 1. Rebuild dictionary from form inputs
                final_data = {
                    "transaction_date": transaction_date,
                    "merchant_name": merchant_name,
                    "tax_id": tax_id,
                    "expense_category": expense_category,
                    "items": edited_df.to_dict(orient="records"),
                    "financial_summary": {
                        "subtotal": subtotal,
                        "discount": discount,
                        "vat_amount": vat_amount,
                        "net_amount": net_amount
                    },
                    "payment_method": payment_method
                }
                
                try:
                    # 2. Transform the confirmed data
                    template_path = os.path.join(templates_dir, f"{selected_template}.json")
                    transformed_rows = transform_data(final_data, template_path)
                    
                    # 3. Write/Append output
                    os.makedirs("outputs", exist_ok=True)
                    output_file_base = os.path.join("outputs", f"{selected_domain}_{selected_template}_export")
                    
                    if export_fmt == "CSV":
                        output_path = f"{output_file_base}.csv"
                        df_new = pd.DataFrame(transformed_rows)
                        
                        if os.path.exists(output_path):
                            df_old = pd.read_csv(output_path)
                            df_final = pd.concat([df_old, df_new], ignore_index=True)
                        else:
                            df_final = df_new
                            
                        df_final.to_csv(output_path, index=False, encoding="utf-8-sig")
                    else:
                        output_path = f"{output_file_base}.json"
                        
                        if os.path.exists(output_path):
                            with open(output_path, "r", encoding="utf-8") as rf:
                                list_old = json.load(rf)
                        else:
                            list_old = []
                            
                        list_old.extend(transformed_rows)
                        with open(output_path, "w", encoding="utf-8") as wf:
                            json.dump(list_old, wf, ensure_ascii=False, indent=2)
                            
                    # 4. Archive raw file & confirmed JSON
                    archive_dir = os.path.join(domain_storage, "04_archive")
                    current_month = datetime.now().strftime("%Y-%m")
                    month_archive_raw = os.path.join(archive_dir, current_month, "raw")
                    month_archive_json = os.path.join(archive_dir, current_month, "verified_json")
                    
                    os.makedirs(month_archive_raw, exist_ok=True)
                    os.makedirs(month_archive_json, exist_ok=True)
                    
                    # Parse original doc_no and page_num from systematic base_name based on filename_pattern
                    archiving_cfg = settings.get("archiving", {})
                    keep_split_pages = archiving_cfg.get("keep_split_pages", True)
                    split_format_str = archiving_cfg.get("split_format", "pdf, png")
                    filename_pattern = archiving_cfg.get("filename_pattern", "{domain}_{source}_{doc_no}_{page_no}")
                    formats = [fmt.strip().lower() for fmt in split_format_str.split(",") if fmt.strip()]
                    
                    doc_no = base_name
                    page_num = 1
                    try:
                        prefix_tpl = filename_pattern.split("{doc_no}")[0]
                        prefix = prefix_tpl.replace("{domain}", selected_domain).replace("{source}", source)
                        suffix_tpl = filename_pattern.split("{doc_no}")[1]
                        
                        if base_name.startswith(prefix):
                            remaining = base_name[len(prefix):]
                            sep = suffix_tpl.replace("{page_no}", "")
                            if sep and sep in remaining:
                                doc_part, page_str = remaining.rsplit(sep, 1)
                                doc_no = doc_part
                                page_num = int(page_str)
                            else:
                                doc_no = remaining
                                page_num = 1
                    except Exception as parse_err:
                        logger.warning(f"Could not parse filename dynamically: {parse_err}. Using fallbacks.")
                        
                    # Search 01_raw_inbox subfolders for the original document
                    inbox_dir = os.path.join(domain_storage, "01_raw_inbox")
                    original_file_path = None
                    if os.path.exists(inbox_dir):
                        for folder in os.listdir(inbox_dir):
                            source_folder = os.path.join(inbox_dir, folder)
                            if os.path.isdir(source_folder) and folder not in ("_default",):
                                for f in os.listdir(source_folder):
                                    if os.path.splitext(f)[0] == doc_no:
                                        original_file_path = os.path.join(source_folder, f).replace("\\", "/")
                                        break
                            if original_file_path:
                                break
                            
                    # Move original file to archive (only if not already moved by another page)
                    dest_orig_path = None
                    if original_file_path and os.path.exists(original_file_path):
                        dest_orig_path = os.path.join(month_archive_raw, os.path.basename(original_file_path)).replace("\\", "/")
                        if not os.path.exists(dest_orig_path):
                            shutil.move(original_file_path, dest_orig_path)
                    elif original_file_path:
                        # If already moved, reference the archived path
                        dest_orig_path = os.path.join(month_archive_raw, os.path.basename(original_file_path)).replace("\\", "/")
                        
                    # Update document status to archived in SQLite DB
                    pdf_source = dest_orig_path if dest_orig_path and os.path.exists(dest_orig_path) else original_file_path
                    if pdf_source and os.path.exists(pdf_source):
                        try:
                            doc_file_hash = calculate_file_hash(pdf_source)
                            update_document_to_archived(doc_file_hash, selected_domain, source)
                        except Exception as ae:
                            logger.error(f"Failed to update document status to archived in database: {ae}")
                    
                    # Write confirmed JSON to archive
                    archive_json_path = os.path.join(month_archive_json, selected_json_file)
                    with open(archive_json_path, "w", encoding="utf-8") as af:
                        json.dump(final_data, af, ensure_ascii=False, indent=2)
                    os.remove(json_path)
                    
                    # Get archiving configurations
                    # (Loaded dynamically above)
                    
                    # Handle split pages archiving
                    if keep_split_pages:
                        # 1. Archive as PNG
                        if "png" in formats and os.path.exists(image_path):
                            shutil.copy(image_path, os.path.join(month_archive_raw, f"{base_name}.png"))
                            
                        # 2. Archive as JPEG/JPG
                        if ("jpg" in formats or "jpeg" in formats) and os.path.exists(image_path):
                            try:
                                im = Image.open(image_path)
                                rgb_im = im.convert('RGB')
                                rgb_im.save(os.path.join(month_archive_raw, f"{base_name}.jpg"), 'JPEG')
                            except Exception as je:
                                logger.error(f"Failed to convert PNG to JPEG for archive: {je}")
                                
                        # 3. Archive as single page PDF
                        if "pdf" in formats:
                            pdf_source = dest_orig_path if dest_orig_path and os.path.exists(dest_orig_path) else original_file_path
                            if pdf_source and pdf_source.lower().endswith(".pdf"):
                                from src.core.pdf_splitter import extract_pdf_page_to_pdf
                                target_pdf_path = os.path.join(month_archive_raw, f"{base_name}.pdf")
                                try:
                                    extract_pdf_page_to_pdf(pdf_source, page_num, target_pdf_path)
                                except Exception as pe:
                                    logger.error(f"Failed to extract single page PDF for archive: {pe}")
                                    
                    # Clean up temporary split image in 02_split_pages
                    if os.path.exists(image_path):
                        os.remove(image_path)
                                    
                    st.success(f"💾 บันทึกข้อมูลและต่อท้ายรายงานใน {output_path} เรียบร้อยแล้ว!")
                    st.toast("บันทึกข้อมูลสำเร็จ!", icon="✅")
                    
                    # Wait and rerun
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกหรือส่งออกรายงาน: {e}")
                    
            # System Log Viewer at the bottom of Col 2
            st.markdown("---")
            with st.expander("🛠️ ประวัติการทำงานระบบย้อนหลัง (System Process Logs)", expanded=False):
                logging_cfg = settings.get("logging", {})
                logs_dir = logging_cfg.get("logs_dir", "logs")
                current_date = datetime.now().strftime("%Y%m%d")
                log_filename = f"logs_{current_date}.txt"
                log_path = os.path.join(logs_dir, log_filename).replace("\\", "/")
                
                # Dynamic line count selector
                log_lines_count = st.number_input(
                    "จำนวนบรรทัดล็อกล่าสุดที่ต้องการแสดง",
                    min_value=10,
                    max_value=500,
                    value=100,
                    step=10
                )
                
                if os.path.exists(log_path):
                    try:
                        with open(log_path, "r", encoding="utf-8") as lf:
                            log_lines = lf.readlines()
                        
                        # Get last N lines
                        sliced_lines = log_lines[-log_lines_count:]
                        st.code("".join(sliced_lines), language="text")
                        
                        # Full Log Download Button
                        with open(log_path, "r", encoding="utf-8") as lf:
                            full_log_data = lf.read()
                            
                        st.download_button(
                            label="📥 ดาวน์โหลดไฟล์ Log ฉบับเต็ม (.txt)",
                            data=full_log_data,
                            file_name=log_filename,
                            mime="text/plain",
                            use_container_width=True
                        )
                    except Exception as le:
                        st.error(f"ไม่สามารถโหลดไฟล์ Log ได้: {le}")
                else:
                    st.info("ยังไม่มีบันทึกประวัติการทำงานในวันนี้")
                
                if st.button("🔄 รีเฟรชบันทึก (Refresh Logs)", use_container_width=True):
                    st.rerun()

if __name__ == "__main__":
    main_app()
