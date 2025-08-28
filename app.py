# streamlit_app.py
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# Base URL for the FastAPI backend
API_BASE = st.secrets.get("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Company Settings", layout="wide")

st.title("Company Settings & Forms")

# Create tabs for different sections of the app
tab1, tab2, tab3, tab4 = st.tabs(["Settings", "Company Config", "Workflow", "LINE Notification"])

# ---------- Shared helper functions ----------
def fetch_companies(): 
    """Fetches the list of companies from the backend."""
    r = requests.get(f"{API_BASE}/companies")
    r.raise_for_status()
    return r.json()

def fetch_banks(company_id: int):
    """Fetches the list of banks for a specific company."""
    r = requests.get(f"{API_BASE}/companies/{company_id}/banks")
    r.raise_for_status()
    return r.json()

def fetch_forms(company_id: int):
    """Fetches the form configurations for a specific company."""
    r = requests.get(f"{API_BASE}/companies/{company_id}/forms")
    r.raise_for_status()
    return r.json()

# ---------- Tab 1: Add Company ----------
with tab1:
    st.subheader("เพิ่ม Company")
    new_company = st.text_input("Company name", key="new_company_name", placeholder="เช่น ACME Co., Ltd.")
    if st.button("➕ เพิ่ม Company", type="primary"):
        if not new_company.strip():
            st.error("กรุณาใส่ชื่อบริษัท")
        else:
            try:
                # POST request to create a new company
                r = requests.post(f"{API_BASE}/companies", json={"name": new_company.strip()})
                r.raise_for_status()
                st.success("เพิ่ม Company สำเร็จ")
                st.toast('เพิ่ม Company สำเร็จ', icon='✅')
            except requests.HTTPError as e:
                detail = e.response.json().get("detail", str(e))
                st.error(f"เพิ่มไม่สำเร็จ: {detail}")

# ---------- Tab 2: Company Config ----------
with tab2:
    st.subheader("ตั้งค่า Company")

    companies = []
    try:
        companies = fetch_companies()
    except Exception as e:
        st.error(f"โหลดรายชื่อบริษัทไม่สำเร็จ: {e}")

    if companies:
        company_names = [c["name"] for c in companies]
        selected_name = st.selectbox("เลือก Company", options=company_names, key="settings_company_select")
        selected_company = next(c for c in companies if c["name"] == selected_name)
        cid = selected_company["id"]
        
        st.divider()

        cols = st.columns(2)
        
        # Left column for managing banks
        with cols[0]:
            st.markdown("### Bank (เพิ่มได้ไม่จำกัด)")
            with st.container():
                st.markdown("**เพิ่ม Bank**")
                bank_name = st.text_input("Bank Name", key="bank_name_input", placeholder="เช่น SCB, KBank")
                bank_tb_code = st.text_input("TB Code (Bank)", key="bank_tb_input", placeholder="เช่น TB-XXXX")
                if st.button("➕ เพิ่ม Bank", key="add_bank_btn"):
                    if not bank_name.strip() or not bank_tb_code.strip():
                        st.error("กรุณากรอกให้ครบ")
                    else:
                        try:
                            # POST request to add a new bank
                            r = requests.post(f"{API_BASE}/banks", json={
                                "company_id": cid,
                                "bank_name": bank_name.strip(),
                                "tb_code": bank_tb_code.strip()
                            })
                            r.raise_for_status()
                            st.success("เพิ่ม Bank สำเร็จ")
                        except requests.HTTPError as e:
                            detail = e.response.json().get("detail", str(e))
                            st.error(f"เพิ่มไม่สำเร็จ: {detail}")

            st.markdown("**รายการ Bank**")
            try:
                banks = fetch_banks(cid)
            except Exception as e:
                banks = []
                st.error(f"โหลด Bank ไม่สำเร็จ: {e}")

            if banks:
                for b in banks:
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    c1.write(b["bank_name"])
                    c2.write(b["tb_code"])
                    c3.write(f'Company ID: {b["company_id"]}')
                    if c4.button("🗑️ ลบ", key=f"del_bank_{b['id']}"):
                        try:
                            # DELETE request to remove a bank
                            rr = requests.delete(f"{API_BASE}/banks/{b['id']}")
                            rr.raise_for_status()
                            st.rerun()
                        except Exception as e:
                            st.error(f"���บไม่สำเร็จ: {e}")
            else:
                st.info("ยังไม่มี Bank ในบริษัทนี้")

        # Right column for managing fixed forms
        with cols[1]:
            st.markdown("### แบบฟอร์มคงที่ (แก้ไข TB Code ได้เท่านั้น)")
            try:
                forms_payload = fetch_forms(cid)
                fixed = forms_payload.get("fixed", [])
                current = forms_payload.get("forms", {})
            except Exception as e:
                fixed, current = [], {}
                st.error(f"โหลดฟอร์มไม่สำเร็จ: {e}")

            form_inputs = {}
            with st.form(key=f"forms_edit_{cid}", clear_on_submit=False):
                for ft in fixed:
                    form_inputs[ft] = st.text_input(f"{ft} TB Code", value=current.get(ft, ""), key=f"tb_{ft}_{cid}")
                submitted = st.form_submit_button("💾 บันทึก TB Code ทั้งหมด", type="primary")
                if submitted:
                    try:
                        # PUT request to update form TB codes
                        r = requests.put(f"{API_BASE}/companies/{cid}/forms", json={"data": form_inputs})
                        r.raise_for_status()
                        st.success("บันทึกสำเร็จ")
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"บันทึกไม่สำเร็จ: {detail}")
    else:
        st.info("ยังไม่มีบริษัทในระบบ — เพิ่มบริษัทก่อนในแท็บ Settings")

