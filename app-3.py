import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import personas
import data_manager
import time
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os

st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")

# --- 🌟 本研究專屬白名單 (Whitelist) ---
WHITELIST = {
    'BB1092033': 'joychen0614@gmail.com',
    'BB1102066': 'bb1102066@hcu.edu.tw',
    'BB1122004': 'bb1122004@hcu.edu.tw',
    'BB1122014': 'chienchiye@gmail.com',
    'BB1122015': 'bb1122015@hcu.edu.tw',
    'BB1122017': 'bb1122017@hcu.edu.tw',
    'BB1122021': 'bb1122021@hcu.edu.tw',
    'BB1122022': 'bb1122022@hcu.edu.tw',
    'BB1122024': 'bb1122024@hcu.edu.tw',
    'BB1122025': 'jason745726@gmail.com',
    'BB1122026': '940104lin@gmail.com',
    'BB1122028': 'bb1122028@hcu.edu.tw',
    'BB1122032': 'a02577koy@gmail.com',
    'BB1122034': 'bb1122034@hcu.edu.tw',
    'BB1122040': 'bb1122040@hcu.edu.tw',
    'BB1122041': 'chenjay0116@gmail.com',
    'BB1122053': 'jasminehu0711@gmail.com',
    'BB1125025': 'bb1125025@hcu.edu.tw',
    'BB1125034': 'bb1125034@hcu.edu.tw',
    'TA1140202': 'ta1140202@hcu.edu.tw',
    'TA1140203': 'ta1140203@hcu.edu.tw',
    'KA1130107': 'si847452195@gmail.com',
    '112152516': 'ryanhsiao89@gmail.com',
    'HOPE HARN': 'hopehopejoy@gmail.com',
}

# --- 寄送 OTP 驗證信模組 ---
def send_otp_email(receiver_email, otp):
    """透過 Gmail 發送 6 位數驗證碼"""
    try:
        sender_email = st.secrets["email"]["sender_email"]
        app_password = st.secrets["email"]["app_password"]
        
        msg = MIMEText(f"您好：\n\n歡迎參與本研究並使用「團體諮商 AI 模擬演練系統」。\n\n您的本次登入驗證碼為：【 {otp} 】\n\n請將此驗證碼輸入系統以開始演練。\n若非您本人操作，請忽略此信件。", 'plain', 'utf-8')
        msg['Subject'] = "團體諮商 AI 模擬系統 - 登入驗證碼"
        msg['From'] = sender_email
        msg['To'] = receiver_email
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"寄信失敗: {e}")
        return False

# --- 初始化 Session State ---
if "otp_verified" not in st.session_state: st.session_state.otp_verified = False
if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
if "student_id" not in st.session_state: st.session_state.student_id = ""
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "api_keys" not in st.session_state: st.session_state.api_keys = []
if "current_key_index" not in st.session_state: st.session_state.current_key_index = 0

