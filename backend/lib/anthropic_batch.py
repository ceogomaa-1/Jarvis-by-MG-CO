"""Small HTTP wrapper for Anthropic Message Batches.

The Anthropic SDK version is intentionally unconstrained in requirements.txt, so this module
uses the stable HTTP API directly instead of assuming batch helpers exist in the installed SDK.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_VERSION = "2023-06-01"
BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"


class AnthropicBatchError(RuntimeError):
    """Raised when the Batches API rejects or cannot return a batch."""


class AnthropicBatchTimeout(AnthropicBatchError):
    """Raised when a created batch is still processing after the local wait budget."""


def _headers(beta_headers: list[str] | None = None) -> dict[str, str]:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    if beta_headers:
        headers["anthropic-beta"] = ",".join(beta_headers)
    return headers


async def create_message_batch(
    requests: list[dict[str, Any]],
    *,
    beta_headers: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Create an Anthropic Message Batch and return the API response."""
    if not ANTHROPIC_API_KEY:
        raise AnthropicBatchError("ANTHROPIC_API_KEY is not configured")
    if not requests:
        raise AnthropicBatchError("Cannot create an empty message batch")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            BATCHES_URL,
            headers=_headers(beta_headers),
            json={"requests": requests},
            timeout=timeout,
        )
    if resp.status_code not in (200, 201):
        raise AnthropicBatchError(f"Batch create failed: API {resp.status_code}: {resp.text[:500]}")
    return resp.json()


async def retrieve_message_batch(
    batch_id: str,
    *,
    beta_headers: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BATCHES_URL}/{batch_id}",
            headers=_headers(beta_headers),
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise AnthropicBatchError(f"Batch retrieve failed: API {resp.status_code}: {resp.text[:500]}")
    return resp.json()


async def get_message_batch_results(
    batch_id: str,
    *,
    beta_headers: list[str] | None = None,
    timeout: float = 120.0,
) -> list[dict[str, Any]]:
    """Download JSONL results for a completed batch."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BATCHES_URL}/{batch_id}/results",
            headers=_headers(beta_headers),
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise AnthropicBatchError(f"Batch results failed: API {resp.status_code}: {resp.text[:500]}")

    results: list[dict[str, Any]] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results


async def run_message_batch(
    requests: list[dict[str, Any]],
    *,
    beta_headers: list[str] | None = None,
    max_wait_seconds: float = 3600.0,
    initial_poll_seconds: float = 5.0,
    max_poll_seconds: float = 60.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create a batch, poll until it ends, then return ``(batch, results)``.

    This is intentionally bounded by a local wait budget. The Anthropic service can keep
    processing for up to 24 hours, but a web worker should not block forever.
    """
    batch = await create_message_batch(requests, beta_headers=beta_headers)
    batch_id = batch.get("id")
    if not batch_id:
        raise AnthropicBatchError("Batch create response did not include an id")

    deadline = asyncio.get_running_loop().time() + max_wait_seconds
    poll_seconds = max(1.0, initial_poll_seconds)
    while batch.get("processing_status") != "ended":
        if asyncio.get_running_loop().time() >= deadline:
            raise AnthropicBatchTimeout(
                f"Batch {batch_id} is still {batch.get('processing_status', 'processing')} "
                f"after {int(max_wait_seconds)}s"
            )
        await asyncio.sleep(poll_seconds)
        poll_seconds = min(max_poll_seconds, poll_seconds * 1.5)
        batch = await retrieve_message_batch(batch_id, beta_headers=beta_headers)

    return batch, await get_message_batch_results(batch_id, beta_headers=beta_headers)
