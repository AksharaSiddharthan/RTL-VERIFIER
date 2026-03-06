"""
RTL·AI Verification System — FastAPI Backend
Run with:  python main.py
API docs:  http://localhost:8000/docs
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

if "ANTHROPIC_API_KEY" not in os.environ:
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-dummy-key-for-local-testing-only"

from ai_agents import AIAgentRunner
from database import db
from models import (
    AgentRunRequest, ChatStreamRequest, ConfirmBugRequest,
    PredictionRequest, SimulateRequest,
)
from simulator import RTLSimulator

# ── App setup ─────────────────────────────────────────────────────────────────


app = FastAPI(
    title="RTL·AI Verification System",
    description="Agentic RTL verification — Sandisk Hackathon",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # or ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


simulator  = RTLSimulator()
ai_runner  = AIAgentRunner()

UPLOAD_DIR = Path("uploads")
SIM_DIR    = Path("simulations")
UPLOAD_DIR.mkdir(exist_ok=True)
SIM_DIR.mkdir(exist_ok=True)


import shutil

has_iverilog = shutil.which("iverilog") is not None
# Seed DB on startup
@app.on_event("startup")
async def startup():
    db.seed_historical_bugs()
    print("RTL·AI Verification System started")
    has_iv = shutil.which("iverilog") is not None

    print(f"   iverilog: {'available' if has_iv else 'not found (AI fallback active)'}")


# ── File Upload ────────────────────────────────────────────────────────────────
@app.post("/api/upload-rtl")
async def upload_rtl(file: UploadFile = File(...)):
    if not file.filename.endswith((".v", ".sv", ".vh", ".svh")):
        raise HTTPException(400, "Only .v / .sv files accepted")
    file_id   = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    content   = await file.read()
    save_path.write_bytes(content)
    text      = content.decode("utf-8", errors="ignore")
    return {
        "file_id":    file_id,
        "filename":   file.filename,
        "path":       str(save_path),
        "size_bytes": len(content),
        "lines":      text.count("\n"),
        "content":    text,
        "uploaded_at": datetime.utcnow().isoformat(),
    }


# ── Jobs ───────────────────────────────────────────────────────────────────────
@app.post("/api/jobs/create")
async def create_job(rtl_code: str, module_name: str = "unknown"):
    job_id = str(uuid.uuid4())[:8]
    job = {
        "job_id":            job_id,
        "module_name":       module_name,
        "rtl_code":          rtl_code,
        "status":            "CREATED",
        "created_at":        datetime.utcnow().isoformat(),
        "stages_completed":  [],
        "score":             0,
    }
    db.save_job(job_id, job)
    return job

@app.get("/api/jobs")
async def list_jobs():
    return db.list_jobs()

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


# ── Generic Chat Proxy (keeps API key server-side) ─────────────────────────────
@app.post("/api/chat/stream")
async def chat_stream(body: ChatStreamRequest):
    """
    The frontend calls THIS endpoint.
    The backend holds the ANTHROPIC_API_KEY — never exposed to the browser.
    """
    async def generate():
        async for chunk in ai_runner._stream(body.system, body.prompt):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

# ── AI Agent: Verification Plan (streaming) ────────────────────────────────────
@app.post("/api/agents/plan/stream")
async def stream_plan(body: AgentRunRequest):
    async def generate():
        print("STREAM STARTED / PLAN")
        try:
            async for chunk in ai_runner.stream_plan(body.rtl_code, body.context):
                print(f"PLAN YIELDING: {repr(chunk)}")
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            print("STREAM FINISHED / PLAN")
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"STREAM ERROR / PLAN: {e}")
            yield f"data: {json.dumps({'chunk': f'Error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


# ── AI Agent: Testbench Writer (streaming) ─────────────────────────────────────
@app.post("/api/agents/testbench/stream")
async def stream_testbench(body: AgentRunRequest):
    async def generate():
        print("STREAM STARTED / TESTBENCH")
        try:
            async for chunk in ai_runner.stream_testbench(body.rtl_code, body.context):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            print("STREAM FINISHED / TESTBENCH")
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"STREAM ERROR / TESTBENCH: {e}")
            yield f"data: {json.dumps({'chunk': f'Error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


# ── AI Agent: Debug & Fix (streaming) ─────────────────────────────────────────
@app.post("/api/agents/debug/stream")
async def stream_debug(body: AgentRunRequest):
    async def generate():
        print("STREAM STARTED / DEBUG")
        try:
            async for chunk in ai_runner.stream_debug(
                body.rtl_code, body.simulation_log, body.context
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            print("STREAM FINISHED / DEBUG")
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"STREAM ERROR / DEBUG: {e}")
            yield f"data: {json.dumps({'chunk': f'Error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
 
    

# ── Simulation ────────────────────────────────────────────────────────────────
@app.post("/api/simulate")
async def run_simulation(body: SimulateRequest):
    sim_id  = str(uuid.uuid4())[:8]
    sim_dir = SIM_DIR / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)

    (sim_dir / "dut.v").write_text(body.rtl_code)
    (sim_dir / "tb.sv").write_text(body.testbench_code)

    has_iverilog = shutil.which("iverilog") is not None

    if has_iverilog:
        result = simulator.run_iverilog(sim_dir)
    else:
        result = await ai_runner.simulate(body.rtl_code, body.testbench_code)
        result["engine"] = "AI-SIMULATED"

    result["sim_id"]   = sim_id
    result["job_id"]   = body.job_id
    result["timestamp"] = datetime.utcnow().isoformat()

    # Extract and persist bugs
    bugs = simulator.extract_bugs(result.get("log", ""))
    for bug in bugs:
        bug["job_id"] = body.job_id
        db.save_bug(bug)
    result["bugs_found"] = bugs

    db.save_simulation(sim_id, result)
    return result

@app.get("/api/simulate/{sim_id}")
async def get_simulation(sim_id: str):
    result = db.get_simulation(sim_id)
    if not result:
        raise HTTPException(404, f"Simulation {sim_id} not found")
    return result


# ── Bugs & Bug Bounty ─────────────────────────────────────────────────────────
@app.get("/api/bugs")
async def get_bugs(job_id: str = None, severity: str = None):
    return db.get_bugs(job_id=job_id, severity=severity)

@app.post("/api/bugs/{bug_id}/confirm")
async def confirm_bug(bug_id: str, body: ConfirmBugRequest):
    bug = db.confirm_bug(bug_id, body.notes or "")
    if not bug:
        raise HTTPException(404, f"Bug {bug_id} not found")
    return bug

@app.get("/api/bounty/leaderboard")
async def leaderboard():
    jobs = db.list_jobs()
    board = []
    for job in jobs:
        bugs  = db.get_bugs(job_id=job["job_id"])
        score = sum(
            b["points"] if b["status"] == "CONFIRMED"
            else int(b["points"] * b.get("probability", 0.5))
            for b in bugs
        )
        board.append({
            "job_id":     job["job_id"],
            "module":     job["module_name"],
            "bugs_found": len(bugs),
            "confirmed":  sum(1 for b in bugs if b["status"] == "CONFIRMED"),
            "score":      score,
            "created_at": job["created_at"],
        })
    return sorted(board, key=lambda x: x["score"], reverse=True)


# ── Historical DB ─────────────────────────────────────────────────────────────
@app.get("/api/historical/bugs")
async def get_historical(module_type: str = None, limit: int = 50):
    return db.get_historical_bugs(module_type, limit)

@app.post("/api/historical/bugs/seed")
async def seed_historical():
    db.seed_historical_bugs()
    return {"status": "seeded", "count": len(db.get_historical_bugs())}


# ── Health & Stats ────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    has_iv = shutil.which("iverilog") is not None
    return {
        "status":    "healthy",
        "iverilog":  has_iv,
        "engine":    "iverilog" if has_iv else "AI-fallback",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/stats")
async def stats():
    return db.get_stats()

@app.post("/api/run-verification")
async def run_verification(body: AgentRunRequest):

    rtl = body.rtl_code
    job_id = body.job_id or str(uuid.uuid4())[:8]

    # 1️⃣ Failure prediction
    historical = db.get_historical_bugs("generic")
    predictions = await ai_runner.predict_failures(rtl, historical)

    # 2️⃣ Generate verification plan
    plan = await ai_runner.generate_plan(rtl)

    # 3️⃣ Generate testbench
    testbench = await ai_runner.generate_testbench(rtl, plan)

    # 4️⃣ Run simulation
    sim_result = await run_simulation(
        SimulateRequest(
            rtl_code=rtl,
            testbench_code=testbench,
            job_id=job_id
        )
    )

    # 5️⃣ Coverage analysis
    coverage = await ai_runner.analyze_coverage(
        rtl,
        sim_result.get("log", "")
    )

    return {
        "job_id": job_id,
        "verification_plan": plan,
        "predictions": predictions,
        "testbench": testbench,
        "simulation": sim_result,
        "coverage": coverage
    }




if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)

