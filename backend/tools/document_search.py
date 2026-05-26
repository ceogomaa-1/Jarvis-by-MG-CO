from backend.tools.registry import register_tool


@register_tool(
    name="search_user_documents",
    description=(
        "Search the user's uploaded documents (PDFs, Word docs, text files, CSVs) "
        "when they ask about content from a file they've shared, or when the question "
        "plausibly relates to something in their documents. Returns the most relevant passages. "
        "Do NOT ask 'did you upload this?' — just search if it's plausibly relevant."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query in natural language — what you're looking for in their documents",
            }
        },
        "required": ["query"],
    },
)
async def search_user_documents_tool(query: str, user_id: str) -> str:
    print(f"TOOL_CALL: search_user_documents query={query!r} user_id={user_id}")
    from backend.routes.documents import search_user_documents
    result = await search_user_documents(user_id, query)
    if not result:
        return "No relevant content found in your documents for that query."
    return result
