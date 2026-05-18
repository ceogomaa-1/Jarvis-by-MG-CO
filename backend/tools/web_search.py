import httpx
from backend.tools.registry import register_tool


@register_tool(
    name="web_search",
    description="Search the web for current information. Use for news, facts, prices, anything that needs real-time data.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=10.0,
        )
    data = resp.json()
    abstract = data.get("AbstractText", "")
    related = [r.get("Text", "") for r in data.get("RelatedTopics", [])[:3] if r.get("Text")]
    if abstract:
        return f"{abstract}\n\nRelated: {'; '.join(related)}" if related else abstract
    return f"No instant answer found for: {query}"
