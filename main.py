from io import BytesIO
from copy import copy
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

try:
    from openpyxl.formula.translate import Translator
    CAN_TRANSLATE = True
except ImportError:
    CAN_TRANSLATE = False
    logging.warning("Could not import openpyxl.formula.translate.Translator. Formulas will be copied without adjusting references.")

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
            name TEXT UNIQUE NOT NULL,
            google_drive_folder_id TEXT,
            google_drive_folder_name TEXT
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
            channel_id INTEGER NOT NULL,
            uid TEXT NOT NULL,
            UNIQUE(channel_id, uid),
            FOREIGN KEY(channel_id) REFERENCES line_channels(id) ON DELETE CASCADE
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS line_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL
        )
        """)
        # line_channels table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS line_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            token TEXT NOT NULL
        )
        """)

# ---------- Pydantic schemas ----------
class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1)

class LineEventSource(BaseModel):
    userId: str

class LineEvent(BaseModel):
    type: str
    source: LineEventSource

class LineWebhook(BaseModel):
    events: List[LineEvent]

class Company(BaseModel):
    id: int
    name: str
    google_drive_folder_id: Optional[str] = None
    google_drive_folder_name: Optional[str] = None

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

class ReconcileStart(BaseModel):
    company_id: int
    year: int
    parts: List[str]

class LineRecipientCreate(BaseModel):
    channel_id: int
    uid: str = Field(..., min_length=1)

class LineRecipient(BaseModel):
    id: int
    channel_id: int
    uid: str

class LineRecipientDetail(BaseModel):
    id: int
    uid: str
    displayName: str

class LineChannelCreate(BaseModel):
    name: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)

class LineChannel(BaseModel):
    id: int
    name: str
    token: str

class LineMessage(BaseModel):
    channel_id: int
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
FIXED_FORMS = ["PND1", "PND3", "PND53", "PP30", "SSO", "Revenue", "Credit Note"]

PROMPTS = {
    "BANK": "หายอดคงเหลืสุดท้ายให้หน่อย ตอบมาแค่ตัวเลขเท่านั้น ห้ามมีตัวหนังสืออื่นๆเด็ดขาด",
    "PND1": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PND3": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PND53": "ภายในหัวข้อ \"สำหรับใบเสร็จรับเงิน\" ให้ตัวเลขของ \"จำนวนเงิน\" ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด",
    "PP30": """ภายในหัวข้อ \"ภาษีสุทธิ\" ให้ดึงตัวเลขของช่องที่ 11 หรือช่องที่ 12 มาโดยหากดึงจากช่อง 11 ให้ดึงมาตรงๆ แต่ถ้าเป็นช่องที่ 12 ให้ดึงแล้วเปลี่ยนเป็นค่าลบ ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามที่ตัวหนังสือเด็ดขาด\n\nหมายเหตุ: ในเอกสารจะมีเลขแค่ช่องใดช่องหนึ่งเท่านั้น (ไม่ 11 ก็ 12)""",
    "SSO": "ภายในหัวข้อ \"จำนวนเงินที่ำระ\" ให้ตัวเลออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด"
}

# ... (FastAPI app setup and other endpoints remain the same) ...
app = FastAPI(title="Company Settings API", version="1.0.0")


origins = [
    "https://app.byteduck.io",
    "http://localhost:8501"
]
# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
        rows = conn.execute("SELECT id, name, google_drive_folder_id, google_drive_folder_name FROM companies ORDER BY name").fetchall()
        return [Company(id=r["id"], name=r["name"], google_drive_folder_id=r["google_drive_folder_id"], google_drive_folder_name=r["google_drive_folder_name"]) for r in rows]

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

@app.delete("/companies/{company_id}")
def delete_company(company_id: int):
    """Deletes a company and all its associated data."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found.")
        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        return {"ok": True}

@app.put("/companies/{company_id}", response_model=Company)
def update_company(company_id: int, payload: CompanyCreate):
    """Updates a company's name."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found.")
        try:
            conn.execute("UPDATE companies SET name = ? WHERE id = ?", (payload.name.strip(), company_id))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Company name already exists.")
        row = conn.execute("SELECT id, name, google_drive_folder_id, google_drive_folder_name FROM companies WHERE id = ?", (company_id,)).fetchone()
        return Company(id=row["id"], name=row["name"], google_drive_folder_id=row["google_drive_folder_id"], google_drive_folder_name=row["google_drive_folder_name"])

