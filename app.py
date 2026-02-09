import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import personas
import data_manager

st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")

# --- 側邊欄 (已移除研究者後台) ---
with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統對話紀錄將自動存入雲端資料庫，作為教學與研究分析使用。")
    st.caption("請盡情演練，無需擔心紀錄遺失。")

# --- 登入與設定 ---
if "current_session_id" not in st.session_state:
    st.title("🎭 團體諮商模擬系統")
    st.markdown("##### 請輸入資訊以開始您的演練")
    
    col1, col2 = st.columns(2)
    
    with col1:
        student_id = st.text_input("學號 (Student ID)", placeholder="S112001")
        api_key_input = st.text_input("Google API Key", type="password")
        user_role = st.radio("👉 您的角色", 
                             ["團體帶領者 (Leader)", "團體成員 (Member)"])
    
    with col2:
        st.markdown("### ⚙️ 劇本設定")
        
        # 1. 擴充團體類型
        group_type_options = [
            "大學生生涯探索團體",
            "人際關係成長團體",
            "情緒支持團體",
            "壓力調適與自我照顧團體", 
            "憤怒情緒管理團體",       
            "哀傷與失落輔導團體",     
            "職場/學校溝通技巧團體",
            "其他 (請自訂)"
        ]
        
        selected_type = st.selectbox("團體類型", group_type_options)
        
        custom_type = ""
        if selected_type == "其他 (請自訂)":
            custom_type = st.text_input("請輸入自訂的團體名稱/性質")
            final_group_type = custom_type
        else:
            final_group_type = selected_type

        session_num = st.slider("現在是第幾次團體？", 1, 10, 1)
        
        context_input = st.text_area(
            "前情提要 / 團體氣氛 (Context)", 
            value="這是第一次團體，成員之間還不熟悉，氣氛有些拘謹。",
            placeholder="例如：上次團體發生了衝突，今天大家都很安靜..."
        )

    if st.button("開始演練", type="primary"):
        if student_id and api_key_input and final_group_type:
            # 啟動並寫入 Google Sheet
            session_id = data_manager.start_session(student_id, user_role, final_group_type, session_num)
            
            st.session_state.current_session_id = session_id
            st.session_state.student_id = student_id
            st.session_state.api_key = api_key_input
            st.session_state.user_role = user_role
            st.session_state.group_context = {
                "type": final_group_type, 
                "session": session_num, 
                "atmosphere": context_input
            }
            
            # 生成成員
            if user_role == "團體帶領者 (Leader)":
                st.session_state.participants = personas.get_mixed_participants(count=5, include_leader=False)
                st.session_state.user_avatar = "🧑‍🏫"
                st.session_state.user_name = "Leader"
            else:
                st.session_state.participants = personas.get_mixed_participants(count=5, include_leader=True)
                st.session_state.user_avatar = "🙋"
                st.session_state.user_name = "Member"
            
            st.session_state.chat_history = []
            st.rerun()
        else:
            st.warning("請完整輸入學號、API Key 與團體資訊")

else:
    # --- 聊天室 ---
    ctx = st.session_state.group_context
    st.subheader(f"💬 {ctx['type']} (第 {ctx['session']} 次)")
    
    cols = st.columns(len(st.session_state.participants))
    for idx, p in enumerate(st.session_state.participants):
        with cols[idx]:
            st.info(f"{p['avatar']} {p['name']}\n\n{p['type']}")

    if st.sidebar.button("🚪 結束/登出"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    # 顯示訊息
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {msg['content']}")
        else:
            member = next((p for p in st.session_state.participants if p['name'] == msg['role']), None)
            avatar = member['avatar'] if member else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{msg['role']}:** {msg['content']}")
        
    # 輸入框
    if user_input := st.chat_input("請輸入..."):
        # 1. 紀錄使用者發言
        st.chat_message("user", avatar=st.session_state.user_avatar).write(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, "User", user_input)

        # 2. AI 回應
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=st.session_state.api_key,
            temperature=0.7
        )
        
        for participant in st.session_state.participants:
            with st.spinner(f"{participant['name']} ..."):
                context_prompt = f"""
                [DYNAMIC CONTEXT]
                Group Type: {ctx['type']}
                Session Number: {ctx['session']}
                Atmosphere: {ctx['atmosphere']}
                Your Role: {participant['system_prompt']}
                User Role: {st.session_state.user_role}
                
                INSTRUCTION: 
                Respond naturally. If you are a quiet member, you can stay silent (return empty string).
                If you are the AI Leader, help facilitate.
                """
                
                messages = [SystemMessage(content=context_prompt)]
                for history_msg in st.session_state.chat_history:
                    role = history_msg["role"]
                    content = history_msg["content"]
                    if role == "user":
                        messages.append(HumanMessage(content=f"User: {content}"))
                    else:
                        prefix = "You" if role == participant['name'] else role
                        messages.append(HumanMessage(content=f"{prefix}: {content}"))
                
                try:
                    response = llm.invoke(messages)
                    content = response.content
                    if len(content.strip()) > 1:
                        st.chat_message("assistant", avatar=participant['avatar']).write(f"**{participant['name']}:** {content}")
                        st.session_state.chat_history.append({"role": participant['name'], "content": content})
                        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, participant['name'], content)
                except Exception:
                    pass