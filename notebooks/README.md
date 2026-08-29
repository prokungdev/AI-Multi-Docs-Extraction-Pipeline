# 📓 Jupyter Notebooks Guide

โฟลเดอร์นี้รวบรวมสมุดบันทึก (Jupyter Notebooks) สำหรับการทดลองรันระบบ, การวัดประสิทธิภาพ AI Models & Prompts, และการวิเคราะห์ข้อมูลค่าใช้จ่ายทางธุรกิจ (Data Analytics)

---

## 📑 รายการ Notebooks ในโฟลเดอร์นี้

### 1. [`01_pipeline_walkthrough.ipynb`](01_pipeline_walkthrough.ipynb)
- **วัตถุประสงค์:** E2E Interactive Pipeline Runner & Staging Dry-Run
- **ฟังก์ชันการทำงาน:**
  - รันการประมวลผลเอกสารจริงจาก `storage/` ทีละขั้นตอน
  - แสดงภาพหน้าที่ตัดแยกแล้ว, ข้อมูลที่ AI สกัดได้, ผลการ Validate, และตารางในฐานข้อมูล SQLite
  - เหมาะสำหรับ: Developer & QA ตรวจสอบการทำงานแบบละเอียด

### 2. [`02_prompt_and_model_evaluation.ipynb`](02_prompt_and_model_evaluation.ipynb)
- **วัตถุประสงค์:** AI Model & Prompt Benchmarking Evaluation
- **ฟังก์ชันการทำงาน:**
  - เปรียบเทียบความแม่นยำ (Accuracy) ของการสกัดข้อมูลระหว่าง AI Models (`gemini-2.5-flash` vs `gpt-4o`)
  - เปรียบเทียบการใช้ Token และความเร็วในการตอบสนอง (Latency)
  - เหมาะสำหรับ: AI Engineer ปรับจูน System Prompt และ Rules

### 3. [`03_expense_analytics_insights.ipynb`](03_expense_analytics_insights.ipynb)
- **วัตถุประสงค์:** Expense Data Analytics & Business Insights Dashboard
- **ฟังก์ชันการทำงาน:**
  - วิเคราะห์ข้อมูลค่าใช้จ่ายที่ได้รับการอนุมัติแล้วจากฐานข้อมูล SQLite
  - สรุปยอดค่าใช้จ่ายแยกตามร้านค้า (Top Merchants), หมวดหมู่ (Categories), และภาษีซื้อ (VAT)
  - พล็อตแผนภูมิสรุปยอด (Charts & Trends)
  - เหมาะสำหรับ: ผู้บริหาร, ฝ่ายบัญชี และ Data Analyst

---

## 🚀 วิธีการรัน Notebooks

1. เปิด Terminal ใน Root Directory ของโปรเจกต์
2. รันคำสั่งเปิด Jupyter Lab หรือ VS Code / Cursor:
   ```bash
   .venv\Scripts\jupyter lab
   ```
3. เลือก Kernel เป็น `.venv` Python Environment
