# -*- coding: utf-8 -*-
"""
(주)도스코 이카운트(ECOUNT) ERP 1:1 호환 통합 데이터베이스 구축 및 초기화 스크립트
Database File: dosko_ecount.db (SQLite3)
"""
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
import os
import re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dosko_ecount.db")
ITEM_XLSX_PATH = r"c:\Users\song9\OneDrive\바탕 화면\Ecount\문서\이카운트.품목.xlsx"
HIST_XLSX_PATH = r"c:\Users\song9\OneDrive\바탕 화면\Ecount\26.06.01-26.생산입고.소모현황Ⅰ.xlsx"

GRADE_CODE_MAP = {
    "SK-5": ("5", "-5", "-53", "-54"),
    "SK-4": ("4", "-4", "-43", "-44"),
    "SK-3": ("3", "-3", "-33", "-34"),
    "SK2CR4": ("24", "-2", "-23", "-24"),
    "SKS-51": ("51", "51", "513", "514"),
    "SKS-7": ("7", "-7", "-73", "-74"),
    "S50C": ("50", "50", "503", "504"),
    "S55C": ("55", "50", "503", "504"),
    "S60C": ("60", "70", "703", "704"),
    "S70C": ("70", "70", "703", "704"),
    "S75C": ("75", "70", "703", "704"),
    "SCM435": ("43", "43", "433", "434"),
    "50CRV4": ("54", "61", "613", "614"),
    "420J2": ("42", "30", "303", "304"),
}

COLOR_CODE_MAP = {
    "원재료": "00",
    "BRIGHT": "10",
    "원재료(임)": "11",
    "원재료(R면치)": "12",
    "원재료(각면치)": "13",
    "백": "20",
    "유광": "20",
    "백(R면치)": "22",
    "백(각면치)": "23",
    "청": "30",
    "녹색": "31",
    "청(R면치)": "32",
    "청(SIDE)": "30",
    "청.R": "35",
    "연마": "40",
    "연마(R면치)": "42",
    "연마(각면치)": "43",
    "연마(SIDE)": "44",
    "착색": "50",
    "PO": "70",
    "PO압연": "71",
    "PA": "80",
    "임(열)": "90",
    "임(원재료)": "95",
}


def generate_ecount_item_code_and_spec(steel_grade, thickness, width, cut_length=0, color_name="청", hardness="HRC45"):
    """
    이카운트 표준 품목코드 및 규격 자동 생성기
    - 규격 공식:
      코일(cut_length=0): {두께:.3f}*{폭:.2f}*({칼라}){경도}  예: 1.200*121.00*(청)HRC45
      절단(cut_length>0): {두께:.3f}*{폭:.0f}*{절단길이:.0f}*({칼라}){경도} 예: 2.500*255*255*(청)HRC47
    - 품목코드 공식:
      [두께4자리(T*1000)][폭5자리(W*100)]-[강종코드][칼라2자리]-[경도3자리]
      예: 120012100-530-045 (구형/품목마스터 호환코드: -530-120012100-045)
    """
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
    prefix_sign = "-" if g_prefix in ("3", "4", "5", "7") else ""
    legacy_code = f"{prefix_sign}{g_prefix}{c_code}-{t_code}{w_code}-{h_code}"
    return item_code, legacy_code, spec_str


