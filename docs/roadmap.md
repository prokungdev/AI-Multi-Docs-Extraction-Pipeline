# 🗺️ Project Architecture & Engineering Roadmap

เอกสารแผนที่นำทางการพัฒนาสถาปัตยกรรมระบบ **AI Multi-Docs Extraction Pipeline**
แสดงลำดับการพัฒนาทั้งฝั่ง **Source Modules (เอกสารต้นทาง)**, **Canonical Core (แกนกลาง)**, **Target Modules (ระบบปลายทาง)**, และ **Presentation Layer (หน้าจอผู้ใช้งาน)**

---

## 📊 ภาพรวมสถานะการพัฒนา (High-Level Status)

| ส่วนของระบบ (Component) | Module ID | รายละเอียด | สถานะ |
| :--- | :--- | :--- | :---: |
| **Source Ingestion** | **Mod-S1** | PDF Vision Core (OCR, Preprocessing, Token Math, Multi-Page Chunking) | 🟢 100% |
| **Pipeline Core** | **Mod-C1** | Stage 0 ➔ Stage 4 (Init, Ingestion, Extraction, Transformation, Validation) | 🟢 100% |
| **Review & Voucher Core** | **Mod-C2** | Stage 5 ➔ Stage 7 (Confirm, Journal Voucher, `is_override_vat`, 50-Tawi WHT) | 🟢 100% |
| **Target Integration** | **Mod-T1** | Express OE Screen RPA Adapter & Concurrency Lease Lock Gateway | 🟢 100% |
| **Interactive Walkthrough** | **Mod-W1** | Jupyter Walkthrough Notebook (`01_pipeline_walkthrough.ipynb` Step 0–9) | 🟢 100% |
| **REST API Gateway** | **Mod-A1** | FastAPI Endpoints สำหรับ Review, Confirm, และ Voucher Generation | 🟡 ถัดไป (Next) |
| **Reviewer Dashboard UI** | **Mod-U1** | Streamlit Real-World UI สำหรับ Review & Confirm พร้อมจัดการ `is_override_vat` | 🟡 ถัดไป (Next) |
| **Target Integration** | **Mod-T2** | Express IV / IS Screen (Direct Invoice & Sales Tax RPA Adapter) | 🔵 วางแผนไว้ |
| **Target Integration** | **Mod-T3** | SAP FB60 Vendor Invoice Plugin (`XMWST: False` / Manual Tax Override) | 🔵 วางแผนไว้ |
| **Source Ingestion** | **Mod-S2** | Tabular Cleansing Ingestion (Multi-Format Excel / CSV Auto-Normalizer) | 🔵 วางแผนไว้ |

---

## 🟢 1. สิ่งที่พัฒนาเสร็จสมบูรณ์แล้ว (Completed Milestones)

### ✅ Mod-S1 & Mod-C1: Pipeline Stages 0 ถึง 4
- **Stage 0 (`init_system`)**: Bootstrap พื้นที่จัดเก็บไฟล์และฐานข้อมูล
- **Stage 1 (`split_and_match`)**: คัดแยกหน้า PDF เป็น JPGs, คำนวณ SHA-256 Hashing, และ Zero-Cost Prefix Matching
- **Stage 2 (`extract_documents`)**: Multimodal AI Extraction (Gemini 2.5 Flash / Flash Lite) พร้อม Smart Chunk Checkpointing & Resume
- **Stage 3 (`transform_to_db`)**: บันทึกข้อมูลลงฐานข้อมูลเชิงสัมพันธ์ Pure SQLAlchemy 2.0 (`document_controls`, `expense_receipts`, `expense_receipt_items`)
- **Stage 4 (`validate_documents`)**: ตรวจสอบสมดุลตัวเลขการเงิน (Math Balance) และประเมิน Confidence Score

### ✅ Mod-C2 & Mod-T1: Review, Voucher & Express OE RPA Integration
- **Stage 5 (`confirm_receipts`)**: ระบบตรวจสอบและประทับตรา Confirmation (`CONFIRMED`) พร้อม Audit Trail (`confirmed_by`, `confirmed_at`)
- **Stage 6 (`generate_journal_vouchers`)**: แปลงเอกสารเป็น Journal Voucher, ออกเลขที่ใบสำคัญอัตโนมัติ, แมปผังบัญชี GL Account, และคำนวณภาษีหัก ณ ที่จ่าย ภ.ง.ด. 53 (50-Tawi WHT 3%)
- **Universal VAT Override (`is_override_vat`)**:
  - รองรับการยึดภาษีตามหน้าบิล 100% ไม่คำนวณซ้ำ
  - แมปส่งออกไปยัง Express OE Payload ในรูป `"EditVat": 1`
