from io import BytesIO
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai 
import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import sqlite3
from contextlib import contextmanager
from fastapi.responses import StreamingResponse
import openpyxl
from dotenv import load_dotenv
import os
import pandas as pd
import requests

load_dotenv() # Load environment variables from .env file

import google_drive as gd
# ... (rest of the file)

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()])

# Configure Gemini API
# IMPORTANT: The API key should be set in your environment or a secure config
# For this project, we assume it's in .streamlit/secrets.toml and loaded by the environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY environment variable not set. PDF processing will fail.")

# Configure LINE API
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

DB_PATH = "app.db"

# ... (Database helpers and Pydantic schemas remain the same) ...
@contextmanager
def get_conn():
    """Context manager to handle database connection."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Initializes the database tables if they don't exist."""
    with get_conn() as conn:
        cur = conn.cursor()
        # companies table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """)
        # banks table (many-to-one relationship with companies)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS company_banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            bank_name TEXT NOT NULL,
            tb_code TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
        """)
        # forms table (many-to-one relationship with companies)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS company_forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            form_type TEXT NOT NULL,
            tb_code TEXT NOT NULL,
            UNIQUE(company_id, form_type),
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
        """)
        # line_recipients table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS line_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL
        )
        """)

# ---------- Pydantic schemas ----------
class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1)

class Company(BaseModel):
    id: int
    name: str

class BankCreate(BaseModel):
    company_id: int
    bank_name: str = Field(..., min_length=1)
    tb_code: str = Field(..., min_length=1)

class Bank(BaseModel):
    id: int
    company_id: int
    bank_name: str
    tb_code: str

class FormsUpsert(BaseModel):
    data: Dict[str, str]

class WorkflowStart(BaseModel):
    company_id: int
    month: str
    year: int

class LineRecipientCreate(BaseModel):
    uid: str = Field(..., min_length=1)

class LineRecipient(BaseModel):
    id: int
    uid: str

class LineMessage(BaseModel):
    message: str = Field(..., min_length=1)

# ---------- New Helper Functions for PDF and LLM ----------
def get_amount_from_gemini(file_content: bytes, prompt: str) -> str:
    """Sends a PDF file to Gemini LLM for OCR and returns the extracted amount."""
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY not set"
    if not file_content:
        return "No file content"

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content([prompt, {"mime_type": "application/pdf", "data": file_content}])
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini API call failed: {e}")
        return f"Error: {e}"

# ---------- Constants ----------
FIXED_FORMS = ["PND1", "PND3", "PND53", "PP30", "SSO"]

PROMPTS = {
    "BANK": "หายอดคงเหลืสุดท้ายให้หน่อย ตอบมาแค่ตัวเลขเท่านั้น ห้ามมีตัวหนังสืออื่นๆเด็ดขาด",
    "PND1": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PND3": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PND53": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PP30": """ภายในหัวข้อ \"ภาษีสุทธิ\" ให้ดึงตัวเลขของช่องที่ 11 หรือช่องที่ 12 มาโดยหากดึงจากช่อง 11 ให้ดึงมาตรงๆ แต่ถ้าเป็นช่องที่ 12 ให้ดึงแล้วเปลี่ยนเป็นค่าลบ ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามที่ตัวหนังสือเด็ดขาด

หมายเหตุ: ในเอกสารจะมีเลขแค่ช่องใดช่องหนึ่งเท่านั้น (ไม่ 11 ก็ 12)""",
    "SSO": "ภายในหัวข้อ \"จำนวนเงินที่ำระ\" ให้ตัวเลออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด"
}

# ... (FastAPI app setup and other endpoints remain the same) ...
app = FastAPI(title="Company Settings API", version="1.0.0")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """Initialize the database when the application starts."""
    init_db()

# ---------- Company endpoints ----------
@app.get("/companies", response_model=List[Company])
def list_companies():
    """Lists all companies."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM companies ORDER BY name").fetchall()
        return [Company(id=r["id"], name=r["name"]) for r in rows]

@app.post("/companies", response_model=Company)
def create_company(payload: CompanyCreate):
    """Creates a new company."""
    with get_conn() as conn:
        try:
            cur = conn.execute("INSERT INTO companies(name) VALUES (?)", (payload.name.strip(),))
            cid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Company name already exists.")
        row = conn.execute("SELECT id, name FROM companies WHERE id = ?", (cid,)).fetchone()
        return Company(id=row["id"], name=row["name"])

