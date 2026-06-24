"""
Model-provider adapter layer (thin, additive, reversible).

Two backends behind one resolver:
  - claude (default, existing) — every mode stays on Anthropic Claude. The Claude
    path is NOT routed through any new code; existing call sites keep calling
    jarvis_think() exactly as before.
  - grok (new, opt-in) — used ONLY by Study Mode, only when explicitly enabled via
    env/flag, and only when a valid GROK_API_KEY is present. Anything else falls
    back to Claude with a small notice. Flipping it off leaves zero residue.

Nothing here can change Personal/Business/CRM/Leads routing — those never call the
resolver and are unconditionally Claude.
"""
