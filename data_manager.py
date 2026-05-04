import time
import uuid
from datetime import datetime, timezone, timedelta

import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials


SHEET_NAME = "AI_Group_Counseling_Data"

TAIWAN_TZ = timezone(timedelta(hours=8))

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SESSION_HEADERS = [
    "Session_ID",
    "Student_ID",
    "Role",
    "Start_Time",
    "Group_Type",
    "Session_Num",
]

CHATLOG_HEADERS = [
    "Timestamp",
    "Session_ID",
    "Student_ID",
    "Speaker",
    "Message",
]

MAX_RETRIES = 3


def get_taiwan_time():
    return datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def print_error(action, error):
    print(f"[data_manager] {action} failed: {error}")


@st.cache_resource(show_spinner=False)
def get_sheet_connection():
    """建立並快取 Google Sheets 連線，避免每句對話都重新連線。"""
    try:
        creds_dict = st.secrets.get("gcp_service_account")

        if not creds_dict:
            raise RuntimeError("找不到 st.secrets['gcp_service_account'] 設定。")

        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            dict(creds_dict),
            SCOPE,
        )

        client = gspread.authorize(creds)
        return client.open(SHEET_NAME)

    except Exception as e:
        print_error("Google Sheet connection", e)
        return None


@st.cache_resource(show_spinner=False)
def get_worksheet(worksheet_name, headers_tuple):
    """取得並快取工作表；如果分頁不存在，就自動建立。"""
    sheet = get_sheet_connection()

    if sheet is None:
        return None

    headers = list(headers_tuple)

    try:
        worksheet = sheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        worksheet = sheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=max(len(headers), 5),
        )
        worksheet.append_row(headers, value_input_option="USER_ENTERED")
        return worksheet
    except Exception as e:
        print_error(f"open worksheet {worksheet_name}", e)
        return None

    try:
        first_row = worksheet.row_values(1)

        if not first_row:
            worksheet.append_row(headers, value_input_option="USER_ENTERED")

    except Exception as e:
        print_error(f"check worksheet header {worksheet_name}", e)

    return worksheet


def append_row_with_retry(worksheet, row, action_name):
    """寫入 Google Sheet；遇到暫時性錯誤會自動重試。"""
    if worksheet is None:
        return False

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            worksheet.append_row(row, value_input_option="USER_ENTERED")
            return True

        except Exception as e:
            last_error = e
            print_error(f"{action_name}, attempt {attempt}", e)

            if attempt < MAX_RETRIES:
                time.sleep(1.5 * attempt)

    print_error(action_name, last_error)
    return False


def start_session(student_id, role, group_type, session_num):
    """學生開始使用，紀錄 Session。即使寫入失敗，也會回傳 session_id。"""
    session_id = str(uuid.uuid4())
    start_time = get_taiwan_time()

    worksheet = get_worksheet("Sessions", tuple(SESSION_HEADERS))

    append_row_with_retry(
        worksheet,
        [session_id, student_id, role, start_time, group_type, session_num],
        "write session",
    )

    return session_id


def log_message(session_id, student_id, speaker, message):
    """紀錄每一句對話到 ChatLogs 分頁。寫入失敗不會中斷主程式。"""
    timestamp = get_taiwan_time()

    worksheet = get_worksheet("ChatLogs", tuple(CHATLOG_HEADERS))

    return append_row_with_retry(
        worksheet,
        [timestamp, session_id, student_id, speaker, message],
        "write chat log",
    )


def end_session(session_id):
    """目前 Google Sheet 版不需要特別更新結束時間。"""
    return True
