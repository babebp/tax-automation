### Company Settings
1. สามารถ Add Company เพิ่มได้
2. สามารถลบ Company ได้
3. สามารถ Rename Company ได้
4. สามารถเลือก Folder จาก Google Drive ที่แชร์ให้กับเราได้
5. สามารถกำหนด TB Code สำหรับ
- PND1
- PND3
- PND53
- PP30
- SSO
- Bank (เพิ่มได้เรื่อยๆ)
- รายได้ 1
- รายได้ 2
- ลดหนี้

### Workflow
1. กำหนด Input ปีกับเดือน (เช่น 2024, 05)
2. สร้าง File Excel
3. Initial Column Header ตามนี้ (Name, TB Code,File Found, PDF Actual Amount, TB Code Amount, Excel Actual Column,Result 1, Result 2)
4. Initial Row ใน Column A ตามนี้ bank1, bank2 ... (ตามจำนวน bank), PND1, PND3, PND53, PP30, SSO
5. Initial Row ใน Column B โดยเอา TB Code สำหรับแต่ละหัวข้อในแต่ละ Row ของ Column A

    ##### BANK PART
    1. หา Folder ข้างใน Folder Company ด้วย Logic "Bank_{year}" เช่น Bank_2024
    2. หาไฟล์ PDF แต่ละไฟล์ด้วย Logic "..._bank{n}_...._{year}{month}.pdf"
    3. เอาชื่อไฟล์ใส่ที่ Row Column C ตาม bank1, bank2, ...
    4. ใช้ LLM อ่านไฟล์ PDF เพื่อดึงยอดคงเหลือสุดท้ายมาในรูปแบบของ Float ใส่ค่าที่ได้ใน Row Column D
    5. อ่านไฟล์ TB ที่ Folder ของ Company ด้วย Logic "..._tb_{year}{month}.xlsx"
    6. หา Row ที่ Column A == TB Code ของ bank แต่ละอัน
    7. ดึง Column G, H ออกมา
    8. ใส่ค่าที่ได้ใน Row Column E (ถ้ามีค่าในช่อง G จะให้เป็น + แต่ถ้ามีค่าในช่อง H 0 จะให้เป็น -)
    9. Row ในแต่ละ bank column F ให้เป็น "-"
    10. Result 1 ให้ใช้ Formula D{n}=E{n} ถ้าใช่ให้ใส่ Correct ถ้าไม่ใช่ให้ใส่ Incorrect
    11.Row ในแต่ละ bank column H ให้เป็น "-"

    ##### PND1
    1. หา Folder ข้างใน Folder Company ด้วย Logic "...ภงด..."
    2. หา Folder PND1 ด้วย Logic "PND1"
    3. หาไฟล์ PDF ด้วย Logic "..._pnd1_...{year}{month}"
    4. 
    ##### PND3
    1. หา Folder ข้างใน Folder Company ด้วย Logic "...ภงด..."
    2. หา Folder PND3 ด้วย Logic "PND3"
    3. หาไฟล์ PDF ด้วย Logic "..._pnd3_...{year}{month}"
    ##### PND53
    1. หา Folder ข้างใน Folder Company ด้วย Logic "...ภงด..."
    2. หาไฟล์ PDF ด้วย Logic "..._pp30_...{year}{month}"
    3. ดึงค่า ..

    ##### PP30
    1. หา Folder ข้างใน Folder Company ด้วย Logic "...ภพ30..."
    2. หา Folder PND53 ด้วย Logic "PND53"
    3. หาไฟล์ PDF ด้วย Logic "..._pnd53_...{year}{month}"
    ##### SSO
    1. หา Folder ข้างใน Folder Company ด้วย Logic "...ภงด..."
    2. หา Folder SSO ด้วย Logic "SSO"
    3. หาไฟล์ PDF ด้วย Logic "..._sso_...{year}{month}"



### Reconcile
1. หาไฟล์ TB 