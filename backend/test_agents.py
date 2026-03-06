import asyncio
import os
import ai_agents

async def test_stream():
    runner = ai_agents.AIAgentRunner()
    try:
        async for chunk in runner.stream_plan("module test(); endmodule", {}):
            print(f"CHUNK: {repr(chunk)}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_stream())
