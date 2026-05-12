import json
import random
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText

import streamlit as st
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import data_manager
import personas


st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")


EXAM_PHASE_SECONDS = 10 * 60
MAX_PREVIOUS_CONTEXT_CHARS = 3500
MAX_RECENT_HISTORY_MESSAGES = 12
API_COOLDOWN_SECONDS = 90
MAX_USER_INPUT_CHARS = 120
INPUT_COOLDOWN_SECONDS = 5


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
    "user_avatar": "🧑‍🏫",
    "user_name": "Leader",
    "group_context": None,
    "turn_index": 0,
    "api_blocked_until": 0,
    "last_user_submit_at": 0,
    "exam_phase": 0,
    "phase_started_at": 0,
    "phase_1_transcript": "",
}


def init_session_state():
    for key, value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, list) else value


init_session_state()


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    remain = seconds % 60
    return f"{minutes:02d}:{remain:02d}"


def phase_elapsed_seconds():
    if not st.session_state.phase_started_at:
        return 0
    return int(time.time() - st.session_state.phase_started_at)


def phase_remaining_seconds():
    return max(0, EXAM_PHASE_SECONDS - phase_elapsed_seconds())


def phase_time_is_up():
    return phase_remaining_seconds() <= 0


def get_input_cooldown_remaining():
    last_submit_at = st.session_state.get("last_user_submit_at", 0)

    if not last_submit_at:
        return 0

    elapsed = time.time() - last_submit_at
    return max(0, int(INPUT_COOLDOWN_SECONDS - elapsed))


def validate_student_input(user_input):
    text = user_input.strip()

    if not text:
        return False, "請輸入內容。"

    if len(text) > MAX_USER_INPUT_CHARS:
        return False, f"本次輸入共 {len(text)} 字，已超過 {MAX_USER_INPUT_CHARS} 字上限，請縮短後再送出。"

    cooldown_remaining = get_input_cooldown_remaining()

    if cooldown_remaining > 0:
        return False, f"請等待 {cooldown_remaining} 秒後再送出下一段。"

    return True, text


def safe_start_session(student_id, user_role, group_type, session_num):
    try:
        return data_manager.start_session(student_id, user_role, group_type, session_num)
    except Exception as e:
        st.warning(f"⚠️ 雲端紀錄建立失敗，本次仍可演練，但可能無法自動保存。錯誤：{e}")
        return f"local_{student_id}_{int(time.time())}"


def role_to_speaker_label(role):
    if role == "user":
        return "Student Leader"
    return role


def role_to_speaker_type(role):
    if role == "user":
        return "student_leader"
    if role == "System":
        return "system"
    if "Leader" in role:
        return "ai_leader"
    return "ai_member"


def safe_log_chat_message(role, content, message_type="dialogue", source="live"):
    try:
        ctx = st.session_state.group_context or {}
        st.session_state.turn_index += 1

        data_manager.log_message(
            session_id=st.session_state.current_session_id,
            student_id=st.session_state.student_id,
            speaker=role_to_speaker_label(role),
            message=content,
            role_mode=st.session_state.user_role,
            group_type=ctx.get("type", ""),
            session_num=ctx.get("session", ""),
            approach=ctx.get("approach", ""),
            speaker_type=role_to_speaker_type(role),
            turn_index=st.session_state.turn_index,
            message_type=message_type,
            source=source,
        )
    except Exception as e:
        print(f"log_message failed: {e}")


def safe_log_transcript_snapshot(session_id, student_id, role, group_type, session_num, approach, transcript_text, reason):
    try:
        data_manager.log_transcript_snapshot(
            session_id=session_id,
            student_id=student_id,
            role=role,
            group_type=group_type,
            session_num=session_num,
            approach=approach,
            transcript_text=transcript_text,
            reason=reason,
        )
    except Exception as e:
        print(f"log_transcript_snapshot failed: {e}")


def safe_log_assessment(session_id, student_id, session_num, assessment, raw_assessment, student_intervention):
    try:
        data_manager.log_assessment(
            session_id=session_id,
            student_id=student_id,
            session_num=session_num,
            assessment=assessment,
            raw_assessment=raw_assessment,
            student_intervention=student_intervention,
        )
    except Exception as e:
        print(f"log_assessment failed: {e}")


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
    keywords = ["429", "quota", "exhausted", "rate limit", "resource exhausted"]
    return any(keyword in error_msg for keyword in keywords)


