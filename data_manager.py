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

MAX_RETRIES = 3
MAX_CELL_CHARS = 45000

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

UPLOADED_TRANSCRIPT_HEADERS = [
    "Timestamp",
    "Session_ID",
    "Student_ID",
    "Session_Num",
    "Filename",
    "Chunk_Index",
    "Chunk_Total",
    "Transcript_Text",
]

TRANSCRIPT_SNAPSHOT_HEADERS = [
    "Timestamp",
    "Session_ID",
    "Student_ID",
    "Role",
    "Group_Type",
    "Session_Num",
    "Approach",
    "Reason",
    "Chunk_Index",
    "Chunk_Total",
    "Transcript_Text",
]

ASSESSMENT_HEADERS = [
    "Timestamp",
    "Session_ID",
    "Student_ID",
    "Session_Num",
    "Total_Score",
    "Empathy_Score",
    "Process_Score",
    "Technique_Score",
    "Safety_Score",
    "Structure_Score",
    "Feedback",
    "Student_Intervention",
    "Raw_Assessment",
]


def get_taiwan_time():
    return datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def print_error(action, error):
    print(f"[data_manager] {action} failed: {error}")


def sanitize_cell(value):
    if value is None:
        return ""

    text = str(value)

    if len(text) > MAX_CELL_CHARS:
        return text[:MAX_CELL_CHARS] + "\n...[內容過長，已截斷]"

    return text


def split_text(text, chunk_size=MAX_CELL_CHARS):
    text = str(text or "")

    if not text:
        return [""]

    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


@st.cache_resource(show_spinner=False)
def get_sheet_connection():
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
        worksheet.append_row(headers, value_input_option="RAW")
        return worksheet
    except Exception as e:
        print_error(f"open worksheet {worksheet_name}", e)
        return None

    try:
        first_row = worksheet.row_values(1)

        if not first_row:
            worksheet.append_row(headers, value_input_option="RAW")

    except Exception as e:
        print_error(f"check worksheet header {worksheet_name}", e)

    return worksheet


def append_row_with_retry(worksheet, row, action_name):
    if worksheet is None:
        return False

    safe_row = [sanitize_cell(value) for value in row]
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            worksheet.append_row(safe_row, value_input_option="RAW")
            return True

        except Exception as e:
            last_error = e
            print_error(f"{action_name}, attempt {attempt}", e)

            if attempt < MAX_RETRIES:
                time.sleep(1.5 * attempt)

    print_error(action_name, last_error)
    return False


def start_session(student_id, role, group_type, session_num):
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
    timestamp = get_taiwan_time()
    worksheet = get_worksheet("ChatLogs", tuple(CHATLOG_HEADERS))

    return append_row_with_retry(
        worksheet,
        [timestamp, session_id, student_id, speaker, message],
        "write chat log",
    )


def log_uploaded_transcript(session_id, student_id, session_num, filename, transcript_text):
    timestamp = get_taiwan_time()
    worksheet = get_worksheet("UploadedTranscripts", tuple(UPLOADED_TRANSCRIPT_HEADERS))

    chunks = split_text(transcript_text)
    chunk_total = len(chunks)
    results = []

    for index, chunk in enumerate(chunks, start=1):
        results.append(
            append_row_with_retry(
                worksheet,
                [
                    timestamp,
                    session_id,
                    student_id,
                    session_num,
                    filename,
                    index,
                    chunk_total,
                    chunk,
                ],
                "write uploaded transcript",
            )
        )

    return all(results)


def log_transcript_snapshot(session_id, student_id, role, group_type, session_num, approach, transcript_text, reason):
    timestamp = get_taiwan_time()
    worksheet = get_worksheet("TranscriptSnapshots", tuple(TRANSCRIPT_SNAPSHOT_HEADERS))

    chunks = split_text(transcript_text)
    chunk_total = len(chunks)
    results = []

    for index, chunk in enumerate(chunks, start=1):
        results.append(
            append_row_with_retry(
                worksheet,
                [
                    timestamp,
                    session_id,
                    student_id,
                    role,
                    group_type,
                    session_num,
                    approach,
                    reason,
                    index,
                    chunk_total,
                    chunk,
                ],
                "write transcript snapshot",
            )
        )

    return all(results)


def log_assessment(session_id, student_id, session_num, assessment, raw_assessment="", student_intervention=""):
    timestamp = get_taiwan_time()
    worksheet = get_worksheet("Assessments", tuple(ASSESSMENT_HEADERS))

    assessment = assessment or {}

    return append_row_with_retry(
        worksheet,
        [
            timestamp,
            session_id,
            student_id,
            session_num,
            assessment.get("total_score", ""),
            assessment.get("empathy_score", ""),
            assessment.get("process_score", ""),
            assessment.get("technique_score", ""),
            assessment.get("safety_score", ""),
            assessment.get("structure_score", ""),
            assessment.get("feedback", ""),
            student_intervention,
            raw_assessment,
        ],
        "write assessment",
    )


def end_session(session_id):
    return True
