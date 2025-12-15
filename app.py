# streamlit_app.py
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# Base URL for the FastAPI backend
API_BASE = st.secrets.get("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Accounting Reconciliation Portal", layout="wide")

st.image("logo.jpg", width=200)

st.title("Accounting Reconciliation Portal")

# Create tabs for different sections of the app
tab1, tab2, tab3 = st.tabs(["Company Config", "Workflow", "Reconcile"])

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

@st.dialog("Add Company")
def add_company_dialog():
    st.subheader("เพิ่ม Company")
    new_company_name = st.text_input("Company name", key="new_company_name_dialog", placeholder="เช่น ACME Co., Ltd.")
    if st.button("Submit", key="submit_new_company"):
        if not new_company_name.strip():
            st.error("กรุณาใส่ชื่อบริษัท")
        else:
            try:
                r = requests.post(f"{API_BASE}/companies", json={"name": new_company_name.strip()})
                r.raise_for_status()
                st.toast('เพิ่ม Company สำเร็จ', icon='✅')
                st.rerun()
            except requests.HTTPError as e:
                detail = e.response.json().get("detail", str(e))
                st.error(f"เพิ่มไม่สำเร็จ: {detail}")

# ---------- Tab 1: Company Config ----------
with tab1:
    st.subheader("ตั้งค่า Company")
    

    if st.button("➕ Add Company"):
        add_company_dialog()

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

        with st.expander("จัดการ Company"):
            st.markdown("**แก้ไขชื่อ Company**")
            new_name = st.text_input("New company name", value=selected_company["name"], key=f"edit_name_{cid}")
            if st.button("💾 บันทึกชื่อใหม่", key=f"save_name_{cid}"):
                if not new_name.strip():
                    st.error("ชื่อบริษัทห้ามว่างเปล่า")
                else:
                    try:
                        r = requests.put(f"{API_BASE}/companies/{cid}", json={"name": new_name.strip()})
                        r.raise_for_status()
                        st.success("เปลี่ยนชื่อ Company สำเร็จ")
                        st.toast('เปลี่ยนชื่อ Company สำเร็จ', icon='✅')
                        st.rerun()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"เปลี่ยนชื่อไม่สำเร็จ: {detail}")

            st.divider()

            st.markdown("**ลบ Company**")
            st.warning(f"การลบ Company '{selected_name}' จะลบข้อมูลทั้งหมดที่เกี่ยวข้องอย่างถาวร")
            if st.checkbox(f"ฉันต้องการลบ Company '{selected_name}'", key=f"delete_confirm_{cid}"):
                if st.button("🗑️ ลบ Company ทันที", type="primary", key=f"delete_btn_{cid}"):
                    try:
                        r = requests.delete(f"{API_BASE}/companies/{cid}")
                        r.raise_for_status()
                        st.success(f"ลบ Company '{selected_name}' สำเร็จ")
                        st.rerun()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"ลบไม่สำเร็จ: {detail}")
        
        st.divider()

        # --- Google Drive Folder Selection ---
        st.subheader("Google Drive Folder")
        folder_name = selected_company.get("google_drive_folder_name") or "ยังไม่ได้เลือก"
        st.info(f"Folder ที่เลือกไว้: **{folder_name}**")

        if 'show_folder_selection' not in st.session_state:
            st.session_state.show_folder_selection = False
        
        st.session_state.selected_company_id_for_folder = cid

        if st.button("เปลี่ยน Folder"):
            st.session_state.show_folder_selection = not st.session_state.show_folder_selection

        if st.session_state.show_folder_selection:
            parent_folder_name = st.text_input(
                "Enter Parent Folder Name to search in:", 
                placeholder="e.g., _0.ปิดงบการเงินปี2568_2025"
            )

            if parent_folder_name and parent_folder_name.strip():
                try:
                    with st.spinner(f"Loading child folders from '{parent_folder_name}'..."):
                        params = {"parent_folder_name": parent_folder_name.strip()}
                        folders_res = requests.get(f"{API_BASE}/google-drive/folders", params=params)
                        folders_res.raise_for_status()
                        drive_folders = folders_res.json()
                    
                    if not drive_folders:
                        st.warning(f"No child folders found in '{parent_folder_name}', or the parent folder itself was not found.")
                    else:
                        folder_options = {f["name"]: f["id"] for f in drive_folders}
                        
                        current_folder_name = selected_company.get("google_drive_folder_name")
                        folder_names = list(folder_options.keys())
                        
                        try:
                            current_index = folder_names.index(current_folder_name) if current_folder_name in folder_names else 0
                        except ValueError:
                            current_index = 0

                        selected_folder_name = st.selectbox(
                            "Select a child folder (you can type to search)", 
                            options=folder_names,
                            index=current_index
                        )

                        if selected_folder_name:
                            col1, col2, _ = st.columns([1, 1, 4])
                            with col1:
                                if st.button("💾 บันทึก", type="primary"):
                                    selected_folder_id = folder_options[selected_folder_name]
                                    company_id_to_update = st.session_state.selected_company_id_for_folder
                                    update_res = requests.put(
                                        f"{API_BASE}/companies/{company_id_to_update}/google-drive-folder",
                                        json={"google_drive_folder_id": selected_folder_id, "google_drive_folder_name": selected_folder_name}
                                    )
                                    update_res.raise_for_status()
                                    st.success(f"เลือก Folder '{selected_folder_name}' เรียบร้อยแล้ว")
                                    st.session_state.show_folder_selection = False
                                    st.rerun()
                            with col2:
                                if st.button("ยกเลิก"):
                                    st.session_state.show_folder_selection = False
                                    st.rerun()

                except Exception as e:
                    st.error(f"Could not load child folders: {e}")
            else:
                st.info("Please enter a parent folder name to begin.")
        
        st.divider()

        cols = st.columns(2)
        
        with cols[1]:
            st.markdown("### Bank")
            with st.container():
                # st.markdown("**เพิ่ม Bank**")
                bank_name = st.text_input("Bank Name", key="bank_name_input", placeholder="เช่น SCB, KBank")
                bank_tb_code = st.text_input("TB Code (Bank)", key="bank_tb_input", placeholder="เช่น TB-XXXX")
                if st.button("➕ เพิ่ม Bank", key="add_bank_btn"):
                    if not bank_name.strip() or not bank_tb_code.strip():
                        st.error("กรุณากรอกให้ครบ")
                    else:
                        try:
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
                    c2, c3, c4 = st.columns([3, 2, 1])
                    c2.write(b["bank_name"])
                    c3.write(b["tb_code"])
                    if c4.button("🗑️ ลบ", key=f"del_bank_{b['id']}"):
                        try:
                            rr = requests.delete(f"{API_BASE}/banks/{b['id']}")
                            rr.raise_for_status()
                            st.rerun()
                        except Exception as e:
                            st.error(f"ลบไม่สำเร็จ: {e}")
            else:
                st.info("ยังไม่มี Bank ในบริษัทนี้")

        with cols[0]:
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
                for ft in ["PND1", "PND3", "PND53", "PP30", "SSO"]:
                    if ft in fixed:
                        form_inputs[ft] = st.text_input(f"{ft} TB Code", value=current.get(ft, ""), key=f"tb_{ft}_{cid}")
                
                st.divider()
                st.markdown("#### Reconcile Settings")
                form_inputs["Revenue"] = st.text_input("รายได้ TB Code 1", value=current.get("Revenue", ""), key=f"tb_revenue_{cid}")
                form_inputs["Revenue2"] = st.text_input("รายได้ TB Code 2", value=current.get("Revenue2", ""), key=f"tb_revenue2_{cid}")
                form_inputs["Credit Note"] = st.text_input("ลดหนี้ TB Code", value=current.get("Credit Note", ""), key=f"tb_credit_note_{cid}")

                submitted = st.form_submit_button("Save", type="primary")
                if submitted:
                    try:
                        r = requests.put(f"{API_BASE}/companies/{cid}/forms", json={"data": form_inputs})
                        r.raise_for_status()
                        st.success("บันทึกสำเร็จ")
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"บันทึกไม่สำเร็จ: {detail}")
    else:
        st.info("ยังไม่มีบริษัทในระบบ")


