-- ============================================================================
-- (주)도스코 통합 MES/ERP/보안 MSSQL 2019 Standard DDL 스크립트 (v2.0)
-- Database: DOSKO_ERP (Collation: Korean_Wansung_CI_AS, Port: 5539)
-- 구성: 33개 테이블 (기준정보 8 + 타임라인/PLC 3 + 공정/ERP/QC 15 + ETL 2 + 보안 5) + 4개 뷰
-- ============================================================================
USE master;
GO
IF DB_ID(N'DOSKO_ERP') IS NULL
BEGIN
    CREATE DATABASE [DOSKO_ERP] COLLATE Korean_Wansung_CI_AS;
END
GO
ALTER DATABASE [DOSKO_ERP] SET RECOVERY SIMPLE WITH NO_WAIT;
GO
ALTER DATABASE [DOSKO_ERP] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
GO
USE [DOSKO_ERP];
GO

-- ============================================================================
-- 0. 안전 재구축을 위한 뷰 및 FK 자식 -> 부모 역순 DROP
-- ============================================================================
IF OBJECT_ID(N'dbo.v_plc_with_confirmed_spec', N'V') IS NOT NULL DROP VIEW dbo.v_plc_with_confirmed_spec;
IF OBJECT_ID(N'dbo.v_lot_genealogy', N'V') IS NOT NULL DROP VIEW dbo.v_lot_genealogy;
IF OBJECT_ID(N'dbo.v_ecount_warehouse_stock_summary', N'V') IS NOT NULL DROP VIEW dbo.v_ecount_warehouse_stock_summary;
IF OBJECT_ID(N'dbo.v_secure_douzone_trades', N'V') IS NOT NULL DROP VIEW dbo.v_secure_douzone_trades;
GO

-- Layer 5 Security (자식 -> 부모)
IF OBJECT_ID(N'dbo.sec_audit_logs', N'U') IS NOT NULL DROP TABLE dbo.sec_audit_logs;
IF OBJECT_ID(N'dbo.sec_sessions', N'U') IS NOT NULL DROP TABLE dbo.sec_sessions;
IF OBJECT_ID(N'dbo.sec_api_tokens', N'U') IS NOT NULL DROP TABLE dbo.sec_api_tokens;
IF OBJECT_ID(N'dbo.sec_role_permissions', N'U') IS NOT NULL DROP TABLE dbo.sec_role_permissions;
IF OBJECT_ID(N'dbo.sec_users', N'U') IS NOT NULL DROP TABLE dbo.sec_users;

-- Layer 4 ETL (자식 -> 부모)
IF OBJECT_ID(N'dbo.etl_anomaly_logs', N'U') IS NOT NULL DROP TABLE dbo.etl_anomaly_logs;
IF OBJECT_ID(N'dbo.etl_batch_runs', N'U') IS NOT NULL DROP TABLE dbo.etl_batch_runs;

-- Layer 3 공정/ERP/QC/DOM & Layer 2 자식 (prod_coil_runs 참조자 우선 DROP)
IF OBJECT_ID(N'dbo.qc_inspection_drafts', N'U') IS NOT NULL DROP TABLE dbo.qc_inspection_drafts;
IF OBJECT_ID(N'dbo.ecount_dom_schemas', N'U') IS NOT NULL DROP TABLE dbo.ecount_dom_schemas;
IF OBJECT_ID(N'dbo.work_event_logs', N'U') IS NOT NULL DROP TABLE dbo.work_event_logs;
IF OBJECT_ID(N'dbo.plc_5min_logs', N'U') IS NOT NULL DROP TABLE dbo.plc_5min_logs;
IF OBJECT_ID(N'dbo.ecount_daily_report_details', N'U') IS NOT NULL DROP TABLE dbo.ecount_daily_report_details;
IF OBJECT_ID(N'dbo.ecount_daily_report_summary', N'U') IS NOT NULL DROP TABLE dbo.ecount_daily_report_summary;
IF OBJECT_ID(N'dbo.ecount_packing_lists', N'U') IS NOT NULL DROP TABLE dbo.ecount_packing_lists;
IF OBJECT_ID(N'dbo.ecount_delivery_slips', N'U') IS NOT NULL DROP TABLE dbo.ecount_delivery_slips;
IF OBJECT_ID(N'dbo.ecount_serial_issue_history', N'U') IS NOT NULL DROP TABLE dbo.ecount_serial_issue_history;
IF OBJECT_ID(N'dbo.ecount_erp_slips', N'U') IS NOT NULL DROP TABLE dbo.ecount_erp_slips;
IF OBJECT_ID(N'dbo.proc_outsourcing_inbounds', N'U') IS NOT NULL DROP TABLE dbo.proc_outsourcing_inbounds;
IF OBJECT_ID(N'dbo.proc_outsourcing_orders', N'U') IS NOT NULL DROP TABLE dbo.proc_outsourcing_orders;
IF OBJECT_ID(N'dbo.proc_5_finished_and_packing', N'U') IS NOT NULL DROP TABLE dbo.proc_5_finished_and_packing;
IF OBJECT_ID(N'dbo.proc_4_grinding_production', N'U') IS NOT NULL DROP TABLE dbo.proc_4_grinding_production;
IF OBJECT_ID(N'dbo.proc_3_grinding_wait_stock', N'U') IS NOT NULL DROP TABLE dbo.proc_3_grinding_wait_stock;
IF OBJECT_ID(N'dbo.proc_2_heat_treatment', N'U') IS NOT NULL DROP TABLE dbo.proc_2_heat_treatment;
IF OBJECT_ID(N'dbo.proc_1_raw_inbounds', N'U') IS NOT NULL DROP TABLE dbo.proc_1_raw_inbounds;

-- Layer 2 핵심 허브
IF OBJECT_ID(N'dbo.prod_coil_runs', N'U') IS NOT NULL DROP TABLE dbo.prod_coil_runs;

-- Layer 1 기준정보
IF OBJECT_ID(N'dbo.proc_outsourcing_partners', N'U') IS NOT NULL DROP TABLE dbo.proc_outsourcing_partners;
IF OBJECT_ID(N'dbo.ecount_address_book', N'U') IS NOT NULL DROP TABLE dbo.ecount_address_book;
IF OBJECT_ID(N'dbo.ecount_items', N'U') IS NOT NULL DROP TABLE dbo.ecount_items;
IF OBJECT_ID(N'dbo.ecount_colors', N'U') IS NOT NULL DROP TABLE dbo.ecount_colors;
IF OBJECT_ID(N'dbo.ecount_steel_grades', N'U') IS NOT NULL DROP TABLE dbo.ecount_steel_grades;
IF OBJECT_ID(N'dbo.ecount_mgmt_items', N'U') IS NOT NULL DROP TABLE dbo.ecount_mgmt_items;
IF OBJECT_ID(N'dbo.ecount_projects', N'U') IS NOT NULL DROP TABLE dbo.ecount_projects;
IF OBJECT_ID(N'dbo.ecount_warehouses', N'U') IS NOT NULL DROP TABLE dbo.ecount_warehouses;
GO

-- ============================================================================
-- [Layer 1] 기준정보 마스터 (8 Tables)
-- ============================================================================
CREATE TABLE dbo.ecount_warehouses (
    wh_code               NVARCHAR(60)   NOT NULL CONSTRAINT PK_ecount_warehouses PRIMARY KEY,
    ecount_code           NVARCHAR(40)   NOT NULL,
    wh_name               NVARCHAR(100)  NOT NULL,
    wh_type               NVARCHAR(40)   NOT NULL,
    process_stage         NVARCHAR(40)   NOT NULL,
    serial_prefix         NVARCHAR(20)   NULL CONSTRAINT DF_wh_pfx DEFAULT (N''),
    default_unit_price_kg DECIMAL(12,2)  NULL CONSTRAINT DF_wh_prc DEFAULT (0),
    description           NVARCHAR(300)  NULL
);
GO

CREATE TABLE dbo.ecount_projects (
    project_code        NVARCHAR(60)  NOT NULL CONSTRAINT PK_ecount_projects PRIMARY KEY,
    ecount_proj_code    NVARCHAR(20)  NOT NULL,
    project_name        NVARCHAR(100) NOT NULL,
    line_id             NVARCHAR(20)  NULL, -- L1,L2,L3,L5,L6,L7,L8,L9,PACK,OUT,WAGE
    cems_meter_no       INT           NULL,
    cems_meter_name     NVARCHAR(100) NULL,
    serial_start_digit  NVARCHAR(30)  NULL,
    default_out_wh      NVARCHAR(60)  NULL,
    default_out_wh_code NVARCHAR(20)  NULL,
    default_in_wh       NVARCHAR(60)  NULL,
    default_in_wh_code  NVARCHAR(20)  NULL
);
CREATE UNIQUE INDEX UX_proj_line_id ON dbo.ecount_projects (line_id) WHERE line_id IS NOT NULL;
GO

