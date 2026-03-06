import asyncio
import anthropic
import os

async def test_stream():
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "sk-ant-dummy"))
    try:
        async with client.messages.stream(
            model="claude-3-5-sonnet-latest", max_tokens=100,
            system="system test",
            messages=[{"role": "user", "content": "hello"}]
        ) as stream:
            async for text in stream.text_stream:
                print(text)
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_stream())
