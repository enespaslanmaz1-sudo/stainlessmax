import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Windows 11 optimizations
if os.name == 'nt':
    # Windows 11 subprocess flags
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    SUBPROCESS_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS
else:
    SUBPROCESS_FLAGS = 0

# Environment Setup
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

ASSETS_DIR = BASE_DIR / "assets"
OUTPUTS_DIR = BASE_DIR / "outputs"
TOKENS_DIR = BASE_DIR / "tokens"
STOCK_FILE = BASE_DIR / "stock.json"

for d in [ASSETS_DIR, OUTPUTS_DIR, TOKENS_DIR]:
    d.mkdir(exist_ok=True)

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

try:
    from lib.config_manager import get_config_manager
    from lib.logger import logger

    def file_log(msg):
        logger.info(msg)

    # Load configuration - Remove global API_KEYS
    config = get_config_manager()
except ImportError:
    # Fallback to environment variables
    def file_log(msg):
        print(f"[{datetime.now()}] {msg}")

    config = None


def validate_actor_id(actor_id, platform):
    """Validate Apify Actor ID format and known working actors"""
    if not actor_id or not isinstance(actor_id, str):
        return False
    
    # Known working actors
    valid_actors = {
        "youtube": [
            "bernardo/youtube-scraper",
            "apify/youtube-scraper",
            "dtrungtin/youtube-scraper"
        ],
        "tiktok": [
            "clockworks/free-tiktok-scraper", 
            "apify/tiktok-scraper",
            "clockworks/tiktok-scraper"
        ]
    }
    
    # Check format (should be username/actor-name)
    if "/" not in actor_id:
        return False
    
    # Check if it's a known working actor
    platform_actors = valid_actors.get(platform, [])
    return actor_id in platform_actors


def fetch_viral_content(platform="youtube"):
    """Fetch trending content via Apify with corrected Actor IDs."""
    try:
        if config:
            token = config.api_keys.apify
        else:
            token = os.getenv("APIFY_API_TOKEN", "")
    except Exception:
        token = ""

    if not token:
        file_log("[VIRAL] Apify token yok.")
        return get_fallback_trends(platform)

    try:
        file_log(f"[VIRAL] {platform} trendleri çekiliyor...")

        # CORRECTED Actor IDs (Verified Public Actors)
        if platform == "youtube":
            # Using verified YouTube scraper
            actor_id = "bernardo/youtube-scraper"  # Public, verified actor
            run_input = {
                "searchKeywords": ["shorts", "viral", "trending"],
                "maxResults": 10,
                "searchType": "video"
            }
        else:
            # Using verified TikTok scraper
            actor_id = "clockworks/free-tiktok-scraper"  # Free, public actor
            run_input = {
                "hashtags": ["viral", "trending", "fyp"],
                "resultsPerPage": 10
            }

        # Validate actor ID
        if not validate_actor_id(actor_id, platform):
            file_log(f"[VIRAL-WARN] Invalid actor ID: {actor_id} for {platform}")
            return get_fallback_trends(platform)

        url = (
            "https://api.apify.com/v2/acts/"
            f"{actor_id}/run-sync-get-dataset-items"
        )
        headers = {"Authorization": f"Bearer {token}"}

        import requests

        resp = requests.post(url, json=run_input, headers=headers, timeout=120)

        if resp.status_code == 200:
            data = resp.json()
            # Validate response structure
            if not isinstance(data, list):
                file_log(f"[VIRAL-WARN] Unexpected response format from {platform}")
                return get_fallback_trends(platform)
                
            trends = []
            for item in data[:10]:
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or item.get("text") or "Viral Trend"
                trends.append({"title": title, "platform": platform})
            
            if trends:
                file_log(f"[VIRAL] Successfully fetched {len(trends)} trends from {platform}")
                return trends
            else:
                file_log(f"[VIRAL-WARN] No valid trends found in response from {platform}")
                return get_fallback_trends(platform)
        else:
            file_log(
                f"[VIRAL-WARN] Apify {resp.status_code}. "
                "Fallback kullanılıyor."
            )

    except Exception as e:
        file_log(f"[VIRAL-WARN] API Hatası: {e}. Fallback kullanılıyor.")

    return get_fallback_trends(platform)


def get_fallback_trends(platform):
    """Return fallback trends when API fails"""
    if platform == "youtube":
        return [
            {"title": "Milyonerlerin Sabah Rutini", "platform": "youtube"},
            {
                "title": "Yapay Zeka Dünyayı Ele Geçiriyor",
                "platform": "youtube",
            },
            {
                "title": "Tarihin En Büyük Gizemi",
                "platform": "youtube",
            },
            {"title": "30 Saniyede Özgüven Hilesi", "platform": "youtube"},
            {"title": "Bunu Asla Yapma!", "platform": "youtube"},
        ]
    return [
        {"title": "POV: Sonunu Bekle", "platform": "tiktok"},
        {"title": "Hayat Değiştiren İpucu", "platform": "tiktok"},
        {"title": "Bu Sesi Kullan", "platform": "tiktok"},
        {"title": "Kimse Bunu Bilmiyor", "platform": "tiktok"},
        {"title": "Tarihin En İlginç Olayı", "platform": "tiktok"},
    ]


def normalize_video(input_path, output_path):
    """Normalize video to 1080x1920 30fps."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-vf",
                (
                    "scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920,setsar=1"
                ),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            creationflags=SUBPROCESS_FLAGS if os.name == 'nt' else 0,
        )
        return True
    except Exception as e:
        file_log(f"[NORMALIZE-ERR] {e}")
        return False
