import os
import sys
import json
import shutil
from datetime import datetime, date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
from loguru import logger

# Set python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import core modules
from src.infrastructure.pdf.image_service import split_pdf
from src.application.usecases.extractor import extract_document_data
from src.domain.services.transformer import transform_data
from src.infrastructure.common.constants import DefaultPath, SystemUserId
from src.application.usecases.initializer import (
    validate_settings_config,
    validate_doc_type_config,
    validate_environment,
    initialize_storage_directories
)
from src.infrastructure.common.logger import setup_logger
from src.infrastructure.common.config_loader import (
    load_system_settings,
    get_active_doc_types,
    get_default_company_code,
    get_company_storage_dir,
    get_company_pipeline_folder,
)
from src.infrastructure.persistence import (
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
    get_doc_types,
    get_sources,
    update_doc_type_active_status,
    update_source_active_status,
    get_pending_merchants,
    get_merchants,
    approve_merchant,
    ignore_merchant,
    upsert_merchant,
    get_all_companies,
    get_company,
    get_company_by_code,
    create_company,
    update_company,
)
from src.application.pipeline import split_and_match, release_pending_merchant_files
from src.application.pipeline.stage_4_validation import post_process_document, archive_and_export_document


from src.infrastructure.exporters import list_exporters
from src.infrastructure.common.config_loader import get_app_metadata

_app_meta = get_app_metadata()

