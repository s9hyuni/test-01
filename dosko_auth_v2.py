import datetime
import hashlib
import hmac
import os
import re
import secrets
from dosko_db import get_db_connection, with_db_retry, fetch_table_dicts

def hash_password(password, salt=None):
    if not salt:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        str(password).encode('utf-8'),
        bytes.fromhex(salt),
        100000
    ).hex()
    return pwd_hash, salt

def verify_password(password, stored_hash, salt=None):
    if not password or not stored_hash:
        return False
    if salt:
        try:
            pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                str(password).encode('utf-8'),
                bytes.fromhex(salt),
                100000
            ).hex()
            return hmac.compare_digest(pwd_hash, stored_hash)
        except Exception:
            return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, it_str, salt_hex, digest_hex = stored_hash.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt_hex.encode("ascii"), int(it_str))
            return hmac.compare_digest(dk.hex(), digest_hex)
        except Exception:
            return False
    return hmac.compare_digest(str(password), str(stored_hash))

def validate_password_by_rule(password, pw_rule_type, emp_no=""):
    pw = str(password or "").strip()
    eno = str(emp_no or "").strip()
    
    if eno and eno in pw:
        return False, "비밀번호에 본인 사번을 포함할 수 없습니다."
        
    if pw_rule_type == 'WORKER_4DIGIT':
        if not re.match(r'^\d{4}$', pw):
            return False, "현장 일반작업자 비밀번호는 4자리 숫자여야 합니다. (예: 1842)"
        if pw in ("0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999", "1234", "4321"):
            return False, "연속되거나 단순 반복되는 숫자는 비밀번호로 사용할 수 없습니다."
        return True, "OK"
        
    elif pw_rule_type == 'PROD_MGR_8DIGIT':
        if not re.match(r'^\d{4,8}$', pw):
            return False, "현장 관리자 비밀번호는 4~8자리 숫자여야 합니다."
        if pw in ("0000", "1111", "2222", "3333", "12345678", "87654321"):
            return False, "단순 연속되거나 반복되는 숫자는 사용할 수 없습니다."
        return True, "OK"
        
    else:  # OFFICE_COMPLEX
        if len(pw) < 8:
            return False, "사무직 비밀번호는 8자 이상이어야 합니다."
        types_count = 0
        if re.search(r'[A-Za-z]', pw):
            types_count += 1
        if re.search(r'[0-9]', pw):
            types_count += 1
        if re.search(r'[^A-Za-z0-9\s]', pw):
            types_count += 1
        if types_count < 2:
            return False, "사무직 비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 조합해야 합니다."
        return True, "OK"

