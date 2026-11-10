import urllib.parse
"""
(주)도스코 열처리 대시보드 크로스-브라우저 & 전 호기(1, 2, 3, 5, 6, 7호기) 실시간 동기화 및 PLC 온도(PV+SV) 스트리밍 서버
DOSKO Multi-Line (All Lines) & Cross-Browser Real-Time Sync & PLC Temperature (PV + SV) Streaming Server

포트: 8089 (HTTP API with full CORS)
PLC 주소: 192.168.0.3:2004 (LS XGT FEnet Protocol)
수집 레지스터:
  - PV 59채널 (D100..D158) + 라인속도 6채널 (D159..D164)
  - SV 59채널 (D1000..D7000 블록, 각 호기별 +3 오프셋)
수집 주기: 1.5초 (백그라운드 비차단 데몬 스레드)
"""

import os
import sys
import json
import time
import socket
import struct
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import sqlite3
import shutil
import re

ECOUNT_DB_PATHS = [
    r"C:\Users\song9\OneDrive\바탕 화면\test-data\dosko_ecount.db",
    r"C:\Users\song9\OneDrive\바탕 화면\dosko_ecount.db",
    r"Z:\HDD1\생산일지\dosko_ecount.db"
]
db_lock = threading.Lock()

GRADE_CODE_MAP = {
    "SK-5": ("5", "-5", "-53", "-54"),
    "SK5": ("5", "-5", "-53", "-54"),
    "SK-4": ("4", "-4", "-43", "-44"),
    "SK-3": ("3", "-3", "-33", "-34"),
    "SK-2": ("2", "-2", "-23", "-24"),
    "S75C": ("75", "75", "753", "754"),
    "S70C": ("70", "70", "703", "704"),
    "S65C": ("65", "65", "653", "654"),
    "S60C": ("60", "60", "603", "604"),
    "S55C": ("55", "55", "553", "554"),
    "S50C": ("50", "50", "503", "504"),
    "S45C": ("45", "45", "453", "454"),
    "SCM435": ("43", "43", "433", "434"),
    "SKS-51": ("51", "51", "513", "514"),
    "SKS-7": ("7", "-7", "-73", "-74"),
    "SAE6150": ("61", "61", "613", "614"),
    "50CRV4": ("61", "61", "613", "614"),
    "420J2": ("42", "42", "423", "424"),
    "STS301": ("30", "30", "303", "304"),
    "STS304": ("34", "34", "343", "344")
}

COLOR_CODE_MAP = {
    "원재료": "00", "백": "20", "백(R면치)": "22", "백(각면치)": "23", "백(SIDE)": "24",
    "청": "30", "청(R면치)": "32", "청(각면치)": "33", "청(SIDE)": "34",
    "연마": "40", "연": "40", "연마(R면치)": "42", "연마(각면치)": "43", "연마(SIDE)": "44", "연마(각R면치)": "45",
    "황도": "50", "착색": "60", "PO": "70", "PO압연": "71", "PA": "80",
    "임(열)": "90", "임(연)": "91", "임(열+연)": "92", "임(열+S)": "93", "임(열+S+연)": "94", "회색": "30"
}

def make_ecount_item_code_and_spec(steel_grade, thickness, width, cut_length=0, color_name="청", hardness="HRC45"):
    t = float(thickness or 0)
    w = float(width or 0)
    c_len = float(cut_length or 0)
    col = (color_name or "청").strip()
    hard = (hardness or "R").strip().upper().replace(" ", "")
    t_code = f"{int(round(t * 1000)):04d}"
    if c_len > 0:
        w_code = f"{int(round(w)):03d}{int(round(c_len)):03d}"
        spec_str = f"{t:.3f}*{w:.0f}*{c_len:.0f}*({col}){hard}"
    else:
        w_code = f"{int(round(w * 100)):05d}"
        w_disp = f"{w:,.2f}" if w >= 1000 else f"{w:.2f}"
        spec_str = f"{t:.3f}*{w_disp}*({col}){hard}"
    g_prefix = GRADE_CODE_MAP.get(steel_grade, ("5", "-5", "-53", "-54"))[0]
    c_code = COLOR_CODE_MAP.get(col, "30")
    if hard == "R":
        h_code = "001"
    elif hard == "S":
        h_code = "000"
    elif hard.startswith("HRC"):
        num_part = re.sub(r"[^0-9]", "", hard[3:])
        h_code = f"{int(num_part or 45):03d}"
    elif hard.startswith("HV"):
        num_part = re.sub(r"[^0-9]", "", hard[2:])
        h_code = f"{int(num_part or 450):03d}"
    else:
        num_part = re.sub(r"[^0-9.]", "", hard)
        h_code = num_part.zfill(3) if num_part else "001"
    item_code = f"{t_code}{w_code}-{g_prefix}{c_code}-{h_code}"
    return item_code, spec_str

def get_primary_ecount_db():
    for p in ECOUNT_DB_PATHS:
        if os.path.exists(p):
            return p
    return ECOUNT_DB_PATHS[0]

def sync_ecount_db_replicas(primary_path):
    def _worker():
        for dst in ECOUNT_DB_PATHS:
            if dst != primary_path:
                try:
                    if os.path.exists(os.path.dirname(dst)):
                        shutil.copy2(primary_path, dst)
                except Exception:
                    pass
    threading.Thread(target=_worker, daemon=True).start()

