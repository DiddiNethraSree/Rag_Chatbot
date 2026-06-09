import sys
import re
import json
import subprocess
import logging
from youtube_transcript_api import YouTubeTranscriptApi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YTDLP_BASE_ARGS = [
    sys.executable,
    "-m",
    "yt_dlp",
    "--dump-json",
    "--no-download",
    "--quiet",
    "--no-warnings",
]


def normalize_instagram_url(url: str) -> str:
    """Normalize Instagram reel/post URLs to the /reel/SHORTCODE/ form."""
    url = url.strip().split("?")[0].split("#")[0].rstrip("/")
    match = re.search(
        r"(?:instagram\.com|instagr\.am)/(?:reels?|p|tv)/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE,
    )
    if match:
        return f"https://www.instagram.com/reel/{match.group(1)}/"
    return url


def extract_youtube_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"youtube\.com/shorts/([0-9A-Za-z_-]{11})",
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(
        f"Invalid YouTube URL: {url}. Must contain video ID or be from youtube.com or youtu.be"
    )


def _run_ytdlp(url: str, timeout: int = 45) -> dict:
    """Run yt-dlp and return parsed JSON metadata."""
    cmd = YTDLP_BASE_ARGS + [url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:200] or "yt-dlp failed")
    return json.loads(result.stdout)


def _safe_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _extract_hashtags(text: str) -> list:
    if not text:
        return []
    return list(dict.fromkeys(re.findall(r"#(\w+)", text)))[:10]


def _compute_engagement(views: int, likes: int, comments: int, platform: str) -> tuple:
    """
    Return (engagement_rate, engagement_note).
    Instagram often hides view counts — use likes/comments in that case.
    """
    if views > 0:
        rate = round((likes + comments) / views * 100, 4)
        return rate, None

    if platform == "instagram" and (likes > 0 or comments > 0):
        note = f"{likes:,} likes, {comments:,} comments (Instagram does not expose view counts)"
        return 0.0, note

    if likes > 0 or comments > 0:
        return 0.0, f"{likes:,} likes, {comments:,} comments (views unavailable)"

    return 0.0, "Engagement data unavailable for this video"


def _parse_ytdlp_meta(meta: dict, platform: str) -> dict:
    """Map yt-dlp JSON fields into our normalized metadata dict."""
    description = (meta.get("description") or "")[:500]
    title = meta.get("title") or description.split("\n")[0][:100] or "Unknown"
    if title.startswith("Video by "):
        title = description.split("\n")[0][:100] or title

    views = _safe_int(meta.get("view_count") or meta.get("play_count"))
    likes = _safe_int(meta.get("like_count"))
    comments = _safe_int(meta.get("comment_count"))
    followers = _safe_int(meta.get("channel_follower_count"))

    engagement_rate, engagement_note = _compute_engagement(views, likes, comments, platform)
    hashtags = meta.get("tags") or _extract_hashtags(description)

    if platform == "instagram":
        creator = meta.get("channel") or meta.get("uploader") or "Unknown"
    else:
        creator = meta.get("uploader") or meta.get("channel") or "Unknown"
    creator = str(creator).lstrip("@")

    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "followers": followers,
        "duration": _safe_int(meta.get("duration")),
        "title": title[:200],
        "creator": creator,
        "description": description,
        "hashtags": hashtags[:10] if isinstance(hashtags, list) else [],
        "upload_date": meta.get("upload_date", "Unknown"),
        "video_id": meta.get("id", "unknown"),
        "engagement_rate": engagement_rate,
        "engagement_note": engagement_note,
    }


def get_youtube_data(url: str) -> dict:
    """Fetch YouTube video data with comprehensive error handling."""
    try:
        video_id = extract_youtube_id(url)
    except ValueError as e:
        logger.warning(f"YouTube URL extraction failed: {str(e)}")
        return _empty_video("youtube", url, str(e), "⚠️ Invalid YouTube URL")

    transcript_text = ""
    first_5s = ""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join(t["text"] for t in transcript_list)
        first_5s = " ".join(t["text"] for t in transcript_list if t["start"] < 5)
        logger.info(f"✓ Transcript fetched for YouTube video {video_id}")
    except Exception as e:
        logger.warning(f"Transcript fetch failed for {video_id}: {str(e)}")

    metadata = {
        "views": 0, "likes": 0, "comments": 0, "followers": 0,
        "duration": 0, "title": "Unknown", "creator": "Unknown",
        "description": "", "hashtags": [], "upload_date": "Unknown",
        "engagement_note": None,
    }

    try:
        meta = _run_ytdlp(f"https://www.youtube.com/watch?v={video_id}")
        parsed = _parse_ytdlp_meta(meta, "youtube")
        metadata.update(parsed)
        logger.info(f"✓ Metadata fetched for YouTube video: {metadata['title']}")
    except subprocess.TimeoutExpired:
        metadata["error"] = "Video metadata fetch timeout. Please check your internet connection."
    except Exception as e:
        logger.warning(f"Metadata fetch error for {video_id}: {str(e)}")
        metadata["error"] = f"Video metadata partially unavailable: {str(e)[:50]}"

    if not transcript_text:
        transcript_text = metadata["description"] or "Transcript not available for this video."
    if not first_5s:
        first_5s = metadata["description"][:200] if metadata["description"] else "No hook data available"

    return {
        "platform": "youtube",
        "url": url,
        "video_id": video_id,
        "title": metadata["title"],
        "creator": metadata["creator"],
        "followers": metadata["followers"],
        "views": metadata["views"],
        "likes": metadata["likes"],
        "comments": metadata["comments"],
        "hashtags": metadata["hashtags"],
        "upload_date": metadata["upload_date"],
        "duration": metadata["duration"],
        "description": metadata["description"],
        "engagement_rate": metadata.get("engagement_rate", 0.0),
        "engagement_note": metadata.get("engagement_note"),
        "transcript": transcript_text,
        "hook_first_5s": first_5s,
        "error": metadata.get("error"),
    }


