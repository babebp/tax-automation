# google_drive.py
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 1. Authenticate with Google Drive
def get_drive_service():
    """Authenticates with the Google Drive API using service account credentials."""
    creds_path = os.path.join(os.path.dirname(__file__), 'credential.json')
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Credential file not found at: {creds_path}")
    
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    service = build('drive', 'v3', credentials=creds)
    return service

# 2. Placeholder functions for the Get Data Workflow
def find_files(service, query):
    """Helper to find files based on a query."""
    results = service.files().list(q=query, pageSize=100, fields="files(id, name)").execute()
    return results.get('files', [])

def get_company_folder(service, company_name):
    """Finds the main folder for a company."""
    query = f"name = '{company_name}' and mimeType = 'application/vnd.google-apps.folder'"
    folders = find_files(service, query)
    return folders[0] if folders else None

# You would add more specific functions here as you implement the workflow, e.g.:
# def find_tb_file(service, parent_folder_id): ...
# def find_gl_file(service, parent_folder_id): ...
# etc.