def is_invalid_key_error(error):
    error_msg = str(error).lower()
    keywords = ["api_key_invalid", "api key not valid", "key not valid", "invalid api key"]
    return any(keyword in error_msg for keyword in keywords)


def set_api_cooldown():
    st.session_state.api_blocked_until = time.time() + API_COOLDOWN_SECONDS


def get_api_cooldown_remaining():
    return max(0, int(st.session_state.api_blocked_until - time.time()))


def normalize_llm_content(response):
    content = getattr(response, "content", "")

    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )

    return str(content).strip()


def create_llm(current_key):
    base_kwargs = {
        "model": "gemini-2.5-flash",
        "google_api_key": current_key,
        "temperature": 0.4,
        "timeout": 30,
        "max_retries": 1,
    }

    try:
        return ChatGoogleGenerativeAI(**base_kwargs, max_output_tokens=220)
    except TypeError:
        return ChatGoogleGenerativeAI(**base_kwargs)


def generate_ai_reply(messages, show_key_switch=True):
    cooldown_remaining = get_api_cooldown_remaining()
    if cooldown_remaining > 0:
        raise RuntimeError(f"Gemini 暫時達到流量限制，請約 {cooldown_remaining} 秒後再試。")

    last_error = None

    while st.session_state.current_key_index < len(st.session_state.api_keys):
        current_key = st.session_state.api_keys[st.session_state.current_key_index]

        try:
            llm = create_llm(current_key)
            response = llm.invoke(messages)
            content = normalize_llm_content(response)

            if not content:
                raise ValueError("AI 回覆為空。")

            return content

        except Exception as e:
            last_error = e

            if is_invalid_key_error(e):
                if st.session_state.current_key_index < len(st.session_state.api_keys) - 1:
                    st.session_state.current_key_index += 1
                    if show_key_switch:
                        st.toast("🔄 其中一把 API Key 無效，已嘗試切換下一把。", icon="🔑")
                    continue

                raise RuntimeError("Google API Key 無效，請確認是否貼上 Gemini API Key。")

            if is_quota_error(e):
                if st.session_state.current_key_index < len(st.session_state.api_keys) - 1:
                    st.session_state.current_key_index += 1
                    if show_key_switch:
                        st.toast(
                            f"🔄 API Key 額度用盡，已切換到第 {st.session_state.current_key_index + 1} 把 Key。",
                            icon="🔋",
                        )
                    continue

                set_api_cooldown()
                raise RuntimeError("所有 API Key 暫時達到額度或流量限制，請稍後再試。")

            raise RuntimeError(f"AI 生成失敗：{e}")

    set_api_cooldown()
    raise RuntimeError(f"AI 生成失敗：{last_error}")


def get_all_persona_pool():
    pool = []

    try:
        pool.extend(personas.get_special_members())
        pool.extend(personas.get_normal_members())
    except Exception:
        pool = personas.get_mixed_participants(count=5, include_leader=False)

    unique = []
    seen_names = set()

    for participant in pool:
        name = participant.get("name")
        if name and name not in seen_names and "Leader" not in name:
            unique.append(participant)
            seen_names.add(name)

    return unique


def select_participants():
    pool = get_all_persona_pool()
    random.shuffle(pool)

    selected = []
    special = [p for p in pool if any(tag in p.get("type", "") for tag in ["情緒", "防衛", "抱怨", "逃避"])]
    normal = [p for p in pool if p not in special]

    if special:
        selected.append(random.choice(special))

    for candidate in normal + special:
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= 3:
            break

    return selected[:3]


def choose_next_speaker(participants, user_input):
    if not participants:
        return None

    text = user_input.lower()

    for participant in participants:
        name = participant.get("name", "")
        participant_id = participant.get("id", "")

        if name and name.lower() in text:
            return participant

        if participant_id and participant_id.lower() in text:
            return participant

    last_ai_roles = [
        msg.get("role")
        for msg in reversed(st.session_state.chat_history)
        if msg.get("role") not in ["user", "System"]
    ]

    candidates = participants[:]

    if last_ai_roles:
        candidates = [p for p in participants if p.get("name") != last_ai_roles[0]] or participants[:]

    return random.choice(candidates)


def extract_json_object(raw_text):
    if not raw_text:
        return {}

    text = raw_text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}

    return {}