def authenticate_emp(emp_no, password, client_ip, user_agent=""):
    eno = str(emp_no or "").strip()
    pw = str(password or "")
    if not eno or not pw:
        return False, 400, "사번과 비밀번호를 입력하세요.", None, None

    def _query():
        with get_db_connection() as conn:
            rows = fetch_table_dicts(conn.cursor(), "SELECT * FROM dbo.sec_users WHERE emp_no = ?", (eno,))
            return rows[0] if rows else None

    user = with_db_retry(_query)
    if not user:
        return False, 401, "사번 또는 비밀번호가 올바르지 않습니다.", None, None

    now = datetime.datetime.now().replace(microsecond=0)
    if not user.get("is_active") or user.get("role_code") == "RESTRICTED" and not user.get("can_login") and not user.get("is_pending_it_setup"):
        return False, 403, "일시정지 또는 사용 중지된 계정입니다. 전산실에 문의하세요.", None, None

    if user.get("is_pending_it_setup") or not user.get("can_login"):
        return False, 403, f"전산실 권한 설정 대기 계정입니다. (사번 {eno}: 전산실 설정 후 사용 가능)", None, None

    locked_until = user.get("locked_until")
    if locked_until:
        try:
            lu_dt = datetime.datetime.fromisoformat(str(locked_until))
            if lu_dt > now:
                rem_min = int((lu_dt - now).total_seconds() // 60) + 1
                return False, 423, f"비밀번호 5회 연속 오류로 계정이 잠겼습니다. ({rem_min}분 후 재시도 또는 전산실 문의)", None, None
        except Exception:
            pass

    # Verify password
    is_valid = verify_password(pw, user["password_hash"], user.get("password_salt"))
    if not is_valid:
        fails = int(user.get("failed_login_count") or 0) + 1
        lock_dt = (now + datetime.timedelta(minutes=15)) if fails >= 5 else None
        def _record_fail():
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE dbo.sec_users SET failed_login_count = ?, locked_until = ?, updated_at = SYSUTCDATETIME() WHERE emp_no = ?",
                    (fails, lock_dt, eno)
                )
        with_db_retry(_record_fail)
        if lock_dt:
            return False, 423, "비밀번호 5회 연속 오류로 15분간 계정이 잠겼습니다. 전산실에 문의하세요.", None, None
        return False, 401, f"비밀번호가 올바르지 않습니다. ({fails}/5회 오류)", None, None

    # Check expiration (2-digit months)
    pw_expire_months = int(user.get("pw_expire_months") or 3)
    pw_updated_at = user.get("pw_updated_at")
    is_pw_expired = False
    if pw_updated_at:
        try:
            pu_dt = datetime.datetime.fromisoformat(str(pw_updated_at))
            expire_dt = pu_dt + datetime.timedelta(days=pw_expire_months * 30)
            if now > expire_dt:
                is_pw_expired = True
        except Exception:
            pass

    # Issue session
    session_token = secrets.token_hex(32)
    csrf_token = secrets.token_hex(24)
    ttl_min = max(15, int(user.get("session_ttl_min") or 480))
    exp_dt = now + datetime.timedelta(minutes=ttl_min)

    def _issue_session():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE dbo.sec_users
                SET failed_login_count = 0, locked_until = NULL, last_login_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                WHERE emp_no = ?;
            """, (eno,))
            cur.execute("""
                INSERT INTO dbo.sec_sessions
                (session_token, emp_no, client_ip, user_agent, csrf_token, is_revoked, expires_at, created_at, last_active_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, SYSUTCDATETIME(), SYSUTCDATETIME());
            """, (session_token, eno, str(client_ip)[:45], str(user_agent or "")[:200], csrf_token, exp_dt))
    with_db_retry(_issue_session)

    profile = {
        "emp_no": user["emp_no"],
        "user_name": user["user_name"],
        "dept_name": user["dept_name"],
        "group_name": user["group_name"],
        "job_rank": user["job_rank"],
        "role_code": user["role_code"],
        "assigned_lines": json.loads(user["assigned_lines"]) if user.get("assigned_lines") else [],
        "pw_rule_type": user.get("pw_rule_type", "WORKER_4DIGIT"),
        "pw_change_type": user.get("pw_change_type", "MOBILE_QR"),
        "must_change_pw": bool(user.get("must_change_pw") or is_pw_expired),
        "is_pw_expired": is_pw_expired,
        "phone_no": user.get("phone_no", "")
    }

    session_info = {
        "session_token": session_token,
        "csrf_token": csrf_token,
        "expires_at": exp_dt.strftime("%Y-%m-%d %H:%M:%S")
    }

    return True, 200, "로그인 성공", profile, session_info

def create_mobile_reset_token(emp_no, client_ip):
    eno = str(emp_no or "").strip()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    expires_at = datetime.datetime.now().replace(microsecond=0) + datetime.timedelta(minutes=5)

    def _save():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dbo.sec_pw_reset_tokens
                (token_hash, emp_no, expires_at, is_used, created_at, created_ip)
                VALUES (?, ?, ?, 0, SYSUTCDATETIME(), ?);
            """, (token_hash, eno, expires_at, str(client_ip)[:45]))
    with_db_retry(_save)

    return raw_token, expires_at

def verify_and_consume_mobile_token(raw_token, new_password):
    token_hash = hashlib.sha256(str(raw_token).encode('utf-8')).hexdigest()
    now = datetime.datetime.now().replace(microsecond=0)

    def _get_token():
        with get_db_connection() as conn:
            rows = fetch_table_dicts(conn.cursor(), """
                SELECT t.*, u.pw_rule_type, u.user_name
                FROM dbo.sec_pw_reset_tokens t
                JOIN dbo.sec_users u ON t.emp_no = u.emp_no
                WHERE t.token_hash = ? AND t.is_used = 0;
            """, (token_hash,))
            return rows[0] if rows else None

    token_row = with_db_retry(_get_token)
    if not token_row:
        return False, "유효하지 않거나 이미 사용된 변경 링크입니다."

    exp_dt = datetime.datetime.fromisoformat(str(token_row["expires_at"]))
    if exp_dt <= now:
        return False, "인증 유효시간(5분)이 만료되었습니다. 현장 PC에서 QR 코드를 다시 요청하세요."

    emp_no = token_row["emp_no"]
    pw_rule_type = token_row.get("pw_rule_type", "WORKER_4DIGIT")

    valid, msg = validate_password_by_rule(new_password, pw_rule_type, emp_no)
    if not valid:
        return False, msg

    pwd_hash, salt = hash_password(new_password)

    def _update_pw():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE dbo.sec_users
                SET password_hash = ?, password_salt = ?, must_change_pw = 0, failed_login_count = 0, locked_until = NULL, pw_updated_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
                WHERE emp_no = ?;
            """, (pwd_hash, salt, emp_no))
            cur.execute("""
                UPDATE dbo.sec_pw_reset_tokens
                SET is_used = 1, used_at = SYSUTCDATETIME()
                WHERE token_hash = ?;
            """, (token_hash,))
    with_db_retry(_update_pw)

    return True, f"[{token_row['user_name']}] 님의 비밀번호가 안전하게 변경되었습니다."
