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


st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")


WHITELIST = {
    "BB1092033": "joychen0614@gmail.com",
    "BB1102066": "bb1102066@hcu.edu.tw",
    "BB1122004": "bb1122004@hcu.edu.tw",
    "BB1122014": "chienchiye@gmail.com",
    "BB1122015": "bb1122015@hcu.edu.tw",
    "BB1122017": "bb1122017@hcu.edu.tw",
    "BB1122021": "bb1122021@hcu.edu.tw",
    "BB1122022": "bb1122022@hcu.edu.tw",
    "BB1122024": "bb1122024@hcu.edu.tw",
    "BB1122025": "jason745726@gmail.com",
    "BB1122026": "940104lin@gmail.com",
    "BB1122028": "bb1122028@hcu.edu.tw",
    "BB1122032": "a02577koy@gmail.com",
    "BB1122034": "bb1122034@hcu.edu.tw",
    "BB1122040": "bb1122040@hcu.edu.tw",
    "BB1122041": "chenjay0116@gmail.com",
    "BB1122053": "jasminehu0711@gmail.com",
    "BB1125025": "bb1125025@hcu.edu.tw",
    "BB1125034": "bb1125034@hcu.edu.tw",
    "TA1140202": "ta1140202@hcu.edu.tw",
    "TA1140203": "ta1140203@hcu.edu.tw",
    "KA1130107": "si847452195@gmail.com",
    "112152516": "ryanhsiao89@gmail.com",
    "HOPE HARN": "hopehopejoy@gmail.com",
}


DEFAULT_SESSION_STATE = {
    "otp_verified": False,
    "generated_otp": None,
    "student_id": "",
    "chat_history": [],
    "api_keys": [],
    "current_key_index": 0,
    "current_session_id": None,
    "participants": [],
    "user_role": "",
    "user_avatar": "🙋",
    "user_name": "User",
    "group_context": None,
    "previous_transcript_text": "",
    "continuation_mode": "僅供 AI 參考",
}


def init_session_state():
    for key, value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, list) else value


init_session_state()


def safe_start_session(student_id, user_role, group_type, session_num):
    try:
        return data_manager.start_session(student_id, user_role, group_type, session_num)
    except Exception as e:
        st.warning(f"⚠️ 雲端紀錄建立失敗，本次仍可演練，但可能無法自動保存。錯誤：{e}")
        return f"local_{student_id}_{int(time.time())}"


def safe_log_message(session_id, student_id, role, content):
    try:
        data_manager.log_message(session_id, student_id, role, content)
    except Exception as e:
        st.toast("⚠️ 雲端紀錄暫時失敗，但畫面中的對話仍會保留。", icon="📝")
        print(f"log_message failed: {e}")


def send_otp_email(receiver_email, otp):
    try:
        email_config = st.secrets.get("email", {})
        sender_email = email_config.get("sender_email")
        app_password = email_config.get("app_password")

        if not sender_email or not app_password:
            st.error("❌ 系統信箱尚未設定，請檢查 Streamlit secrets。")
            return False

        body = (
            "您好：\n\n"
            "歡迎參與本研究並使用「團體諮商 AI 模擬演練系統」。\n\n"
            f"您的本次登入驗證碼為：【 {otp} 】\n\n"
            "請將此驗證碼輸入系統以開始演練。\n"
            "若非您本人操作，請忽略此信件。"
        )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "團體諮商 AI 模擬系統 - 登入驗證碼"
        msg["From"] = sender_email
        msg["To"] = receiver_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)

        return True

    except smtplib.SMTPAuthenticationError:
        st.error("❌ 信箱驗證失敗，請確認 Gmail App Password 是否正確。")
        return False
    except Exception as e:
        st.error(f"❌ 驗證信寄送失敗：{e}")
        return False


def is_quota_error(error):
    error_msg = str(error).lower()
    quota_keywords = ["429", "quota", "exhausted", "rate limit", "resource exhausted"]
    return any(keyword in error_msg for keyword in quota_keywords)


def normalize_llm_content(response):
    content = getattr(response, "content", "")

    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )

    return str(content).strip()


