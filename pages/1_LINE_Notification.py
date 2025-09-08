import streamlit as st
import requests

# Base URL for the FastAPI backend, assuming it's defined in the main app's secrets
API_BASE = st.secrets.get("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="LINE Notification", layout="wide")

st.title("LINE Notification")

def censor_token(token: str) -> str:
    """Censors a token, showing only the first character and the last four characters."""
    if not isinstance(token, str) or len(token) <= 5: # 1 for prefix, 4 for suffix
        return "********"
    return f"{token[:1]}...........{token[-4:]}"

@st.dialog("Add LINE Channel")
def add_channel_dialog():
    st.markdown("**เพิ่มช่องทางใหม่**")
    new_channel_name = st.text_input("ชื่อช่องทาง (Channel Name)", placeholder="เช่น 'Marketing', 'Support'")
    new_channel_token = st.text_input("Channel Access Token", type="password", placeholder="ใส่ Token ที่นี่")
    if st.button("Submit"):
        if not new_channel_name.strip() or not new_channel_token.strip():
            st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
        else:
            try:
                add_res = requests.post(f"{API_BASE}/line/channels", json={
                    "name": new_channel_name.strip(),
                    "token": new_channel_token.strip()
                })
                add_res.raise_for_status()
                st.toast("เพิ่มช่องทางสำเร็จ", icon="✅")
                st.rerun()
            except requests.HTTPError as e:
                detail = e.response.json().get("detail", str(e))
                st.error(f"เพิ่มไม่สำเร็จ: {detail}")

# ---------- LINE Notification Page Content ----------
st.subheader("LINE Message Management")

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["Send Message", "Manage Recipients", "Registered Users", "Active Groups"])

# --- Tab 1: Send Message ---
with tab1:
    st.markdown("### ส่งข้อความ")

    # Fetch channels for dropdown
    try:
        channels_res = requests.get(f"{API_BASE}/line/channels")
        channels_res.raise_for_status()
        channels = channels_res.json()
        channel_map = {ch['name']: ch['id'] for ch in channels}
    except Exception as e:
        st.error(f"ไม่สามารถโหลดรายชื่อช่องทางได้: {e}")
        channels = []
        channel_map = {}

    if not channels:
        st.warning("ยังไม่มีการตั้งค่าช่องทางสำหรับส่งข้อความ กรุณาเพิ่มช่องทางก่อน")
    else:
        selected_channel_name = st.selectbox("เลือกช่องทางที่จะใช้ส่ง", options=list(channel_map.keys()))
        
        message_text = st.text_area("ข้อความที่จะส่ง:", height=150, placeholder="พิมพ์ข้อความที่นี่...")
        
        if st.button("🚀 ส่งข้อความ", type="primary"):
            if not message_text.strip():
                st.error("กรุณาพิมพ์ข้อความที่จะส่ง")
            elif not selected_channel_name:
                st.error("กรุณาเลือกช่องทางที่จะใช้ส่ง")
            else:
                selected_channel_id = channel_map[selected_channel_name]
                with st.spinner("กำลังส่งข้อความ..."):
                    try:
                        send_res = requests.post(f"{API_BASE}/line/send_message", json={
                            "channel_id": selected_channel_id,
                            "message": message_text.strip()
                        })
                        send_res.raise_for_status()
                        sent_count = send_res.json().get("sent_count", 0)
                        st.success(f"ส่งข้อความสำเร็จ ({sent_count} คน)")
                        st.balloons()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"ส่งข้อความไม่สำเร็จ: {detail}")
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")

