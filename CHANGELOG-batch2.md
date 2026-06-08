# Batch 2 - Buffer Social Publishing Connector

## What changed
- Replaced the Metricool connector with a native `buffer` connector using Buffer's GraphQL API and bearer-token auth.
- Added Buffer tools for organizations, channels, scheduled posts, sent posts, queue posting, and exact-time scheduling.
- Routed Buffer write tools through the existing hold-to-confirm flow.
- Added Buffer social publishing instructions to Jarvis's system prompt so it asks for real channel IDs and does not invent unavailable analytics.

## Why
- Metricool API access is locked behind a much more expensive paid tier.
- Buffer gives Jarvis the core social publishing workflow we need first: connect channels, build posts, schedule posts, and queue posts.

## Safety
- `buffer__create_post`, `buffer__schedule_post`, and `buffer__add_to_queue` require explicit user confirmation before execution.
- X/Twitter posts are locally rejected above 280 characters when Jarvis marks the target network as X/Twitter.
- Jarvis is instructed to treat Buffer sent posts as lightweight content review only and not fabricate analytics.

## Tests
- Added tests for Buffer manifest fields, tool visibility gating, write-action confirmation, Metricool removal from tools, missing channel validation, and X/Twitter character-limit validation.
