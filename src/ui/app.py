import os
import sys
import json
import shutil
import pandas as pd
import streamlit as st
from PIL import Image
from datetime import datetime, date
from dotenv import load_dotenv

# Set python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import core modules
from src.core.pdf_splitter import split_pdf
from src.core.source_matcher import match_source
from src.core.extractor import extract_document_data
from src.core.transformer import transform_data
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    validate_environment,
    initialize_storage_directories
)
from src.core.logger import setup_logger
from loguru import logger
from src.core.config_loader import load_system_settings, get_active_domains_hybrid, get_active_sources_hybrid
from src.core.db import (
    calculate_file_hash,
    check_duplicate_document,
    get_pending_documents,
    get_document_pages,
    get_batch_pages,
    get_document_by_id,
    update_document_to_approved,
    update_document_payload,
    update_document_to_failed,
    search_documents,
    get_domains,
    get_sources,
    update_domain_active_status,
    update_source_active_status
)
from main import process_document

# Page configuration
st.set_page_config(
    page_title="AI Multi-Docs Extraction Pipeline",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load settings and environment
load_dotenv()
settings = load_system_settings("configs/settings.json")
storage_root = settings.get("storage_root", "pipeline_storage")

def ensure_mock_data(domain: str):
    """
    Ensures that mock data exists in the database if empty.
    """
    # Simply runs database and directory setup
    initialize_storage_directories()

def main_app():
    # Setup logger
    setup_logger()
    
    # 1. System configurations check
    settings_valid, settings_errors = validate_settings_config()
    if not settings_valid:
        st.title("❌ ระบบขัดข้อง: ตั้งค่าระบบไม่ถูกต้อง")
        st.error("พบข้อผิดพลาดรุนแรงในไฟล์ `configs/settings.json`:")
        for err in settings_errors:
            st.markdown(f"- {err}")
        st.info("💡 กรุณาตรวจสอบและแก้ไขไฟล์ตั้งค่าให้ถูกต้อง")
        return
        
    # 2. Dependency check
    env_warnings = validate_environment()
    env_errors = [msg for msg in env_warnings if "[ERROR]" in msg]
    if env_errors:
        st.title("❌ ระบบขัดข้อง: ขาดไลบรารีในระบบ")
        st.error("โฮสต์ของเซิร์ฟเวอร์ยังไม่พร้อมใช้งานเนื่องจากขาดแพ็คเกจที่สำคัญ:")
        for err in env_errors:
            st.markdown(f"- {err}")
        st.info("💡 กรุณารันคำสั่ง `pip install -r requirements.txt` ใน Terminal")
        return
        
    # 3. Ensure directories are ready
    initialize_storage_directories()
    
    st.title("📄 AI-Multi-Docs-Extraction-Pipeline Dashboard")
    
    # Sidebar: Domain Selection and Document Ingestion
    st.sidebar.header("⚙️ เมนูควบคุม (Control Panel)")
    
    # Check Gemini API Key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.sidebar.warning("⚠️ ไม่พบ GEMINI_API_KEY ในไฟล์ .env โปรดกรอกเพื่อสกัดด้วย AI")
    else:
        st.sidebar.success("🔑 ตรวจพบ Gemini API Key เรียบร้อย")
        
    # Load Active Domains dynamically from SQLite
    active_domains = get_active_domains_hybrid()
    if not active_domains:
        st.error("❌ ไม่พบโดเมนที่เปิดใช้งานในระบบ แอดมินต้องเปิดใช้งานอย่างน้อย 1 โดเมนที่แท็บ Settings")
        active_domains = [{"domain_id": "expense_receipt", "display_name": "ใบเสร็จค่าใช้จ่าย (Expense Receipt)"}]
        
    domain_options = {d["display_name"]: d["domain_id"] for d in active_domains}
    selected_domain_name = st.sidebar.selectbox("เลือกโดเมนเอกสาร (Domain)", list(domain_options.keys()))
    selected_domain = domain_options[selected_domain_name]
    
    domain_storage = os.path.join(storage_root, selected_domain)
    
    # Document upload block
    st.sidebar.subheader("📥 อัปโหลดเอกสารใหม่ (Upload Document)")
    uploaded_file = st.sidebar.file_uploader(
        "อัปโหลดไฟล์ PDF หรือรูปภาพใบเสร็จ", 
        type=["pdf", "png", "jpg", "jpeg"]
    )
    
    if uploaded_file is not None:
        # Load output templates for select
        templates_dir = f"configs/domains/{selected_domain}/outputs"
        templates = sorted([os.path.splitext(f)[0] for f in os.listdir(templates_dir) if f.endswith(".json")])
        selected_template = st.sidebar.selectbox("เลือกเทมเพลตส่งออก", templates)
        export_fmt = st.sidebar.radio("ฟอร์แมตไฟล์ปลายทาง", ["CSV", "JSON"], horizontal=True)
        
        if st.sidebar.button("🚀 ประมวลผลเอกสารด้วย AI"):
            inbox_uncat = os.path.join(domain_storage, "01_raw_inbox", "_uncategorized")
            os.makedirs(inbox_uncat, exist_ok=True)
            
            temp_path = os.path.join(inbox_uncat, uploaded_file.name).replace("\\", "/")
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            with st.spinner("กำลังประมวลผลไฟล์ (ตรวจสอบความสมบูรณ์ -> แยกหน้า -> ค้นหาร้านค้า -> สกัดข้อมูลด้วย AI)..."):
                try:
                    process_document(
                        file_path=temp_path,
                        domain=selected_domain,
                        template_name=selected_template,
                        export_format=export_fmt.lower(),
                        settings=settings
                    )
                    st.sidebar.success("🎉 ประมวลผลสำเร็จและเพิ่มเข้าคิวตรวจแก้เรียบร้อยแล้ว!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ เกิดข้อผิดพลาดในการประมวลผล: {e}")
                    # Clean up temp file if error
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

    # 3-Tab structure
    tab_review, tab_search, tab_settings = st.tabs([
        "🔎 ตรวจและอนุมัติ (Review & Approve)", 
        "📊 ค้นหาและประวัติ (Search & History)", 
        "⚙️ ตั้งค่าระบบ (Settings)"
    ])
    
    # TAB 1: REVIEW & APPROVE
    with tab_review:
        pending_docs = get_pending_documents(selected_domain)
        
        if not pending_docs:
            st.info("ℹ️ ไม่มีเอกสารค้างอยู่ในคิวตรวจสอบในขณะนี้ คุณสามารถอัปโหลดไฟล์ใหม่ได้ในเมนูด้านซ้าย")
        else:
            st.subheader(f"📋 คิวรอการตรวจสอบและยืนยัน ({len(pending_docs)} รายการ)")
            
            # Format selectbox choices
            doc_choices = {}
            for d in pending_docs:
                prio = d.get("review_priority") or "LOW"
                conf = d.get("overall_confidence")
                conf_str = f"{int(conf*100)}%" if conf is not None else "ไม่มีข้อมูล"
                is_blurry = " [ภาพเบลอ]" if d.get("is_blurry") == 1 else ""
                label = f"[{prio}] {d['original_pdf_name']} (ความแม่นยำ: {conf_str}{is_blurry}) - ID: {d['document_id'][:6]}"
                doc_choices[label] = d["document_id"]
                
            selected_doc_label = st.selectbox("เลือกเอกสารที่ต้องการตรวจสอบ", list(doc_choices.keys()))
            selected_doc_id = doc_choices[selected_doc_label]
            
            # Load selected document metadata and payload
            doc = get_document_by_id(selected_doc_id)
            pages = get_document_pages(selected_doc_id)
            if not pages:
                pages = get_batch_pages(doc["batch_id"])
                
            if doc:
                try:
                    data = json.loads(doc["data_payload"]) if doc["data_payload"] else {}
                except Exception:
                    data = {}
                
                # Check locked state
                is_locked = doc["is_locked"] == 1
                
                # Warning banner if locked
                if is_locked:
                    st.warning("⚠️ เอกสารนี้ได้รับการอนุมัติและล็อคแล้ว ไม่สามารถทำการแก้ไขหรือประมวลผลซ้ำได้")
                
                # Warning banner if scan was incomplete
                if doc["status_code"] == "FAILED" and doc["error_reason"]:
                    st.error(f"❌ พบข้อผิดพลาดของเอกสาร: {doc['error_reason']}")
                
                # Layout: 2 Columns
                col_left, col_right = st.columns([1.2, 1.0])
                
                # Left Column: Document viewer
                with col_left:
                    st.markdown("### 🖼️ ภาพเอกสารต้นฉบับ")
                    if pages:
                        if len(pages) > 1:
                            st.markdown(f"**📄 ตรวจพบหลายหน้า ({len(pages)} หน้า)**")
                            page_numbers = [p["page_number"] for p in pages]
                            selected_page_num = st.select_slider(
                                "เลื่อนสลับหน้าเอกสารเพื่อดูรายละเอียด", 
                                options=page_numbers, 
                                value=1
                            )
                            # Find matching page
                            selected_page = [p for p in pages if p["page_number"] == selected_page_num][0]
                            if os.path.exists(selected_page["image_path"]):
                                st.image(selected_page["image_path"], use_container_width=True, caption=f"หน้า {selected_page_num}")
                            else:
                                st.warning(f"⚠️ ไม่พบไฟล์รูปภาพหน้า {selected_page_num} ที่ {selected_page['image_path']}")
                        else:
                            # Single page
                            if os.path.exists(pages[0]["image_path"]):
                                st.image(pages[0]["image_path"], use_container_width=True)
                            else:
                                st.warning("⚠️ ไม่พบไฟล์รูปภาพของหน้าเอกสารต้นฉบับ")
                    else:
                        st.warning("⚠️ ไม่พบหน้ารูปภาพใดๆ ที่ผูกกับเอกสารนี้")
                
                # Right Column: Data Editor form
                with col_right:
                    st.markdown("### ✍️ แบบฟอร์มตรวจแก้ไขข้อมูล")
                    
                    # AI Quality Assessment Info Box
                    st.markdown("##### 🔍 ผลการประเมินการสกัดข้อมูล (AI Quality Assessment)")
                    col_conf, col_prio = st.columns(2)
                    with col_conf:
                        conf_val = doc.get("overall_confidence")
                        conf_str = f"{int(conf_val*100)}%" if conf_val is not None else "ไม่มีข้อมูล"
                        st.metric("ความแม่นยำของการสกัด (Confidence)", conf_str, 
                                  delta=doc.get("confidence_level"), delta_color="normal")
                    with col_prio:
                        st.metric("ลำดับความสำคัญในการตรวจ (Review Priority)", doc.get("review_priority") or "LOW")
                        
                    if doc.get("is_blurry") == 1:
                        st.warning("⚠️ ภาพต้นฉบับอาจจะเบลอหรือไม่ชัดเจน (Possibly blurry/low quality image)")
                    if doc.get("has_ambiguous_fields") == 1:
                        st.warning("⚠️ ตรวจพบฟิลด์ที่คลุมเครือหรือสูตรการคำนวณเงินไม่ตรงกัน (Ambiguous fields or math validation discrepancy)")
                        
                    notes = doc.get("confidence_notes")
                    if notes:
                        st.info(f"**บันทึกการประเมิน:** {notes}")
                        
                    st.markdown("---")
                    
                    st.markdown("##### 📌 ข้อมูลทั่วไป")
                    
                    col_doc_no, col_date = st.columns(2)
                    with col_doc_no:
                        doc_number = st.text_input(
                            "เลขที่เอกสาร (Document Number)", 
                            value=doc["doc_number"] if doc["doc_number"] else "",
                            disabled=is_locked
                        )
                    with col_date:
                        raw_date = doc["doc_date"] if doc["doc_date"] else ""
                        try:
                            default_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                        except ValueError:
                            default_date = date.today()
                        
                        date_val = st.date_input(
                            "วันที่ทำรายการ (Transaction Date)", 
                            value=default_date,
                            disabled=is_locked
                        )
                        transaction_date = date_val.strftime("%Y-%m-%d")
                        
                    col_merchant, col_tax = st.columns(2)
                    with col_merchant:
                        entity_name = st.text_input(
                            "ชื่อร้านค้า (Merchant Name)", 
                            value=doc["entity_name"] if doc["entity_name"] else "",
                            disabled=is_locked
                        )
                    with col_tax:
                        tax_id = st.text_input(
                            "เลขผู้เสียภาษี (Tax ID)", 
                            value=data.get("tax_id", ""),
                            disabled=is_locked
                        )
                        
                    expense_category = st.selectbox(
                        "หมวดหมู่ค่าใช้จ่าย (Expense Category)",
                        ["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"],
                        index=["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"].index(
                            data.get("expense_category", "Other") if data.get("expense_category", "Other") in 
                            ["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"] else "Other"
                        ),
                        disabled=is_locked
                    )
                    
                    # Items List Editor
                    st.markdown("##### 🛍️ รายการสินค้าและบริการ (Items)")
                    items_list = data.get("items", [])
                    df_items = pd.DataFrame(items_list)
                    if df_items.empty:
                        df_items = pd.DataFrame(columns=["name", "qty", "unit_price", "total_price"])
                        
                    edited_df = st.data_editor(
                        df_items, 
                        num_rows="dynamic" if not is_locked else "fixed",
                        column_config={
                            "name": st.column_config.TextColumn("ชื่อสินค้า / บริการ", width="medium", required=True),
                            "qty": st.column_config.NumberColumn("จำนวน", min_value=1, step=1, required=True),
                            "unit_price": st.column_config.NumberColumn("ราคาต่อหน่วย", min_value=0.0, format="%.2f", required=True),
                            "total_price": st.column_config.NumberColumn("ราคารวม", min_value=0.0, format="%.2f", required=True),
                        },
                        use_container_width=True,
                        disabled=is_locked
                    )
                    
                    # Financial Summary
                    st.markdown("##### 💰 ยอดรวมเงิน (Financial Summary)")
                    summary = data.get("financial_summary", {})
                    
                    col_sub, col_disc = st.columns(2)
                    with col_sub:
                        subtotal = st.number_input(
                            "ยอดรวมก่อนหักส่วนลด (Subtotal)", 
                            min_value=0.0, 
                            value=float(summary.get("subtotal", doc["total_amount"] or 0.0)), 
                            format="%.2f",
                            disabled=is_locked
                        )
                    with col_disc:
                        discount = st.number_input(
                            "ส่วนลด (Discount)", 
                            min_value=0.0, 
                            value=float(summary.get("discount", 0.0)), 
                            format="%.2f",
                            disabled=is_locked
                        )
                        
                    col_vat, col_net = st.columns(2)
                    with col_vat:
                        vat_amount = st.number_input(
                            "ภาษีมูลค่าเพิ่ม (VAT Amount)", 
                            min_value=0.0, 
                            value=float(summary.get("vat_amount", 0.0)), 
                            format="%.2f",
                            disabled=is_locked
                        )
                    with col_net:
                        net_amount = st.number_input(
                            "ยอดเงินสุทธิ (Net Amount)", 
                            min_value=0.0, 
                            value=float(summary.get("net_amount", doc["total_amount"] or 0.0)), 
                            format="%.2f",
                            disabled=is_locked
                        )
                        
                    payment_method = st.text_input(
                        "ช่องทางการชำระเงิน (Payment Method)", 
                        value=data.get("payment_method", ""),
                        disabled=is_locked
                    )
                    
                    st.markdown("---")
                    
                    # Export options
                    st.markdown("##### 📤 การส่งออกรายงาน")
                    from src.core.exporters import list_exporters
                    exporters_list = list_exporters(selected_domain)
                    
                    exporter_options = {exp["name"]: exp for exp in exporters_list}
                    selected_exp_name = st.selectbox("เลือกรูปแบบปลายทางสำหรับการส่งออก", list(exporter_options.keys()), disabled=is_locked)
                    selected_exporter = exporter_options[selected_exp_name]
                    selected_exporter_id = selected_exporter["exporter_id"]
                    
                    # Display custom parameters for the exporter if any
                    start_no = 1
                    voucher_prefix = "PV2608-"
                    
                    if selected_exporter["has_custom_params"]:
                        # Retrieve next running number from DB as default!
                        default_seq = 1
                        try:
                            default_seq = selected_exporter["handler"].get_next_sequence_number()
                        except Exception:
                            pass
                            
                        col_prefix, col_start_seq = st.columns(2)
                        with col_prefix:
                            voucher_prefix = st.text_input("Voucher Prefix", value="PV2608-", disabled=is_locked)
                        with col_start_seq:
                            start_no = st.number_input("เลขรันใบสำคัญเริ่มต้น (Start Sequence)", value=int(default_seq), min_value=1, step=1, disabled=is_locked)
                            
                    export_fmt = st.radio("ฟอร์แมตไฟล์ส่งออก", ["CSV", "JSON"], horizontal=True, disabled=is_locked)
                    
                    # If locked (meaning it's already APPROVED), show direct download button
                    if is_locked:
                        st.success("💾 เอกสารนี้ได้รับการอนุมัติเรียบร้อยแล้ว!")
                        try:
                            handler = selected_exporter["handler"]
                            doc_data = {
                                **data,
                                "source_id": doc["source_id"],
                                "domain_id": selected_domain,
                                "document_id": selected_doc_id,
                                "original_pdf_name": doc["original_pdf_name"]
                            }
                            kwargs = {}
                            if selected_exporter_id == "express_pv":
                                kwargs["start_voucher_no"] = start_no
                                kwargs["voucher_prefix"] = voucher_prefix
                                
                            df_dl = handler.transform([doc_data], **kwargs)
                            if not df_dl.empty:
                                if export_fmt == "CSV":
                                    encoding_dl = "cp874" if selected_exporter_id == "express_pv" else "utf-8-sig"
                                    csv_bytes = df_dl.to_csv(index=False, encoding=encoding_dl).encode(encoding_dl, errors="ignore")
                                    st.download_button(
                                        label=f"📥 ดาวน์โหลดไฟล์ CSV ({selected_exporter_id})",
                                        data=csv_bytes,
                                        file_name=f"{selected_domain}_{selected_exporter_id}_export.csv",
                                        mime="text/csv",
                                        use_container_width=True
                                    )
                                else:
                                    json_bytes = df_dl.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8")
                                    st.download_button(
                                        label=f"📥 ดาวน์โหลดไฟล์ JSON ({selected_exporter_id})",
                                        data=json_bytes,
                                        file_name=f"{selected_domain}_{selected_exporter_id}_export.json",
                                        mime="application/json",
                                        use_container_width=True
                                    )
                        except Exception as dl_err:
                            st.error(f"ไม่สามารถจัดทำไฟล์ดาวน์โหลดได้: {dl_err}")
                            
                    # Action buttons
                    col_action_confirm, col_action_re = st.columns(2)
                    with col_action_confirm:
                        if st.button("✅ อนุมัติข้อมูลและส่งออก (Confirm & Export)", type="primary", use_container_width=True, disabled=is_locked):
                            # Rebuild payload
                            items_dict = edited_df.to_dict(orient="records")
                            
                            # Check if human modified the payload values
                            original_items = data.get("items", [])
                            original_summary = data.get("financial_summary", {})
                            
                            is_edited = 0
                            if (items_dict != original_items or 
                                doc_number != doc["doc_number"] or 
                                transaction_date != doc["doc_date"] or 
                                entity_name != doc["entity_name"] or 
                                subtotal != original_summary.get("subtotal") or 
                                net_amount != original_summary.get("net_amount")):
                                is_edited = 1
                                
                            final_data = {
                                "transaction_date": transaction_date,
                                "merchant_name": entity_name,
                                "tax_id": tax_id,
                                "expense_category": expense_category,
                                "doc_number": doc_number,
                                "items": items_dict,
                                "financial_summary": {
                                    "subtotal": subtotal,
                                    "discount": discount,
                                    "vat_amount": vat_amount,
                                    "net_amount": net_amount
                                },
                                "payment_method": payment_method,
                                "validation_meta": data.get("validation_meta", {"is_complete": True, "missing_pages": [], "logical_page_order": []})
                            }
                            
                            # Update Payload and status to APPROVED in database
                            update_document_payload(
                                document_id=selected_doc_id,
                                data_payload=json.dumps(final_data, ensure_ascii=False),
                                status_code="APPROVED",
                                doc_number=doc_number,
                                doc_date=transaction_date,
                                entity_name=entity_name,
                                total_amount=net_amount,
                                is_manually_edited=is_edited
                            )
                            
                            update_document_to_approved(
                                document_id=selected_doc_id,
                                doc_number=doc_number,
                                doc_date=transaction_date,
                                entity_name=entity_name,
                                total_amount=net_amount,
                                data_payload=json.dumps(final_data, ensure_ascii=False),
                                confirmed_by="admin"
                            )
                            
                            # Call centralized archiving and exporting helper with custom exporter params
                            from src.core.post_processor import archive_and_export_document
                            kwargs = {}
                            if selected_exporter_id == "express_pv":
                                kwargs["start_voucher_no"] = start_no
                                kwargs["voucher_prefix"] = voucher_prefix
                                
                            archive_and_export_document(
                                document_id=selected_doc_id,
                                payload=final_data,
                                original_pdf_name=doc["original_pdf_name"],
                                domain_id=selected_domain,
                                source_id=doc["source_id"],
                                settings=settings,
                                **kwargs
                            )
                                
                            st.success(f"💾 อนุมัติข้อมูลและต่อท้ายรายงานเรียบร้อยแล้ว!")
                            st.toast("อนุมัติข้อมูลสำเร็จ!", icon="✅")
                            st.rerun()
                            
                    with col_action_re:
                        if st.button("🔄 สกัดข้อมูลใหม่ด้วย AI (Re-extract)", use_container_width=True, disabled=is_locked):
                            with st.spinner("กำลังเรียก AI สกัดหน้าเอกสารซ้ำ..."):
                                try:
                                    image_paths = [p["image_path"] for p in pages]
                                    re_extracted = extract_document_data(image_paths, doc["source_id"], selected_domain)
                                    
                                    # Re-calculate representation values
                                    doc_number = re_extracted.get("doc_number", "")
                                    doc_date = re_extracted.get("transaction_date", "")
                                    entity_name = re_extracted.get("merchant_name", "")
                                    total_amount = re_extracted.get("financial_summary", {}).get("net_amount", 0.0)
                                    
                                    validation_meta = re_extracted.get("validation_meta", {})
                                    is_complete = validation_meta.get("is_complete", True)
                                    missing = validation_meta.get("missing_pages", [])
                                    
                                    status_code = "PROCESSED"
                                    error_reason = None
                                    if not is_complete:
                                        status_code = "FAILED"
                                        error_reason = f"เอกสารสแกนมาไม่ครบถ้วน: ขาดหน้า {', '.join(map(str, missing))}"
                                        
                                    update_document_payload(
                                        document_id=selected_doc_id,
                                        data_payload=json.dumps(re_extracted, ensure_ascii=False),
                                        status_code=status_code,
                                        doc_number=doc_number,
                                        doc_date=doc_date,
                                        entity_name=entity_name,
                                        total_amount=total_amount,
                                        is_manually_edited=0
                                    )
                                    
                                    # Run Post-Processing Quality Assessment & Auto-Approval
                                    from src.core.post_processor import post_process_document
                                    post_process_document(
                                        document_id=selected_doc_id,
                                        payload=re_extracted,
                                        source_id=doc["source_id"],
                                        domain_id=selected_domain,
                                        settings=settings
                                    )
                                    
                                    if not is_complete:
                                        update_document_to_failed(selected_doc_id, error_reason)
                                        
                                    st.success("สกัดรูปภาพซ้ำเรียบร้อยแล้ว!")
                                    st.rerun()
                                except Exception as re_err:
                                    st.error(f"การสกัดข้อมูลซ้ำล้มเหลว: {re_err}")
                                    
    # TAB 2: SEARCH & HISTORY
    with tab_search:
        st.subheader("📊 ค้นหาประวัติเอกสารย้อนหลัง (Search & Historical Dashboard)")
        
        # Filter layout
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            sources = get_sources(selected_domain)
            source_options = ["All"] + [s["source_id"] for s in sources]
            search_source = st.selectbox("กรองตามร้านค้า (Source)", source_options)
        with col_f2:
            start_date_val = st.date_input("ตั้งแต่วันที่ (Start Date)", value=date(2026, 1, 1))
        with col_f3:
            end_date_val = st.date_input("ถึงวันที่ (End Date)", value=date.today())
        with col_f4:
            search_kw = st.text_input("ค้นหาคีย์เวิร์ด (Keyword Search)", placeholder="เลขที่เอกสาร, ชื่อร้านค้า...")
            
        # Run search query
        results = search_documents(
            domain_id=selected_domain,
            source_id=search_source if search_source != "All" else None,
            start_date=start_date_val.strftime("%Y-%m-%d"),
            end_date=end_date_val.strftime("%Y-%m-%d"),
            keyword=search_kw if search_kw else None
        )
        
        if not results:
            st.info("🔍 ไม่พบประวัติเอกสารที่ตรงตามเงื่อนไขที่เลือก")
        else:
            # Display results table
            df_res = pd.DataFrame(results)
            df_display = df_res[[
                "document_id", "doc_number", "doc_date", "entity_name", 
                "total_amount", "status_code", "is_manually_edited", "confirmed_at"
            ]].copy()
            df_display.columns = [
                "ID เอกสาร", "เลขที่เอกสาร", "วันที่ทำรายการ", "ชื่อร้านค้า", 
                "ยอดเงินสุทธิ", "สถานะ", "แก้ไขด้วยคน", "วันอนุมัติ"
            ]
            
            st.markdown(f"**พบลัพธ์ทั้งหมด {len(results)} รายการ**")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Select row for detail preview
            doc_ids = [r["document_id"] for r in results]
            select_detail_id = st.selectbox("เลือกเอกสารเพื่อดูรายละเอียดและภาพสแกน", doc_ids, format_func=lambda x: f"เอกสาร ID: {x[:8]}...")
            
            if select_detail_id:
                selected_result = [r for r in results if r["document_id"] == select_detail_id][0]
                
                col_det1, col_det2 = st.columns([1.0, 1.2])
                with col_det1:
                    st.markdown("### 📋 ข้อมูลสกัดโดยละเอียด")
                    st.write(f"**เลขที่เอกสาร:** {selected_result['doc_number']}")
                    st.write(f"**ร้านค้า:** {selected_result['entity_name']}")
                    st.write(f"**ยอดเงินสุทธิ:** {selected_result['total_amount']} บาท")
                    st.write(f"**สถานะการทำงาน:** `{selected_result['status_code']}`")
                    
                    if selected_result["error_reason"]:
                        st.error(f"**ปัญหาข้อผิดพลาด:** {selected_result['error_reason']}")
                        
                    st.markdown("**ข้อมูล JSON ดั้งเดิม (Raw Extraction Payload)**")
                    try:
                        st.json(json.loads(selected_result["data_payload"]))
                    except Exception:
                        st.text(selected_result["data_payload"])
                        
                with col_det2:
                    st.markdown("### 🖼️ เอกสารอ้างอิง")
                    res_pages = get_document_pages(select_detail_id)
                    if not res_pages:
                        res_pages = get_batch_pages(selected_result["batch_id"])
                        
                    if res_pages:
                        # Find valid image path
                        valid_page = None
                        for rp in res_pages:
                            if os.path.exists(rp["image_path"]):
                                valid_page = rp
                                break
                                
                        if valid_page:
                            st.image(valid_page["image_path"], use_container_width=True)
                        else:
                            st.warning("⚠️ ไฟล์รูปภาพถูกย้ายเข้าสู่แฟ้มจัดเก็บถาวร (Archive) แล้ว")
                    else:
                        st.info("ไม่มีรูปภาพสแกนสำหรับเอกสารนี้")
                        
    # TAB 3: ADMIN SETTINGS
    with tab_settings:
        st.subheader("⚙️ ระบบเปิด/ปิดการใช้งานและตั้งค่าแอดมิน (Admin & Toggle Settings)")
        
        # 1. Manage domains
        st.markdown("#### 📂 1. จัดการการเปิดใช้งานโดเมนเอกสาร (Manage Domains)")
        all_domains = get_domains()
        
        # Draw columns/grid for domains
        for d in all_domains:
            col_d_name, col_d_toggle = st.columns([3, 1])
            with col_d_name:
                st.write(f"**{d['display_name']}** (ID: `{d['domain_id']}`)")
            with col_d_toggle:
                is_act = d["is_active"] == 1
                toggle_val = st.checkbox("เปิดใช้งาน", value=is_act, key=f"domain_toggle_{d['domain_id']}")
                if toggle_val != is_act:
                    update_domain_active_status(d["domain_id"], 1 if toggle_val else 0)
                    st.toast(f"อัปเดตโดเมน {d['domain_id']} เป็น {'เปิด' if toggle_val else 'ปิด'} เรียบร้อย", icon="⚙️")
                    st.rerun()
                    
        st.markdown("---")
        
        # 2. Manage sources for selected domain
        st.markdown(f"#### 🛍️ 2. จัดการร้านค้า/ผู้ให้บริการ (Manage Sources) สำหรับ: {selected_domain_name}")
        all_sources = get_sources(selected_domain)
        
        if not all_sources:
            st.info("ไม่พบร้านค้าในโดเมนนี้")
        else:
            for s in all_sources:
                if s["source_id"] == "_default":
                    # Default fallback cannot be toggled off
                    st.write(f"🔹 **{s['display_name']}** (ID: `{s['source_id']}`) - ระบบบังคับเปิดเสมอ")
                    continue
                    
                col_s_name, col_s_toggle = st.columns([3, 1])
                with col_s_name:
                    st.write(f"**{s['display_name']}** (ID: `{s['source_id']}`)")
                with col_s_toggle:
                    is_act = s["is_active"] == 1
                    toggle_val = st.checkbox("เปิดใช้งาน", value=is_act, key=f"source_toggle_{s['source_id']}")
                    if toggle_val != is_act:
                        update_source_active_status(s["source_id"], 1 if toggle_val else 0)
                        st.toast(f"อัปเดตร้านค้า {s['source_id']} เป็น {'เปิด' if toggle_val else 'ปิด'} เรียบร้อย", icon="⚙️")
                        st.rerun()

if __name__ == "__main__":
    main_app()
