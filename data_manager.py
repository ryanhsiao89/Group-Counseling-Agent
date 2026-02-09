import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# Google Sheet 的名稱 (必須跟您雲端硬碟裡的檔名一模一樣)
SHEET_NAME = "AI_Group_Counseling_Data"

def get_sheet_connection():
    """建立 Google Sheets 連線"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # 從 Streamlit Secrets 讀取 JSON 金鑰
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"無法連線到 Google Sheet，請檢查 Secrets 設定或檔名。\n錯誤訊息: {e}")
        return None

def start_session(student_id, role, group_type, session_num):
    """學生開始使用，紀錄 Session"""
    session_id = str(uuid.uuid4())
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sheet = get_sheet_connection()
    if sheet:
        try:
            worksheet = sheet.worksheet("Sessions")
            # 寫入欄位: Session_ID, Student_ID, Role, Start_Time, Group_Type, Session_Num
            worksheet.append_row([session_id, student_id, role, start_time, group_type, session_num])
        except Exception as e:
            print(f"寫入 Session 失敗: {e}")
            
    return session_id

def log_message(session_id, student_id, speaker, message):
    """紀錄每一句對話到 ChatLogs 分頁"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sheet = get_sheet_connection()
    if sheet:
        try:
            worksheet = sheet.worksheet("ChatLogs")
            # 寫入欄位: Timestamp, Session_ID, Student_ID, Speaker, Message
            worksheet.append_row([timestamp, session_id, student_id, speaker, message])
        except Exception as e:
            print(f"寫入 Log 失敗: {e}")

def end_session(session_id):
    """Google Sheet 版不需要特別更新結束時間，只要有對話紀錄即可"""
    pass