# --- 🧠 15 大諮商學派專屬 Prompt 設定庫 ---
APPROACH_PROMPTS = {
    "不指定（預設）": "",
    
    "「心理動力取向」精神分析取向": """
        [特別指示：這是一個「精神分析」取向的團體]
        若你是 AI 帶領者：請關注潛意識、防衛機制、移情與過去童年經驗。適時對成員的發言進行「詮釋（Interpretation）」，並探索行為背後的潛意識動機。
        若你是 AI 團體成員：請偶爾展現出抗拒（Resistance），或是將對權威/父母的情感投射（移情）到帶領者或其他成員身上，並自然分享夢境或童年回憶。
    """,
    "「心理動力取向」阿德勒取向": """
        [特別指示：這是一個「阿德勒學派」取向的團體]
        若你是 AI 帶領者：請營造充滿鼓勵的氛圍，適時引導成員探索「家庭星座（手足關係）」、「早期回憶」、「社會興趣」與「自卑與超越」的議題。
        若你是 AI 團體成員：請自然地分享你在人際關係中感到的氣餒（自卑感），或是想要討好別人、尋求關注的行為目的與生命風格。
    """,
    
    "「經驗與關係導向取向」存在主義取向": """
        [特別指示：這是一個「存在主義」取向的團體]
        若你是 AI 帶領者：請關注終極關懷議題（死亡、自由與責任、孤獨、無意義）。不提供廉價的安慰，而是陪伴成員面對存在的焦慮，鼓勵其真實生活並為自己的選擇負責。
        若你是 AI 團體成員：請表達存在性焦慮，例如對未來的迷惘、感覺生命沒有意義、或是害怕做出選擇後必須承擔的責任。
    """,
    "「經驗與關係導向取向」個人中心取向": """
        [特別指示：這是一個「個人中心治療」取向的團體]
        若你是 AI 帶領者：請展現高度的「真誠一致」、「無條件正向關懷」與「同理心」。絕不主動給予建議、分析或指導，僅專注於反映成員的情感，創造安全的氣氛讓成員自我實現。
        若你是 AI 團體成員：請自然地表達內心的感受、理想我與真實我的矛盾。當感受到帶領者或團體高度同理時，會展現出更深層、更真實的自我揭露。
    """,
    "「經驗與關係導向取向」完形治療": """
        [特別指示：這是一個「完形治療」取向的團體]
        若你是 AI 帶領者：請高度關注「此時此地（Here and Now）」，要求成員使用「我」的語言，適時點出成員的非語文行為，並引導成員覺察當下的身體感受或處理「未竟事宜」。
        若你是 AI 團體成員：請多用第一人稱表達當下的情緒與身體感受（如：我現在覺得胸口很緊）。自然地對帶領者的引導做出反應，不過度理性分析。
    """,
    "「經驗與關係導向取向」心理劇": """
        [特別指示：這是一個「心理劇」取向的團體]
        若你是 AI 帶領者：請化身為「導演」，鼓勵成員「不要只用說的，演出來」。引導使用角色扮演、替身、鏡照與角色交換等技術來重現生活情境。
        若你是 AI 團體成員：請展現出願意配合演出、嘗試扮演自己生活中重要他人（輔角）的意願，並在演練對話中釋放真實的情感（宣洩）。
    """,

    "「認知行為取向」行為治療法": """
        [特別指示：這是一個「行為治療」取向的團體]
        若你是 AI 帶領者：請關注可觀察的具體行為，強調設定明確目標、增強作用、楷模學習與行為演練。鼓勵成員在團體中進行社會技巧訓練並指派家庭作業。
        若你是 AI 團體成員：請具體描述自己想改變的問題行為（如：不敢拒絕別人），並願意在團體中進行角色扮演與行為演練。
    """,
    "「認知行為取向」認知治療法": """
        [特別指示：這是一個「Beck 認知治療」取向的團體]
        若你是 AI 帶領者：請協助成員指認「自動化思考」與「認知扭曲（如非黑即白、災難化、過度推論）」。運用「蘇格拉底式提問」與合作經驗主義，邀請團體一起尋找替代性思考。
        若你是 AI 團體成員：請在分享煩惱時，自然地展現出對自我、世界或未來的負向認知基模與悲觀想法，等待帶領者與你核對證據。
    """,
    "「認知行為取向」理情行為治療": """
        [特別指示：這是一個「Ellis 理情行為治療 (REBT)」取向的團體]
        若你是 AI 帶領者：請主動、具指導性地揪出成員的「非理性信念（如：絕對必須、應該、糟透了）」。運用 ABCDE 模式，直接且有力地「駁斥（Disputing）」這些非理性想法。
        若你是 AI 團體成員：請在發言中頻繁使用「我必須...」、「他應該...」、「這真是太糟糕了」等極端且僵化的語氣來表達煩惱。
    """,
    "「認知行為取向」現實治療": """
        [特別指示：這是一個「現實治療（選擇理論）」取向的團體]
        若你是 AI 帶領者：請聚焦於成員「現在的行為」而非過去。不接受藉口，運用 WDEP 系統（想要什麼、正在做什麼、評估行為是否有效、計畫），協助成員為自己的選擇負責。
        若你是 AI 團體成員：請抱怨外界對你的不公或別人的錯誤，等待帶領者將焦點拉回「你自己選擇了什麼行為」以及「這行為對你有幫助嗎」的評估上。
    """,

    "「後現代取向」焦點解決短期治療": """
        [特別指示：這是一個「焦點解決短期治療 (SFBT)」取向的團體]
        若你是 AI 帶領者：請完全不探究問題成因與過去病理。專注於尋找「例外經驗」、運用「奇蹟問句」、「量尺問句」與「應對問句」，並給予成員真誠的讚美與賦能。
        若你是 AI 團體成員：一開始可能專注於抱怨問題，但在帶領者引導下，會開始思考自己曾經成功解決問題的時刻，並願意給自己的狀態打分數。
    """,
    "「後現代取向」敘事治療": """
        [特別指示：這是一個「敘事治療」取向的團體]
        若你是 AI 帶領者：請運用「問題外部化（人不是問題，問題才是問題）」，探討主流論述的壓迫，並協助成員尋找生命中的「獨特結果（閃亮時刻）」，以重寫充滿力量的生命故事。
        若你是 AI 團體成員：請將困擾你的問題視為一個實體（例如：「『憂鬱』一直纏著我，讓我...」），並在引導下探索自己如何抵抗這個問題的經驗。
    """,
    "「後現代取向」女性主義治療": """
        [特別指示：這是一個「女性主義治療」取向的團體]
        若你是 AI 帶領者：請強調「個人即政治」，注重權力分析與性別角色社會化的影響。與成員建立平等的關係，致力於成員的增能（Empowerment）與去病理化。
        若你是 AI 團體成員：請分享在家庭、職場或社會期待中感受到的壓迫、角色衝突或權力不對等，尋求團體的看見與集體力量的支持。
    """,
    "「後現代取向」正向心理治療": """
        [特別指示：這是一個「正向心理治療」取向的團體]
        若你是 AI 帶領者：請將焦點從「修復缺陷」轉移到「建立優勢」。引導成員探索自身的品格優勢、培養感恩之心、品味美好經驗，並促進 PERMA（正向情緒、全心投入、正向人際、生命意義、成就感）的發展。
        若你是 AI 團體成員：請在團體中分享生活中微小但美好的事物、個人的成功經驗或優勢，並在帶領者的引導下，展現出對未來抱持希望與感恩的態度。
    """
}

