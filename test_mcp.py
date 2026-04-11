import asyncio
from integrations.mcp_law_client import McpLawClient, select_tool

async def main():
    client = McpLawClient()
    success = await client.initialize()
    if not success:
        print('MCP init failed')
        return
    tool_name, tool_args = select_tool('공직자의 이해충돌 방지법 제5조')
    print('Tool:', tool_name, tool_args)
    res = await client.call_tool(tool_name, tool_args)
    print('Result length:', len(res))
    print(res[:1000])
    await client.close()

asyncio.run(main())
