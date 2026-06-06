import sys
import re
import json
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


def extract_youtube_id(url: str) -> str:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract YouTube ID from: {url}")


def get_youtube_data(url: str) -> dict:
    video_id = extract_youtube_id(url)

    # Get transcript
    transcript_text = ""
    first_5s = ""
    try:
        transcript_list = YouTubeTranscriptApi().fetch(video_id)
        transcript_text = " ".join([t.text for t in transcript_list])
        first_5s = " ".join([t.text for t in transcript_list if t.start < 5])
    except Exception as e:
        # Fail silently here; we will fall back to the description once metadata is loaded
        pass

    # Get metadata via yt-dlp
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-json",
        "--no-download",
        "--quiet",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        meta = json.loads(result.stdout)
        views = meta.get("view_count", 0) or 0
        likes = meta.get("like_count", 0) or 0
        comments = meta.get("comment_count", 0) or 0
        creator = meta.get("uploader", "Unknown")
        followers = meta.get("channel_follower_count", 0) or 0
        hashtags = meta.get("tags", [])[:10]
        upload_date = meta.get("upload_date", "Unknown")
        duration = meta.get("duration", 0)
        title = meta.get("title", "Unknown")
        description = meta.get("description", "")[:500]
    except Exception as e:
        views = likes = comments = followers = duration = 0
        creator = "Unknown"
        hashtags = []
        upload_date = "Unknown"
        title = "Unknown"
        description = ""

    engagement_rate = round((likes + comments) / views * 100, 4) if views > 0 else 0.0

    if not transcript_text:
        transcript_text = description if description else "Transcript not available."
    if not first_5s:
        first_5s = description[:200] if description else ""

    return {
        "platform": "youtube",
        "url": url,
        "video_id": video_id,
        "title": title,
        "creator": creator,
        "followers": followers,
        "views": views,
        "likes": likes,
        "comments": comments,
        "hashtags": hashtags,
        "upload_date": upload_date,
        "duration": duration,
        "description": description,
        "engagement_rate": engagement_rate,
        "transcript": transcript_text,
        "hook_first_5s": first_5s,
    }


def get_instagram_data(url: str) -> dict:
    """Fetch Instagram reel metadata and transcript using yt-dlp."""
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-json",
        "--no-download",
        "--quiet",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        meta = json.loads(result.stdout)
        views = meta.get("view_count", 0) or 0
        likes = meta.get("like_count", 0) or 0
        comments = meta.get("comment_count", 0) or 0
        creator = meta.get("uploader", meta.get("channel", "Unknown"))
        followers = meta.get("channel_follower_count", 0) or 0
        hashtags = meta.get("tags", [])[:10]
        upload_date = meta.get("upload_date", "Unknown")
        duration = meta.get("duration", 0) or 0
        title = meta.get("title", meta.get("description", "Instagram Reel"))[:100]
        description = meta.get("description", "")[:500]
        video_id = meta.get("id", url.split("/")[-2] if "/" in url else "insta")
    except Exception as e:
        views = likes = comments = followers = duration = 0
        creator = "Unknown"
        hashtags = []
        upload_date = "Unknown"
        title = "Instagram Reel"
        description = ""
        video_id = "insta_video"

    engagement_rate = round((likes + comments) / views * 100, 4) if views > 0 else 0.0

    # Instagram rarely has auto-captions; use description as transcript fallback
    transcript_text = description if description else "Transcript not available for this Instagram reel."

    return {
        "platform": "instagram",
        "url": url,
        "video_id": video_id,
        "title": title,
        "creator": creator,
        "followers": followers,
        "views": views,
        "likes": likes,
        "comments": comments,
        "hashtags": hashtags,
        "upload_date": upload_date,
        "duration": duration,
        "description": description,
        "engagement_rate": engagement_rate,
        "transcript": transcript_text,
        "hook_first_5s": transcript_text[:200],
    }


def fetch_video_data(url: str, label: str) -> dict:
    """Auto-detect platform and fetch data."""
    if "instagram.com" in url or "instagr.am" in url:
        data = get_instagram_data(url)
    else:
        data = get_youtube_data(url)
    data["label"] = label  # "A" or "B"
    return data