CREATE TABLE dbo.ecount_mgmt_items (
    mgmt_code      NVARCHAR(60)  NOT NULL CONSTRAINT PK_ecount_mgmt_items PRIMARY KEY,
    mgmt_name      NVARCHAR(100) NOT NULL,
    io_direction   NVARCHAR(30)  NOT NULL,
    target_process NVARCHAR(60)  NULL,
    description    NVARCHAR(300) NULL
);
GO

CREATE TABLE dbo.ecount_steel_grades (
    grade_name            NVARCHAR(60)  NOT NULL CONSTRAINT PK_ecount_steel_grades PRIMARY KEY,
    raw_code_prefix       NVARCHAR(20)  NOT NULL,
    raw_group_code        NVARCHAR(20)  NOT NULL,
    heat_group_code       NVARCHAR(20)  NOT NULL,
    grind_group_code      NVARCHAR(20)  NOT NULL,
    hardness_unit_default NVARCHAR(20)  NULL CONSTRAINT DF_grade_hu DEFAULT (N'HRC'),
    description           NVARCHAR(300) NULL
);
GO

CREATE TABLE dbo.ecount_colors (
    color_code    NVARCHAR(20)  NOT NULL CONSTRAINT PK_ecount_colors PRIMARY KEY,
    color_name    NVARCHAR(60)  NOT NULL,
    process_stage NVARCHAR(30)  NOT NULL,
    description   NVARCHAR(300) NULL
);
GO

