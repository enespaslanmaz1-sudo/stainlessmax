"""
YouTube Shorts Uploader
Handles video upload with SEO optimization
"""
import os
import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    from lib.config_manager import get_config_manager
    from lib.logger import logger
    from lib.error_handler import handle_error
except ImportError:
    logger = None
    handle_error = None
    get_config_manager = None

# OAuth scopes for YouTube
YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.readonly'
]


class YouTubeUploader:
    """YouTube Shorts uploader with SEO optimization"""
    
    def __init__(self, channel_id: str = None, base_dir: Path = None):
        self.channel_id = channel_id or "default"
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.tokens_dir = self.base_dir / "tokens"
        self.tokens_dir.mkdir(exist_ok=True)
        
        self.credentials = None
        self.youtube = None
        
        # Load credentials
        self._load_credentials()
    
    def _get_token_file(self) -> Path:
        """Get token file path for this channel"""
        return self.tokens_dir / f"youtube_{self.channel_id}_token.json"
    
    def _load_credentials(self) -> bool:
        """Load or refresh YouTube credentials"""
        if not GOOGLE_AVAILABLE:
            if logger:
                logger.error("Google API libraries not available")
            return False
        
        token_file = self._get_token_file()
        creds = None
        
        # Load existing credentials
        if token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_file), YOUTUBE_SCOPES
                )
            except Exception as e:
                if handle_error:
                    handle_error(e, {"context": "youtube_token_load"})
                elif logger:
                    logger.error(f"Failed to load YouTube token: {e}")
        
        # Refresh or create new credentials
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                if handle_error:
                    handle_error(e, {"context": "youtube_token_refresh"})
                elif logger:
                    logger.error(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            # Need to authenticate
            return False
        
        self.credentials = creds
        self.youtube = build('youtube', 'v3', credentials=creds)
        
        # Save credentials
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
        
        return True
    
    def authenticate(self, client_id: str = None, client_secret: str = None) -> bool:
        """Authenticate with YouTube OAuth"""
        if not GOOGLE_AVAILABLE:
            print("❌ Google API libraries not installed")
            print("   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            return False
        
        try:
            # Get credentials from config if not provided
            if not client_id or not client_secret:
                if get_config_manager:
                    config = get_config_manager()
                    channel_config = config.get_youtube_channel_config(self.channel_id)
                    client_id = client_id or channel_config.get('client_id')
                    client_secret = client_secret or channel_config.get('client_secret')
            
            if not client_id or not client_secret:
                print("❌ YouTube OAuth credentials required")
                return False
            
            # Create client secrets JSON
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
                }
            }
            
            # Create flow
            flow = InstalledAppFlow.from_client_config(
                client_config, YOUTUBE_SCOPES
            )
            
            # Run local server
            print("🔐 YouTube OAuth başlatılıyor...")
            print("Tarayıcı açılacak, izin verin...")
            
            creds = flow.run_local_server(port=0)
            
            self.credentials = creds
            self.youtube = build('youtube', 'v3', credentials=creds)
            
            # Save token
            token_file = self._get_token_file()
            with open(token_file, 'w') as f:
                f.write(creds.to_json())
            
            print("✅ YouTube OAuth tamamlandı!")
            return True
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "youtube_authentication"})
            print(f"❌ YouTube auth error: {e}")
            return False
    
    def generate_seo_metadata(self, title: str, script: str, theme: str) -> Dict[str, Any]:
        """Generate SEO optimized title, description, and tags"""
        
        # SEO templates for different themes
        seo_templates = {
            "mystery": {
                "prefixes": ["🔍 Gizem Çözüldü:", "🕵️ Kimse Bunu Bilmiyor:", "🤫 Gizli Kaldı:", "⚠️ Şok Gerçek:"],
                "suffixes": ["#Gizem #Bilinmeyen #Keşfet", "#GizliGerçekler #Mystery #Viral", "#Şok #Gizemli #Bilgi"],
                "tags": ["gizem", "bilinmeyen", "gizli", "şok", "keşif", "tarih", "gizemli", "viral"]
            },
            "finance": {
                "prefixes": ["💰 Para Sırrı:", "📈 Finansal Özgürlük:", "🤑 Zengin Olmanın Yolu:", "💵 Para Hilesi:"],
                "suffixes": ["#Para #Finans #Zenginlik", "#Yatırım #Borsa #Kripto", "#FinansalÖzgürlük #ParaYönetimi #Bütçe"],
                "tags": ["para", "finans", "yatırım", "zenginlik", "borsa", "kripto", "bütçe", "tasarruf"]
            },
            "health": {
                "prefixes": ["🧘 Sağlık Sırrı:", "💪 Vücut Hilesi:", "🥗 Sağlıklı Yaşam:", "⚡ Enerji Patlaması:"],
                "suffixes": ["#Sağlık #Wellness #Spor", "#SağlıklıYaşam #Fitness #Beslenme", "#Zindelik #Sağlıklı #Yaşam"],
                "tags": ["sağlık", "fitness", "beslenme", "wellness", "spor", "zindelik", "yaşam", "sağlıklı"]
            }
        }
        
        template = seo_templates.get(theme, seo_templates["mystery"])
        
        # Generate optimized title
        prefix = random.choice(template["prefixes"])
        # Clean original title
        clean_title = title.replace("🔥", "").replace("🚢", "").replace("🔺", "").strip()
        optimized_title = f"{prefix} {clean_title} #Shorts"
        
        # Ensure title is under 100 characters
        if len(optimized_title) > 100:
            optimized_title = optimized_title[:97] + "..."
        
        # Generate description
        description = f"""{optimized_title}

{clean_title} hakkında bilmeniz gerekenler!

🎯 Bu videoda:
• Önemli bilgiler
• Şaşırtıcı gerçekler  
• Uygulanabilir tavsiyeler

📌 Abone olun, daha fazla içerik için bildirimleri açın!

{random.choice(template["suffixes"])}
"""
        
        # Generate tags (mix of theme tags and extracted keywords)
        tags = template["tags"].copy()
        tags.extend(["shorts", "viral", "trend", "keşfet", "youtube shorts", "60saniye"])
        
        # Extract keywords from script (simple word extraction)
        script_words = script.lower().split()
        important_words = [w for w in script_words if len(w) > 4 and w.isalpha()]
        tags.extend(list(set(important_words))[:5])  # Add up to 5 unique keywords
        
        # Ensure we don't exceed YouTube's 500 character limit for tags
        total_length = sum(len(tag) for tag in tags)
        while total_length > 480 and len(tags) > 10:
            tags.pop()
            total_length = sum(len(tag) for tag in tags)
        
        return {
            "title": optimized_title,
            "description": description,
            "tags": tags[:15],  # Max 15 tags recommended
            "category_id": "22",  # People & Blogs
            "privacy_status": "public",
            "made_for_kids": False
        }
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        script: str,
        theme: str = "mystery",
        schedule_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Upload video to YouTube Shorts"""
        
        if not self.youtube:
            if not self._load_credentials():
                print("❌ YouTube not authenticated")
                return None
        
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"❌ Video file not found: {video_path}")
            return None
        
        # Generate SEO metadata
        metadata = self.generate_seo_metadata(title, script, theme)
        
        try:
            print(f"📤 YouTube'a yükleniyor: {metadata['title'][:50]}...")
            
            # Build video body
            body = {
                'snippet': {
                    'title': metadata['title'],
                    'description': metadata['description'],
                    'tags': metadata['tags'],
                    'categoryId': metadata['category_id']
                },
                'status': {
                    'privacyStatus': 'private' if schedule_time else metadata['privacy_status'],
                    'madeForKids': metadata['made_for_kids'],
                    'selfDeclaredMadeForKids': metadata['made_for_kids']
                }
            }
            
            # Add publishAt if scheduled
            if schedule_time:
                # YouTube requires RFC 3339 format
                publish_at = schedule_time.isoformat() + 'Z'
                body['status']['publishAt'] = publish_at
                print(f"⏰ Zamanlandı: {schedule_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Create media upload
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/mp4',
                resumable=True
            )
            
            # Execute upload
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"  Upload progress: {int(status.progress() * 100)}%")
            
            video_id = response['id']
            video_url = f"https://youtube.com/shorts/{video_id}"
            
            print(f"✅ YouTube'a yüklendi: {video_url}")
            
            if logger:
                logger.info(f"Video uploaded to YouTube: {video_id}")
            
            return video_id
            
        except HttpError as e:
            error_details = e.error_details if hasattr(e, 'error_details') else str(e)
            if logger:
                logger.error(f"YouTube upload HTTP error: {error_details}")
            print(f"❌ YouTube HTTP error: {error_details}")
            return None
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "youtube_upload", "video_path": str(video_path)})
            print(f"❌ YouTube upload error: {e}")
            return None
    
    def get_upload_quota(self) -> Dict[str, Any]:
        """Get current upload quota status"""
        if not self.youtube:
            return {"error": "Not authenticated"}
        
        try:
            # Get channel info
            channels_response = self.youtube.channels().list(
                mine=True,
                part='statistics,contentDetails'
            ).execute()
            
            if not channels_response.get('items'):
                return {"error": "No channel found"}
            
            channel = channels_response['items'][0]
            stats = channel.get('statistics', {})
            
            return {
                'subscriber_count': stats.get('subscriberCount', '0'),
                'video_count': stats.get('videoCount', '0'),
                'view_count': stats.get('viewCount', '0'),
                'authenticated': True
            }
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "youtube_quota_check"})
            return {"error": str(e)}


# Global uploader instances
_uploaders = {}


def get_youtube_uploader(channel_id: str = "default") -> YouTubeUploader:
    """Get or create YouTube uploader instance"""
    global _uploaders
    
    if channel_id not in _uploaders:
        _uploaders[channel_id] = YouTubeUploader(channel_id)
    
    return _uploaders[channel_id]


def upload_to_youtube(
    video_path: str,
    title: str,
    script: str,
    channel_id: str = "default",
    theme: str = "mystery",
    schedule_time: Optional[datetime] = None
) -> Optional[str]:
    """Convenience function to upload video"""
    uploader = get_youtube_uploader(channel_id)
    return uploader.upload_video(video_path, title, script, theme, schedule_time)
