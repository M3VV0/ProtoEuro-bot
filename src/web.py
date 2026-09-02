
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

import aiohttp

from utils import YOUTUBE_API_TOKEN

logger = logging.getLogger(__name__)
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


@dataclass(frozen=True)
class YouTubeVideo:
    title: str
    published_year: int
    view_count: int


def _youtube_watch_url(link: str) -> Optional[str]:
    parsed = urlsplit(link.strip())
    if parsed.scheme not in {"http", "https"}:
        logger.debug("Rejected YouTube URL without an HTTP/S scheme.")
        return None

    host = (parsed.hostname or "").lower()
    video_id: Optional[str] = None

    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        path_parts = parsed.path.strip("/").split("/")
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path_parts) == 2 and path_parts[0] in {"embed", "live", "shorts"}: # todo validate
            video_id = path_parts[1]

    if video_id is None or re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) is None:
        logger.debug("Could not extract a valid YouTube video ID from the URL.")
        return None

    return f"https://www.youtube.com/watch?v={video_id}"


def _parse_youtube_api_response(data: dict[str, Any]) -> Optional[YouTubeVideo]:
    items = data.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        logger.warning("YouTube API returned no matching public video.")
        return None

    snippet = items[0].get("snippet")
    statistics = items[0].get("statistics")
    if not isinstance(snippet, dict) or not isinstance(statistics, dict):
        logger.warning("YouTube API response did not include video metadata.")
        return None

    title = snippet.get("title")
    published_at = snippet.get("publishedAt")
    view_count = statistics.get("viewCount")
    if not isinstance(title, str) or not title.strip() or not isinstance(published_at, str):
        logger.warning("YouTube API response has an incomplete snippet.")
        return None

    year_match = re.match(r"(\d{4})-\d{2}-\d{2}", published_at)
    if year_match is None:
        logger.warning("YouTube API returned an unsupported publication date: %r.", published_at)
        return None

    try:
        parsed_view_count = int(view_count) # type: ignore
    except (TypeError, ValueError):
        logger.warning("YouTube API response has no usable view count.")
        return None

    return YouTubeVideo(
        title=title.strip(),
        published_year=int(year_match.group(1)),
        view_count=parsed_view_count,
    )


async def parse_youtube_video(
    link: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[YouTubeVideo]:
    """Fetch public metadata for a valid YouTube video URL."""
    watch_url = _youtube_watch_url(link)
    if watch_url is None:
        return None

    video_id = parse_qs(urlsplit(watch_url).query)["v"][0]
    owns_session = session is None
    client = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    try:
        logger.info("Requesting YouTube API metadata for %s", watch_url)
        async with client.get(
            YOUTUBE_VIDEOS_URL,
            params={
                "part": "snippet,statistics",
                "id": video_id,
                "key": YOUTUBE_API_TOKEN,
                "fields": "items(id,snippet(title,publishedAt),statistics(viewCount))",
            },
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200:
                error = data.get("error") if isinstance(data, dict) else None
                error_message = error.get("message") if isinstance(error, dict) else None
                logger.warning(
                    "YouTube API request returned HTTP %s for %s: %s",
                    response.status,
                    watch_url,
                    error_message or "no error message",
                )
                return None

            if not isinstance(data, dict):
                logger.warning("YouTube API returned a non-object JSON response.")
                return None
            video = _parse_youtube_api_response(data)
            if video is None:
                logger.warning("Could not parse YouTube API metadata for %s.", watch_url)
                return None

            logger.info("YouTube API metadata parsed successfully for %s", watch_url)
            return video
    except asyncio.TimeoutError:
        logger.warning("YouTube metadata request timed out for %s.", watch_url)
        return None
    except aiohttp.ClientError as error:
        logger.warning("YouTube metadata request failed for %s: %s", watch_url, error)
        return None
    except ValueError as error:
        logger.warning("YouTube API returned invalid JSON for %s: %s", watch_url, error)
        return None
    finally:
        if owns_session:
            await client.close()
