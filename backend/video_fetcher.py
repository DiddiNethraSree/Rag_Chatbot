import sys
import re
import json
import subprocess
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_youtube_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    
    # If no pattern matches, raise a clear error
    raise ValueError(f"Invalid YouTube URL: {url}. Must contain video ID or be from youtube.com or youtu.be")


def get_youtube_data(url: str) -> dict:
    """Fetch YouTube video data with comprehensive error handling."""
    try:
        video_id = extract_youtube_id(url)
    except ValueError as e:
        logger.warning(f"YouTube URL extraction failed: {str(e)}")
        return {
            "platform": "youtube",
            "url": url,
            "video_id": "unknown",
            "title": "⚠️ Invalid YouTube URL",
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
            "transcript": "Unable to fetch - Invalid URL provided",
            "hook_first_5s": "Invalid URL",
            "error": str(e),
        }

    # Get transcript
    transcript_text = ""
    first_5s = ""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join([t["text"] for t in transcript_list])
        first_5s = " ".join([t["text"] for t in transcript_list if t["start"] < 5])
        logger.info(f"✓ Transcript fetched for YouTube video {video_id}")
    except Exception as e:
        logger.warning(f"Transcript fetch failed for {video_id}: {str(e)}")
        # Transcript will fall back to description later

    # Get metadata via yt-dlp
    metadata = {
        "views": 0,
        "likes": 0,
        "comments": 0,
        "followers": 0,
        "duration": 0,
        "title": "Unknown",
        "creator": "Unknown",
        "description": "",
        "hashtags": [],
        "upload_date": "Unknown",
    }

    try:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-json",
            "--no-download",
            "--quiet",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Check for subprocess errors
        if result.returncode != 0:
            logger.warning(f"yt-dlp returned code {result.returncode}: {result.stderr}")
            raise Exception(f"yt-dlp error: {result.stderr[:100]}")
        
        # Parse JSON safely
        try:
            meta = json.loads(result.stdout)
        except json.JSONDecodeError as je:
            logger.warning(f"Invalid JSON from yt-dlp: {str(je)}")
            raise Exception(f"Invalid video metadata response: {str(je)[:100]}")
        
        # Extract metadata with safe defaults
        metadata["views"] = max(0, meta.get("view_count", 0) or 0)
        metadata["likes"] = max(0, meta.get("like_count", 0) or 0)
        metadata["comments"] = max(0, meta.get("comment_count", 0) or 0)
        metadata["followers"] = max(0, meta.get("channel_follower_count", 0) or 0)
        metadata["hashtags"] = meta.get("tags", [])[:10] if meta.get("tags") else []
        metadata["upload_date"] = meta.get("upload_date", "Unknown")
        metadata["duration"] = max(0, meta.get("duration", 0) or 0)
        metadata["title"] = meta.get("title", "Unknown")[:200]
        metadata["description"] = meta.get("description", "")[:500]
        metadata["creator"] = meta.get("uploader", "Unknown")
        
        logger.info(f"✓ Metadata fetched for YouTube video: {metadata['title']}")
    
    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp timeout for video {video_id}")
        metadata["error"] = "Video metadata fetch timeout. Please check your internet connection."
    except Exception as e:
        logger.warning(f"Metadata fetch error for {video_id}: {str(e)}")
        metadata["error"] = f"Video metadata partially unavailable: {str(e)[:50]}"

    # Calculate engagement rate
    engagement_rate = 0.0
    if metadata["views"] > 0:
        engagement_rate = round((metadata["likes"] + metadata["comments"]) / metadata["views"] * 100, 4)

    # Fallback for transcript
    if not transcript_text:
        transcript_text = metadata["description"] if metadata["description"] else "Transcript not available for this video."
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
        "engagement_rate": engagement_rate,
        "transcript": transcript_text,
        "hook_first_5s": first_5s,
    }


