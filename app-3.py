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
    "turn_index": 0,
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


def role_to_speaker_label(role):
    if role == "user":
        if st.session_state.user_role == "團體帶領者 (Leader)":
            return "Student Leader"
        return "Student Member"

    return role


def role_to_speaker_type(role):
    if role == "user":
        if st.session_state.user_role == "團體帶領者 (Leader)":
            return "student_leader"
        return "student_member"

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


def safe_log_uploaded_transcript(session_id, student_id, session_num, filename, transcript_text):
    try:
        data_manager.log_uploaded_transcript(
            session_id=session_id,
            student_id=student_id,
            session_num=session_num,
            filename=filename,
            transcript_text=transcript_text,
        )
    except Exception as e:
        print(f"log_uploaded_transcript failed: {e}")


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


def normalize_llm_content(response):
    content = getattr(response, "content", "")

    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )

    return str(content).strip()


def generate_ai_reply(messages, show_key_switch=True):
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

    user_aliases = [
        "User",
        "user",
        "使用者",
        "學生",
        "Leader",
        "Member",
        "Student Leader",
        "Student Member",
        "團體帶領者",
        "團體成員",
    ]

    if role in user_aliases:
        return "user"

    return role


def parse_transcript_to_history(transcript_text, max_messages=100):
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
        "是否續談：",
        "是否續談:",
        "續談方式：",
        "續談方式:",
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
            if 0 < index <= 40:
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


def get_all_persona_pool(include_leader=False):
    pool = []

    try:
        if include_leader:
            pool.append(personas.get_ai_leader())

        pool.extend(personas.get_special_members())
        pool.extend(personas.get_normal_members())
    except Exception:
        pool = personas.get_mixed_participants(count=5, include_leader=include_leader)

    unique = []
    seen_names = set()

    for participant in pool:
        name = participant.get("name")
        if name and name not in seen_names:
            unique.append(participant)
            seen_names.add(name)

    return unique


def select_participants(user_role, uploaded_history):
    include_leader = user_role == "團體成員 (Member)"
    target_count = 4 if include_leader else 3
    pool = get_all_persona_pool(include_leader=include_leader)

    previous_names = []
    for msg in uploaded_history:
        role = msg.get("role", "")
        if role and role not in ["user", "System"] and role not in previous_names:
            previous_names.append(role)

    selected = []
    selected_names = set()

    if include_leader:
        leader = next((p for p in pool if "Leader" in p.get("name", "")), None)
        if leader:
            selected.append(leader)
            selected_names.add(leader.get("name"))

    for name in previous_names:
        if not include_leader and "Leader" in name:
            continue

        matched = next((p for p in pool if p.get("name") == name), None)

        if matched and matched.get("name") not in selected_names:
            selected.append(matched)
            selected_names.add(matched.get("name"))

        if len(selected) >= target_count:
            break

    if len(selected) < target_count:
        try:
            mixed = personas.get_mixed_participants(count=5, include_leader=include_leader)
        except Exception:
            mixed = pool

        candidate_pool = pool + mixed
        random.shuffle(candidate_pool)

        for candidate in candidate_pool:
            name = candidate.get("name")

            if not name or name in selected_names:
                continue

            if not include_leader and "Leader" in name:
                continue

            selected.append(candidate)
            selected_names.add(name)

            if len(selected) >= target_count:
                break

    if include_leader:
        leader = next((p for p in selected if "Leader" in p.get("name", "")), None)
        others = [p for p in selected if p is not leader]
        return ([leader] + others[:3]) if leader else selected[:target_count]

    return selected[:target_count]


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


