import requests

try:
    with requests.post(
        "http://localhost:8001/api/agents/plan/stream",
        json={"rtl_code": "module test(); endmodule"},
        stream=True,
        timeout=10
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                print(f"CHUNK: {line.decode('utf-8')}")
except Exception as e:
    print(f"REQUEST FAILED: {e}")

