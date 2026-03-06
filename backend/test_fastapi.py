import asyncio
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_stream():
    try:
        with client.stream(
            "POST",
            "/api/agents/plan/stream",
            json={"rtl_code": "module test(); endmodule"}
        ) as response:
            for chunk in response.iter_text():
                print(f"CHUNK: {chunk}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_stream()
