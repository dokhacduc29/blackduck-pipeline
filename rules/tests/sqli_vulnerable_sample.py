"""
=============================================================================
Semgrep Test Target: SQL Injection Patterns
Day 20 — Custom Rule Validation

Quy ước Semgrep test annotations:
  # ruleid: <rule-id>   → dòng TIẾP THEO phải bị flag (TRUE POSITIVE expected)
  # ok: <rule-id>       → dòng TIẾP THEO KHÔNG được flag (safe code)
  # todoruleid: <id>    → sẽ bị flag trong tương lai (rule chưa cover)

Chạy validation: semgrep --test rules/
Chạy scan thực:  semgrep --config rules/sqli-custom.yaml rules/tests/
=============================================================================
"""
import sqlite3
import os

# Giả lập user input từ HTTP request
user_id = "1 OR 1=1 --"          # payload điển hình
username = "admin' OR '1'='1"    # payload bypass auth
table_name = "users"


# =============================================================================
# TRUE POSITIVES — phải bị Semgrep flag
# =============================================================================

def get_user_by_id_vulnerable(conn: sqlite3.Connection, user_id: str):
    cursor = conn.cursor()

    # ruleid: python-sqli-fstring
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchone()


def login_vulnerable(conn: sqlite3.Connection, username: str, password: str):
    cursor = conn.cursor()

    # ruleid: python-sqli-format-method
    cursor.execute(
        "SELECT * FROM users WHERE name = '{}' AND pass = '{}'".format(
            username, password
        )
    )
    return cursor.fetchone()


def search_by_name_vulnerable(conn: sqlite3.Connection, name: str):
    cursor = conn.cursor()

    # ruleid: python-sqli-percent-format
    cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)
    return cursor.fetchall()


def delete_record_vulnerable(conn: sqlite3.Connection, record_id: str):
    cursor = conn.cursor()
    sql = "DELETE FROM records WHERE id = "

    # ruleid: python-sqli-string-concat
    cursor.execute(sql + record_id)


def dynamic_table_vulnerable(conn: sqlite3.Connection, table: str, col: str, val: str):
    """Đặc biệt nguy hiểm: cả tên bảng lẫn giá trị đều không được parameterize."""
    cursor = conn.cursor()

    # ruleid: python-sqli-fstring
    cursor.execute(f"SELECT * FROM {table} WHERE {col} = '{val}'")
    return cursor.fetchall()


# =============================================================================
# FALSE POSITIVES — KHÔNG được flag (code an toàn)
# =============================================================================

def get_user_safe_parameterized(conn: sqlite3.Connection, user_id: int):
    """Parameterized query — cách đúng duy nhất."""
    cursor = conn.cursor()

    # ok: python-sqli-fstring
    # ok: python-sqli-string-concat
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


def login_safe_psycopg2(conn, username: str, password: str):
    """psycopg2 parameterized — %s là placeholder, KHÔNG phải formatting."""
    cursor = conn.cursor()

    # ok: python-sqli-percent-format
    cursor.execute(
        "SELECT * FROM users WHERE name = %s AND pass = %s",
        (username, password),   # tuple truyền riêng → safe
    )
    return cursor.fetchone()


def get_config_value(conn: sqlite3.Connection):
    """Hardcoded SQL, không có user input — không có risk."""
    cursor = conn.cursor()

    # ok: python-sqli-fstring
    # ok: python-sqli-format-method
    cursor.execute("SELECT value FROM config WHERE key = 'app_version'")
    return cursor.fetchone()


def count_rows_safe(conn: sqlite3.Connection):
    """Integer tính toán nội bộ — không có user-controlled input."""
    cursor = conn.cursor()
    limit = 100  # hardcoded integer, không phải user input

    # ok: python-sqli-fstring
    cursor.execute(f"SELECT * FROM logs LIMIT {limit}")
    return cursor.fetchall()


# =============================================================================
# UNCERTAIN / CONTEXT-DEPENDENT
# (Semgrep flag nhưng cần con người + LLM phán định)
# =============================================================================

def search_admin_panel(conn: sqlite3.Connection, search_term: str):
    """
    Context: hàm này chỉ được gọi từ admin route đã xác thực.
    Semgrep VẪN flag → cần LLM triage để đánh giá risk thực tế.
    Risk thực: thấp (authenticated admin), nhưng best practice là vẫn parameterize.
    """
    cursor = conn.cursor()
    # todoruleid: python-sqli-format-method
    query = "SELECT * FROM audit_logs WHERE event LIKE '%{}%'".format(search_term)
    cursor.execute(query)
    return cursor.fetchall()


def build_report_query(conn: sqlite3.Connection, date_from: str, date_to: str):
    """
    date_from / date_to đến từ form nhưng đã qua datetime.fromisoformat() validation.
    Semgrep không biết về validation upstream → flag.
    LLM triage nên đánh giá: UNCERTAIN / LOW RISK.
    """
    from datetime import datetime
    # Validate trước khi dùng
    datetime.fromisoformat(date_from)
    datetime.fromisoformat(date_to)

    cursor = conn.cursor()
    # ruleid: python-sqli-format-method
    cursor.execute(
        "SELECT * FROM events WHERE date BETWEEN '{}' AND '{}'".format(
            date_from, date_to
        )
    )
    return cursor.fetchall()