# ---------- Tab 2: Workflow ----------
with tab2:
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

        months = [f"{i:02d}" for i in range(1, 13)]
        current_year = 2025
        years = list(range(2021, current_year + 1))

        selected_month = st.selectbox("เลือกเดือน", options=months)
        selected_year = st.selectbox("เลือกปี", options=years, index=len(years) - 1)

        if st.button("Start Workflow", type="primary"):
            with st.spinner(f"Processing workflow for {selected_name} for {selected_month}/{selected_year}..."):
                try:
                    r = requests.post(f"{API_BASE}/workflow/start", json={
                        "company_id": cid,
                        "month": selected_month,
                        "year": selected_year
                    }, stream=True)
                    r.raise_for_status()
                    
                    # Construct the filename directly on the frontend
                    filename = f"{selected_name}_{selected_year}{selected_month}_workflow.xlsx"

                    st.success("✅ Workflow complete!")
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
        st.info("ยังไม่มีบริษัทในระบบ")

# ---------- Tab 3: Reconcile ----------
with tab3:
    st.subheader("Reconcile")

    companies = []
    try:
        companies = fetch_companies()
    except Exception as e:
        st.error(f"โหลดรายชื่อบริษัทไม่สำเร็จ: {e}")

    if companies:
        company_names = [c["name"] for c in companies]
        selected_name = st.selectbox("เลือก Company", options=company_names, key="reconcile_company_select")
        selected_company = next(c for c in companies if c["name"] == selected_name)
        cid = selected_company["id"]

        current_year = 2025
        years = list(range(2021, current_year + 1))
        months = [f"{i:02d}" for i in range(1, 13)]
        selected_month = st.selectbox("เลือกเดือน", options=months, key="reconcile_month_select")
        selected_year = st.selectbox("เลือกปี", options=years, index=len(years) - 1, key="reconcile_year_select")


        st.divider()
        st.subheader("Select parts to run:")
        run_tb_subsheet = st.checkbox("TB Sub-sheet", value=True)
        run_gl_subsheet = st.checkbox("GL Sub-sheet", value=True)
        run_pp30_subsheet = st.checkbox("PP30 Sub-sheet", value=True)
        st.divider()

        if st.button("Start Reconcile", type="primary"):
            parts_to_run = []
            if run_tb_subsheet:
                parts_to_run.append("tb_subsheet")
            if run_gl_subsheet:
                parts_to_run.append("gl_subsheet")
            if run_pp30_subsheet:
                parts_to_run.append("pp30_subsheet")

            with st.spinner(f"Processing reconcile for {selected_name} for {selected_year}..."):
                try:
                    # POST request to start the reconcile and receive a file
                    r = requests.post(f"{API_BASE}/reconcile/start", json={
                        "company_id": cid,
                        "year": selected_year,
                        "month": selected_month,
                        "parts": parts_to_run
                    }, stream=True)
                    r.raise_for_status()
                    
                    # Construct the filename directly on the frontend
                    filename = f"{selected_name}_{selected_year}{selected_month}_reconcile.xlsx"

                    st.success("✅ Reconcile complete!")
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
                    st.error(f"Reconcile failed: {detail}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
    else:
        st.info("ยังไม่มีบริษัทในระบบ")

