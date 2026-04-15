import streamlit as st
import pandas as pd
from server.admin_auth import get_all_users, upsert_user, toggle_user_active, delete_user, ROLE_DISPLAY, ROLE_HIERARCHY

st.title("👥 사용자 계정 관리")
st.markdown("관리자 콘솔에 접근할 수 있는 사용자 계정을 생성하고 권한을 부여합니다.  \n**최고관리자(superadmin)**만 접근할 수 있는 메뉴입니다.")

# 데이터 새로고침 함수
def load_users():
    return get_all_users()

users = load_users()

if not users:
    st.warning("사용자 정보를 불러올 수 없습니다. DB 연결 상태를 확인해주세요.")
    st.stop()

# ── 1. 현재 사용자 목록 표시 ──
st.subheader("📋 등록된 관리자 목록")
df = pd.DataFrame(users)

# 표시용 데이터 변환
display_df = df.copy()
display_df["role"] = display_df["role"].map(lambda r: ROLE_DISPLAY.get(r, r))
display_df["is_active"] = display_df["is_active"].map(lambda a: "활성" if a else "비활성")
display_df = display_df[["id", "username", "display_name", "role", "is_active", "created_at", "last_login"]]
display_df.columns = ["ID", "아이디", "표시 이름", "역할", "상태", "생성일", "최근 로그인"]

st.dataframe(display_df, use_container_width=True, hide_index=True)


st.divider()

# ── 2. 사용자 추가/수정 / 3. 상태 변경 및 삭제 ──
col1, col2 = st.columns(2)

with col1:
    st.subheader("➕ 사용자 추가 및 권한 수정")
    with st.form("upsert_user_form", clear_on_submit=True):
        st.markdown("기존 아이디 입력시 덮어씌워집니다 (비밀번호도 변경됨).")
        input_username = st.text_input("아이디 (필수)")
        input_display = st.text_input("표시 이름 (필수)")
        input_password = st.text_input("비밀번호 (필수)", type="password")
        input_role = st.selectbox("부여할 역할", options=["viewer", "admin", "superadmin"], format_func=lambda x: ROLE_DISPLAY.get(x, x), index=0)
        
        submit_btn = st.form_submit_button("저장하기", type="primary")
        if submit_btn:
            if not input_username or not input_display or not input_password:
                st.error("빈 칸을 모두 채워주세요.")
            else:
                success, msg = upsert_user(input_username, input_password, input_display, input_role)
                if success:
                    st.success(f"[{input_username}] 계정이 성공적으로 저장되었습니다.")
                    st.rerun()
                else:
                    st.error(f"저장 실패: {msg}")

with col2:
    st.subheader("🔒 상태 변경 및 삭제")
    
    # 활성/비활성 토글
    with st.form("toggle_active_form"):
        st.markdown("**계정 활성/비활성** (비활성화 시 로그인 불가)")
        toggle_username = st.selectbox("대상 아이디 선택", options=[u["username"] for u in users], key="toggle")
        current_active = next((u["is_active"] for u in users if u["username"] == toggle_username), True)
        new_status = st.radio("변경할 상태", ["활성", "비활성"], index=0 if current_active else 1)
        
        toggle_btn = st.form_submit_button("상태 변경 적용")
        if toggle_btn:
            # 상태 변경 로직
            to_bool = new_status == "활성"
            success, msg = toggle_user_active(toggle_username, to_bool)
            if success:
                st.success(f"[{toggle_username}] 상태를 '{new_status}'(으)로 변경했습니다.")
                st.rerun()
            else:
                st.error(f"변경 실패: {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 삭제
    with st.form("delete_user_form"):
        st.markdown("**계정 영구 삭제** (복구 불가)")
        del_username = st.selectbox("삭제할 아이디 선택", options=[u["username"] for u in users], key="delete")
        st.warning("경고: 삭제를 누르면 이 계정은 영구 삭제됩니다.")
        delete_btn = st.form_submit_button("영구 삭제")
        if delete_btn:
            if del_username == "acrcaimanager" or del_username == st.session_state["username"]:
                st.error("최고관리자 전용 계정이나 현재 접속중인 계정은 삭제할 수 없습니다.")
            else:
                success, msg = delete_user(del_username)
                if success:
                    st.success(f"[{del_username}] 계정이 삭제되었습니다.")
                    st.rerun()
                else:
                    st.error(f"삭제 실패: {msg}")
