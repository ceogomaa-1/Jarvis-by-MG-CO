"""
Buffer social publishing connector.

Buffer API notes verified from official docs:
- GraphQL endpoint: https://api.buffer.com
- Auth header: Authorization: Bearer <api_key>
- Posting supports queue/custom scheduled modes through createPost.
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

BASE = "https://api.buffer.com"


def _compact(value: Any) -> Any:
    """Remove None/empty values before sending GraphQL variables."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_compact(v) for v in value if v not in (None, "", [], {})]
    return value


class BufferConnector(BaseConnector):
    CONNECTOR_TYPE = "buffer"
    DISPLAY_NAME = "Buffer"
    DESCRIPTION = "Schedule, queue, and manage social posts through Buffer."
    DOCS_URL = "https://developers.buffer.com/"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "Buffer API Key",
            "type": "password",
            "placeholder": "buf_...",
            "secret": True,
            "required": True,
        },
        "organization_id": {
            "label": "Default Organization ID (optional)",
            "type": "text",
            "placeholder": "org_...",
            "required": False,
        },
    }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '')}",
            "Content-Type": "application/json",
        }

    async def _graphql(self, query: str, variables: dict | None = None) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing Buffer credential field(s): {', '.join(missing)}")

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    BASE,
                    headers=self._headers(),
                    json={"query": query, "variables": variables or {}},
                )
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Buffer request failed: {e}")

        if resp.status_code in (401, 403):
            return ConnectorResult(ok=False, error="Buffer access denied. Check the API key and organization permissions.")
        if resp.status_code >= 400:
            return ConnectorResult(ok=False, error=f"Buffer {resp.status_code}: {resp.text[:300]}")

        try:
            body = resp.json()
        except Exception:
            return ConnectorResult(ok=False, error=f"Buffer returned non-JSON response: {resp.text[:300]}")

        errors = body.get("errors") if isinstance(body, dict) else None
        if errors:
            message = errors[0].get("message") if isinstance(errors, list) and errors else str(errors)
            return ConnectorResult(ok=False, error=f"Buffer GraphQL error: {message}")

        return ConnectorResult(ok=True, data=body.get("data", body))

    async def test(self) -> ConnectorResult:
        result = await self.list_organizations()
        if result.ok:
            return ConnectorResult(ok=True, data={"message": "Buffer connection OK", **(result.data or {})})
        if self.credentials.get("organization_id"):
            return await self.list_channels()
        return result

    async def list_organizations(self) -> ConnectorResult:
        query = """
        query JarvisBufferOrganizations {
          account {
            organizations {
              id
              name
            }
          }
        }
        """
        return await self._graphql(query)

    async def list_channels(self, organization_id: str | None = None) -> ConnectorResult:
        org_id = organization_id or self.credentials.get("organization_id")
        if not org_id:
            return ConnectorResult(ok=False, error="Buffer organization_id is required to list channels.")
        query = """
        query JarvisBufferChannels($input: ChannelsInput!) {
          channels(input: $input) {
            id
            name
            displayName
            service
            avatar
            isQueuePaused
          }
        }
        """
        return await self._graphql(query, {"input": {"organizationId": org_id}})

    async def get_channel(self, channel_id: str) -> ConnectorResult:
        if not channel_id:
            return ConnectorResult(ok=False, error="channel_id is required.")
        query = """
        query JarvisBufferChannel($input: ChannelInput!) {
          channel(input: $input) {
            id
            name
            displayName
            service
            avatar
            isQueuePaused
          }
        }
        """
        return await self._graphql(query, {"input": {"id": channel_id}})

    async def list_posts(
        self,
        channel_ids: list[str] | None = None,
        status: str = "scheduled",
        limit: int = 20,
        organization_id: str | None = None,
    ) -> ConnectorResult:
        org_id = organization_id or self.credentials.get("organization_id")
        if not org_id:
            return ConnectorResult(ok=False, error="Buffer organization_id is required to list posts.")
        query = """
        query JarvisBufferPosts($first: Int!, $input: PostsInput!) {
          posts(first: $first, input: $input) {
            edges {
              node {
                id
                text
                status
                dueAt
                channelId
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """
        variables = {
            "first": max(1, min(int(limit or 20), 100)),
            "input": _compact({
                "organizationId": org_id,
                "filter": {
                    "status": [status],
                    "channelIds": channel_ids or [],
                },
                "sort": [{"field": "dueAt", "direction": "asc"}],
            })
        }
        return await self._graphql(query, variables)

    async def get_scheduled_posts(
        self,
        channel_ids: list[str] | None = None,
        limit: int = 20,
        organization_id: str | None = None,
    ) -> ConnectorResult:
        return await self.list_posts(channel_ids=channel_ids, status="scheduled", limit=limit, organization_id=organization_id)

    async def get_sent_posts(
        self,
        channel_ids: list[str] | None = None,
        limit: int = 20,
        organization_id: str | None = None,
    ) -> ConnectorResult:
        return await self.list_posts(channel_ids=channel_ids, status="sent", limit=limit, organization_id=organization_id)

    def _validate_post(
        self,
        text: str,
        channel_ids: list[str],
        networks: list[str] | None = None,
        publish_at: str | None = None,
        scheduled: bool = False,
    ) -> ConnectorResult | None:
        if not text.strip():
            return ConnectorResult(ok=False, error="Post text is required.")
        if not channel_ids:
            return ConnectorResult(ok=False, error="At least one Buffer channel_id is required.")
        network_names = {str(n).lower() for n in (networks or [])}
        if ({"x", "twitter"} & network_names) and len(text) > 280:
            return ConnectorResult(ok=False, error="X/Twitter posts must be 280 characters or fewer.")
        if scheduled and not publish_at:
            return ConnectorResult(ok=False, error="publish_at is required for scheduled Buffer posts.")
        return None

    async def create_post(
        self,
        text: str,
        channel_ids: list[str],
        mode: str = "addToQueue",
        publish_at: str | None = None,
        media_urls: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> ConnectorResult:
        scheduled = mode == "customScheduled"
        validation = self._validate_post(text, channel_ids, networks=networks, publish_at=publish_at, scheduled=scheduled)
        if validation:
            return validation

        assets = []
        for url in media_urls or []:
            if not url:
                continue
            lower = url.lower()
            if lower.endswith((".mp4", ".mov", ".webm")):
                assets.append({"video": {"url": url}})
            else:
                assets.append({"image": {"url": url}})
        query = """
        mutation JarvisBufferCreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                text
                dueAt
                status
                channelId
              }
            }
            ... on MutationError {
              message
            }
          }
        }
        """
        created: list[dict] = []
        errors: list[str] = []
        for channel_id in channel_ids:
            payload = _compact({
                "channelId": channel_id,
                "text": text,
                "schedulingType": "automatic",
                "mode": mode,
                "dueAt": publish_at,
                "assets": assets,
            })
            result = await self._graphql(query, {"input": payload})
            if not result.ok:
                errors.append(f"{channel_id}: {result.error}")
                continue
            create_result = ((result.data or {}).get("createPost") or {})
            if create_result.get("message"):
                errors.append(f"{channel_id}: {create_result['message']}")
                continue
            created.append({"channel_id": channel_id, **(create_result.get("post") or {})})

        if errors and not created:
            return ConnectorResult(ok=False, error="; ".join(errors))
        return ConnectorResult(ok=True, data={"created": created, "errors": errors})

    async def schedule_post(
        self,
        text: str,
        channel_ids: list[str],
        publish_at: str,
        media_urls: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> ConnectorResult:
        return await self.create_post(
            text=text,
            channel_ids=channel_ids,
            mode="customScheduled",
            publish_at=publish_at,
            media_urls=media_urls,
            networks=networks,
        )

    async def add_to_queue(
        self,
        text: str,
        channel_ids: list[str],
        media_urls: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> ConnectorResult:
        return await self.create_post(
            text=text,
            channel_ids=channel_ids,
            mode="addToQueue",
            media_urls=media_urls,
            networks=networks,
        )