def assess_full_exam(ctx, final_transcript):
    try:
        transcript_for_assessment = final_transcript[-14000:]

        rubric_prompt = f"""
你是團體諮商教學評分助理。請只回傳 JSON，不要加任何說明文字。

請根據完整逐字稿，評估「學生作為團體帶領者」在本次考試中的整體專業度。
本次考試包含第 1 次團體與第 2 次續談團體。
這個評分只給教授後台參考，不會顯示給學生。

團體類型：{ctx.get('type', '')}
學派取向：{ctx.get('approach', '')}

評分向度，每項 0 到 5 分：
1. empathy_score：同理與情緒涵容
2. process_score：團體歷程促進能力
3. technique_score：諮商技術與學派取向契合度
4. safety_score：安全、界線、危機敏感度
5. structure_score：清楚度、聚焦度與帶領結構

請回傳 JSON 格式：
{{
  "total_score": 0,
  "empathy_score": 0,
  "process_score": 0,
  "technique_score": 0,
  "safety_score": 0,
  "structure_score": 0,
  "feedback": "給教授看的整體評語，簡短指出主要優點、限制與可改進處"
}}
"""

        messages = [
            SystemMessage(content=rubric_prompt),
            HumanMessage(content=f"[完整考試逐字稿]\n{transcript_for_assessment}"),
        ]

        raw_assessment = generate_ai_reply(messages, show_key_switch=False)
        assessment = extract_json_object(raw_assessment)

        safe_log_assessment(
            session_id=st.session_state.current_session_id,
            student_id=st.session_state.student_id,
            session_num="1+2",
            assessment=assessment,
            raw_assessment=raw_assessment,
            student_intervention="FULL_EXAM_ASSESSMENT",
        )

    except Exception as e:
        safe_log_assessment(
            session_id=st.session_state.current_session_id,
            student_id=st.session_state.student_id,
            session_num="1+2",
            assessment={},
            raw_assessment=f"assessment_error: {e}",
            student_intervention="FULL_EXAM_ASSESSMENT",
        )


def transcript_role_label(role):
    if role == "user":
        return "Student Leader"
    return role


def build_transcript(ctx):
    transcript = (
        "\n"
        f"學號：{st.session_state.student_id}\n"
        f"匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"目前階段：第 {st.session_state.exam_phase} 次團體\n"
        f"學派取向：{ctx.get('approach', '不指定（預設）')}\n\n"
    )

    for msg in st.session_state.chat_history:
        if msg.get("role") == "System":
            transcript += f"{msg.get('content', '')}\n\n"
            continue
        transcript += f"{transcript_role_label(msg.get('role', ''))}： {msg.get('content', '')}\n\n"

    return transcript


def move_to_phase_2():
    ctx = st.session_state.group_context or {}
    phase_1_transcript = build_transcript(ctx)
    st.session_state.phase_1_transcript = phase_1_transcript

    safe_log_transcript_snapshot(
        session_id=st.session_state.current_session_id,
        student_id=st.session_state.student_id,
        role=st.session_state.user_role,
        group_type=ctx.get("type", ""),
        session_num=1,
        approach=ctx.get("approach", ""),
        transcript_text=phase_1_transcript,
        reason="phase_1_complete",
    )

    base_context = ctx.get("base_context", "")
    approach_prompt = ctx.get("approach_prompt", "")
    previous_block = f"""

以下是剛剛第 1 次團體的內容節錄。第 2 次團體需要自然接續前次主題、成員情緒、互動與未完成議題。

{phase_1_transcript[-MAX_PREVIOUS_CONTEXT_CHARS:]}
"""

    ctx["session"] = 2
    ctx["has_previous_transcript"] = True
    ctx["atmosphere"] = f"{base_context}\n\n{previous_block}\n\n{approach_prompt}"
    st.session_state.group_context = ctx
    st.session_state.exam_phase = 2
    st.session_state.phase_started_at = time.time()
    st.session_state.last_user_submit_at = 0

    transition_msg = "第 1 次團體已結束，系統已自動保存逐字稿並進入第 2 次續談團體。"
    st.session_state.chat_history.append({"role": "System", "content": transition_msg})
    safe_log_chat_message("System", transition_msg, "phase_transition", "system")
    st.rerun()


