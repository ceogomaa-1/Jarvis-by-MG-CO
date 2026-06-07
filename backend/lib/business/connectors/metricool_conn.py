"""
Metricool social media connector.

Metricool API notes verified from official docs:
- Base URL: https://app.metricool.com/api
- Auth header: X-Mc-Auth
- Calls identify the user with userId and usually a brand/blog with blogId.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

BASE = "https://app.metricool.com/api"

NETWORK_SUBJECT_METRICS: dict[str, dict[str, list[str]]] = {
    "instagram": {
        "account": ["followers", "friends", "postsCount", "postsInteractions", "clicks_total"],
        "posts": ["count", "interactions", "engagement", "reach", "impressions", "likes", "comments", "saves", "shares"],
        "reels": ["count", "comments", "likes", "saved", "shares", "engagement", "impressions", "reach", "interactions", "videoviews"],
    },
    "facebook": {
        "account": ["likes", "pageFollows", "pageImpressions", "pageViews", "postsCount", "postsInteractions"],
        "posts": ["count", "interactions", "engagement", "impressionsunique", "impressions", "clicks", "comments", "shares", "reactions"],
        "reels": ["blue_reels_play_count", "post_impressions_unique", "post_video_likes_by_reaction_type", "post_video_social_actions", "engagement", "count"],
        "stories": ["storiesCount"],
    },
    "linkedin": {
        "account": ["followers", "paidFollowers", "companyImpressions", "deltaFollowers"],
        "posts": ["posts", "clicks", "likes", "comments", "shares", "engagement", "impressions", "interactions"],
        "stories": ["inStoriesEngagement", "inStoriesInteractions", "inStoriesImpressions", "inStoriesCliks", "inStories"],
    },
    "tiktok": {
        "account": ["video_views", "profile_views", "followers_count", "followers_delta_count", "likes", "comments", "shares"],
        "videos": ["videos", "views", "comments", "shares", "interactions", "likes", "reach", "engagement", "impressionSources", "averageVideoViews"],
    },
    "youtube": {
        "account": ["yttotalSubscribers", "ytestimatedRevenue", "ytVideos", "ytsubscribersGained", "ytsubscribersLost"],
        "videos": ["views", "interactions", "likes", "dislikes", "comments", "shares"],
    },
    "pinterest": {
        "account": ["followers", "following", "delta followers", "IMPRESSION", "ENGAGEMENT_RATE", "ENGAGEMENT", "PIN_CLICK", "OUTBOUND_CLICK", "SAVE"],
        "pins": ["impression", "save", "pin_click", "outbound_click", "video_mrc_view", "video_avg_watch_time", "video_v50_watch_time", "quartile_95_percent_view", "pins"],
        "posts": ["PINS"],
    },
    "twitter": {
        "account": ["twitterFollowers", "twFriends", "twTweets", "follows", "unfollows", "twEngagement", "twImpressions", "twInteractions", "twFavorites", "twRetweets", "twReplies", "twQuotes", "twProfileClicks", "twLinkClicks"],
    },
    "threads": {
        "account": ["followers_count", "delta_followers"],
        "posts": ["count", "views", "likes", "replies", "reposts", "engagement", "quotes", "interactions"],
    },
    "bluesky": {
        "account": ["followers_count", "follows_count", "count", "follow_event", "unfollow_event"],
        "posts": ["posts_count", "interactions", "likes", "replies", "reposts", "quotes"],
    },
    "gmb": {
        "business": ["business_impressions_maps", "business_impressions_search", "business_impressions_total", "business_direction_requests", "call_clicks", "website_clicks", "clicks_total", "business_conversations", "business_bookings", "business_food_orders", "business_actions_total"],
    },
    "webpage": {
        "account": ["PageViews", "SessionsCount", "Visitors", "DailyPosts", "DailyComments"],
    },
    "twitch": {
        "account": ["TotalFollowers", "TotalSubscribers", "TotalVideos", "DeltaFollowers", "TotalTier1", "TotalTier2", "TotalTier3", "TotalGifts", "TotalViews", "TotalDuration"],
    },
}

POST_ENDPOINTS = {
    "instagram": "/v2/analytics/posts/instagram",
    "instagram_reels": "/v2/analytics/reels/instagram",
    "instagram_stories": "/v2/analytics/stories/instagram",
    "facebook": "/v2/analytics/posts/facebook",
    "facebook_reels": "/v2/analytics/reels/facebook",
    "facebook_stories": "/v2/analytics/stories/facebook",
    "linkedin": "/v2/analytics/posts/linkedin",
    "tiktok": "/v2/analytics/posts/tiktok",
    "youtube": "/v2/analytics/posts/youtube",
    "pinterest": "/v2/analytics/posts/pinterest",
    "threads": "/v2/analytics/posts/threads",
    "bluesky": "/v2/analytics/posts/bluesky",
}


class MetricoolConnector(BaseConnector):
    CONNECTOR_TYPE = "metricool"
    DISPLAY_NAME = "Metricool"
    DESCRIPTION = "Read social analytics, find best posting times, and schedule posts after approval."
    DOCS_URL = "https://app.metricool.com/resources/apidocs/index.html"
    REQUIRED_FIELDS = {
        "access_token": {
            "label": "Metricool API access token",
            "type": "password",
            "placeholder": "X-Mc-Auth token",
            "secret": True,
            "required": True,
        },
        "user_id": {
            "label": "Metricool User ID",
            "type": "text",
            "placeholder": "1234567",
            "required": True,
        },
        "default_blog_id": {
            "label": "Default Brand / Blog ID (optional)",
            "type": "text",
            "placeholder": "1234567",
            "required": False,
        },
    }

    def _headers(self) -> dict:
        return {
            "X-Mc-Auth": (self.credentials.get("access_token") or self.credentials.get("userToken") or "").strip(),
            "Content-Type": "application/json",
        }

    def _user_id(self) -> str:
        return str(self.credentials.get("user_id") or self.credentials.get("userId") or "").strip()

    def _blog_id(self, blog_id: str | int | None = None) -> str:
        chosen = blog_id or self.credentials.get("default_blog_id") or self.credentials.get("blog_id") or self.credentials.get("blogId")
        return str(chosen or "").strip()

    def _params(self, blog_id: str | int | None = None, include_blog: bool = True, **extra) -> dict:
        params = {"userId": self._user_id(), "integrationSource": "Jarvis"}
        if include_blog:
            chosen_blog = self._blog_id(blog_id)
            if chosen_blog:
                params["blogId"] = chosen_blog
        for key, value in extra.items():
            if value is not None and value != "":
                params[key] = value
        return params

    async def _request(self, method: str, path: str, *, params: dict | None = None, json_body: Any = None, timeout: float = 20.0) -> ConnectorResult:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, f"{BASE}{path}", headers=self._headers(), params=params, json=json_body)
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:1000]}
                return ConnectorResult(ok=True, data=_trim_payload(data))
            if resp.status_code in (401, 403):
                return ConnectorResult(ok=False, error="Metricool access denied. Check the API token, user ID, brand ID, and plan access.")
            return ConnectorResult(ok=False, error=f"Metricool {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Metricool request failed: {e}")

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        return await self.list_brands()

    async def list_brands(self) -> ConnectorResult:
        res = await self._request("GET", "/admin/simpleProfiles", params=self._params(include_blog=False), timeout=10.0)
        if not res.ok:
            return res
        brands = _normalise_brands(res.data)
        return ConnectorResult(ok=True, data={"brands": brands, "count": len(brands)})

    async def get_profile(self, blog_id: str | int | None = None) -> ConnectorResult:
        brands_res = await self.list_brands()
        if not brands_res.ok:
            return brands_res
        chosen = self._blog_id(blog_id)
        brands = brands_res.data.get("brands", [])
        brand = next((b for b in brands if str(b.get("blog_id")) == chosen), None) if chosen else (brands[0] if brands else None)
        settings = await self._request("GET", "/admin/blog/profiles", params=self._params(blog_id), timeout=10.0)
        return ConnectorResult(ok=True, data={
            "brand": brand,
            "settings": settings.data if settings.ok else None,
            "settings_error": None if settings.ok else settings.error,
        })

    async def get_recent_posts(
        self,
        blog_id: str | int | None = None,
        network: str | None = None,
        limit: int = 20,
        start: str | None = None,
        end: str | None = None,
        timezone_name: str = "America/Toronto",
    ) -> ConnectorResult:
        start, end = _default_window(start, end, days=30)
        networks = [network.lower()] if network else ["instagram", "facebook", "linkedin", "tiktok", "youtube", "pinterest"]
        out = {}
        for net in networks:
            path = POST_ENDPOINTS.get(net)
            if not path:
                out[net] = {"error": f"Unsupported recent-post network: {net}"}
                continue
            res = await self._request(
                "GET",
                path,
                params=self._params(
                    blog_id,
                    **{
                        "from": f"{start}T00:00:00",
                        "to": f"{end}T23:59:59",
                        "timezone": timezone_name,
                    },
                ),
            )
            if res.ok:
                out[net] = _limit_items(res.data, limit)
            else:
                out[net] = {"error": res.error}
        return ConnectorResult(ok=True, data={"posts": out, "start": start, "end": end})

    async def get_scheduled_posts(
        self,
        blog_id: str | int | None = None,
        start: str | None = None,
        end: str | None = None,
        timezone_name: str = "America/Toronto",
        extended_range: bool = False,
    ) -> ConnectorResult:
        start, end = _default_window(start, end, days=30, future=True)
        return await self._request(
            "GET",
            "/v2/scheduler/posts",
            params=self._params(
                blog_id,
                start=f"{start}T00:00:00",
                end=f"{end}T23:59:59",
                timezone=timezone_name,
                extendedRange=str(bool(extended_range)).lower(),
            ),
        )

    async def get_available_metrics(self, blog_id: str | int | None = None, network: str | None = None) -> ConnectorResult:
        del blog_id
        if network:
            net = network.lower()
            if net not in NETWORK_SUBJECT_METRICS:
                return ConnectorResult(ok=False, error=f"Unsupported network '{network}'. Available: {', '.join(NETWORK_SUBJECT_METRICS)}")
            return ConnectorResult(ok=True, data={"network": net, "metrics": NETWORK_SUBJECT_METRICS[net]})
        return ConnectorResult(ok=True, data={"metrics_by_network": NETWORK_SUBJECT_METRICS})

    async def get_metrics(
        self,
        blog_id: str | int | None = None,
        network: str | None = None,
        metric: str | list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        timezone_name: str = "America/Toronto",
        subject: str | None = None,
    ) -> ConnectorResult:
        if not network:
            return ConnectorResult(ok=False, error="network is required for Metricool analytics.")
        net = network.lower()
        if net not in NETWORK_SUBJECT_METRICS:
            return ConnectorResult(ok=False, error=f"Unsupported network '{network}'. Available: {', '.join(NETWORK_SUBJECT_METRICS)}")
        start, end = _default_window(start, end, days=30)
        metrics = metric if isinstance(metric, list) else [metric] if metric else _default_metrics_for(net)
        results = {}
        for met in metrics:
            subj = subject or _subject_for_metric(net, met)
            if not subj:
                results[met] = {"error": f"Metric '{met}' is not available for {net}."}
                continue
            params = self._params(
                blog_id,
                **{
                    "from": f"{start}T00:00:00",
                    "to": f"{end}T23:59:59",
                    "timezone": timezone_name,
                    "metric": met,
                    "network": net,
                },
            )
            if net == "linkedin":
                params["metricType"] = subj
            else:
                params["subject"] = subj
            if net == "youtube" and subj == "videos":
                params["postsType"] = "publishedInRange"
            res = await self._request("GET", "/v2/analytics/timelines", params=params)
            results[f"{subj}:{met}"] = res.data if res.ok else {"error": res.error}
        return ConnectorResult(ok=True, data={"network": net, "start": start, "end": end, "results": results})

    async def get_best_time_to_post(
        self,
        blog_id: str | int | None = None,
        network: str | None = None,
        start: str | None = None,
        end: str | None = None,
        timezone_name: str = "America/Toronto",
    ) -> ConnectorResult:
        if not network:
            return ConnectorResult(ok=False, error="network is required for best-time lookup.")
        start, end = _default_window(start, end, days=7, future=True)
        provider = _normalise_network(network)
        res = await self._request(
            "GET",
            f"/v2/scheduler/besttimes/{provider}",
            params=self._params(blog_id, start=f"{start}T00:00:00", end=f"{end}T23:59:59", timezone=timezone_name),
        )
        if res.ok and isinstance(res.data, dict) and isinstance(res.data.get("data"), list):
            days = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday", 6: "Friday", 7: "Saturday"}
            for entry in res.data["data"]:
                if isinstance(entry, dict):
                    entry["dayOfWeekName"] = days.get(entry.get("dayOfWeek"), "Unknown")
        return res

    async def schedule_post(
        self,
        blog_id: str | int | None = None,
        text: str = "",
        networks: list[str] | None = None,
        media_urls: list[str] | None = None,
        publish_at: str | None = None,
        timezone_name: str = "America/Toronto",
        info: dict | None = None,
        **extra,
    ) -> ConnectorResult:
        networks = [_normalise_network(n) for n in (networks or [])]
        if not networks and info:
            networks = [p.get("network") for p in info.get("providers", []) if p.get("network")]
        if not networks:
            return ConnectorResult(ok=False, error="At least one network is required.")
        body = info.copy() if isinstance(info, dict) else _schedule_body(text, networks, publish_at, timezone_name, media_urls or [])
        body.update({k: v for k, v in extra.items() if v is not None and k not in {"blog_id", "timezone_name"}})
        validation = _validate_post_body(body)
        if validation:
            return ConnectorResult(ok=False, error=validation)
        return await self._request("POST", "/v2/scheduler/posts", params=self._params(blog_id), json_body=body, timeout=30.0)

    async def update_scheduled_post(
        self,
        blog_id: str | int | None = None,
        post_id: str = "",
        changes: dict | None = None,
        info: dict | None = None,
        **extra,
    ) -> ConnectorResult:
        if not post_id:
            post_id = str(extra.get("id") or "")
        if not post_id:
            return ConnectorResult(ok=False, error="post_id is required.")
        body = info.copy() if isinstance(info, dict) else {}
        if changes:
            body.update(changes)
        body.update({k: v for k, v in extra.items() if v is not None and k not in {"blog_id", "post_id", "id"}})
        validation = _validate_post_body(body)
        if validation:
            return ConnectorResult(ok=False, error=validation)
        return await self._request("PUT", f"/v2/scheduler/posts/{post_id}", params=self._params(blog_id), json_body=body, timeout=30.0)


def _trim_payload(data: Any, max_items: int = 50) -> Any:
    if isinstance(data, list):
        return [_trim_payload(x, max_items) for x in data[:max_items]]
    if isinstance(data, dict):
        return {k: _trim_payload(v, max_items) for k, v in data.items() if k not in {"accessToken", "token", "userToken"}}
    return data


def _normalise_brands(data: Any) -> list[dict]:
    rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
    brands = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blog_id = row.get("blogId") or row.get("id") or row.get("blog_id")
        brands.append({
            "blog_id": blog_id,
            "name": row.get("label") or row.get("name") or row.get("blogName") or str(blog_id),
            "timezone": row.get("timezone") or row.get("timeZone"),
            "raw": _trim_payload(row),
        })
    return brands


def _default_window(start: str | None, end: str | None, *, days: int, future: bool = False) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    if future:
        return start or today.isoformat(), end or (today + timedelta(days=days)).isoformat()
    return start or (today - timedelta(days=days)).isoformat(), end or today.isoformat()


def _limit_items(data: Any, limit: int) -> Any:
    if isinstance(data, list):
        return data[: max(1, min(limit, 100))]
    if isinstance(data, dict):
        for key in ("data", "posts", "items"):
            if isinstance(data.get(key), list):
                data = data.copy()
                data[key] = data[key][: max(1, min(limit, 100))]
                return data
    return data


def _normalise_network(network: str) -> str:
    net = (network or "").lower().strip()
    return "twitter" if net in {"x", "twitter/x"} else net


def _default_metrics_for(network: str) -> list[str]:
    subjects = NETWORK_SUBJECT_METRICS.get(network, {})
    if "account" in subjects:
        return subjects["account"][:3]
    first = next(iter(subjects.values()), [])
    return first[:3]


def _subject_for_metric(network: str, metric: str) -> str | None:
    for subject, metrics in NETWORK_SUBJECT_METRICS.get(network, {}).items():
        if metric in metrics:
            return subject
    return None


def _schedule_body(text: str, networks: list[str], publish_at: str | None, timezone_name: str, media_urls: list[str]) -> dict:
    when = publish_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "")
    body = {
        "autoPublish": True,
        "descendants": [],
        "draft": False,
        "firstCommentText": "",
        "hasNotReadNotes": False,
        "media": [{"url": url} for url in media_urls],
        "mediaAltText": [],
        "providers": [{"network": n} for n in networks],
        "publicationDate": {"dateTime": when, "timezone": timezone_name},
        "shortener": False,
        "smartLinkData": {"ids": []},
        "text": text,
    }
    for net in networks:
        if net == "twitter":
            body["twitterData"] = {"tags": []}
        elif net == "facebook":
            body["facebookData"] = {"type": "POST", "title": ""}
        elif net == "instagram":
            body["instagramData"] = {"type": "POST", "collaborators": [], "showReelOnFeed": True}
        elif net == "linkedin":
            body["linkedinData"] = {"previewIncluded": True, "type": "post"}
        elif net == "pinterest":
            body["pinterestData"] = {}
        elif net == "youtube":
            body["youtubeData"] = {"type": "video", "privacy": "public"}
        elif net == "tiktok":
            body["tiktokData"] = {"disableComment": False, "disableDuet": False, "disableStitch": False, "privacyOption": "PUBLIC_TO_EVERYONE"}
        elif net == "bluesky":
            body["blueskyData"] = {"postLanguages": []}
        elif net == "threads":
            body["threadsData"] = {"allowedCountryCodes": []}
    return body


def _validate_post_body(body: dict) -> str | None:
    text = body.get("text", "") or ""
    networks = [p.get("network") for p in body.get("providers", []) if isinstance(p, dict)]
    if "twitter" in networks and len(text) > 280:
        return "The text exceeds the 280-character limit allowed on X. Please edit it."
    if "bluesky" in networks and len(text) > 300:
        return "The text exceeds the 300-character limit allowed on Bluesky. Please edit it."
    return None