def generate_ai_reply(messages):
    last_error = None

    while st.session_state.current_key_index < len(st.session_state.api_keys):
        current_key = st.session_state.api_keys[st.session_state.current_key_index]

        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=current_key,
                temperature=0.4,
                timeout=30,
                max_retries=1,
            )

            response = llm.invoke(messages)
            content = normalize_llm_content(response)

            if not content:
                raise ValueError("AI 回覆為空，系統將略過本次回覆。")

            return content

        except Exception as e:
            last_error = e

            if is_quota_error(e):
                if st.session_state.current_key_index < len(st.session_state.api_keys) - 1:
                    st.session_state.current_key_index += 1
                    st.toast(
                        f"🔄 API Key 額度用盡，已切換到第 {st.session_state.current_key_index + 1} 把 Key。",
                        icon="🔋",
                    )
                    continue

                raise RuntimeError("所有 API Key 額度皆已用盡，請稍後再試或更換 Key。")

            raise RuntimeError(f"AI 生成失敗：{e}")

    raise RuntimeError(f"AI 生成失敗：{last_error}")


def read_uploaded_text(uploaded_file):
    if uploaded_file is None:
        return ""

    raw_bytes = uploaded_file.read()

    for encoding in ["utf-8-sig", "utf-8", "big5", "cp950"]:
        try:
            return raw_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue

    return raw_bytes.decode("utf-8", errors="ignore").strip()


def normalize_role_name(role):
    role = role.strip()

    user_aliases = ["User", "user", "使用者", "學生", "Leader", "Member", "團體帶領者", "團體成員"]

    if role in user_aliases:
        return "user"

    return role


def parse_transcript_to_history(transcript_text, max_messages=60):
    """
    解析格式：
    角色： 內容
    角色: 內容

    若某一行沒有角色標記，會接在上一則訊息後面。
    """
    if not transcript_text:
        return []

    parsed_messages = []
    current_role = None
    current_content = []

    skip_prefixes = [
        "【團體諮商模擬演練逐字稿】",
        "學號：",
        "學號:",
        "匯出時間：",
        "匯出時間:",
        "學派取向：",
        "學派取向:",
    ]

    def flush_message():
        if current_role and current_content:
            content = "\n".join(current_content).strip()
            if content:
                parsed_messages.append({
                    "role": normalize_role_name(current_role),
                    "content": content,
                })

    for raw_line in transcript_text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue

        split_index = -1

        for symbol in ["：", ":"]:
            index = line.find(symbol)
            if 0 < index <= 30:
                split_index = index
                break

        if split_index > 0:
            flush_message()
            current_role = line[:split_index].strip()
            current_content = [line[split_index + 1:].strip()]
        else:
            if current_role:
                current_content.append(line)

    flush_message()

    return parsed_messages[-max_messages:]


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
若你是 AI 團體成員：請多用第一人稱表達當下的情緒與身體感受。自然地對帶領者的引導做出反應，不過度理性分析。
""",

    "「經驗與關係導向取向」心理劇": """
[特別指示：這是一個「心理劇」取向的團體]
若你是 AI 帶領者：請化身為「導演」，鼓勵成員「不要只用說的，演出來」。引導使用角色扮演、替身、鏡照與角色交換等技術來重現生活情境。
若你是 AI 團體成員：請展現出願意配合演出、嘗試扮演自己生活中重要他人的意願，並在演練對話中釋放真實的情感。
""",

    "「認知行為取向」行為治療法": """
[特別指示：這是一個「行為治療」取向的團體]
若你是 AI 帶領者：請關注可觀察的具體行為，強調設定明確目標、增強作用、楷模學習與行為演練。鼓勵成員在團體中進行社會技巧訓練並指派家庭作業。
若你是 AI 團體成員：請具體描述自己想改變的問題行為，並願意在團體中進行角色扮演與行為演練。
""",

    "「認知行為取向」認知治療法": """
[特別指示：這是一個「Beck 認知治療」取向的團體]
若你是 AI 帶領者：請協助成員指認「自動化思考」與「認知扭曲」。運用「蘇格拉底式提問」與合作經驗主義，邀請團體一起尋找替代性思考。
若你是 AI 團體成員：請在分享煩惱時，自然地展現出負向認知基模與悲觀想法，等待帶領者與你核對證據。
""",

    "「認知行為取向」理情行為治療": """
[特別指示：這是一個「Ellis 理情行為治療 (REBT)」取向的團體]
若你是 AI 帶領者：請主動、具指導性地揪出成員的「非理性信念」。運用 ABCDE 模式，直接且有力地「駁斥」這些非理性想法。
若你是 AI 團體成員：請在發言中使用「我必須」、「他應該」、「這真是太糟糕了」等較僵化的語氣來表達煩惱。
""",

    "「認知行為取向」現實治療": """