class CompanyDriveFolderUpdate(BaseModel):
    google_drive_folder_id: str
    google_drive_folder_name: str

@app.put("/companies/{company_id}/google-drive-folder", response_model=Company)
def update_company_drive_folder(company_id: int, payload: CompanyDriveFolderUpdate):
    """Updates the Google Drive folder for a company."""
    with get_conn() as conn:
        c = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found.")
        conn.execute(
            "UPDATE companies SET google_drive_folder_id = ?, google_drive_folder_name = ? WHERE id = ?",
            (payload.google_drive_folder_id, payload.google_drive_folder_name, company_id)
        )
        row = conn.execute("SELECT id, name, google_drive_folder_id, google_drive_folder_name FROM companies WHERE id = ?", (company_id,)).fetchone()
        return Company(id=row["id"], name=row["name"], google_drive_folder_id=row["google_drive_folder_id"], google_drive_folder_name=row["google_drive_folder_name"])

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
@app.post("/line/webhook")
def line_webhook(payload: LineWebhook):
    """Handles incoming LINE messages to capture user information."""
    for event in payload.events:
        if event.type == "message":
            user_id = event.source.userId
            # Fetch user profile from LINE API
            profile_url = f"https://api.line.me/v2/bot/profile/{user_id}"
            headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
            try:
                res = requests.get(profile_url, headers=headers, timeout=5)
                res.raise_for_status()
                profile = res.json()
                display_name = profile.get("displayName", "Unknown")
                
                # Store user in the database, ignoring duplicates
                with get_conn() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO line_users (uid, display_name) VALUES (?, ?)",
                        (user_id, display_name)
                    )
            except requests.RequestException as e:
                logging.error(f"Could not fetch LINE profile for UID {user_id}: {e}")
    return {"ok": True}

@app.post("/line/recipients", response_model=LineRecipient)
def add_line_recipient(payload: LineRecipientCreate):
    """Adds a new LINE recipient to a specific channel."""
    with get_conn() as conn:
        # Check if channel exists
        channel = conn.execute("SELECT id FROM line_channels WHERE id = ?", (payload.channel_id,)).fetchone()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found.")
        
        try:
            cur = conn.execute("INSERT INTO line_recipients(channel_id, uid) VALUES (?, ?)", (payload.channel_id, payload.uid.strip()))
            rid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Recipient UID already exists for this channel.")
        
        row = conn.execute("SELECT id, channel_id, uid FROM line_recipients WHERE id = ?", (rid,)).fetchone()
        return LineRecipient(id=row["id"], channel_id=row["channel_id"], uid=row["uid"])

@app.delete("/line/recipients/{recipient_id}")
def delete_line_recipient(recipient_id: int):
    """Deletes a LINE recipient."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM line_recipients WHERE id = ?", (recipient_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recipient not found.")
        conn.execute("DELETE FROM line_recipients WHERE id = ?", (recipient_id,))
        return {"ok": True}

@app.get("/line/channels/{channel_id}/recipients", response_model=List[LineRecipientDetail])
def get_recipient_details(channel_id: int):
    """Gets details for all recipients using a specific channel to fetch profiles."""
    with get_conn() as conn:
        channel_row = conn.execute("SELECT token FROM line_channels WHERE id = ?", (channel_id,)).fetchone()
        if not channel_row:
            raise HTTPException(status_code=404, detail="LINE channel not found.")
        access_token = channel_row["token"]

        recipient_rows = conn.execute("SELECT id, uid FROM line_recipients WHERE channel_id = ?", (channel_id,)).fetchall()

    headers = {"Authorization": f"Bearer {access_token}"}
    detailed_recipients = []

    for r in recipient_rows:
        uid = r["uid"]
        profile_url = f"https://api.line.me/v2/bot/profile/{uid}"
        display_name = "(Profile not found)"
        try:
            res = requests.get(profile_url, headers=headers, timeout=5) # Add 5-second timeout
            res.raise_for_status()
            display_name = res.json().get("displayName", "(Name not available)")
        except requests.Timeout:
            logging.warning(f"Timeout while fetching profile for UID {uid}")
            display_name = "(Profile fetch timed out)"
        except requests.HTTPError as e:
            logging.warning(f"Could not fetch profile for UID {uid}: {e.response.text}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while fetching profile for UID {uid}: {e}")
        
        detailed_recipients.append(
            LineRecipientDetail(id=r["id"], uid=uid, displayName=display_name)
        )
    
    return detailed_recipients


# ---------- LINE Channel endpoints ----------
@app.get("/line/channels", response_model=List[LineChannel])
def list_line_channels():
    """Lists all LINE channels."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, token FROM line_channels ORDER BY name").fetchall()
        return [LineChannel(id=r["id"], name=r["name"], token=r["token"]) for r in rows]

