# main.py
import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import sqlite3
from contextlib import contextmanager
from fastapi.responses import StreamingResponse
import openpyxl
from io import BytesIO

import google_drive as gd # Import the new module

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()])

DB_PATH = "app.db"

# ... (rest of the file is the same)

# ---------- Database helpers ----------
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

# ---------- Constants ----------
FIXED_FORMS = ["PND1", "PND3", "PND53", "PP30", "SSO"]

# ---------- App ----------
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

# ---------- Workflow endpoints ----------
@app.post("/workflow/start")
def start_workflow(payload: WorkflowStart):
    """Main workflow to get data from Google Drive and generate an Excel report."""
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

    # --- Get Data Workflow ---
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

    # --- Process Data Workflow ---
    logging.info("Starting Process Data Workflow.")
    # Create a new Excel workbook in memory
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Workflow Result"
    sheet.append(['Name', 'TB Code', 'File Found'])
    logging.info("Excel workbook created.")

    # Add bank data to the sheet
    logging.info("Adding bank data to the sheet.")
    for bank in banks:
        bank_name = bank['bank_name']
        tb_code = bank['tb_code']
        found_file_names = [f['name'] for f in bank_files if bank_name.lower() in f['name'].lower()]
        sheet.append([bank_name, tb_code, ", ".join(found_file_names)])

    # Add form data to the sheet
    logging.info("Adding form data to the sheet.")
    form_data_map = {
        "PND1": (pnd1_files, forms_map.get("PND1", "")),
        "PND3": (pnd3_files, forms_map.get("PND3", "")),
        "PND53": (pnd53_files, forms_map.get("PND53", "")),
        "PP30": (pp30_files, forms_map.get("PP30", "")),
        "SSO": (sso_files, forms_map.get("SSO", "")),
    }
    for form_name, (files, tb_code) in form_data_map.items():
        file_names = ", ".join([f['name'] for f in files])
        sheet.append([form_name, tb_code, file_names])
    logging.info("Data added to the sheet.")

    # Save the workbook to a byte stream
    virtual_workbook = BytesIO()
    wb.save(virtual_workbook)
    virtual_workbook.seek(0)
    logging.info("Workbook saved to memory.")

    # Return the Excel file as a downloadable response
    filename = f"{company_name}_{payload.year}_{payload.month}_workflow.xlsx"
    logging.info(f"Returning Excel file: {filename}")
    return StreamingResponse(
        virtual_workbook,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
