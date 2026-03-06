"""
AI Agent Runner — 6 verification agents powered by Claude Sonnet
"""

import anthropic
import json 
import re
from typing import AsyncGenerator, Dict, Any, List

import os

_api_key = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-dummy")
client = anthropic.AsyncAnthropic(api_key=_api_key)
MODEL  = "claude-3-5-sonnet-latest"

HIST_CONTEXT = """
Historical bug frequency (from 10,000+ RTL designs):
- FIFO overflow: 72%  |  Pointer wrap off-by-one: 61%
- Simultaneous rd/wr race: 55%  |  Async reset glitch: 43%
- Full/empty metastability: 38%  |  Arbiter starvation: 66%
- FSM illegal state: 47%  |  Memory read-during-write: 51%
"""


class AIAgentRunner:

    # ── Helper: stream text from Claude ──────────────────────────────────────
    async def _stream(self, system: str, prompt: str) -> AsyncGenerator[str, None]:
        try:
            async with client.messages.stream(
                model=MODEL, max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"\n\n[API Error] {str(e)}\n\nPlease ensure you have set a valid ANTHROPIC_API_KEY environment variable. The current key is invalid."

    async def _complete(self, system: str, prompt: str) -> str:
        try:
            resp = await client.messages.create(
                model=MODEL, max_tokens=3000,
                system=system,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text
        except Exception as e:
            return f"{{\"error\": \"API Error: {str(e)}. Please check your ANTHROPIC_API_KEY.\"}}"

    # ── Agent 1: Verification Plan ────────────────────────────────────────────
    async def stream_plan(self, rtl_code: str, context: dict = None) -> AsyncGenerator[str, None]:
        system = """You are a senior RTL verification architect.
Return ONLY valid JSON — no preamble, no markdown fences — with this exact structure:
{
  "module": "module name",
  "complexity": "LOW|MEDIUM|HIGH|CRITICAL",
  "test_groups": [
    {
      "id": "TG001",
      "name": "Group Name",
      "priority": "P0|P1|P2",
      "tests": ["test description", ...],
      "coverage_target": 95,
      "rationale": "why this group matters"
    }
  ],
  "total_tests": <number>,
  "estimated_time": "X hours",
  "risk_areas": ["area1", "area2"],
  "verification_strategy": "brief strategy"
}"""
        prompt = f"Generate a full verification plan for:\n```verilog\n{rtl_code}\n```\n{HIST_CONTEXT}"
        async for chunk in self._stream(system, prompt):
            yield chunk

    async def generate_plan(self, rtl_code: str, context: dict = None) -> dict:
        system = """You are a senior RTL verification architect.
Return ONLY valid JSON — no preamble, no markdown fences — with this exact structure:
{
  "module": "module name",
  "complexity": "LOW|MEDIUM|HIGH|CRITICAL",
  "test_groups": [
    {
      "id": "TG001",
      "name": "Group Name",
      "priority": "P0|P1|P2",
      "tests": ["test description", ...],
      "coverage_target": 95,
      "rationale": "why this group matters"
    }
  ],
  "total_tests": <number>,
  "estimated_time": "X hours",
  "risk_areas": ["area1", "area2"],
  "verification_strategy": "brief strategy"
}"""
        prompt = f"Generate a full verification plan for:\n```verilog\n{rtl_code}\n```\n{HIST_CONTEXT}"
        text = await self._complete(system, prompt)
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"error": "failed to parse plan", "raw": text}

    # ── Agent 2: Testbench Writer ─────────────────────────────────────────────
    async def stream_testbench(self, rtl_code: str, context: dict = None) -> AsyncGenerator[str, None]:
        plan_ctx = ""
        if context and context.get("plan"):
            plan_ctx = f"\nVerification Plan:\n{json.dumps(context['plan'], indent=2)}"

        system = """You are an expert SystemVerilog testbench engineer.
Write a COMPLETE, self-checking testbench with:
- Full module instantiation matching all ports exactly
- Clock generation and proper reset sequences
- Tasks for write/read operations
- Self-checking logic: $display("[PASS] testname") or $display("[FAIL] testname : reason")
- SVA assertions for key properties
- Covergroups for functional coverage
- Edge cases: boundary values, overflow, underflow, simultaneous signals, mid-op reset
- Timeout watchdog
Output ONLY valid SystemVerilog. No explanation outside the code."""

        prompt = f"""Write a complete self-checking SystemVerilog testbench for this module.
RTL:
```verilog
{rtl_code}
```
{plan_ctx}
Cover every edge case. Use $display("[PASS]") and $display("[FAIL]") per test."""
        async for chunk in self._stream(system, prompt):
            yield chunk

    async def generate_testbench(self, rtl_code: str, plan: dict = None) -> str:
        plan_ctx = ""
        if plan:
            plan_ctx = f"\nVerification Plan:\n{json.dumps(plan, indent=2)}"

        system = """You are an expert SystemVerilog testbench engineer.
Write a COMPLETE, self-checking testbench with:
- Full module instantiation matching all ports exactly
- Clock generation and proper reset sequences
- Tasks for write/read operations
- Self-checking logic: $display("[PASS] testname") or $display("[FAIL] testname : reason")
- SVA assertions for key properties
- Covergroups for functional coverage
- Edge cases: boundary values, overflow, underflow, simultaneous signals, mid-op reset
- Timeout watchdog
Output ONLY valid SystemVerilog. No explanation outside the code."""

        prompt = f"""Write a complete self-checking SystemVerilog testbench for this module.
RTL:
```verilog
{rtl_code}
```
{plan_ctx}
Cover every edge case. Use $display("[PASS]") and $display("[FAIL]") per test."""
        
        text = await self._complete(system, prompt)
        m = re.search(r"```(?:systemverilog|verilog)?\s*([\s\S]*?)```", text)
        if m:
            return m.group(1).strip()
        return text.strip()

    # ── Agent 3: Simulate (AI fallback when iverilog not available) ───────────
    async def simulate(self, rtl_code: str, testbench_code: str) -> Dict[str, Any]:
        system = """You are a hardware simulation expert.
Mentally execute this RTL + testbench and produce realistic simulation output.
Rules:
- Prefix each test result with [PASS] or [FAIL]
- Include @Xns timestamps for key events
- On failures show: expected=X got=Y
- End with: PASSED: X / FAILED: Y  and  Coverage: Z%"""

        prompt = f"""Simulate this design:

RTL:
```verilog
{rtl_code}
```
Testbench:
```systemverilog
{testbench_code}
```"""
        log = await self._complete(system, prompt)

        passed  = len(re.findall(r"\[PASS\]", log, re.IGNORECASE))
        failed  = len(re.findall(r"\[FAIL\]", log, re.IGNORECASE))
        total   = passed + failed
        cov     = 0.0
        m = re.search(r"coverage[:\s]+(\d+\.?\d*)%", log, re.IGNORECASE)
        if m:
            cov = float(m.group(1))
        elif total > 0:
            cov = round(passed / total * 100, 1)

        return {
            "engine": "AI-SIMULATED",
            "status": "PASS" if failed == 0 else "FAIL",
            "log": log,
            "passed": passed,
            "failed": failed,
            "coverage": cov,
        }

    # ── Agent 4: Coverage Analysis ────────────────────────────────────────────
    async def analyze_coverage(self, rtl_code: str, sim_log: str = None) -> Dict[str, Any]:
        system = """You are a functional coverage expert.
Return ONLY valid JSON, no markdown fences:
{
  "coverage_achieved": <0-100>,
  "coverage_grade": "A|B|C|D|F",
  "holes": [
    {
      "area": "name",
      "priority": "CRITICAL|HIGH|MEDIUM|LOW",
      "reason": "why this matters",
      "suggested_test": "specific test",
      "estimated_effort": "X min"
    }
  ],
  "prioritized_next": ["ordered list of next tests"],
  "well_covered": ["areas already well tested"],
  "recommendation": "overall recommendation"
}"""
        prompt = f"""Analyze coverage for:
```verilog
{rtl_code}
```
Simulation results:
{sim_log or "No simulation yet — analyze what SHOULD be covered."}

{HIST_CONTEXT}
Prioritize holes by historical bug frequency."""

        text = await self._complete(system, prompt)
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"coverage_achieved": 0, "coverage_grade": "F",
                "holes": [], "prioritized_next": [], "raw": text}

    # ── Agent 5: Debug & Fix ──────────────────────────────────────────────────
    async def stream_debug(self, rtl_code: str, sim_log: str = None,
                           context: dict = None) -> AsyncGenerator[str, None]:
        system = """You are an RTL debug expert.
Use EXACTLY these section headers (with ## prefix):
## ROOT CAUSE ANALYSIS
## FIXED RTL CODE
## ENHANCED TESTBENCH ADDITIONS
## VERIFICATION SIGN-OFF

Wrap fixed RTL in ```verilog blocks.
Wrap testbench additions in ```systemverilog blocks.
Be specific: name each signal, explain each change."""

        prompt = f"""Debug and fix all issues:

Original RTL:
```verilog
{rtl_code}
```

Simulation failures:
{sim_log or "No simulation yet — proactively find all RTL bugs."}

{HIST_CONTEXT}"""
        async for chunk in self._stream(system, prompt):
            yield chunk

    # ── Agent 6: Failure Prediction ───────────────────────────────────────────
    async def predict_failures(self, rtl_code: str,
                               historical_bugs: list = None) -> Dict[str, Any]:
        hist = ""
        if historical_bugs:
            hist = f"\nHistorical DB:\n{json.dumps(historical_bugs[:10], indent=2)}"

        system = """You are a verification AI specialising in predicting RTL bugs before simulation.
Return ONLY valid JSON, no markdown fences:
{
  "predictions": [
    {
      "bug_type": "name",
      "probability": <0.0-1.0>,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "location": "signal/block name",
      "description": "what the bug is",
      "historical_frequency": "X% of similar designs",
      "prevention_test": "exact test to catch this",
      "code_evidence": "quote from RTL suggesting risk"
    }
  ],
  "overall_risk": "CRITICAL|HIGH|MEDIUM|LOW",
  "confidence": <0.0-1.0>,
  "summary": "brief risk summary"
}"""

        prompt = f"""Predict all likely bugs:
```verilog
{rtl_code}
```
{hist}
{HIST_CONTEXT}
Reference actual signal names from the code."""

        text = await self._complete(system, prompt)
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"predictions": [], "overall_risk": "UNKNOWN",
                "confidence": 0, "raw": text}