# ---------- Bank endpoints ----------
@app.get("/companies/{company_id}/banks", response_model=List[Bank])
def list_banks(company_id: int):
    """Lists all banks for a given company."""
    with get_conn() as conn:
        c = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found.")
        rows = conn.execute("SELECT id, company_id, bank_name, tb_code FROM company_banks WHERE company_id = ? ORDER BY bank_name", (company_id,)).fetchall()
        return [Bank(id=r["id"], company_id=r["company_id"], bank_name=r["bank_name"], tb_code=r["tb_code"]) for r in rows]

@app.post("/banks", response_model=Bank)
def add_bank(payload: BankCreate):
    """Adds a new bank to a company."""
    with get_conn() as conn:
        c = conn.execute("SELECT id FROM companies WHERE id = ?", (payload.company_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found.")
        cur = conn.execute("INSERT INTO company_banks(company_id, bank_name, tb_code) VALUES (?, ?, ?)", (payload.company_id, payload.bank_name.strip(), payload.tb_code.strip()))
        bid = cur.lastrowid
        row = conn.execute("SELECT id, company_id, bank_name, tb_code FROM company_banks WHERE id = ?", (bid,)).fetchone()
        return Bank(id=row["id"], company_id=row["company_id"], bank_name=row["bank_name"], tb_code=row["tb_code"])

@app.delete("/banks/{bank_id}")
def delete_bank(bank_id: int):
    """Deletes a bank."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM company_banks WHERE id = ?", (bank_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bank record not found.")
        conn.execute("DELETE FROM company_banks WHERE id = ?", (bank_id,))
        return {"ok": True}

# ---------- Forms endpoints ----------
@app.get("/companies/{company_id}/forms")
def get_company_forms(company_id: int):
    """Gets all form configurations for a company."""
    with get_conn() as conn:
        c = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found.")
        rows = conn.execute("SELECT form_type, tb_code FROM company_forms WHERE company_id = ?", (company_id,)).fetchall()
        existing = {r["form_type"]: r["tb_code"] for r in rows}
        result = {ft: existing.get(ft, "") for ft in FIXED_FORMS}
        return {"company_id": company_id, "forms": result, "fixed": FIXED_FORMS}

@app.put("/companies/{company_id}/forms")
def upsert_company_forms(company_id: int, payload: FormsUpsert):
    """Updates or creates form configurations for a company."""
    for k in payload.data.keys():
        if k not in FIXED_FORMS:
            raise HTTPException(status_code=400, detail=f"Invalid form type: {k}")
    with get_conn() as conn:
        c = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found.")
        for form_type, tb_code in payload.data.items():
            tb_code = tb_code.strip()
            conn.execute("INSERT INTO company_forms(company_id, form_type, tb_code) VALUES (?, ?, ?) ON CONFLICT(company_id, form_type) DO UPDATE SET tb_code=excluded.tb_code", (company_id, form_type, tb_code))
        return {"ok": True}

# ---------- LINE Notify endpoints ----------
@app.get("/line/recipients", response_model=List[LineRecipient])
def list_line_recipients():
    """Lists all LINE recipients."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, uid FROM line_recipients ORDER BY id").fetchall()
        return [LineRecipient(id=r["id"], uid=r["uid"]) for r in rows]

@app.post("/line/recipients", response_model=LineRecipient)
def add_line_recipient(payload: LineRecipientCreate):
    """Adds a new LINE recipient."""
    with get_conn() as conn:
        try:
            cur = conn.execute("INSERT INTO line_recipients(uid) VALUES (?)", (payload.uid.strip(),))
            rid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Recipient UID already exists.")
        row = conn.execute("SELECT id, uid FROM line_recipients WHERE id = ?", (rid,)).fetchone()
        return LineRecipient(id=row["id"], uid=row["uid"])

@app.delete("/line/recipients/{recipient_id}")
def delete_line_recipient(recipient_id: int):
    """Deletes a LINE recipient."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM line_recipients WHERE id = ?", (recipient_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recipient not found.")
        conn.execute("DELETE FROM line_recipients WHERE id = ?", (recipient_id,))
        return {"ok": True}

@app.post("/line/send_message")
def send_line_message(payload: LineMessage):
    """Sends a message to all registered LINE recipients."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logging.error("LINE_CHANNEL_ACCESS_TOKEN is not set.")
        raise HTTPException(status_code=500, detail="LINE API is not configured on the server.")

    with get_conn() as conn:
        rows = conn.execute("SELECT uid FROM line_recipients").fetchall()
        uids = [r["uid"] for r in rows]

    if not uids:
        raise HTTPException(status_code=400, detail="No recipients configured.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    error_details = []
    success_count = 0

    for uid in uids:
        body = {
            "to": uid,
            "messages": [{"type": "text", "text": payload.message}]
        }
        try:
            response = requests.post(LINE_API_URL, headers=headers, json=body)
            response.raise_for_status()
            success_count += 1
        except requests.HTTPError as e:
            logging.error(f"Failed to send message to {uid}: {e.response.text}")
            error_details.append(f"Failed for UID {uid}: {e.response.status_code}")
    
    if error_details:
        raise HTTPException(
            status_code=500, 
            detail=f"Sent {success_count}/{len(uids)} messages. Errors: {', '.join(error_details)}"
        )

    return {"ok": True, "sent_count": success_count}

# ---------- Workflow endpoints ----------
@app.post("/workflow/start")
def start_workflow(payload: WorkflowStart):
    # ... (Existing setup code: logging, get company settings, auth with Drive) ...
    logging.info(f"Workflow started for company_id: {payload.company_id}, month: {payload.month}, year: {payload.year}")
    
    # Get company settings from the database
    logging.info("Fetching company settings from database.")
    with get_conn() as conn:
        c = conn.execute("SELECT name FROM companies WHERE id = ?", (payload.company_id,)).fetchone()
        if not c:
            logging.error(f"Company with id {payload.company_id} not found.")
            raise HTTPException(status_code=404, detail="Company not found.")
        company_name = c["name"]
        banks_cursor = conn.execute("SELECT bank_name, tb_code FROM company_banks WHERE company_id = ? ORDER BY bank_name", (payload.company_id,))
        banks = banks_cursor.fetchall()
        forms_cursor = conn.execute("SELECT form_type, tb_code FROM company_forms WHERE company_id = ?", (payload.company_id,))
        forms_map = {row['form_type']: row['tb_code'] for row in forms_cursor.fetchall()}
    logging.info(f"Found company: {company_name}")

    # Authenticate with Google Drive
    logging.info("Authenticating with Google Drive.")
    try:
        drive_service = gd.get_drive_service()
    except FileNotFoundError as e:
        logging.error(f"Credential file not found: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logging.error(f"Google Drive authentication failed: {e}")
        raise HTTPException(status_code=500, detail=f"Google Drive authentication failed: {e}")
    logging.info("Google Drive authentication successful.")

    # Find the company's main folder in Google Drive
    folder_search_term = f"{company_name}"
    logging.info(f"Searching for company folder with term: {folder_search_term}")
    query = f"name contains '{folder_search_term}' and mimeType = 'application/vnd.google-apps.folder'"
    folders = gd.find_files(drive_service, query)
    if not folders:
        logging.error(f"No Google Drive folder found for '{folder_search_term}'")
        raise HTTPException(status_code=404, detail=f"No Google Drive folder found for '{folder_search_term}'")
    company_folder_id = folders[0]['id']
    logging.info(f"Found company folder with id: {company_folder_id}")

    # --- Get Data Workflow (Same as before) ---
    logging.info("Starting Get Data Workflow.")

    # Find top-level folders within the company folder
    bank_folder_name = f"Bank_{payload.year}"
    logging.info(f"Searching for bank folder: {bank_folder_name}")
    bank_folders_query = f"'{company_folder_id}' in parents and name contains '{bank_folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    bank_folders = gd.find_files(drive_service, bank_folders_query)
    
    logging.info("Searching for PP30 folder.")
    pp30_folders_query = f"'{company_folder_id}' in parents and name contains 'ภพ30' and mimeType = 'application/vnd.google-apps.folder'"
    pp30_folders = gd.find_files(drive_service, pp30_folders_query)

    logging.info("Searching for PND folder.")
    pnd_folders_query = f"'{company_folder_id}' in parents and name contains 'ภงด' and mimeType = 'application/vnd.google-apps.folder'"
    pnd_folders = gd.find_files(drive_service, pnd_folders_query)

    # Find files within the bank folder
    bank_files = []
    if bank_folders:
        bank_folder_id = bank_folders[0]['id']
        logging.info(f"Bank folder found with id: {bank_folder_id}, searching for files.")
        bank_files_query = f"'{bank_folder_id}' in parents and name contains '{payload.year}{payload.month}' and mimeType = 'application/pdf'"
        bank_files = gd.find_files(drive_service, bank_files_query)
    logging.info(f"Found {len(bank_files)} bank files.")

    # Find files within the PP30 folder
    pp30_files = []
    if pp30_folders:
        pp30_folder_id = pp30_folders[0]['id']
        logging.info(f"PP30 folder found with id: {pp30_folder_id}, searching for files.")
        pp30_files_query = f"'{pp30_folder_id}' in parents and name contains '{payload.year}{payload.month}' and mimeType = 'application/pdf'"
        pp30_files = gd.find_files(drive_service, pp30_files_query)
    logging.info(f"Found {len(pp30_files)} PP30 files.")

    # Find files within the PND subfolders
    sso_files, pnd1_files, pnd3_files, pnd53_files = [], [], [], []
    if pnd_folders:
        pnd_folder_id = pnd_folders[0]['id']
        logging.info(f"PND folder found with id: {pnd_folder_id}")
        def find_in_pnd_subfolder(subfolder_name):
            logging.info(f"Searching for PND subfolder: {subfolder_name}")
            subfolder_query = f"'{pnd_folder_id}' in parents and name contains '{subfolder_name}' and mimeType = 'application/vnd.google-apps.folder'"
            subfolders = gd.find_files(drive_service, subfolder_query)
            if subfolders:
                subfolder_id = subfolders[0]['id']
                logging.info(f"{subfolder_name} subfolder found with id: {subfolder_id}, searching for files.")
                file_query = f"'{subfolder_id}' in parents and name contains '{payload.year}{payload.month}' and mimeType = 'application/pdf'"
                files = gd.find_files(drive_service, file_query)
                logging.info(f"Found {len(files)} files in {subfolder_name} subfolder.")
                return files
            logging.warning(f"{subfolder_name} subfolder not found.")
            return []
        sso_files = find_in_pnd_subfolder("SSO")
        pnd1_files = find_in_pnd_subfolder("PND1")
        pnd3_files = find_in_pnd_subfolder("PND3")
        pnd53_files = find_in_pnd_subfolder("PND53")

    # Find VAT files
    vat_folder_name = f"VAT_{payload.year}"
    logging.info(f"Searching for VAT folder: {vat_folder_name}")
    vat_folders_query = f"'{company_folder_id}' in parents and name contains '{vat_folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    vat_folders = gd.find_files(drive_service, vat_folders_query)
    vat_files = []
    if vat_folders:
        vat_folder_id = vat_folders[0]['id']
        logging.info(f"VAT folder found with id: {vat_folder_id}, searching for files.")
        year_short = str(payload.year)[-2:]
        vat_file_search_term = f"VAT{payload.month}_{year_short}"
        vat_files_query = f"'{vat_folder_id}' in parents and name contains '{vat_file_search_term}' and mimeType = 'application/vnd.ms-excel'"
        vat_files = gd.find_files(drive_service, vat_files_query)
    logging.info(f"Found {len(vat_files)} VAT files: {[f['name'] for f in vat_files]}")

    # --- Process Data Workflow ---
    logging.info("Starting Process Data Workflow.")
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Workflow Result"
    sheet.append(['Name', 'TB Code', 'File Found', 'PDF Actual Amount', 'TB Code Amount', 'Excel Actual Column']) # Add new header
    logging.info("Excel workbook created with new header.")

    # Find and read the TB file
    tb_files_query = f"'{company_folder_id}' in parents and name contains 'tb' and mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
    tb_files = gd.find_files(drive_service, tb_files_query)
    tb_data = {}
    if tb_files:
        tb_file_id = tb_files[0]['id']
        logging.info(f"TB file found with id: {tb_file_id}")
        request = drive_service.files().get_media(fileId=tb_file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        tb_wb = openpyxl.load_workbook(fh)
        tb_sheet = tb_wb.active
        for row in tb_sheet.iter_rows(min_row=2):
            tb_code = row[0].value
            if tb_code:
                val_col7 = row[6].value if len(row) > 6 else 0
                val_col8 = row[7].value if len(row) > 7 else 0
                amount = 0
                if val_col7 and val_col7 > 0:
                    amount = val_col7
                elif val_col8:
                    amount = -val_col8
                tb_data[str(tb_code)] = amount
    else:
        logging.warning("TB file not found.")

    # Process VAT files for "Excel Actual Column"
    vat_amounts = {}
    form_mapping = {
        "ภงด.1": "PND1",
        "ภงด.3": "PND3",
        "ภงด.53": "PND53",
        "ภพ.30": "PP30",
    }
    if vat_files:
        for vat_file in vat_files:
            vat_file_id = vat_file['id']
            logging.info(f"Processing VAT file: {vat_file['name']} (id: {vat_file_id})")
            request = drive_service.files().get_media(fileId=vat_file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            df = pd.read_excel(fh, engine='xlrd', header=None)
            for index, row in df.iterrows():
                if len(row) > 3:
                    cell_value = str(row.iloc[1])
                    for key, form_name in form_mapping.items():
                        if key in cell_value:
                            amount_cell = row.iloc[3]
                            amount = 0
                            if amount_cell != "-" and amount_cell is not None:
                                try:
                                    amount = float(amount_cell)
                                except (ValueError, TypeError):
                                    amount = "Invalid Value"
                            vat_amounts[form_name] = amount
                            break # Move to next row once a match is found

    # Add bank data
    for bank in banks:
        bank_name = bank['bank_name']
        tb_code = bank['tb_code']
        found_files = [f for f in bank_files if bank_name.lower() in f['name'].lower()]
        file_names = ", ".join([f['name'] for f in found_files])
        
        amount = "N/A"
        if found_files:
            amounts = []
            for f in found_files:
                request = drive_service.files().get_media(fileId=f['id'])
                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                amount_from_pdf = get_amount_from_gemini(fh.getvalue(), PROMPTS["BANK"])
                amounts.append(amount_from_pdf)
            amount = ", ".join(amounts)
            
        tb_amount = tb_data.get(str(tb_code), "Not Found")
        sheet.append([bank_name, tb_code, file_names, amount, tb_amount, "N/A"])

    # Add form data
    form_data_map = {
        "PND1": (pnd1_files, forms_map.get("PND1", ""), PROMPTS.get("PND1")),
        "PND3": (pnd3_files, forms_map.get("PND3", ""), PROMPTS.get("PND3")),
        "PND53": (pnd53_files, forms_map.get("PND53", ""), PROMPTS.get("PND53")),
        "PP30": (pp30_files, forms_map.get("PP30", ""), PROMPTS.get("PP30")),
        "SSO": (sso_files, forms_map.get("SSO", ""), PROMPTS.get("SSO")),
    }

    for form_name, (files, tb_code, prompt) in form_data_map.items():
        file_names = ", ".join([f['name'] for f in files])
        amount = "N/A"
        if files and prompt:
            amounts = []
            for f in files:
                request = drive_service.files().get_media(fileId=f['id'])
                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                amount_from_pdf = get_amount_from_gemini(fh.getvalue(), prompt)
                amounts.append(amount_from_pdf)
            amount = ", ".join(amounts)

        tb_amount = tb_data.get(str(tb_code), "Not Found")
        excel_actual_amount = vat_amounts.get(form_name, "N/A")
        sheet.append([form_name, tb_code, file_names, amount, tb_amount, excel_actual_amount])
    
    logging.info("Data added to the sheet.")

    # Save and return workbook
    virtual_workbook = BytesIO()
    wb.save(virtual_workbook)
    virtual_workbook.seek(0)
    filename = f"{company_name}_{payload.year}_{payload.month}_workflow.xlsx"
    logging.info(f"Returning Excel file: {filename}")
    return StreamingResponse(
        virtual_workbook,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
