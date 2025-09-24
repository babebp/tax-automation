# Tax Automation Project

This project is a Streamlit web application that automates tax-related workflows. It integrates with Google Drive to fetch source files, uses a FastAPI backend for data processing and database operations, and leverages the Gemini API for data extraction from PDFs.

## Workflows

### Workflow A: Initial System Setup

This workflow covers the initial configuration of the system for a new company. All steps are performed in the **Company Config** tab of the Streamlit application.

*   **Step 1: Add a Company**
    *   Click the "➕ Add Company" button.
    *   Enter the company name in the dialog and submit.

*   **Step 2: Configure Google Drive Folder**
    *   Select the newly created company from the dropdown.
    *   Click "เปลี่ยน Folder" (Change Folder).
    *   Enter the name of a parent folder in your Google Drive to search within (e.g., `_0.ปิดงบการเงินปี2568_2025`).
    *   Select the correct child folder for the company from the resulting dropdown.
    *   Click "💾 บันทึก" (Save) to link the folder to the company. This folder is where the system will look for all necessary files (TB, GL, bank statements, tax forms, etc.).

*   **Step 3: Add Bank Information**
    *   In the "Bank" section, enter the bank's name (e.g., `SCB`) and its corresponding TB Code.
    *   Click "➕ เพิ่ม Bank" (Add Bank).
    *   Repeat for all company bank accounts.

*   **Step 4: Configure Form TB Codes**
    *   In the "แบบฟอร์มคงที่" (Fixed Forms) section, enter the correct TB Code for each tax form (PND1, PND3, PND53, PP30, SSO).
    *   In the "Reconcile Settings" section, enter the TB Codes for "รายได้" (Revenue) and "ลดหนี้" (Credit Note).
    *   Click "Save" to store the configuration.

### Workflow B: Monthly Tax Document Processing

This workflow is executed monthly to process tax documents and generate a verification report. It is performed in the **Workflow** tab.

*   **Step 1: Select Company and Period**
    *   Navigate to the "Workflow" tab.
    *   Select the target company from the dropdown.
    *   Choose the month and year for the workflow.

*   **Step 2: Start the Workflow**
    *   Click the "Start Workflow" button.
    *   The system will then perform the following actions automatically:
        1.  **Fetch Data from Google Drive:** It locates the company's configured Google Drive folder and searches for required files for the selected month/year, including:
            *   The main TB (Trial Balance) Excel file.
            *   Bank statement PDFs from the `Bank_YYYY` folder.
            *   Tax form PDFs (PP30, PND1, PND3, PND53, SSO) from their respective folders (`ภพ30`, `ภงด`).
            *   VAT Excel files from the `VAT_YYYY` folder.
        2.  **Process Data:**
            *   It reads the TB file to get the expected financial amounts for each TB Code.
            *   For each PDF file (bank statements, tax forms), it sends the content to the **Gemini API** to extract the relevant financial amount.
            *   It reads the VAT Excel file to get actual tax amounts.
        3.  **Generate Report:** It creates an Excel spreadsheet (`.xlsx`) comparing the amounts from the PDFs (Actual Amount) with the amounts from the TB file (TB Code Amount) and the VAT file (Excel Actual Column). It includes formulas to check if the values match.

*   **Step 3: Download the Report**
    *   Once the process is complete, a "📥 Download Excel File" button will appear.
    *   Click it to download the generated report.

### Workflow C: Year-End Financial Reconcile

This workflow is used to generate a comprehensive year-end reconciliation workbook. It is performed in the **Reconcile** tab.

*   **Step 1: Select Company and Year**
    *   Navigate to the "Reconcile" tab.
    *   Select the company and the financial year to reconcile.

*   **Step 2: Choose Parts to Run**
    *   Select the specific sub-sheets you want to generate:
        *   **TB Sub-sheet:** Creates a detailed Trial Balance sheet with adjustments and financial statement columns.
        *   **GL Sub-sheet:** Copies the raw General Ledger data into its own sheet.
        *   **TB Code Sub-sheets:** Creates a separate sheet for each TB Code that starts with '1' or '2', containing all its corresponding GL entries.
        *   **PP30 Sub-sheet:** Creates a summary sheet comparing monthly revenue and credit notes from the GL against the sales figures reported in the monthly PP30 PDFs.

*   **Step 3: Start the Reconcile Process**
    *   Click the "Start Reconcile" button.
    *   The system fetches the main TB and GL Excel files from the company's Google Drive folder for the selected year.
    *   It processes the data and generates a new Excel workbook containing the selected sub-sheets. For the PP30 sheet, it also fetches all 12 monthly PP30 PDFs from Google Drive and uses the Gemini API to extract the required sales figures.

*   **Step 4: Download the Reconcile Workbook**
    *   A "📥 Download Excel File" button will appear upon completion.
    *   Click it to download the final reconciliation workbook.

### Utility: LINE Notification Setup

The application includes a separate utility for sending notifications via the LINE Messaging API. This is configured on the **LINE Notification** page.

*   **Step 1: Add a LINE Channel**
    *   Navigate to the "LINE Notification" page and the "Channel Info" tab.
    *   Click "➕ Add Line Channel".
    *   Provide a name for the channel and the Channel Access Token from your LINE Developers Console.

*   **Step 2: Send a Message**
    *   Go to the "Send Message" tab.
    *   Select the channel you configured.
    *   Choose the registered users or groups you want to send a message to. (Users and groups are automatically registered when they interact with your LINE bot).
    *   Type your message and click "🚀 ส่งข้อความ" (Send Message).
