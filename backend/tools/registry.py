from typing import Any

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def register_tool(name: str, description: str, parameters: dict):
    def decorator(func):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "execute": func,
        }
        return func
    return decorator


def get_tools_for_claude() -> list:
    """Return registered tools in Claude API format. user_id is stripped from all
    schemas because it is injected server-side by the dispatcher — Claude should
    never need to know or pass a user_id."""
    result = []
    for t in TOOL_REGISTRY.values():
        params = t["parameters"]
        props = {k: v for k, v in params.get("properties", {}).items() if k != "user_id"}
        required = [r for r in params.get("required", []) if r != "user_id"]
        result.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": {**params, "properties": props, "required": required},
        })
    return result