def create_schema(conn):
    cur = conn.cursor()

    # 1. 창고 마스터 (ecount_warehouses)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_warehouses (
        wh_code TEXT PRIMARY KEY,
        wh_name TEXT NOT NULL,
        wh_category TEXT NOT NULL, -- RAW(원재료), WIP_GRIND(연마대기), WIP_NARROW(소폭대기), FINISHED(완제품), PACKING(포장반/수출대기), SUBCONTRACT(외주처), DEFECT(불량)
        ecount_wh_name TEXT NOT NULL,
        default_location TEXT,
        description TEXT,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 2. 프로젝트(공정/호기) 마스터 (ecount_projects)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_projects (
        project_code TEXT PRIMARY KEY,
        project_name TEXT NOT NULL,
        process_type TEXT NOT NULL, -- HEAT(열처리), QUENCH_HEAT(수냉열처리), QUENCH_GRIND(수냉연마), GRIND(연마), PACKING(포장반), SUBCONTRACT(외주가공), ADJUST(조정/수정)
        default_mgmt_item TEXT NOT NULL,
        default_out_wh TEXT NOT NULL,
        default_in_wh TEXT NOT NULL,
        lot_prefix_rule TEXT NOT NULL, -- 예: YYYYMMDD-1XX, YYYYMMDD-8XX, YYYYMMDD-9XX
        group_suffix_code TEXT,        -- 품번 접미 규칙 (원재료:'', 열처리:'3', 연마:'4')
        cems_meter_ids TEXT,           -- 현대 CEMS 전력계측기 번호 매핑
        description TEXT
    );
    """)

    # 3. 관리항목 마스터 (ecount_mgmt_items)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_mgmt_items (
        mgmt_code TEXT PRIMARY KEY,
        mgmt_name TEXT NOT NULL,
        io_direction TEXT NOT NULL, -- CONSUME(투입/소모), WIP_RETURN(재공환원 -kg), PRODUCE(생산입고), ADJUST(조정)
        target_process TEXT,
        description TEXT
    );
    """)

    # 4. 품목(강종) 마스터 (ecount_steel_grades)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_steel_grades (
        grade_name TEXT PRIMARY KEY,   -- 예: SK-5, SK-4, S75C, SCM435
        raw_code_prefix TEXT NOT NULL, -- 품목코드용 강종코드 (예: -5, 5, 75, 43)
        raw_group_code TEXT NOT NULL,  -- 원재료 품번 (예: -5, 70, 50, 43)
        heat_group_code TEXT NOT NULL, -- 열처리 제품 품번 (뒤에 3 추가: -53, 703, 503, 433)
        grind_group_code TEXT NOT NULL,-- 연마 제품 품번 (뒤에 4 추가: -54, 704, 504, 434)
        hardness_unit_default TEXT DEFAULT 'HRC',
        description TEXT
    );
    """)

    # 5. 칼라/표면가공 코드 마스터 (ecount_colors)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_colors (
        color_code TEXT PRIMARY KEY, -- 예: 00, 11, 20, 30, 40, 42, 44, 70, 90
        color_name TEXT NOT NULL,    -- 예: 원재료, 백, 청, 연마, 연마(R면치), 연마(SIDE), PO, 임(열)
        process_stage TEXT NOT NULL, -- RAW, HEAT, GRIND
        description TEXT
    );
    """)

    # 6. 이카운트 품목 및 규격 마스터 (ecount_items)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_items (
        item_code TEXT PRIMARY KEY,      -- 이카운트 품목코드 (예: 120012100-530-045 또는 -530-120012100-045)
        legacy_item_code TEXT,           -- 구/신 코드 상호 매핑용
        item_name TEXT NOT NULL,         -- 품목명 (강종: SK-5 등)
        item_type TEXT DEFAULT '0',      -- 품목구분 (0:원재료, 1:반제품, 2:제품/완제품)
        group_code TEXT,                 -- 품목군/품번 (-5, -53, -54 등)
        thickness REAL NOT NULL,         -- 두께(T, mm)
        width REAL NOT NULL,             -- 폭(W, mm)
        cut_length REAL DEFAULT 0,       -- 절단길이(mm, 코일은 0)
        color_code TEXT,                 -- 칼라코드 (00, 30, 40, 44 등)
        color_name TEXT,                 -- 칼라명 (원재료, 청, 연마, 연마(SIDE) 등)
        hardness_code TEXT,              -- 경도코드 3자리 (001:R, 000:S, 045:HRC45, 540:HV540)
        hardness_display TEXT,           -- 경도 표기 (R, S, HRC45, HV540)
        spec_full TEXT NOT NULL,         -- 이카운트 표준 규격 (예: 1.200*121.00*(청)HRC45)
        unit TEXT DEFAULT 'KG',          -- 기본단위 (KG)
        mgmt_flag TEXT DEFAULT 'B',      -- 관리항목 플래그
        lot_flag TEXT DEFAULT 'B',       -- 시리얼/로트 플래그
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_lookup ON ecount_items(item_name, thickness, width, color_name, hardness_display);")

    # [프로세스 1] 원재료 매입 및 외주가공 입고 테이블 (proc_1_raw_inbounds -> 0.도스코 창고)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proc_1_raw_inbounds (
        inbound_id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_date_no TEXT NOT NULL,         -- 일자-No. (예: 2026/08/01 -1)
        inbound_type TEXT NOT NULL,        -- PURCHASE(원재료매입), WAGE_IN(임가공입고), SUBCONTRACT(외주가공입고)
        project_name TEXT DEFAULT '외주가공',
        mgmt_item TEXT DEFAULT '외주가공',
        partner_or_out_wh TEXT,            -- 거래처 또는 외주 출고창고 (예: 4.디아이스틸, 4.이지철강, 명성스리팅)
        in_wh TEXT DEFAULT '0.도스코',       -- 입고창고 (기본: 0.도스코)
        item_code TEXT,
        steel_grade TEXT NOT NULL,         -- 품목(강종)
        thickness REAL NOT NULL,           -- 두께(mm)
        width REAL NOT NULL,               -- 폭(mm)
        cut_length REAL DEFAULT 0,         -- 절단길이(mm)
        color_name TEXT DEFAULT '원재료',
        hardness_display TEXT DEFAULT 'R', -- R(코일) 또는 S(시트)
        spec_full TEXT NOT NULL,           -- 규격
        lot_no TEXT NOT NULL,              -- 원소재/외주 로트번호 (예: DI260702-003, 20260801-D03)
        unit_weight_kg REAL NOT NULL,      -- 단위환산량/kg
        qty_ea INTEGER DEFAULT 1,          -- 수량/EA
        total_weight_kg REAL NOT NULL,     -- 환산량/kg (총중량)
        remain_weight_kg REAL NOT NULL,    -- 현재 남은 가용 중량(kg)
        worker_name TEXT DEFAULT '송구현',
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [프로세스 2] 열처리 및 수냉열처리 공정 테이블 (proc_2_heat_treatment: 1·2·3·5·6·7호기)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proc_2_heat_treatment (
        heat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_date_no TEXT NOT NULL,         -- 일자-No. (예: 2026/11/03 -1)
        work_date TEXT NOT NULL,           -- 작업일자 (YYYY-MM-DD)
        project_name TEXT NOT NULL,        -- 호기 (1호기, 2호기, 3호기, 5호기, 6호기, 7호기)
        worker_name TEXT,                  -- 작업자
        -- [소모(투입/재공) 파트: 0.도스코 창고 출고]
        out_wh TEXT DEFAULT '0.도스코',
        consume_mgmt TEXT DEFAULT '투입',   -- 투입
        raw_item_code TEXT,
        raw_steel_grade TEXT NOT NULL,
        raw_thickness REAL NOT NULL,
        raw_width REAL NOT NULL,
        raw_cut_length REAL DEFAULT 0,
        raw_spec_full TEXT,                -- 소모 규격 (예: 1.200*121.10*(원재료)R)
        raw_lot_no TEXT,                   -- 소모 시리얼/로트No. (예: T260630-01)
        input_unit_kg REAL DEFAULT 0,      -- 투입 단위환산량/kg
        input_qty_ea INTEGER DEFAULT 1,    -- 투입 수량/EA
        input_total_kg REAL NOT NULL,      -- 투입 총환산량/kg (투입량)
        wip_return_kg REAL DEFAULT 0,      -- 재공 환원 중량 (이카운트 음수 표기용, 예: -195)
        wip_lot_no TEXT,                   -- 재공 시리얼 (예: T260630-01-1)
        -- [생산(열처리/수냉열처리) 파트: 01.완제품 또는 01.연마(연마대기)/01.소폭 입고]
        next_route TEXT DEFAULT 'FINISHED',-- FINISHED(바로 완제품창고), GRIND_WAIT(연마대기 누적), NARROW_WAIT(소폭연마대기 누적)
        in_wh TEXT NOT NULL,               -- 입고창고 ('01.완제품', '01.연마', '01.소폭')
        prod_mgmt TEXT NOT NULL,           -- 관리항목 ('열처리', '수냉열처리')
        prod_item_code TEXT,               -- 생산품목코드 (예: 120012100-530-045)
        prod_steel_grade TEXT NOT NULL,    -- 생산품목명 (강종: SK-5)
        prod_thickness REAL NOT NULL,      -- 생산 두께
        prod_width REAL NOT NULL,          -- 생산 폭
        prod_cut_length REAL DEFAULT 0,    -- 절단길이
        prod_color TEXT NOT NULL,          -- 칼라 (청, 백, 임(열) 등)
        prod_hardness TEXT NOT NULL,       -- 경도 (HRC45, HV480 등)
        prod_spec_full TEXT NOT NULL,      -- 생산 규격명 (예: 1.200*121.00*(청)HRC45)
        prod_lot_no TEXT NOT NULL,         -- 생산 시리얼/로트No. (예: 20261103-301)
        unit_weight_kg REAL NOT NULL,      -- 단위환산량/kg (코일당 중량)
        qty_ea INTEGER DEFAULT 1,          -- 수량/EA (코일수)
        total_weight_kg REAL NOT NULL,     -- 환산량/kg (합격 생산중량 합계)
        scrap_kg REAL DEFAULT 0,           -- 스크랩/불량 중량(kg)
        power_kwh REAL DEFAULT 0,          -- 호기 소비전력량(kWh)
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [프로세스 3] 연마대기 / 수냉연마대기 중간재고 테이블 (proc_3_grinding_wait_stock: 01.연마 / 01.소폭 창고)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proc_3_grinding_wait_stock (
        wait_id INTEGER PRIMARY KEY AUTOINCREMENT,
        wh_code TEXT NOT NULL,             -- '01.연마' (일반/대폭연마대기) 또는 '01.소폭' (소폭/수냉연마대기)
        source_heat_id INTEGER,            -- proc_2_heat_treatment 참조 ID
        source_project TEXT NOT NULL,      -- 생산한 열처리 호기 (예: 1호기, 3호기, 5호기, 7호기)
        prod_date TEXT NOT NULL,           -- 열처리 생산일자
        heat_lot_no TEXT NOT NULL UNIQUE,  -- 열처리 생산 로트번호 (연마 소모 시리얼로 직결, 예: 20261103-301)
        item_code TEXT,                    -- 열처리 품목코드 (예: 120012100-530-045)
        steel_grade TEXT NOT NULL,         -- 강종 (SK-5, SKS-51 등)
        thickness REAL NOT NULL,           -- 열처리 두께 (예: 1.200)
        width REAL NOT NULL,               -- 열처리 폭 (예: 121.00 -> 연마 시 120.00으로 가공될 원소재 폭)
        cut_length REAL DEFAULT 0,
        color_name TEXT NOT NULL,          -- 열처리 칼라 (청, 임(열) 등)
        hardness_display TEXT NOT NULL,    -- 열처리 경도 (HRC45, HV520 등)
        spec_full TEXT NOT NULL,           -- 열처리 규격 (예: 1.200*121.00*(청)HRC45)
        unit_weight_kg REAL NOT NULL,      -- 단위환산량/kg
        init_qty_ea INTEGER DEFAULT 1,     -- 입고 코일수(EA)
        remain_qty_ea INTEGER DEFAULT 1,   -- 잔여 코일수(EA)
        init_weight_kg REAL NOT NULL,      -- 입고 총환산량/kg (예: 202kg)
        used_weight_kg REAL DEFAULT 0,     -- 연마 투입 누적 중량(kg)
        remain_weight_kg REAL NOT NULL,    -- 현재 연마대기 잔여 중량(kg)
        status TEXT DEFAULT 'WAITING',     -- WAITING(연마대기), PARTIAL(부분투입), CONSUMED(전량투입완료)
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [프로세스 4] 연마 및 수냉연마 생산/소모 테이블 (proc_4_grinding_production: 연마 / 수냉연마 프로젝트)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proc_4_grinding_production (
        grind_id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_date_no TEXT NOT NULL,         -- 일자-No. (예: 2026/11/03 -3)
        work_date TEXT NOT NULL,           -- 연마 작업일자 (YYYY-MM-DD)
        project_name TEXT NOT NULL,        -- '연마' (로트 900번대) 또는 '수냉연마' (로트 800번대)
        worker_name TEXT,
        -- [소모(연마투입) 파트: 연마대기(01.연마/01.소폭)에서 가져오기]
        source_wait_id INTEGER,            -- proc_3_grinding_wait_stock.wait_id 참조
        out_wh TEXT DEFAULT '01.연마',      -- 출고창고 ('01.연마', '01.소폭', '0.도스코')
        consume_mgmt TEXT DEFAULT '투입',   -- 관리항목 ('투입')
        consume_item_code TEXT,            -- 소모품목코드 (열처리 품목코드: 120012100-530-045)
        consume_steel_grade TEXT NOT NULL, -- 소모품목명 (SK-5)
        consume_spec_full TEXT NOT NULL,   -- 소모 규격명 (예: 1.200*121.00*(청)HRC45)
        consume_heat_lot_no TEXT NOT NULL, -- 소모 시리얼/로트No. (열처리 로트번호: 20260630-301)
        consume_unit_kg REAL NOT NULL,     -- 소모 단위환산량/kg (예: 202)
        consume_qty_ea INTEGER DEFAULT 1,  -- 소모 수량/EA (예: 1)
        consume_total_kg REAL NOT NULL,    -- 투입량/소모량 (예: 202)
        -- [생산(연마완제품) 파트: 01.완제품 창고 입고]
        in_wh TEXT DEFAULT '01.완제품',     -- 입고창고 ('01.완제품')
        prod_mgmt TEXT NOT NULL,           -- 관리항목 ('연마' 또는 '수냉연마')
        prod_item_code TEXT,               -- 연마 생산품목코드 (예: 120012000-544-045)
        prod_steel_grade TEXT NOT NULL,    -- 생산품목명 (SK-5)
        prod_thickness REAL NOT NULL,      -- 연마 후 두께 (예: 1.200)
        prod_width REAL NOT NULL,          -- 연마 후 폭 (예: 120.00)
        prod_cut_length REAL DEFAULT 0,    -- 절단길이
        prod_color TEXT NOT NULL,          -- 연마 칼라 ('연마', '연마(SIDE)', '연마(R면치)', '백(R면치)')
        prod_hardness TEXT NOT NULL,       -- 경도 (HRC45, HV520 등)
        prod_spec_full TEXT NOT NULL,      -- 생산 규격명 (예: 1.200*120.00*(연마(SIDE))HRC45)
        prod_lot_no TEXT NOT NULL,         -- 연마 완제품 시리얼/로트No. (연마: YYYYMMDD-901~, 수냉연마: YYYYMMDD-801~)
        unit_weight_kg REAL NOT NULL,      -- 단위환산량/kg (예: 198)
        qty_ea INTEGER DEFAULT 1,          -- 수량/EA (예: 1)
        total_weight_kg REAL NOT NULL,     -- 환산량/kg (예: 198)
        scrap_kg REAL DEFAULT 0,           -- 연마 스크랩/감량 (예: 202 - 198 = 4kg)
        cems_power_kwh REAL DEFAULT 0,     -- CEMS 15번(소폭연마)/16번(대폭연마) 소비전력(kWh)
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [프로세스 5] 완제품 창고 재고 및 포장반(수출가공·출고대기) 테이블 (proc_5_finished_and_packing)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proc_5_finished_and_packing (
        pack_id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_date_no TEXT,                  -- 일자-No.
        process_stage TEXT NOT NULL,       -- FINISHED_STOCK(완제품재고), DOMESTIC_OUT(국내출고), PACKING_PROC(포장반가공), EXPORT_WAIT(수출출고대기), EXPORT_SHIPPED(수출선적완료)
        project_name TEXT DEFAULT '완제품', -- 프로젝트 ('완제품', '포장반' 등)
        mgmt_item TEXT DEFAULT '완제품입고',-- 관리항목 ('열처리', '연마', '포장반' 등)
        out_wh TEXT DEFAULT '01.완제품',    -- 출고창고 ('01.완제품')
        in_wh TEXT DEFAULT '01.완제품',     -- 현재 보관창고 ('01.완제품' 또는 '02.포장반')
        source_type TEXT NOT NULL,         -- HEAT(열처리 직결 완제품) 또는 GRIND(연마 완제품)
        source_lot_no TEXT NOT NULL,       -- 완제품 로트번호 (예: 20261103-301 또는 20261103-901)
        pack_lot_no TEXT,                  -- 포장반 수출 로트번호/패킹번호 (예: 20261103-P01)
        item_code TEXT,
        steel_grade TEXT NOT NULL,
        thickness REAL NOT NULL,
        width REAL NOT NULL,
        cut_length REAL DEFAULT 0,
        color_name TEXT NOT NULL,
        hardness_display TEXT NOT NULL,
        spec_full TEXT NOT NULL,
        unit_weight_kg REAL NOT NULL,      -- 단위환산량/kg
        qty_ea INTEGER DEFAULT 1,          -- 수량/EA (코일/파레트 수)
        total_weight_kg REAL NOT NULL,     -- 환산량/kg
        remain_weight_kg REAL NOT NULL,    -- 현재 창고 잔여 중량(kg)
        customer_or_dest TEXT,             -- 국내 납품처 또는 수출 국가/바이어
        packing_spec TEXT,                 -- 수출 포장 사양 (우든박스, 스키드, 방청지 등)
        worker_name TEXT,
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [통합 전표] 이카운트 ERP 생산입고/소모현황 1:1 호환 통합 전표 테이블 (ecount_erp_slips)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_erp_slips (
        slip_id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_date_no TEXT NOT NULL,         -- 일자-No. (예: 2026/06/30 -1)
        writer_name TEXT DEFAULT '송구현',  -- 최초작성자
        project_name TEXT NOT NULL,        -- 프로젝트명 (1~7호기, 연마, 수냉연마, 포장반, 외주가공)
        mgmt_item TEXT NOT NULL,           -- 관리항목명 (투입, 재공, 열처리, 수냉열처리, 연마, 수냉연마, 포장반, 외주가공)
        manager_name TEXT DEFAULT '송구현', -- 담당자명
        consume_item_name TEXT,            -- 소모품목명 (강종)
        consume_spec TEXT,                 -- 규격명(소모)
        consume_serial_lot TEXT,           -- 시리얼(소모) / 원소재 또는 열처리 로트번호
        consume_item_code TEXT,            -- 소모품목코드
        prod_item_code TEXT,               -- 생산품목코드
        prod_item_name TEXT,               -- 생산품목명 (강종)
        prod_spec TEXT,                    -- 생산 규격명
        color_name TEXT,                   -- 칼라
        prod_serial_lot TEXT,              -- 시리얼(생산) / 생산 로트번호
        unit_weight_kg REAL,               -- 단위환산량/kg (ADD_NUM_03)
        qty_ea INTEGER,                    -- 수량/EA (ADD_NUM_04, 재공 시 -1)
        input_kg REAL,                     -- 투입량 / 입력수량(환산량/kg, 재공 시 -스크랩kg)
        prod_kg REAL,                      -- 생산량
        consume_kg REAL,                   -- 소모량 (p_amt1)
        out_wh_name TEXT,                  -- 출고창고명 (0.도스코, 01.연마, 01.소폭, 01.완제품 등)
        in_wh_name TEXT,                   -- 입고창고명 (01.완제품, 01.연마, 01.소폭, 02.포장반, 0.도스코 등)
        scrap_kg REAL DEFAULT 0,           -- 스크랩 (ADD_NUM_05)
        remarks TEXT,                      -- 적요
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [배포용 커스터마이징 1] 생산실적등록(E040407) 시리얼/로트 발행 이력 테이블 (ecount_serial_issue_history)
    # Chrome Extension (options.js / production-general-wip.js) generalSerialIssueHistory & wipSerialIssueHistory 100% 호환
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_serial_issue_history (
        history_type TEXT NOT NULL,        -- 'generalSerialIssueHistory' (일반생산) 또는 'wipSerialIssueHistory' (재공생산)
        record_key TEXT NOT NULL,          -- 일반: 'YYYYMMDD-1'(호기/공장코드), 재공: '원소재시리얼(baseSerialText)'
        last_suffix INTEGER NOT NULL,      -- 일반: 마지막 시리얼번호(예: 105, 802, 904, 3), 재공: 마지막 suffix(1, 2, 3...)
        last_serial_full TEXT,             -- 실제 발행된 전체 시리얼 문자열 (예: 20260630-105, 20260625-101-1)
        updated_at INTEGER NOT NULL,       -- Unix epoch ms (chrome.storage.local 호환)
        PRIMARY KEY (history_type, record_key)
    );
    """)

    # [배포용 커스터마이징 2-A] 일일업무일지 상세 내역 테이블 (ecount_daily_report_details)
    # popup-daily-report.js (생산입고 E040410 / 입고구매 E040305 / 출고판매 E040207) <생산내역>, <입고내역>, <출고내역> 1:1 호환
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_daily_report_details (
        detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT NOT NULL,         -- 기준일 (YYYY-MM-DD 또는 YYYYMMDD)
        section_type TEXT NOT NULL,        -- 'PROD'(<생산 내역>), 'PURCH'(<입고 내역>), 'SALES'(<출고 내역>)
        seq_no INTEGER NOT NULL,           -- No. (행 순번)
        orig_gubun TEXT NOT NULL,          -- 업무구분 (생산: 열처리/수냉/연마 | 입고: 매입/임가공 | 출고: 제품/임가공/원재료)
        material_grade TEXT NOT NULL,      -- 강종 (SK-5, SKS-51 등)
        spec_normalized TEXT NOT NULL,     -- 정규화 규격 (normalizeSpec: 괄호 앞 순수 치수 예: 1.200*121.00)
        division_or_color TEXT,            -- 생산(열처리): 호기번호(1,2,3,5) / 생산(수냉·연마)·입고·출고: 칼라
        heat_qty_kg REAL DEFAULT 0,        -- 생산: 열처리 중량(kg)
        cool_qty_kg REAL DEFAULT 0,        -- 생산: 수냉 중량(kg)
        grind_qty_kg REAL DEFAULT 0,       -- 생산: 연마 중량(kg)
        raw_qty_kg REAL DEFAULT 0,         -- 입고(원재료) / 출고(원재료) 중량(kg)
        wage_or_fin_qty_kg REAL DEFAULT 0, -- 입고(임가공) / 출고(제품) 중량(kg)
        raw_ret_qty_kg REAL DEFAULT 0,     -- 입고(원재반품) / 출고(원재반품) 중량(kg)
        wage_or_fin_ret_kg REAL DEFAULT 0, -- 입고(임가공반품) / 출고(제품반품) 중량(kg)
        partner_name TEXT,                 -- 입고/출고 거래처명
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [배포용 커스터마이징 2-B] 일일업무일지 요약결재 테이블 (ecount_daily_report_summary)
    # popup-daily-report.js '요약결재' 시트 (담당/차장/부장/이사/전무 결재란 + 6대 핵심지표 일계/월계)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_daily_report_summary (
        report_date TEXT PRIMARY KEY,      -- 기준일 (YYYY-MM-DD)
        sheet_name TEXT NOT NULL,          -- 시트명 (예: '06월30일')
        day_prod_heat_cool_kg REAL DEFAULT 0, -- 일계: 생산(열처리) = 열처리 + 수냉 합산
        mon_prod_heat_cool_kg REAL DEFAULT 0, -- 월계: 생산(열처리) 누계
        day_prod_grind_kg REAL DEFAULT 0,     -- 일계: 생산(연마)
        mon_prod_grind_kg REAL DEFAULT 0,     -- 월계: 생산(연마) 누계
        day_in_raw_net_kg REAL DEFAULT 0,     -- 일계: 입고(원재) = 원재매입 - 원재반품
        mon_in_raw_net_kg REAL DEFAULT 0,     -- 월계: 입고(원재) 누계
        day_in_wage_net_kg REAL DEFAULT 0,    -- 일계: 입고(임) = 임가공입고 - 임가공반품
        mon_in_wage_net_kg REAL DEFAULT 0,    -- 월계: 입고(임) 누계
        day_out_fin_net_kg REAL DEFAULT 0,    -- 일계: 출고(제품) = 제품출고 - 제품반품
        mon_out_fin_net_kg REAL DEFAULT 0,    -- 월계: 출고(제품) 누계
        day_out_raw_net_kg REAL DEFAULT 0,    -- 일계: 출고(원재) = 원재출고 - 원재반품
        mon_out_raw_net_kg REAL DEFAULT 0,    -- 월계: 출고(원재) 누계
        approval_status TEXT DEFAULT '작성완료', -- 결재상태 (담당/차장/부장/이사/전무)
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [배포용 커스터마이징 3] 출고 명세서 (거래명세서, C000004/C000030) 테이블 (ecount_delivery_slips)
    # print-popup-observer.js mergeSalesSlipRows (강종->규격->구분 정렬, 중복행 병합, 10행 A4 분할) 호환
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_delivery_slips (
        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
        slip_date TEXT NOT NULL,           -- 전표일자 (YYYY-MM-DD)
        slip_serial_no TEXT NOT NULL,      -- 일련번호 (예: 20260630-1)
        recipient_name TEXT NOT NULL,      -- 상호 / 공급받는자(거래처명)
        out_wh_name TEXT DEFAULT '01.완제품', -- 출하창고 (01.완제품 또는 02.포장반)
        sales_gubun TEXT DEFAULT '제품',    -- 업무구분 (제품 / 임가공 / 원재료)
        steel_grade TEXT NOT NULL,         -- 강종 (grade)
        spec_display TEXT NOT NULL,        -- 규격 (sale003.no_user1 + TXT_ADD1 + sale003.no_user2)
        category_name TEXT DEFAULT '',     -- 구분 (칼라/표면: 청, 백, 연마(SIDE) 등)
        lot_no TEXT,                       -- 출고 코일 시리얼/로트번호
        unit_weight_kg REAL NOT NULL,      -- 단위환산량 (ADD_NUM_03, 코일당 kg)
        qty_ea INTEGER NOT NULL DEFAULT 1, -- 수량/EA (ADD_NUM_04, 코일수)
        total_weight_kg REAL NOT NULL,     -- 환산량/kg (총중량)
        unit_price REAL DEFAULT 0,         -- 단가 (SELL_D.price)
        supply_amt REAL DEFAULT 0,         -- 공급가액 (SELL_D.supply_amt)
        vat_amt REAL DEFAULT 0,            -- 부가세
        page_no INTEGER DEFAULT 1,         -- A4 인쇄 페이지 번호 (10행 단위 분할)
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [배포용 커스터마이징 4-A] 패킹리스트 (PACKING LIST, C000030) 테이블 (ecount_packing_lists)
    # print-popup-observer.js extractPackingListDocument & openPackingList (10칸 명세 CHUNK_SIZE=10, 12행 페이지, 공급자/공급받는자 2단)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_packing_lists (
        packing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        packing_date TEXT NOT NULL,        -- 작성일 (date)
        serial_num TEXT NOT NULL,          -- 전표 일련번호 (serialNum)
        recipient_name TEXT NOT NULL,      -- 업체명 (recipient)
        out_wh_name TEXT DEFAULT '01.완제품', -- 출하창고 (01.완제품: 국내/일반, 02.포장반: 수출출고)
        layout_id TEXT DEFAULT '_fixed_4dan', -- 양식 레이아웃 ('_fixed_4dan': [4단설정], '_fixed_1dan': [1단설정])
        spec_clean TEXT NOT NULL,          -- 규격 (spec-cell)
        steel_grade TEXT NOT NULL,         -- 강종 (grade-cell)
        category_name TEXT DEFAULT '',     -- 구분 (category)
        coil_count_ea INTEGER NOT NULL,    -- 해당 규격 코일 수 (EA)
        coil_weights_json TEXT NOT NULL,   -- 코일별 개별 중량 배열 JSON (10칸 명세표 출력용, 예: "[415, 415, 420]")
        subtotal_weight_kg REAL NOT NULL,  -- 소계 중량 (subtotal-cell, Kgs)
        doc_total_qty_ea INTEGER NOT NULL, -- 문서 전체 합계 코일수 (footer-qty)
        doc_total_weight_kg REAL NOT NULL, -- 문서 전체 합계 중량 (footer-detail-weight, Kgs)
        remarks TEXT DEFAULT '',           -- 비고 (footer-detail-bigo)
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # [배포용 커스터마이징 4-B] 출고 거래처 주소록 히스토리 테이블 (ecount_address_book)
    # address-search.js / options.js CSV 업로드 (거래처,수취인,전화번호,우편번호,우편주소,상세주소) 100% 호환
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ecount_address_book (
        addr_id INTEGER PRIMARY KEY AUTOINCREMENT,
        saved_date TEXT NOT NULL,          -- 날짜
        partner_name TEXT NOT NULL,        -- 거래처
        receiver_name TEXT NOT NULL,       -- 수취인
        phone_no TEXT,                     -- 전화번호
        zip_code TEXT,                     -- 우편번호
        road_address TEXT,                 -- 우편주소
        detail_address TEXT,               -- 상세주소
        wh_filter TEXT DEFAULT '01.완제품', -- 출하창고 필터
        UNIQUE(partner_name, receiver_name, zip_code, detail_address)
    );
    """)

    conn.commit()


def seed_master_data(conn):
    cur = conn.cursor()

    warehouses = [
        ("0.도스코", "도스코 원재료창고", "RAW", "0.도스코", "원재료", "원재료 매입 입고 및 외주가공 완료 입고 창고 (열처리 투입 시 출고처)"),
        ("01.연마", "연마대기 창고 (WIP)", "WIP_GRIND", "01.연마", "연마대기", "열처리 완료 후 연마 가공을 대기하는 생산재고 누적 창고 (연마 탭 투입 시 출고처)"),
        ("01.소폭", "소폭/수냉연마대기 창고 (WIP)", "WIP_NARROW", "01.소폭", "소폭대기", "6·7호기 수냉열처리 후 소폭/수냉연마 가공을 대기하는 재고 창고"),
        ("01.완제품", "완제품 창고", "FINISHED", "01.완제품", "완제품", "열처리 완제품 및 연마 완제품이 입고되어 국내 출고 또는 포장반 이동을 대기하는 창고"),
        ("02.포장반", "포장반 수출대기 창고", "PACKING", "포장반", "수출대기", "수출을 위한 가공·포장 완료 후 해외 선적 출고를 대기하는 창고"),
        ("09.불량품", "불량/스크랩/단가조정 장소", "DEFECT", "0.도스코(불량품)", "불량품", "스크랩 및 외주가공 단가조정 처리용 장소"),
        ("4.디아이스틸", "외주처: 디아이스틸", "SUBCONTRACT", "4.디아이스틸", "외주처", "압연/슬리팅 외주가공처 (로트 접미: -D01)"),
        ("4.이지철강", "외주처: 이지철강", "SUBCONTRACT", "4.이지철강", "외주처", "슬리팅/절단 외주가공처 (로트 접미: -E01)"),
        ("4.창성철강", "외주처: 창성철강", "SUBCONTRACT", "4.창성철강", "외주처", "절단/샤링 외주가공처 (로트 접미: -C01)"),
        ("4.아이엔", "외주처: 아이엔", "SUBCONTRACT", "4.아이엔", "외주처", "외주가공처 (로트 접미: -I01)"),
        ("4.면치용", "외주처: 면치용", "SUBCONTRACT", "4.면치용", "외주처", "엣지 면치 외주가공처"),
        ("명성스리팅", "외주처: 명성스리팅", "SUBCONTRACT", "명성스리팅", "외주처", "정밀 슬리팅 외주가공처 (로트 접미: -M01)")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO ecount_warehouses
        (wh_code, wh_name, wh_category, ecount_wh_name, default_location, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, warehouses)

    projects = [
        ("1호기", "1호기 (연속열처리)", "HEAT", "열처리", "0.도스코", "01.완제품", "YYYYMMDD-1XX", "3", "17,1", "1호기 열처리 생산 (연마 대상일 시 01.연마 입고)"),
        ("2호기", "2호기 (연속열처리)", "HEAT", "열처리", "0.도스코", "01.완제품", "YYYYMMDD-2XX", "3", "2,3,4", "2호기 열처리 생산 (연마 대상일 시 01.연마 입고)"),
        ("3호기", "3호기 (연속열처리)", "HEAT", "열처리", "0.도스코", "01.완제품", "YYYYMMDD-3XX", "3", "5,6", "3호기 열처리 생산 (연마 대상일 시 01.연마 입고)"),
        ("5호기", "5호기 (연속열처리)", "HEAT", "열처리", "0.도스코", "01.완제품", "YYYYMMDD-5XX", "3", "9,10", "5호기 열처리 생산 (연마 대상일 시 01.연마 입고)"),
        ("6호기", "6호기 (수냉열처리)", "QUENCH_HEAT", "수냉열처리", "0.도스코", "01.완제품", "YYYYMMDD-6XX", "3", "11,12", "6호기 수냉열처리 생산 (소폭/연마 대상일 시 01.소폭 입고)"),
        ("7호기", "7호기 (수냉열처리)", "QUENCH_HEAT", "수냉열처리", "0.도스코", "01.완제품", "YYYYMMDD-7XX", "3", "13,14", "7호기 수냉열처리 생산 (소폭/연마 대상일 시 01.소폭 입고)"),
        ("수냉연마", "수냉연마 (소폭연마)", "QUENCH_GRIND", "수냉연마", "01.소폭", "01.완제품", "YYYYMMDD-8XX", "4", "15", "수냉열처리 재고를 투입하여 수냉연마 후 완제품 창고 입고 (800번대 로트)"),
        ("연마", "연마 (표면/사이드/R면치)", "GRIND", "연마", "01.연마", "01.완제품", "YYYYMMDD-9XX", "4", "15,16", "열처리 연마대기 재고를 투입하여 연마 가공 후 완제품 창고 입고 (900번대 로트)"),
        ("포장반", "포장반 (수출포장가공)", "PACKING", "포장반", "01.완제품", "02.포장반", "YYYYMMDD-PXX", "3", "", "완제품을 수출 출고 대기용으로 포장 가공하여 포장반 창고 입고"),
        ("외주가공", "외주가공 (슬리팅/절단/압연)", "SUBCONTRACT", "외주가공", "4.외주처", "0.도스코", "YYYYMMDD-D/E/C/M", "", "", "외주 가공 완료 후 0.도스코 원재료 창고 입고"),
        ("조정,수정", "재고/단가 조정 및 대체처리", "ADJUST", "조정,수정", "0.도스코", "0.도스코", "", "", "", "대체처리 및 외주가공 단가조정 입력")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO ecount_projects
        (project_code, project_name, process_type, default_mgmt_item, default_out_wh, default_in_wh, lot_prefix_rule, group_suffix_code, cems_meter_ids, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, projects)

    mgmt_items = [
        ("투입", "투입 (원재료/연마대기재 소모)", "CONSUME", "ALL", "열처리 원재료 투입 또는 연마대기 재고 투입 소모 행"),
        ("재공", "재공 (투입 잔여중량 환원)", "WIP_RETURN", "ALL", "투입 총중량 중 미소모 잔여중량을 음수(-kg)로 출고창고에 환원 (로트 -1 부여)"),
        ("열처리", "열처리 (1·2·3·5호기 생산)", "PRODUCE", "HEAT", "1, 2, 3, 5호기 열처리 완제품 또는 연마대기품 생산 입고"),
        ("수냉열처리", "수냉열처리 (6·7호기 생산)", "PRODUCE", "QUENCH_HEAT", "6, 7호기 수냉열처리 완제품 또는 소폭대기품 생산 입고"),
        ("수냉연마", "수냉연마 (수냉연마 생산)", "PRODUCE", "QUENCH_GRIND", "수냉연마 완제품 생산 입고 (품번 끝자리 4, 로트 800번대)"),
        ("연마", "연마 (일반/SIDE/R면치 연마 생산)", "PRODUCE", "GRIND", "연마 완제품 생산 입고 (품번 끝자리 4, 로트 900번대)"),
        ("포장반", "포장반 (수출가공 완료 입고)", "PRODUCE", "PACKING", "수출 출고 대기용 포장반 가공 완료 입고"),
        ("외주가공", "외주가공 (외주 임가공 입고)", "PRODUCE", "SUBCONTRACT", "외주처 가공 후 도스코 창고 입고"),
        ("조정,수정", "조정,수정 (대체/수율조정)", "ADJUST", "ADJUST", "대체처리 및 외주 로스 조정"),
        ("단가조정", "단가조정 (외주 중량차이 조정)", "ADJUST", "SUBCONTRACT", "외주 투입-생산 중량 차이 조정 (품목코드 99 / 0099)")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO ecount_mgmt_items
        (mgmt_code, mgmt_name, io_direction, target_process, description)
        VALUES (?, ?, ?, ?, ?)
    """, mgmt_items)

    grades = [
        ("SK-5", "5", "-5", "-53", "-54", "HRC", "고탄소 공구강 (주력 강종)"),
        ("SK-4", "4", "-4", "-43", "-44", "HRC", "고탄소 공구강"),
        ("SK-3", "3", "-3", "-33", "-34", "HRC", "고탄소 공구강"),
        ("SK2CR4", "24", "-2", "-23", "-24", "HRC", "크롬 합금 공구강"),
        ("SKS-51", "51", "51", "513", "514", "HRC", "합금 공구강 (톱날/나이프용)"),
        ("SKS-7", "7", "-7", "-73", "-74", "HRC", "합금 공구강"),
        ("S50C", "50", "50", "503", "504", "HV", "기계구조용 탄소강"),
        ("S55C", "55", "50", "503", "504", "HV", "기계구조용 탄소강"),
        ("S60C", "60", "70", "703", "704", "HV", "기계구조용 탄소강"),
        ("S70C", "70", "70", "703", "704", "HV", "기계구조용 고탄소강"),
        ("S75C", "75", "70", "703", "704", "HV", "기계구조용 고탄소강"),
        ("SCM435", "43", "43", "433", "434", "HRC", "크롬몰리브덴강"),
        ("50CRV4", "54", "61", "613", "614", "HRC", "스프링강"),
        ("420J2", "42", "30", "303", "304", "HV", "마르텐사이트계 스테인리스강")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO ecount_steel_grades
        (grade_name, raw_code_prefix, raw_group_code, heat_group_code, grind_group_code, hardness_unit_default, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, grades)

    colors = [
        ("00", "원재료", "RAW", "일반 매입 원재료"),
        ("10", "BRIGHT", "HEAT", "광휘(유광) 열처리"),
        ("11", "원재료(임)", "RAW", "임가공용 원재료"),
        ("12", "원재료(R면치)", "RAW", "R면치 가공된 원재료"),
        ("13", "원재료(각면치)", "RAW", "각면치 가공된 원재료"),
        ("20", "백", "HEAT", "백색(유광) 템퍼링/연마"),
        ("22", "백(R면치)", "GRIND", "백색 R면치 가공"),
        ("23", "백(각면치)", "GRIND", "백색 각면치 가공"),
        ("30", "청", "HEAT", "청색(Blue) 열처리 완제품"),
        ("31", "녹색", "HEAT", "녹색 열처리"),
        ("32", "청(R면치)", "HEAT", "청색 R면치 열처리"),
        ("35", "청.R", "HEAT", "청색 R가공"),
        ("40", "연마", "GRIND", "표면 연마 완제품"),
        ("42", "연마(R면치)", "GRIND", "연마 및 R면치 완제품"),
        ("43", "연마(각면치)", "GRIND", "연마 및 각면치 완제품"),
        ("44", "연마(SIDE)", "GRIND", "사이드(폭) 정밀 연마 완제품"),
        ("50", "착색", "HEAT", "착색 열처리"),
        ("70", "PO", "RAW", "산세(Pickled & Oiled) 원재료"),
        ("71", "PO압연", "RAW", "PO 정밀압연 원재료"),
        ("80", "PA", "RAW", "소둔(Annealed) 원재료"),
        ("90", "임(열)", "HEAT", "임가공 열처리 제품"),
        ("95", "임(원재료)", "RAW", "임가공 원재료")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO ecount_colors
        (color_code, color_name, process_stage, description)
        VALUES (?, ?, ?, ?)
    """, colors)

    conn.commit()


def import_ecount_items(conn):
    if not os.path.exists(ITEM_XLSX_PATH):
        return 0

    cur = conn.cursor()
    with zipfile.ZipFile(ITEM_XLSX_PATH, 'r') as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                text_val = ''.join([t.text for t in si.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t') if t.text])
                shared_strings.append(text_val)

        s1_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        rows = s1_tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row')

        items_to_insert = []
        for row in rows[1:]:
            cols = {}
            for c in row.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                ref = ''.join([ch for ch in c.attrib.get('r', '') if ch.isalpha()])
                t_type = c.attrib.get('t')
                v_el = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                v_val = v_el.text if v_el is not None else ''
                if t_type == 's' and v_val.isdigit():
                    val = shared_strings[int(v_val)]
                else:
                    val = v_val
                cols[ref] = val

            code = cols.get('A', '').strip()
            name = cols.get('B', '').strip()
            spec = cols.get('D', '').strip()
            unit = cols.get('E', 'KG').strip()
            itype = cols.get('F', '0').strip()
            group_code = cols.get('H', '').strip()
            try:
                thick = round(float(cols.get('N', 0) or 0), 3)
            except:
                thick = 0.0
            try:
                width = round(float(cols.get('O', 0) or 0), 2)
            except:
                width = 0.0
            try:
                cut_len = round(float(cols.get('P', 0) or 0), 1)
            except:
                cut_len = 0.0

            hard_code = cols.get('Q', '').strip()
            color_code = cols.get('R', '').strip()
            mgmt_flag = cols.get('S', 'B').strip()
            lot_flag = cols.get('T', 'B').strip()

            color_name = ''
            hard_disp = ''
            if '(' in spec and ')' in spec:
                p1 = spec.find('(')
                p2 = spec.rfind(')')
                color_name = spec[p1+1:p2]
                hard_disp = spec[p2+1:].strip()

            parts = [p for p in code.split('-') if p]
            alt_code = code
            if len(parts) == 3 and len(parts[1]) >= 8:
                alt_code = f"{parts[1]}-{parts[0]}-{parts[2]}"

            if code:
                items_to_insert.append((
                    code, alt_code, name, itype, group_code,
                    thick, width, cut_len, color_code, color_name,
                    hard_code, hard_disp, spec, unit, mgmt_flag, lot_flag
                ))

        cur.executemany("""
            INSERT OR REPLACE INTO ecount_items
            (item_code, legacy_item_code, item_name, item_type, group_code,
             thickness, width, cut_length, color_code, color_name,
             hardness_code, hardness_display, spec_full, unit, mgmt_flag, lot_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, items_to_insert)
        conn.commit()
        return len(items_to_insert)


def parse_spec_components(spec_str):
    if not spec_str:
        return (0.0, 0.0, 0.0, '', '')
    s = spec_str.strip()
    color = ''
    hardness = ''
    dim_part = s
    if '(' in s and ')' in s:
        p1 = s.find('(')
        p2 = s.rfind(')')
        color = s[p1+1:p2].strip()
        hardness = s[p2+1:].strip()
        dim_part = s[:p1].rstrip('*').strip()
    dims = [d.replace(',', '').strip() for d in dim_part.split('*') if d.strip()]
    thick = float(dims[0]) if len(dims) >= 1 and re.match(r'^\d+(\.\d+)?$', dims[0]) else 0.0
    width = float(dims[1]) if len(dims) >= 2 and re.match(r'^\d+(\.\d+)?$', dims[1]) else 0.0
    cut_len = float(dims[2]) if len(dims) >= 3 and re.match(r'^\d+(\.\d+)?$', dims[2]) else 0.0
    return (thick, width, cut_len, color, hardness)


def import_historical_slips_and_populate_processes(conn):
    if not os.path.exists(HIST_XLSX_PATH):
        return 0

    cur = conn.cursor()
    cur.execute("DELETE FROM ecount_erp_slips;")
    cur.execute("DELETE FROM proc_1_raw_inbounds;")
    cur.execute("DELETE FROM proc_2_heat_treatment;")
    cur.execute("DELETE FROM proc_3_grinding_wait_stock;")
    cur.execute("DELETE FROM proc_4_grinding_production;")
    cur.execute("DELETE FROM proc_5_finished_and_packing;")

    with zipfile.ZipFile(HIST_XLSX_PATH, 'r') as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                text_val = ''.join([t.text for t in si.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t') if t.text])
                shared_strings.append(text_val)

        s_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        rows = s_tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row')

        def num(v):
            try:
                return float(str(v).replace(',', '').strip())
            except:
                return 0.0

        slip_count = 0
        grouped = {}
        order_keys = []

        for row in rows[1:]:
            cols = {}
            for c in row.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                ref = ''.join([ch for ch in c.attrib.get('r', '') if ch.isalpha()])
                t_type = c.attrib.get('t')
                v_el = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                v_val = v_el.text if v_el is not None else ''
                if t_type == 's' and v_val.isdigit():
                    val = shared_strings[int(v_val)]
                else:
                    val = v_val
                cols[ref] = val

            doc_no = cols.get('A', '').strip()
            if not doc_no or '계' in doc_no:
                continue

            rec = {
                'doc_date_no': doc_no,
                'writer': cols.get('B', '송구현').strip(),
                'project': cols.get('C', '').strip(),
                'mgmt': cols.get('D', '').strip(),
                'manager': cols.get('E', '송구현').strip(),
                'c_name': cols.get('F', '').strip(),
                'c_spec': cols.get('G', '').strip(),
                'c_lot': cols.get('H', '').strip(),
                'c_code': cols.get('I', '').strip(),
                'p_code': cols.get('J', '').strip(),
                'p_name': cols.get('K', '').strip(),
                'p_spec': cols.get('L', '').strip(),
                'color': cols.get('M', '').strip(),
                'p_lot': cols.get('N', '').strip(),
                'unit_kg': num(cols.get('O', 0)),
                'qty_ea': int(num(cols.get('P', 1)) or 1),
                'input_kg': num(cols.get('Q', 0)),
                'prod_kg': num(cols.get('R', 0)),
                'consume_kg': num(cols.get('S', 0)),
                'out_wh': cols.get('T', '0.도스코').strip(),
                'in_wh': cols.get('U', '01.완제품').strip(),
            }

            cur.execute("""
                INSERT INTO ecount_erp_slips
                (doc_date_no, writer_name, project_name, mgmt_item, manager_name,
                 consume_item_name, consume_spec, consume_serial_lot, consume_item_code,
                 prod_item_code, prod_item_name, prod_spec, color_name, prod_serial_lot,
                 unit_weight_kg, qty_ea, input_kg, prod_kg, consume_kg, out_wh_name, in_wh_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec['doc_date_no'], rec['writer'], rec['project'], rec['mgmt'], rec['manager'],
                rec['c_name'], rec['c_spec'], rec['c_lot'], rec['c_code'],
                rec['p_code'], rec['p_name'], rec['p_spec'], rec['color'], rec['p_lot'],
                rec['unit_kg'], rec['qty_ea'], rec['input_kg'], rec['prod_kg'], rec['consume_kg'],
                rec['out_wh'], rec['in_wh']
            ))
            slip_count += 1

            if doc_no not in grouped:
                grouped[doc_no] = []
                order_keys.append(doc_no)
            grouped[doc_no].append(rec)

        for doc_no in order_keys:
            items = grouped[doc_no]
            proj = items[0]['project']
            work_date = doc_no.split()[0].replace('/', '-') if '/' in doc_no else doc_no[:10]

            consume_row = next((x for x in items if x['mgmt'] == '투입'), None)
            wip_row = next((x for x in items if x['mgmt'] == '재공'), None)
            prod_rows = [x for x in items if x['mgmt'] in ('열처리', '수냉열처리', '연마', '수냉연마', '외주가공')]

            if proj == '외주가공':
                for pr in prod_rows:
                    t, w, c_len, col, hard = parse_spec_components(pr['p_spec'])
                    cur.execute("""
                        INSERT INTO proc_1_raw_inbounds
                        (doc_date_no, inbound_type, project_name, mgmt_item, partner_or_out_wh, in_wh,
                         item_code, steel_grade, thickness, width, cut_length, color_name, hardness_display,
                         spec_full, lot_no, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, worker_name)
                        VALUES (?, 'SUBCONTRACT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_no, proj, pr['mgmt'], pr['out_wh'], pr['in_wh'] or '0.도스코',
                        pr['p_code'], pr['p_name'] or 'SK-5', t, w, c_len, col or '원재료', hard or 'R',
                        pr['p_spec'], pr['p_lot'] or f"{work_date.replace('-','')}-D01",
                        pr['unit_kg'], pr['qty_ea'], pr['prod_kg'] or pr['unit_kg'], pr['prod_kg'] or pr['unit_kg'],
                        pr['manager']
                    ))

            elif proj in ('1호기', '2호기', '3호기', '5호기', '6호기', '7호기'):
                for pr in prod_rows:
                    rt, rw, rcl, rcol, rhard = parse_spec_components(consume_row['c_spec'] if consume_row else pr['p_spec'])
                    pt, pw, pcl, pcol, phard = parse_spec_components(pr['p_spec'])
                    in_wh = pr['in_wh'] or '01.완제품'
                    next_route = 'GRIND_WAIT' if in_wh == '01.연마' else ('NARROW_WAIT' if in_wh == '01.소폭' else 'FINISHED')
                    in_total = (consume_row['input_kg'] or consume_row['unit_kg']) if consume_row else pr['consume_kg']
                    wip_kg = (wip_row['input_kg'] or wip_row['unit_kg']) if wip_row else 0.0
                    p_total = pr['prod_kg'] or pr['unit_kg']
                    scrap = max(0.0, (in_total + wip_kg) - p_total) if in_total > 0 else 0.0
                    p_lot = pr['p_lot'] or f"{work_date.replace('-','')}-{proj[0]}01"
                    col_final = pcol or pr['color'] or '청'
                    hard_final = phard or 'HRC45'

                    cur.execute("""
                        INSERT INTO proc_2_heat_treatment
                        (doc_date_no, work_date, project_name, worker_name, out_wh, consume_mgmt,
                         raw_item_code, raw_steel_grade, raw_thickness, raw_width, raw_cut_length, raw_spec_full, raw_lot_no,
                         input_unit_kg, input_qty_ea, input_total_kg, wip_return_kg, wip_lot_no,
                         next_route, in_wh, prod_mgmt, prod_item_code, prod_steel_grade,
                         prod_thickness, prod_width, prod_cut_length, prod_color, prod_hardness, prod_spec_full,
                         prod_lot_no, unit_weight_kg, qty_ea, total_weight_kg, scrap_kg)
                        VALUES (?, ?, ?, ?, ?, '투입', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_no, work_date, proj, pr['manager'], pr['out_wh'] or '0.도스코',
                        consume_row['c_code'] if consume_row else '',
                        (consume_row['c_name'] if consume_row and consume_row['c_name'] else pr['p_name']) or 'SK-5',
                        rt, rw, rcl,
                        consume_row['c_spec'] if consume_row else '',
                        consume_row['c_lot'] if consume_row else '',
                        consume_row['unit_kg'] if consume_row else 0,
                        consume_row['qty_ea'] if consume_row else 1,
                        in_total, wip_kg,
                        wip_row['c_lot'] if wip_row else '',
                        next_route, in_wh, pr['mgmt'], pr['p_code'], pr['p_name'] or 'SK-5',
                        pt, pw, pcl, col_final, hard_final, pr['p_spec'],
                        p_lot, pr['unit_kg'], pr['qty_ea'], p_total, scrap
                    ))
                    heat_id = cur.lastrowid

                    if in_wh in ('01.연마', '01.소폭') and p_lot:
                        cur.execute("""
                            INSERT OR IGNORE INTO proc_3_grinding_wait_stock
                            (wh_code, source_heat_id, source_project, prod_date, heat_lot_no,
                             item_code, steel_grade, thickness, width, cut_length, color_name, hardness_display,
                             spec_full, unit_weight_kg, init_qty_ea, remain_qty_ea, init_weight_kg, used_weight_kg, remain_weight_kg, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'WAITING')
                        """, (
                            in_wh, heat_id, proj, work_date, p_lot,
                            pr['p_code'], pr['p_name'] or 'SK-5', pt, pw, pcl, col_final, hard_final,
                            pr['p_spec'], pr['unit_kg'], pr['qty_ea'], pr['qty_ea'], p_total, p_total
                        ))
                    elif in_wh == '01.완제품' and p_lot:
                        cur.execute("""
                            INSERT INTO proc_5_finished_and_packing
                            (doc_date_no, process_stage, project_name, mgmt_item, out_wh, in_wh,
                             source_type, source_lot_no, item_code, steel_grade, thickness, width, cut_length,
                             color_name, hardness_display, spec_full, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, worker_name)
                            VALUES (?, 'FINISHED_STOCK', ?, ?, '0.도스코', '01.완제품',
                                    'HEAT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            doc_no, proj, pr['mgmt'], p_lot, pr['p_code'], pr['p_name'] or 'SK-5',
                            pt, pw, pcl, col_final, hard_final, pr['p_spec'],
                            pr['unit_kg'], pr['qty_ea'], p_total, p_total, pr['manager']
                        ))

            elif proj in ('연마', '수냉연마'):
                for pr in prod_rows:
                    pt, pw, pcl, pcol, phard = parse_spec_components(pr['p_spec'])
                    c_lot = consume_row['c_lot'] if consume_row else ''
                    c_total = (consume_row['input_kg'] or consume_row['unit_kg']) if consume_row else pr['consume_kg']
                    p_total = pr['prod_kg'] or pr['unit_kg']
                    scrap = max(0.0, c_total - p_total) if c_total > 0 else 0.0
                    p_lot = pr['p_lot'] or f"{work_date.replace('-','')}-{'901' if proj == '연마' else '801'}"
                    col_final = pcol or pr['color'] or '연마'
                    hard_final = phard or 'HRC45'

                    cur.execute("""
                        INSERT INTO proc_4_grinding_production
                        (doc_date_no, work_date, project_name, worker_name,
                         out_wh, consume_mgmt, consume_item_code, consume_steel_grade, consume_spec_full,
                         consume_heat_lot_no, consume_unit_kg, consume_qty_ea, consume_total_kg,
                         in_wh, prod_mgmt, prod_item_code, prod_steel_grade,
                         prod_thickness, prod_width, prod_cut_length, prod_color, prod_hardness, prod_spec_full,
                         prod_lot_no, unit_weight_kg, qty_ea, total_weight_kg, scrap_kg)
                        VALUES (?, ?, ?, ?, ?, '투입', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_no, work_date, proj, pr['manager'],
                        '01.연마' if proj == '연마' else '01.소폭',
                        consume_row['c_code'] if consume_row else '',
                        (consume_row['c_name'] if consume_row and consume_row['c_name'] else pr['p_name']) or 'SK-5',
                        consume_row['c_spec'] if consume_row else pr['p_spec'],
                        c_lot,
                        consume_row['unit_kg'] if consume_row else c_total,
                        consume_row['qty_ea'] if consume_row else 1,
                        c_total,
                        pr['in_wh'] or '01.완제품', pr['mgmt'], pr['p_code'], pr['p_name'] or 'SK-5',
                        pt, pw, pcl, col_final, hard_final, pr['p_spec'],
                        p_lot, pr['unit_kg'], pr['qty_ea'], p_total, scrap
                    ))

                    # 연마 생산품 -> 01.완제품 창고 재고 테이블(proc_5_finished_and_packing)에 입고!
                    cur.execute("""
                        INSERT INTO proc_5_finished_and_packing
                        (doc_date_no, process_stage, project_name, mgmt_item, out_wh, in_wh,
                         source_type, source_lot_no, item_code, steel_grade, thickness, width, cut_length,
                         color_name, hardness_display, spec_full, unit_weight_kg, qty_ea, total_weight_kg, remain_weight_kg, worker_name)
                        VALUES (?, 'FINISHED_STOCK', ?, ?, ?, '01.완제품',
                                'GRIND', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_no, proj, pr['mgmt'], '01.연마' if proj == '연마' else '01.소폭',
                        p_lot, pr['p_code'], pr['p_name'] or 'SK-5',
                        pt, pw, pcl, col_final, hard_final, pr['p_spec'],
                        pr['unit_kg'], pr['qty_ea'], p_total, p_total, pr['manager']
                    ))

        conn.commit()
        return slip_count


def normalize_spec_for_daily_report(raw_spec):
    """
    popup-daily-report.js 의 normalizeSpec(rawSpec) 100% 동일 구현
    예: '1.200*121.00*(청)HRC45' -> '1.200*121.00'
    """
    spec = str(raw_spec or '').strip()
    star_paren_idx = spec.find('*(')
    m = re.match(r'^\s*\d+(?:\.\d+)?\*\d+(?:\.\d+)?\*\d+(?:\.\d+)?\(', spec)
    cut_idx = star_paren_idx if star_paren_idx >= 0 else (m.group(0).rfind('(') if m else -1)
    return spec[:cut_idx] if cut_idx >= 0 else spec


def populate_customizing_extension_tables(conn):
    """
    Ecount-Chrome-Extension - 배포용 (v0.1.42) 4대 핵심 기능 테이블 데이터 생성 및 동기화:
    1. ecount_serial_issue_history (일반생산 generalSerialIssueHistory & 재공생산 wipSerialIssueHistory)
    2. ecount_daily_report_details & ecount_daily_report_summary (일일업무일지: 생산/입고/출고 & 요약결재)
    3. ecount_delivery_slips (출고 명세서 / 거래명세서 C000004/C000030)
    4. ecount_packing_lists & ecount_address_book (패킹리스트 10칸 명세표 & 출고 주소록)
    """
    import json
    cur = conn.cursor()
    cur.execute("DELETE FROM ecount_serial_issue_history;")
    cur.execute("DELETE FROM ecount_daily_report_details;")
    cur.execute("DELETE FROM ecount_daily_report_summary;")
    cur.execute("DELETE FROM ecount_delivery_slips;")
    cur.execute("DELETE FROM ecount_packing_lists;")
    cur.execute("DELETE FROM ecount_address_book;")

    now_ms = int(datetime.now().timestamp() * 1000)

    # 1. 시리얼 발행 이력 (ecount_serial_issue_history) 추출
    cur.execute("SELECT consume_serial_lot, prod_serial_lot, mgmt_item FROM ecount_erp_slips")
    for c_lot, p_lot, mgmt in cur.fetchall():
        # 일반생산 시리얼: YYYYMMDD-101, YYYYMMDD-801, YYYYMMDD-901, YYYYMMDD-D01 등
        if p_lot and '-' in p_lot:
            parts = p_lot.strip().split('-')
            if len(parts) == 2 and len(parts[0]) == 8 and parts[0].isdigit():
                date_str, suffix_part = parts[0], parts[1]
                m_alpha = re.match(r'^([A-Za-z])(\d+)$', suffix_part)
                m_num = re.match(r'^(\d)(\d{2})$', suffix_part)
                if m_alpha:
                    rec_key = f"{date_str}-{m_alpha.group(1)}"
                    sfx = int(m_alpha.group(2))
                    cur.execute("""
                        INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                        VALUES ('generalSerialIssueHistory', ?, ?, ?, ?)
                        ON CONFLICT(history_type, record_key) DO UPDATE SET
                            last_suffix = MAX(last_suffix, excluded.last_suffix),
                            last_serial_full = CASE WHEN excluded.last_suffix >= last_suffix THEN excluded.last_serial_full ELSE last_serial_full END
                    """, (rec_key, sfx, p_lot.strip(), now_ms))
                elif m_num:
                    rec_key = f"{date_str}-{m_num.group(1)}"
                    sfx = int(suffix_part)
                    cur.execute("""
                        INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                        VALUES ('generalSerialIssueHistory', ?, ?, ?, ?)
                        ON CONFLICT(history_type, record_key) DO UPDATE SET
                            last_suffix = MAX(last_suffix, excluded.last_suffix),
                            last_serial_full = CASE WHEN excluded.last_suffix >= last_suffix THEN excluded.last_serial_full ELSE last_serial_full END
                    """, (rec_key, sfx, p_lot.strip(), now_ms))

        # 재공생산 시리얼: baseSerialText-1, -2, -01 등
        if mgmt == '재공' and c_lot and '-' in c_lot:
            r_idx = c_lot.rfind('-')
            base_serial = c_lot[:r_idx].strip()
            sfx_str = c_lot[r_idx+1:].strip()
            if base_serial and sfx_str.isdigit() and int(sfx_str) > 0:
                cur.execute("""
                    INSERT INTO ecount_serial_issue_history (history_type, record_key, last_suffix, last_serial_full, updated_at)
                    VALUES ('wipSerialIssueHistory', ?, ?, ?, ?)
                    ON CONFLICT(history_type, record_key) DO UPDATE SET
                        last_suffix = MAX(last_suffix, excluded.last_suffix),
                        last_serial_full = CASE WHEN excluded.last_suffix >= last_suffix THEN excluded.last_serial_full ELSE last_serial_full END
                """, (base_serial, int(sfx_str), c_lot.strip(), now_ms))

    # 2. 일일업무일지 (ecount_daily_report_details & ecount_daily_report_summary) 생성
    cur.execute("""
        SELECT doc_date_no, project_name, mgmt_item, prod_item_name, prod_spec, color_name, prod_kg, unit_weight_kg, out_wh_name, in_wh_name
        FROM ecount_erp_slips
        WHERE mgmt_item IN ('열처리', '수냉열처리', '연마', '수냉연마', '외주가공')
    """)
    daily_Bucket = {}
    for doc_no, proj, mgmt, p_name, p_spec, col, prod_kg, unit_kg, out_wh, in_wh in cur.fetchall():
        d_str = doc_no.split()[0].replace('/', '-') if '/' in doc_no else doc_no[:10]
        qty = float(prod_kg or unit_kg or 0)
        if qty <= 0:
            continue
        if d_str not in daily_Bucket:
            daily_Bucket[d_str] = {'prod': [], 'purch': [], 'sales': []}
        norm_spec = normalize_spec_for_daily_report(p_spec)
        _, _, _, parsed_col, _ = parse_spec_components(p_spec)
        final_col = col or parsed_col or ''
        if mgmt == '외주가공':
            daily_Bucket[d_str]['purch'].append({
                'gubun': '임가공',
                'material': p_name or 'SK-5',
                'spec': norm_spec,
                'color': final_col or '원재료',
                'raw_qty': 0.0,
                'wage_qty': qty,
                'partner': out_wh or '4.디아이스틸'
            })
        else:
            kind = 'heat' if mgmt == '열처리' else ('cool' if mgmt == '수냉열처리' else 'grind')
            gubun_disp = '열처리' if kind == 'heat' else ('수냉' if kind == 'cool' else '연마')
            div_val = re.sub(r'[^0-9]', '', proj) if (kind == 'heat' and '호기' in proj) else final_col
            daily_Bucket[d_str]['prod'].append({
                'gubun': gubun_disp,
                'kind': kind,
                'material': p_name or 'SK-5',
                'spec': norm_spec,
                'division': div_val,
                'heat_qty': qty if kind == 'heat' else 0.0,
                'cool_qty': qty if kind == 'cool' else 0.0,
                'grind_qty': qty if kind == 'grind' else 0.0,
            })
            if in_wh == '01.완제품':
                daily_Bucket[d_str]['sales'].append({
                    'gubun': '제품',
                    'material': p_name or 'SK-5',
                    'spec': norm_spec,
                    'color': final_col,
                    'fin_qty': qty,
                    'raw_qty': 0.0,
                    'partner': '국내출고/포장반'
                })

    mon_heat_cool = 0.0
    mon_grind = 0.0
    mon_in_raw = 0.0
    mon_in_wage = 0.0
    mon_out_fin = 0.0
    mon_out_raw = 0.0

    for d_str in sorted(daily_Bucket.keys()):
        b = daily_Bucket[d_str]
        d_heat_cool = sum(x['heat_qty'] + x['cool_qty'] for x in b['prod'])
        d_grind = sum(x['grind_qty'] for x in b['prod'])
        d_in_raw = sum(x['raw_qty'] for x in b['purch'])
        d_in_wage = sum(x['wage_qty'] for x in b['purch'])
        d_out_fin = sum(x['fin_qty'] for x in b['sales'])

        mon_heat_cool += d_heat_cool
        mon_grind += d_grind
        mon_in_raw += d_in_raw
        mon_in_wage += d_in_wage
        mon_out_fin += d_out_fin

        for idx, r in enumerate(b['prod'], 1):
            cur.execute("""
                INSERT INTO ecount_daily_report_details
                (report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized, division_or_color,
                 heat_qty_kg, cool_qty_kg, grind_qty_kg)
                VALUES (?, 'PROD', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d_str, idx, r['gubun'], r['material'], r['spec'], r['division'], r['heat_qty'], r['cool_qty'], r['grind_qty']))

        for idx, r in enumerate(b['purch'], 1):
            cur.execute("""
                INSERT INTO ecount_daily_report_details
                (report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized, division_or_color,
                 raw_qty_kg, wage_or_fin_qty_kg, partner_name)
                VALUES (?, 'PURCH', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d_str, idx, r['gubun'], r['material'], r['spec'], r['color'], r['raw_qty'], r['wage_qty'], r['partner']))

        for idx, r in enumerate(b['sales'], 1):
            cur.execute("""
                INSERT INTO ecount_daily_report_details
                (report_date, section_type, seq_no, orig_gubun, material_grade, spec_normalized, division_or_color,
                 wage_or_fin_qty_kg, raw_qty_kg, partner_name)
                VALUES (?, 'SALES', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d_str, idx, r['gubun'], r['material'], r['spec'], r['color'], r['fin_qty'], r['raw_qty'], r['partner']))

        parts = d_str.split('-')
        sheet_nm = f"{int(parts[1]):02d}월{int(parts[2]):02d}일" if len(parts) == 3 else d_str
        cur.execute("""
            INSERT OR REPLACE INTO ecount_daily_report_summary
            (report_date, sheet_name, day_prod_heat_cool_kg, mon_prod_heat_cool_kg,
             day_prod_grind_kg, mon_prod_grind_kg, day_in_raw_net_kg, mon_in_raw_net_kg,
             day_in_wage_net_kg, mon_in_wage_net_kg, day_out_fin_net_kg, mon_out_fin_net_kg,
             day_out_raw_net_kg, mon_out_raw_net_kg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        """, (d_str, sheet_nm, d_heat_cool, mon_heat_cool, d_grind, mon_grind, d_in_raw, mon_in_raw, d_in_wage, mon_in_wage, d_out_fin, mon_out_fin))

    # 3. 출고 명세서(ecount_delivery_slips) 및 패킹리스트(ecount_packing_lists) 생성 (01.완제품 및 02.포장반 기준)
    cur.execute("""
        SELECT doc_date_no, project_name, source_lot_no, steel_grade, spec_full, color_name, unit_weight_kg, qty_ea, total_weight_kg
        FROM proc_5_finished_and_packing
        ORDER BY rowid ASC
    """)
    fin_rows = cur.fetchall()
    slip_groups = {}
    for doc_no, proj, lot_no, grade, spec_full, color_nm, unit_kg, qty_ea, total_kg in fin_rows:
        d_str = doc_no.split()[0].replace('/', '-') if '/' in doc_no else doc_no[:10]
        serial_no = doc_no.replace('/', '-').replace(' ', '')
        recipient = "수출포장반(해외바이어)" if proj in ('연마', '수냉연마') else "(주)도스코 국내거래처"
        out_wh = "02.포장반" if proj in ('연마', '수냉연마') else "01.완제품"
        norm_spec = normalize_spec_for_daily_report(spec_full)
        ea = max(1, int(qty_ea or 1))
        u_kg = float(unit_kg or total_kg or 0)
        t_kg = float(total_kg or (u_kg * ea))

        cur.execute("""
            INSERT INTO ecount_delivery_slips
            (slip_date, slip_serial_no, recipient_name, out_wh_name, sales_gubun,
             steel_grade, spec_display, category_name, lot_no, unit_weight_kg, qty_ea, total_weight_kg,
             unit_price, supply_amt, vat_amt, page_no)
            VALUES (?, ?, ?, ?, '제품', ?, ?, ?, ?, ?, ?, ?, 3500, ?, ?, 1)
        """, (d_str, serial_no, recipient, out_wh, grade, norm_spec, color_nm, lot_no, u_kg, ea, t_kg, round(t_kg * 3500), round(t_kg * 350)))

        g_key = (d_str, serial_no, recipient, out_wh)
        if g_key not in slip_groups:
            slip_groups[g_key] = {}
        item_key = (norm_spec, grade, color_nm)
        if item_key not in slip_groups[g_key]:
            slip_groups[g_key][item_key] = []
        for _ in range(ea):
            slip_groups[g_key][item_key].append(round(u_kg, 2))

    for (d_str, serial_no, recipient, out_wh), items_dict in slip_groups.items():
        doc_total_ea = sum(len(weights) for weights in items_dict.values())
        doc_total_kg = round(sum(sum(weights) for weights in items_dict.values()), 3)
        for (norm_spec, grade, color_nm), weights in items_dict.items():
            cur.execute("""
                INSERT INTO ecount_packing_lists
                (packing_date, serial_num, recipient_name, out_wh_name, layout_id,
                 spec_clean, steel_grade, category_name, coil_count_ea, coil_weights_json,
                 subtotal_weight_kg, doc_total_qty_ea, doc_total_weight_kg, remarks)
                VALUES (?, ?, ?, ?, '_fixed_4dan', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d_str, serial_no, recipient, out_wh,
                norm_spec, grade, color_nm, len(weights), json.dumps(weights, ensure_ascii=False),
                round(sum(weights), 3), doc_total_ea, doc_total_kg,
                "수출포장 대기" if out_wh == "02.포장반" else "국내출고"
            ))

    # 4. 기본 거래처/외주처 주소록 (ecount_address_book) 시드
    addresses = [
        ("2026-06-30", "4.디아이스틸", "디아이스틸 출하담당", "031-000-0001", "15000", "경기도 시흥시 산기대학로", "시화공단 슬리팅공장", "0.도스코"),
        ("2026-06-30", "4.이지철강", "이지철강 담당자", "031-000-0002", "15001", "경기도 안산시 단원구", "반월공단 1블럭", "0.도스코"),
        ("2026-06-30", "4.창성철강", "창성철강 담당자", "031-000-0003", "15002", "경기도 시흥시 공단1대로", "절단가공동", "0.도스코"),
        ("2026-06-30", "명성스리팅", "명성스리팅 담당자", "031-000-0004", "15003", "경기도 시흥시 마유로", "스리팅동", "0.도스코"),
        ("2026-06-30", "(주)도스코 수출포장반", "포장반장", "032-000-0005", "21000", "인천광역시 서구 가좌동", "도스코 포장반 (수출출고대기)", "02.포장반"),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO ecount_address_book
        (saved_date, partner_name, receiver_name, phone_no, zip_code, road_address, detail_address, wh_filter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, addresses)
    conn.commit()


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    seed_master_data(conn)
    item_cnt = import_ecount_items(conn)
    slip_cnt = import_historical_slips_and_populate_processes(conn)
    populate_customizing_extension_tables(conn)

    cur = conn.cursor()
    tables = [
        "ecount_warehouses", "ecount_projects", "ecount_mgmt_items",
        "ecount_steel_grades", "ecount_colors", "ecount_items",
        "proc_1_raw_inbounds", "proc_2_heat_treatment",
        "proc_3_grinding_wait_stock", "proc_4_grinding_production",
        "proc_5_finished_and_packing", "ecount_erp_slips",
        "ecount_serial_issue_history", "ecount_daily_report_details",
        "ecount_daily_report_summary", "ecount_delivery_slips",
        "ecount_packing_lists", "ecount_address_book"
    ]
    print(f"=== DOSKO ECOUNT DB INITIALIZED (WITH EXTENSION v0.1.42 TABLES): {DB_PATH} ===")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  - {t}: {cur.fetchone()[0]} rows")

    # Test automatic generator
    code, leg, spec = generate_ecount_item_code_and_spec("SK-5", 1.2, 120.0, 0, "연마(SIDE)", "HRC45")
    print(f"  - Generator Test: code={code}, legacy={leg}, spec={spec}")
    conn.close()
