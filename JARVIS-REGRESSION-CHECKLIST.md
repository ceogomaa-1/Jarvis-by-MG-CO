# Jarvis Brain Stabilization — Manual Regression Checklist

This is the manual companion to `backend/tests/test_regression_suite.py`
(JARVIS-BRAIN-MAP.md §D). The automated suite covers all 7 listed scenarios
at the API level. The items below need a human in a browser because they
involve real-time waits, UI rendering, or external deploy pipelines that
aren't worth automating.

Run the automated suite first: `RUN_LIVE_TESTS=1 python -m pytest backend/tests/test_regression_suite.py -v -s`
with a local server up on :8123.

## 1. Reminder #4 — real-time in-app delivery

The automated test only checks that `remind_at` is saved correctly (~60s
out). It does not wait for delivery.

- [ ] In the Jarvis Personal UI, send "Remind me in 1 min to check the oven"
- [ ] Wait ~60 seconds without refreshing
- [ ] Confirm the reminder is delivered live in-app (toast/message), not just
      visible after a manual refresh

## 2. Business Creation → Vercel deploy pipeline (C7, Phase 3)

Phase 3 fixed the backend `create.py` UNKNOWN-state handling and the frontend
`ChatCanvas.js` status message for a failed/unknown deployment lookup, but
this was verified via direct API calls, not in the browser.

- [ ] In Jarvis OS1 Business, run the Creation flow end-to-end for a new agent
- [ ] If the Vercel deployment lookup fails or returns an unknown state,
      confirm the UI shows the honest "deployment status unknown / check
      back shortly" message — not a fake "Live!" confirmation
- [ ] If the deployment succeeds, confirm the UI reflects the real live URL

## 3. New-user onboarding flow (Phase 5 finding)

Phase 5 fixed a bug where a brand-new user's first message (e.g. "remind me
in 1 min...", "note this down...") produced raw `<function_calls>` XML and a
false "Reminder set" / "Noted" claim, because onboarding suppresses all tools
but the prompt didn't say so. Verified via direct API calls; not yet checked
in the chat UI.

- [ ] In the Jarvis Personal UI, start a brand-new session (new/incognito
      user) and as the FIRST message send "remind me in 1 min to check the
      oven"
- [ ] Confirm the response is plain conversational text (no `<function_calls>`
      / `<invoke>` / XML-looking text rendered in the chat bubble)
- [ ] Confirm it does NOT claim the reminder was set, and instead says
      something like "once we're set up I'll be able to do that"
- [ ] Continue onboarding for a few messages and confirm reminders/notes work
      normally once onboarding completes

## 4. Voice mode

Not exercised by the text-based regression suite (`_VOICE_MODE_BLOCK`,
`_VOICE_MODE_SELF_AWARENESS` in `backend/llm.py`).

- [ ] In voice mode, ask Jarvis to set a reminder / save a note and confirm
      it actually calls the tool (not just narrates)
- [ ] Ask "can you hear me" / "do you have a voice" type questions and confirm
      it doesn't claim to be text-only

## 5. Business Creation sub-agent grounding (Phase 2)

The dead-URL grounding test (#2) runs against the Business **chat** flow.
The Creation sub-agents (`backend/lib/business/creation/sub_agents.py`) have
their own grounding addendum (generic placeholders instead of invented facts)
that isn't exercised by the chat-based test.

- [ ] Run the Creation flow with a dead/unreachable business URL
- [ ] Confirm the generated agent uses an obviously-generic placeholder (no
      invented menu items, founding years, addresses, etc.)
