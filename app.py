import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import personas
import data_manager  # 匯入資料管家

# 1. 初始化資料庫 (如果不存在則建立)
data_manager.init_db()

st.set_page_config(page_title="AI 團體諮商研究版", page_icon="📝", layout="wide")

# --- 側邊欄：研究者控制台 (以密碼保護) ---
with st.sidebar:
    st.markdown("### 🎓 研究後台")
    admin_password = st.text_input("研究者密碼", type="password")
    
    if admin_password == "phd2026":  # 您設定的密碼
        st.success("身分驗證成功")
        
        # 下載質性文本
        if st.button("📥 下載：對話文本 (Excel)"):
            try:
                df_logs = data_manager.export_chat_logs()
                df_logs.to_excel("chat_transcripts.xlsx", index=False)
                st.success("已匯出 chat_transcripts.xlsx")
            except Exception as e:
                st.error(f"匯出失敗: {e}")
        
        # 下載量化統計
        if st.button("📊 下載：使用行為統計 (Excel)"):
            try:
                df_stats = data_manager.export_usage_stats()
                df_stats.to_excel("usage_stats.xlsx", index=False)
                st.success("已匯出 usage_stats.xlsx")
                st.dataframe(df_stats) # 預覽數據
            except Exception as e:
                st.error(f"匯出失敗: {e}")

# --- 登入畫面邏輯 ---
if "current_session_id" not in st.session_state:
    st.title("🎓 團體諮商帶領演練：登入")
    st.info("請輸入學號與 Google API Key 以開始實驗。")
    
    student_id = st.text_input("請輸入您的學號/編號 (Student ID)", placeholder="例如：S112001")
    api_key_input = st.text_input("請輸入 Google API Key", type="password")
    
    if st.button("開始演練"):
        if student_id and api_key_input:
            # 1. 記錄登入時間與 Session ID
            session_id = data_manager.start_session(student_id)
            
            # 2. 存入 Session State
            st.session_state.current_session_id = session_id
            st.session_state.student_id = student_id
            st.session_state.api_key = api_key_input
            # 隨機抽取 2 位成員
            st.session_state.participants = personas.get_random_participants(2)
            st.session_state.chat_history = []
            st.rerun() # 重新整理進入聊天室
        else:
            st.warning("請完整輸入學號與 API Key")

else:
    # --- 進入聊天室 (已登入狀態) ---
    st.title(f"💬 團體諮商室 (成員：{st.session_state.student_id})")
    
    # 顯示目前隨機抽到的成員
    cols = st.columns(len(st.session_state.participants))
    for idx, p in enumerate(st.session_state.participants):
        with cols[idx]:
            st.caption(f"成員: {p['avatar']} {p['name']} ({p['type']})")

    # 顯示結束按鈕
    if st.sidebar.button("🚪 結束本次練習 (登出)"):
        data_manager.end_session(st.session_state.current_session_id)
        # 清除狀態，回到登入畫面
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    # --- 顯示歷史訊息 ---
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="🧑‍🏫"):
                st.write(f"**Leader:** {msg['content']}")
        else:
            # 尋找對應的成員頭像
            member = next((p for p in st.session_state.participants if p['name'] == msg['role']), None)
            avatar = member['avatar'] if member else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{msg['role']}:** {msg['content']}")
        
    # --- 處理發言與紀錄 ---
    if user_input := st.chat_input("請輸入您的帶領語句..."):
        
        # 1. 顯示並儲存使用者發言 (UI & Session State)
        st.chat_message("user", avatar="🧑‍🏫").write(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # 【關鍵】紀錄學生的發言到資料庫
        data_manager.log_message(
            st.session_state.current_session_id, 
            st.session_state.student_id, 
            "Student_Leader", 
            user_input
        )

        # 2. AI 回應邏輯 (使用 Gemini 2.5 Flash)
        # 初始化 LLM
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=st.session_state.api_key,
            temperature=0.7
        )
        
        # 讓每位成員依序回應 (或可改為隨機一位)
        for participant in st.session_state.participants:
            with st.spinner(f"{participant['name']} 正在思考..."):
                
                # --- 建構 Prompt ---
                # 放入角色設定
                messages = [
                    SystemMessage(content=participant['system_prompt']),
                    SystemMessage(content="你是團體諮商的一員。請根據對話紀錄回應 Leader 或其他成員。保持你的角色設定。回應要簡短有力，像真人一樣。")
                ]
                
                # 放入歷史對話 (Context)
                for history_msg in st.session_state.chat_history:
                    role = history_msg["role"]
                    content = history_msg["content"]
                    
                    if role == "user":
                        messages.append(HumanMessage(content=f"Leader: {content}"))
                    else:
                        # 標記是自己說的還是別人說的
                        prefix = "You" if role == participant['name'] else role
                        messages.append(HumanMessage(content=f"{prefix}: {content}"))
                
                # --- 呼叫 AI ---
                try:
                    response = llm.invoke(messages)
                    response_content = response.content
                    
                    # 顯示在 UI
                    st.chat_message("assistant", avatar=participant['avatar']).write(f"**{participant['name']}:** {response_content}")
                    
                    # 存入 Session State
                    st.session_state.chat_history.append({"role": participant['name'], "content": response_content})
                    
                    # 【關鍵】紀錄 AI 成員的發言到資料庫
                    data_manager.log_message(
                        st.session_state.current_session_id, 
                        st.session_state.student_id, 
                        participant['name'], 
                        response_content
                    )
                except Exception as e:
                    st.error(f"AI 生成錯誤 (請檢查 API Key): {e}")