# --- 側邊欄 (基本說明) ---
with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統對話紀錄將自動存入雲端資料庫，作為教學與研究分析使用。")
    st.caption("請盡情演練，無需擔心紀錄遺失。")

# --- 階段 1：登入與雙重驗證 (OTP) ---
if not st.session_state.otp_verified:
    st.title("🛡️ 團體諮商 AI 模擬系統")
    st.info("本系統為專屬演練平台。為確保研究資料正確性，請先進行身分驗證。")
    
    st.markdown("### 🧑‍🤝‍🧑 步驟一：輸入學號或訪客碼")
    # ⏬ 更新介面提示詞，引導訪客輸入 GUEST
    student_id_input = st.text_input("請輸入您的學號/ID（研討會訪客請輸入 GUEST）：", placeholder="例如：BB1112067 或 GUEST")
    
    # ⏬ 將按鈕文字修改得更通用
    if st.button("🚀 登入 / 發送驗證碼"):
        if not student_id_input.strip():
            st.error("❌ 欄位不能為空！")
        else:
            student_id_clean = student_id_input.strip().upper() 
            
            # ⏬ 新增：訪客專屬免驗證一鍵通關通道
            if student_id_clean == "GUEST":
                st.session_state.otp_verified = True
                st.session_state.student_id = "GUEST"
                st.rerun()
                
            # 原本的白名單與 OTP 驗證邏輯
            else:
                if student_id_input.strip() in WHITELIST:
                    student_id_clean = student_id_input.strip()
                    
                if student_id_clean not in WHITELIST:
                    st.error("❌ 查無此學號/ID，請確認您是否具備本研究之參與資格。")
                else:
                    target_email = WHITELIST[student_id_clean]
                    masked_email = target_email[:4] + "****" + target_email[target_email.find("@"):]
                    
                    with st.spinner("正在發送驗證信，請稍候..."):
                        otp = str(random.randint(100000, 999999))
                        if send_otp_email(target_email, otp):
                            st.session_state.generated_otp = otp
                            st.session_state.student_id = student_id_clean
                            st.success(f"✅ 驗證碼已發送至您的專屬信箱 ({masked_email})！請檢查收件匣（若無請檢查垃圾郵件）。")
                        else:
                            st.error("❌ 寄信失敗，請向研究者確認系統後台信箱設定。")
    
    if st.session_state.generated_otp:
        st.markdown("### 🔐 步驟二：輸入驗證碼")
        user_otp = st.text_input("請輸入您信箱收到的 6 位數驗證碼：", type="password")
        if st.button("🚀 驗證並前往劇本設定"):
            if user_otp == st.session_state.generated_otp:
                st.session_state.otp_verified = True
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")

