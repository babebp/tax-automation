# Workflow Tab Documentation

This document explains the functionality of the "Workflow" tab in the Tax Automation application.

## Overview

The Workflow tab allows users to initiate a data processing workflow for a selected company, month, and year. Upon completion, the workflow generates an Excel file that the user can download.

## Step-by-Step Guide

1.  **Navigate to the Workflow Tab**: Open the application and click on the "Workflow" tab.

2.  **Select a Company**:
    *   The application will load a list of all available companies.
    *   Choose the desired company from the "เลือก Company" (Select Company) dropdown menu.
    *   **Note**: If no companies are listed, you must first add a company in the "Settings" tab.

3.  **Select the Period**:
    *   **Month**: Choose the desired month from the "เลือกเดือน" (Select Month) dropdown. The months are listed as two-digit numbers (e.g., "01" for January).
    *   **Year**: Choose the desired year from the "เลือกปี" (Select Year) dropdown. The available years range from 2021 to the current year.

4.  **Start the Workflow**:
    *   Click the "Start" button to begin the process.
    *   A spinner will appear with the message "Processing workflow for [Company Name] for [Month]/[Year]..." to indicate that the process is running.

5.  **Download the Result**:
    *   Once the workflow is complete, a success message "✅ Workflow complete!" will be displayed.
    *   A download button labeled "📥 Download Excel File" will appear.
    *   Click this button to download the generated Excel file. The filename is determined by the backend process (e.g., `workflow_result.xlsx`).

## Error Handling

*   If the workflow process fails, an error message will be displayed with details about the failure (e.g., "Workflow failed: [Error Details]").
*   If there is an unexpected error, a generic error message will be shown.

In case of an error, please check the selected parameters and try again. If the issue persists, contact support.

## Backend Workflow (What Happens on the Server)

When you click the "Start" button, a detailed process is initiated on the backend server. Here is a step-by-step breakdown of what occurs:

1.  **Initialization**: The backend receives the company ID, month, and year from the frontend.

2.  **Database Query**: It connects to the local database to retrieve essential company-specific settings:
    *   The company's official name.
    *   A list of all registered bank accounts and their corresponding Trial Balance (TB) codes.
    *   The TB codes assigned to standard tax forms (`PND1`, `PND3`, `PND53`, `PP30`, `SSO`).

3.  **Google Drive Authentication**: The server authenticates with the Google Drive API using its stored credentials to gain access to the company's files.

4.  **File & Folder Search**: The server systematically searches for the necessary files and folders within Google Drive:
    *   It locates the main folder for the selected company.
    *   Within this folder, it searches for year-specific subfolders like `Bank_YYYY`, `VAT_YYYY`, `ภพ30` (PP30), and `ภงด` (PND).
    *   It then drills down into these subfolders to find all relevant PDF and Excel files for the selected month and year. This includes bank statements, various tax forms, and VAT reports.

5.  **Data Extraction from Trial Balance (TB)**:
    *   The server finds the main Trial Balance Excel file (usually containing "tb" in its name).
    *   It reads this file to create an in-memory map of each `TB Code` to its corresponding financial amount. This is used for reconciliation.

6.  **Data Extraction from VAT Report**:
    *   It locates the VAT Excel file for the specified period.
    *   It parses this file to extract the actual amounts paid for different tax forms. This data serves as a secondary source for verification.

7.  **AI-Powered PDF Processing (Google Gemini)**: This is a key step for handling unstructured documents.
    *   For every PDF file found (such as a scanned bank statement or a tax receipt), the server downloads its content.
    *   It sends the PDF data to the **Google Gemini AI model**.
    *   Along with the PDF, it sends a specific prompt tailored to the document type (e.g., *"From this bank statement, extract only the final balance amount."* or *"From this tax receipt, extract the total payment amount."*).
    *   The AI performs Optical Character Recognition (OCR) on the PDF and returns the precise numerical value it was asked to find.

8.  **Final Excel Report Generation**:
    *   The server creates a new, blank Excel workbook in memory.
    *   It adds a worksheet with the following columns: `Name`, `TB Code`, `File Found`, `PDF Actual Amount`, `TB Code Amount`, `Excel Actual Column`, `Result 1`, and `Result 2`.
    *   It populates this sheet with the processed data:
        *   **For each bank**: It adds a row with the bank's name, its TB code, the name of the statement PDF found, the balance extracted by the AI, and the corresponding balance from the TB file.
        *   **For each tax form**: It adds a row with the form's name (e.g., "PND53"), its TB code, the receipt PDF found, the amount extracted by the AI, the corresponding amount from the TB file, and the amount cross-referenced from the VAT report.
    *   **Result Columns**: After populating the data, it adds Excel formulas to the `Result 1` and `Result 2` columns to perform automatic validation:
        *   **Result 1**: This column compares the AI-extracted amount (`PDF Actual Amount`) with the `TB Code Amount`.
            *   If the `TB Code` starts with "1", the formula checks for a direct match (`D = E`).
            *   If the `TB Code` starts with "2", the formula checks if the PDF amount matches the negative of the TB amount (`D = -E`).
            *   The cell will show "Correct" or "Incorrect".
        *   **Result 2**: This column is mainly for tax forms and compares the `TB Code Amount` with the `Excel Actual Column` from the VAT report.
            *   If the `TB Code` starts with "2", the formula checks if the negative of the TB amount matches the VAT report amount (`-E = F`).
            *   The cell will show "Correct" or "Incorrect".

9.  **Sending the File**:
    *   The completed Excel report, which exists only in the server's memory, is prepared for sending.
    *   The server sends this Excel file back to the user's browser, which triggers the "Download Excel File" button to appear and allows the user to save the final report.