def finish_exam_and_logout():
    ctx = st.session_state.group_context or {}
    final_transcript = build_transcript(ctx)

    safe_log_transcript_snapshot(
        session_id=st.session_state.current_session_id,
        student_id=st.session_state.student_id,
        role=st.session_state.user_role,
        group_type=ctx.get("type", ""),
        session_num="1+2",
        approach=ctx.get("approach", ""),
        transcript_text=final_transcript,
        reason="exam_final_submit",
    )

    assess_full_exam(ctx, final_transcript)

    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.rerun()


APPROACH_PROMPTS = {
    "不指定（預設）": "",
    "「心理動力取向」精神分析取向": """
[特別指示：這是一個「精神分析」取向的團體]
若你是 AI 團體成員：請偶爾展現抗拒，或將對權威/父母的情感投射到帶領者或其他成員身上。
""",
    "「心理動力取向」阿德勒取向": """
[特別指示：這是一個「阿德勒學派」取向的團體]
若你是 AI 團體成員：請分享人際中的氣餒、自卑感，或想討好、尋求關注的生命風格。
""",
    "「經驗與關係導向取向」存在主義取向": """
[特別指示：這是一個「存在主義」取向的團體]
若你是 AI 團體成員：請表達對未來、選擇、責任或生命意義的焦慮。
""",
    "「經驗與關係導向取向」個人中心取向": """
[特別指示：這是一個「個人中心治療」取向的團體]
若你是 AI 團體成員：請表達內在感受、理想我與真實我的矛盾。
""",
    "「經驗與關係導向取向」完形治療": """
[特別指示：這是一個「完形治療」取向的團體]
若你是 AI 團體成員：請多用第一人稱表達當下情緒與身體感受。
""",
    "「經驗與關係導向取向」心理劇": """
[特別指示：這是一個「心理劇」取向的團體]
若你是 AI 團體成員：請願意配合演出並表達真實情感。
""",
    "「認知行為取向」行為治療法": """
[特別指示：這是一個「行為治療」取向的團體]
若你是 AI 團體成員：請具體描述想改變的問題行為。
""",
    "「認知行為取向」認知治療法": """
[特別指示：這是一個「Beck 認知治療」取向的團體]
若你是 AI 團體成員：請自然展現負向認知與悲觀想法。
""",
    "「認知行為取向」理情行為治療": """
[特別指示：這是一個「Ellis 理情行為治療 (REBT)」取向的團體]
若你是 AI 團體成員：請使用我必須、他應該、糟透了等僵化語氣。
""",
    "「認知行為取向」現實治療": """
[特別指示：這是一個「現實治療」取向的團體]
若你是 AI 團體成員：請抱怨外界或他人，等待帶領者拉回自己的選擇。
""",
    "「後現代取向」焦點解決短期治療": """
[特別指示：這是一個「焦點解決短期治療」取向的團體]
若你是 AI 團體成員：請從抱怨問題逐漸轉向成功經驗與可行下一步。
""",
    "「後現代取向」敘事治療": """
[特別指示：這是一個「敘事治療」取向的團體]
若你是 AI 團體成員：請把困擾視為一個外在問題並探索抵抗經驗。
""",
    "「後現代取向」女性主義治療": """
[特別指示：這是一個「女性主義治療」取向的團體]
若你是 AI 團體成員：請分享家庭、職場或社會期待中的壓迫與角色衝突。
""",
    "「後現代取向」正向心理治療": """
[特別指示：這是一個「正向心理治療」取向的團體]
若你是 AI 團體成員：請分享生活中微小美好、成功經驗或個人優勢。
""",
}


with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統採考試模式：第 1 次團體 10 分鐘，第 2 次續談團體 10 分鐘。")
    st.caption("學生端不會顯示 AI 評分；評分僅供教授後台參考。")


if not st.session_state.otp_verified:
    st.title("🛡️ 團體諮商 AI 模擬系統")
    st.info("本系統為專屬演練平台。請先進行身分驗證。")

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
            masked_email = target_email[:4] + "****" + target_email[target_email.find("@"):]

            with st.spinner("正在發送驗證信，請稍候..."):
                otp = str(random.randint(100000, 999999))
                if send_otp_email(target_email, otp):
                    st.session_state.generated_otp = otp
                    st.session_state.student_id = student_id_clean
                    st.success(f"✅ 驗證碼已發送至您的專屬信箱 ({masked_email})！")
                else:
                    st.error("❌ 寄信失敗，請向研究者確認系統後台信箱設定。")

    if st.session_state.generated_otp:
        user_otp = st.text_input("請輸入您信箱收到的 6 位數驗證碼：", type="password")

        if st.button("🚀 驗證並前往考試設定"):
            if user_otp.strip() == st.session_state.generated_otp:
                st.session_state.otp_verified = True
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")


