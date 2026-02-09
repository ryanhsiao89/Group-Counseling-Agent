# data_manager.py
import sqlite3
import pandas as pd
from datetime import datetime
import uuid

DB_NAME = "research_data.db"

def init_db():
    """初始化資料庫：建立所需的資料表"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. 建立「會話紀錄表」 (Session Table)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            student_id TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration_seconds REAL
        )
    ''')
    
    # 2. 建立「對話內容表」 (Chat Logs)
    # 修正重點：移除了 SQL 字串中的 # 註解
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            student_id TEXT,
            speaker_role TEXT,
            message_content TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def start_session(student_id):
    """學生開始使用，建立一個新的 session"""
    session_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (session_id, student_id, start_time) VALUES (?, ?, ?)",
              (session_id, student_id, start_time))
    conn.commit()
    conn.close()
    return session_id

def log_message(session_id, student_id, role, content):
    """紀錄每一句對話"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO chat_logs (session_id, student_id, speaker_role, message_content, timestamp) VALUES (?, ?, ?, ?, ?)",
              (session_id, student_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

def end_session(session_id):
    """學生結束使用，計算時長"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    end_time = datetime.now()
    
    # 抓取開始時間來計算時長
    c.execute("SELECT start_time FROM sessions WHERE session_id = ?", (session_id,))
    result = c.fetchone()
    
    if result:
        start_time = datetime.fromisoformat(result[0])
        duration = (end_time - start_time).total_seconds()
        
        c.execute('''
            UPDATE sessions 
            SET end_time = ?, duration_seconds = ? 
            WHERE session_id = ?
        ''', (end_time, duration, session_id))
        
    conn.commit()
    conn.close()

# --- 研究者專用：匯出資料 ---
def export_chat_logs():
    """匯出所有質性文本"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM chat_logs ORDER BY timestamp", conn)
    conn.close()
    return df

def export_usage_stats():
    """匯出量化統計 (頻率、時長)"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT 
            student_id, 
            COUNT(session_id) as login_count, 
            SUM(duration_seconds)/60 as total_minutes_used,
            AVG(duration_seconds)/60 as avg_session_minutes
        FROM sessions 
        WHERE end_time IS NOT NULL 
        GROUP BY student_id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df