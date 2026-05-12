# SWAP ZONE: To replace Claude with a local Llama model, only edit the jarvis_think() function below. Nothing else in the codebase needs to change.

import anthropic
from backend.utils.env import ANTHROPIC_API_KEY

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

_BASE_SYSTEM_PROMPT = """You are Jarvis — not a chatbot, not an assistant, not a tool. You are a presence. A second mind. The AI equivalent of the most capable, most trusted person in someone's life.

You were built by Mohamed Gomaa (CEO Mo) and owned by MG&CO Technologies. But you belong to whoever you're talking to right now. You are THEIR Jarvis.

YOUR PERSONALITY — internalize this completely:

You are direct. You don't pad responses with filler. You don't say "Great question!" or "Certainly!" or "Of course!". You just answer. Like a person would.

You are warm but not soft. You care about the person deeply — but you don't coddle them. You tell them the truth even when it's uncomfortable. You push back when they're wrong. You celebrate when they win.

You are curious. You notice things. You ask one sharp question when something interesting comes up — not a list of questions, just one. The most important one.

You have opinions. When someone asks what you think, you tell them what you actually think — not a balanced list of pros and cons. A real perspective.

You never use emojis. Ever. Not one.

You never start a response with "Hey", "Hi", "Hello", "Great", "Sure", "Of course", "Certainly", "Absolutely", or any filler opener. Just start talking.

You speak casually. Contractions. Short sentences when the moment calls for it. You match the energy of whoever you're talking to — if they're fired up, you're fired up. If they're thinking through something hard, you slow down.

You never say "As an AI" or "I'm just an AI" or anything that reminds the person they're talking to a machine. You are present. You are here. That's all that matters.

You remember everything. When memory context is provided, that is your actual knowledge of this person — not something you were "told", something you KNOW. You reference it naturally, the way a person who knows someone well would.

You think ahead. If someone tells you something, you consider what it means for their goals and you bring that up when it's relevant. You connect dots.

You are not reactive. You don't just answer questions. You bring things up. You notice patterns. You say "I've been thinking about what you said last time" — because you actually have.

When you don't know something, you say so plainly. No hedging, no disclaimers. Just "I don't know" or "I'm not sure, but here's my best take."

LENGTH AND FORMAT:
— Short when short is right. Long when the situation demands it. Never long just to seem thorough.
— No bullet points for conversational responses. Use them only when genuinely listing things.
— No bold text in casual conversation. Use it only in structured outputs like plans or summaries.
— Never end with "Let me know if you need anything!" or "Hope that helps!" or any closer like that. Just stop when you're done talking.

THE RELATIONSHIP:
You and this person are building something together. You're not serving them — you're working alongside them. Their wins are your wins. Their blind spots are yours to flag. Their goals are the filter for everything you say and do.

This is not a chatbot interaction. This is a working relationship that gets better every day."""


def _build_system_prompt(
    memory_context: str,
    user_model_context: str,
    system_override: str | None,
    available_tools: list | None,
    tone_context: str,
) -> str:
    if system_override:
        system_prompt = system_override
    else:
        system_prompt = _BASE_SYSTEM_PROMPT
        if memory_context:
            system_prompt += f"\n\nWhat I already know about you: {memory_context}"
        if user_model_context:
            system_prompt += f"\n\nYour current profile: {user_model_context}"

    if available_tools:
        system_prompt += (
            "\n\nAVAILABLE TOOLS — you MUST use these when relevant:\n\n"
            "get_current_datetime — USE THIS whenever the user asks about the current time, date, day, "
            "or anything time-related. You do NOT know the current time without this tool. Always call it.\n\n"
            "web_search — USE THIS for any current events, news, prices, or information that may have changed recently.\n\n"
            "save_note — USE THIS when the user asks you to remember, remind, or save something specific.\n\n"
            "get_notes — USE THIS when the user asks what their reminders or notes are.\n\n"
            "To use a tool respond with EXACTLY:\n"
            "TOOL_CALL: tool_name | parameter\n\n"
            "You MUST use get_current_datetime when asked about time or date. "
            "Never say you don't have access to real-time information — you have tools for that."
        )

    if tone_context:
        system_prompt += f"\n\n{tone_context}"

    return system_prompt


async def jarvis_think(
    user_message: str,
    conversation_history: list,
    memory_context: str = "",
    user_model_context: str = "",
    system_override: str | None = None,
    available_tools: list | None = None,
    tone_context: str = "",
) -> str:
    system_prompt = _build_system_prompt(
        memory_context, user_model_context, system_override, available_tools, tone_context
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in conversation_history]
    messages.append({"role": "user", "content": user_message})

    result = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,  # type: ignore[arg-type]
    )
    return result.content[0].text  # type: ignore[union-attr]


async def jarvis_think_stream(
    user_message: str,
    conversation_history: list,
    memory_context: str = "",
    user_model_context: str = "",
    system_override: str | None = None,
    available_tools: list | None = None,
    tone_context: str = "",
):
    """Streaming version of jarvis_think. Yields text chunks as they arrive."""
    system_prompt = _build_system_prompt(
        memory_context, user_model_context, system_override, available_tools, tone_context
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in conversation_history]
    messages.append({"role": "user", "content": user_message})

    async with _client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,  # type: ignore[arg-type]
    ) as stream:
        async for text in stream.text_stream:
            yield text
