"""
SQLite database layer for RTL·AI Verification System
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = "rtl_verification.db"

HISTORICAL_BUG_DATA = [
    {"module_type": "fifo", "bug_type": "Write-when-full overflow", "severity": "CRITICAL",
     "frequency": 0.72, "description": "Writing to FIFO when full flag is asserted, corrupting data",
     "prevention": "Check full flag assertion before wr_en"},
    {"module_type": "fifo", "bug_type": "Read-when-empty underflow", "severity": "CRITICAL",
     "frequency": 0.68, "description": "Reading from FIFO when empty returns garbage data",
     "prevention": "Check empty flag before rd_en assertion"},
    {"module_type": "fifo", "bug_type": "Pointer wrap-around off-by-one", "severity": "HIGH",
     "frequency": 0.61, "description": "rd_ptr or wr_ptr not wrapping at DEPTH boundary",
     "prevention": "Test DEPTH-1 and DEPTH writes, verify ptr == 0 after wrap"},
    {"module_type": "fifo", "bug_type": "Simultaneous read/write count race", "severity": "HIGH",
     "frequency": 0.55, "description": "count register wrong when rd_en and wr_en same cycle",
     "prevention": "Simultaneous rd+wr test: count should stay same"},
    {"module_type": "fifo", "bug_type": "Async reset glitch", "severity": "MEDIUM",
     "frequency": 0.43, "description": "Glitchy reset causing partial reset of internal state",
     "prevention": "Assert reset for minimum 2 clock cycles"},
    {"module_type": "fifo", "bug_type": "Full/empty flag metastability", "severity": "MEDIUM",
     "frequency": 0.38, "description": "full/empty flags toggling wrong at boundary conditions",
     "prevention": "Check flags at exactly DEPTH and 0 entries"},
    {"module_type": "fifo", "bug_type": "Data bypass missing when empty", "severity": "MEDIUM",
     "frequency": 0.31, "description": "Simultaneous wr+rd when empty: data not forwarded",
     "prevention": "Simultaneous wr+rd when empty test"},
    {"module_type": "counter", "bug_type": "Overflow wrap mismatch", "severity": "HIGH",
     "frequency": 0.58, "description": "Counter wraps to wrong value or doesn't wrap",
     "prevention": "Test MAX_VALUE+1 transition"},
    {"module_type": "arbiter", "bug_type": "Starvation of low-priority request", "severity": "HIGH",
     "frequency": 0.66, "description": "Low priority requestor never granted when high priority active",
     "prevention": "Fair arbitration stress test"},
    {"module_type": "arbiter", "bug_type": "Double-grant race condition", "severity": "CRITICAL",
     "frequency": 0.52, "description": "Two requestors granted simultaneously",
     "prevention": "Simultaneous multi-request test"},
    {"module_type": "fsm", "bug_type": "Illegal state reachable", "severity": "CRITICAL",
     "frequency": 0.47, "description": "FSM reaches undefined state on unexpected input",
     "prevention": "Default state transition test, X-state injection"},
    {"module_type": "fsm", "bug_type": "Reset doesn't reach IDLE", "severity": "HIGH",
     "frequency": 0.39, "description": "Reset doesn't return FSM to IDLE state",
     "prevention": "Reset from every state test"},
    {"module_type": "memory", "bug_type": "Read-during-write hazard", "severity": "HIGH",
     "frequency": 0.51, "description": "Reading same address being written returns stale data",
     "prevention": "Same-address read/write same cycle test"},
    {"module_type": "memory", "bug_type": "Address decode boundary error", "severity": "MEDIUM",
     "frequency": 0.44, "description": "Last address not accessible or maps incorrectly",
     "prevention": "Walking address pattern, corner address test"},
]


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id      TEXT PRIMARY KEY,
                    module_name TEXT,
                    rtl_code    TEXT,
                    status      TEXT,
                    created_at  TEXT,
                    stages_completed TEXT DEFAULT '[]',
                    score       INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS simulations (
                    sim_id    TEXT PRIMARY KEY,
                    job_id    TEXT,
                    engine    TEXT,
                    log       TEXT,
                    passed    INTEGER DEFAULT 0,
                    failed    INTEGER DEFAULT 0,
                    coverage  REAL    DEFAULT 0.0,
                    timestamp TEXT,
                    raw_json  TEXT
                );

                CREATE TABLE IF NOT EXISTS bugs (
                    bug_id       TEXT PRIMARY KEY,
                    job_id       TEXT,
                    type         TEXT,
                    severity     TEXT,
                    location     TEXT,
                    description  TEXT,
                    status       TEXT DEFAULT 'PREDICTED',
                    probability  REAL DEFAULT 0.5,
                    points       INTEGER DEFAULT 100,
                    source       TEXT,
                    created_at   TEXT,
                    confirmed_at TEXT,
                    notes        TEXT
                );

                CREATE TABLE IF NOT EXISTS coverage_reports (
                    id               TEXT PRIMARY KEY,
                    job_id           TEXT,
                    coverage_achieved REAL,
                    coverage_grade   TEXT,
                    holes            TEXT,
                    prioritized_next TEXT,
                    created_at       TEXT
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id                   TEXT PRIMARY KEY,
                    job_id               TEXT,
                    bug_type             TEXT,
                    probability          REAL,
                    severity             TEXT,
                    location             TEXT,
                    historical_frequency TEXT,
                    prevention_test      TEXT,
                    created_at           TEXT
                );

                CREATE TABLE IF NOT EXISTS historical_bugs (
                    id          TEXT PRIMARY KEY,
                    module_type TEXT,
                    bug_type    TEXT,
                    severity    TEXT,
                    frequency   REAL,
                    description TEXT,
                    prevention  TEXT
                );
            """)

    # ── Jobs ──────────────────────────────────────────────────────────────────
    def save_job(self, job_id: str, job: dict):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO jobs
                   (job_id, module_name, rtl_code, status, created_at, stages_completed, score)
                   VALUES (?,?,?,?,?,?,?)""",
                (job_id, job.get("module_name"), job.get("rtl_code"),
                 job.get("status"), job.get("created_at"),
                 json.dumps(job.get("stages_completed", [])), job.get("score", 0))
            )

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row:
                d = dict(row)
                d["stages_completed"] = json.loads(d["stages_completed"])
                return d
        return None

    def list_jobs(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["stages_completed"] = json.loads(d["stages_completed"])
                result.append(d)
            return result

    # ── Simulations ───────────────────────────────────────────────────────────
    def save_simulation(self, sim_id: str, data: dict):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO simulations
                   (sim_id, job_id, engine, log, passed, failed, coverage, timestamp, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (sim_id, data.get("job_id"), data.get("engine", "unknown"),
                 data.get("log", ""), data.get("passed", 0), data.get("failed", 0),
                 data.get("coverage", 0.0), data.get("timestamp"), json.dumps(data))
            )

    def get_simulation(self, sim_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM simulations WHERE sim_id=?", (sim_id,)).fetchone()
            if row:
                d = dict(row)
                try:
                    d.update(json.loads(d.get("raw_json", "{}")))
                except Exception:
                    pass
                return d
        return None

    # ── Bugs ──────────────────────────────────────────────────────────────────
    def save_bug(self, bug: dict) -> str:
        bug_id = bug.get("bug_id") or str(uuid.uuid4())[:8]
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO bugs
                   (bug_id, job_id, type, severity, location, description,
                    status, probability, points, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (bug_id, bug.get("job_id"), bug.get("type", "Unknown"),
                 bug.get("severity", "MEDIUM"), bug.get("location", "unknown"),
                 bug.get("description", ""), bug.get("status", "PREDICTED"),
                 bug.get("probability", 0.5),
                 self._sev_points(bug.get("severity", "MEDIUM")),
                 bug.get("source", "AI"), datetime.utcnow().isoformat())
            )
        return bug_id

    def get_bugs(self, job_id: str = None, severity: str = None) -> List[dict]:
        query = "SELECT * FROM bugs WHERE 1=1"
        params = []
        if job_id:
            query += " AND job_id=?"; params.append(job_id)
        if severity:
            query += " AND severity=?"; params.append(severity)
        query += " ORDER BY created_at DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def confirm_bug(self, bug_id: str, notes: str = "") -> Optional[dict]:
        with self._conn() as conn:
            conn.execute(
                "UPDATE bugs SET status='CONFIRMED', confirmed_at=?, notes=? WHERE bug_id=?",
                (datetime.utcnow().isoformat(), notes, bug_id)
            )
            row = conn.execute("SELECT * FROM bugs WHERE bug_id=?", (bug_id,)).fetchone()
            return dict(row) if row else None

    def save_prediction(self, job_id: str, prediction: dict):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO predictions
                   (id, job_id, bug_type, probability, severity, location,
                    historical_frequency, prevention_test, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4())[:8], job_id, prediction.get("bug_type"),
                 prediction.get("probability"), prediction.get("severity"),
                 prediction.get("location"), prediction.get("historical_frequency"),
                 prediction.get("prevention_test"), datetime.utcnow().isoformat())
            )

    # ── Coverage ──────────────────────────────────────────────────────────────
    def save_coverage(self, job_id: str, data: dict):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO coverage_reports
                   (id, job_id, coverage_achieved, coverage_grade, holes, prioritized_next, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (str(uuid.uuid4())[:8], job_id,
                 data.get("coverage_achieved"), data.get("coverage_grade"),
                 json.dumps(data.get("holes", [])),
                 json.dumps(data.get("prioritized_next", [])),
                 datetime.utcnow().isoformat())
            )

    # ── Historical ────────────────────────────────────────────────────────────
    def seed_historical_bugs(self):
        with self._conn() as conn:
            for bug in HISTORICAL_BUG_DATA:
                conn.execute(
                    """INSERT OR IGNORE INTO historical_bugs
                       (id, module_type, bug_type, severity, frequency, description, prevention)
                       VALUES (?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4())[:8], bug["module_type"], bug["bug_type"],
                     bug["severity"], bug["frequency"], bug["description"], bug["prevention"])
                )

    def get_historical_bugs(self, module_type: str = None, limit: int = 50) -> List[dict]:
        query = "SELECT * FROM historical_bugs"
        params = []
        if module_type:
            query += " WHERE module_type=?"; params.append(module_type)
        query += f" ORDER BY frequency DESC LIMIT {limit}"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    # ── Stats ─────────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        bugs = self.get_bugs()
        return {
            "total_jobs": len(self.list_jobs()),
            "total_bugs": len(bugs),
            "confirmed": sum(1 for b in bugs if b["status"] == "CONFIRMED"),
            "predicted": sum(1 for b in bugs if b["status"] == "PREDICTED"),
            "by_severity": {
                sev: sum(1 for b in bugs if b.get("severity") == sev)
                for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            }
        }

    def _sev_points(self, sev: str) -> int:
        return {"CRITICAL": 500, "HIGH": 300, "MEDIUM": 150, "LOW": 50}.get(sev, 100)


db = Database()