elif not st.session_state.current_session_id:
    st.title("🎭 團體諮商模擬考試")
    st.markdown(f"##### 👤 歡迎，**{st.session_state.student_id}**")

    st.info("本考試固定為「團體帶領者」模式。系統會自動進行第 1 次團體與第 2 次續談團體。")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🔑 系統設定")
        api_key_input = st.text_input(
            "Google Gemini API Key（若有多把請用半形逗號 , 分隔）",
            type="password",
            placeholder="例如：AIzaSy..., AIzaSy...",
        )

    with col2:
        st.markdown("### ⚙️ 考試設定")

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

        context_input = st.text_area(
            "本次前情提要 / 團體氣氛（可選）",
            value="",
            placeholder="若留白，系統會自動產生溫和安全的團體情境。",
        )

    if st.button("開始考試：第 1 次團體", type="primary"):
        parsed_keys = [key.strip() for key in api_key_input.replace("，", ",").split(",") if key.strip()]

        if not parsed_keys:
            st.warning("請至少輸入一把有效的 Google Gemini API Key。")
            st.stop()

        if not final_group_type:
            st.warning("請確認團體類型或自訂團體名稱。")
            st.stop()

        if context_input.strip():
            base_context = context_input.strip()
        else:
            random_contexts = [
                "成員們態度友善，但稍微有些害羞，等待帶領者給予清楚的引導。",
                "有成員提到最近對未來與課業有些迷惘，其他人聽了頻頻點頭。",
                "目前氣氛溫暖，有成員分享了生活中微小但開心的事情。",
                "成員對團體諮商感到好奇，也展現高度參與意願。",
                "大家情緒平穩，只是不知道該說什麼，適合用低威脅問題開場。",
            ]
            base_context = random.choice(random_contexts)

        approach_prompt = APPROACH_PROMPTS[selected_approach]
        final_context = f"{base_context}\n\n{approach_prompt}"

        user_role = "團體帶領者 (Leader)"
        session_id = safe_start_session(
            st.session_state.student_id,
            user_role,
            final_group_type,
            "1+2 Exam",
        )

        st.session_state.api_keys = parsed_keys
        st.session_state.current_key_index = 0
        st.session_state.current_session_id = session_id
        st.session_state.user_role = user_role
        st.session_state.user_avatar = "🧑‍🏫"
        st.session_state.user_name = "Leader"
        st.session_state.turn_index = 0
        st.session_state.api_blocked_until = 0
        st.session_state.last_user_submit_at = 0
        st.session_state.exam_phase = 1
        st.session_state.phase_started_at = time.time()
        st.session_state.participants = select_participants()
        st.session_state.chat_history = []
        st.session_state.group_context = {
            "type": final_group_type,
            "session": 1,
            "atmosphere": final_context,
            "base_context": base_context,
            "approach": selected_approach,
            "approach_prompt": approach_prompt,
            "has_previous_transcript": False,
        }

        st.rerun()


