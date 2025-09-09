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

# --- Fetch channels for dropdown ---
try:
    channels_res = requests.get(f"{API_BASE}/line/channels")
    channels_res.raise_for_status()
    channels = channels_res.json()
    channel_map = {ch['name']: ch['id'] for ch in channels}
except Exception as e:
    st.error(f"ไม่สามารถโหลดรายชื่อช่องทางได้: {e}")
    channels = []
    channel_map = {}

# Create tabs
tab1, tab2 = st.tabs(["Send Message", "Channel Info"])

# --- Tab 1: Send Message ---
with tab1:
    st.markdown("### ส่งข้อความ")

    if not channels:
        st.warning("ยังไม่มีการตั้งค่าช่องทางสำหรับส่งข้อความ กรุณาเพิ่มช่องทางก่อนในแท็บ 'Channel Info'")
    else:
        selected_channel_name = st.selectbox("เลือกช่องทางที่จะใช้ส่ง", options=list(channel_map.keys()), key="send_msg_channel")
        selected_channel_id = channel_map.get(selected_channel_name)

        # Fetch registered users for the selected channel
        try:
            params = {"channel_id": selected_channel_id} if selected_channel_id else {}
            all_users_res = requests.get(f"{API_BASE}/line/users", params=params)
            all_users_res.raise_for_status()
            all_users = all_users_res.json()
            all_user_map = {u['display_name']: u['uid'] for u in all_users}
        except Exception as e:
            st.warning(f"ไม่สามารถโหลดรายชื่อผู้ใช้ทั้งหมดได้: {e}")
            all_user_map = {}

        # Fetch active groups for the selected channel
        try:
            params = {"channel_id": selected_channel_id} if selected_channel_id else {}
            all_groups_res = requests.get(f"{API_BASE}/line/groups", params=params)
            all_groups_res.raise_for_status()
            all_groups = all_groups_res.json()
            all_group_map = {g['group_name']: g['group_id'] for g in all_groups}
        except Exception as e:
            st.warning(f"ไม่สามารถโหลดรายชื่อกลุ่มทั้งหมดได้: {e}")
            all_group_map = {}

        selected_users = st.multiselect(
            "เลือกผู้ใช้ที่จะส่งข้อความถึง (เลือกได้หลายคน)",
            options=list(all_user_map.keys()),
            placeholder="เลือกผู้ใช้..."
        )
        selected_groups = st.multiselect(
            "เลือกกลุ่มที่จะส่งข้อความถึง (เลือกได้หลายกลุ่ม)",
            options=list(all_group_map.keys()),
            placeholder="เลือกกลุ่ม..."
        )
        
        message_text = st.text_area("ข้อความที่จะส่ง:", height=150, placeholder="พิมพ์ข้อความที่นี่...")
        
        if st.button("🚀 ส่งข้อความ", type="primary"):
            if not message_text.strip():
                st.error("กรุณาพิมพ์ข้อความที่จะส่ง")
            elif not selected_channel_id:
                st.error("กรุณาเลือกช่องทางที่จะใช้ส่ง")
            elif not selected_users and not selected_groups:
                st.error("กรุณาเลือกผู้ใช้หรือกลุ่มอย่างน้อยหนึ่งรายการ")
            else:
                recipient_uids = [all_user_map.get(name) for name in selected_users]
                recipient_gids = [all_group_map.get(name) for name in selected_groups]

                # Filter out any potential None values if names somehow don't match
                recipient_uids = [uid for uid in recipient_uids if uid]
                recipient_gids = [gid for gid in recipient_gids if gid]

                with st.spinner("กำลังส่งข้อความ..."):
                    try:
                        payload = {
                            "channel_id": selected_channel_id,
                            "message": message_text.strip(),
                            "recipient_uids": recipient_uids,
                            "recipient_gids": recipient_gids
                        }
                        send_res = requests.post(f"{API_BASE}/line/send_message", json=payload)
                        send_res.raise_for_status()
                        sent_count = send_res.json().get("sent_count", 0)
                        st.success(f"ส่งข้อความสำเร็จ ({sent_count} получатели)")
                        st.balloons()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"ส่งข้อความไม่สำเร็จ: {detail}")
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")

# --- Tab 2: Channel Info ---
with tab2:
    st.markdown("### Channel Info")
    
    with st.expander("Manage Sender Accounts (LINE Channels)"):
        # Display channels with delete buttons
        if channels:
            for ch in channels:
                c1, c2, c3 = st.columns([2, 4, 1])
                c1.text(ch['name'])
                c2.text(censor_token(ch['token']))
                if c3.button("🗑️ Delete", key=f"del_channel_{ch['id']}"):
                    try:
                        del_res = requests.delete(f"{API_BASE}/line/channels/{ch['id']}")
                        del_res.raise_for_status()
                        st.toast("Channel deleted successfully", icon="✅")
                        st.rerun()
                    except requests.HTTPError as e:
                        detail = e.response.json().get("detail", str(e))
                        st.error(f"Failed to delete: {detail}")
        else:
            st.info("No channels have been set up for sending messages yet")

    st.divider()

    if st.button("➕ Add Line Channel"):
        add_channel_dialog()

    # Channel selector for filtering users and groups
    if channels:
        channel_names = ["All Channels"] + [ch['name'] for ch in channels]
        selected_channel_name = st.selectbox("Select a channel to view information", options=channel_names)

        selected_channel_id = None
        if selected_channel_name != "All Channels":
            selected_channel_id = next((ch['id'] for ch in channels if ch['name'] == selected_channel_name), None)
    else:
        selected_channel_id = None

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### All users registered via LINE")
        st.markdown("_A list of all users who have ever sent a message to the bot_")
        try:
            params = {"channel_id": selected_channel_id} if selected_channel_id else {}
            users_res = requests.get(f"{API_BASE}/line/users", params=params)
            users_res.raise_for_status()
            users = users_res.json()
            if users:
                user_data = {"User ID": [u["uid"] for u in users], "Display Name": [u["display_name"] for u in users]}
                st.dataframe(user_data, use_container_width=True)
            else:
                st.info("No users have registered via LINE yet")
        except requests.HTTPError as e:
            detail = e.response.json().get("detail", str(e))
            st.error(f"Could not load user list: {detail}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")

    with col2:
        st.markdown("### Groups the bot is a member of")
        st.markdown("_A list of all groups the bot is currently a member of_")
        try:
            params = {"channel_id": selected_channel_id} if selected_channel_id else {}
            groups_res = requests.get(f"{API_BASE}/line/groups", params=params)
            groups_res.raise_for_status()
            groups = groups_res.json()
            if groups:
                group_data = {"Group ID": [g["group_id"] for g in groups], "Group Name": [g["group_name"] for g in groups]}
                st.dataframe(group_data, use_container_width=True)
            else:
                st.info("The bot is not in any groups")
        except requests.HTTPError as e:
            detail = e.response.json().get("detail", str(e))
            st.error(f"Could not load group list: {detail}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")

