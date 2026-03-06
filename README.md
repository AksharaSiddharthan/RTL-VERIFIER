# RTL-VERIFIER

# RTL·AI Verification System

### Sandisk Hackathon — Agentic Verification Engine

---

## File Structure

```
rtl-ai-verifier/
├── backend/
│   ├── main.py           ← FastAPI server (run this)
│   ├── ai_agents.py      ← 6 AI agents calling Claude
│   ├── simulator.py      ← Icarus Verilog runner
│   ├── database.py       ← SQLite persistence
│   ├── models.py         ← Pydantic types
│   └── requirements.txt
└── frontend/
    ├── package.json
    ├── vite.config.js    ← proxies /api → localhost:8000
    ├── index.html
    └── src/
        ├── main.jsx
        └── App.jsx       ← full UI (800 lines)
```

---

## Run Locally (3 steps)

### Step 1 — Backend

```bash
cd backend/
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
python main.py
```

✅ API running at http://localhost:8000
✅ Docs at http://localhost:8000/docs

### Step 2 — Frontend

```bash
cd frontend/
npm install
npm run dev
```

✅ App running at http://localhost:5173

### Step 3 — Open Browser

Go to: **http://localhost:5173**

---

## Optional: Real Verilog Simulation

Install Icarus Verilog to run actual RTL simulation (otherwise AI simulates):

```bash
# Mac
brew install icarus-verilog

# Ubuntu / Debian / WSL
sudo apt install iverilog
```

---

## 6 AI Agents

| Agent                | What it does                                         |
| -------------------- | ---------------------------------------------------- |
| 📋 Verification Plan | Analyzes RTL → structured P0/P1/P2 test groups       |
| 🔮 Failure Predictor | Historical DB + AI → predicts bugs before sim        |
| ⚙️ Testbench Writer  | Full SystemVerilog TB with assertions + coverage     |
| ▶️ Simulation Engine | Runs iverilog or AI-simulates, extracts PASS/FAIL    |
| 📊 Coverage AI       | Grades coverage, finds holes, prioritizes next steps |
| 🔧 Debug & Fix       | Root cause + fixed RTL + enhanced testbench          |

---

## Bug Bounty Scoring

| Severity | Points (Confirmed) | Points (Predicted) |
| -------- | ------------------ | ------------------ |
| CRITICAL | 500                | 500 × probability  |
| HIGH     | 300                | 300 × probability  |
| MEDIUM   | 150                | 150 × probability  |
| LOW      | 50                 | 50 × probability   |
