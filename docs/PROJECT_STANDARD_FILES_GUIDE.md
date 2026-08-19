# 📚 คู่มือโครงสร้างไฟล์มาตรฐานสำหรับระบบ AI Document Processing & Data Pipeline
(Production Standard Files & Architecture Guide)

เอกสารนี้รวบรวมมาตรฐานการจัดวางไฟล์, หน้าที่การทำงาน, และหมวดหมู่เอกสารที่จำเป็นสำหรับระบบ **AI-Multi-Docs-Extraction-Pipeline** ระดับ Production-ready เพื่อให้ทีมผู้พัฒนา, QA, และผู้ดูแลระบบสามารถต่อยอดและบำรุงรักษาได้อย่างเป็นระบบ

---

## 🏗️ โครงสร้างโฟลเดอร์ภาพรวม (Overall Directory Layout)

```
AI-Multi-Docs-Extraction-Pipeline/
│
├── configs/                          # ⚙️ ไฟล์การตั้งค่ากลางและกฎของแต่ละโดเมน
│   ├── settings.json                 # Single Source of Truth (Storage, AI Providers, Domains)
│   └── domains/                      # กฎและ Schema แยกตาม Domain (เช่น expense_receipt)
│
├── pipeline_storage/                 # 🗄️ พื้นที่จัดเก็บเอกสารตาม Lifecycle
│   └── expense_receipt/
│       ├── 01_raw_inbox/             # ไฟล์ PDF ต้นฉบับ
│       ├── 02_split_pages/           # ไฟล์ภาพ PNG ที่ตัดแยกหน้า
│       ├── 03_processing_queue/      # ไฟล์ JSON ที่ AI สกัดและ Validate แล้ว
│       └── 04_archive/               # คลังเอกสารที่ได้รับการอนุมัติแล้ว
│
├── outputs/                          # 📤 รายงานผลลัพธ์ที่ Export ออกมา (CSV, Excel, Express PV)
├── logs/                             # 📋 Application Logs
│
├── src/                              # 📦 ซอร์สโค้ดหลักของระบบ
│   ├── core/                         # Core Pipeline Engine, DB, Exporters, Extractor, Post-Processor
│   └── ui/                           # Streamlit Web UI Portal (app.py)
│
├── notebooks/                        # 📓 รวม Jupyter Notebooks สำหรับพัฒนา, ทดสอบ, และวิเคราะห์
│   ├── README.md                     # คำแนะนำการใช้งาน Notebooks
│   ├── 01_pipeline_walkthrough.ipynb # E2E Interactive Pipeline Runner
│   ├── 02_prompt_and_model_evaluation.ipynb # AI Model & Prompt Benchmarking
│   └── 03_expense_analytics_insights.ipynb  # Expense Data Analytics & Visualizations
│
├── scripts/                          # 🛠️ สคริปต์เครื่องมือเสริม (Seeding, Maintenance, Backup)
│   └── seed_merchants.py             # Script สำหรับ Seed ร้านค้าเข้า Master
│
├── tests/                            # 🧪 รวมชุดทดสอบอัตโนมัติ (Unit & Integration Tests)
│   ├── test_pipeline.py              # End-to-End Pipeline Tests
│   └── test_db.py                    # Database Schema & CRUD Tests
│
├── docs/                             # 📖 เอกสารคู่มือทางเทคนิคและสถาปัตยกรรม
│   ├── PROJECT_STATUS.md             # รายงานสถานะโปรเจกต์
│   ├── PROJECT_STANDARD_FILES_GUIDE.md # เอกสารคู่มือมาตรฐานไฟล์ (เอกสารนี้)
│   ├── ARCHITECTURE.md               # สถาปัตยกรรมระบบและ Data Flow
│   └── ADDING_NEW_MERCHANT.md        # คู่มือการเพิ่มร้านค้าใหม่ (SOP)
│
├── main.py                           # 🚀 Universal CLI Dispatcher
├── Run_01_Init.bat ... Run_07.bat    # Windows Batch Launchers (เรียก main.py)
├── requirements.txt                  # Python Dependencies
├── .env.example                      # ตัวอย่าง Environment Variables
└── .gitignore
```

---

## 🗂️ รายละเอียดไฟล์มาตรฐานแยกตาม 5 หมวดหมู่

### 1. 📓 หมวดหมู่ Jupyter Notebooks (`notebooks/`)
ใช้สำหรับ Interactive Development, Staging Execution, Model Benchmarking และ Data Science Analytics:

| ชื่อไฟล์ | วัตถุประสงค์ & หน้าที่การทำงาน |
| :--- | :--- |
| **`01_pipeline_walkthrough.ipynb`** | **E2E Interactive Runner:** รันข้อมูลจริงจาก `pipeline_storage` ทีละขั้นตอน สังเกตภาพเอกสาร ดู JSON และตารางในฐานข้อมูล |
| **`02_prompt_and_model_evaluation.ipynb`** | **AI Evaluation & Benchmarking:** ทดสอบเปรียบเทียบความแม่นยำ (Accuracy) และต้นทุน Token ระหว่างโมเดล `gemini-2.5-flash` vs `gpt-4o` กับเอกสารตัวอย่าง |
| **`03_expense_analytics_insights.ipynb`** | **Data Analytics & Dashboard:** ดึงข้อมูลจาก SQLite มาวิเคราะห์สรุปยอด เช่น ร้านค้าที่จ่ายบ่อยที่สุด (Top Merchants), หมวดหมู่ค่าใช้จ่ายรายเดือน, และภาษีซื้อที่เคลมได้ |

---

### 2. 📖 หมวดหมู่เอกสารและคู่มือ (`docs/`)
ใช้สำหรับเป็นแนวทางปฏิบัติ (SOP) และเอกสารอ้างอิงของทีม:

| ชื่อไฟล์ | วัตถุประสงค์ & หน้าที่การทำงาน |
| :--- | :--- |
| **`README.md`** *(ที่ Root)* | **หน้าแรกของโปรเจกต์:** แนะนำระบบ, ข้อกำหนด, วิธีติดตั้ง, และวิธีสั่งรันทั้ง UI และ CLI |
| **`docs/PROJECT_STANDARD_FILES_GUIDE.md`** | **เอกสารคู่มือมาตรฐานไฟล์:** แนะนำโครงสร้างไฟล์มาตรฐานระดับ Production |
| **`docs/KNOWLEDGE_BASE.md`** | **คลังความรู้ทางเทคนิคและ Best Practices:** ศูนย์รวมองค์ความรู้ด้าน Token Optimization, Thai OCR, และ DPI Guidelines |
| **`docs/ARCHITECTURE.md`** | **อธิบายสถาปัตยกรรม:** เจาะลึกโครงสร้าง Data Flow, Database Schema DDL, และ Module Design |
| **`docs/ADDING_NEW_MERCHANT.md`** | **คู่มือการเพิ่มร้านค้าใหม่ (SOP):** วิธีเพิ่ม Merchant ใหม่ (เช่น 7-Eleven, BigC, Grab) แค่สร้างโฟลเดอร์ใน `configs/domains/expense_receipt/sources/` พร้อมตัวอย่าง `rules.json` |
| **`docs/EXPRESS_INTEGRATION_GUIDE.md`** | **คู่มือนำเข้าโปรแกรมบัญชี Express:** วิธีนำไฟล์ `express_pv_export.csv` (CP874) ไป Import เข้าโปรแกรมบัญชี Express ให้ไม่มีปัญหาเรื่องภาษาไทย |

---

### 3. 🛠️ หมวดหมู่ Scripts บริหารจัดการระบบ (`scripts/`)
ใช้สำหรับบำรุงรักษาและจัดการข้อมูลเบื้องหลัง:

| ชื่อไฟล์ | วัตถุประสงค์ & หน้าที่การทำงาน |
| :--- | :--- |
| **`scripts/seed_merchants.py`** | **Database Seeding:** นำเข้ารายชื่อร้านค้าและประวัติเอกสารเข้าฐานข้อมูล |
| **`scripts/clean_pipeline_storage.py`** | **Storage Maintenance:** ล้างไฟล์ภาพชั่วคราวใน `02_split_pages` และ `03_processing_queue` ที่ค้างเกิน 30 วัน เพื่อประหยัดพื้นที่ดิสก์ |
| **`scripts/backup_db.py`** | **Database Backup:** ทำสำเนาฐานข้อมูล SQLite (`pipeline.db`) เก็บไว้ในโฟลเดอร์ `backups/` อัตโนมัติ |

---

### 4. 🐳 หมวดหมู่ Deployment & DevOps (สำหรับขึ้น Server / Cloud)
ใช้สำหรับบรรจุระบบเป็น Container เพื่อ Deploy:

| ชื่อไฟล์ | วัตถุประสงค์ & หน้าที่การทำงาน |
| :--- | :--- |
| **`Dockerfile`** | **Container Build:** บรรจุทั้ง Python, PyMuPDF, Streamlit, และ Dependencies เป็น Docker Container |
| **`docker-compose.yml`** | **Container Orchestration:** สั่งรัน Web Portal พร้อมกำหนด Volume Mount สำหรับ `pipeline_storage/` และ `configs/` |
| **`.dockerignore`** | **Build Optimization:** ป้องกันการก๊อปปี้ไฟล์ขยะเข้า Container Image เพื่อให้มีขนาดเล็กและเร็ว |

---

### 5. 🤖 หมวดหมู่ CI/CD Automation (`.github/workflows/`)
ใช้สำหรับทดสอบโค้ดอัตโนมัติบน Git Repository:

| ชื่อไฟล์ | วัตถุประสงค์ & หน้าที่การทำงาน |
| :--- | :--- |
| **`.github/workflows/ci.yml`** | **Automated Testing:** รันคำสั่ง `unittest discover tests` อัตโนมัติทุกครั้งที่มีการ `git push` หรือ Pull Request |