def fetch_table_dicts(cur, query, params=()):
    cur.execute(query, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_ecount_overview_payload():
    db_path = get_primary_ecount_db()
    if not os.path.exists(db_path):
        return {"error": "dosko_ecount.db not found", "db_path": db_path}
    with db_lock:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            warehouses = fetch_table_dicts(cur, "SELECT * FROM ecount_warehouses ORDER BY wh_code")
            projects = fetch_table_dicts(cur, "SELECT * FROM ecount_projects ORDER BY project_code")
            mgmt_items = fetch_table_dicts(cur, "SELECT * FROM ecount_mgmt_items ORDER BY mgmt_code")
            steel_grades = fetch_table_dicts(cur, "SELECT * FROM ecount_steel_grades ORDER BY grade_name")
            colors = fetch_table_dicts(cur, "SELECT * FROM ecount_colors ORDER BY color_code")
            raw_inbounds = fetch_table_dicts(cur, "SELECT * FROM proc_1_raw_inbounds ORDER BY inbound_id DESC LIMIT 100")
            heat_treatment = fetch_table_dicts(cur, "SELECT * FROM proc_2_heat_treatment ORDER BY heat_id DESC LIMIT 120")
            grinding_wait_stock = fetch_table_dicts(cur, "SELECT * FROM proc_3_grinding_wait_stock ORDER BY wait_id DESC LIMIT 100")
            grinding_production = fetch_table_dicts(cur, "SELECT * FROM proc_4_grinding_production ORDER BY grind_id DESC LIMIT 100")
            finished_and_packing = fetch_table_dicts(cur, "SELECT * FROM proc_5_finished_and_packing ORDER BY pack_id DESC LIMIT 150")
            erp_slips = fetch_table_dicts(cur, "SELECT * FROM ecount_erp_slips ORDER BY slip_id DESC LIMIT 250")
            serial_history = fetch_table_dicts(cur, "SELECT * FROM ecount_serial_issue_history ORDER BY updated_at DESC")
            daily_report_details = fetch_table_dicts(cur, "SELECT * FROM ecount_daily_report_details ORDER BY report_date DESC, seq_no ASC LIMIT 400")
            daily_report_summary = fetch_table_dicts(cur, "SELECT * FROM ecount_daily_report_summary ORDER BY report_date DESC LIMIT 60")
            delivery_slips = fetch_table_dicts(cur, "SELECT * FROM ecount_delivery_slips ORDER BY delivery_id DESC LIMIT 150")
            packing_lists = fetch_table_dicts(cur, "SELECT * FROM ecount_packing_lists ORDER BY packing_id DESC LIMIT 150")
            address_book = fetch_table_dicts(cur, "SELECT * FROM ecount_address_book ORDER BY addr_id DESC")

            general_map = {}
            wip_map = {}
            for sh in serial_history:
                if sh["history_type"] == "generalSerialIssueHistory":
                    general_map[sh["record_key"]] = {"lastSerial": sh["last_suffix"], "updatedAt": sh["updated_at"]}
                elif sh["history_type"] == "wipSerialIssueHistory":
                    wip_map[sh["record_key"]] = {"lastSuffix": sh["last_suffix"], "updatedAt": sh["updated_at"]}

            return {
                "status": "ok",
                "db_path": db_path,
                "warehouses": warehouses,
                "projects": projects,
                "mgmt_items": mgmt_items,
                "steel_grades": steel_grades,
                "colors": colors,
                "raw_inbounds": raw_inbounds,
                "heat_treatment": heat_treatment,
                "grinding_wait_stock": grinding_wait_stock,
                "grinding_production": grinding_production,
                "finished_and_packing": finished_and_packing,
                "erp_slips": erp_slips,
                "serial_history": serial_history,
                "serial_extension_json": {
                    "version": 1,
                    "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "generalSerialIssueHistory": general_map,
                    "wipSerialIssueHistory": wip_map
                },
                "daily_report_details": daily_report_details,
                "daily_report_summary": daily_report_summary,
                "delivery_slips": delivery_slips,
                "packing_lists": packing_lists,
                "address_book": address_book
            }
        finally:
            conn.close()

PORT = 8089
SHARED_FILE_NETWORK = r"Z:\HDD1\생산일지\dosko_shared_state.json"
SHARED_FILE_LOCAL = r"C:\Users\song9\.gemini\antigravity\brain\23a680d4-8e31-4cb3-a873-f48a7c7e79e9\scratch\dosko_shared_state.json"

PLC_IP = "192.168.0.3"
PLC_PORT = 2004

state_lock = threading.Lock()

server_state = {
    "version": 1,
    "last_updated": time.time(),
    "specs": {},      # { "L1": {...}, "L2": {...}, ... }
    "workers": {"L1": "-", "L5": "-", "L6": "-"},    
    "coils": {},      
    "statuses": {"L1": "정상가동", "L2": "정상가동", "L3": "정상가동", "L5": "비가동", "L6": "비가동", "L7": "정상가동"},   
    "work_orders": {},
    "cleared_specs": ["L5", "L6"],
    "cleared_workers": ["L5", "L6"],  # 명시적 초기화 라인
    "live_power": {
        "timestamp": time.time(),
        "total_kwh": 3779.3,
        "peak_kw": 362.0,
        "target_peak": 420.0,
        "lines": {
            "L1": {"cur_kw": 78.4, "tot_kwh": 1413.2},
            "L2": {"cur_kw": 107.1, "tot_kwh": 1162.1},
            "L3": {"cur_kw": 71.7, "tot_kwh": 826.0},
            "L5": {"cur_kw": 7.3, "tot_kwh": 30.9},
            "L6": {"cur_kw": 0.5, "tot_kwh": 0.2},
            "L7": {"cur_kw": 30.5, "tot_kwh": 314.8}
        }
    },
    "plc_stream": {
        "status": "initializing",
        "timestamp": time.time(),
        "read_ms": 0,
        "consecutive_errors": 0,
        "lines": {},
        "raw_registers": {
            "temperatures": [],
            "speeds": [],
            "svs": []
        }
    }
}

# 전 호기(1, 2, 3, 5, 6, 7호기) 59개 SV 주소 전수 정밀 매핑 테이블 (cMT Viewer 1:1 일치)
ALL_SV_ADDRS = [
    # 1호기 (15개)
    1005, 1015, 1025, 1035, 1045, 1055, # 가열 6개 (SV: 960)
    1063, 1073, 1083, 1093,             # 템퍼링 4개 (SV: 479)
    1103, 1113, 1123,                   # 레베링 3개 (SV: 540)
    1133, 1143,                         # 납로 2개 (SV: 350)
    # 2호기 (12개)
    2003, 2013, 2023, 2033, 2043, 2053, # 가열 6개 (SV: 970)
    2063, 2073, 2083,                   # 템퍼링 3개 (SV: 567)
    2093, 2103,                         # 레베링 2개 (SV: 550)
    2113,                               # 오일 1개 (SV: 100)
    # 3호기 (9개)
    3003, 3013, 3023, 3033,             # 가열 4개 (SV: 980)
    3043, 3053,                         # 템퍼링 2개 (SV: 499)
    3063, 3073,                         # 레베링 2개 (SV: 480)
    3083,                               # 오일 1개 (SV: 100)
    # 5호기 (10개)
    5003, 5013, 5023, 5033, 5043,       # 가열 5개 (SV: 975)
    5053, 5063, 5073,                   # 템퍼링 3개 (SV: 541)
    5083, 5093,                         # 레베링 2개 (SV: 500)
    # 6호기 (8개)
    6003, 6013, 6023,                   # 가열 3개 (SV: 950)
    6033, 6043,                         # 템퍼링 2개 (SV: 542)
    6053, 6063,                         # 레베링 2개 (SV: 35, 34)
    6073,                               # 오일 1개 (SV: 34)
    # 7호기 (5개)
    7003, 7013, 7023,                   # 가열 3개 (SV: 960)
    7033, 7043                          # 템퍼링 2개 (SV: 500)
]

def load_initial_state():
    for p in [SHARED_FILE_NETWORK, SHARED_FILE_LOCAL]:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    with state_lock:
                        for k in ["specs", "workers", "coils", "statuses", "work_orders"]:
                            if k in data and isinstance(data[k], dict):
                                server_state[k].update(data[k])
                        if "cleared_workers" in data and isinstance(data["cleared_workers"], list):
                            server_state["cleared_workers"] = list(set(server_state.get("cleared_workers", []) + data["cleared_workers"]))
                        if "cleared_specs" in data and isinstance(data["cleared_specs"], list):
                            server_state["cleared_specs"] = list(set(server_state["cleared_specs"] + data["cleared_specs"]))
                        # L1은 항상 specs에서 배제 보장
                        # server_state["specs"].pop("L1", None)
                        server_state["specs"].pop("2026-10-29_L1", None)
                        server_state["specs"].pop("2026-10-28_L1", None)
                        if "L1" not in server_state["statuses"]:
                            server_state["statuses"]["L1"] = "정상가동"
                    print(f"[동기화 서버] 공유 상태 로드 성공: {p}")
                    return
            except Exception as e:
                print(f"[동기화 서버] 파일 로드 오류: {e}")

def _save_state_disk_worker(data_to_write):
    try:
        os.makedirs(os.path.dirname(SHARED_FILE_LOCAL), exist_ok=True)
        with open(SHARED_FILE_LOCAL, 'w', encoding='utf-8') as f:
            f.write(data_to_write)
    except Exception as e:
        pass

    try:
        os.makedirs(os.path.dirname(SHARED_FILE_NETWORK), exist_ok=True)
        with open(SHARED_FILE_NETWORK, 'w', encoding='utf-8') as f:
            f.write(data_to_write)
    except Exception as e:
        pass

def save_state_to_files():
    with state_lock:
        persistent_data = {
            "version": server_state["version"],
            "last_updated": server_state["last_updated"],
            "specs": dict(server_state["specs"]),
            "workers": dict(server_state["workers"]),
            "coils": dict(server_state["coils"]),
            "statuses": dict(server_state.get("statuses", {})),
            "work_orders": dict(server_state.get("work_orders", {})),
            "cleared_specs": list(server_state.get("cleared_specs", [])),
            "cleared_workers": list(server_state.get("cleared_workers", []))
        }
    data = json.dumps(persistent_data, ensure_ascii=False, indent=2)
    t = threading.Thread(target=_save_state_disk_worker, args=(data,), daemon=True)
    t.start()
    return

def make_plc_read_packet(addrs, seq=1):
    company_id = b'LSIS-XGT\x00\x00'
    plc_info = b'\x00\x00'
    cpu_info = b'\xa0'
    source = b'\x33'
    blocks = [struct.pack('<H', len(f'%DW{a}'.encode('ascii'))) + f'%DW{a}'.encode('ascii') for a in addrs]
    app_data = struct.pack('<HHH', 0x0054, 0x0002, 0x0000) + struct.pack('<H', len(addrs)) + b''.join(blocks)
    header_pre = company_id + plc_info + cpu_info + source + struct.pack('<H', seq) + struct.pack('<H', len(app_data))
    checksum = sum(header_pre) & 0xFF
    return header_pre + bytes([0, checksum]) + app_data

def poll_plc_all():
    """D100..D164 (PV 59개 + 속도 6개) 및 59개 SV 레지스터 일괄 수집"""
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect((PLC_IP, PLC_PORT))
        
        # 1. PV (D100~D164: 65개)
        pv_chunks = [
            list(range(100, 116)),
            list(range(116, 132)),
            list(range(132, 148)),
            list(range(148, 164)),
            [164]
        ]
        all_pv_vals = []
        for chunk in pv_chunks:
            pkt = make_plc_read_packet(chunk)
            s.sendall(pkt)
            resp = s.recv(1024)
            if len(resp) < 30:
                raise ValueError(f"비정상 PV 응답 길이: {len(resp)} 바이트")
            data_r = resp[20:]
            cmd, dtype, resv, err_state = struct.unpack('<HHHH', data_r[:8])
            if err_state != 0:
                raise ValueError(f"PLC 에러 상태 코드: {err_state}")
            block_cnt = struct.unpack('<H', data_r[8:10])[0]
            offset = 10
            for _ in range(block_cnt):
                dlen = struct.unpack('<H', data_r[offset:offset+2])[0]
                val = struct.unpack('<H', data_r[offset+2:offset+4])[0]
                all_pv_vals.append(val)
                offset += 2 + dlen
                
        # 2. SV (59개 주소: 16, 16, 16, 11)
        sv_chunks = [
            ALL_SV_ADDRS[0:16],
            ALL_SV_ADDRS[16:32],
            ALL_SV_ADDRS[32:48],
            ALL_SV_ADDRS[48:59]
        ]
        all_sv_vals = []
        for chunk in sv_chunks:
            pkt = make_plc_read_packet(chunk)
            s.sendall(pkt)
            resp = s.recv(1024)
            data_r = resp[20:]
            block_cnt = struct.unpack('<H', data_r[8:10])[0]
            offset = 10
            for _ in range(block_cnt):
                dlen = struct.unpack('<H', data_r[offset:offset+2])[0]
                val = struct.unpack('<H', data_r[offset+2:offset+4])[0]
                all_sv_vals.append(val)
                offset += 2 + dlen
                
        s.close()
        elapsed = (time.time() - t0) * 1000
        return all_pv_vals, all_sv_vals, elapsed
    except Exception as e:
        try:
            s.close()
        except:
            pass
        raise e

# 일시적 통신 노이즈/센서 0 글리치 방지 필터 캐시 (3회 이하 0값은 직전 유효온도 유지)
last_valid_pv = [None] * 59
zero_streak_pv = [0] * 59
last_valid_spd = [None] * 6
zero_streak_spd = [0] * 6

def plc_collector_loop():
    """백그라운드에서 1.5초마다 PLC PV 및 SV 온도를 수집하여 server_state에 실시간 저장 (0 글리치 필터 적용)"""
    global last_valid_pv, zero_streak_pv, last_valid_spd, zero_streak_spd
    print(f"[PLC 스트리머] {PLC_IP}:{PLC_PORT} 수집 스레드 시작 (PV+속도 65개 + SV 59개, 0 글리치 필터 활성)")
    while True:
        try:
            pv_vals, sv_vals, elapsed = poll_plc_all()
            if len(pv_vals) >= 65 and len(sv_vals) >= 59:
                raw_t_vals = pv_vals[:59]
                raw_s_vals = pv_vals[59:65]
                
                # [개선] 온도 0 글리치 필터링: 가열 중 일시적으로 0이 들어오면 직전 정상 온도 유지 (최대 3회/약 4.5초)
                t_vals = list(raw_t_vals)
                for i in range(len(t_vals)):
                    v = t_vals[i]
                    if v == 0:
                        if last_valid_pv[i] is not None and last_valid_pv[i] > 50:
                            zero_streak_pv[i] += 1
                            if zero_streak_pv[i] <= 3:
                                t_vals[i] = last_valid_pv[i] # 직전 정상 온도 유지
                            else:
                                last_valid_pv[i] = 0
                        else:
                            last_valid_pv[i] = 0
                    else:
                        zero_streak_pv[i] = 0
                        last_valid_pv[i] = v
                
                # [개선] 속도 0 글리치 필터링: 주행 중 순간 1프레임 0 누락 방지
                s_vals = list(raw_s_vals)
                for i in range(len(s_vals)):
                    sv = s_vals[i]
                    if sv == 0:
                        if last_valid_spd[i] is not None and last_valid_spd[i] > 10:
                            zero_streak_spd[i] += 1
                            if zero_streak_spd[i] <= 2:
                                s_vals[i] = last_valid_spd[i]
                            else:
                                last_valid_spd[i] = 0
                        else:
                            last_valid_spd[i] = 0
                    else:
                        zero_streak_spd[i] = 0
                        last_valid_spd[i] = sv
                
                # 라인별 분할 (PV & SV)
                # 1:1 정밀 채널 매핑 (59채널 PV & 59채널 SV)
                # L1 (15개: 0..15) -> 가열 6개, 템퍼링 4개, 레베링 3개, 납로 2개
                l1_heat = t_vals[0:6]
                l1_temp = t_vals[6:10]
                l1_level = t_vals[10:13]
                l1_lead = t_vals[13:15]
                l1_heat_sv = sv_vals[0:6]
                l1_temp_sv = sv_vals[6:10]
                l1_level_sv = sv_vals[10:13]
                l1_lead_sv = sv_vals[13:15]
                
                # L2 (12개: 15..27) -> 가열 6개, 템퍼링 3개, 레베링 2개, 오일 1개
                l2_heat = t_vals[15:21]
                l2_temp = t_vals[21:24]
                l2_level = t_vals[24:26]
                l2_lead = [t_vals[26]]  # 오일 1개 (DOM ID: pv-L2-lead-1)
                l2_heat_sv = sv_vals[15:21]
                l2_temp_sv = sv_vals[21:24]
                l2_level_sv = sv_vals[24:26]
                l2_lead_sv = [sv_vals[26]]
                
                # L3 (9개: 27..36) -> 가열 4개, 템퍼링 2개, 레베링 2개, 오일 1개
                l3_heat = t_vals[27:31]
                l3_temp = t_vals[31:33]
                l3_level = t_vals[33:35]
                l3_lead = [t_vals[35]]  # 오일 1개 (DOM ID: pv-L3-lead-1)
                l3_heat_sv = sv_vals[27:31]
                l3_temp_sv = sv_vals[31:33]
                l3_level_sv = sv_vals[33:35]
                l3_lead_sv = [sv_vals[35]]
                
                # L5 (10개: 36..46) -> 가열 5개, 템퍼링 3개, 레베링 2개
                l5_heat = t_vals[36:41]
                l5_temp = t_vals[41:44]
                l5_level = t_vals[44:46]
                l5_heat_sv = sv_vals[36:41]
                l5_temp_sv = sv_vals[41:44]
                l5_level_sv = sv_vals[44:46]
                
                # L6 (8개: 46..54) -> 가열 3개, 템퍼링 2개, 레베링 2개, 오일 1개
                l6_heat = t_vals[46:49]
                l6_temp = t_vals[49:51]
                l6_level = t_vals[51:53]
                l6_lead = [t_vals[53]]  # 오일 1개 (DOM ID: pv-L6-lead-1)
                l6_heat_sv = sv_vals[46:49]
                l6_temp_sv = sv_vals[49:51]
                l6_level_sv = sv_vals[51:53]
                l6_lead_sv = [sv_vals[53]]
                
                # L7 (5개: 54..59) -> 가열 3개, 템퍼링 2개
                l7_heat = t_vals[54:57]
                l7_temp = t_vals[57:59]
                l7_heat_sv = sv_vals[54:57]
                l7_temp_sv = sv_vals[57:59]
                
                # 속도 (6개)
                speed_l1 = s_vals[0]
                speed_l2 = s_vals[1]
                speed_l3 = s_vals[2]
                speed_l5 = s_vals[3]
                speed_l6 = s_vals[4]
                speed_l7 = s_vals[5]
                
                now_ts = time.time()
                with state_lock:
                    server_state["plc_stream"] = {
                        "status": "connected",
                        "timestamp": now_ts,
                        "read_ms": round(elapsed, 1),
                        "consecutive_errors": 0,
                        "lines": {
                            "L1": {
                                "speed": speed_l1,
                                "zones": {
                                    "heat": l1_heat, "temp": l1_temp, "level": l1_level, "lead": l1_lead,
                                    "heat_sv": l1_heat_sv, "temp_sv": l1_temp_sv, "level_sv": l1_level_sv, "lead_sv": l1_lead_sv,
                                    "가열": l1_heat, "템퍼링": l1_temp, "레베링": l1_level, "납로": l1_lead
                                }
                            },
                            "L2": {
                                "speed": speed_l2,
                                "zones": {
                                    "heat": l2_heat, "temp": l2_temp, "level": l2_level, "lead": l2_lead,
                                    "heat_sv": l2_heat_sv, "temp_sv": l2_temp_sv, "level_sv": l2_level_sv, "lead_sv": l2_lead_sv,
                                    "가열": l2_heat, "템퍼링": l2_temp, "레베링": l2_level, "오일": l2_lead
                                }
                            },
                            "L3": {
                                "speed": speed_l3,
                                "zones": {
                                    "heat": l3_heat, "temp": l3_temp, "level": l3_level, "lead": l3_lead,
                                    "heat_sv": l3_heat_sv, "temp_sv": l3_temp_sv, "level_sv": l3_level_sv, "lead_sv": l3_lead_sv,
                                    "가열": l3_heat, "템퍼링": l3_temp, "레베링": l3_level, "오일": l3_lead
                                }
                            },
                            "L5": {
                                "speed": speed_l5,
                                "zones": {
                                    "heat": l5_heat, "temp": l5_temp, "level": l5_level,
                                    "heat_sv": l5_heat_sv, "temp_sv": l5_temp_sv, "level_sv": l5_level_sv,
                                    "가열": l5_heat, "템퍼링": l5_temp, "레베링": l5_level
                                }
                            },
                            "L6": {
                                "speed": speed_l6,
                                "zones": {
                                    "heat": l6_heat, "temp": l6_temp, "level": l6_level, "lead": l6_lead,
                                    "heat_sv": l6_heat_sv, "temp_sv": l6_temp_sv, "level_sv": l6_level_sv, "lead_sv": l6_lead_sv,
                                    "가열": l6_heat, "템퍼링": l6_temp, "레베링": l6_level, "오일": l6_lead
                                }
                            },
                            "L7": {
                                "speed": speed_l7,
                                "zones": {
                                    "heat": l7_heat, "temp": l7_temp,
                                    "heat_sv": l7_heat_sv, "temp_sv": l7_temp_sv,
                                    "가열": l7_heat, "템퍼링": l7_temp
                                }
                            }
                        },
                        "raw_registers": {
                            "temperatures": t_vals,
                            "speeds": s_vals,
                            "svs": sv_vals
                        }
                    }
        except Exception as e:
            with state_lock:
                err_cnt = server_state["plc_stream"].get("consecutive_errors", 0) + 1
                server_state["plc_stream"]["status"] = "offline" if err_cnt > 3 else "warning"
                server_state["plc_stream"]["consecutive_errors"] = err_cnt
                server_state["plc_stream"]["last_error"] = str(e)
        
        time.sleep(1.5)

# ==============================================================================
# HTTP API 핸들러
# ==============================================================================
class SyncHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data, code=200):
        try:
            payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except Exception as e:
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        # 1. Pro Mode Dashboard (기본 실시간 통합관제)
        pro_paths = ["/", "/index.html", "/dashboard", "/dosko_dashboard.html", "/pro", "/대시보드"]
        # URL decode path for korean matching
        req_path = urllib.parse.unquote(self.path)
        
        if req_path in pro_paths or self.path in pro_paths:
            pro_candidates = [
                r"C:\Users\song9\OneDrive\바탕 화면\도스코_열처리_대시보드.html",
                r"C:\Users\song9\OneDrive\바탕 화면\dosko_dashboard.html",
                r"C:\Users\song9\.gemini\antigravity\brain\23a680d4-8e31-4cb3-a873-f48a7c7e79e9\dosko_energy_process_dashboard.html",
                r"Z:\HDD1\생산일지\도스코_열처리_대시보드.html",
                r"Z:\HDD1\생산일지\dosko_dashboard.html"
            ]
            for p in pro_candidates:
                if os.path.exists(p):
                    try:
                        with open(p, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self._set_cors_headers()
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(content)))
                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
                        self.send_header("Pragma", "no-cache")
                        self.send_header("Expires", "0")
                        self.end_headers()
                        self.wfile.write(content)
                        return
                    except Exception as e:
                        pass
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Error: Pro dashboard file not found")
            return

        # 2. Easy Mode (현장용 생산일지 및 이지모드)
        easy_paths = ["/easy", "/dosko_easy.html", "/easy.html", "/이지", "/현장", "/field", "/이지모드", "/현장용"]
        if req_path in easy_paths or self.path in easy_paths:
            easy_candidates = [
                r"C:\Users\song9\OneDrive\바탕 화면\도스코_열처리_대시보드_이지모드.html",
                r"C:\Users\song9\OneDrive\바탕 화면\도스코_열처리_대시보드_현장용.html",
                r"C:\Users\song9\OneDrive\바탕 화면\dosko_easy.html",
                r"C:\Users\song9\.gemini\antigravity\brain\23a680d4-8e31-4cb3-a873-f48a7c7e79e9\dosko_easy.html",
                r"Z:\HDD1\생산일지\도스코_열처리_대시보드_이지모드.html",
                r"Z:\HDD1\생산일지\도스코_열처리_대시보드_현장용.html",
                r"Z:\HDD1\생산일지\dosko_easy.html"
            ]
            for p in easy_candidates:
                if os.path.exists(p):
                    try:
                        with open(p, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self._set_cors_headers()
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(content)))
                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
                        self.send_header("Pragma", "no-cache")
                        self.send_header("Expires", "0")
                        self.end_headers()
                        self.wfile.write(content)
                        return
                    except Exception as e:
                        pass
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Error: Easy dashboard file not found")
            return

        if self.path == "/health":
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if self.path == "/api/ecount/overview" or self.path.startswith("/api/ecount/overview?"):
            self._send_json(get_ecount_overview_payload())
            return

        if self.path == "/api/state":
            with state_lock:
                resp_data = {
                    "version": server_state["version"],
                    "timestamp": server_state["last_updated"],
                    "specs": server_state["specs"],
                    "workers": server_state["workers"],
                    "coils": server_state["coils"],
                    "statuses": server_state.get("statuses", {}),
                    "cleared_specs": server_state.get("cleared_specs", []),
                    "cleared_workers": server_state.get("cleared_workers", []),
                    "work_orders": server_state.get("work_orders", {}),
                    "line_work_state": server_state.get("line_work_state", {}),
                    "live_power": server_state.get("live_power", {}),
                    "plc_stream": server_state.get("plc_stream", {})
                }
            payload = json.dumps(resp_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        
        if self.path == "/api/ecount/heat-production":
            try:
                data = json.loads(body)
                db_path = get_primary_ecount_db()
                with db_lock:
                    conn = sqlite3.connect(db_path)
                    try:
                        cur = conn.cursor()
                        work_date = data.get("work_date") or time.strftime("%Y-%m-%d")
                        date_compact = work_date.replace("-", "")
                        doc_date_no = f"{work_date.replace('-', '/')} -1"
                        project_name = data.get("project_name") or "2호기"
                        worker_name = data.get("worker_name") or "송구현"
                        grade = data.get("steel_grade") or "SK-5"
                        in_t = float(data.get("in_t") or data.get("target_t") or 1.2)
                        in_w = float(data.get("in_w") or data.get("target_w") or 100.0)
                        target_t = float(data.get("target_t") or in_t)
                        target_w = float(data.get("target_w") or in_w)
                        color = data.get("color") or "청"
                        hardness = (data.get("hardness") or "HRC46").replace(" ", "")
                        raw_lot = data.get("in_lot") or f"{date_compact}-R01"
                        in_kg = float(data.get("in_kg") or 0)
                        prod_kg = float(data.get("prod_kg") or 0)
                        qty_ea = int(data.get("coils_count") or data.get("qty_ea") or 1)
                        unit_kg = round(prod_kg / max(1, qty_ea), 1) if prod_kg > 0 else 0
                        wip_kg = float(data.get("wip_kg") or 0)
                        scrap_kg = float(data.get("scrap_kg") or max(0.0, round(in_kg - prod_kg - wip_kg, 1)))
                        prod_mgmt = data.get("prod_mgmt") or ("수냉열처리" if ("6" in project_name or "7" in project_name) else "열처리")
                        in_wh = data.get("in_wh") or ("01.소폭" if ("6" in project_name or "7" in project_name) and "연" in color else ("01.연마" if "연" in color else "01.완제품"))
                        next_route = "NARROW_WAIT" if in_wh == "01.소폭" else ("GRIND_WAIT" if in_wh == "01.연마" else "FINISHED")

                        # Serial generation (handleGeneralProduction compatible)
                        disc = re.sub(r"[^0-9]", "", project_name) or "1"
                        rec_key = f"{date_compact}-{disc}"
                        cur.execute("SELECT last_suffix FROM ecount_serial_issue_history WHERE history_type='generalSerialIssueHistory' AND record_key=?", (rec_key,))
                        row_sh = cur.fetchone()
                        next_suffix = (row_sh[0] + 1) if row_sh else (int(disc) * 100 + 1)
                        prod_lot = data.get("prod_lot") or f"{date_compact}-{next_suffix}"
                        now_ms = int(time.time() * 1000)
                        cur.execute("""
                            INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                            VALUES ('generalSerialIssueHistory', ?, ?, ?, ?)
                            ON CONFLICT(history_type, record_key) DO UPDATE SET
                                last_suffix=excluded.last_suffix, last_serial_full=excluded.last_serial_full, updated_at=excluded.updated_at
                        """, (rec_key, next_suffix, prod_lot, now_ms))

                        # WIP serial generation (handleWipProduction compatible: -1, -2...)
                        wip_lot = None
                        if wip_kg > 0:
                            cur.execute("SELECT last_suffix FROM ecount_serial_issue_history WHERE history_type='wipSerialIssueHistory' AND record_key=?", (raw_lot,))
                            row_wip = cur.fetchone()
                            wip_suf = (row_wip[0] + 1) if row_wip else 1
                            wip_lot = f"{raw_lot}-{wip_suf}"
                            cur.execute("""
                                INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                                VALUES ('wipSerialIssueHistory', ?, ?, ?, ?)
                                ON CONFLICT(history_type, record_key) DO UPDATE SET
                                    last_suffix=excluded.last_suffix, last_serial_full=excluded.last_serial_full, updated_at=excluded.updated_at
                            """, (raw_lot, wip_suf, wip_lot, now_ms))

                        raw_item_cd, raw_spec = make_ecount_item_code_and_spec(grade, in_t, in_w, 0, "원재료", "R")
                        prod_item_cd, prod_spec = make_ecount_item_code_and_spec(grade, target_t, target_w, 0, color, hardness)

                        cur.execute("""
                            INSERT INTO proc_2_heat_treatment (
                                doc_date_no, work_date, project_name, worker_name, out_wh, consume_mgmt,
                                raw_item_code, raw_steel_grade, raw_thickness, raw_width, raw_cut_length, raw_spec_full, raw_lot_no,
                                input_unit_kg, input_qty_ea, input_total_kg, wip_return_kg, wip_lot_no,
                                next_route, in_wh, prod_mgmt, prod_item_code, prod_steel_grade, prod_thickness, prod_width, prod_cut_length,
                                prod_color, prod_hardness, prod_spec_full, prod_lot_no, unit_weight_kg, qty_ea, total_weight_kg, scrap_kg, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, work_date, project_name, worker_name, "0.도스코", "투입",
                            raw_item_cd, grade, in_t, in_w, 0, raw_spec, raw_lot,
                            in_kg, 1, in_kg, (-wip_kg if wip_kg > 0 else 0), wip_lot,
                            next_route, in_wh, prod_mgmt, prod_item_cd, grade, target_t, target_w, 0,
                            color, hardness, prod_spec, prod_lot, unit_kg, qty_ea, prod_kg, scrap_kg, data.get("remarks", "")
                        ))
                        heat_id = cur.lastrowid

                        # Route to proc_3_grinding_wait_stock (01.연마 / 01.소폭) or proc_5_finished_and_packing (01.완제품 / 02.포장반)
                        if in_wh in ("01.연마", "01.소폭"):
                            cur.execute("""
                                INSERT OR REPLACE INTO proc_3_grinding_wait_stock (
                                    wh_code, source_heat_id, source_project, prod_date, heat_lot_no, item_code,
                                    steel_grade, thickness, width, cut_length, color_name, hardness_display, spec_full,
                                    unit_weight_kg, init_qty_ea, remain_qty_ea, init_weight_kg, used_weight_kg, remain_weight_kg, status, remarks
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'WAITING',?)
                            """, (
                                in_wh, heat_id, project_name, work_date, prod_lot, prod_item_cd,
                                grade, target_t, target_w, 0, color, hardness, prod_spec,
                                unit_kg, qty_ea, qty_ea, prod_kg, 0, prod_kg, f"{project_name} 열처리 생산 -> 연마대기 입고"
                            ))
                        else:
                            stage = "EXPORT_WAIT" if in_wh == "02.포장반" else "FINISHED_STOCK"
                            cur.execute("""
                                INSERT INTO proc_5_finished_and_packing (
                                    doc_date_no, process_stage, project_name, mgmt_item, out_wh, in_wh,
                                    source_type, source_lot_no, pack_lot_no, item_code, steel_grade, thickness, width, cut_length,
                                    color_name, hardness_display, spec_full, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, worker_name, remarks
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (
                                doc_date_no, stage, project_name, prod_mgmt, "0.도스코", in_wh,
                                "HEAT", prod_lot, (f"{date_compact}-P01" if in_wh == "02.포장반" else None), prod_item_cd, grade, target_t, target_w, 0,
                                color, hardness, prod_spec, unit_kg, qty_ea, prod_kg, prod_kg, worker_name, data.get("remarks", "")
                            ))

                        # Ecount ERP Slips (E040407): 1) 투입 소모행, 2) 재공 소모행(수량=-1, 단위환산량=+wip_kg, 투입량=-wip_kg), 3) 생산행
                        cur.execute("""
                            INSERT INTO ecount_erp_slips (
                                doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                                consume_item_name, consume_spec, consume_serial_lot, consume_item_code,
                                unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name, scrap_kg, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, "송구현", project_name, "투입", worker_name,
                            grade, raw_spec, raw_lot, raw_item_cd,
                            in_kg, 1, in_kg, 0, in_kg, "0.도스코", in_wh, 0, "원소재 투입"
                        ))
                        if wip_kg > 0 and wip_lot:
                            cur.execute("""
                                INSERT INTO ecount_erp_slips (
                                    doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                                    consume_item_name, consume_spec, consume_serial_lot, consume_item_code,
                                    unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name, scrap_kg, remarks
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (
                                doc_date_no, "송구현", project_name, "재공", worker_name,
                                grade, raw_spec, wip_lot, raw_item_cd,
                                wip_kg, -1, -wip_kg, 0, -wip_kg, "0.도스코", "0.도스코", 0, f"재공환원(수량-1, 단위환산량+{wip_kg})"
                            ))
                        cur.execute("""
                            INSERT INTO ecount_erp_slips (
                                doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                                prod_item_code, prod_item_name, prod_spec, color_name, prod_serial_lot,
                                unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name, scrap_kg, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, "송구현", project_name, prod_mgmt, worker_name,
                            prod_item_cd, grade, prod_spec, color, prod_lot,
                            unit_kg, qty_ea, prod_kg, prod_kg, round(in_kg - wip_kg, 1), "0.도스코", in_wh, scrap_kg, f"{in_wh} 입고"
                        ))

                        # Daily report details update
                        spec_norm = f"{target_t:.3f}*{target_w:.2f}"
                        is_cool = ("수냉" in prod_mgmt or "6" in project_name or "7" in project_name)
                        div_str = color if is_cool else (re.sub(r"[^0-9]", "", project_name) or "1")
                        cur.execute("""
                            INSERT INTO ecount_daily_report_details (
                                report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized,
                                division_or_color, heat_qty_kg, cool_qty_kg, grind_qty_kg, remarks
                            ) VALUES (?, 'PROD', 1, ?, ?, ?, ?, ?, ?, 0, ?)
                        """, (
                            work_date, ("수냉" if is_cool else "열처리"), grade, spec_norm, div_str,
                            (0 if is_cool else prod_kg), (prod_kg if is_cool else 0), f"LOT:{prod_lot}"
                        ))
                        conn.commit()
                    finally:
                        conn.close()
                sync_ecount_db_replicas(db_path)
                self._send_json({"status": "ok", "prod_lot": prod_lot, "wip_lot": wip_lot, "in_wh": in_wh, "prod_item_cd": prod_item_cd})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path == "/api/ecount/grinding-production":
            try:
                data = json.loads(body)
                db_path = get_primary_ecount_db()
                with db_lock:
                    conn = sqlite3.connect(db_path)
                    try:
                        cur = conn.cursor()
                        work_date = data.get("work_date") or time.strftime("%Y-%m-%d")
                        date_compact = work_date.replace("-", "")
                        doc_date_no = f"{work_date.replace('-', '/')} -3"
                        project_name = data.get("project_name") or "연마"
                        is_water_grind = ("수냉" in project_name or data.get("line_id") == "L8")
                        if is_water_grind:
                            project_name = "수냉연마"
                        worker_name = data.get("worker_name") or "송구현"
                        wait_id = data.get("wait_id")
                        out_wh = data.get("out_wh") or ("01.소폭" if is_water_grind else "01.연마")
                        in_wh = data.get("in_wh") or "01.완제품"
                        grade = data.get("steel_grade") or "SK-5"
                        in_t = float(data.get("in_t") or data.get("target_t") or 1.2)
                        in_w = float(data.get("in_w") or data.get("target_w") or 121.0)
                        prod_t = float(data.get("target_t") or in_t)
                        prod_w = float(data.get("target_w") or in_w)
                        prod_color = data.get("color") or "연마(SIDE)"
                        hardness = (data.get("hardness") or "HRC45").replace(" ", "")
                        heat_lot = data.get("heat_lot_no") or data.get("in_lot") or f"{date_compact}-301"
                        in_kg = float(data.get("in_kg") or 0)
                        prod_kg = float(data.get("prod_kg") or 0)
                        qty_ea = int(data.get("qty_ea") or data.get("coils_count") or 1)
                        unit_kg = round(prod_kg / max(1, qty_ea), 1) if prod_kg > 0 else 0
                        wip_kg = float(data.get("wip_kg") or 0)
                        scrap_kg = float(data.get("scrap_kg") or max(0.0, round(in_kg - prod_kg - wip_kg, 1)))
                        cems_kwh = float(data.get("cems_power_kwh") or 42.5)

                        # Serial generation: 800번대(수냉연마) or 900번대(연마)
                        disc = "8" if is_water_grind else "9"
                        rec_key = f"{date_compact}-{disc}"
                        cur.execute("SELECT last_suffix FROM ecount_serial_issue_history WHERE history_type='generalSerialIssueHistory' AND record_key=?", (rec_key,))
                        row_sh = cur.fetchone()
                        next_suffix = (row_sh[0] + 1) if row_sh else (int(disc) * 100 + 1)
                        prod_lot = data.get("prod_lot") or f"{date_compact}-{next_suffix}"
                        now_ms = int(time.time() * 1000)
                        cur.execute("""
                            INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                            VALUES ('generalSerialIssueHistory', ?, ?, ?, ?)
                            ON CONFLICT(history_type, record_key) DO UPDATE SET
                                last_suffix=excluded.last_suffix, last_serial_full=excluded.last_serial_full, updated_at=excluded.updated_at
                        """, (rec_key, next_suffix, prod_lot, now_ms))

                        wip_lot = None
                        if wip_kg > 0:
                            cur.execute("SELECT last_suffix FROM ecount_serial_issue_history WHERE history_type='wipSerialIssueHistory' AND record_key=?", (heat_lot,))
                            row_wip = cur.fetchone()
                            wip_suf = (row_wip[0] + 1) if row_wip else 1
                            wip_lot = f"{heat_lot}-{wip_suf}"
                            cur.execute("""
                                INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                                VALUES ('wipSerialIssueHistory', ?, ?, ?, ?)
                                ON CONFLICT(history_type, record_key) DO UPDATE SET
                                    last_suffix=excluded.last_suffix, last_serial_full=excluded.last_serial_full, updated_at=excluded.updated_at
                            """, (heat_lot, wip_suf, wip_lot, now_ms))

                        consume_item_cd, consume_spec = make_ecount_item_code_and_spec(grade, in_t, in_w, 0, "청", hardness)
                        prod_item_cd, prod_spec = make_ecount_item_code_and_spec(grade, prod_t, prod_w, 0, prod_color, hardness)

                        # Update proc_3_grinding_wait_stock
                        if wait_id:
                            cur.execute("SELECT remain_weight_kg, used_weight_kg FROM proc_3_grinding_wait_stock WHERE wait_id=?", (wait_id,))
                        else:
                            cur.execute("SELECT wait_id, remain_weight_kg, used_weight_kg FROM proc_3_grinding_wait_stock WHERE heat_lot_no=?", (heat_lot,))
                        w_row = cur.fetchone()
                        if w_row:
                            if not wait_id:
                                wait_id, rem_w, used_w = w_row
                            else:
                                rem_w, used_w = w_row
                            actual_used = max(0.0, in_kg - wip_kg)
                            new_rem = max(0.0, round(rem_w - actual_used, 1))
                            new_used = round(used_w + actual_used, 1)
                            new_st = "CONSUMED" if new_rem <= 0 else "PARTIAL"
                            cur.execute("""
                                UPDATE proc_3_grinding_wait_stock
                                SET remain_weight_kg=?, used_weight_kg=?, status=?
                                WHERE wait_id=?
                            """, (new_rem, new_used, new_st, wait_id))

                        # Insert into proc_4_grinding_production
                        cur.execute("""
                            INSERT INTO proc_4_grinding_production (
                                doc_date_no, work_date, project_name, worker_name, source_wait_id, out_wh, consume_mgmt,
                                consume_item_code, consume_steel_grade, consume_spec_full, consume_heat_lot_no,
                                consume_unit_kg, consume_qty_ea, consume_total_kg,
                                in_wh, prod_mgmt, prod_item_code, prod_steel_grade, prod_thickness, prod_width, prod_cut_length,
                                prod_color, prod_hardness, prod_spec_full, prod_lot_no, unit_weight_kg, qty_ea, total_weight_kg,
                                scrap_kg, cems_power_kwh, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, work_date, project_name, worker_name, wait_id, out_wh, "투입",
                            consume_item_cd, grade, consume_spec, heat_lot,
                            in_kg, 1, round(in_kg - wip_kg, 1),
                            in_wh, project_name, prod_item_cd, grade, prod_t, prod_w, 0,
                            prod_color, hardness, prod_spec, prod_lot, unit_kg, qty_ea, prod_kg,
                            scrap_kg, cems_kwh, data.get("remarks", "연마 완제품 생산 -> 완제품 창고 입고")
                        ))

                        # Insert into proc_5_finished_and_packing (01.완제품 or 02.포장반)
                        stage = "EXPORT_WAIT" if in_wh == "02.포장반" else "FINISHED_STOCK"
                        cur.execute("""
                            INSERT INTO proc_5_finished_and_packing (
                                doc_date_no, process_stage, project_name, mgmt_item, out_wh, in_wh,
                                source_type, source_lot_no, pack_lot_no, item_code, steel_grade, thickness, width, cut_length,
                                color_name, hardness_display, spec_full, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, worker_name, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, stage, project_name, project_name, out_wh, in_wh,
                            "GRIND", prod_lot, (f"{date_compact}-P01" if in_wh == "02.포장반" else None), prod_item_cd, grade, prod_t, prod_w, 0,
                            prod_color, hardness, prod_spec, unit_kg, qty_ea, prod_kg, prod_kg, worker_name, data.get("remarks", "연마 완제품 입고")
                        ))

                        # Insert Ecount ERP Slips
                        cur.execute("""
                            INSERT INTO ecount_erp_slips (
                                doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                                consume_item_name, consume_spec, consume_serial_lot, consume_item_code,
                                prod_item_code, prod_item_name, prod_spec, color_name, prod_serial_lot,
                                unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name, scrap_kg, remarks
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            doc_date_no, "송구현", project_name, project_name, worker_name,
                            grade, consume_spec, heat_lot, consume_item_cd,
                            prod_item_cd, grade, prod_spec, prod_color, prod_lot,
                            unit_kg, qty_ea, in_kg, prod_kg, round(in_kg - wip_kg, 1), out_wh, in_wh, scrap_kg, f"{out_wh} -> {in_wh}"
                        ))
                        if wip_kg > 0 and wip_lot:
                            cur.execute("""
                                INSERT INTO ecount_erp_slips (
                                    doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                                    consume_item_name, consume_spec, consume_serial_lot, consume_item_code,
                                    unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name, scrap_kg, remarks
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (
                                doc_date_no, "송구현", project_name, "재공", worker_name,
                                grade, consume_spec, wip_lot, consume_item_cd,
                                wip_kg, -1, -wip_kg, 0, -wip_kg, out_wh, out_wh, 0, f"연마 재공환원(수량-1, 단위환산량+{wip_kg})"
                            ))

                        # Daily report details update
                        spec_norm = f"{prod_t:.3f}*{prod_w:.2f}"
                        cur.execute("""
                            INSERT INTO ecount_daily_report_details (
                                report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized,
                                division_or_color, heat_qty_kg, cool_qty_kg, grind_qty_kg, remarks
                            ) VALUES (?, 'PROD', 1, '연마', ?, ?, ?, 0, 0, ?, ?)
                        """, (
                            work_date, grade, spec_norm, prod_color, prod_kg, f"LOT:{prod_lot}"
                        ))
                        conn.commit()
                    finally:
                        conn.close()
                sync_ecount_db_replicas(db_path)
                self._send_json({"status": "ok", "prod_lot": prod_lot, "wip_lot": wip_lot, "prod_item_cd": prod_item_cd})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path == "/api/ecount/warehouse-action":
            try:
                data = json.loads(body)
                act = data.get("action")
                db_path = get_primary_ecount_db()
                with db_lock:
                    conn = sqlite3.connect(db_path)
                    try:
                        cur = conn.cursor()
                        work_date = data.get("work_date") or time.strftime("%Y-%m-%d")
                        date_compact = work_date.replace("-", "")
                        if act == "RAW_INBOUND":
                            grade = data.get("steel_grade") or "SK-5"
                            t = float(data.get("thickness") or 1.2)
                            w = float(data.get("width") or 121.0)
                            partner = data.get("partner_name") or "4.디아이스틸"
                            inbound_type = data.get("inbound_type") or "PURCHASE"
                            unit_kg = float(data.get("unit_weight_kg") or 1500)
                            qty_ea = int(data.get("qty_ea") or 1)
                            tot_kg = round(unit_kg * qty_ea, 1)
                            lot_no = data.get("lot_no") or f"{date_compact}-D01"
                            item_cd, spec_full = make_ecount_item_code_and_spec(grade, t, w, 0, "원재료", "R")
                            cur.execute("""
                                INSERT INTO proc_1_raw_inbounds (
                                    doc_date_no, inbound_type, project_name, mgmt_item, partner_or_out_wh, in_wh,
                                    item_code, steel_grade, thickness, width, cut_length, color_name, hardness_display,
                                    spec_full, lot_no, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, remarks
                                ) VALUES (?,?,?,?,?,'0.도스코',?,?,?,?,0,'원재료','R',?,?,?,?,?,?,?)
                            """, (
                                f"{work_date.replace('-', '/')} -1", inbound_type, "외주가공", "외주가공", partner,
                                item_cd, grade, t, w, spec_full, lot_no, unit_kg, qty_ea, tot_kg, tot_kg, data.get("remarks", "0.도스코 원재료/외주 입고")
                            ))
                            cur.execute("""
                                INSERT INTO ecount_daily_report_details (
                                    report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized,
                                    division_or_color, raw_qty_kg, wage_or_fin_qty_kg, partner_name, remarks
                                ) VALUES (?, 'PURCH', 1, ?, ?, ?, '원재료', ?, ?, ?, ?)
                            """, (
                                work_date, ("임가공" if inbound_type != "PURCHASE" else "매입"), grade, f"{t:.3f}*{w:.2f}",
                                (tot_kg if inbound_type == "PURCHASE" else 0), (tot_kg if inbound_type != "PURCHASE" else 0), partner, f"LOT:{lot_no}"
                            ))
                        elif act == "TRANSFER_PACKING":
                            pack_id = data.get("pack_id")
                            pack_lot = data.get("pack_lot_no") or f"{date_compact}-P01"
                            dest = data.get("customer_or_dest") or "수출 바이어"
                            packing_spec = data.get("packing_spec") or "수출 우든박스/방청포장"
                            if pack_id:
                                cur.execute("""
                                    UPDATE proc_5_finished_and_packing
                                    SET process_stage='EXPORT_WAIT', project_name='포장반', mgmt_item='포장반',
                                        out_wh='01.완제품', in_wh='02.포장반', pack_lot_no=?, customer_or_dest=?, packing_spec=?
                                    WHERE pack_id=?
                                """, (pack_lot, dest, packing_spec, pack_id))
                        elif act == "CREATE_SHIPMENT":
                            recipient = data.get("recipient_name") or "(주)도스코 거래처"
                            out_wh = data.get("out_wh_name") or "01.완제품"
                            serial_no = data.get("slip_serial_no") or f"{date_compact}-1"
                            items = data.get("items") or []
                            doc_tot_ea = sum(int(it.get("qty_ea") or 1) for it in items)
                            doc_tot_kg = sum(float(it.get("total_weight_kg") or 0) for it in items)
                            for it in items:
                                grade = it.get("steel_grade") or "SK-5"
                                spec_disp = it.get("spec_display") or "1.200*120.00"
                                cat_name = it.get("category_name") or "연마(SIDE)"
                                lot_no = it.get("lot_no") or ""
                                u_kg = float(it.get("unit_weight_kg") or 200)
                                q_ea = int(it.get("qty_ea") or 1)
                                t_kg = float(it.get("total_weight_kg") or (u_kg * q_ea))
                                price = float(it.get("unit_price") or 4200)
                                sup = round(t_kg * price)
                                vat = round(sup * 0.1)
                                cur.execute("""
                                    INSERT INTO ecount_delivery_slips (
                                        slip_date, slip_serial_no, recipient_name, out_wh_name, sales_gubun,
                                        steel_grade, spec_display, category_name, lot_no, unit_weight_kg, qty_ea,
                                        total_weight_kg, unit_price, supply_amt, vat_amt, page_no
                                    ) VALUES (?,?,?,?,'제품',?,?,?,?,?,?,?,?,?,?,1)
                                """, (work_date, serial_no, recipient, out_wh, grade, spec_disp, cat_name, lot_no, u_kg, q_ea, t_kg, price, sup, vat))
                                weights_arr = it.get("coil_weights") or [round(u_kg, 1)] * max(1, q_ea)
                                cur.execute("""
                                    INSERT INTO ecount_packing_lists (
                                        packing_date, serial_num, recipient_name, out_wh_name, layout_id,
                                        spec_clean, steel_grade, category_name, coil_count_ea, coil_weights_json,
                                        subtotal_weight_kg, doc_total_qty_ea, doc_total_weight_kg, remarks
                                    ) VALUES (?,?,?,?,'_fixed_4dan',?,?,?,?,?,?,?,?,?)
                                """, (
                                    work_date, serial_no, recipient, out_wh, spec_disp, grade, cat_name, q_ea,
                                    json.dumps(weights_arr, ensure_ascii=False), t_kg, doc_tot_ea, doc_tot_kg, data.get("remarks", "")
                                ))
                                if it.get("pack_id"):
                                    st_new = "EXPORT_SHIPPED" if out_wh == "02.포장반" else "DOMESTIC_OUT"
                                    cur.execute("UPDATE proc_5_finished_and_packing SET process_stage=?, remain_weight_kg=0, customer_or_dest=? WHERE pack_id=?",
                                                (st_new, recipient, it.get("pack_id")))
                                cur.execute("""
                                    INSERT INTO ecount_daily_report_details (
                                        report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized,
                                        division_or_color, wage_or_fin_qty_kg, partner_name, remarks
                                    ) VALUES (?, 'SALES', 1, '제품', ?, ?, ?, ?, ?, ?)
                                """, (work_date, grade, spec_disp.split("*(")[0], cat_name, t_kg, recipient, f"전표:{serial_no}"))
                        elif act == "SAVE_ADDRESS":
                            cur.execute("""
                                INSERT OR REPLACE INTO ecount_address_book (
                                    saved_date, partner_name, receiver_name, phone_no, zip_code, road_address, detail_address, wh_filter
                                ) VALUES (?,?,?,?,?,?,?,?)
                            """, (
                                work_date, data.get("partner_name", ""), data.get("receiver_name", ""),
                                data.get("phone_no", ""), data.get("zip_code", ""),
                                data.get("road_address", ""), data.get("detail_address", ""),
                                data.get("wh_filter", "01.완제품")
                            ))
                        conn.commit()
                    finally:
                        conn.close()
                sync_ecount_db_replicas(db_path)
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        if self.path in ["/api/clear-spec", "/api/clear_spec", "/api/clear-all"]:
            try:
                data = json.loads(body)
                lid = data.get("lid") or data.get("line_id")
                date = data.get("date")
                if lid:
                    with state_lock:
                        server_state["version"] += 1
                        server_state["last_updated"] = time.time()
                        server_state["specs"].pop(lid, None)
                        server_state["workers"].pop(lid, None)
                        if date:
                            server_state["specs"].pop(f"{date}_{lid}", None)
                            server_state["workers"].pop(f"{date}_{lid}", None)
                        for k in list(server_state["specs"].keys()):
                            if k.endswith(f"_{lid}"):
                                server_state["specs"].pop(k, None)
                        for k in list(server_state["workers"].keys()):
                            if k.endswith(f"_{lid}"):
                                server_state["workers"].pop(k, None)
                        if "cleared_specs" not in server_state:
                            server_state["cleared_specs"] = []
                        if lid not in server_state["cleared_specs"]:
                            server_state["cleared_specs"].append(lid)
                        if "cleared_workers" not in server_state:
                            server_state["cleared_workers"] = []
                        if lid not in server_state["cleared_workers"]:
                            server_state["cleared_workers"].append(lid)
                        server_state["statuses"][lid] = "비가동"
                    save_state_to_files()
                self._send_json({"status": "ok", "cleared": True})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path in ["/api/spec", "/api/update_spec", "/api/update"]:
            try:
                data = json.loads(body)
                lid = data.get("lid") or data.get("line_id")
                date = data.get("date")
                spec = data.get("spec") or data
                if lid and spec:
                    with state_lock:
                        server_state["version"] += 1
                        server_state["last_updated"] = time.time()
                        server_state["specs"][lid] = spec
                        if date:
                            server_state["specs"][f"{date}_{lid}"] = spec
                        if "cleared_specs" in server_state and lid in server_state["cleared_specs"]:
                            server_state["cleared_specs"].remove(lid)
                    save_state_to_files()
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path == "/api/worker":
            try:
                data = json.loads(body)
                lid = data.get("lid") or data.get("line_id")
                worker = data.get("worker")
                date = data.get("date")
                if lid:
                    with state_lock:
                        server_state["version"] += 1
                        server_state["last_updated"] = time.time()
                        if worker and str(worker).strip() and str(worker).strip() != '-':
                            w_str = str(worker).strip()
                            server_state["workers"][lid] = w_str
                            if date:
                                server_state["workers"][f"{date}_{lid}"] = w_str
                            if "cleared_workers" in server_state and lid in server_state["cleared_workers"]:
                                server_state["cleared_workers"].remove(lid)
                        else:
                            server_state["workers"].pop(lid, None)
                            if "cleared_workers" not in server_state:
                                server_state["cleared_workers"] = []
                            if lid not in server_state["cleared_workers"]:
                                server_state["cleared_workers"].append(lid)
                    save_state_to_files()
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path == "/api/status":
            try:
                data = json.loads(body)
                lid = data.get("lid") or data.get("line_id")
                status = data.get("status")
                if lid and status:
                    with state_lock:
                        server_state["version"] += 1
                        server_state["last_updated"] = time.time()
                        server_state["statuses"][lid] = status
                    save_state_to_files()
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path in ["/api/work_orders", "/api/work-orders"]:
            try:
                data = json.loads(body)
                lid = data.get("lid") or data.get("line_id")
                wos = data.get("work_orders") or data.get("wos")
                if lid and isinstance(wos, list):
                    with state_lock:
                        server_state["version"] += 1
                        server_state["last_updated"] = time.time()
                        server_state["work_orders"][lid] = wos
                    save_state_to_files()
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        elif self.path == "/api/sync":
            try:
                req = json.loads(body)
                action = req.get("action")
                payload = req.get("payload", {})
                
                with state_lock:
                    server_state["version"] += 1
                    server_state["last_updated"] = time.time()
                    
                    if action == "UPDATE_SPEC":
                        lid = payload.get("line_id") or payload.get("lid")
                        spec = payload.get("spec")
                        date = payload.get("date")
                        if lid and spec:
                            server_state["specs"][lid] = spec
                            if date:
                                server_state["specs"][f"{date}_{lid}"] = spec
                            if lid in server_state.get("cleared_specs", []):
                                server_state["cleared_specs"].remove(lid)
                                
                    elif action in ["CLEAR_SPEC", "CLEAR_SPEC_AND_WORKER"]:
                        lid = payload.get("line_id") or payload.get("lid")
                        date = payload.get("date")
                        if lid:
                            server_state["specs"].pop(lid, None)
                            server_state["workers"].pop(lid, None)
                            if date:
                                server_state["specs"].pop(f"{date}_{lid}", None)
                                server_state["workers"].pop(f"{date}_{lid}", None)
                            for k in list(server_state["specs"].keys()):
                                if k.endswith(f"_{lid}"):
                                    server_state["specs"].pop(k, None)
                            for k in list(server_state["workers"].keys()):
                                if k.endswith(f"_{lid}"):
                                    server_state["workers"].pop(k, None)
                            if "cleared_specs" not in server_state:
                                server_state["cleared_specs"] = []
                            if lid not in server_state["cleared_specs"]:
                                server_state["cleared_specs"].append(lid)
                            if "cleared_workers" not in server_state:
                                server_state["cleared_workers"] = []
                            if lid not in server_state["cleared_workers"]:
                                server_state["cleared_workers"].append(lid)
                            server_state["statuses"][lid] = "비가동"
                                
                    elif action == "UPDATE_STATUS":
                        lid = payload.get("line_id") or payload.get("lid")
                        status = payload.get("status")
                        if lid and status:
                            server_state["statuses"][lid] = status
                            
                    elif action == "UPDATE_WORKER":
                        lid = payload.get("line_id") or payload.get("lid")
                        worker = payload.get("worker")
                        if lid:
                            if worker and str(worker).strip() and str(worker).strip() != '-':
                                server_state["workers"][lid] = str(worker).strip()
                                if "cleared_workers" in server_state and lid in server_state["cleared_workers"]:
                                    server_state["cleared_workers"].remove(lid)
                            else:
                                server_state["workers"].pop(lid, None)
                                if "cleared_workers" not in server_state:
                                    server_state["cleared_workers"] = []
                                if lid not in server_state["cleared_workers"]:
                                    server_state["cleared_workers"].append(lid)
                            
                    elif action == "UPDATE_COILS":
                        date = payload.get("date")
                        lid = payload.get("line_id") or payload.get("lid")
                        coils = payload.get("coils")
                        if date and lid and coils is not None:
                            server_state["coils"][f"{date}_{lid}"] = coils

                    elif action == "UPDATE_WORK_ORDERS":
                        lid = payload.get("line_id") or payload.get("lid")
                        wos = payload.get("work_orders")
                        if lid and isinstance(wos, list):
                            server_state["work_orders"][lid] = wos

                    elif action == "UPDATE_LINE_WORK_STATE":
                        lid = payload.get("line_id") or payload.get("lid")
                        date = payload.get("date")
                        state = payload.get("state")
                        if lid and state:
                            if "line_work_state" not in server_state:
                                server_state["line_work_state"] = {}
                            server_state["line_work_state"][lid] = state
                            if date:
                                server_state["line_work_state"][f"{date}_{lid}"] = state

                    elif action == "START_WORK_ORDER":
                        lid = payload.get("line_id") or payload.get("lid")
                        wo_id = payload.get("wo_id")
                        date = payload.get("date")
                        if lid and wo_id:
                            wos = server_state["work_orders"].get(lid, [])
                            target_wo = None
                            for w in wos:
                                if w.get("id") == wo_id:
                                    w["status"] = "running"
                                    target_wo = w
                                elif w.get("status") == "running":
                                    w["status"] = "completed"
                            if target_wo:
                                new_spec = {
                                    "wo": target_wo.get("wo_no", ""),
                                    "t": str(target_wo.get("thick", "")),
                                    "w": str(target_wo.get("width", "")),
                                    "steel": target_wo.get("steel", ""),
                                    "hardness": target_wo.get("hrc", ""),
                                    "memo": target_wo.get("memo", "")
                                }
                                server_state["specs"][lid] = new_spec
                                if date:
                                    server_state["specs"][f"{date}_{lid}"] = new_spec
                                if lid in server_state.get("cleared_specs", []):
                                    server_state["cleared_specs"].remove(lid)
                
                save_state_to_files()
                
                self._send_json({"status": "ok"})
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
                return

        self.send_response(404)
        self.end_headers()

def run_server():
    load_initial_state()
    # PLC 백그라운드 수집 스레드 시작
    plc_thread = threading.Thread(target=plc_collector_loop, daemon=True)
    plc_thread.start()
    
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, SyncHandler)
    print(f"[동기화 서버] http://localhost:{PORT} (PLC PV+SV 스트리밍 포함) 가동 시작...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run_server()