else:
    ctx = st.session_state.group_context or {}
    participants = st.session_state.participants or []
    current_phase = st.session_state.exam_phase

    st.subheader(f"💬 {ctx.get('type', '團體諮商模擬')}（第 {current_phase} 次團體）")

    remaining = phase_remaining_seconds()
    elapsed = phase_elapsed_seconds()
    progress_value = min(1.0, elapsed / EXAM_PHASE_SECONDS)

    st.progress(progress_value)
    st.caption(f"本階段時間：已進行 {format_seconds(elapsed)} / 剩餘 {format_seconds(remaining)}")

    if phase_time_is_up():
        st.warning("⏰ 本階段 10 分鐘已到，請使用側邊欄按鈕進入下一步。")

    approach = ctx.get("approach", "不指定（預設）")
    atmosphere = ctx.get("atmosphere", "")
    display_atmosphere = atmosphere.split("")[0].split("[特別指示")[0].strip()

    continuation_display = " | 📎 已自動接續第 1 次團體" if ctx.get("has_previous_transcript") else ""
    approach_display = f" | 🧠 學派取向：{approach}" if approach != "不指定（預設）" else ""

    st.success(f"🎬 **當前情境設定：** {display_atmosphere}{approach_display}{continuation_display}")

    if not participants:
        st.error("⚠️ 找不到 AI 參與者資料，請重新開始。")
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
        st.markdown("### 📝 考試控制區")
        st.metric("目前階段", f"第 {current_phase} 次團體")
        st.metric("剩餘時間", format_seconds(remaining))

        transcript = build_transcript(ctx)

        st.download_button(
            label="📥 下載目前逐字稿備份",
            data=transcript.encode("utf-8-sig"),
            file_name=f"GroupExam_{st.session_state.student_id}_{datetime.now().strftime('%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        if current_phase == 1:
            if st.button("➡️ 進入第 2 次團體", use_container_width=True, disabled=not phase_time_is_up()):
                move_to_phase_2()

            if not phase_time_is_up():
                st.caption("第 1 次團體滿 10 分鐘後，才能進入第 2 次。")

        elif current_phase == 2:
            if st.button("✅ 結束並送出考試", use_container_width=True, disabled=not phase_time_is_up(), type="primary"):
                with st.spinner("正在保存逐字稿並送出後台評分..."):
                    finish_exam_and_logout()

            if not phase_time_is_up():
                st.caption("第 2 次團體滿 10 分鐘後，才能送出。")

    for msg in st.session_state.chat_history:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "System":
            st.caption(f"系統：{content}")
            continue

        if role == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {content}")
        else:
            member = next((p for p in participants if p.get("name") == role), None)
            avatar = member.get("avatar", "🤖") if member else "🤖"

            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{role}:** {content}")

    cooldown_remaining = get_input_cooldown_remaining()

    st.caption(f"每次輸入最多 {MAX_USER_INPUT_CHARS} 字；AI 回應後請間隔至少 {INPUT_COOLDOWN_SECONDS} 秒再送出下一段。")

    if cooldown_remaining > 0:
        st.info(f"請等待 {cooldown_remaining} 秒後再送出下一段。")

    user_input = st.chat_input("請輸入...", disabled=phase_time_is_up())

    if user_input:
        is_valid, result = validate_student_input(user_input)

        if not is_valid:
            st.warning(result)
            st.stop()

        user_input = result

        with st.chat_message("user", avatar=st.session_state.user_avatar):
            st.write(user_input)

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
        })

        safe_log_chat_message("user", user_input, "student_message", "live")

        participant = choose_next_speaker(participants, user_input)

        if participant is not None:
            participant_name = participant.get("name", "AI")
            participant_avatar = participant.get("avatar", "🤖")
            participant_prompt = participant.get("system_prompt", "")

            with st.spinner(f"{participant_name} 思考中..."):
                try:
                    context_prompt = f"""
[DYNAMIC CONTEXT]
Group Type: {ctx.get('type', '')}
Session Number: {ctx.get('session', '')}
Exam Phase: {current_phase}
Atmosphere and Previous Session:
{ctx.get('atmosphere', '')}

Your Role:
{participant_prompt}

User Role:
{st.session_state.user_role}

INSTRUCTION:
Respond naturally according to your persona.
Use Traditional Chinese.
Use direct speech only.
Reply in 1 to 3 short sentences.
Keep the response supportive and appropriate for group counseling training.
If this is phase 2, continue naturally from phase 1 without mechanically summarizing everything.
Do not mention that you are an AI unless the role setting explicitly requires it.
"""

                    recent_history = st.session_state.chat_history[-MAX_RECENT_HISTORY_MESSAGES:]
                    history_text = ""

                    for history_msg in recent_history:
                        role = history_msg.get("role", "")
                        content = history_msg.get("content", "")

                        if role == "System":
                            continue

                        if role == "user":
                            history_text += f"Student Leader: {content}\n"
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

                    safe_log_chat_message(participant_name, content, "ai_response", "live")

                except Exception as e:
                    error_text = f"{participant_name} 回應失敗：{e}"
                    safe_log_chat_message("System", error_text, "ai_error", "system")
                    st.warning(f"⚠️ {participant_name} 暫時無法回應：{e}")

        st.session_state.last_user_submit_at = time.time()
