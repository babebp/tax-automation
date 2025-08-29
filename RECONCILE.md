### Objective
Create new spreadsheet with sub sheet inside contains information from various files.

### Step
0. In streamlit create new tab called "Reconcile" and then it has one button to click start if click start then to this step
1. Sub Sheet: TB
1.1 From company directory in google drive (as we selected for example "0.Com1_TestWorkFlowAutomation_2025"); Read file xlsx that filename contain "tb";
1.2 Copy first 8 columns all rows and paste into this sheet (start at row 6)
1.3 (column C to O, row 5) the formula in these cell are "=SUBTOTAL(9,C8:C)" *for each column (if D then D8:D)*
1.4 (column I-J, row 6) merge cell and the value is "ปรับปรุง"
1.5 (column I, row 7) = "เดบิท"
1.6 (column J, row 7) = "เครดิต"
1.7 (column K, row 6-7) merge cell and the value is "Net"
1.8 (column K, row 4) = "กำไร"
1.9 (column K, row 8++) cell formula is "=G8+I8-H8-J8" *for each row (if row 9 then =G9+I9-H9-J9)*
1.10 (column L, row 3) cell formula is "=+L5+L4"
1.11 (column L, row 4) cell formula is "=+M5-L5"
1.12 (column M, row 3) cell formula is "=+M5+M4"
1.13 (column L-M, row 6) merge cell and value is "งบกำไรขาดทุน"
1.14 (column L, row 7) = "เดบิท"
1.15 (column M, row 7) = "เครดิต"
1.16 (column N, row 3) formula is "=+N5+N4"
1.17 (column O, row 2) formula is "=+N3-O3"
1.18 (column O, row 3) formula is "=+O5+O4"
1.19 (column O, row 4) formula is "=+L4"
1.20 (column L, row 8++) formula is IF column A value (same row) start with "4" or "5" then "=IF(K65>0,K65,0)" (according to the row number) else ""
1.21 (column M, row 8++) formula is IF column A value (same row) start with "4" or "5" then "=IF(K65<0,-K65,0)" (according to the row number) else ""
1.22 (column N, row 8++) formula is IF column A value (same row) start with "1" or "2" or "3" then "=IF(K65>0,K65,0)" (according to the row number) else ""
1.23 (column O, row 8++) formula is IF column A value (same row) start with "1" or "2" or "3" then "=IF(K65<0,-K65,0)" (according to the row number) else ""
1.24 (column M, row 2) formula is "=+L3-M3"
1.25 (column N-O, row 6) merge cell and value is "งบแสดงฐานะการเงิน"
1.26 (column N, row 7) = "เดบิท"
1.27 (column O, row 7) = "เครดิต"
1.28 (column A, row 1) = "ชื่อบริษัท"
1.29 (column A, row 2) = "งบทดลอง ณ วันที่"
1.30 (column A, row 3) = "เลขที่บัญชีจาก"
1.31 (column A, row 4) = "วันที่จาก"
1.32 (column A, row 5) = "เลือกแผนก"
1.33 (column B, row 3) = "xxxxxx - xxxxxx"
1.34 (column B, row 5) = "* รวมบัญชียอดเป็น 0 N"
1.35 (column B, row 4) = "_ ถึง _"
1.36 (column B, row 2) = "xx มกราคม xxx"


2. Sub Sheet: GL
2.1 From root directory; Read file xlsx that filename contain "gl"; Copy all content and paste into this sheet; DONE !

3. Sub Sheet: PP30
3.1
C4 = "เดือน"
D4 = "PP30"
E4 = "รายได้"
F4 = "ลดหนี้"
G4 = "Diff"

3.2
C5-C16 = List month in Thai (มกราคม - ธันวาคม)

3.3
D5-D16 = Read from GL sub sheet 41210

4. Each TB Code
4.1 From company directory in google drive (as we selected for example "0.Com1_TestWorkFlowAutomation_2025"); Read file xlsx that filename contain "gl";
4.2 Loop column A each row, to find these
- If value is "ลำดับที่" then go back one row and see if it start with "1" or "2", if so then split the text and get first part it will be number like this "xxxxxx"
- get from the number part's row to the next empty cell, for example

"xxxxxx" (from here)
ลำดับที่
1
2
3
4
5
6
(to here)

"yyyyyy" (from here)
ลำดับที่
1
2
3
(to here)

- check if there're sub sheet that is this number, if exist then append to that sub sheet, if not then create new sheet with this number "xxxxxx" and put the content inside