# ---------- Tab 3: Workflow ----------
with tab3:
    st.subheader("Workflow")

    companies = []
    try:
        companies = fetch_companies()
    except Exception as e:
        st.error(f"โหลดรายชื่อบริษัทไม่สำเร็จ: {e}")

    if companies:
        company_names = [c["name"] for c in companies]
        selected_name = st.selectbox("เลือก Company", options=company_names, key="workflow_company_select")
        selected_company = next(c for c in companies if c["name"] == selected_name)
        cid = selected_company["id"]

        # Dropdowns for month and year selection
        months = [f"{i:02d}" for i in range(1, 13)]
        current_year = 2025
        years = list(range(2021, current_year + 1))

        selected_month = st.selectbox("เลือกเดือน", options=months)
        selected_year = st.selectbox("เลือกปี", options=years, index=len(years) - 1)

        if st.button("Start", type="primary"):
            with st.spinner(f"Processing workflow for {selected_name} for {selected_month}/{selected_year}..."):
                try:
                    # POST request to start the workflow and receive a file
                    r = requests.post(f"{API_BASE}/workflow/start", json={
                        "company_id": cid,
                        "month": selected_month,
                        "year": selected_year
                    }, stream=True)
                    r.raise_for_status()
                    
                    # Extract filename from response headers
                    content_disposition = r.headers.get('content-disposition')
                    filename = "workflow_result.xlsx" # Default filename
                    if content_disposition:
                        parts = content_disposition.split(';')
                        for part in parts:
                            if 'filename=' in part:
                                filename = part.split('=')[1].strip('"')

                    st.success("✅ Workflow complete!")
                    # Display download button for the generated Excel file
                    st.download_button(
                        label="📥 Download Excel File",
                        data=r.content,
                        file_name=filename,
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )

                except requests.HTTPError as e:
                    try:
                        detail = e.response.json().get("detail", str(e))
                    except:
                        detail = str(e)
                    st.error(f"Workflow failed: {detail}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
    else:
        st.info("ยังไม่มีบริษัทในระบบ — เพิ่มบริษัทก่อนในแท็บ Settings")

# ---------- Tab 4: LINE Notification ----------
with tab4:
    st.subheader("ส่งข้อความผ่าน LINE")

    # --- Recipient Management ---
    with st.expander("จัดการรายชื่อผู้รับ (LINE User ID)"):
        st.markdown("เพิ่มหรือลบรายชื่อผู้รับข้อความ")

        # Fetch current recipients
        try:
            recipients_res = requests.get(f"{API_BASE}/line/recipients")
            recipients_res.raise_for_status()
            recipients = recipients_res.json()
        except Exception as e:
            st.error(f"ไม่สามารถโหลดรายชื่อผู้รับได้: {e}")
            recipients = []

        # Display recipients with delete buttons
        if recipients:
            for r in recipients:
                col1, col2 = st.columns([4, 1])
                col1.text(r['uid'])
                if col2.button("🗑️ ลบ", key=f"del_recipient_{r['id']}"):
                    try:
                        del_res = requests.delete(f"{API_BASE}/line/recipients/{r['id']}")
                        del_res.raise_for_status()
                        st.toast("ลบผู้รับสำเร็จ", icon="✅")
                        st.rerun()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"ลบไม่สำเร็จ: {detail}")

        # Add new recipient
        with st.form("add_recipient_form", clear_on_submit=True):
            new_uid = st.text_input("LINE User ID", placeholder="U123456789...")
            submitted = st.form_submit_button("➕ เพิ่มผู้รับ")
            if submitted:
                if not new_uid.strip():
                    st.error("กรุณาใส่ User ID")
                else:
                    try:
                        add_res = requests.post(f"{API_BASE}/line/recipients", json={"uid": new_uid.strip()})
                        add_res.raise_for_status()
                        st.toast("เพิ่มผู้รับสำเร็จ", icon="✅")
                        st.rerun()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"เพิ่มไม่สำเร็จ: {detail}")

    st.divider()

    # --- Send Message ---
    st.markdown("### ส่งข้อความ")
    message_text = st.text_area("ข้อความที่จะส่ง:", height=150, placeholder="พิมพ์ข้อความที่นี่...")
    if st.button("🚀 ส่งข้อความ", type="primary"):
        if not message_text.strip():
            st.error("กรุณาพิมพ์ข้อความที่จะส่ง")
        else:
            with st.spinner("กำลังส่งข้อความ..."):
                try:
                    send_res = requests.post(f"{API_BASE}/line/send_message", json={"message": message_text.strip()})
                    send_res.raise_for_status()
                    sent_count = send_res.json().get("sent_count", 0)
                    st.success(f"ส่งข้อความสำเร็จ ({sent_count} คน)")
                    st.balloons()
                except requests.HTTPError as e:
                    detail = e.response.json().get("detail", str(e))
                    st.error(f"ส่งข้อความไม่สำเร็จ: {detail}")