def assess_leader_turn(ctx, student_intervention):
    if st.session_state.user_role != "團體帶領者 (Leader)":
        return

    try:
        recent_history = st.session_state.chat_history[-18:]
        history_text = ""

        for msg in recent_history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "System":
                continue

            speaker = "Student Leader" if role == "user" else role
            history_text += f"{speaker}: {content}\n"

        rubric_prompt = f"""
你是團體諮商教學評分助理。請只回傳 JSON，不要加任何說明文字。

請根據以下團體脈絡與最近對話，評估「學生作為團體帶領者」剛剛這一次介入的專業度。
這個評分只給教授後台參考，不會顯示給學生。

團體類型：{ctx.get('type', '')}
第幾次團體：{ctx.get('session', '')}
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
  "feedback": "給教授看的簡短評語，指出優點與可改進處"
}}
"""

        messages = [
            SystemMessage(content=rubric_prompt),
            HumanMessage(
                content=(
                    "[最近對話]\n"
                    f"{history_text}\n\n"
                    "[本次學生帶領者介入]\n"
                    f"{student_intervention}"
                )
            ),
        ]

        raw_assessment = generate_ai_reply(messages, show_key_switch=False)
        assessment = extract_json_object(raw_assessment)

        safe_log_assessment(
            session_id=st.session_state.current_session_id,
            student_id=st.session_state.student_id,
            session_num=ctx.get("session", ""),
            assessment=assessment,
            raw_assessment=raw_assessment,
            student_intervention=student_intervention,
        )

    except Exception as e:
        safe_log_assessment(
            session_id=st.session_state.current_session_id,
            student_id=st.session_state.student_id,
            session_num=ctx.get("session", ""),
            assessment={},
            raw_assessment=f"assessment_error: {e}",
            student_intervention=student_intervention,
        )


def transcript_role_label(role):
    if role == "user":
        return role_to_speaker_label(role)

    return role


def build_transcript(ctx):
    transcript = (
        "【團體諮商模擬演練逐字稿】\n"
        f"學號：{st.session_state.student_id}\n"
        f"匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"學派取向：{ctx.get('approach', '不指定（預設）')}\n"
        f"是否續談：{'是' if ctx.get('has_previous_transcript') else '否'}\n\n"
    )

    for msg in st.session_state.chat_history:
        if msg.get("role") == "System":
            continue
        transcript += f"{transcript_role_label(msg.get('role', ''))}： {msg.get('content', '')}\n\n"

    return transcript


APPROACH_PROMPTS = {
    "不指定（預設）": "",
    "「心理動力取向」精神分析取向": """
[特別指示：這是一個「精神分析」取向的團體]
若你是 AI 帶領者：請關注潛意識、防衛機制、移情與過去童年經驗。適時對成員的發言進行詮釋，並探索行為背後的潛意識動機。
若你是 AI 團體成員：請偶爾展現抗拒，或將對權威/父母的情感投射到帶領者或其他成員身上。
""",
    "「心理動力取向」阿德勒取向": """
[特別指示：這是一個「阿德勒學派」取向的團體]
若你是 AI 帶領者：請營造鼓勵氛圍，引導成員探索家庭星座、早期回憶、社會興趣、自卑與超越。
若你是 AI 團體成員：請分享人際中的氣餒、自卑感，或想討好、尋求關注的生命風格。
""",
    "「經驗與關係導向取向」存在主義取向": """
[特別指示：這是一個「存在主義」取向的團體]
若你是 AI 帶領者：請關注死亡、自由與責任、孤獨、無意義等終極關懷，陪伴成員面對存在焦慮。
若你是 AI 團體成員：請表達對未來、選擇、責任或生命意義的焦慮。
""",
    "「經驗與關係導向取向」個人中心取向": """
[特別指示：這是一個「個人中心治療」取向的團體]
若你是 AI 帶領者：請展現真誠一致、無條件正向關懷與同理心，不主動說教。
若你是 AI 團體成員：請表達內在感受、理想我與真實我的矛盾。
""",
    "「經驗與關係導向取向」完形治療": """
[特別指示：這是一個「完形治療」取向的團體]
若你是 AI 帶領者：請關注此時此地、第一人稱語言、身體感受與未竟事宜。
若你是 AI 團體成員：請多用第一人稱表達當下情緒與身體感受。
""",
    "「經驗與關係導向取向」心理劇": """
[特別指示：這是一個「心理劇」取向的團體]
若你是 AI 帶領者：請像導演般引導角色扮演、替身、鏡照與角色交換。
若你是 AI 團體成員：請願意配合演出並表達真實情感。
""",
    "「認知行為取向」行為治療法": """
[特別指示：這是一個「行為治療」取向的團體]
若你是 AI 帶領者：請關注具體行為、明確目標、增強、楷模學習、行為演練與家庭作業。
若你是 AI 團體成員：請具體描述想改變的問題行為。
""",
    "「認知行為取向」認知治療法": """
[特別指示：這是一個「Beck 認知治療」取向的團體]
若你是 AI 帶領者：請協助指認自動化思考與認知扭曲，使用蘇格拉底式提問。
若你是 AI 團體成員：請自然展現負向認知與悲觀想法。
""",
    "「認知行為取向」理情行為治療": """
[特別指示：這是一個「Ellis 理情行為治療 (REBT)」取向的團體]
若你是 AI 帶領者：請運用 ABCDE 模式辨識並駁斥非理性信念。
若你是 AI 團體成員：請使用我必須、他應該、糟透了等僵化語氣。
""",
    "「認知行為取向」現實治療": """
[特別指示：這是一個「現實治療」取向的團體]
若你是 AI 帶領者：請聚焦現在行為，運用 WDEP 協助成員為選擇負責。
若你是 AI 團體成員：請抱怨外界或他人，等待帶領者拉回自己的選擇。
""",
    "「後現代取向」焦點解決短期治療": """
[特別指示：這是一個「焦點解決短期治療」取向的團體]
若你是 AI 帶領者：請尋找例外經驗，使用奇蹟問句、量尺問句、應對問句與賦能。
若你是 AI 團體成員：請從抱怨問題逐漸轉向成功經驗與可行下一步。
""",
    "「後現代取向」敘事治療": """
[特別指示：這是一個「敘事治療」取向的團體]
若你是 AI 帶領者：請運用問題外部化、獨特結果與重寫故事。
若你是 AI 團體成員：請把困擾視為一個外在問題並探索抵抗經驗。
""",
    "「後現代取向」女性主義治療": """
[特別指示：這是一個「女性主義治療」取向的團體]
若你是 AI 帶領者：請重視權力分析、性別角色社會化、平等關係與增能。
若你是 AI 團體成員：請分享家庭、職場或社會期待中的壓迫與角色衝突。
""",
    "「後現代取向」正向心理治療": """
[特別指示：這是一個「正向心理治療」取向的團體]
若你是 AI 帶領者：請引導成員探索優勢、感恩、品味美好經驗與 PERMA。
若你是 AI 團體成員：請分享生活中微小美好、成功經驗或個人優勢。
""",
}