@app.post("/line/channels", response_model=LineChannel)
def add_line_channel(payload: LineChannelCreate):
    """Adds a new LINE channel."""
    with get_conn() as conn:
        try:
            cur = conn.execute("INSERT INTO line_channels(name, token) VALUES (?, ?)", (payload.name.strip(), payload.token.strip()))
            cid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Channel name already exists.")
        row = conn.execute("SELECT id, name, token FROM line_channels WHERE id = ?", (cid,)).fetchone()
        return LineChannel(id=row["id"], name=row["name"], token=row["token"])

@app.delete("/line/channels/{channel_id}")
def delete_line_channel(channel_id: int):
    """Deletes a LINE channel."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM line_channels WHERE id = ?", (channel_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Channel not found.")
        conn.execute("DELETE FROM line_channels WHERE id = ?", (channel_id,))
        return {"ok": True}


@app.post("/line/send_message")
def send_line_message(payload: LineMessage):
    """Sends a message to all registered LINE recipients using a specific channel."""
    with get_conn() as conn:
        # Get the channel's access token
        channel_row = conn.execute("SELECT token FROM line_channels WHERE id = ?", (payload.channel_id,)).fetchone()
        if not channel_row:
            raise HTTPException(status_code=404, detail="LINE channel not found.")
        access_token = channel_row["token"]

        # Get recipient UIDs for the specific channel
        rows = conn.execute("SELECT uid FROM line_recipients WHERE channel_id = ?", (payload.channel_id,)).fetchall()
        uids = [r["uid"] for r in rows]

    if not uids:
        raise HTTPException(status_code=400, detail="No recipients configured.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
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

class GoogleDriveFolder(BaseModel):
    id: str
    name: str

@app.get("/google-drive/folders", response_model=List[GoogleDriveFolder])
def list_google_drive_folders():
    """Lists all folders accessible by the service account in Google Drive."""
    try:
        drive_service = gd.get_drive_service()
        # Query for all folders accessible by the service account.
        # This is simpler and more robust than checking ownership.
        query = "mimeType = 'application/vnd.google-apps.folder'"
        
        folders = gd.find_files(drive_service, query)
        return [GoogleDriveFolder(id=f['id'], name=f['name']) for f in folders]
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Drive API error: {e}")

# ---------- Workflow endpoints ----------
@app.post("/workflow/start")
def start_workflow(payload: WorkflowStart):
    # ... (Existing setup code: logging, get company settings, auth with Drive) ...
    logging.info(f"Workflow started for company_id: {payload.company_id}, month: {payload.month}, year: {payload.year}")
    
    # Get company settings from the database
    logging.info("Fetching company settings from database.")
    with get_conn() as conn:
        c = conn.execute("SELECT name, google_drive_folder_id FROM companies WHERE id = ?", (payload.company_id,)).fetchone()
        if not c:
            logging.error(f"Company with id {payload.company_id} not found.")
            raise HTTPException(status_code=404, detail="Company not found.")
        company_name = c["name"]
        company_folder_id = c["google_drive_folder_id"]
        if not company_folder_id:
            raise HTTPException(status_code=400, detail="Company does not have a Google Drive folder configured.")
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
    logging.info(f"Using company folder with id: {company_folder_id}")

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
    sheet.append(['Name', 'TB Code', 'File Found', 'PDF Actual Amount', 'TB Code Amount', 'Excel Actual Column', 'Result 1', 'Result 2']) # Add new header
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

        # Add formulas for result columns
        row_num = sheet.max_row
        tb_code_str = str(tb_code)
        if tb_code_str.startswith('1'):
            sheet[f'G{row_num}'] = f'=IF(D{row_num}=E{row_num}, "Correct", "Incorrect")'
            sheet[f'H{row_num}'] = "N/A"
        elif tb_code_str.startswith('2'):
            sheet[f'G{row_num}'] = f'=IF(D{row_num}=-E{row_num}, "Correct", "Incorrect")'
            sheet[f'H{row_num}'] = "N/A" # No Excel Actual Column for banks
        else:
            sheet[f'G{row_num}'] = "N/A"
            sheet[f'H{row_num}'] = "N/A"

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

        # Add formulas for result columns
        row_num = sheet.max_row
        tb_code_str = str(tb_code)
        if tb_code_str.startswith('1'):
            sheet[f'G{row_num}'] = f'=IF(D{row_num}=E{row_num}, "Correct", "Incorrect")'
            sheet[f'H{row_num}'] = "N/A"
        elif tb_code_str.startswith('2'):
            sheet[f'G{row_num}'] = f'=IF(D{row_num}=-E{row_num}, "Correct", "Incorrect")'
            sheet[f'H{row_num}'] = f'=IF(-E{row_num}=F{row_num}, "Correct", "Incorrect")'
        else:
            sheet[f'G{row_num}'] = "N/A"
            sheet[f'H{row_num}'] = "N/A"
    
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
        headers={'Content-Disposition': f'attachment; filename="{filename}"'} # Corrected header escaping
    )

# ---------- Reconcile endpoints ----------
@app.post("/reconcile/start")
def start_reconcile(payload: ReconcileStart):
    logging.info(f"Reconcile started for company_id: {payload.company_id}")
    
    # Get company name
    with get_conn() as conn:
        c = conn.execute("SELECT name, google_drive_folder_id FROM companies WHERE id = ?", (payload.company_id,)).fetchone()
        if not c:
            logging.error(f"Company with id {payload.company_id} not found.")
            raise HTTPException(status_code=404, detail="Company not found.")
        company_name = c["name"]
        company_folder_id = c["google_drive_folder_id"]
        if not company_folder_id:
            raise HTTPException(status_code=400, detail="Company does not have a Google Drive folder configured.")

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
    logging.info(f"Using company folder with id: {company_folder_id}")

    # Find and read the TB file
    tb_files_query = f"'{company_folder_id}' in parents and name contains 'tb' and mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
    tb_files = gd.find_files(drive_service, tb_files_query)
    if not tb_files:
        logging.error("TB file not found.")
        raise HTTPException(status_code=404, detail="TB file not found.")

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

    # Create a new workbook for reconcile result
    wb = openpyxl.Workbook()
    # Remove the default sheet created
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    if "tb_subsheet" in payload.parts:
        # Find and read the TB file
        tb_files_query = f"'{company_folder_id}' in parents and name contains 'tb' and mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
        tb_files = gd.find_files(drive_service, tb_files_query)
        if not tb_files:
            logging.error("TB file not found.")
            raise HTTPException(status_code=404, detail="TB file not found.")

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

        sheet = wb.create_sheet(title="TB")

        # Copy data from tb_sheet to the new sheet, excluding the last row
        for row_index, row in enumerate(tb_sheet.iter_rows(max_row=tb_sheet.max_row - 1), start=1):
            for col_index, cell in enumerate(row[:8], start=1):
                sheet.cell(row=row_index + 5, column=col_index, value=cell.value)

        # Add formulas and static values
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O']:
            sheet[f'{col}5'] = f'=SUBTOTAL(9,{col}8:{col}{sheet.max_row})'
        sheet.merge_cells('I6:J6')
        sheet['I6'] = 'ปรับปรุง'
        sheet['I7'] = 'เดบิท'
        sheet['J7'] = 'เครดิต'
        sheet.merge_cells('K6:K7')
        sheet['K6'] = 'Net'
        sheet['K4'] = 'กำไร'
        for row in range(8, sheet.max_row + 1):
            sheet[f'K{row}'] = f'=G{row}+I{row}-H{row}-J{row}'
        sheet['L3'] = '=+L5+L4'
        sheet['L4'] = '=+M5-L5'
        sheet['M3'] = '=+M5+M4'
        sheet.merge_cells('L6:M6')
        sheet['L6'] = 'งบกำไรขาดทุน'
        sheet['L7'] = 'เดบิท'
        sheet['M7'] = 'เครดิต'
        sheet['N3'] = '=+N5+N4'
        sheet['O2'] = '=+N3-O3'
        sheet['O3'] = '=+O5+O4'
        sheet['O4'] = '=+L4'
        for row in range(8, sheet.max_row + 1):
            a_val = sheet[f'A{row}'].value
            if a_val and str(a_val).startswith(('4', '5')):
                sheet[f'L{row}'] = f'=IF(K{row}>0,K{row},0)'
                sheet[f'M{row}'] = f'=IF(K{row}<0,-K{row},0)'
        for row in range(8, sheet.max_row + 1):
            a_val = sheet[f'A{row}'].value
            if a_val and str(a_val).startswith(('1', '2', '3')):
                sheet[f'N{row}'] = f'=IF(K{row}>0,K{row},0)'
                sheet[f'O{row}'] = f'=IF(K{row}<0,-K{row},0)'
        sheet['M2'] = '=+L3-M3'
        sheet.merge_cells('N6:O6')
        sheet['N6'] = 'งบแสดงฐานะการเงิน'
        sheet['N7'] = 'เดบิท'
        sheet['O7'] = 'เครดิต'
        sheet['A1'] = 'ชื่อบริษัท'
        sheet['B1'] = company_name
        sheet['A2'] = 'งบทดลอง ณ วันที่'
        sheet['A3'] = 'เลขที่บัญชีจาก'
        sheet['A4'] = 'วันที่จาก'
        sheet['A5'] = 'เลือกแผนก'
        sheet['B3'] = 'xxxxxx - xxxxxx'
        sheet['B5'] = '* รวมบัญชียอดเป็น 0 N'
        sheet['B4'] = '_ ถึง _'
        sheet['B2'] = 'xx มกราคม xxx'

    if any(part in payload.parts for part in ["gl_subsheet", "tb_code_subsheets", "pp30_subsheet"]):
        # Find and read the GL file
        gl_files_query = f"'{company_folder_id}' in parents and name contains 'gl' and mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
        gl_files = gd.find_files(drive_service, gl_files_query)
        if gl_files:
            gl_file_id = gl_files[0]['id']
            logging.info(f"GL file found with id: {gl_file_id}")
            request = drive_service.files().get_media(fileId=gl_file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            gl_wb = openpyxl.load_workbook(fh, data_only=True)
            gl_sheet = gl_wb.active

            if "gl_subsheet" in payload.parts:
                gl_ws = wb.create_sheet(title="GL")
                for row in gl_sheet.iter_rows(values_only=True):
                    gl_ws.append(row)

            if "tb_code_subsheets" in payload.parts:
                data_rows = list(gl_sheet.iter_rows(values_only=True))
                i = 0
                while i < len(data_rows):
                    row = data_rows[i]
                    if row and row[0] and "ลำดับที่" in str(row[0]):
                        if i > 0:
                            prev_row = data_rows[i-1]
                            account_info = str(prev_row[0]) if prev_row and prev_row[0] else ""
                            if account_info.startswith(('1', '2')):
                                account_number = account_info.split()[0]
                                account_data_block = []
                                block_end_index = i
                                for j in range(i, len(data_rows)):
                                    current_block_row = data_rows[j]
                                    account_data_block.append(current_block_row)
                                    block_end_index = j
                                    if not current_block_row or not current_block_row[0]:
                                        break
                                if account_number in wb.sheetnames:
                                    ws = wb[account_number]
                                else:
                                    ws = wb.create_sheet(title=account_number)
                                for data_row in account_data_block:
                                    ws.append(data_row)
                                ws.append([])
                                i = block_end_index + 1
                                continue
                    i += 1
            
            if "pp30_subsheet" in payload.parts:
                # This part will be executed within the GL file processing block
                # It assumes gl_wb and gl_sheet are available.
                
                # Ensure the PP30 sheet is created once
                if "PP30" not in wb.sheetnames:
                    pp30_ws = wb.create_sheet(title="PP30")
                    # Setup headers and months as per RECONCILE.md 3.1 & 3.2
                    pp30_ws['C4'] = "เดือน"
                    pp30_ws['D4'] = "PP30"
                    pp30_ws['E4'] = "รายได้"
                    pp30_ws['F4'] = "ลดหนี้"
                    pp30_ws['G4'] = "Diff"
                    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
                    for i, month in enumerate(thai_months):
                        pp30_ws[f'C{i+5}'] = month
                
                # Get a reference to the possibly newly created sheet
                pp30_ws = wb["PP30"]

                # --- Logic to populate Column E from GL file based on PP30.md ---
                with get_conn() as conn:
                    forms_cursor = conn.execute("SELECT form_type, tb_code FROM company_forms WHERE company_id = ?", (payload.company_id,))
                    forms_map = {row['form_type']: row['tb_code'] for row in forms_cursor.fetchall()}
                
                revenue_tb_code = forms_map.get("Revenue")
                
                if revenue_tb_code:
                    monthly_revenue = {i: 0 for i in range(1, 13)}
                    
                    # Iterate through all sheets in the GL workbook
                    for sheet_name in gl_wb.sheetnames:
                        current_sheet = gl_wb[sheet_name]
                        data_rows = list(current_sheet.iter_rows())
                        
                        i = 0
                        while i < len(data_rows):
                            row = data_rows[i]
                            cell_value = row[0].value if row else None
                            
                            # Find a cell in column A containing the revenue TB code
                            if cell_value and revenue_tb_code in str(cell_value):
                                # Start processing transactions 2 rows down
                                j = i + 2
                                while j < len(data_rows):
                                    transaction_row = data_rows[j]
                                    
                                    # Stop if column A is empty
                                    if not transaction_row or not transaction_row[0].value:
                                        break
                                    
                                    try:
                                        date_cell = transaction_row[2].value if len(transaction_row) > 2 else None
                                        amount_cell = transaction_row[8].value if len(transaction_row) > 8 else None

                                        if date_cell and hasattr(date_cell, 'month'):
                                            month = date_cell.month
                                            amount = 0
                                            if amount_cell and amount_cell != '-':
                                                try:
                                                    amount = float(amount_cell)
                                                except (ValueError, TypeError):
                                                    logging.warning(f"Could not convert amount '{amount_cell}' to number in row {j+1} of sheet {sheet_name}. Treating as 0.")
                                            
                                            monthly_revenue[month] += amount
                                    except Exception as e:
                                        logging.error(f"Error processing row {j+1} in sheet {sheet_name}: {e}")

                                    j += 1
                                
                                i = j # Continue searching from where the block ended
                            else:
                                i += 1
                    
                    # Populate the PP30 sheet with the final totals
                    for month, total in monthly_revenue.items():
                        cell = f'E{month+4}'
                        pp30_ws[cell] = total if total != 0 else "-"

        # --- This block is now outside the GL file check ---
        if "pp30_subsheet" in payload.parts:
            # If the sheet wasn't created above (e.g. no GL file), create it now.
            if "PP30" not in wb.sheetnames:
                pp30_ws = wb.create_sheet(title="PP30")
                pp30_ws['C4'] = "เดือน"
                pp30_ws['D4'] = "PP30"
                pp30_ws['E4'] = "รายได้"
                pp30_ws['F4'] = "ลดหนี้"
                pp30_ws['G4'] = "Diff"
                thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
                for i, month in enumerate(thai_months):
                    pp30_ws[f'C{i+5}'] = month
            
            pp30_ws = wb["PP30"]

            # --- Logic to populate Column D from PDF files (RECONCILE.md 3.3) ---
            pp30_folders_query = f"'{company_folder_id}' in parents and name contains 'ภพ30' and mimeType = 'application/vnd.google-apps.folder'"
            pp30_folders = gd.find_files(drive_service, pp30_folders_query)
            if pp30_folders:
                pp30_folder_id = pp30_folders[0]['id']
                for i, month in enumerate(range(1, 13)):
                    month_str = f"{month:02d}"
                    file_query = f"'{pp30_folder_id}' in parents and name contains '{payload.year}{month_str}' and mimeType = 'application/pdf'"
                    pp30_files = gd.find_files(drive_service, file_query)

                    if pp30_files:
                        file_id = pp30_files[0]['id']
                        request = drive_service.files().get_media(fileId=file_id)
                        fh = BytesIO()
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                        fh.seek(0)
                        
                        prompt = "จากเอกสารนี้ ให้ดึงตัวเลขของหัวข้อ 'ยอดขายที่ต้องเสียภาษี' ออกมา ตอบกลับเฉพาะตัวเลขเท่านั้น ห้ามมีตัวหนังสือเด็ดขาด"
                        amount_str = get_amount_from_gemini(fh.getvalue(), prompt)
                        try:
                            amount = float(amount_str.replace(",", ""))
                        except (ValueError, TypeError):
                            logging.warning(f"Could not convert '{amount_str}' to a number for PP30 month {month_str}.")
                            amount = amount_str
                        pp30_ws[f'D{i+5}'] = amount
                    else:
                        pp30_ws[f'D{i+5}'] = "-"
            else:
                for i in range(12):
                    pp30_ws[f'D{i+5}'] = "-"
    
    # Save and return workbook
    virtual_workbook = BytesIO()
    wb.save(virtual_workbook)
    virtual_workbook.seek(0)
    filename = f"{company_name}_reconcile.xlsx"
    logging.info(f"Returning Excel file: {filename}")
    return StreamingResponse(
        virtual_workbook,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'} # Corrected header escaping
    )