[特別指示：這是一個「現實治療（選擇理論）」取向的團體]
若你是 AI 帶領者：請聚焦於成員「現在的行為」而非過去。不接受藉口，運用 WDEP 系統協助成員為自己的選擇負責。
若你是 AI 團體成員：請抱怨外界對你的不公或別人的錯誤，等待帶領者將焦點拉回「你自己選擇了什麼行為」。
""",

    "「後現代取向」焦點解決短期治療": """
[特別指示：這是一個「焦點解決短期治療 (SFBT)」取向的團體]
若你是 AI 帶領者：請不探究問題成因與過去病理。專注於尋找「例外經驗」、運用「奇蹟問句」、「量尺問句」與「應對問句」，並給予成員真誠的讚美與賦能。
若你是 AI 團體成員：一開始可能專注於抱怨問題，但在帶領者引導下，會開始思考自己曾經成功解決問題的時刻。
""",

    "「後現代取向」敘事治療": """
[特別指示：這是一個「敘事治療」取向的團體]
若你是 AI 帶領者：請運用「問題外部化」，探討主流論述的壓迫，並協助成員尋找生命中的「獨特結果」，以重寫充滿力量的生命故事。
若你是 AI 團體成員：請將困擾你的問題視為一個實體，並在引導下探索自己如何抵抗這個問題的經驗。
""",

    "「後現代取向」女性主義治療": """
[特別指示：這是一個「女性主義治療」取向的團體]
若你是 AI 帶領者：請強調「個人即政治」，注重權力分析與性別角色社會化的影響。與成員建立平等的關係，致力於成員的增能與去病理化。
若你是 AI 團體成員：請分享在家庭、職場或社會期待中感受到的壓迫、角色衝突或權力不對等。
""",

    "「後現代取向」正向心理治療": """
