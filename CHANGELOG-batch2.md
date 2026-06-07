# Batch 2 - Metricool Social Media Agency Connector

## Added
- Added native `metricool` connector with Metricool API auth via `X-Mc-Auth`, `user_id`, and optional `default_blog_id`.
- Added read tools for brands, profile/settings, recent posts, scheduled posts, available metrics, analytics timelines, and best posting times.
- Added write tools for scheduling and updating Metricool posts.
- Routed Metricool write tools through the existing hold-to-confirm flow.
- Added Metricool social agency instructions to Jarvis's system prompt so social advice is grounded in real Metricool data.

## Verified API Notes
- Official Metricool API docs state the base URL is `https://app.metricool.com/api`.
- Official docs state the auth token is sent in the `X-Mc-Auth` header.
- Official docs state API calls identify the account with `userId` and brand with `blogId`.
- Metricool's public MCP tool docs confirm scheduler endpoints:
  - `GET /v2/scheduler/posts`
  - `POST /v2/scheduler/posts`
  - `PUT /v2/scheduler/posts/{id}`
  - `GET /v2/scheduler/besttimes/{provider}`
- Metricool's public MCP tool docs confirm analytics timeline usage through `/v2/analytics/timelines`.

## Guardrails
- `metricool__schedule_post` and `metricool__update_scheduled_post` require explicit user confirmation before execution.
- Jarvis is instructed not to fabricate social metrics and to call Metricool read tools before reporting performance numbers.
- Connector responses strip token-like fields before returning payloads to the model.

## Tests
- Added tests for Metricool manifest fields, tool visibility gating, write-action confirmation, and X/Twitter character-limit validation.