# --- Tab 2: Manage Recipients ---
with tab2:
    st.markdown("### จัดการบัญชีผู้ส่ง (LINE Channels)")
    if st.button("➕ Add Line Channel"):
        add_channel_dialog()

    # Fetch current channels
    try:
        channels_res = requests.get(f"{API_BASE}/line/channels")
        channels_res.raise_for_status()
        channels = channels_res.json()
    except Exception as e:
        st.error(f"ไม่สามารถโหลดรายชื่อช่องทางได้: {e}")
        channels = []

    # Display channels with delete buttons
    if channels:
        for ch in channels:
            col1, col2, c3 = st.columns([2, 4, 1])
            col1.text(ch['name'])
            col2.text(censor_token(ch['token']))
            if c3.button("🗑️ ลบ", key=f"del_channel_{ch['id']}"):
                try:
                    del_res = requests.delete(f"{API_BASE}/line/channels/{ch['id']}")
                    del_res.raise_for_status()
                    st.toast("ลบช่องทางสำเร็จ", icon="✅")
                    st.rerun()
                except requests.HTTPError as e:
                    detail = e.response.json().get("detail", str(e))
                    st.error(f"ลบไม่สำเร็จ: {detail}")
    
    st.divider()

    st.markdown("### จัดการรายชื่อผู้รับ")
    
    # Fetch channels for dropdown
    try:
        channels_res = requests.get(f"{API_BASE}/line/channels")
        channels_res.raise_for_status()
        channels = channels_res.json()
        channel_map = {ch['name']: ch['id'] for ch in channels}
    except Exception as e:
        st.error(f"ไม่สามารถโหลดรายชื่อช่องทางได้: {e}")
        channels = []
        channel_map = {}

    if not channels:
        st.warning("กรุณาเพิ่มช่องทางผู้ส่งก่อน เพื่อใช้ในการจัดการผู้รับ")
    else:
        selected_channel_name_for_recipients = st.selectbox(
            "เลือกช่องทางเพื่อจัดการผู้รับ", 
            options=list(channel_map.keys()),
            key="recipient_channel_select"
        )
        
        if selected_channel_name_for_recipients:
            selected_channel_id = channel_map[selected_channel_name_for_recipients]
            
            st.markdown("**รายชื่อผู้รับปัจจุบัน**")
            # Fetch recipient details using the selected channel
            try:
                recipients_res = requests.get(f"{API_BASE}/line/channels/{selected_channel_id}/recipients")
                recipients_res.raise_for_status()
                recipients = recipients_res.json()
            except Exception as e:
                st.error(f"ไม่สามารถโหลดรายชื่อผู้รับได้: {e}")
                recipients = []

            # Display recipients with delete buttons
            if recipients:
                for r in recipients:
                    col1, col2 = st.columns([4, 1])
                    col1.text(f"{r['displayName']} ({r['uid']})")
                    if col2.button("🗑️ ลบ", key=f"del_recipient_{r['id']}"):
                        try:
                            del_res = requests.delete(f"{API_BASE}/line/recipients/{r['id']}")
                            del_res.raise_for_status()
                            st.toast("ลบผู้รับสำเร็จ", icon="✅")
                            st.rerun()
                        except requests.HTTPError as e:
                            detail = e.response.json().get("detail", str(e))
                            st.error(f"ลบไม่สำเร็จ: {detail}")
            else:
                st.info("ยังไม่มีผู้รับในช่องทางนี้")

            st.divider()

            # --- Add New Recipients ---
            st.markdown("**เพิ่มผู้รับใหม่**")
            
            # Add by User ID
            with st.form("add_user_form", clear_on_submit=True):
                st.markdown("เพิ่มโดยใช้ User ID")
                new_uid = st.text_input("LINE User ID", placeholder="U123456789...")
                submitted_user = st.form_submit_button("➕ เพิ่มผู้ใช้")
                if submitted_user:
                    if not new_uid.strip():
                        st.error("กรุณาใส่ User ID")
                    else:
                        try:
                            add_res = requests.post(f"{API_BASE}/line/recipients", json={
                                "channel_id": selected_channel_id, "uid": new_uid.strip()
                            })
                            add_res.raise_for_status()
                            st.toast("เพิ่มผู้ใช้สำเร็จ", icon="✅")
                            st.rerun()
                        except requests.HTTPError as e:
                            detail = e.response.json().get("detail", str(e))
                            st.error(f"เพิ่มไม่สำเร็จ: {detail}")

            # Add from list of Groups
            with st.form("add_group_form"):
                st.markdown("เพิ่มจากกลุ่มที่บอทเป็นสมาชิก")
                try:
                    groups_res = requests.get(f"{API_BASE}/line/groups")
                    groups_res.raise_for_status()
                    groups = groups_res.json()
                    group_map = {g['group_name']: g['group_id'] for g in groups}
                except Exception as e:
                    st.error(f"ไม่สามารถโหลดรายชื่อกลุ่มได้: {e}")
                    groups = []
                    group_map = {}

                if not groups:
                    st.warning("บอทไม่ได้อยู่ในกลุ่มใดๆ")
                else:
                    selected_group_name = st.selectbox(
                        "เลือกกลุ่มที่จะเพิ่ม", 
                        options=list(group_map.keys())
                    )
                    submitted_group = st.form_submit_button("➕ เพิ่มกลุ่ม")
                    if submitted_group and selected_group_name:
                        group_id_to_add = group_map[selected_group_name]
                        try:
                            add_res = requests.post(f"{API_BASE}/line/recipients", json={
                                "channel_id": selected_channel_id, "uid": group_id_to_add
                            })
                            add_res.raise_for_status()
                            st.toast(f"เพิ่มกลุ่ม '{selected_group_name}' สำเร็จ", icon="✅")
                            st.rerun()
                        except requests.HTTPError as e:
                            detail = e.response.json().get("detail", str(e))
                            st.error(f"เพิ่มไม่สำเร็จ: {detail}")

# --- Tab 3: Registered Users ---
with tab3:
    st.markdown("### ผู้ใช้ทั้งหมดที่ลงทะเบียนผ่าน LINE")
    st.markdown("รายชื่อผู้ใช้ทั้งหมดที่เคยส่งข้อความหาบอท")

    try:
        users_res = requests.get(f"{API_BASE}/line/users")
        users_res.raise_for_status()
        users = users_res.json()
        
        if users:
            # Prepare data for display
            user_data = {
                "User ID": [u["uid"] for u in users],
                "Display Name": [u["display_name"] for u in users]
            }
            st.dataframe(user_data, use_container_width=True)
        else:
            st.info("ยังไม่มีผู้ใช้ที่ลงทะเบียนผ่าน LINE")

    except requests.HTTPError as e:
        detail = e.response.json().get("detail", str(e))
        st.error(f"ไม่สามารถโหลดรายชื่อผู้ใช้ได้: {detail}")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")

# --- Tab 4: Active Groups ---
with tab4:
    st.markdown("### กลุ่มที่บอทเป็นสมาชิกอยู่")
    st.markdown("รายชื่อกลุ่มทั้งหมดที่บอทเป็นสมาชิกอยู่ ณ ปัจจุบัน")

    try:
        groups_res = requests.get(f"{API_BASE}/line/groups")
        groups_res.raise_for_status()
        groups = groups_res.json()
        
        if groups:
            # Prepare data for display
            group_data = {
                "Group ID": [g["group_id"] for g in groups],
                "Group Name": [g["group_name"] for g in groups]
            }
            st.dataframe(group_data, use_container_width=True)
        else:
            st.info("บอทไม่ได้อยู่ในกลุ่มใดๆ")

    except requests.HTTPError as e:
        detail = e.response.json().get("detail", str(e))
        st.error(f"ไม่สามารถโหลดรายชื่อกลุ่มได้: {detail}")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")