[特別指示：這是一個「正向心理治療」取向的團體]
若你是 AI 帶領者：請將焦點從「修復缺陷」轉移到「建立優勢」。引導成員探索自身的品格優勢、培養感恩之心，並促進 PERMA 的發展。
若你是 AI 團體成員：請分享生活中微小但美好的事物、個人的成功經驗或優勢。
""",
}


with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統對話紀錄將自動存入雲端資料庫，作為教學與研究分析使用。")
    st.caption("若雲端紀錄暫時失敗，畫面中的逐字稿仍可下載。")


if not st.session_state.otp_verified:
    st.title("🛡️ 團體諮商 AI 模擬系統")
    st.info("本系統為專屬演練平台。為確保研究資料正確性，請先進行身分驗證。")

    st.markdown("### 🧑‍🤝‍🧑 步驟一：輸入學號或訪客碼")
    student_id_input = st.text_input(
        "請輸入您的學號/ID（研討會訪客請輸入 GUEST）：",
        placeholder="例如：BB1112067 或 GUEST",
    )

    if st.button("🚀 登入 / 發送驗證碼"):
        student_id_clean = student_id_input.strip().upper()

        if not student_id_clean:
            st.error("❌ 欄位不能為空！")

        elif student_id_clean == "GUEST":
            st.session_state.otp_verified = True
            st.session_state.student_id = "GUEST"
            st.rerun()

        elif student_id_clean not in WHITELIST:
            st.error("❌ 查無此學號/ID，請確認您是否具備本研究之參與資格。")

        else:
            target_email = WHITELIST[student_id_clean]
            at_index = target_email.find("@")
            masked_email = target_email[:4] + "****" + target_email[at_index:]

            with st.spinner("正在發送驗證信，請稍候..."):
                otp = str(random.randint(100000, 999999))

                if send_otp_email(target_email, otp):
                    st.session_state.generated_otp = otp
                    st.session_state.student_id = student_id_clean
                    st.success(f"✅ 驗證碼已發送至您的專屬信箱 ({masked_email})！請檢查收件匣或垃圾郵件。")
                else:
                    st.error("❌ 寄信失敗，請向研究者確認系統後台信箱設定。")

    if st.session_state.generated_otp:
        st.markdown("### 🔐 步驟二：輸入驗證碼")
        user_otp = st.text_input("請輸入您信箱收到的 6 位數驗證碼：", type="password")

        if st.button("🚀 驗證並前往劇本設定"):
            if user_otp.strip() == st.session_state.generated_otp:
                st.session_state.otp_verified = True
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")


elif not st.session_state.current_session_id:
    st.title("🎭 團體諮商模擬系統")
    st.markdown(f"##### 👤 歡迎，**{st.session_state.student_id}**！請完成演練設定")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🔑 系統設定")
        api_key_input = st.text_input(
            "Google API Key（若有多把請用半形逗號 , 分隔）",
            type="password",
            placeholder="例如：AIzaSy..., AIzaSy...",
        )

        user_role = st.radio(
            "👉 您的角色",
            ["團體帶領者 (Leader)", "團體成員 (Member)"],
        )

    with col2:
        st.markdown("### ⚙️ 劇本設定")

        group_type_options = [
            "大學生生涯探索團體",
            "人際關係成長團體",
            "情緒支持團體",
            "壓力調適與自我照顧團體",
            "憤怒情緒管理團體",
            "哀傷與失落輔導團體",
            "職場/學校溝通技巧團體",
            "其他 (請自訂)",
        ]

        selected_type = st.selectbox("團體類型", group_type_options)

        if selected_type == "其他 (請自訂)":
            final_group_type = st.text_input("請輸入自訂的團體名稱/性質").strip()
        else:
            final_group_type = selected_type

        selected_approach = st.selectbox("🧠 理論學派取向（可選）", list(APPROACH_PROMPTS.keys()))

        session_num = st.slider("現在是第幾次團體？", 1, 10, 1)

        context_input = st.text_area(
            "前情提要 / 團體氣氛 (Context) 🎲",
            value="",
            placeholder="請輸入情境。若留白，系統將自動隨機抽取一個溫和安全的狀況讓您練習！",
        )

    st.markdown("---")
    st.markdown("### 📎 續談設定（可選）")

    uploaded_transcript = st.file_uploader(
        "上傳前次晤談逐字稿 .txt",
        type=["txt"],
        help="可上傳本系統先前下載的逐字稿，讓 AI 接續前次內容。",
    )

    continuation_mode = st.radio(
        "續談方式",
        ["僅供 AI 參考", "載入到聊天室畫面並接續"],
        horizontal=True,
    )

    previous_transcript_text = ""
    uploaded_history = []

    if uploaded_transcript is not None:
        previous_transcript_text = read_uploaded_text(uploaded_transcript)
        uploaded_history = parse_transcript_to_history(previous_transcript_text)

        if previous_transcript_text:
            st.success(f"✅ 已讀取前次逐字稿，共 {len(previous_transcript_text)} 個字。")
            st.caption(f"系統解析出 {len(uploaded_history)} 則可接續的對話。")

            with st.expander("預覽前次逐字稿"):
                st.text(previous_transcript_text[:3000])

        else:
            st.warning("⚠️ 上傳檔案內容為空，請確認逐字稿檔案。")

    if st.button("開始演練", type="primary"):
        parsed_keys = [key.strip() for key in api_key_input.split(",") if key.strip()]

        if not parsed_keys:
            st.warning("請至少輸入一把有效的 Google API Key。")
            st.stop()

        if not final_group_type:
            st.warning("請確認團體類型或自訂團體名稱。")
            st.stop()

        if len(parsed_keys) > 5:
            st.warning("⚠️ API Key 數量較多，建議以 1 到 3 把為主，較容易除錯。")

        if not all(key.startswith("AIza") for key in parsed_keys):
            st.warning("⚠️ 有些 Key 看起來不像 Google Gemini API Key，若稍後失敗請重新確認。")

        st.session_state.api_keys = parsed_keys
        st.session_state.current_key_index = 0
        st.session_state.previous_transcript_text = previous_transcript_text
        st.session_state.continuation_mode = continuation_mode

        if context_input.strip():
            base_context = context_input.strip()
        else:
            random_contexts = [
                "【溫和破冰】這是第一次團體，成員們態度都很友善，但稍微有些害羞。大家面帶微笑看著帶領者，等待您給予明確的指示或有趣的破冰小活動。",
                "【建立共鳴】剛剛有成員提到最近對於『未來發展』和『課業』感到一點點迷惘，其他幾個人聽了頻頻點頭。這是一個建立『普遍性』，讓大家知道彼此都有同感的好時機。",
                "【正向支持】目前氣氛很溫暖。有成員主動分享了最近生活中一件微小但開心的事情，非常適合帶領者與其他成員練習給予肯定與支持。",
                "【目標探索】成員們對於『團體諮商』感到好奇，雖然不太確定具體要怎麼運作，但大家展現出高度的參與意願，很適合一起討論並建立團體的共同目標。",
                "【溫和沉默】大家目前情緒很平穩，只是靜靜地坐著。氣氛並不緊張或抗拒，只是單純不知道該說什麼。這時只要帶領者拋出簡單、低威脅性的問題，大家就很願意回答。",
            ]
            base_context = random.choice(random_contexts)

        previous_context_block = ""

        if previous_transcript_text:
            previous_context_block = f"""