# --- 階段 2：劇本與參數設定 ---
elif "current_session_id" not in st.session_state:
    st.title("🎭 團體諮商模擬系統")
    st.markdown(f"##### 👤 歡迎，**{st.session_state.student_id}**！請完成演練設定")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🔑 系統設定")
        api_key_input = st.text_input("Google API Key (若有多把請用半形逗號 , 分隔)", type="password", placeholder="例如: AIzaSy..., AIzaSy..., AIzaSy...")
        user_role = st.radio("👉 您的角色", 
                             ["團體帶領者 (Leader)", "團體成員 (Member)"])
    
    with col2:
        st.markdown("### ⚙️ 劇本設定")
        
        group_type_options = [
            "大學生生涯探索團體", "人際關係成長團體", "情緒支持團體",
            "壓力調適與自我照顧團體", "憤怒情緒管理團體", "哀傷與失落輔導團體",     
            "職場/學校溝通技巧團體", "其他 (請自訂)"
        ]
        
        selected_type = st.selectbox("團體類型", group_type_options)
        
        custom_type = ""
        if selected_type == "其他 (請自訂)":
            custom_type = st.text_input("請輸入自訂的團體名稱/性質")
            final_group_type = custom_type
        else:
            final_group_type = selected_type

        selected_approach = st.selectbox("🧠 理論學派取向 (可選)", list(APPROACH_PROMPTS.keys()))

        session_num = st.slider("現在是第幾次團體？", 1, 10, 1)
        
        context_input = st.text_area(
            "前情提要 / 團體氣氛 (Context) 🎲", 
            value="",
            placeholder="請輸入情境。若留白，系統將自動隨機抽取一個溫和安全的狀況讓您練習！"
        )

    if st.button("開始演練", type="primary"):
        if api_key_input and final_group_type:
            
            parsed_keys = [k.strip() for k in api_key_input.split(",") if k.strip()]
            if not parsed_keys:
                st.warning("請至少輸入一把有效的 API Key！")
                st.stop()
            
            st.session_state.api_keys = parsed_keys
            st.session_state.current_key_index = 0
            
            if context_input.strip() == "":
                random_contexts = [
                    "【溫和破冰】這是第一次團體，成員們態度都很友善，但稍微有些害羞。大家面帶微笑看著帶領者，等待您給予明確的指示或有趣的破冰小活動。",
                    "【建立共鳴】剛剛有成員提到最近對於『未來發展』和『課業』感到一點點迷惘，其他幾個人聽了頻頻點頭。這是一個建立『普遍性 (Universality)』，讓大家知道彼此都有同感的好時機。",
                    "【正向支持】目前氣氛很溫暖。有成員主動分享了最近生活中一件微小但開心的事情（例如發掘了自己的某個小優勢或興趣），非常適合帶領者與其他成員練習給予肯定與支持。",
                    "【目標探索】成員們對於『團體諮商』感到好奇，雖然不太確定具體要怎麼運作，但大家展現出高度的參與意願，很適合在這裡一起討論並建立團體的共同目標。",
                    "【溫和沉默】大家目前情緒很平穩，只是靜靜地坐著。氣氛並不緊張或抗拒，只是單純不知道該說什麼。這時只要帶領者拋出一個簡單、低威脅性的問題（例如：今天出門前心情怎麼樣？），大家就很願意回答。"
                ]
                base_context = random.choice(random_contexts)
            else:
                base_context = context_input

            final_context = base_context + "\n" + APPROACH_PROMPTS[selected_approach]

            session_id = data_manager.start_session(st.session_state.student_id, user_role, final_group_type, session_num)
            
            st.session_state.current_session_id = session_id
            st.session_state.user_role = user_role
            st.session_state.group_context = {
                "type": final_group_type, 
                "session": session_num, 
                "atmosphere": final_context,
                "approach": selected_approach 
            }
            
            # 四選三出場機制
            if user_role == "團體帶領者 (Leader)":
                full_pool = personas.get_mixed_participants(count=5, include_leader=False)
                members_only = [p for p in full_pool if "Leader" not in p['name']]
                st.session_state.participants = random.sample(members_only, min(3, len(members_only)))
                
                st.session_state.user_avatar = "🧑‍🏫"
                st.session_state.user_name = "Leader"
                st.session_state.chat_history = [] 
            else:
                full_pool = personas.get_mixed_participants(count=5, include_leader=True)
                ai_leader = [p for p in full_pool if "Leader" in p['name']]
                members_only = [p for p in full_pool if "Leader" not in p['name']]
                
                selected_members = random.sample(members_only, min(3, len(members_only)))
                st.session_state.participants = ai_leader + selected_members
                
                st.session_state.user_avatar = "🙋"
                st.session_state.user_name = "Member"
                
                welcome_msg = f"大家好，歡迎大家來到這次的「{final_group_type}」。今天是我們的第 {session_num} 次聚會，有人想先分享一下最近的心情，或是帶著什麼期待來嗎？"
                st.session_state.chat_history = [{"role": "Dr. AI (Leader)", "content": welcome_msg}]
                data_manager.log_message(session_id, st.session_state.student_id, "Dr. AI (Leader)", welcome_msg)
            
            st.rerun()
        else:
            st.warning("請輸入 API Key 並確認團體資訊")