CREATE TABLE dbo.ecount_items (
    item_code        NVARCHAR(60)  NOT NULL CONSTRAINT PK_ecount_items PRIMARY KEY,
    legacy_item_code NVARCHAR(60)  NULL,
    item_name        NVARCHAR(80)  NOT NULL,
    item_type        NVARCHAR(10)  NOT NULL CONSTRAINT DF_items_type DEFAULT (N'0'), -- 문자열 0 보존
    group_code       NVARCHAR(30)  NULL,
    thickness        DECIMAL(12,3) NOT NULL,
    width            DECIMAL(12,3) NOT NULL,
    cut_length       DECIMAL(12,3) NULL CONSTRAINT DF_items_cut DEFAULT (0),
    color_code       NVARCHAR(20)  NULL,
    color_name       NVARCHAR(60)  NULL,
    hardness_code    NVARCHAR(20)  NULL,
    hardness_display NVARCHAR(40)  NULL,
    spec_full        NVARCHAR(200) NOT NULL,
    unit             NVARCHAR(20)  NULL CONSTRAINT DF_items_unit DEFAULT (N'KG'),
    mgmt_flag        NVARCHAR(10)  NULL CONSTRAINT DF_items_mgmt DEFAULT (N'B'),
    lot_flag         NVARCHAR(10)  NULL CONSTRAINT DF_items_lot DEFAULT (N'B'),
    created_at       DATETIME2(0)  NOT NULL CONSTRAINT DF_items_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_items_lookup ON dbo.ecount_items (item_name, thickness, width, color_name, hardness_display)
    INCLUDE (item_code, spec_full, group_code);
GO

CREATE TABLE dbo.ecount_address_book (
    addr_id        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ecount_address_book PRIMARY KEY,
    saved_date     DATE              NOT NULL,
    partner_name   NVARCHAR(120)     NOT NULL,
    receiver_name  NVARCHAR(120)     NOT NULL,
    phone_no       NVARCHAR(60)      NULL,
    zip_code       NVARCHAR(20)      NULL CONSTRAINT DF_addr_zip DEFAULT (N''),
    road_address   NVARCHAR(300)     NULL,
    detail_address NVARCHAR(300)     NULL CONSTRAINT DF_addr_det DEFAULT (N''),
    wh_filter      NVARCHAR(60)      NULL CONSTRAINT DF_addr_wh DEFAULT (N'01.완제품'),
    CONSTRAINT UX_addr_book UNIQUE (partner_name, receiver_name, zip_code, detail_address)
);
GO

CREATE TABLE dbo.proc_outsourcing_partners (
    partner_code       NVARCHAR(20)   NOT NULL CONSTRAINT PK_proc_outsourcing_partners PRIMARY KEY,
    wh_code            NVARCHAR(20)   NOT NULL,
    wh_name            NVARCHAR(100)  NOT NULL,
    serial_prefix      NVARCHAR(10)   NOT NULL,
    process_types      NVARCHAR(120)  NOT NULL,
    slitting_price_kg  DECIMAL(12,2)  NULL CONSTRAINT DF_osp_slit DEFAULT (65.00),
    shearing_price_kg  DECIMAL(12,2)  NULL CONSTRAINT DF_osp_shear DEFAULT (80.00),
    edgemill_price_kg  DECIMAL(12,2)  NULL CONSTRAINT DF_osp_edge DEFAULT (120.00),
    loss_item_code     NVARCHAR(20)   NOT NULL CONSTRAINT DF_osp_loss DEFAULT (N'0099'), -- 선행 0 보존
    loss_item_name     NVARCHAR(60)   NOT NULL CONSTRAINT DF_osp_loss_nm DEFAULT (N'단가조정'),
    manager_name       NVARCHAR(60)   NULL,
    phone              NVARCHAR(40)   NULL,
    portal_access_code NVARCHAR(60)   NULL, -- 레거시 표시/초기시드; 실제 인증은 hash 우선
    portal_access_hash NVARCHAR(256)  NULL, -- PBKDF2-HMAC-SHA256
    is_active          BIT            NOT NULL CONSTRAINT DF_osp_act DEFAULT (1),
    remarks            NVARCHAR(500)  NULL
);
GO

-- ============================================================================
-- [Layer 2] 통합 생산 타임라인 · 5분 PLC 로그 · 작업 이벤트 (3 Tables)
-- ============================================================================
CREATE TABLE dbo.prod_coil_runs (
    run_id               BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_prod_coil_runs PRIMARY KEY,
    process_group        NVARCHAR(10)   NOT NULL,  -- 'HEAT' | 'COOL' | 'GRIND' | 'PACK'
    line_id              NVARCHAR(10)   NOT NULL,  -- 'L1'..'L9', 'PACK'
    business_date        DATE           NOT NULL,  -- 완결 귀속 영업일 [D-1 16:00, D 16:00)
    lot_no               NVARCHAR(60)   NOT NULL,
    mother_lot_no        NVARCHAR(80)   NULL,
    consumed_heat_lot_no NVARCHAR(60)   NULL,      -- 연마 투입 열처리 LOT (계보 연결키)
    seq_no               INT            NOT NULL CONSTRAINT DF_runs_seq DEFAULT (1),

    carryover_flag       NVARCHAR(30)   NOT NULL CONSTRAINT DF_runs_carry DEFAULT (N'NONE'), -- NONE | FROM_PREV_MID | PENDING_CARRYOVER | IDLE_GAP_CARRYOVER
    linked_prev_run_id   BIGINT         NULL,
    batch_group_id       NVARCHAR(60)   NULL,      -- 예: '2026-11-06_L7_B01' (*S 동시가닥 공유)
    run_status           NVARCHAR(20)   NOT NULL CONSTRAINT DF_runs_status DEFAULT (N'COMPLETED'), -- RUNNING | COMPLETED | PENDING_WIP

    steel_grade          NVARCHAR(40)   NOT NULL,
    color_name           NVARCHAR(40)   NULL,
    target_t             DECIMAL(10,3)  NULL,
    target_w             DECIMAL(10,2)  NULL,
    target_hardness      NVARCHAR(30)   NULL,
    in_t                 DECIMAL(10,3)  NULL,
    in_w                 DECIMAL(10,2)  NULL,
    in_kg                DECIMAL(12,2)  NULL,
    prod_kg              DECIMAL(12,2)  NULL,
    out_t                DECIMAL(10,3)  NULL,
    out_w                DECIMAL(10,2)  NULL,
    out_h                NVARCHAR(30)   NULL,
    scrap_kg             DECIMAL(12,2)  NULL CONSTRAINT DF_runs_scrap DEFAULT (0),
    strands_used         INT            NULL CONSTRAINT DF_runs_strands DEFAULT (1),
    strands_source       NVARCHAR(20)   NULL,      -- HINT_PARSE | SPEED_SOLVER | MANUAL

    start_at             DATETIME2(0)   NULL,
    end_at               DATETIME2(0)   NULL,
    duration_min         DECIMAL(10,2)  NULL,
    time_source          NVARCHAR(30)   NOT NULL,  -- DIRECT_MANUAL | INFERRED_PLC_CHANGEPOINT | ERP_LEDGER_ONLY
    confidence_grade     CHAR(1)        NULL,      -- 'A' | 'B' | NULL

    source_type          NVARCHAR(30)   NOT NULL,  -- EXCEL_MAIN | EXCEL_HOME_JM | DZICUBE_LDISJOIN | DASHBOARD_LIVE
    source_file          NVARCHAR(260)  NULL,
    source_row_no        INT            NULL,
    erp_disjoin_nb       NVARCHAR(40)   NULL,
    erp_disjoin_sq       INT            NULL,
    excel_speed          DECIMAL(10,2)  NULL,
    plc_avg_speed        DECIMAL(10,2)  NULL,
    plc_avg_heat         DECIMAL(10,2)  NULL,
    spec_override_flag   BIT            NOT NULL CONSTRAINT DF_runs_ovr DEFAULT (0),
    cems_power_kwh       DECIMAL(12,2)  NULL,
    worker_emp_no        NVARCHAR(20)   NULL,
    worker_name          NVARCHAR(60)   NULL,
    created_by_emp_no    NVARCHAR(20)   NULL,
    updated_by_emp_no    NVARCHAR(20)   NULL,
    pass_fail            NVARCHAR(20)   NULL,
    remarks              NVARCHAR(500)  NULL,
    etl_batch_id         BIGINT         NULL,
    created_at           DATETIME2(0)   NOT NULL CONSTRAINT DF_runs_created DEFAULT (SYSDATETIME()),
    updated_at           DATETIME2(0)   NOT NULL CONSTRAINT DF_runs_updated DEFAULT (SYSDATETIME()),

    CONSTRAINT FK_runs_prev FOREIGN KEY (linked_prev_run_id) REFERENCES dbo.prod_coil_runs(run_id),
    CONSTRAINT CK_runs_time_order CHECK (start_at IS NULL OR end_at IS NULL OR start_at < end_at),
    CONSTRAINT CK_runs_process_grp CHECK (process_group IN (N'HEAT', N'COOL', N'GRIND', N'PACK')),
    CONSTRAINT CK_runs_conf CHECK (confidence_grade IS NULL OR confidence_grade IN ('A', 'B'))
);
CREATE INDEX IX_runs_line_window
    ON dbo.prod_coil_runs (line_id, start_at, end_at)
    INCLUDE (business_date, lot_no, steel_grade, target_t, target_w, target_hardness, time_source, confidence_grade)
    WHERE start_at IS NOT NULL AND end_at IS NOT NULL;
CREATE INDEX IX_runs_bizdate_line ON dbo.prod_coil_runs (business_date DESC, line_id, seq_no);
CREATE INDEX IX_runs_lot ON dbo.prod_coil_runs (lot_no, line_id);
CREATE INDEX IX_runs_consumed_lot ON dbo.prod_coil_runs (consumed_heat_lot_no) WHERE consumed_heat_lot_no IS NOT NULL;
CREATE UNIQUE INDEX UX_runs_dzicube_doc
    ON dbo.prod_coil_runs (erp_disjoin_nb, erp_disjoin_sq)
    WHERE erp_disjoin_nb IS NOT NULL AND erp_disjoin_sq IS NOT NULL;
GO

CREATE TABLE dbo.plc_5min_logs (
    log_id                  BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_plc_5min_logs PRIMARY KEY,
    logged_at               DATETIME2(0)   NOT NULL,
    logged_epoch            FLOAT          NOT NULL,
    logged_business_date    DATE           NOT NULL,  -- 수집시각 기준 16:00 영업일
    trigger_type            NVARCHAR(30)   NOT NULL,  -- INTERVAL_5M | CSV_10S_RESAMPLED | CHANGEPOINT | EVENT_START | EVENT_END | EVENT_INPUT
    line_id                 NVARCHAR(10)   NOT NULL,
    work_status             NVARCHAR(30)   NULL,
    active_wo_id            NVARCHAR(80)   NULL,
    lot_no                  NVARCHAR(60)   NULL,
    spec_summary            NVARCHAR(200)  NULL,
    worker_emp_no           NVARCHAR(20)   NULL,
    worker_name             NVARCHAR(60)   NULL,

    raw_speed               INT            NOT NULL CONSTRAINT DF_plc_spd DEFAULT (0),
    is_active               BIT            NOT NULL CONSTRAINT DF_plc_active DEFAULT (0),
    is_smoothed             BIT            NOT NULL CONSTRAINT DF_plc_smooth DEFAULT (0),
    speed_step_id           INT            NULL,
    plc_raw_t               DECIMAL(10,3)  NULL,
    plc_raw_w               DECIMAL(10,2)  NULL,
    heat_avg                DECIMAL(8,2)   NULL,
    heat_min                DECIMAL(8,2)   NULL,
    heat_max                DECIMAL(8,2)   NULL,
    temp_avg                DECIMAL(8,2)   NULL,
    level_avg               DECIMAL(8,2)   NULL,
    lead_avg                DECIMAL(8,2)   NULL,
    temperatures_json       NVARCHAR(MAX)  NULL,
    svs_json                NVARCHAR(MAX)  NULL,
    zones_json              NVARCHAR(MAX)  NULL,

    confirmed_run_id        BIGINT         NULL,
    confirmed_business_date DATE           NULL,
    confirmed_lot_no        NVARCHAR(60)   NULL,
    confirmed_spec_full     NVARCHAR(200)  NULL,
    spec_source             NVARCHAR(20)   NOT NULL CONSTRAINT DF_plc_spec_src DEFAULT (N'UNMAPPED'),
    rebound_at              DATETIME2(0)   NULL,

    CONSTRAINT FK_plc_confirmed_run FOREIGN KEY (confirmed_run_id) REFERENCES dbo.prod_coil_runs(run_id),
    CONSTRAINT UX_plc_line_time_trig UNIQUE (line_id, logged_at, trigger_type)
);
CREATE INDEX IX_plc_line_logged_at ON dbo.plc_5min_logs (line_id, logged_at DESC)
    INCLUDE (raw_speed, heat_avg, heat_min, heat_max, temp_avg, level_avg, lead_avg, work_status, lot_no, trigger_type);
CREATE INDEX IX_plc_confirmed_run ON dbo.plc_5min_logs (confirmed_run_id) WHERE confirmed_run_id IS NOT NULL;
CREATE INDEX IX_plc_bizdate_line ON dbo.plc_5min_logs (logged_business_date DESC, line_id);
CREATE INDEX IX_plc_epoch_line ON dbo.plc_5min_logs (line_id, logged_epoch DESC);
GO

CREATE TABLE dbo.work_event_logs (
    event_id          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_work_event_logs PRIMARY KEY,
    event_at          DATETIME2(0)   NOT NULL,
    event_epoch       FLOAT          NOT NULL,
    business_date     DATE           NOT NULL,
    line_id           NVARCHAR(20)   NOT NULL,
    run_id            BIGINT         NULL,
    event_type        NVARCHAR(40)   NOT NULL,
    source_endpoint   NVARCHAR(120)  NULL,
    lot_no            NVARCHAR(60)   NULL,
    worker_emp_no     NVARCHAR(20)   NULL,
    worker_name       NVARCHAR(60)   NULL,
    created_by_emp_no NVARCHAR(20)   NULL,
    work_status       NVARCHAR(30)   NULL,
    payload_json      NVARCHAR(MAX)  NULL,
    plc_snapshot_json NVARCHAR(MAX)  NULL,
    CONSTRAINT FK_event_run FOREIGN KEY (run_id) REFERENCES dbo.prod_coil_runs(run_id)
);
CREATE INDEX IX_event_line_at ON dbo.work_event_logs (line_id, event_at DESC);
CREATE INDEX IX_event_epoch ON dbo.work_event_logs (line_id, event_epoch DESC);
CREATE INDEX IX_event_run ON dbo.work_event_logs (run_id) WHERE run_id IS NOT NULL;
GO

-- ============================================================================
-- [Layer 3] 공정 · ERP 전표 · QC · ECOUNT DOM (15 Tables)
-- ============================================================================
CREATE TABLE dbo.proc_1_raw_inbounds (
    inbound_id        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_proc1 PRIMARY KEY,
    doc_date_no       NVARCHAR(60)   NOT NULL,
    inbound_type      NVARCHAR(30)   NOT NULL,
    project_name      NVARCHAR(60)   NULL CONSTRAINT DF_p1_proj DEFAULT (N'외주가공'),
    mgmt_item         NVARCHAR(60)   NULL CONSTRAINT DF_p1_mgmt DEFAULT (N'외주가공'),
    partner_or_out_wh NVARCHAR(100)  NULL,
    in_wh             NVARCHAR(60)   NULL CONSTRAINT DF_p1_wh DEFAULT (N'0.도스코'),
    item_code         NVARCHAR(60)   NULL,
    steel_grade       NVARCHAR(40)   NOT NULL,
    thickness         DECIMAL(12,3)  NOT NULL,
    width             DECIMAL(12,3)  NOT NULL,
    cut_length        DECIMAL(12,3)  NULL CONSTRAINT DF_p1_cut DEFAULT (0),
    color_name        NVARCHAR(40)   NULL CONSTRAINT DF_p1_col DEFAULT (N'원재료'),
    hardness_display  NVARCHAR(30)   NULL CONSTRAINT DF_p1_hard DEFAULT (N'R'),
    spec_full         NVARCHAR(200)  NOT NULL,
    lot_no            NVARCHAR(60)   NOT NULL,
    unit_weight_kg    DECIMAL(12,2)  NOT NULL,
    qty_ea            INT            NULL CONSTRAINT DF_p1_qty DEFAULT (1),
    total_weight_kg   DECIMAL(12,2)  NOT NULL,
    remain_weight_kg  DECIMAL(12,2)  NOT NULL,
    worker_emp_no     NVARCHAR(20)   NULL,
    worker_name       NVARCHAR(60)   NULL, -- 하드코딩 기본값 제거
    created_by_emp_no NVARCHAR(20)   NULL,
    remarks           NVARCHAR(MAX)  NULL,
    created_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_p1_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_p1_lot ON dbo.proc_1_raw_inbounds (lot_no);
GO

CREATE TABLE dbo.proc_2_heat_treatment (
    heat_id           INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_proc2 PRIMARY KEY,
    run_id            BIGINT         NULL,
    doc_date_no       NVARCHAR(60)   NOT NULL,
    work_date         DATE           NOT NULL,
    business_date     DATE           NULL,
    project_name      NVARCHAR(60)   NOT NULL,
    worker_emp_no     NVARCHAR(20)   NULL,
    worker_name       NVARCHAR(60)   NULL,
    created_by_emp_no NVARCHAR(20)   NULL,
    out_wh            NVARCHAR(60)   NULL CONSTRAINT DF_p2_out DEFAULT (N'0.도스코'),
    consume_mgmt      NVARCHAR(40)   NULL CONSTRAINT DF_p2_cmg DEFAULT (N'투입'),
    raw_item_code     NVARCHAR(60)   NULL,
    raw_steel_grade   NVARCHAR(40)   NOT NULL,
    raw_thickness     DECIMAL(12,3)  NOT NULL,
    raw_width         DECIMAL(12,3)  NOT NULL,
    raw_cut_length    DECIMAL(12,3)  NULL CONSTRAINT DF_p2_rcut DEFAULT (0),
    raw_spec_full     NVARCHAR(200)  NULL,
    raw_lot_no        NVARCHAR(60)   NULL,
    input_unit_kg     DECIMAL(12,2)  NULL CONSTRAINT DF_p2_iukg DEFAULT (0),
    input_qty_ea      INT            NULL CONSTRAINT DF_p2_iqty DEFAULT (1),
    input_total_kg    DECIMAL(12,2)  NOT NULL,
    wip_return_kg     DECIMAL(12,2)  NULL CONSTRAINT DF_p2_wip DEFAULT (0),
    wip_lot_no        NVARCHAR(60)   NULL,
    next_route        NVARCHAR(40)   NULL CONSTRAINT DF_p2_route DEFAULT (N'FINISHED'),
    in_wh             NVARCHAR(60)   NOT NULL,
    prod_mgmt         NVARCHAR(60)   NOT NULL,
    prod_item_code    NVARCHAR(60)   NULL,
    prod_steel_grade  NVARCHAR(40)   NOT NULL,
    prod_thickness    DECIMAL(12,3)  NOT NULL,
    prod_width        DECIMAL(12,3)  NOT NULL,
    prod_cut_length   DECIMAL(12,3)  NULL CONSTRAINT DF_p2_pcut DEFAULT (0),
    prod_color        NVARCHAR(40)   NOT NULL,
    prod_hardness     NVARCHAR(30)   NOT NULL,
    prod_spec_full    NVARCHAR(200)  NOT NULL,
    prod_lot_no       NVARCHAR(60)   NOT NULL,
    unit_weight_kg    DECIMAL(12,2)  NOT NULL,
    qty_ea            INT            NULL CONSTRAINT DF_p2_pqty DEFAULT (1),
    total_weight_kg   DECIMAL(12,2)  NOT NULL,
    scrap_kg          DECIMAL(12,2)  NULL CONSTRAINT DF_p2_scr DEFAULT (0),
    power_kwh         DECIMAL(12,2)  NULL CONSTRAINT DF_p2_pwr DEFAULT (0),
    remarks           NVARCHAR(MAX)  NULL,
    created_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_p2_crt DEFAULT (SYSDATETIME()),
    CONSTRAINT FK_p2_run FOREIGN KEY (run_id) REFERENCES dbo.prod_coil_runs(run_id)
);
CREATE INDEX IX_p2_date_proj ON dbo.proc_2_heat_treatment (work_date DESC, project_name);
CREATE INDEX IX_p2_lot ON dbo.proc_2_heat_treatment (prod_lot_no);
GO

CREATE TABLE dbo.proc_3_grinding_wait_stock (
    wait_id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_proc3 PRIMARY KEY,
    wh_code          NVARCHAR(40)   NOT NULL,
    source_heat_id   INT            NULL,
    source_project   NVARCHAR(60)   NOT NULL,
    prod_date        DATE           NOT NULL,
    heat_lot_no      NVARCHAR(80)   NOT NULL,
    item_code        NVARCHAR(60)   NULL,
    steel_grade      NVARCHAR(40)   NOT NULL,
    thickness        DECIMAL(12,3)  NOT NULL,
    width            DECIMAL(12,3)  NOT NULL,
    cut_length       DECIMAL(12,3)  NULL CONSTRAINT DF_p3_cut DEFAULT (0),
    color_name       NVARCHAR(40)   NOT NULL,
    hardness_display NVARCHAR(30)   NOT NULL,
    spec_full        NVARCHAR(200)  NOT NULL,
    unit_weight_kg   DECIMAL(12,2)  NOT NULL,
    init_qty_ea      INT            NULL CONSTRAINT DF_p3_iq DEFAULT (1),
    remain_qty_ea    INT            NULL CONSTRAINT DF_p3_rq DEFAULT (1),
    init_weight_kg   DECIMAL(12,2)  NOT NULL,
    used_weight_kg   DECIMAL(12,2)  NULL CONSTRAINT DF_p3_uw DEFAULT (0),
    remain_weight_kg DECIMAL(12,2)  NOT NULL,
    status           NVARCHAR(20)   NULL CONSTRAINT DF_p3_st DEFAULT (N'WAITING'),
    remarks          NVARCHAR(MAX)  NULL,
    created_at       DATETIME2(0)   NOT NULL CONSTRAINT DF_p3_crt DEFAULT (SYSDATETIME()),
    CONSTRAINT UX_proc3_heat_lot_no UNIQUE (heat_lot_no)
);
CREATE INDEX IX_p3_status_wh ON dbo.proc_3_grinding_wait_stock (wh_code, status);
GO

CREATE TABLE dbo.proc_4_grinding_production (
    grind_id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_proc4 PRIMARY KEY,
    run_id              BIGINT         NULL,
    doc_date_no         NVARCHAR(60)   NOT NULL,
    work_date           DATE           NOT NULL,
    business_date       DATE           NULL,
    project_name        NVARCHAR(60)   NOT NULL,
    worker_emp_no       NVARCHAR(20)   NULL,
    worker_name         NVARCHAR(60)   NULL,
    created_by_emp_no   NVARCHAR(20)   NULL,
    source_wait_id      INT            NULL,
    out_wh              NVARCHAR(60)   NULL CONSTRAINT DF_p4_out DEFAULT (N'01.연마'),
    consume_mgmt        NVARCHAR(40)   NULL CONSTRAINT DF_p4_cmg DEFAULT (N'투입'),
    consume_item_code   NVARCHAR(60)   NULL,
    consume_steel_grade NVARCHAR(40)   NOT NULL,
    consume_spec_full   NVARCHAR(200)  NOT NULL,
    consume_heat_lot_no NVARCHAR(80)   NOT NULL,
    consume_unit_kg     DECIMAL(12,2)  NOT NULL,
    consume_qty_ea      INT            NULL CONSTRAINT DF_p4_cqty DEFAULT (1),
    consume_total_kg    DECIMAL(12,2)  NOT NULL,
    in_wh               NVARCHAR(60)   NULL CONSTRAINT DF_p4_in DEFAULT (N'01.완제품'),
    prod_mgmt           NVARCHAR(60)   NOT NULL,
    prod_item_code      NVARCHAR(60)   NULL,
    prod_steel_grade    NVARCHAR(40)   NOT NULL,
    prod_thickness      DECIMAL(12,3)  NOT NULL,
    prod_width          DECIMAL(12,3)  NOT NULL,
    prod_cut_length     DECIMAL(12,3)  NULL CONSTRAINT DF_p4_pcut DEFAULT (0),
    prod_color          NVARCHAR(40)   NOT NULL,
    prod_hardness       NVARCHAR(30)   NOT NULL,
    prod_spec_full      NVARCHAR(200)  NOT NULL,
    prod_lot_no         NVARCHAR(80)   NOT NULL,
    unit_weight_kg      DECIMAL(12,2)  NOT NULL,
    qty_ea              INT            NULL CONSTRAINT DF_p4_pqty DEFAULT (1),
    total_weight_kg     DECIMAL(12,2)  NOT NULL,
    scrap_kg            DECIMAL(12,2)  NULL CONSTRAINT DF_p4_scr DEFAULT (0),
    cems_power_kwh      DECIMAL(12,2)  NULL CONSTRAINT DF_p4_pwr DEFAULT (0),
    erp_disjoin_nb      NVARCHAR(40)   NULL,
    erp_disjoin_sq      INT            NULL,
    remarks             NVARCHAR(MAX)  NULL,
    created_at          DATETIME2(0)   NOT NULL CONSTRAINT DF_p4_crt DEFAULT (SYSDATETIME()),
    CONSTRAINT FK_p4_run FOREIGN KEY (run_id) REFERENCES dbo.prod_coil_runs(run_id)
);
CREATE INDEX IX_p4_date_proj ON dbo.proc_4_grinding_production (work_date DESC, project_name);
CREATE UNIQUE INDEX UX_p4_disjoin ON dbo.proc_4_grinding_production (erp_disjoin_nb, erp_disjoin_sq)
    WHERE erp_disjoin_nb IS NOT NULL AND erp_disjoin_sq IS NOT NULL;
GO

CREATE TABLE dbo.proc_5_finished_and_packing (
    pack_id           INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_proc5 PRIMARY KEY,
    doc_date_no       NVARCHAR(60)   NULL,
    business_date     DATE           NULL,
    process_stage     NVARCHAR(40)   NOT NULL,
    project_name      NVARCHAR(60)   NULL CONSTRAINT DF_p5_proj DEFAULT (N'포장반'),
    mgmt_item         NVARCHAR(60)   NULL CONSTRAINT DF_p5_mgmt DEFAULT (N'포장반'),
    out_wh            NVARCHAR(60)   NULL CONSTRAINT DF_p5_out DEFAULT (N'01.완제품'),
    in_wh             NVARCHAR(60)   NULL CONSTRAINT DF_p5_in DEFAULT (N'02.포장반'),
    source_type       NVARCHAR(30)   NOT NULL,
    source_lot_no     NVARCHAR(80)   NOT NULL,
    pack_lot_no       NVARCHAR(80)   NULL,
    item_code         NVARCHAR(60)   NULL,
    steel_grade       NVARCHAR(40)   NOT NULL,
    thickness         DECIMAL(12,3)  NOT NULL,
    width             DECIMAL(12,3)  NOT NULL,
    cut_length        DECIMAL(12,3)  NULL CONSTRAINT DF_p5_cut DEFAULT (0),
    color_name        NVARCHAR(40)   NOT NULL,
    hardness_display  NVARCHAR(30)   NOT NULL,
    spec_full         NVARCHAR(200)  NOT NULL,
    unit_weight_kg    DECIMAL(12,2)  NOT NULL,
    qty_ea            INT            NULL CONSTRAINT DF_p5_qty DEFAULT (1),
    total_weight_kg   DECIMAL(12,2)  NOT NULL,
    remain_weight_kg  DECIMAL(12,2)  NOT NULL,
    customer_or_dest  NVARCHAR(120)  NULL,
    packing_spec      NVARCHAR(300)  NULL,
    worker_emp_no     NVARCHAR(20)   NULL,
    worker_name       NVARCHAR(60)   NULL,
    created_by_emp_no NVARCHAR(20)   NULL,
    remarks           NVARCHAR(MAX)  NULL,
    created_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_p5_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_p5_stage_wh ON dbo.proc_5_finished_and_packing (process_stage, in_wh);
GO

CREATE TABLE dbo.proc_outsourcing_orders (
    order_id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_os_orders PRIMARY KEY,
    order_no          NVARCHAR(60)   NOT NULL,
    order_date        DATE           NOT NULL,
    partner_code      NVARCHAR(20)   NOT NULL,
    partner_wh_name   NVARCHAR(100)  NOT NULL,
    process_type      NVARCHAR(60)   NOT NULL,
    steel_grade       NVARCHAR(40)   NOT NULL,
    raw_thickness     DECIMAL(12,3)  NOT NULL,
    raw_width         DECIMAL(12,3)  NOT NULL,
    raw_spec_full     NVARCHAR(200)  NOT NULL,
    raw_item_code     NVARCHAR(60)   NOT NULL,
    raw_lot_no        NVARCHAR(80)   NOT NULL,
    raw_weight_kg     DECIMAL(12,2)  NOT NULL,
    remain_weight_kg  DECIMAL(12,2)  NOT NULL,
    target_slit_plan  NVARCHAR(300)  NOT NULL,
    unit_price_kg     DECIMAL(12,2)  NOT NULL,
    target_in_wh_code NVARCHAR(20)   NULL CONSTRAINT DF_oso_wh DEFAULT (N'01'), -- 문자열 '01' 보존
    target_in_wh_name NVARCHAR(60)   NULL CONSTRAINT DF_oso_whnm DEFAULT (N'0.도스코'),
    status            NVARCHAR(30)   NULL CONSTRAINT DF_oso_st DEFAULT (N'ORDERED'),
    created_by_emp_no NVARCHAR(20)   NULL,
    remarks           NVARCHAR(MAX)  NULL,
    created_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_oso_crt DEFAULT (SYSDATETIME())
);
GO

CREATE TABLE dbo.proc_outsourcing_inbounds (
    os_inbound_id      INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_os_inbounds PRIMARY KEY,
    doc_date_no        NVARCHAR(60)   NOT NULL,
    work_date          DATE           NOT NULL,
    project_code       NVARCHAR(20)   NULL CONSTRAINT DF_osi_proj DEFAULT (N'20'),
    project_name       NVARCHAR(60)   NULL CONSTRAINT DF_osi_pnm DEFAULT (N'외주가공'),
    mgmt_item          NVARCHAR(60)   NULL CONSTRAINT DF_osi_mgmt DEFAULT (N'외주가공'),
    partner_code       NVARCHAR(20)   NOT NULL,
    out_wh_code        NVARCHAR(20)   NOT NULL,
    out_wh_name        NVARCHAR(100)  NOT NULL,
    in_wh_code         NVARCHAR(20)   NOT NULL,
    in_wh_name         NVARCHAR(100)  NOT NULL,
    process_type       NVARCHAR(60)   NOT NULL,
    raw_item_code      NVARCHAR(60)   NOT NULL,
    raw_steel_grade    NVARCHAR(40)   NOT NULL,
    raw_thickness      DECIMAL(12,3)  NOT NULL,
    raw_width          DECIMAL(12,3)  NOT NULL,
    raw_spec_full      NVARCHAR(200)  NOT NULL,
    raw_lot_no         NVARCHAR(80)   NOT NULL,
    input_weight_kg    DECIMAL(12,2)  NOT NULL,
    slit_items_json    NVARCHAR(MAX)  NOT NULL,
    prod_summary_spec  NVARCHAR(300)  NOT NULL,
    prod_first_lot_no  NVARCHAR(80)   NOT NULL,
    prod_total_ea      INT            NOT NULL,
    prod_total_kg      DECIMAL(12,2)  NOT NULL,
    wip_return_kg      DECIMAL(12,2)  NULL CONSTRAINT DF_osi_wip DEFAULT (0),
    wip_lot_no         NVARCHAR(80)   NULL CONSTRAINT DF_osi_wl DEFAULT (N''),
    loss_item_code     NVARCHAR(20)   NULL CONSTRAINT DF_osi_lc DEFAULT (N'0099'),
    loss_item_name     NVARCHAR(60)   NULL CONSTRAINT DF_osi_ln DEFAULT (N'단가조정'),
    loss_weight_kg     DECIMAL(12,2)  NULL CONSTRAINT DF_osi_lw DEFAULT (0),
    unit_price_kg      DECIMAL(12,2)  NOT NULL,
    settlement_basis   NVARCHAR(30)   NULL CONSTRAINT DF_osi_sb DEFAULT (N'PROD_KG'),
    billable_weight_kg DECIMAL(12,2)  NOT NULL,
    supply_amt         BIGINT         NOT NULL,
    vat_amt            BIGINT         NOT NULL,
    total_amt          BIGINT         NOT NULL,
    settle_status      NVARCHAR(30)   NULL CONSTRAINT DF_osi_st DEFAULT (N'CONFIRMED'),
    submitted_by       NVARCHAR(80)   NULL,
    remarks            NVARCHAR(MAX)  NULL,
    created_at         DATETIME2(0)   NOT NULL CONSTRAINT DF_osi_crt DEFAULT (SYSDATETIME())
);
GO

CREATE TABLE dbo.ecount_erp_slips (
    slip_id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ecount_erp_slips PRIMARY KEY,
    doc_date_no        NVARCHAR(60)   NOT NULL,
    writer_emp_no      NVARCHAR(20)   NULL,
    writer_name        NVARCHAR(60)   NULL, -- 하드코딩 '송구현' 제거, 로그인 작성자 기록
    project_name       NVARCHAR(60)   NOT NULL,
    mgmt_item          NVARCHAR(60)   NOT NULL,
    manager_emp_no     NVARCHAR(20)   NULL,
    manager_name       NVARCHAR(60)   NULL,
    consume_item_name  NVARCHAR(60)   NULL,
    consume_spec       NVARCHAR(200)  NULL,
    consume_serial_lot NVARCHAR(80)   NULL,
    consume_item_code  NVARCHAR(60)   NULL,
    prod_item_code     NVARCHAR(60)   NULL,
    prod_item_name     NVARCHAR(60)   NULL,
    prod_spec          NVARCHAR(200)  NULL,
    color_name         NVARCHAR(40)   NULL,
    prod_serial_lot    NVARCHAR(80)   NULL,
    unit_weight_kg     DECIMAL(12,2)  NULL,
    qty_ea             INT            NULL,
    input_kg           DECIMAL(12,2)  NULL,
    prod_kg            DECIMAL(12,2)  NULL,
    consume_kg         DECIMAL(12,2)  NULL,
    out_wh_name        NVARCHAR(80)   NULL,
    in_wh_name         NVARCHAR(80)   NULL,
    scrap_kg           DECIMAL(12,2)  NULL CONSTRAINT DF_slips_scr DEFAULT (0),
    remarks            NVARCHAR(MAX)  NULL,
    created_at         DATETIME2(0)   NOT NULL CONSTRAINT DF_slips_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_slips_doc ON dbo.ecount_erp_slips (doc_date_no, project_name);
GO

CREATE TABLE dbo.ecount_serial_issue_history (
    history_type     NVARCHAR(60) NOT NULL,
    record_key       NVARCHAR(80) NOT NULL,
    last_suffix      INT          NOT NULL,
    last_serial_full NVARCHAR(80) NULL,
    updated_at       BIGINT       NOT NULL,
    CONSTRAINT PK_serial_hist PRIMARY KEY (history_type, record_key)
);
GO

CREATE TABLE dbo.ecount_delivery_slips (
    delivery_id       INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_delivery PRIMARY KEY,
    slip_date         DATE           NOT NULL,
    slip_serial_no    NVARCHAR(40)   NOT NULL,
    recipient_name    NVARCHAR(120)  NOT NULL,
    out_wh_name       NVARCHAR(80)   NULL CONSTRAINT DF_del_wh DEFAULT (N'01.완제품'),
    sales_gubun       NVARCHAR(40)   NULL CONSTRAINT DF_del_sg DEFAULT (N'제품'),
    steel_grade       NVARCHAR(40)   NOT NULL,
    spec_display      NVARCHAR(200)  NOT NULL,
    category_name     NVARCHAR(60)   NULL CONSTRAINT DF_del_cat DEFAULT (N''),
    lot_no            NVARCHAR(80)   NULL,
    unit_weight_kg    DECIMAL(12,2)  NOT NULL,
    qty_ea            INT            NOT NULL CONSTRAINT DF_del_qty DEFAULT (1),
    total_weight_kg   DECIMAL(12,2)  NOT NULL,
    unit_price        DECIMAL(14,2)  NULL CONSTRAINT DF_del_up DEFAULT (0),
    supply_amt        DECIMAL(16,2)  NULL CONSTRAINT DF_del_sup DEFAULT (0),
    vat_amt           DECIMAL(16,2)  NULL CONSTRAINT DF_del_vat DEFAULT (0),
    page_no           INT            NULL CONSTRAINT DF_del_pg DEFAULT (1),
    created_by_emp_no NVARCHAR(20)   NULL,
    created_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_del_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_del_date ON dbo.ecount_delivery_slips (slip_date DESC, recipient_name);
GO

CREATE TABLE dbo.ecount_packing_lists (
    packing_id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_packing PRIMARY KEY,
    packing_date        DATE           NOT NULL,
    serial_num          NVARCHAR(40)   NOT NULL,
    recipient_name      NVARCHAR(120)  NOT NULL,
    out_wh_name         NVARCHAR(80)   NULL CONSTRAINT DF_pk_wh DEFAULT (N'01.완제품'),
    layout_id           NVARCHAR(40)   NULL CONSTRAINT DF_pk_lay DEFAULT (N'_fixed_4dan'),
    spec_clean          NVARCHAR(200)  NOT NULL,
    steel_grade         NVARCHAR(40)   NOT NULL,
    category_name       NVARCHAR(60)   NULL CONSTRAINT DF_pk_cat DEFAULT (N''),
    coil_count_ea       INT            NOT NULL,
    coil_weights_json   NVARCHAR(MAX)  NOT NULL,
    subtotal_weight_kg  DECIMAL(12,2)  NOT NULL,
    doc_total_qty_ea    INT            NOT NULL,
    doc_total_weight_kg DECIMAL(12,2)  NOT NULL,
    created_by_emp_no   NVARCHAR(20)   NULL,
    remarks             NVARCHAR(MAX)  NULL CONSTRAINT DF_pk_rem DEFAULT (N''),
    created_at          DATETIME2(0)   NOT NULL CONSTRAINT DF_pk_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_pack_date ON dbo.ecount_packing_lists (packing_date DESC);
GO

CREATE TABLE dbo.ecount_daily_report_summary (
    report_date           DATE          NOT NULL CONSTRAINT PK_daily_sum PRIMARY KEY,
    sheet_name            NVARCHAR(40)  NOT NULL,
    day_prod_heat_cool_kg DECIMAL(14,2) NULL CONSTRAINT DF_drs_1 DEFAULT (0),
    mon_prod_heat_cool_kg DECIMAL(14,2) NULL CONSTRAINT DF_drs_2 DEFAULT (0),
    day_prod_grind_kg     DECIMAL(14,2) NULL CONSTRAINT DF_drs_3 DEFAULT (0),
    mon_prod_grind_kg     DECIMAL(14,2) NULL CONSTRAINT DF_drs_4 DEFAULT (0),
    day_in_raw_net_kg     DECIMAL(14,2) NULL CONSTRAINT DF_drs_5 DEFAULT (0),
    mon_in_raw_net_kg     DECIMAL(14,2) NULL CONSTRAINT DF_drs_6 DEFAULT (0),
    day_in_wage_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_7 DEFAULT (0),
    mon_in_wage_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_8 DEFAULT (0),
    day_out_fin_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_9 DEFAULT (0),
    mon_out_fin_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_10 DEFAULT (0),
    day_out_raw_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_11 DEFAULT (0),
    mon_out_raw_net_kg    DECIMAL(14,2) NULL CONSTRAINT DF_drs_12 DEFAULT (0),
    approval_status       NVARCHAR(40)  NULL CONSTRAINT DF_drs_app DEFAULT (N'작성완료'),
    updated_at            DATETIME2(0)  NOT NULL CONSTRAINT DF_drs_upd DEFAULT (SYSDATETIME())
);
GO

CREATE TABLE dbo.ecount_daily_report_details (
    detail_id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_daily_det PRIMARY KEY,
    report_date        DATE           NOT NULL,
    section_type       NVARCHAR(20)   NOT NULL,
    seq_no             INT            NOT NULL,
    orig_gubun         NVARCHAR(40)   NOT NULL,
    material_grade     NVARCHAR(40)   NOT NULL,
    spec_normalized    NVARCHAR(80)   NOT NULL,
    division_or_color  NVARCHAR(40)   NULL,
    heat_qty_kg        DECIMAL(12,2)  NULL CONSTRAINT DF_drd_1 DEFAULT (0),
    cool_qty_kg        DECIMAL(12,2)  NULL CONSTRAINT DF_drd_2 DEFAULT (0),
    grind_qty_kg       DECIMAL(12,2)  NULL CONSTRAINT DF_drd_3 DEFAULT (0),
    raw_qty_kg         DECIMAL(12,2)  NULL CONSTRAINT DF_drd_4 DEFAULT (0),
    wage_or_fin_qty_kg DECIMAL(12,2)  NULL CONSTRAINT DF_drd_5 DEFAULT (0),
    raw_ret_qty_kg     DECIMAL(12,2)  NULL CONSTRAINT DF_drd_6 DEFAULT (0),
    wage_or_fin_ret_kg DECIMAL(12,2)  NULL CONSTRAINT DF_drd_7 DEFAULT (0),
    partner_name       NVARCHAR(120)  NULL,
    remarks            NVARCHAR(MAX)  NULL,
    created_at         DATETIME2(0)   NOT NULL CONSTRAINT DF_drd_crt DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_drd_date_sec ON dbo.ecount_daily_report_details (report_date DESC, section_type, seq_no);
GO

CREATE TABLE dbo.qc_inspection_drafts (
    draft_id               BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_qc_drafts PRIMARY KEY,
    run_id                 BIGINT         NULL,
    updated_at             DATETIME2(0)   NOT NULL CONSTRAINT DF_qc_upd DEFAULT (SYSDATETIME()),
    work_date              DATE           NOT NULL,
    line_id                NVARCHAR(10)   NOT NULL,
    lot_no                 NVARCHAR(60)   NOT NULL,
    steel_grade            NVARCHAR(40)   NULL,
    target_spec            NVARCHAR(200)  NULL,
    thickness_meas         NVARCHAR(40)   NULL,
    width_meas             NVARCHAR(40)   NULL,
    hardness_meas          NVARCHAR(40)   NULL,
    appearance             NVARCHAR(40)   NOT NULL CONSTRAINT DF_qc_app DEFAULT (N'양호'),
    flatness               NVARCHAR(40)   NOT NULL CONSTRAINT DF_qc_flat DEFAULT (N'양호'),
    temp_summary_json      NVARCHAR(MAX)  NULL,
    speed_summary          NVARCHAR(120)  NULL,
    plc_5min_timeline_json NVARCHAR(MAX)  NULL,
    event_timeline_json    NVARCHAR(MAX)  NULL,
    judgment               NVARCHAR(20)   NOT NULL CONSTRAINT DF_qc_judg DEFAULT (N'합격'),
    inspector_emp_no       NVARCHAR(20)   NULL,
    inspector_name         NVARCHAR(60)   NULL,
    remarks                NVARCHAR(500)  NULL,
    ecount_status          NVARCHAR(20)   NOT NULL CONSTRAINT DF_qc_stat DEFAULT (N'DRAFT'),
    CONSTRAINT FK_qc_run FOREIGN KEY (run_id) REFERENCES dbo.prod_coil_runs(run_id),
    CONSTRAINT UX_qc_date_line_lot UNIQUE (work_date, line_id, lot_no)
);
CREATE INDEX IX_qc_date_line ON dbo.qc_inspection_drafts (work_date DESC, line_id);
GO

CREATE TABLE dbo.ecount_dom_schemas (
    prg_id      NVARCHAR(60)  NOT NULL CONSTRAINT PK_ecount_dom_schemas PRIMARY KEY,
    page_title  NVARCHAR(120) NULL,
    url_hash    NVARCHAR(200) NULL,
    captured_at DATETIME2(0)  NOT NULL CONSTRAINT DF_dom_cap DEFAULT (SYSDATETIME()),
    schema_json NVARCHAR(MAX) NOT NULL
);
GO

-- ============================================================================
-- [Layer 4] ETL 실행 감사 & 이상치 로그 (2 Tables)
-- ============================================================================
CREATE TABLE dbo.etl_batch_runs (
    batch_id       BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_batch_runs PRIMARY KEY,
    job_name       NVARCHAR(80)  NOT NULL,
    started_at     DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_st DEFAULT (SYSDATETIME()),
    finished_at    DATETIME2(0)  NULL,
    status         NVARCHAR(20)  NOT NULL,
    date_from      DATE          NULL,
    date_to        DATE          NULL,
    rows_processed INT           NOT NULL CONSTRAINT DF_etl_pr DEFAULT (0),
    rows_upserted  INT           NOT NULL CONSTRAINT DF_etl_up DEFAULT (0),
    anomaly_count  INT           NOT NULL CONSTRAINT DF_etl_an DEFAULT (0),
    summary_json   NVARCHAR(MAX) NULL
);
GO

CREATE TABLE dbo.etl_anomaly_logs (
    anomaly_id    BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_anomaly_logs PRIMARY KEY,
    batch_id      BIGINT        NOT NULL,
    severity      NVARCHAR(10)  NOT NULL,
    source_type   NVARCHAR(30)  NOT NULL,
    business_date DATE          NULL,
    line_id       NVARCHAR(10)  NULL,
    lot_no        NVARCHAR(60)  NULL,
    anomaly_code  NVARCHAR(60)  NOT NULL,
    detail_msg    NVARCHAR(MAX) NOT NULL,
    auto_fixed    BIT           NOT NULL CONSTRAINT DF_anom_fx DEFAULT (0),
    created_at    DATETIME2(0)  NOT NULL CONSTRAINT DF_anom_crt DEFAULT (SYSDATETIME()),
    CONSTRAINT FK_anom_batch FOREIGN KEY (batch_id) REFERENCES dbo.etl_batch_runs(batch_id)
);
GO

-- ============================================================================
-- [Layer 5] 사번 로그인 · 역할별 RBAC · 개인별 스코프 · 세션 · 토큰 · 감사 (5 Tables)
-- ============================================================================
CREATE TABLE dbo.sec_users (
    user_id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_sec_users PRIMARY KEY,
    emp_no              NVARCHAR(20)   NOT NULL CONSTRAINT UX_sec_users_emp UNIQUE, -- 사번 = 로그인 ID
    gw_login_id         NVARCHAR(50)   NULL,     -- 그룹웨어 ID (dosko.skh 등)
    password_hash       NVARCHAR(256)  NOT NULL, -- PBKDF2-HMAC-SHA256
    display_name        NVARCHAR(60)   NOT NULL,
    org_level3          NVARCHAR(60)   NULL,
    org_level4          NVARCHAR(60)   NULL,
    org_level5          NVARCHAR(60)   NULL,
    job_title           NVARCHAR(40)   NULL,     -- 직위 (실장, 팀장, 차장, 과장, 대리, 주임, 사원, 이사, 전무, 대표이사)
    job_role_type       NVARCHAR(40)   NULL,     -- 직무 (관리, 경영, 생산, 영업, 개발, 관리.품질)
    work_type           NVARCHAR(40)   NULL,     -- 근로형태 (A조, B조, 생산직, 일반직, 전산, 임원 등)
    employment_status   NVARCHAR(20)   NOT NULL CONSTRAINT DF_sec_empst DEFAULT (N'정상'), -- 정상 | 일시정지

    role_code           NVARCHAR(30)   NOT NULL, -- IT_ADMIN | EXEC_READ | BIZ_EXEC | SALES_MGR | PROD_GLOBAL | QC_PROD_MGR | PROD_OP | RESTRICTED | LOCKED
    is_pending_it_setup BIT            NOT NULL CONSTRAINT DF_sec_pend DEFAULT (0),
    can_login           BIT            NOT NULL CONSTRAINT DF_sec_clog DEFAULT (1),
    is_active           BIT            NOT NULL CONSTRAINT DF_sec_act  DEFAULT (1),

    allowed_tabs_json   NVARCHAR(1000) NULL,
    allowed_lines_json  NVARCHAR(300)  NULL,     -- '["L1","L5"]', '["PACK"]', '["ALL"]', '[]'
    allowed_wh_json     NVARCHAR(300)  NULL,
    module_perms_json   NVARCHAR(1000) NULL,     -- 전산실 세부 모듈별 없음/보기/쓰기 오버라이드

    can_view_price      BIT            NOT NULL CONSTRAINT DF_sec_prc  DEFAULT (0),
    can_edit_confirmed  BIT            NOT NULL CONSTRAINT DF_sec_conf DEFAULT (0),
    can_export_excel    BIT            NOT NULL CONSTRAINT DF_sec_exp  DEFAULT (0),
    can_use_ecount_rpa  BIT            NOT NULL CONSTRAINT DF_sec_rpa  DEFAULT (0),

    allowed_ip_cidr     NVARCHAR(200)  NULL,
    session_ttl_min     INT            NOT NULL CONSTRAINT DF_sec_ttl  DEFAULT (480),
    must_change_pw      BIT            NOT NULL CONSTRAINT DF_sec_mcp  DEFAULT (1),
    failed_attempts     INT            NOT NULL CONSTRAINT DF_sec_fail DEFAULT (0),
    locked_until        DATETIME2(0)   NULL,
    last_login_at       DATETIME2(0)   NULL,
    created_by_emp_no   NVARCHAR(20)   NULL,
    updated_by_emp_no   NVARCHAR(20)   NULL,
    created_at          DATETIME2(0)   NOT NULL CONSTRAINT DF_sec_crt  DEFAULT (SYSDATETIME()),
    updated_at          DATETIME2(0)   NOT NULL CONSTRAINT DF_sec_upd  DEFAULT (SYSDATETIME()),

    CONSTRAINT CK_sec_emp_status CHECK (employment_status IN (N'정상', N'일시정지')),
    CONSTRAINT CK_sec_role CHECK (role_code IN (N'IT_ADMIN', N'EXEC_READ', N'BIZ_EXEC', N'SALES_MGR', N'PROD_GLOBAL', N'QC_PROD_MGR', N'PROD_OP', N'RESTRICTED', N'LOCKED'))
);
CREATE INDEX IX_sec_users_role ON dbo.sec_users (role_code, is_active, can_login);
GO

CREATE TABLE dbo.sec_role_permissions (
    role_code    NVARCHAR(30) NOT NULL,
    resource_key NVARCHAR(80) NOT NULL,
    allow_read   BIT          NOT NULL CONSTRAINT DF_rp_r DEFAULT (0),
    allow_write  BIT          NOT NULL CONSTRAINT DF_rp_w DEFAULT (0),
    allow_delete BIT          NOT NULL CONSTRAINT DF_rp_d DEFAULT (0),
    CONSTRAINT PK_sec_role_perm PRIMARY KEY (role_code, resource_key)
);
GO

CREATE TABLE dbo.sec_sessions (
    session_token_hash CHAR(64)     NOT NULL CONSTRAINT PK_sec_sessions PRIMARY KEY,
    session_type       NVARCHAR(20) NOT NULL CONSTRAINT DF_sess_tp DEFAULT (N'USER'), -- USER | PARTNER
    user_id            INT          NULL,
    emp_no             NVARCHAR(20) NULL,
    partner_code       NVARCHAR(20) NULL,
    client_ip          NVARCHAR(45) NOT NULL,
    user_agent         NVARCHAR(200) NULL,
    csrf_token         NVARCHAR(64) NOT NULL,
    issued_at          DATETIME2(0) NOT NULL CONSTRAINT DF_sess_iss DEFAULT (SYSDATETIME()),
    last_activity_at   DATETIME2(0) NOT NULL CONSTRAINT DF_sess_act DEFAULT (SYSDATETIME()),
    expires_at         DATETIME2(0) NOT NULL,
    is_revoked         BIT          NOT NULL CONSTRAINT DF_sess_rev DEFAULT (0),
    CONSTRAINT FK_sess_user FOREIGN KEY (user_id) REFERENCES dbo.sec_users(user_id)
);
CREATE INDEX IX_sess_emp_active ON dbo.sec_sessions (emp_no, is_revoked, expires_at);
GO

CREATE TABLE dbo.sec_audit_logs (
    audit_id      BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_sec_audit PRIMARY KEY,
    event_at      DATETIME2(0)  NOT NULL CONSTRAINT DF_aud_at DEFAULT (SYSDATETIME()),
    user_id       INT           NULL,
    emp_no        NVARCHAR(20)  NULL,
    display_name  NVARCHAR(60)  NULL,
    role_code     NVARCHAR(30)  NULL,
    client_ip     NVARCHAR(45)  NULL,
    action_type   NVARCHAR(40)  NOT NULL, -- LOGIN_OK | LOGIN_FAIL | ACCOUNT_LOCKED | PW_CHANGED | FORBIDDEN_403 | DATA_WRITE | USER_MOD | TOKEN_MOD
    resource_path NVARCHAR(120) NULL,
    target_key    NVARCHAR(100) NULL,
    before_json   NVARCHAR(MAX) NULL,
    after_json    NVARCHAR(MAX) NULL,
    detail_json   NVARCHAR(MAX) NULL
);
CREATE INDEX IX_audit_at_emp ON dbo.sec_audit_logs (event_at DESC, emp_no);
CREATE INDEX IX_audit_action ON dbo.sec_audit_logs (action_type, event_at DESC);
GO

CREATE TABLE dbo.sec_api_tokens (
    token_id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_sec_tokens PRIMARY KEY,
    token_prefix        NVARCHAR(20)  NOT NULL,
    token_hash          CHAR(64)      NOT NULL CONSTRAINT UX_sec_token_hash UNIQUE,
    token_name          NVARCHAR(100) NOT NULL,
    scope_type          NVARCHAR(30)  NOT NULL, -- ECOUNT_RPA | KIOSK_MONITOR
    partner_code        NVARCHAR(20)  NULL,
    allowed_routes_json NVARCHAR(500) NULL,
    is_active           BIT           NOT NULL CONSTRAINT DF_tok_act DEFAULT (1),
    expires_at          DATETIME2(0)  NULL,
    last_used_at        DATETIME2(0)  NULL,
    created_by_emp_no   NVARCHAR(20)  NULL,
    created_at          DATETIME2(0)  NOT NULL CONSTRAINT DF_tok_crt DEFAULT (SYSDATETIME())
);
GO

-- ============================================================================
-- [Views] 통합 조회 뷰 4종
-- ============================================================================
CREATE OR ALTER VIEW dbo.v_plc_with_confirmed_spec AS
SELECT
    p.log_id, p.logged_at, p.logged_business_date,
    COALESCE(r.business_date, p.confirmed_business_date, p.logged_business_date) AS confirmed_business_date,
    p.line_id, p.trigger_type, p.raw_speed, p.heat_avg, p.heat_min, p.heat_max,
    p.temp_avg, p.level_avg, p.lead_avg,
    COALESCE(r.run_id, p.confirmed_run_id) AS confirmed_run_id,
    COALESCE(r.lot_no, p.confirmed_lot_no, p.lot_no) AS confirmed_lot_no,
    COALESCE(
        CASE WHEN r.run_id IS NOT NULL THEN CONCAT(r.steel_grade, N' ', CAST(r.target_t AS NVARCHAR(20)), N'*', CAST(r.target_w AS NVARCHAR(20))) END,
        p.confirmed_spec_full,
        p.spec_summary
    ) AS confirmed_spec_full,
    r.process_group, r.carryover_flag, r.time_source, r.confidence_grade,
    p.plc_raw_t, p.plc_raw_w,
    CASE WHEN r.run_id IS NOT NULL THEN 1 ELSE 0 END AS is_confirmed_bound
FROM dbo.plc_5min_logs p
LEFT JOIN dbo.prod_coil_runs r
  ON p.line_id = r.line_id
 AND r.process_group IN (N'HEAT', N'COOL')
 AND r.start_at IS NOT NULL AND r.end_at IS NOT NULL
 AND p.logged_at >= r.start_at AND p.logged_at < r.end_at;
GO

CREATE OR ALTER VIEW dbo.v_lot_genealogy AS
SELECT
    g.run_id AS grind_run_id, g.business_date AS grind_date, g.line_id AS grind_line_id,
    g.lot_no AS grind_lot_no, g.steel_grade, g.in_kg AS grind_in_kg, g.prod_kg AS grind_prod_kg,
    g.consumed_heat_lot_no,
    h.run_id AS heat_run_id, h.business_date AS heat_date, h.line_id AS heat_line_id,
    h.start_at AS heat_start_at, h.end_at AS heat_end_at,
    h.plc_avg_heat, h.plc_avg_speed, h.confidence_grade AS heat_time_confidence
FROM dbo.prod_coil_runs g
LEFT JOIN dbo.prod_coil_runs h
  ON g.consumed_heat_lot_no = h.lot_no
 AND h.process_group IN (N'HEAT', N'COOL')
WHERE g.process_group = N'GRIND';
GO

CREATE OR ALTER VIEW dbo.v_ecount_warehouse_stock_summary AS
SELECT N'0.도스코 (001)' AS wh_name, COUNT(*) AS lot_count, COALESCE(SUM(remain_weight_kg), 0) AS stock_kg
FROM dbo.proc_1_raw_inbounds WHERE remain_weight_kg > 0
UNION ALL
SELECT N'01.연마 (11)', COUNT(*), COALESCE(SUM(remain_weight_kg), 0)
FROM dbo.proc_3_grinding_wait_stock WHERE wh_code = N'01.연마' AND remain_weight_kg > 0
UNION ALL
SELECT N'01.소폭 (12)', COUNT(*), COALESCE(SUM(remain_weight_kg), 0)
FROM dbo.proc_3_grinding_wait_stock WHERE wh_code = N'01.소폭' AND remain_weight_kg > 0
UNION ALL
SELECT N'01.완제품 (01/22)', COUNT(*), COALESCE(SUM(remain_weight_kg), 0)
FROM dbo.proc_5_finished_and_packing WHERE in_wh = N'01.완제품' AND remain_weight_kg > 0
UNION ALL
SELECT N'02.포장반 (02)', COUNT(*), COALESCE(SUM(remain_weight_kg), 0)
FROM dbo.proc_5_finished_and_packing WHERE in_wh = N'02.포장반' AND remain_weight_kg > 0
UNION ALL
SELECT CONCAT(partner_wh_name, N' (', partner_code, N')'), COUNT(*), COALESCE(SUM(remain_weight_kg), 0)
FROM dbo.proc_outsourcing_orders WHERE remain_weight_kg > 0 GROUP BY partner_code, partner_wh_name;
GO

IF DB_ID(N'DZICUBE') IS NOT NULL
BEGIN
    EXEC(N'
    CREATE OR ALTER VIEW dbo.v_secure_douzone_trades AS
    SELECT
        t.CO_CD, t.TR_CD, t.TR_NM, t.ATTR_NM, t.TR_FG_NM,
        t.AREA_NM, t.TRADE_GRP_NM, t.TEL, t.FAX, t.DIV_ADDR1, t.ADDR2,
        CASE
            WHEN LEN(t.REG_NB) >= 10 THEN SUBSTRING(t.REG_NB, 1, 3) + ''-'' + SUBSTRING(t.REG_NB, 4, 2) + ''-*****''
            ELSE t.REG_NB
        END AS MASKED_REG_NB,
        t.CEO_NM, t.USE_YN
    FROM DZICUBE.dbo.ZL_DOSKO_VL_STRADE t
    WHERE t.USE_YN = 1;
    ');
END
GO