【前次晤談逐字稿摘要參考】
以下是使用者上傳的前次晤談紀錄。你需要把它視為前次團體歷程，理解曾出現的主題、情緒、成員互動與未完成議題。本次回覆要自然接續，但不要逐字重複。

{previous_transcript_text[-8000:]}
"""

        final_context = f"""
{base_context}

{previous_context_block}

{APPROACH_PROMPTS[selected_approach]}
"""

        session_id = safe_start_session(
            st.session_state.student_id,
            user_role,
            final_group_type,
            session_num,
        )

        st.session_state.current_session_id = session_id
        st.session_state.user_role = user_role
        st.session_state.group_context = {
            "type": final_group_type,
            "session": session_num,
            "atmosphere": final_context,
            "approach": selected_approach,
            "has_previous_transcript": bool(previous_transcript_text),
            "continuation_mode": continuation_mode,
        }

        if user_role == "團體帶領者 (Leader)":
            full_pool = personas.get_mixed_participants(count=5, include_leader=False)
            members_only = [p for p in full_pool if "Leader" not in p.get("name", "")]
            st.session_state.participants = random.sample(members_only, min(3, len(members_only)))
            st.session_state.user_avatar = "🧑‍🏫"
            st.session_state.user_name = "Leader"

            if previous_transcript_text and continuation_mode == "載入到聊天室畫面並接續" and uploaded_history:
                st.session_state.chat_history = uploaded_history
            else:
                st.session_state.chat_history = []

        else:
            full_pool = personas.get_mixed_participants(count=5, include_leader=True)
            ai_leader = [p for p in full_pool if "Leader" in p.get("name", "")]
            members_only = [p for p in full_pool if "Leader" not in p.get("name", "")]

            selected_members = random.sample(members_only, min(3, len(members_only)))
            st.session_state.participants = ai_leader + selected_members

            st.session_state.user_avatar = "🙋"
            st.session_state.user_name = "Member"

            if previous_transcript_text and continuation_mode == "載入到聊天室畫面並接續" and uploaded_history:
                st.session_state.chat_history = uploaded_history
            else:
                welcome_msg = (
                    f"大家好，歡迎大家回到這次的「{final_group_type}」。"
                    f"今天是我們的第 {session_num} 次聚會。"
                    "如果大家願意，我們可以先從上次談完後，這段時間有什麼變化或感受開始。"
                    if previous_transcript_text
                    else (
                        f"大家好，歡迎大家來到這次的「{final_group_type}」。"
                        f"今天是我們的第 {session_num} 次聚會，有人想先分享一下最近的心情，或是帶著什麼期待來嗎？"
                    )
                )

                st.session_state.chat_history = [
                    {"role": "Dr. AI (Leader)", "content": welcome_msg}
                ]

                safe_log_message(
                    session_id,
                    st.session_state.student_id,
                    "Dr. AI (Leader)",
                    welcome_msg,
                )

        if previous_transcript_text:
            safe_log_message(
                session_id,
                st.session_state.student_id,
                "System",
                f"本次演練已上傳前次逐字稿作為續談參考。續談方式：{continuation_mode}",
            )

        st.rerun()


else:
    ctx = st.session_state.group_context or {}

    st.subheader(f"💬 {ctx.get('type', '團體諮商模擬')} (第 {ctx.get('session', 1)} 次)")

    approach = ctx.get("approach", "不指定（預設）")
    atmosphere = ctx.get("atmosphere", "")
    display_atmosphere = atmosphere.split("[特別指示")[0].split("【前次晤談逐字稿摘要參考】")[0].strip()
    approach_display = f" | 🧠 學派取向：{approach}" if approach != "不指定（預設）" else ""
    continuation_display = " | 📎 已載入前次晤談紀錄" if ctx.get("has_previous_transcript") else ""

    st.success(f"🎬 **當前情境設定：** {display_atmosphere}{approach_display}{continuation_display}")

    participants = st.session_state.participants or []

    if not participants:
        st.error("⚠️ 找不到 AI 參與者資料，請登出後重新開始演練。")
        st.stop()

    cols = st.columns(len(participants))

    for idx, participant in enumerate(participants):
        with cols[idx]:
            st.info(
                f"{participant.get('avatar', '🤖')} {participant.get('name', 'AI')}\n\n"
                f"{participant.get('type', '')}"
            )

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📝 演練結束區")

        transcript = (
            "【團體諮商模擬演練逐字稿】\n"
            f"學號：{st.session_state.student_id}\n"
            f"匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"學派取向：{approach}\n"
            f"是否續談：{'是' if ctx.get('has_previous_transcript') else '否'}\n"
            f"續談方式：{ctx.get('continuation_mode', '無')}\n\n"
        )

        for msg in st.session_state.chat_history:
            transcript += f"{msg.get('role', '')}： {msg.get('content', '')}\n\n"

        st.download_button(
            label="📥 1. 先下載本次逐字稿",
            data=transcript.encode("utf-8-sig"),
            file_name=f"GroupLog_{st.session_state.student_id}_{datetime.now().strftime('%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            type="primary",
        )

        st.warning("⚠️ 離開前請務必確認已下載逐字稿。")

        if st.button("🚪 2. 結束並登出系統", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    for msg in st.session_state.chat_history:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {content}")
        elif role == "System":
            continue
        else:
            member = next((p for p in participants if p.get("name") == role), None)
            avatar = member.get("avatar", "🤖") if member else "🤖"

            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{role}:** {content}")

    user_input = st.chat_input("請輸入...")

    if user_input:
        with st.chat_message("user", avatar=st.session_state.user_avatar):
            st.write(user_input)

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
        })

        safe_log_message(
            st.session_state.current_session_id,
            st.session_state.student_id,
            "User",
            user_input,
        )

        active_speakers = []

        for participant in participants:
            participant_name = participant.get("name", "")

            if "Leader" in participant_name:
                if random.random() < 0.80:
                    active_speakers.append(participant)
            else:
                if random.random() < 0.40:
                    active_speakers.append(participant)

        if not active_speakers:
            active_speakers = [random.choice(participants)]

        random.shuffle(active_speakers)

        for participant in active_speakers:
            participant_name = participant.get("name", "AI")
            participant_avatar = participant.get("avatar", "🤖")
            participant_prompt = participant.get("system_prompt", "")

            with st.spinner(f"{participant_name} 思考中..."):
                try:
                    context_prompt = f"""