- **Stage 7 (`export_target_payloads`)**: Sealing ใบสำคัญเป็นสถานะ `READY` สำหรับให้หุ่นยนต์ RPA ดึงงาน
- **RPA Lease Lock Gateway**:
  - Concurrency Lease Lock ป้องกันบอทแย่งงานกัน (`READY` ➔ `POSING` ➔ `POSTED`)
- **Test Suite Clean-Up**: รวม Test ทั้งหมดเข้า `test_voucher_integration.py` (181 passed 100% Green)

### ✅ Mod-W1: Jupyter Notebook Walkthrough
- [01_pipeline_walkthrough.ipynb](file:///d:/PROKUNG/GitHub-Source/AI-Multi-Docs-Extraction-Pipeline/notebooks/01_pipeline_walkthrough.ipynb): เพิ่ม Step 6 (Confirm) ➔ Step 7 (Voucher) ➔ Step 8 (Export Payload) ➔ Step 9 (RPA Lease Simulation) โดยเรียกใช้ฟังก์ชัน Pipeline สะอาดตาแบบ Thin Client

---

## 🟡 2. งานระยะสั้น (Immediate Next Milestones)

### 📌 Milestone 1: FastAPI REST Endpoints Expansion (Mod-A1)
- [ ] สร้าง Endpoint `POST /api/v1/batches/{batch_id}/confirm` สำหรับสั่ง Confirm เอกสารทั้ง Batch
- [ ] สร้าง Endpoint `POST /api/v1/documents/{document_id}/confirm` สำหรับ Confirm รายเอกสาร
- [ ] สร้าง Endpoint `POST /api/v1/batches/{batch_id}/generate-vouchers` สำหรับสั่งสร้าง Journal Vouchers
- [ ] สร้าง Endpoint `GET /api/v1/batches/{batch_id}/export-payloads` สำหรับดึงข้อมูล Express Payload
- [ ] เขียน Automated API Integration Tests

### 📌 Milestone 2: Streamlit Reviewer & Voucher UI Dashboard (Mod-U1)
- [ ] อัปเดตหน้าจอ Streamlit ใน [apps/streamlit/app.py](file:///d:/PROKUNG/GitHub-Source/AI-Multi-Docs-Extraction-Pipeline/apps/streamlit/app.py)
- [ ] เพิ่มปุ่ม **"Confirm & Lock Receipt"** ในหน้า Document Detail
- [ ] เพิ่มสวิตช์เปิด/ปิด **"Override VAT from Bill (`is_override_vat`)"** ต่อร้านค้าและรายบิล
- [ ] เพิ่มหน้าจอแสดงรายการ **Journal Vouchers & Express RPA Payload Preview**
- [ ] เพิ่มปุ่ม **"Simulate RPA Worker (Post to Express)"** บน UI สำหรับทดสอบ Workflow

---

## 🔵 3. งานระยะกลางและระยะยาว (Future Planned Milestones)

### 📌 Milestone 3: Module T2 - Express IV / IS Screen Adapter (Mod-T2)
- [ ] สร้าง `ExpressIvTargetAdapter` สำหรับรองรับการส่งออกหน้าจอซื้อสินค้าเชื่อ/เงินสด (IV) และหน้าจอขาย (IS)
- [ ] รองรับการแยกรายการสินค้าละเอียด (No Consolidation Line Items)

### 📌 Milestone 4: Module T3 - SAP ERP Target Adapter Plugin (Mod-T3)
- [ ] สร้าง `SAPTargetAdapter` รองรับการยิงข้อมูลเข้า SAP FB60 (Vendor Invoice)
- [ ] แมปแฟล็ก `is_override_vat: 1` ➔ `XMWST: False` (Calculate Tax = False) และใส่ยอด `WMWST` ตามหน้าบิล
- [ ] ลงทะเบียนเข้าสู่ `TargetAdapterRegistry`

### 📌 Milestone 5: Module S2 - Tabular Cleansing Ingestion (Mod-S2)
- [ ] พัฒนาโมดูลอ่านและคลีนไฟล์ Excel / CSV จากหลาย Vendor (เช่น Statement, E-Tax CSV, Shopee/Lazada Report)
- [ ] แปลงโครงสร้างเข้าสู่ Canonical `ExpenseReceipt` Schema โดยไม่ต้องผ่าน Vision OCR

### 📌 Milestone 6: Enterprise Multi-Tenant RBAC & Observability
- [ ] ระบบสลับ Company Isolation แบบสมบูรณ์บน Streamlit / Web UI
- [ ] หน้า Dashboard แสดง Token Usage, Latency, และประมาณการค่าใช้จ่าย AI แยกรายบริษัท