def get_instagram_data(url: str) -> dict:
    """Fetch Instagram reel metadata and transcript using yt-dlp with error handling."""
    
    # Validate Instagram URL
    if not ("instagram.com" in url or "instagr.am" in url):
        logger.warning(f"Invalid Instagram URL: {url}")
        return {
            "platform": "instagram",
            "url": url,
            "video_id": "unknown",
            "title": "⚠️ Invalid Instagram URL",
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
            "transcript": "Unable to fetch - Invalid Instagram URL provided",
            "hook_first_5s": "Invalid URL",
            "error": "Invalid Instagram URL",
        }

    metadata = {
        "views": 0,
        "likes": 0,
        "comments": 0,
        "followers": 0,
        "duration": 0,
        "title": "Instagram Reel",
        "creator": "Unknown",
        "description": "",
        "hashtags": [],
        "upload_date": "Unknown",
        "video_id": "insta_video",
    }

    try:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-json",
            "--no-download",
            "--quiet",
            url,
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Check for subprocess errors
        if result.returncode != 0:
            logger.warning(f"yt-dlp returned code {result.returncode} for Instagram: {result.stderr}")
            raise Exception(f"yt-dlp error: {result.stderr[:100]}")
        
        # Parse JSON safely
        try:
            meta = json.loads(result.stdout)
        except json.JSONDecodeError as je:
            logger.warning(f"Invalid JSON from yt-dlp for Instagram: {str(je)}")
            raise Exception(f"Invalid metadata response: {str(je)[:100]}")
        
        # Extract metadata with safe defaults
        metadata["views"] = max(0, meta.get("view_count", 0) or 0)
        metadata["likes"] = max(0, meta.get("like_count", 0) or 0)
        metadata["comments"] = max(0, meta.get("comment_count", 0) or 0)
        metadata["followers"] = max(0, meta.get("channel_follower_count", 0) or 0)
        metadata["hashtags"] = meta.get("tags", [])[:10] if meta.get("tags") else []
        metadata["upload_date"] = meta.get("upload_date", "Unknown")
        metadata["duration"] = max(0, meta.get("duration", 0) or 0)
        metadata["title"] = meta.get("title", meta.get("description", "Instagram Reel"))[:100]
        metadata["description"] = meta.get("description", "")[:500]
        metadata["creator"] = meta.get("uploader", meta.get("channel", "Unknown"))
        metadata["video_id"] = meta.get("id", url.split("/")[-2] if "/" in url else "insta")
        
        logger.info(f"✓ Metadata fetched for Instagram reel: {metadata['creator']}")
    
    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp timeout for Instagram reel")
        metadata["error"] = "Instagram metadata fetch timeout. Please check your internet connection."
    except Exception as e:
        logger.warning(f"Instagram metadata fetch error: {str(e)}")
        metadata["error"] = f"Instagram metadata partially unavailable: {str(e)[:50]}"

    # Calculate engagement rate
    engagement_rate = 0.0
    if metadata["views"] > 0:
        engagement_rate = round((metadata["likes"] + metadata["comments"]) / metadata["views"] * 100, 4)

    # Instagram rarely has auto-captions; use description as transcript fallback
    transcript_text = metadata["description"] if metadata["description"] else "Transcript not available for this Instagram reel."

    return {
        "platform": "instagram",
        "url": url,
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
        "engagement_rate": engagement_rate,
        "transcript": transcript_text,
        "hook_first_5s": transcript_text[:200],
    }


def fetch_video_data(url: str, label: str) -> dict:
    """Auto-detect platform and fetch data with fallbacks."""
    try:
        if "instagram.com" in url or "instagr.am" in url:
            data = get_instagram_data(url)
        else:
            data = get_youtube_data(url)
        
        data["label"] = label  # "A" or "B"
        return data
    
    except Exception as e:
        logger.error(f"Unexpected error fetching video {label}: {str(e)}")
        # Return minimal safe data structure
        return {
            "platform": "unknown",
            "url": url,
            "label": label,
            "video_id": "error",
            "title": "⚠️ Error Loading Video",
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
            "transcript": f"Error: Unable to fetch video data. {str(e)[:100]}",
            "hook_first_5s": "Error",
            "error": str(e),
        }