[DYNAMIC CONTEXT]
Group Type: {ctx.get('type', '')}
Session Number: {ctx.get('session', '')}
Atmosphere and Previous Session Reference:
{ctx.get('atmosphere', '')}

Your Role:
{participant_prompt}

User Role:
{st.session_state.user_role}

INSTRUCTION:
Respond naturally according to your persona.
Use direct speech only.
Use Traditional Chinese.
Keep the response concise, supportive, and appropriate for a counseling training simulation.
If previous transcript exists, continue naturally from prior themes without mechanically summarizing everything.
Do not mention that you are an AI unless the role setting explicitly requires it.
"""

                    recent_history = st.session_state.chat_history[-24:]
                    history_text = ""

                    for history_msg in recent_history:
                        role = history_msg.get("role", "")
                        content = history_msg.get("content", "")

                        if role == "System":
                            continue

                        if role == "user":
                            history_text += f"User: {content}\n"
                        else:
                            prefix = "You" if role == participant_name else role
                            history_text += f"{prefix}: {content}\n"

                    messages = [
                        SystemMessage(content=context_prompt),
                        HumanMessage(
                            content=(
                                "[Conversation Transcript]\n"
                                f"{history_text}\n\n"
                                "[Instruction]\n"
                                f"What do you, as {participant_name}, say next? "
                                "Please provide your direct speech only."
                            )
                        ),
                    ]

                    content = generate_ai_reply(messages)

                    with st.chat_message("assistant", avatar=participant_avatar):
                        st.write(f"**{participant_name}:** {content}")

                    st.session_state.chat_history.append({
                        "role": participant_name,
                        "content": content,
                    })

                    safe_log_message(
                        st.session_state.current_session_id,
                        st.session_state.student_id,
                        participant_name,
                        content,
                    )

                    time.sleep(1.2)

                except Exception as e:
                    st.warning(f"⚠️ {participant_name} 暫時無法回應：{e}")
                    continue