with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統對話紀錄與後台評分將存入雲端資料庫，供教學與研究分析使用。")
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
            "Google Gemini API Key（若有多把請用半形逗號 , 分隔）",
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
            "本次前情提要 / 團體氣氛（可選）",
            value="",
            placeholder="若留白，系統會自動產生溫和安全的團體情境。",
        )

    st.markdown("---")
    st.markdown("### 📎 前次晤談逐字稿")
    st.caption("第 2 次以上晤談必須上傳前次下載的逐字稿，系統會直接載入聊天室並接續晤談。")

    uploaded_transcript = st.file_uploader(
        "上傳前次晤談逐字稿 .txt",
        type=["txt"],
    )

    previous_transcript_text = ""
    uploaded_history = []

    if uploaded_transcript is not None:
        previous_transcript_text = read_uploaded_text(uploaded_transcript)
        uploaded_history = parse_transcript_to_history(previous_transcript_text)

        if previous_transcript_text and uploaded_history:
            st.success(f"✅ 已讀取前次逐字稿，並解析出 {len(uploaded_history)} 則對話。")
            with st.expander("預覽前次逐字稿"):
                st.text(previous_transcript_text[:3000])
        elif previous_transcript_text:
            st.warning("⚠️ 已讀取檔案，但無法解析成可接續的對話。請使用本系統下載的逐字稿。")
        else:
            st.warning("⚠️ 上傳檔案內容為空。")

    if st.button("開始演練", type="primary"):
        parsed_keys = [key.strip() for key in api_key_input.replace("，", ",").split(",") if key.strip()]

        if not parsed_keys:
            st.warning("請至少輸入一把有效的 Google Gemini API Key。")
            st.stop()

        if not final_group_type:
            st.warning("請確認團體類型或自訂團體名稱。")
            st.stop()

        if session_num > 1 and not previous_transcript_text:
            st.warning("第 2 次以上晤談請先上傳前次逐字稿，才能接續團體歷程。")
            st.stop()

        if previous_transcript_text and not uploaded_history:
            st.warning("前次逐字稿無法解析，請確認是由本系統下載的 .txt 檔。")
            st.stop()

        st.session_state.api_keys = parsed_keys
        st.session_state.current_key_index = 0
        st.session_state.previous_transcript_text = previous_transcript_text
        st.session_state.turn_index = 0

        if context_input.strip():
            base_context = context_input.strip()
        else:
            random_contexts = [
                "【溫和破冰】成員們態度友善，但稍微有些害羞，等待帶領者給予清楚的引導。",
                "【建立共鳴】有成員提到最近對未來與課業有些迷惘，其他人聽了頻頻點頭。",
                "【正向支持】目前氣氛溫暖，有成員分享了生活中微小但開心的事情。",
                "【目標探索】成員對團體諮商感到好奇，也展現高度參與意願。",
                "【溫和沉默】大家情緒平穩，只是不知道該說什麼，適合用低威脅問題開場。",
            ]
            base_context = random.choice(random_contexts)

        previous_context_block = ""
        if previous_transcript_text:
            previous_context_block = f"""
【前次晤談逐字稿】
以下是學生上傳的前次團體晤談紀錄。請把它視為已發生的團體歷程，本次要自然接續前次的主題、情緒、互動與未完成議題。

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
        }

        st.session_state.participants = select_participants(user_role, uploaded_history)

        if user_role == "團體帶領者 (Leader)":
            st.session_state.user_avatar = "🧑‍🏫"
            st.session_state.user_name = "Leader"
        else:
            st.session_state.user_avatar = "🙋"
            st.session_state.user_name = "Member"

        if previous_transcript_text:
            st.session_state.chat_history = uploaded_history

            safe_log_uploaded_transcript(
                session_id=session_id,
                student_id=st.session_state.student_id,
                session_num=session_num,
                filename=uploaded_transcript.name,
                transcript_text=previous_transcript_text,
            )

            for imported_msg in uploaded_history:
                safe_log_chat_message(
                    role=imported_msg.get("role", ""),
                    content=imported_msg.get("content", ""),
                    message_type="imported_transcript",
                    source="uploaded_previous_transcript",
                )

        else:
            if user_role == "團體成員 (Member)":
                welcome_msg = (
                    f"大家好，歡迎大家來到這次的「{final_group_type}」。"
                    f"今天是我們的第 {session_num} 次聚會，有人想先分享一下最近的心情嗎？"
                )
                st.session_state.chat_history = [{"role": "Dr. AI (Leader)", "content": welcome_msg}]
                safe_log_chat_message("Dr. AI (Leader)", welcome_msg, "ai_response", "live")
            else:
                st.session_state.chat_history = []

        st.rerun()


else:
    ctx = st.session_state.group_context or {}
    participants = st.session_state.participants or []

    st.subheader(f"💬 {ctx.get('type', '團體諮商模擬')}（第 {ctx.get('session', 1)} 次）")

    approach = ctx.get("approach", "不指定（預設）")
    atmosphere = ctx.get("atmosphere", "")
    display_atmosphere = atmosphere.split("【前次晤談逐字稿】")[0].split("[特別指示")[0].strip()

    continuation_display = " | 📎 已載入前次逐字稿" if ctx.get("has_previous_transcript") else ""
    approach_display = f" | 🧠 學派取向：{approach}" if approach != "不指定（預設）" else ""

    st.success(f"🎬 **當前情境設定：** {display_atmosphere}{approach_display}{continuation_display}")

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

        transcript = build_transcript(ctx)

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
            final_transcript = build_transcript(ctx)

            safe_log_transcript_snapshot(
                session_id=st.session_state.current_session_id,
                student_id=st.session_state.student_id,
                role=st.session_state.user_role,
                group_type=ctx.get("type", ""),
                session_num=ctx.get("session", ""),
                approach=ctx.get("approach", ""),
                transcript_text=final_transcript,
                reason="logout",
            )

            for key in list(st.session_state.keys()):
                del st.session_state[key]

            st.rerun()

    for msg in st.session_state.chat_history:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "System":
            continue

        if role == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {content}")
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

        safe_log_chat_message("user", user_input, "student_message", "live")

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
Keep the response concise, supportive, and appropriate for a group counseling training simulation.
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
                            history_text += f"Student: {content}\n"
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

                    time.sleep(1.2)

                except Exception as e:
                    error_text = f"{participant_name} 回應失敗：{e}"
                    safe_log_chat_message("System", error_text, "ai_error", "system")
                    st.warning(f"⚠️ {participant_name} 暫時無法回應：{e}")
                    continue

        assess_leader_turn(ctx, user_input)
