Project Overview
    - ใช้ Streamlit เป็น Frontend (app.py) ใช้ FastAPI เป็น Backend (main.py) ใช้ SQLite เป็น Database
    - credential ในการเชื่อม Google Service จะใช้ Service Account ในไฟล์ credential.json

Project's Goal
1. สามารถเพิ่ม Company ได้
2. แต่ละ Company สามารถ Setup TB Code สำหรับ Bank, PND1, PND3, PND53, SSO, PP30
3. มีหน้า "Workflow" โดยมี Dropdown ให้เลือก Company, เดือน (01, 02, 03, ..., 12) และเลือกปี (2021, 2022, 2023, ..., Current Year(2025) ) และมีปุ่มให้กด "Start" เพื่อเริ่มกระบวนการทำงานตาม Section Project Workflow ข้างล่างนี้

Project Workflow
* ใช้ {ปี} และ {เดือน} ที่เลือกเอาไว้ สมมติว่าเลือกเดือน 05 และเลือกปี 2025*

### Get Data Workflow 
0. ดำเนินการข้อต่อๆไปนี้ โดย File และ Folder จะอยู่ใน Folder Google Drive {Company} ตามที่เลือกเอาไว้ เช่น "0.Com1_TestWorkFlowAutomation_2025"
1. หา File xlsx ที่มี "tb" อยู่ในชื่อไฟล์
2. หา File xlsx ที่มี "gl" อยู่ในชื่อไฟล์
3. หา Folder ที่มีคำว่า "Bank_{ปี}" อยู่ในชื่อ Folder
    3.1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือน 05 และปี 2025 ตามที่เลือกไว้ก่อนกด Start)
4. หา Folder ที่มีคำว่า "ภพ30" อยู่ในชื่อ Folder
    4,1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือน 05 และปี 2025 ตามที่เลือกไว้ก่อนกด Start)
5. หา Folder ที่มีคำว่า "ภงด" อยู่ในชื่อ Folder
    5.1 หา Folder ที่มี "SSO" อยู่ในชื่อ Folder
        5.1.1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือ��� 05 และปี 2025 ตามที่เลือก���ว้ก่อนกด Start)
    5.2 หา Folder ที่มี "PND1" อยู่ในชื่อ Folder
        5.2.1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือน 05 และปี 2025 ตามที่เลือกไว้ก่อนกด Start)
    5.3 หา Folder ที่มี "PND3" อยู่ในชื่อ Folder
        5.3.1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือน 05 และปี 2025 ตามที่เลือกไว้ก่อนกด Start)
    5.4 หา Folder ที่มี "PND53" อยู่ในชื่อ Folder
        5.4.1 หาทุก File PDF ที่มี "{ปี}{เดือน}" อยู่ เช่น 202505 (สำหรับเดือน 05 และปี 2025 ตามที่เลือกไว้ก่อนกด Start) 
6. หา Folder ที่มีคำว่า "VAT_{ปี}" อยู่ในชื่อ Folder
    6.1 หาทุก File xlsx ที่มี "{เดือน}{ปี}" อยู่ในชื่อ File (ในส่วนของ {ปี} เอามาแค่ 2 ตัวท้าย เช่น 2025 เอามาแ���� 25)

### Process Data Workflow
7. สร้าง File xlsx โดยใช้ openpyxl
    7.1 สร้างคอลัมน์ชื่อ 'Name' โดยให้มีข้อมูลดังนี้:
        - ดึงรายชื่อธนาคารทั้งหมดจากฐานข้อมูล SQLite ของ {Company} นี้ (เช่น bank1, bank2, bank3) มาเรียงเป็นแต่ละแถว
        - ต่อจากรายชื่อธนาคาร ให้เพิ่มรายการต่อไปนี้ในแต่ละแถวตามลำดับ: PND1, PND3, PND53, PP30, SSO
    7.2 สร้างคอลัมน์ชื่อ "TB Code" ให้เอา TB Code ที่ตั้งค่าไว้ของแต่ละข้อเอามาใส่ตาม Row
    7.3 แต่ละ Row ของ Bank ให้เอาชื่อไฟล์จากข้อ 3.1 มาใส่ โดยใช้ Logic if bank1 in filename, bank2 in filename
    7.4 แต่ละ Row ของ PND1, PND3, PND53, PP30, SSO ให้เอาชื่อไฟล์มาใส่จาก 4. ถึง 5.


Constraints:
1. code แต่ละส่วนของ comment ��ั��นๆไว้ด้วย
2. code เน้น simplify not complicate

---

### Gemini Work Done
- **Project Setup**: Installed necessary libraries (`openpyxl`, `google-api-python-client`, etc.) and updated `requirements.txt`.
- **Environment Management**: Integrated `python-dotenv` to manage the `GEMINI_API_KEY` from a `.env` file for local development.
- **Frontend (Streamlit)**: Implemented the "Workflow" tab in `app.py` with dropdowns for company, month, and year, and a "Start" button.
- **Backend (FastAPI)**: Created the `/workflow/start` endpoint in `main.py`.
- **Google Drive Integration**: Implemented the "Get Data Workflow" by creating a `google_drive.py` module to search for and identify the required files and folders in Google Drive based on the user's selection.
- **Data Processing**: Implemented the "Process Data Workflow" to fetch data from the SQLite database and combine it with the file information from Google Drive.
- **Excel Generation**: The workflow now generates an XLSX file in memory using `openpyxl` as specified in the requirements.
- **PDF Data Extraction**:
    - Integrated `pdfplumber` to extract text from PDF documents.
    - Integrated the Gemini LLM (`google-generativeai`) to extract specific monetary values from the PDF text based on custom prompts.
    - Added a new "PDF Actual Amount" column to the generated Excel file.
- **File Download**: The Streamlit frontend was updated to handle the file download response from the backend, providing a download button for the generated Excel report.
- **Code Quality**: Added comments to `main.py` and `app.py` to improve code clarity.
- **Logging**: Implemented logging in `main.py` to record the steps of the workflow process into `app.log`.
- **Cleanup**: Removed unnecessary files (`create_xlsx.py`, `created_by_openpyxl.xlsx`, `backup.py`).
- **Bug Fixes**:
    - Corrected the search logic for PND subfolders, which were not being found.
    - Changed the bank folder search from an exact match to `contains` to make it more flexible.
    - Fixed the file search logic for all subfolders (Bank, PP30, PND) to correctly query within the subfolder instead of the root company folder.
- **OCR Integration**:
    - Replaced `pdfplumber` with a direct-to-API OCR approach.
    - Updated the workflow to send PDF file bytes directly to the Gemini `gemini-1.5-pro` model.
    - This removes the local text extraction step, relying on Gemini's multimodal capabilities for more robust text extraction from scanned documents.
    - Corrected the Gemini model name from `gemini-pro` to `gemini-1.5-flash` and subsequently to `gemini-1.5-pro` to resolve API errors and support OCR.