# --- 階段 3：聊天室 ---
else:
    ctx = st.session_state.group_context
    st.subheader(f"💬 {ctx['type']} (第 {ctx['session']} 次)")
    
    approach_display = f" | 🧠 學派取向：{ctx['approach']}" if ctx['approach'] != "不指定（預設）" else ""
    st.success(f"🎬 **當前情境設定：** {ctx['atmosphere'].split('[特別指示')[0].strip()}{approach_display}")
    
    cols = st.columns(len(st.session_state.participants))
    for idx, p in enumerate(st.session_state.participants):
        with cols[idx]:
            st.info(f"{p['avatar']} {p['name']}\n\n{p['type']}")

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📝 演練結束區")
        
        transcript = f"【團體諮商模擬演練逐字稿】\n學號：{st.session_state.student_id}\n匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n學派取向：{ctx['approach']}\n\n"
        for msg in st.session_state.chat_history:
            transcript += f"{msg['role']}： {msg['content']}\n\n"
            
        st.download_button(
            label="📥 1. 先下載本次逐字稿",
            data=transcript.encode('utf-8-sig'), 
            file_name=f"GroupLog_{st.session_state.student_id}_{datetime.now().strftime('%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            type="primary"
        )
        
        st.warning("⚠️ 離開前請務必確認已下載逐字稿。")
        
        if st.button("🚪 2. 結束並登出系統", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {msg['content']}")
        else:
            member = next((p for p in st.session_state.participants if p['name'] == msg['role']), None)
            avatar = member['avatar'] if member else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{msg['role']}:** {msg['content']}")
        
    if user_input := st.chat_input("請輸入..."):
        st.chat_message("user", avatar=st.session_state.user_avatar).write(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, "User", user_input)
        
        error_shown = False
        
        active_speakers = []
        for p in st.session_state.participants:
            if "Leader" in p['name']:
                if random.random() < 0.80:
                    active_speakers.append(p)
            else:
                if random.random() < 0.40:
                    active_speakers.append(p)
                    
        if not active_speakers:
            active_speakers = [random.choice(st.session_state.participants)]
            
        random.shuffle(active_speakers)
        
        for participant in active_speakers:
            with st.spinner(f"{participant['name']} 思考中..."):
                
                success = False
                while not success and st.session_state.current_key_index < len(st.session_state.api_keys):
                    
                    context_prompt = f"""
                    [DYNAMIC CONTEXT]
                    Group Type: {ctx['type']}
                    Session Number: {ctx['session']}
                    Atmosphere: {ctx['atmosphere']}
                    Your Role: {participant['system_prompt']}
                    User Role: {st.session_state.user_role}
                    
                    INSTRUCTION: 
                    Respond naturally according to your persona.
                    """
                    
                    history_text = ""
                    for history_msg in st.session_state.chat_history:
                        role = history_msg["role"]
                        content = history_msg["content"]
                        if role == "user":
                            history_text += f"User: {content}\n"
                        else:
                            prefix = "You" if role == participant['name'] else role
                            history_text += f"{prefix}: {content}\n"
                            
                    messages = [
                        SystemMessage(content=context_prompt),
                        HumanMessage(content=f"[Conversation Transcript]\n{history_text}\n\n[Instruction]\nWhat do you (as {participant['name']}) say next? Please provide your direct speech only.")
                    ]

                    current_key = st.session_state.api_keys[st.session_state.current_key_index]
                    
                    os.environ["GOOGLE_API_KEY"] = current_key
                    
                    llm = ChatGoogleGenerativeAI(
                        model="gemini-2.5-flash", 
                        google_api_key=current_key,
                        temperature=0
                    )
                    
                    try:
                        response = llm.invoke(messages)
                        content = response.content
                        if len(content.strip()) > 1:
                            st.chat_message("assistant", avatar=participant['avatar']).write(f"**{participant['name']}:** {content}")
                            st.session_state.chat_history.append({"role": participant['name'], "content": content})
                            data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, participant['name'], content)
                        
                        time.sleep(2.5)
                        success = True 
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                            if st.session_state.current_key_index < len(st.session_state.api_keys) - 1:
                                st.session_state.current_key_index += 1
                                st.toast(f"🔄 第 {st.session_state.current_key_index} 把 API Key 額度用盡，已自動切換備用 Key！", icon="🔋")
                                time.sleep(1)
                                continue 
                            else:
                                if not error_shown:
                                    st.error("❌ 您輸入的所有 API Key 額度皆已用盡！請稍等幾分鐘後再試，或更換新的 API Key。")
                                    error_shown = True
                                break 
                        else:
                            st.error(f"⚠️ 發生未知錯誤：{e}")
                            break
