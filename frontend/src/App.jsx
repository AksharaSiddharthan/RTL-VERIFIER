import { useState, useRef, useEffect, useCallback } from "react";

const API = "http://localhost:8001";

// ─── Call backend streaming endpoint ──────────────────────────────────────────
async function streamAgent(endpoint, body, onChunk) {
  const response = await fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let full = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const lines = decoder.decode(value).split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const parsed = JSON.parse(raw);
          if (parsed.chunk) { full += parsed.chunk; onChunk(full); }
        } catch (e) {
          console.warn("Stream unparseable chunk:", raw, e);
        }
      }
    }
  }
  return full;
}

// ─── Call backend non-streaming endpoint ──────────────────────────────────────
async function callAPI(endpoint, body) {
  const r = await fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ─── Sample RTL ───────────────────────────────────────────────────────────────
const SAMPLE_RTL = `module fifo #(
  parameter DEPTH = 8,
  parameter WIDTH = 8
)(
  input  wire        clk,
  input  wire        rst_n,
  input  wire        wr_en,
  input  wire        rd_en,
  input  wire [WIDTH-1:0] din,
  output reg  [WIDTH-1:0] dout,
  output wire        full,
  output wire        empty,
  output reg  [$clog2(DEPTH):0] count
);
  reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;

  assign full  = (count == DEPTH);
  assign empty = (count == 0);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wr_ptr <= 0; rd_ptr <= 0; count <= 0; dout <= 0;
    end else begin
      if (wr_en && !full) begin
        mem[wr_ptr] <= din;
        wr_ptr <= wr_ptr + 1;
        count  <= count + 1;
      end
      if (rd_en && !empty) begin
        dout   <= mem[rd_ptr];
        rd_ptr <= rd_ptr + 1;
        count  <= count - 1;
      end
    end
  end
endmodule`;

const HISTORICAL = [
  { pattern: "fifo",    type: "overflow",              freq: 0.72, severity: "CRITICAL" },
  { pattern: "pointer", type: "wrap-around off-by-one", freq: 0.61, severity: "HIGH"     },
  { pattern: "count",   type: "simultaneous rd/wr race",freq: 0.55, severity: "HIGH"     },
  { pattern: "reset",   type: "async reset glitch",     freq: 0.43, severity: "MEDIUM"   },
  { pattern: "flags",   type: "full/empty metastability",freq: 0.38, severity: "MEDIUM"  },
];

const AGENTS = {
  PLAN:      { id: "PLAN",      label: "Verification Plan", icon: "📋", color: "#00d4ff" },
  PREDICT:   { id: "PREDICT",   label: "Failure Predictor", icon: "🔮", color: "#9d4edd" },
  TESTBENCH: { id: "TESTBENCH", label: "Testbench Writer",  icon: "⚙️",  color: "#ff6b35" },
  SIMULATE:  { id: "SIMULATE",  label: "Simulation Engine", icon: "▶️",  color: "#7fff00" },
  COVERAGE:  { id: "COVERAGE",  label: "Coverage AI",       icon: "📊", color: "#ff00aa" },
  DEBUG:     { id: "DEBUG",     label: "Debug & Fix",       icon: "🔧", color: "#ffd700" },
};

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [rtlCode,     setRtlCode]     = useState(SAMPLE_RTL);
  const [activeTab,   setActiveTab]   = useState("input");
  const [results,     setResults]     = useState({});
  const [running,     setRunning]     = useState({});
  const [streamText,  setStreamText]  = useState({});
  const [bugBounty,   setBugBounty]   = useState([]);
  const [pipelineStep,setPipelineStep]= useState(null);
  const [error,       setError]       = useState(null);

  // ── Run a single agent ────────────────────────────────────────────────────
// inside App component

const runAgent = useCallback(async (agentId) => {
  setRunning(r => ({ ...r, [agentId]: true }));
  setError(null);

  // small delay to simulate work
  await new Promise(r => setTimeout(r, 300));

  let fakeResult = null;

  if (agentId === "PLAN") {
    fakeResult = {
      module: "fifo",
      complexity: "MEDIUM",
      total_tests: 12,
      estimated_time: "2 hours",
      risk_areas: ["overflow", "pointer wrap-around"],
      verification_strategy: "Constrained-random plus directed corner tests",
      test_groups: [
        {
          id: "TG001",
          name: "Basic sanity",
          priority: "P1",
          tests: ["reset behavior", "single write/read"],
          coverage_target: 90,
          rationale: "Ensure basic FIFO operation"
        },
        {
          id: "TG002",
          name: "Stress & overflow",
          priority: "P0",
          tests: ["fill to full", "overflow attempts", "wrap-around pointers"],
          coverage_target: 95,
          rationale: "Most common bug patterns"
        }
      ]
    };

  } else if (agentId === "PREDICT") {
    fakeResult = {
      overall_risk: "HIGH",
      confidence: 0.82,
      predictions: [
        {
          bug_type: "FIFO overflow not blocked",
          probability: 0.72,
          severity: "CRITICAL",
          location: "count / full flag",
          description: "Write enable not gated correctly when full.",
          historical_frequency: "72% of similar designs",
          prevention_test: "Drive continuous writes until full+2 and check no data corruption.",
          code_evidence: "assign full = (count == DEPTH);"
        },
        {
          bug_type: "Pointer wrap off-by-one",
          probability: 0.6,
          severity: "HIGH",
          location: "wr_ptr / rd_ptr",
          description: "Pointers may wrap before reaching last entry.",
          historical_frequency: "61% of similar designs",
          prevention_test: "Randomized sequences around DEPTH-1 and DEPTH transitions.",
          code_evidence: "wr_ptr <= wr_ptr + 1; rd_ptr <= rd_ptr + 1;"
        }
      ]
    };

    // also seed bugBounty so the board is not empty
    const preds = fakeResult.predictions.map(p => ({
      id: `PRED-${Date.now()}-${Math.random().toString(36).slice(2,5)}`,
      type: p.bug_type,
      severity: p.severity,
      source: "AI Prediction (FAKE)",
      probability: p.probability,
      location: p.location,
      status: "PREDICTED",
      points: { CRITICAL:500, HIGH:300, MEDIUM:150, LOW:50 }[p.severity] || 100,
      description: p.description,
    }));
    setBugBounty(b => {
      const existing = new Set(b.map(x => x.type));
      return [...b, ...preds.filter(p => !existing.has(p.type))];
    });

  } else if (agentId === "TESTBENCH") {
    fakeResult = `
module tb;
  reg clk = 0;
  reg rst_n = 0;
  reg wr_en = 0;
  reg rd_en = 0;
  reg [7:0] din  = 0;
  wire [7:0] dout;
  wire full, empty;
  reg [7:0] exp;

  fifo #(.DEPTH(8), .WIDTH(8)) dut (
    .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .rd_en(rd_en),
    .din(din), .dout(dout), .full(full), .empty(empty)
  );

  always #5 clk = ~clk;

  initial begin
    $display("[INFO] Starting FIFO testbench (FAKE)");
    rst_n = 0; #20; rst_n = 1; #10;

    // simple write/read
    wr_en = 1; din = 8'hAA; #10;
    wr_en = 0; rd_en = 1; #10;
    rd_en = 0;

    if (dout === 8'hAA)
      $display("[PASS] basic write/read");
    else
      $display("[FAIL] basic write/read : expected=0xAA got=%0h", dout);

    #50;
    $display("[INFO] Ending simulation");
    $finish;
  end
endmodule
`.trim();

  } else if (agentId === "SIMULATE") {
    fakeResult = {
      engine: "AI-SIMULATED",
      status: "FAIL",
      log: [
        "@0ns  [INFO] Reset asserted",
        "@30ns [INFO] Reset deasserted",
        "@40ns [INFO] Writing 0xAA",
        "@60ns [INFO] Reading ... dout=0x00",
        "@60ns [FAIL] basic write/read : expected=0xAA got=0x00",
        "PASSED: 0 / FAILED: 1  Coverage: 40%"
      ].join("\n"),
      passed: 0,
      failed: 1,
      coverage: 40.0
    };

    const confirmed = [
      {
        id: "BUG-FAKE-1",
        type: "Data mismatch on basic write/read",
        severity: "HIGH",
        source: "Simulation (FAKE)",
        probability: 1.0,
        location: "dout",
        status: "CONFIRMED",
        points: 300
      }
    ];
    setBugBounty(bb => [...bb, ...confirmed]);

  } else if (agentId === "COVERAGE") {
    fakeResult = {
      coverage_achieved: 42,
      coverage_grade: "C",
      holes: [
        {
          area: "Overflow / underflow behavior",
          priority: "CRITICAL",
          reason: "No tests driving writes beyond full or reads beyond empty.",
          suggested_test: "Randomized push/pop sequence with constraints to hit boundary conditions.",
          estimated_effort: "20 min"
        }
      ],
      prioritized_next: [
        "Add directed overflow/underflow tests.",
        "Add mid-operation reset test.",
        "Add randomized stress with covergroups."
      ],
      well_covered: ["Basic reset", "Single write/read"],
      recommendation: "Focus next on boundary and stress conditions."
    };

  } else if (agentId === "DEBUG") {
    fakeResult = `
## ROOT CAUSE ANALYSIS
- FIFO full flag logic is correct, but dout is not updated until after the first read.

## FIXED RTL CODE
\`\`\`verilog
// (fake) fixed code would go here
\`\`\`

## ENHANCED TESTBENCH ADDITIONS
\`\`\`systemverilog
// (fake) additional checks and corner-case tests
\`\`\`

## VERIFICATION SIGN-OFF
- Risk reduced after fix + new tests.
`.trim();
  }

  setResults(r => ({ ...r, [agentId]: fakeResult }));
  setRunning(r => ({ ...r, [agentId]: false }));
}, [rtlCode, results, setBugBounty]);



  // ── Run full pipeline ─────────────────────────────────────────────────────
  const runPipeline = async () => {
  const steps = ["PLAN", "PREDICT", "TESTBENCH", "SIMULATE", "COVERAGE", "DEBUG"];
  for (const step of steps) {
    setPipelineStep(step);
    setActiveTab(step.toLowerCase());
    console.log("Running pipeline step (FAKE):", step);
    await runAgent(step);
    await new Promise(r => setTimeout(r, 200));
  }
  setPipelineStep(null);
  setActiveTab("bounty");
  console.log("Pipeline complete (FAKE), final results:", results);
};



  const totalScore = bugBounty.reduce((s, b) =>
    s + (b.status === "CONFIRMED" ? b.points : Math.round(b.points * b.probability)), 0);

  const sevColor = s =>
    s === "CRITICAL" ? "#ff2020" : s === "HIGH" ? "#ff6b35" :
    s === "MEDIUM"   ? "#ffd700" : "#00d4ff";

  const tabs = [
    { id: "input",     label: "RTL Input",    },
    { id: "plan",      label: "Plan",         },
    { id: "predict",   label: "Predict",     },
    { id: "testbench", label: "Testbench",    },
    { id: "simulate",  label: "Simulate",   },
    { id: "coverage",  label: "Coverage",   },
    { id: "debug",     label: "Debug/Fix",  },
    { id: "bounty",    label: `Bug Bounty ${bugBounty.length ? `(${bugBounty.length})` : ""}`},
  ];

  return (
    <div style={{ fontFamily:"'JetBrains Mono','Fira Code',monospace", background:"#0a0a0f",
      minHeight:"100vh", color:"#e0e0e0", display:"flex", flexDirection:"column" }}>

      {/* HEADER */}
      <header style={{ padding:"14px 24px", borderBottom:"1px solid #1a1a2e",
        background:"#0a0a0f", display:"flex", alignItems:"center",
        justifyContent:"space-between", position:"sticky", top:0, zIndex:100 }}>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <div style={{ width:36, height:36, borderRadius:8,
            background:"linear-gradient(135deg,#00d4ff,#7fff00)",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:18, fontWeight:"bold", color:"#000" }}>V</div>
          <div>
            <div style={{ fontSize:16, fontWeight:700, color:"#fff" }}>
              RTL<span style={{ color:"#00d4ff" }}>·AI</span> Verification System
            </div>
            <div style={{ fontSize:10, color:"#444", letterSpacing:"0.1em" }}>
              SANDISK HACKATHON · AGENTIC VERIFICATION ENGINE
            </div>
          </div>
        </div>
        <div style={{ display:"flex", gap:10, alignItems:"center" }}>
          {pipelineStep && (
            <span style={{ fontSize:11, color:"#00d4ff" }}>
              <span style={{ animation:"pulse 1s infinite" }}>●</span> RUNNING {pipelineStep}...
            </span>
          )}
          {error && (
            <span style={{ fontSize:11, color:"#ff4444", maxWidth:300, overflow:"hidden",
              textOverflow:"ellipsis", whiteSpace:"nowrap" }}>⚠ {error}</span>
          )}
          <button onClick={runPipeline} disabled={!!pipelineStep} style={{
            background: pipelineStep ? "#1a1a2e" : "linear-gradient(135deg,#00d4ff,#0080ff)",
            border:"none", borderRadius:8, padding:"8px 20px",
            color: pipelineStep ? "#444" : "#000",
            fontWeight:700, fontSize:12, cursor: pipelineStep ? "not-allowed":"pointer",
            fontFamily:"inherit",
          }}>
            {pipelineStep ? " RUNNING..." : " RUN FULL PIPELINE"}
          </button>
        </div>
      </header>

      {/* TABS */}
      <div style={{ display:"flex", gap:2, padding:"8px 16px",
        borderBottom:"1px solid #1a1a2e", overflowX:"auto" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
            background: activeTab===t.id ? "#1a1a2e" : "transparent",
            border: activeTab===t.id ? "1px solid #2a2a4e" : "1px solid transparent",
            borderRadius:6, padding:"6px 14px",
            color: activeTab===t.id ? "#fff" : "#555",
            fontSize:11, cursor:"pointer", whiteSpace:"nowrap",
            display:"flex", alignItems:"center", gap:5, fontFamily:"inherit",
          }}>
            {t.icon} {t.label}
            {running[t.id.toUpperCase()] && <span style={{ color:"#00d4ff",fontSize:8 }}>●</span>}
            {results[t.id.toUpperCase()] && !running[t.id.toUpperCase()] &&
              <span style={{ color:"#7fff00",fontSize:8 }}>✓</span>}
          </button>
        ))}
      </div>

      {/* CONTENT */}
      <main style={{ flex:1, padding:20, maxWidth:1400, width:"100%", margin:"0 auto",
        boxSizing:"border-box" }}>

        {/* ── INPUT ── */}
        {activeTab === "input" && (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 300px", gap:16 }}>
            <div>
              <div style={{ fontSize:11, color:"#555", marginBottom:8, letterSpacing:"0.1em" }}>
                RTL SOURCE — SystemVerilog / Verilog
              </div>
              <textarea value={rtlCode} onChange={e => setRtlCode(e.target.value)} style={{
                width:"100%", height:500, background:"#0d0d1a",
                border:"1px solid #1a1a2e", borderRadius:10, padding:16,
                color:"#c9d1d9", fontSize:12, lineHeight:1.6, fontFamily:"inherit",
                resize:"vertical", outline:"none", boxSizing:"border-box",
              }}/>
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
              <Panel title="PIPELINE STAGES">
                {Object.values(AGENTS).map(a => (
                  <button key={a.id}
                    onClick={() => { setActiveTab(a.id.toLowerCase()); runAgent(a.id); }}
                    disabled={running[a.id]}
                    style={{
                      width:"100%", background:"#111122",
                      border:`1px solid ${running[a.id] ? a.color : "#2a2a3e"}`,
                      borderRadius:6, padding:"8px 12px",
                      color: running[a.id] ? a.color : "#888",
                      fontSize:11, cursor:"pointer", textAlign:"left",
                      display:"flex", justifyContent:"space-between",
                      marginBottom:6, fontFamily:"inherit",
                    }}>
                    <span>{a.icon} {a.label}</span>
                    <span style={{ fontSize:9 }}>
                      {running[a.id] ? "RUNNING" : results[a.id] ? "✓ DONE" : "RUN →"}
                    </span>
                  </button>
                ))}
              </Panel>
              <Panel title="HISTORICAL BUG DB">
                {HISTORICAL.map((b,i) => (
                  <div key={i} style={{ display:"flex", justifyContent:"space-between",
                    padding:"5px 0", borderBottom:"1px solid #111", fontSize:10 }}>
                    <span style={{ color:"#666" }}>{b.type}</span>
                    <span style={{ color:sevColor(b.severity) }}>{Math.round(b.freq*100)}%</span>
                  </div>
                ))}
              </Panel>
            </div>
          </div>
        )}

        {/* ── PLAN ── */}
        {activeTab === "plan" && (
          <AgentTab agent={AGENTS.PLAN} result={results.PLAN} stream={streamText.PLAN}
            running={running.PLAN} onRun={() => runAgent("PLAN")}>
            {r => typeof r === "object" ? (
              <div style={{ display:"grid", gap:12 }}>
                <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
                  <Stat label="Module"     value={r.module}         color="#00d4ff"/>
                  <Stat label="Complexity" value={r.complexity}     color={sevColor(r.complexity)}/>
                  <Stat label="Tests"      value={r.total_tests}    color="#7fff00"/>
                  <Stat label="Est. Time"  value={r.estimated_time} color="#ff6b35"/>
                </div>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
                  {(r.test_groups||[]).map(tg => (
                    <div key={tg.id} style={{ background:"#0d0d1a", border:"1px solid #1a1a2e",
                      borderRadius:8, padding:12 }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
                        <span style={{ fontSize:12, color:"#fff", fontWeight:600 }}>{tg.name}</span>
                        <Badge text={tg.priority}
                          color={tg.priority==="P0"?"#ff2020":tg.priority==="P1"?"#ff6b35":"#00d4ff"}/>
                      </div>
                      <div style={{ fontSize:10, color:"#555", marginBottom:5 }}>
                        Target: <span style={{ color:"#7fff00" }}>{tg.coverage_target}%</span>
                      </div>
                      {(tg.tests||[]).map((t,i) => (
                        <div key={i} style={{ fontSize:10, color:"#777", padding:"2px 0" }}>→ {t}</div>
                      ))}
                    </div>
                  ))}
                </div>
                {r.risk_areas && (
                  <div style={{ background:"#1a0a0a", border:"1px solid #3a1010",
                    borderRadius:8, padding:12 }}>
                    <div style={{ fontSize:11, color:"#ff4040", marginBottom:6 }}>⚠ RISK AREAS</div>
                    {r.risk_areas.map((ra,i) => (
                      <div key={i} style={{ fontSize:11, color:"#ff6060", padding:"2px 0" }}>• {ra}</div>
                    ))}
                  </div>
                )}
              </div>
            ) : <CodeBlock code={r}/>}
          </AgentTab>
        )}

        {/* ── PREDICT ── */}
        {activeTab === "predict" && (
          <AgentTab agent={AGENTS.PREDICT} result={results.PREDICT} stream={streamText.PREDICT}
            running={running.PREDICT} onRun={() => runAgent("PREDICT")}>
            {r => r && r.predictions ? (
              <div style={{ display:"grid", gap:12 }}>
                <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
                  <Stat label="Overall Risk" value={r.overall_risk} color={sevColor(r.overall_risk)}/>
                  <Stat label="Confidence"   value={`${Math.round((r.confidence||0)*100)}%`} color="#9d4edd"/>
                  <Stat label="Predictions"  value={r.predictions.length} color="#00d4ff"/>
                </div>
                {r.predictions.map((p,i) => (
                  <div key={i} style={{ background:"#0d0d1a",
                    border:`1px solid ${sevColor(p.severity)}33`, borderRadius:8, padding:14 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
                      <span style={{ fontSize:13, color:"#fff", fontWeight:600 }}>{p.bug_type}</span>
                      <div style={{ display:"flex", gap:8 }}>
                        <Badge text={p.severity} color={sevColor(p.severity)}/>
                        <span style={{ fontSize:10, color:"#9d4edd" }}>
                          {Math.round(p.probability*100)}% likely
                        </span>
                      </div>
                    </div>
                    <div style={{ fontSize:10, color:"#666", marginBottom:4 }}>{p.description}</div>
                    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6, fontSize:10 }}>
                      <span style={{ color:"#555" }}>Location: <span style={{ color:"#00d4ff" }}>{p.location}</span></span>
                      <span style={{ color:"#555" }}>Historical: <span style={{ color:"#ffd700" }}>{p.historical_frequency}</span></span>
                    </div>
                    <div style={{ marginTop:6, fontSize:10, color:"#888" }}>
                      Test: <span style={{ color:"#7fff00" }}>{p.prevention_test}</span>
                    </div>
                    <ProbBar prob={p.probability} color={sevColor(p.severity)}/>
                  </div>
                ))}
              </div>
            ) : <CodeBlock code={JSON.stringify(r, null, 2)}/>}
          </AgentTab>
        )}

        {/* ── TESTBENCH ── */}
        {activeTab === "testbench" && (
          <AgentTab agent={AGENTS.TESTBENCH} result={results.TESTBENCH} stream={streamText.TESTBENCH}
            running={running.TESTBENCH} onRun={() => runAgent("TESTBENCH")}>
            {r => <CodeBlock code={typeof r==="string"?r:JSON.stringify(r,null,2)} lang="SystemVerilog"/>}
          </AgentTab>
        )}

        {/* ── SIMULATE ── */}
        {activeTab === "simulate" && (
          <AgentTab agent={AGENTS.SIMULATE} result={results.SIMULATE} stream={streamText.SIMULATE}
            running={running.SIMULATE} onRun={() => runAgent("SIMULATE")}>
            {r => {
              const data = typeof r === "object" ? r : null;
              const log  = data ? data.log : r;
              return (
                <div style={{ display:"grid", gap:12 }}>
                  {data && (
                    <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
                      <Stat label="Status"   value={data.status}   color={data.status==="PASS"?"#7fff00":"#ff2020"}/>
                      <Stat label="Passed"   value={data.passed}   color="#7fff00"/>
                      <Stat label="Failed"   value={data.failed}   color="#ff2020"/>
                      <Stat label="Coverage" value={`${data.coverage}%`} color="#00d4ff"/>
                      <Stat label="Engine"   value={data.engine}   color="#555"/>
                    </div>
                  )}
                  <SimLog text={log||""}/>
                </div>
              );
            }}
          </AgentTab>
        )}

        {/* ── COVERAGE ── */}
        {activeTab === "coverage" && (
          <AgentTab agent={AGENTS.COVERAGE} result={results.COVERAGE} stream={streamText.COVERAGE}
            running={running.COVERAGE} onRun={() => runAgent("COVERAGE")}>
            {r => r && r.holes ? (
              <div style={{ display:"grid", gap:12 }}>
                <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
                  <Stat label="Coverage" value={`${r.coverage_achieved}%`} color="#7fff00"/>
                  <Stat label="Grade"    value={r.coverage_grade}
                    color={r.coverage_grade==="A"?"#7fff00":r.coverage_grade==="B"?"#00d4ff":
                           r.coverage_grade==="C"?"#ffd700":"#ff2020"}/>
                  <Stat label="Holes"    value={r.holes.length} color="#ff6b35"/>
                </div>
                <div style={{ background:"#0d0d1a", border:"1px solid #1a1a2e", borderRadius:8, padding:14 }}>
                  <div style={{ fontSize:10, color:"#555", marginBottom:6 }}>COVERAGE METER</div>
                  <div style={{ background:"#111", borderRadius:4, height:18, overflow:"hidden" }}>
                    <div style={{ width:`${r.coverage_achieved}%`, height:"100%",
                      background:"linear-gradient(90deg,#ff2020,#ffd700,#7fff00)", borderRadius:4 }}/>
                  </div>
                  <div style={{ fontSize:10, color:"#555", marginTop:4, textAlign:"right" }}>
                    {r.coverage_achieved}% / 100%
                  </div>
                </div>
                <div style={{ fontSize:11, color:"#555" }}>COVERAGE HOLES</div>
                {r.holes.map((h,i) => (
                  <div key={i} style={{ background:"#0d0d1a",
                    border:`1px solid ${sevColor(h.priority)}33`, borderRadius:8, padding:12 }}>
                    <div style={{ display:"flex", justifyContent:"space-between" }}>
                      <span style={{ fontSize:12, color:"#fff" }}>{h.area}</span>
                      <Badge text={h.priority} color={sevColor(h.priority)}/>
                    </div>
                    <div style={{ fontSize:10, color:"#777", marginTop:4 }}>{h.reason}</div>
                    <div style={{ fontSize:10, color:"#00d4ff", marginTop:4 }}>→ {h.suggested_test}</div>
                  </div>
                ))}
                {r.prioritized_next && (
                  <div style={{ background:"#0a1a0a", border:"1px solid #1a3a1a", borderRadius:8, padding:12 }}>
                    <div style={{ fontSize:11, color:"#7fff00", marginBottom:8 }}>📌 NEXT PRIORITIES</div>
                    {r.prioritized_next.map((n,i) => (
                      <div key={i} style={{ fontSize:11, color:"#888", padding:"3px 0" }}>
                        <span style={{ color:"#7fff00" }}>{i+1}.</span> {n}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : <CodeBlock code={JSON.stringify(r,null,2)}/>}
          </AgentTab>
        )}

        {/* ── DEBUG ── */}
        {activeTab === "debug" && (
          <AgentTab agent={AGENTS.DEBUG} result={results.DEBUG} stream={streamText.DEBUG}
            running={running.DEBUG} onRun={() => runAgent("DEBUG")}>
            {r => <DebugResult text={typeof r==="string"?r:JSON.stringify(r,null,2)}/>}
          </AgentTab>
        )}

        {/* ── BUG BOUNTY ── */}
        {activeTab === "bounty" && (
          <div>
            <div style={{ display:"flex", justifyContent:"space-between",
              alignItems:"center", marginBottom:16 }}>
              <div>
                <div style={{ fontSize:20, fontWeight:700, color:"#ffd700" }}>🏆 Bug Bounty Board</div>
                <div style={{ fontSize:11, color:"#555" }}>End-to-End Verification Challenge</div>
              </div>
              <div style={{ background:"linear-gradient(135deg,#ffd70015,#ff6b3510)",
                border:"1px solid #ffd70033", borderRadius:10, padding:"12px 24px", textAlign:"center" }}>
                <div style={{ fontSize:10, color:"#555" }}>TOTAL SCORE</div>
                <div style={{ fontSize:32, fontWeight:700, color:"#ffd700" }}>{totalScore.toLocaleString()}</div>
                <div style={{ fontSize:10, color:"#666" }}>verification points</div>
              </div>
            </div>

            {bugBounty.length === 0 ? (
              <div style={{ textAlign:"center", padding:60, color:"#333",
                border:"1px dashed #1a1a2e", borderRadius:12 }}>
                <div style={{ fontSize:40, marginBottom:12 }}></div>
                <div style={{ fontSize:14 }}>Run the pipeline to discover bugs</div>
                <div style={{ fontSize:11, marginTop:4, color:"#444" }}>
                  Confirmed = full points · Predicted = probability-weighted points
                </div>
              </div>
            ) : (
              <>
                <div style={{ display:"grid", gap:8 }}>
                  <div style={{ display:"grid",
                    gridTemplateColumns:"50px 1fr 100px 100px 90px 70px 90px",
                    padding:"4px 12px", fontSize:10, color:"#444", letterSpacing:"0.08em" }}>
                    <span>#</span><span>BUG</span><span>SEVERITY</span>
                    <span>SOURCE</span><span>STATUS</span><span>PROB</span><span>POINTS</span>
                  </div>
                  {bugBounty.map((bug,i) => (
                    <div key={bug.id} style={{
                      display:"grid",
                      gridTemplateColumns:"50px 1fr 100px 100px 90px 70px 90px",
                      padding:"10px 12px", background:"#0d0d1a",
                      border:`1px solid ${sevColor(bug.severity)}22`,
                      borderRadius:8, alignItems:"center", fontSize:11,
                    }}>
                      <span style={{ color:"#333" }}>#{i+1}</span>
                      <span style={{ color:"#e0e0e0", fontSize:10 }}>{bug.type}</span>
                      <span><Badge text={bug.severity} color={sevColor(bug.severity)}/></span>
                      <span style={{ color:"#666", fontSize:10 }}>{bug.source}</span>
                      <span style={{ color:bug.status==="CONFIRMED"?"#7fff00":"#ffd700", fontSize:10 }}>
                        {bug.status}
                      </span>
                      <span style={{ color:"#9d4edd" }}>{Math.round(bug.probability*100)}%</span>
                      <span style={{ color:"#ffd700", fontWeight:700 }}>
                        +{bug.status==="CONFIRMED"
                          ? bug.points
                          : Math.round(bug.points*bug.probability)}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop:14, display:"grid",
                  gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:10 }}>
                  {["CRITICAL","HIGH","MEDIUM","LOW"].map(sev => (
                    <div key={sev} style={{ background:"#0d0d1a",
                      border:`1px solid ${sevColor(sev)}33`, borderRadius:8,
                      padding:10, textAlign:"center" }}>
                      <div style={{ fontSize:22, fontWeight:700, color:sevColor(sev) }}>
                        {bugBounty.filter(b=>b.severity===sev).length}
                      </div>
                      <div style={{ fontSize:10, color:"#555" }}>{sev}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </main>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        ::-webkit-scrollbar { width:5px; height:5px }
        ::-webkit-scrollbar-track { background:#0a0a0f }
        ::-webkit-scrollbar-thumb { background:#2a2a4e; border-radius:3px }
      `}</style>
    </div>
  );
}

// ─── Shared UI Components ──────────────────────────────────────────────────────

function Panel({ title, children }) {
  return (
    <div style={{ background:"#0d0d1a", border:"1px solid #1a1a2e", borderRadius:10, padding:14 }}>
      <div style={{ fontSize:10, color:"#444", letterSpacing:"0.1em", marginBottom:10 }}>{title}</div>
      {children}
    </div>
  );
}

function AgentTab({ agent, result, stream, running, onRun, children }) {
  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between",
        alignItems:"center", marginBottom:14 }}>
        <div>
          <div style={{ fontSize:18, fontWeight:700, color:"#fff" }}>
            {agent.icon} {agent.label}
          </div>
          <div style={{ fontSize:10, color:"#444", marginTop:2 }}>AI Agent · Claude Sonnet</div>
        </div>
        <button onClick={onRun} disabled={running} style={{
          background: running ? "#111" :`linear-gradient(135deg,${agent.color}22,${agent.color}11)`,
          border:`1px solid ${running?"#222":agent.color}`,
          borderRadius:8, padding:"8px 18px",
          color: running?"#444":agent.color,
          fontSize:11, cursor:running?"not-allowed":"pointer",
          fontWeight:600, fontFamily:"inherit",
        }}>
          {running ? " PROCESSING..." : `▶ RUN ${agent.label.toUpperCase()}`}
        </button>
      </div>

      {running && (
        <div style={{ background:"#0d0d1a", border:`1px solid ${agent.color}22`,
          borderRadius:10, padding:16, marginBottom:14 }}>
          <div style={{ fontSize:10, color:agent.color, marginBottom:6 }}>◌ STREAMING...</div>
          <pre style={{ fontSize:11, color:"#777", whiteSpace:"pre-wrap",
            wordBreak:"break-word", maxHeight:400, overflow:"auto",
            lineHeight:1.5, fontFamily:"inherit" }}>
            {stream || "Initializing..."}
          </pre>
        </div>
      )}

      {!running && result != null && (
        <div style={{ background:"#0d0d1a", border:"1px solid #1a1a2e",
          borderRadius:10, padding:16 }}>
          {children(result)}
        </div>
      )}

      {!running && result == null && (
        <div style={{ textAlign:"center", padding:60, color:"#2a2a2a",
          border:"1px dashed #1a1a2e", borderRadius:12 }}>
          <div style={{ fontSize:32, marginBottom:8 }}>{agent.icon}</div>
          <div style={{ fontSize:13 }}>Click Run to start {agent.label}</div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ background:"#111122", border:`1px solid ${color}22`,
      borderRadius:8, padding:"8px 14px", minWidth:90 }}>
      <div style={{ fontSize:9, color:"#444", letterSpacing:"0.1em", marginBottom:3 }}>{label}</div>
      <div style={{ fontSize:16, fontWeight:700, color }}>{value}</div>
    </div>
  );
}

function Badge({ text, color }) {
  return (
    <span style={{ fontSize:10, padding:"2px 7px", borderRadius:4,
      background:`${color}20`, color, display:"inline-block" }}>{text}</span>
  );
}

function ProbBar({ prob, color }) {
  return (
    <div style={{ marginTop:8, background:"#111", borderRadius:3, height:3, overflow:"hidden" }}>
      <div style={{ width:`${prob*100}%`, height:"100%", background:color, borderRadius:3 }}/>
    </div>
  );
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false);
  const clean = (code||"").replace(/```\w*\n?/g,"").replace(/```/g,"").trim();
  return (
    <div style={{ position:"relative" }}>
      {lang && <div style={{ fontSize:10, color:"#444", marginBottom:5 }}>{lang}</div>}
      <button onClick={() => { navigator.clipboard.writeText(clean); setCopied(true);
        setTimeout(()=>setCopied(false),2000); }} style={{
        position:"absolute", top:8, right:8, background:"#1a1a2e",
        border:"1px solid #2a2a4e", borderRadius:4, padding:"2px 8px",
        color:copied?"#7fff00":"#444", fontSize:10, cursor:"pointer", fontFamily:"inherit",
      }}>
        {copied?"✓ COPIED":"COPY"}
      </button>
      <pre style={{ background:"#060608", border:"1px solid #1a1a2e", borderRadius:8,
        padding:16, fontSize:11, color:"#c9d1d9", overflowX:"auto",
        whiteSpace:"pre-wrap", wordBreak:"break-word", lineHeight:1.6,
        maxHeight:500, overflowY:"auto", fontFamily:"inherit" }}>{clean}</pre>
    </div>
  );
}

function SimLog({ text }) {
  return (
    <div style={{ background:"#010305", border:"1px solid #0a2a0a", borderRadius:8,
      padding:16, maxHeight:500, overflowY:"auto", fontFamily:"monospace" }}>
      {(text||"").split("\n").map((line,i) => {
        const ll = line.toLowerCase();
        const isPass = ll.includes("[pass]") || ll.includes("passed");
        const isFail = ll.includes("[fail]") || ll.includes("failed") || ll.includes("error");
        const isTime = /^[@\[]?\d/.test(line.trim());
        return (
          <div key={i} style={{ fontSize:11, lineHeight:1.8,
            color: isFail?"#ff4444": isPass?"#7fff00": isTime?"#00d4ff":"#666" }}>
            {line}
          </div>
        );
      })}
    </div>
  );
}

function DebugResult({ text }) {
  const sections = text.split(/\n##\s+/).filter(Boolean);
  if (sections.length <= 1) return <CodeBlock code={text}/>;
  return (
    <div style={{ display:"grid", gap:12 }}>
      {sections.map((s,i) => {
        const [title,...body] = s.split("\n");
        const content = body.join("\n").trim();
        return (
          <div key={i} style={{ background:"#0a0a14", border:"1px solid #1a1a2e",
            borderRadius:8, padding:14 }}>
            <div style={{ fontSize:12, fontWeight:700, color:"#00d4ff", marginBottom:8 }}>
              {title.trim()}
            </div>
            {content.includes("```")
              ? <CodeBlock code={content}/>
              : <div style={{ fontSize:11, color:"#777", lineHeight:1.7, whiteSpace:"pre-wrap" }}>
                  {content.replace(/```\w*|```/g,"")}
                </div>
            }
          </div>
        );
      })}
    </div>
  );
}