# Page configuration
st.set_page_config(
    page_title=_app_meta["app_name"],
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cached resources for performance
@st.cache_resource
def get_cached_settings() -> dict:
    """
    Loads and caches system settings resource.
    """
    load_dotenv()
    return load_system_settings("configs/settings.json")

@st.cache_data(ttl=15)
def get_cached_pending_documents(domain_id: str, company_id: str = None) -> List[Dict[str, Any]]:
    """
    Caches pending documents for 15 seconds to improve UI snappiness.
    """
    return get_pending_documents(domain_id, company_id=company_id)

def main_app():
    # Setup logger once per session
    if "logger_initialized" not in st.session_state:
        setup_logger()
        st.session_state["logger_initialized"] = True
        
    settings = get_cached_settings()
    storage_root = settings.get("storage_root", DefaultPath.STORAGE_ROOT)
    
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
    
    # Sidebar: Company Selection, Domain Selection and Document Ingestion
    st.sidebar.header("⚙️ เมนูควบคุม (Control Panel)")
    
    # Company Selection
    all_companies = get_all_companies(active_only=True)
    if not all_companies:
        from src.infrastructure.persistence import get_or_create_default_company
        default_c = get_or_create_default_company()
        all_companies = [default_c]
        
    company_options = {f"{c['company_code']} - {c['company_name']}": c for c in all_companies}
    selected_company_label = st.sidebar.selectbox(
        "🏢 เลือกลูกค้า / บริษัท (Company)",
        list(company_options.keys())
    )
    selected_company = company_options[selected_company_label]
    selected_company_code = selected_company["company_code"]
    selected_company_id = selected_company["company_id"]
    
    # Reviewer Name (Configurable instead of hardcoded 'admin')
    reviewer_name = st.sidebar.text_input("👤 ชื่อผู้ตรวจสอบ (Reviewer)", value="admin")
    
    # Check Gemini API Key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.sidebar.warning("⚠️ ไม่พบ GEMINI_API_KEY ในไฟล์ .env โปรดกรอกเพื่อสกัดด้วย AI")
    else:
        st.sidebar.success("🔑 ตรวจพบ Gemini API Key เรียบร้อย")
        
    # Load Active Doc Types dynamically from configs/settings.json
    active_doc_types = get_active_doc_types()
    if not active_doc_types:
        st.error("❌ ไม่พบประเภทเอกสารที่เปิดใช้งานในระบบ แอดมินต้องเปิดใช้งานอย่างน้อย 1 ประเภทที่แท็บ Settings")
        active_doc_types = [{"doc_type_id": "expense_receipt", "display_name": "ใบเสร็จค่าใช้จ่าย (Expense Receipt)"}]
        
    doc_type_options = {d["display_name"]: d.get("doc_type_id") or d.get("domain_id") for d in active_doc_types}
    selected_domain_name = st.sidebar.selectbox("เลือกประเภทเอกสาร (Doc Type)", list(doc_type_options.keys()))
    selected_domain = doc_type_options[selected_domain_name]
    
    # Document upload block
    st.sidebar.subheader("📥 อัปโหลดเอกสารใหม่ (Upload Document)")
    uploaded_file = st.sidebar.file_uploader(
        f"อัปโหลดไฟล์สำหรับ {selected_company_code}", 
        type=["pdf", "png", "jpg", "jpeg"]
    )
    
    if uploaded_file is not None:
        # Load output templates for select
        templates_dir = f"configs/domains/{selected_domain}/outputs"
        templates = []
        if os.path.exists(templates_dir):
            templates = sorted([os.path.splitext(f)[0] for f in os.listdir(templates_dir) if f.endswith(".json")])
        if not templates:
            templates = ["google_sheet_summary"]
            
        selected_template = st.sidebar.selectbox("เลือกเทมเพลตส่งออก", templates)
        export_fmt = st.sidebar.radio("ฟอร์แมตไฟล์ปลายทาง", ["CSV", "JSON"], horizontal=True)
        
        if st.sidebar.button("🚀 ประมวลผลเอกสารด้วย AI"):
            inbox_upload = get_company_pipeline_folder(selected_company_code, "01_drop_zone", "Upload")
            os.makedirs(inbox_upload, exist_ok=True)
            
            temp_path = os.path.join(inbox_upload, uploaded_file.name).replace("\\", "/")
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            with st.spinner(f"กำลังประมวลผลไฟล์สำหรับ {selected_company_code} (ตรวจสอบความสมบูรณ์ -> แยกหน้า -> ค้นหาร้านค้า)..."):
                try:
                    split_and_match(doc_type=selected_domain, input_file=temp_path, company_code=selected_company_code)
                    st.sidebar.success(f"🎉 อัปโหลดและแยกไฟล์ของบริษัท {selected_company_code} เรียบร้อยแล้ว!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ เกิดข้อผิดพลาดในการประมวลผล: {e}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

    # 4-Tab structure
    tab_review, tab_merchants, tab_search, tab_settings = st.tabs([
        "🔎 ตรวจและอนุมัติ (Review & Approve)", 
        "🏪 ร้านค้ารอการอนุมัติ (Merchant Gatekeeper)",
        "📊 ค้นหาและประวัติ (Search & History)", 
        "⚙️ ตั้งค่าระบบ (Settings)"
    ])
    
    # TAB 1: REVIEW & APPROVE
    with tab_review:
        pending_docs = get_cached_pending_documents(selected_domain, company_id=selected_company_id)
        
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
            if not pages and doc:
                pages = get_batch_pages(doc["batch_id"])
                
            if doc:
                try:
                    data = json.loads(doc["data_payload"]) if doc["data_payload"] else {}
                except Exception:
                    data = {}
                
                # Check closed state
                is_closed = doc.get("is_closed", 0) == 1
                is_locked = is_closed
                
                # Warning banner if closed
                if is_closed:
                    st.warning("⚠️ เอกสารนี้ได้รับการอนุมัติและปิดรอบแล้ว (Closed) ไม่สามารถทำการแก้ไขหรือประมวลผลซ้ำได้")
                
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
                    
                    # AI Quality & Cost Assessment Info Box
                    st.markdown("##### 🔍 ผลการประเมินและการใช้จ่าย (AI Quality & Cost Metering)")
                    col_conf, col_prio, col_cost = st.columns(3)
                    with col_conf:
                        conf_val = doc.get("overall_confidence")
                        conf_str = f"{int(conf_val*100)}%" if conf_val is not None else "ไม่มีข้อมูล"
                        st.metric("ความแม่นยำ (Confidence)", conf_str, 
                                  help="คะแนนความมั่นใจของแบบจำลอง AI จากการสกัดหน้าเอกสารนี้")
                    with col_prio:
                        prio_val = doc.get("review_priority") or "LOW"
                        prio_colors = {"HIGH": "🔴 เร่งด่วน (HIGH)", "MEDIUM": "🟡 ปานกลาง (MEDIUM)", "LOW": "🟢 ปกติ (LOW)"}
                        st.metric("ลำดับความสำคัญ (Priority)", prio_colors.get(prio_val, prio_val))
                    with col_cost:
                        c_usd = doc.get("cost_usd", 0.0) or 0.0
                        c_thb = doc.get("cost_thb", 0.0) or 0.0
                        is_free = doc.get("is_free_tier", 0)
                        tier_label = "🆓 Free Tier" if is_free else f"${c_usd:.4f}"
                        sub_label = f"~{c_thb:.3f} THB" if not is_free else "0.00 THB"
                        st.metric("ต้นทุน AI (Cost)", tier_label, delta=sub_label, delta_color="off",
                                  help="ต้นทุนค่าธรรมเนียม AI ประเมินจริงตามจำนวน Token ที่ประมวลผล")
                        
                    if doc.get("is_blurry") == 1 or doc.get("has_ambiguous_fields") == 1:
                        alerts = []
                        if doc.get("is_blurry") == 1:
                            alerts.append("ภาพถ่ายเบลอหรือไม่ชัดเจน")
                        if doc.get("has_ambiguous_fields") == 1:
                            alerts.append("มีฟิลด์ข้อมูลที่กำกวม/ไม่ชัดเจน")
                        st.warning(f"⚠️ **ข้อควรระวัง:** {', '.join(alerts)}")
                        
                    if doc.get("confidence_notes"):
                        st.caption(f"📝 **หมายเหตุ AI:** {doc['confidence_notes']}")
                        
                    st.markdown("---")
                    
                    # Fields Form
                    receipt_info_obj = data.get("receipt_info", {})
                    merchant_obj = data.get("merchant", {})
                    customer_obj = data.get("customer", {})
                    
                    doc_number = st.text_input(
                        "เลขที่เอกสาร / เลขที่ใบเสร็จ (Doc Number)", 
                        value=doc["doc_number"] or receipt_info_obj.get("receipt_number") or data.get("doc_number", ""),
                        disabled=is_locked
                    )
                    
                    # Extract date
                    raw_date = doc["doc_date"] or receipt_info_obj.get("transaction_date") or data.get("transaction_date", "")
                    try:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except Exception:
                        parsed_date = date.today()
                        
                    transaction_date_val = st.date_input(
                        "วันที่ทำรายการ (Date)", 
                        value=parsed_date,
                        disabled=is_locked
                    )
                    transaction_date = transaction_date_val.strftime("%Y-%m-%d")
                    
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        entity_name = st.text_input(
                            "ชื่อร้านค้า / ผู้จำหน่าย (Merchant Name)", 
                            value=doc["entity_name"] or merchant_obj.get("name") or data.get("merchant_name", ""),
                            disabled=is_locked
                        )
                    with col_m2:
                        tax_id = st.text_input(
                            "เลขประจำตัวผู้เสียภาษี (Tax ID)", 
                            value=merchant_obj.get("tax_id") or data.get("tax_id", ""),
                            disabled=is_locked
                        )
                        
                    current_category = receipt_info_obj.get("expense_category") or data.get("expense_category", "Other")
                    cat_options = ["Delivery", "Food & Beverage", "Transport", "Office Supplies", "Utilities", "Other"]
                    cat_index = cat_options.index(current_category) if current_category in cat_options else cat_options.index("Other")
                    
                    expense_category = st.selectbox(
                        "หมวดหมู่ค่าใช้จ่าย (Expense Category)",
                        cat_options,
                        index=cat_index,
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
                    summary = data.get("totals") or data.get("financial_summary", {})
                    
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
                        
                    current_payment_method = receipt_info_obj.get("payment_method") or data.get("payment_method", "")
                    payment_method = st.text_input(
                        "ช่องทางการชำระเงิน (Payment Method)", 
                        value=current_payment_method,
                        disabled=is_locked
                    )
                    
                    st.markdown("---")
                    
                    # Export options
                    st.markdown("##### 📤 การส่งออกรายงาน")
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
                            
                        col_p1, col_p2 = st.columns(2)
                        with col_p1:
                            start_no = st.number_input("ลำดับเลขที่ใบสำคัญเริ่มต้น (Sequence No.)", min_value=1, value=default_seq, disabled=is_locked)
                        with col_p2:
                            voucher_prefix = st.text_input("รหัสคำนำหน้าใบสำคัญจ่าย (Voucher Prefix)", value="PV2608-", disabled=is_locked)
                            
                    # Export Preview Table
                    with st.expander("👁️ แสดงตัวอย่างข้อมูลส่งออก (Export Preview Table)", expanded=False):
                        try:
                            # Construct unified document record for exporter transformation
                            # Note: selected_source is not defined in this scope, assuming source from doc
                            preview_doc = {
                                **data,
                                "source_id": doc.get("source_id"),
                                "domain_id": selected_domain,
                                "document_id": selected_doc_id,
                                "original_pdf_name": doc["original_pdf_name"]
                            }
                            kwargs_preview = {}
                            if selected_exporter["has_custom_params"]:
                                kwargs_preview = {"start_seq_no": start_no, "voucher_prefix": voucher_prefix}
                                
                            df_preview = selected_exporter["handler"].transform([preview_doc], **kwargs_preview)
                            if not df_preview.empty:
                                st.dataframe(df_preview, use_container_width=True)
                                
                                # Download buttons
                                df_dl = df_preview.copy()
                                if selected_exporter_id != "json_dump":
                                    csv_bytes = df_dl.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
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
                                
                            # Rebuild canonical nested objects + top-level aliases
                            new_receipt_info = dict(receipt_info_obj)
                            new_receipt_info.update({
                                "receipt_number": doc_number,
                                "transaction_date": transaction_date,
                                "expense_category": expense_category,
                                "payment_method": payment_method
                            })
                            
                            new_merchant = dict(merchant_obj)
                            new_merchant.update({
                                "name": entity_name,
                                "tax_id": tax_id
                            })
                            
                            new_totals = dict(summary)
                            new_totals.update({
                                "subtotal": subtotal,
                                "discount": discount,
                                "vat_amount": vat_amount,
                                "net_amount": net_amount
                            })
                            
                            final_data = {
                                **data,
                                "receipt_info": new_receipt_info,
                                "merchant": new_merchant,
                                "customer": customer_obj,
                                "items": items_dict,
                                "totals": new_totals,
                                "transaction_date": transaction_date,
                                "merchant_name": entity_name,
                                "tax_id": tax_id,
                                "expense_category": expense_category,
                                "doc_number": doc_number,
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
                                confirmed_by=reviewer_name or SystemUserId.DEV_ADMIN
                            )
                            
                            # Call centralized archiving and exporting helper with custom exporter params
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
                            st.cache_data.clear()
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
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as re_err:
                                    st.error(f"การสกัดข้อมูลซ้ำล้มเหลว: {re_err}")
                                    
    # TAB 2: MERCHANT GATEKEEPER & APPROVAL
    with tab_merchants:
        st.subheader(f"🏪 ศูนย์ตรวจสอบและอนุมัติร้านค้าใหม่ (Merchant Gatekeeper) - บริษัท {selected_company_code}")
        st.markdown(
            "ร้านค้าใหม่ที่มี Tax ID ที่ระบบยังไม่เคยรู้จักจะถูกตั้งสถานะเป็น **`PENDING`** "
            f"และเอกสารจะถูก **พักการทำงาน (Hold)** ไว้ใน `storage/companies/{selected_company_code}/02_raw_data/PENDING/` จนกว่าแอดมินจะกดอนุมัติที่นี่"
        )
        
        pending_merchants = get_pending_merchants(company_id=selected_company_id)
        
        if not pending_merchants:
            st.success(f"🎉 ไม่มีร้านค้าใหม่ค้างรอการอนุมัติสำหรับบริษัท {selected_company_code} ในขณะนี้")
        else:
            st.warning(f"⚠️ พบร้านค้าใหม่รอการอนุมัติ {len(pending_merchants)} รายการ")
            
            for m in pending_merchants:
                m_id = m["merchant_id"]
                tax_id_val = m.get("tax_id") or "NO_TAXID"
                m_name = m.get("merchant_name") or "New Merchant"
                short_n = m.get("short_name") or "merchant"
                file_pfx = m.get("file_prefix") or short_n
                created_t = m.get("created_at") or ""
                
                with st.expander(f"📌 {m_name} (Tax ID: {tax_id_val})", expanded=True):
                    col_m1, col_m2 = st.columns([1.5, 1])
                    with col_m1:
                        st.markdown(f"- **ชื่อร้านค้า (Merchant Name)**: `{m_name}`")
                        st.markdown(f"- **เลขประจำตัวผู้เสียภาษี (Tax ID)**: `{tax_id_val}`")
                        st.markdown(f"- **ตรวจพบเมื่อ (Registered At)**: `{created_t}`")
                        
                        edit_short_name = st.text_input(
                            "✏️ ชื่อย่อร้านค้า (Short Name - ต้องไม่ซ้ำกัน)",
                            value=short_n,
                            key=f"short_{m_id}"
                        ).strip()
                        edit_file_prefix = st.text_input(
                            "⚡ คำนำหน้าชื่อไฟล์ (File Prefix สำหรับ Zero-Cost Match)",
                            value=file_pfx,
                            key=f"pfx_{m_id}"
                        ).strip()
                        
                        # Real-time uniqueness alert
                        from src.infrastructure.persistence import check_short_name_duplicate, check_file_prefix_duplicate
                        is_short_dup = check_short_name_duplicate(edit_short_name, exclude_merchant_id=m_id, company_id=selected_company_id)
                        is_pfx_dup = check_file_prefix_duplicate(edit_file_prefix, exclude_merchant_id=m_id, company_id=selected_company_id)
                        
                        if is_short_dup:
                            st.error(f"❌ ชื่อย่อ `{edit_short_name}` ซ้ำกับร้านอื่นในระบบ กรุณาแก้ไขให้ไม่ซ้ำ")
                        if is_pfx_dup:
                            st.error(f"❌ File Prefix `{edit_file_prefix}` ซ้ำกับร้านอื่นในระบบ กรุณาแก้ไขให้ไม่ซ้ำ")
                            
                    with col_m2:
                        st.markdown("#### การดำเนินการ")
                        st.info(f"📂 โฟลเดอร์ปลายทาง: `02_raw_data/{tax_id_val}_{edit_short_name}`")
                        col_btn_app, col_btn_ign = st.columns(2)
                        with col_btn_app:
                            btn_disabled = is_short_dup or is_pfx_dup or not edit_short_name or not edit_file_prefix
                            if st.button("✅ อนุมัติ (Approve)", key=f"app_{m_id}", use_container_width=True, disabled=btn_disabled):
                                ok, msg = approve_merchant(
                                    m_id,
                                    reviewer_name=reviewer_name or "admin",
                                    short_name=edit_short_name,
                                    file_prefix=edit_file_prefix
                                )
                                if ok:
                                    released = release_pending_merchant_files(selected_domain, tax_id_val, edit_short_name, company_code=selected_company_code)
                                    st.success(f"🎉 อนุมัติร้านค้า '{m_name}' สำเร็จ! ปล่อยเอกสาร {len(released)} รายการเข้าสู่คิวประมวลผลต่อแล้ว")
                                    st.toast("อนุมัติร้านค้าและปล่อยเอกสารเรียบร้อย!", icon="🚀")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(f"ไม่สามารถอนุมัติได้: {msg}")
                        with col_btn_ign:
                            if st.button("🚫 ปฏิเสธ (Ignore)", key=f"ign_{m_id}", use_container_width=True):
                                ignore_merchant(m_id, reviewer_name=reviewer_name or "admin")
                                st.info(f"🚫 ตั้งสถานะเป็น IGNORED ให้ร้านค้า '{m_name}' แล้ว (จะไม่ประมวลผลบิลจากร้านนี้อีก)")
                                st.toast("บันทึกเป็นร้านค้าที่ไม่ประมวลผลแล้ว", icon="🛑")
                                st.cache_data.clear()
                                st.rerun()

        st.divider()
        st.subheader(f"📋 รายชื่อร้านค้าทั้งหมดของบริษัท {selected_company_code} (Merchant Directory)")
        all_merchants = get_merchants(company_id=selected_company_id)
        if all_merchants:
            df_m = pd.DataFrame(all_merchants)
            cols_to_show = [c for c in ["merchant_id", "tax_id", "merchant_name", "short_name", "status", "approved_by", "created_at"] if c in df_m.columns]
            st.dataframe(df_m[cols_to_show], use_container_width=True, hide_index=True)

    # TAB 3: SEARCH & HISTORY
    with tab_search:
        st.subheader(f"📊 ค้นหาประวัติเอกสารย้อนหลัง (Search & History) - บริษัท {selected_company_code}")
        
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
            keyword=search_kw if search_kw else None,
            company_id=selected_company_id
        )
        
        if not results:
            st.info("🔍 ไม่พบประวัติเอกสารที่ตรงตามเงื่อนไขที่เลือก")
        else:
            # Display results table
            df_res = pd.DataFrame(results)
            cols_to_display = [c for c in ["document_id", "doc_number", "doc_date", "entity_name", "total_amount", "status_code", "is_manually_edited", "confirmed_at"] if c in df_res.columns]
            st.dataframe(df_res[cols_to_display], use_container_width=True, hide_index=True)
        st.subheader("🔍 ค้นหาและตรวจสอบข้อมูลเอกสารย้อนหลัง (Audit Search)")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            search_query = st.text_input("คำค้นหา (ชื่อร้าน / เลขใบเสร็จ / เลขผู้เสียภาษี)", "")
        with col_s2:
            status_filter = st.selectbox("สถานะเอกสาร", ["ทั้งหมด", "EXTRACTED", "APPROVED", "FAILED", "NEEDS_REVIEW"])
        with col_s3:
            search_btn = st.button("ค้นหาข้อมูล", use_container_width=True)

        if search_btn or search_query:
            status_arg = None if status_filter == "ทั้งหมด" else status_filter
            search_results = search_documents(query=search_query, status=status_arg)
            if search_results:
                st.success(f"พบข้อมูลทั้งหมด {len(search_results)} รายการ")
                df_search = pd.DataFrame(search_results)
                cols_to_display = [c for c in ["document_id", "doc_type_id", "merchant_name", "tax_id", "receipt_number", "status_code", "created_at"] if c in df_search.columns]
                st.dataframe(df_search[cols_to_display], use_container_width=True, hide_index=True)
            else:
                st.info("ไม่พบข้อมูลเอกสารตามเงื่อนไขที่ระบุ")
            
            # Select row for detail preview
            doc_ids = [r["document_id"] for r in search_results]
            select_detail_id = st.selectbox("เลือกเอกสารเพื่อดูรายละเอียดและภาพสแกน", doc_ids, format_func=lambda x: f"เอกสาร ID: {x[:8]}...")
            
            if select_detail_id:
                selected_result = [r for r in search_results if r["document_id"] == select_detail_id][0]
                
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
                        
    # TAB 4: ADMIN SETTINGS
    with tab_settings:
        st.subheader("⚙️ ระบบเปิด/ปิดการใช้งานและตั้งค่าแอดมิน (Admin & Multi-Company Settings)")
        
        # 1. Manage Companies
        st.markdown("#### 🏢 1. จัดการข้อมูลบริษัทลูกค้า (Client Companies Management)")
        comps = get_all_companies(active_only=False)
        
        # Form to add new company
        with st.expander("➕ เพิ่มบริษัทลูกค้าใหม่ (Register New Company)", expanded=False):
            with st.form("add_company_form", clear_on_submit=True):
                c_code_input = st.text_input("รหัสบริษัท (Company Code e.g. C00001_TRD)*").strip()
                c_name_input = st.text_input("ชื่อบริษัทเต็ม (Full Legal Name)*").strip()
                c_short_input = st.text_input("ชื่อย่อบริษัท (Short Name e.g. TRD)").strip()
                c_tax_input = st.text_input("เลขประจำตัวผู้เสียภาษี 13 หลัก (Tax ID)").strip()
                c_branch_input = st.text_input("รหัสสาขา 5 หลัก (Branch Code)", value="00000").strip()
                
                submitted_company = st.form_submit_button("บันทึกและสร้างโฟลเดอร์จัดเก็บ")
                if submitted_company:
                    if not c_code_input or not c_name_input:
                        st.error("กรุณากรอกรหัสบริษัทและชื่อบริษัทให้ครบถ้วน")
                    else:
                        existing_comp = get_company_by_code(c_code_input)
                        if existing_comp:
                            st.error(f"รหัสบริษัท '{c_code_input}' มีอยู่ในระบบแล้ว")
                        else:
                            created_id = create_company(
                                company_code=c_code_input,
                                company_name=c_name_input,
                                short_name=c_short_input or None,
                                tax_id=c_tax_input or None,
                                branch_code=c_branch_input or "00000",
                            )
                            if created_id:
                                initialize_storage_directories()
                                st.success(f"🎉 สร้างบริษัท '{c_code_input}' และโฟลเดอร์จัดเก็บเรียบร้อยแล้ว!")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("ไม่สามารถสร้างบริษัทได้")

        # Company list table & toggle
        if comps:
            for comp_item in comps:
                col_c1, col_c2, col_c3 = st.columns([3, 2, 1])
                with col_c1:
                    st.markdown(f"**{comp_item['company_code']}** - {comp_item['company_name']}")
                with col_c2:
                    st.caption(f"Tax ID: `{comp_item.get('tax_id') or 'N/A'}` | สาขา: `{comp_item.get('branch_code') or '00000'}`")
                with col_c3:
                    is_active_c = comp_item.get("is_active", 1) == 1
                    tog_c = st.checkbox("เปิดใช้งาน", value=is_active_c, key=f"comp_tog_{comp_item['company_id']}")
                    if tog_c != is_active_c:
                        update_company(comp_item["company_id"], is_active=1 if tog_c else 0)
                        st.toast(f"อัปเดตสถานะบริษัท {comp_item['company_code']} เรียบร้อย", icon="🏢")
                        st.cache_data.clear()
                        st.rerun()

        st.markdown("---")

        # 2. Manage doc_types
        st.markdown("#### 📂 2. จัดการประเภทเอกสาร (Manage Doc Types)")
        all_doc_types = get_doc_types()
        
        # Draw columns/grid for doc_types
        for d in all_doc_types:
            dt_id = d.get("doc_type_id")
            col_d_name, col_d_toggle = st.columns([3, 1])
            with col_d_name:
                st.write(f"**{d['display_name']}** (ID: `{dt_id}`)")
            with col_d_toggle:
                is_act = d["is_active"] == 1
                toggle_val = st.checkbox("เปิดใช้งาน", value=is_act, key=f"doc_type_toggle_{dt_id}")
                if toggle_val != is_act:
                    update_doc_type_active_status(dt_id, 1 if toggle_val else 0)
                    st.toast(f"อัปเดตประเภทเอกสาร {dt_id} เป็น {'เปิด' if toggle_val else 'ปิด'} เรียบร้อย", icon="⚙️")
                    st.cache_data.clear()
                    st.rerun()
                    
        st.markdown("---")
        
        # 3. Manage sources for selected domain
        st.markdown(f"#### 🛍️ 3. จัดการร้านค้า/ผู้ให้บริการ (Manage Sources) สำหรับ: {selected_domain_name}")
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
                        st.cache_data.clear()
                        st.rerun()

if __name__ == "__main__":
    main_app()
