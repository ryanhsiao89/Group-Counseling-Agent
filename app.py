import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import personas
import data_manager

# 初始化
data_manager.init_db()
st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")

# --- 側邊欄 ---
with st.sidebar:
    st.markdown("### 🎓 研究後台")
    if st.text_input("研究者密碼", type="password") == "phd2026":
        st.success("已解鎖")
        if st.button("📥 下載對話"):
            try:
                data_manager.export_chat_logs().to_excel("chat.xlsx", index=False)
                st.success("匯出 chat.xlsx")
            except: st.error("匯出失敗")

# --- 登入與設定 ---
if "current_session_id" not in st.session_state:
    st.title("🎭 團體諮商模擬系統")
    st.info("請設定本次的演練參數。")
    
    col1, col2 = st.columns(2)
    
    with col1:
        student_id = st.text_input("學號", placeholder="S112001")
        api_key_input = st.text_input("Google API Key", type="password")
        # 新增：角色選擇
        user_role = st.radio("👉 這次演練你想擔任什麼角色？", 
                             ["團體帶領者 (Leader)", "團體成員 (Member)"])
    
    with col2:
        st.markdown("### ⚙️ 劇本設定")
        group_type = st.selectbox("團體類型", ["大學生生涯探索", "人際關係成長", "情緒支持"])
        session_num = st.slider("第幾次團體？", 1, 10, 1)
        context_input = st.text_area("前情提要", value="成員間還不熟悉，氣氛有些拘謹。")

    if st.button("開始演練", type="primary"):
        if student_id and api_key_input:
            session_id = data_manager.start_session(student_id)
            
            st.session_state.current_session_id = session_id
            st.session_state.student_id = student_id
            st.session_state.api_key = api_key_input
            st.session_state.user_role = user_role # 存下使用者角色
            
            st.session_state.group_context = {
                "type": group_type, "session": session_num, "atmosphere": context_input
            }
            
            # --- 關鍵修改：根據角色生成不同的成員名單 ---
            if user_role == "團體帶領者 (Leader)":
                # 使用者是 Leader -> 生成 5 位混合成員 (不含 AI Leader)
                st.session_state.participants = personas.get_mixed_participants(count=5, include_leader=False)
                st.session_state.user_avatar = "🧑‍🏫"
                st.session_state.user_name = "Leader (You)"
            else:
                # 使用者是 Member -> 生成 4 位成員 + 1 位 AI Leader
                st.session_state.participants = personas.get_mixed_participants(count=5, include_leader=True)
                st.session_state.user_avatar = "🙋"
                st.session_state.user_name = "Member (You)"
            
            st.session_state.chat_history = []
            st.rerun()

else:
    # --- 聊天室 ---
    ctx = st.session_state.group_context
    role_display = "帶領者" if st.session_state.user_role == "團體帶領者 (Leader)" else "成員"
    
    st.subheader(f"💬 {ctx['type']} (第 {ctx['session']} 次) - 你的角色：{role_display}")
    
    # 顯示成員列表 (用 Columns 排列)
    cols = st.columns(len(st.session_state.participants))
    for idx, p in enumerate(st.session_state.participants):
        with cols[idx]:
            # 如果是 AI Leader，特別標註
            border = True if p['id'] == 'ai_leader' else False
            st.info(f"{p['avatar']} {p['name']}\n\n{p['type']}")

    if st.sidebar.button("🚪 登出"):
        data_manager.end_session(st.session_state.current_session_id)
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
    prompt_text = "請輸入帶領語句..." if st.session_state.user_role == "團體帶領者 (Leader)" else "請輸入發言..."
    if user_input := st.chat_input(prompt_text):
        
        # 1. 使用者發言
        st.chat_message("user", avatar=st.session_state.user_avatar).write(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, "User", user_input)

        # 2. AI 群體回應
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=st.session_state.api_key,
            temperature=0.7
        )
        
        # 為了避免 5 個 AI 同時回話太冗長，我們可以做一個簡單的過濾：
        # 如果是 Member 模式，AI Leader 幾乎每次都要講話來控場。
        # 其他成員則隨機發言，或者根據 Context 決定。
        # 但為了簡單起見，目前先讓所有人都"思考"要不要回話 (透過 Prompt 控制簡短)
        
        for participant in st.session_state.participants:
            # 如果使用者是 Member，且現在輪到 AI Leader，他應該要比較積極回應
            # 這裡簡化處理：所有 AI 都會收到訊息並產生回應
            
            with st.spinner(f"{participant['name']} ..."):
                context_prompt = f"""
                [CONTEXT]
                Type: {ctx['type']}, Session: {ctx['session']}
                Atmosphere: {ctx['atmosphere']}
                Your Role: {participant['system_prompt']}
                User's Role: {st.session_state.user_role}
                
                INSTRUCTION: 
                Respond naturally to the last message. 
                Keep it concise (1-3 sentences). 
                If you are a 'Quiet' member, you might just nod or say nothing (return empty string).
                If you are the AI Leader, facilitate the discussion.
                """
                
                messages = [
                    SystemMessage(content=context_prompt)
                ]
                
                # 載入歷史
                for history_msg in st.session_state.chat_history:
                    role = history_msg["role"]
                    content = history_msg["content"]
                    if role == "user":
                        messages.append(HumanMessage(content=f"{st.session_state.user_name}: {content}"))
                    else:
                        prefix = "You" if role == participant['name'] else role
                        messages.append(HumanMessage(content=f"{prefix}: {content}"))
                
                try:
                    response = llm.invoke(messages)
                    content = response.content
                    
                    # 只有當內容不為空時才顯示 (模擬沈默成員)
                    if len(content.strip()) > 2:
                        st.chat_message("assistant", avatar=participant['avatar']).write(f"**{participant['name']}:** {content}")
                        st.session_state.chat_history.append({"role": participant['name'], "content": content})
                        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, participant['name'], content)
                        
                except Exception as e:
                    pass