def get_instagram_data(url: str) -> dict:
    """Fetch Instagram reel metadata using yt-dlp (requires recent yt-dlp version)."""
    if not ("instagram.com" in url or "instagr.am" in url):
        return _empty_video("instagram", url, "Invalid Instagram URL", "⚠️ Invalid Instagram URL")

    normalized = normalize_instagram_url(url)
    metadata = {
        "views": 0, "likes": 0, "comments": 0, "followers": 0,
        "duration": 0, "title": "Instagram Reel", "creator": "Unknown",
        "description": "", "hashtags": [], "upload_date": "Unknown",
        "video_id": normalized.rstrip("/").split("/")[-1],
        "engagement_note": None,
    }

    try:
        meta = _run_ytdlp(normalized, timeout=60)
        parsed = _parse_ytdlp_meta(meta, "instagram")
        metadata.update(parsed)
        logger.info(
            f"✓ Instagram reel fetched: {metadata['creator']} — "
            f"{metadata['likes']:,} likes, {metadata['comments']:,} comments"
        )
    except subprocess.TimeoutExpired:
        metadata["error"] = "Instagram metadata fetch timeout. Please check your internet connection."
        metadata["data_note"] = "Could not fetch Instagram data in time. Try again or use a public reel URL."
    except Exception as e:
        logger.warning(f"Instagram metadata fetch error: {str(e)}")
        metadata["error"] = f"Instagram fetch failed: {str(e)[:80]}"
        metadata["data_note"] = (
            "Instagram blocked metadata access. Ensure the reel is public and run: "
            "pip install -U yt-dlp"
        )

    transcript_text = metadata["description"] or "Caption not available for this Instagram reel."
    hook = transcript_text[:200] if transcript_text else "No caption available"

    return {
        "platform": "instagram",
        "url": normalized,
        "video_id": metadata["video_id"],
        "title": metadata["title"],
        "creator": metadata["creator"],
        "followers": metadata["followers"],
        "views": metadata["views"],
        "likes": metadata["likes"],
        "comments": metadata["comments"],
        "hashtags": metadata["hashtags"],
        "upload_date": metadata["upload_date"],
        "duration": metadata["duration"],
        "description": metadata["description"],
        "engagement_rate": metadata.get("engagement_rate", 0.0),
        "engagement_note": metadata.get("engagement_note"),
        "data_note": metadata.get("data_note"),
        "transcript": transcript_text,
        "hook_first_5s": hook,
        "error": metadata.get("error"),
    }


def _empty_video(platform: str, url: str, error: str, title: str) -> dict:
    return {
        "platform": platform,
        "url": url,
        "video_id": "unknown",
        "title": title,
        "creator": "Unknown",
        "followers": 0,
        "views": 0,
        "likes": 0,
        "comments": 0,
        "hashtags": [],
        "upload_date": "Unknown",
        "duration": 0,
        "description": "",
        "engagement_rate": 0.0,
        "engagement_note": "No data available",
        "transcript": f"Unable to fetch — {error}",
        "hook_first_5s": "N/A",
        "error": error,
    }


def fetch_video_data(url: str, label: str) -> dict:
    """Auto-detect platform and fetch data with fallbacks."""
    try:
        if "instagram.com" in url or "instagr.am" in url:
            data = get_instagram_data(url)
        else:
            data = get_youtube_data(url)
        data["label"] = label
        return data
    except Exception as e:
        logger.error(f"Unexpected error fetching video {label}: {str(e)}")
        data = _empty_video("unknown", url, str(e), "⚠️ Error Loading Video")
        data["label"] = label
        return data
