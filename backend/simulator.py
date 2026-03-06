"""
RTL Simulator — wraps Icarus Verilog (iverilog + vvp).
Auto-falls back to AI simulation if iverilog is not installed.
"""

import subprocess
import re
import uuid
from pathlib import Path
from typing import Dict, Any, List


class RTLSimulator:

    def run_iverilog(self, sim_dir: Path) -> Dict[str, Any]:
        """Compile with iverilog then run with vvp."""
        dut_file = sim_dir / "dut.v"
        tb_file  = sim_dir / "tb.sv"
        out_file = sim_dir / "sim.out"

        # ── Compile ──────────────────────────────────────────────────────────
        compile_result = subprocess.run(
            ["iverilog", "-g2012", "-o", str(out_file), "-Wall",
             str(tb_file), str(dut_file)],
            capture_output=True, text=True, timeout=30
        )

        if compile_result.returncode != 0:
            errors = self._parse_compile_errors(compile_result.stderr)
            return {
                "engine": "iverilog",
                "status": "COMPILE_ERROR",
                "log": f"COMPILE ERRORS:\n{compile_result.stderr}",
                "passed": 0, "failed": 0, "coverage": 0.0,
                "errors": errors,
            }

        # ── Run ───────────────────────────────────────────────────────────────
        run_result = subprocess.run(
            ["vvp", str(out_file)],
            capture_output=True, text=True, timeout=60
        )
        log = run_result.stdout
        if run_result.stderr:
            log += "\n" + run_result.stderr

        parsed = self._parse_sim_log(log)
        return {
            "engine": "iverilog",
            "status": "PASS" if parsed["failed"] == 0 else "FAIL",
            "log": log,
            "passed":   parsed["passed"],
            "failed":   parsed["failed"],
            "coverage": parsed["coverage"],
            "test_results": parsed["test_results"],
        }

    def _parse_compile_errors(self, stderr: str) -> List[Dict]:
        errors = []
        for line in stderr.split("\n"):
            m = re.match(r"(.+):(\d+):\s+(.+)", line)
            if m:
                errors.append({"file": m.group(1),
                                "line": int(m.group(2)),
                                "message": m.group(3).strip()})
        return errors

    def _parse_sim_log(self, log: str) -> Dict[str, Any]:
        lines = log.split("\n")
        passed, failed = 0, 0
        test_results   = []
        coverage       = 0.0

        for line in lines:
            ll = line.lower().strip()
            if re.search(r"\[pass\]|\bpassed\b", ll):
                passed += 1
                test_results.append({"status": "PASS", "message": line.strip()})
            elif re.search(r"\[fail\]|\bfailed\b|\berror\b", ll):
                failed += 1
                test_results.append({"status": "FAIL", "message": line.strip()})
            m = re.search(r"coverage[:\s]+(\d+\.?\d*)%", ll)
            if m:
                coverage = float(m.group(1))

        total = passed + failed
        if coverage == 0.0 and total > 0:
            coverage = round(passed / total * 100, 1)

        return {"passed": passed, "failed": failed,
                "coverage": coverage, "test_results": test_results}

    def extract_bugs(self, log: str) -> List[Dict]:
        """Pull confirmed bugs out of a simulation log."""
        bugs  = []
        lines = log.split("\n")
        for i, line in enumerate(lines):
            ll = line.lower()
            if not re.search(r"\[fail\]|\bfailed\b|\berror\b|\bassert.*fail", ll):
                continue

            sev = "CRITICAL" if any(w in ll for w in ["overflow", "corrupt", "illegal"]) \
                else "HIGH"   if any(w in ll for w in ["mismatch", "wrong", "unexpected"]) \
                else "MEDIUM"

            loc_m = re.search(r"@\s*(\d+)\s*ns", line)
            loc   = f"t={loc_m.group(1)}ns" if loc_m else "unknown"

            ctx_lines = lines[max(0, i-1): min(len(lines), i+2)]
            ctx = " | ".join(l.strip() for l in ctx_lines if l.strip())

            bugs.append({
                "bug_id":      str(uuid.uuid4())[:8],
                "type":        self._classify(line),
                "severity":    sev,
                "location":    loc,
                "description": ctx[:200],
                "status":      "CONFIRMED",
                "probability": 1.0,
                "source":      "SIMULATION",
            })
        return bugs[:10]

    def _classify(self, line: str) -> str:
        ll = line.lower()
        if "overflow"  in ll: return "FIFO Overflow"
        if "underflow" in ll: return "FIFO Underflow"
        if "full"      in ll: return "Full Flag Error"
        if "empty"     in ll: return "Empty Flag Error"
        if "count"     in ll: return "Count Mismatch"
        if "ptr"       in ll or "pointer" in ll: return "Pointer Error"
        if "data"      in ll: return "Data Corruption"
        if "assert"    in ll: return "Assertion Failure"
        if "reset"     in ll: return "Reset Issue"
        return "Functional Failure"
