"""
TikTok Video Uploader
Handles video upload with SEO optimization
Uses TikTok's Creator Portal API or browser automation as fallback
"""
import os
import sys
import json
import time
import random
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

try:
    from lib.config_manager import get_config_manager
    from lib.logger import logger
    from lib.error_handler import handle_error
except ImportError:
    logger = None
    handle_error = None
    get_config_manager = None


class TikTokUploader:
    """TikTok video uploader with SEO optimization"""
    
    # TikTok API endpoints
    TIKTOK_API_BASE = "https://open-api.tiktok.com"
    TIKTOK_BUSINESS_BASE = "https://business-api.tiktok.com"
    
    def __init__(self, account_id: str = None, base_dir: Path = None):
        self.account_id = account_id or "default"
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.tokens_dir = self.base_dir / "tokens"
        self.tokens_dir.mkdir(exist_ok=True)
        
        self.access_token = None
        self.refresh_token = None
        
        # Load credentials
        self._load_credentials()
    
    def _get_token_file(self) -> Path:
        """Get token file path for this account"""
        return self.tokens_dir / f"tiktok_{self.account_id}_token.json"
    
    def _load_credentials(self) -> bool:
        """Load saved credentials"""
        token_file = self._get_token_file()
        
        if token_file.exists():
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                
                # Check if token is expired
                expires_at = data.get('expires_at')
                if expires_at:
                    from datetime import datetime
                    if datetime.fromisoformat(expires_at) < datetime.now():
                        return self._refresh_token()
                
                return bool(self.access_token)
                
            except Exception as e:
                if handle_error:
                    handle_error(e, {"context": "tiktok_token_load"})
                return False
        
        return False
    
    def _save_credentials(self, access_token: str, refresh_token: str = None, expires_in: int = 7200):
        """Save credentials to file"""
        token_file = self._get_token_file()
        
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        data = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _refresh_token(self) -> bool:
        """Refresh access token"""
        if not self.refresh_token:
            return False
        
        try:
            # This would use TikTok's refresh token endpoint
            # Implementation depends on TikTok API version
            if logger:
                logger.info("Refreshing TikTok token...")
            
            # Placeholder for actual refresh logic
            return False
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_token_refresh"})
            return False
    
    def authenticate(self, client_key: str = None, client_secret: str = None) -> bool:
        """Authenticate with TikTok OAuth"""
        try:
            # Get credentials from config
            if not client_key or not client_secret:
                if get_config_manager:
                    config = get_config_manager()
                    client_key = client_key or config.tiktok_config.client_id
                    client_secret = client_secret or config.tiktok_config.client_secret
            
            # TikTok OAuth flow would go here
            # For now, we use a simplified version
            print("🔐 TikTok OAuth başlatılıyor...")
            print("⚠️ TikTok API entegrasyonu için developer hesabı gerekli")
            print("   https://developers.tiktok.com/")
            
            return False
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_authentication"})
            return False
    
    def generate_seo_metadata(self, title: str, script: str, theme: str) -> Dict[str, Any]:
        """Generate SEO optimized caption and hashtags"""
        
        # TikTok-optimized hashtag sets
        hashtag_sets = {
            "mystery": {
                "primary": ["#gizem", "#bilinmeyen", "#keşfet", "#gizli"],
                "secondary": ["#şok", "#gizemli", "#tarih", "#bilgi", "#viral"],
                "trending": ["#fyp", "#foryou", "#foryoupage", "#keşfetteyiz"]
            },
            "finance": {
                "primary": ["#para", "#finans", "#zenginlik", "#yatırım"],
                "secondary": ["#borsa", "#kripto", "#tasarruf", "#paraönerisi"],
                "trending": ["#fyp", "#foryou", "#motivasyon", "#başarı"]
            },
            "health": {
                "primary": ["#sağlık", "#fitness", "#wellness", "#spor"],
                "secondary": ["#beslenme", "#sağlıklıyaşam", "#zindelik", "#diyet"],
                "trending": ["#fyp", "#foryou", "#sağlıklı", "#yaşam"]
            }
        }
        
        hashtag_set = hashtag_sets.get(theme, hashtag_sets["mystery"])
        
        # Generate caption hooks
        hooks = [
            "Bu bilgiyi herkes bilmeli! 👇",
            "Sonunu bekleyin... 😱",
            "Bu gerçekten oluyor! 🔥",
            "Kaydet ve sonra izle! 💾",
            "Arkadaşını etiketle! 👥",
            "Yorumlara fikrini yaz! 💬"
        ]
        
        # Build caption
        clean_title = ''.join(c for c in title if c.isalnum() or c.isspace() or c in '!?.,')
        hook = random.choice(hooks)
        
        # Select hashtags (max 10 for best engagement)
        primary = hashtag_set["primary"]
        secondary = random.sample(hashtag_set["secondary"], min(3, len(hashtag_set["secondary"])))
        trending = random.sample(hashtag_set["trending"], min(2, len(hashtag_set["trending"])))
        
        hashtags = primary + secondary + trending
        hashtag_str = ' '.join(hashtags[:10])
        
        caption = f"{clean_title}\n\n{hook}\n\n{hashtag_str}"
        
        # Ensure caption is under 2200 characters (TikTok limit)
        if len(caption) > 2200:
            caption = caption[:2197] + "..."
        
        return {
            "caption": caption,
            "hashtags": hashtags,
            "title": clean_title,
            "privacy_status": "public",
            "allow_comments": True,
            "allow_duet": True,
            "allow_stitch": True
        }
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        script: str,
        theme: str = "mystery",
        schedule_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Upload video to TikTok"""
        
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"❌ Video file not found: {video_path}")
            return None
        
        # Generate SEO metadata
        metadata = self.generate_seo_metadata(title, script, theme)
        
        try:
            print(f"📤 TikTok'a yükleniyor: {metadata['title'][:40]}...")
            
            # Check if using TikTok API
            if self.access_token:
                return self._upload_via_api(video_path, metadata, schedule_time)
            else:
                # Fallback: Save upload instructions
                return self._save_upload_instructions(video_path, metadata, schedule_time)
                
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_upload", "video_path": str(video_path)})
            print(f"❌ TikTok upload error: {e}")
            return None
    
    def _upload_via_api(
        self,
        video_path: Path,
        metadata: Dict[str, Any],
        schedule_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Upload using TikTok API"""
        
        try:
            # TikTok video upload implementation
            # This requires TikTok for Developers API access
            
            if logger:
                logger.info("Uploading via TikTok API...")
            
            # Step 1: Initialize upload
            init_url = f"{self.TIKTOK_API_BASE}/video/upload/"
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Get video size
            video_size = video_path.stat().st_size
            
            init_data = {
                'source_info': {
                    'source': 'PULL_FROM_URL',
                    'video_size': video_size,
                    'chunk_size': video_size,
                    'total_chunk_count': 1
                },
                'title': metadata['caption'],
                'privacy_level': metadata['privacy_status'],
                'disable_duet': not metadata['allow_duet'],
                'disable_comment': not metadata['allow_comments'],
                'disable_stitch': not metadata['allow_stitch']
            }
            
            if schedule_time:
                init_data['schedule_time'] = int(schedule_time.timestamp())
            
            # This is a simplified version - actual implementation would handle chunking
            print("⚠️ TikTok API upload - implementasyon gerekli")
            print(f"   Video: {video_path}")
            print(f"   Caption: {metadata['caption'][:50]}...")
            
            return None
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_api_upload"})
            return None
    
    def _save_upload_instructions(
        self,
        video_path: Path,
        metadata: Dict[str, Any],
        schedule_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Save upload instructions for manual upload"""
        
        try:
            # Create instructions file
            instructions_dir = self.base_dir / "upload_queue" / "tiktok"
            instructions_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(time.time())
            instructions_file = instructions_dir / f"upload_{timestamp}.json"
            
            instructions = {
                "platform": "tiktok",
                "account_id": self.account_id,
                "video_path": str(video_path),
                "caption": metadata['caption'],
                "hashtags": metadata['hashtags'],
                "schedule_time": schedule_time.isoformat() if schedule_time else None,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            
            with open(instructions_file, 'w', encoding='utf-8') as f:
                json.dump(instructions, f, indent=2, ensure_ascii=False)
            
            print(f"📋 TikTok yükleme talimatları kaydedildi:")
            print(f"   Dosya: {instructions_file}")
            print(f"   Video: {video_path.name}")
            print(f"   Caption: {metadata['caption'][:60]}...")
            
            if schedule_time:
                print(f"   Zamanlama: {schedule_time.strftime('%Y-%m-%d %H:%M')}")
            
            return str(instructions_file)
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_save_instructions"})
            return None
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get TikTok account information"""
        if not self.access_token:
            return {
                "authenticated": False,
                "message": "TikTok API token not configured"
            }
        
        try:
            # This would call TikTok's user info endpoint
            return {
                "authenticated": True,
                "account_id": self.account_id,
                "note": "TikTok API integration requires developer account"
            }
            
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "tiktok_account_info"})
            return {"error": str(e)}


# Global uploader instances
_uploaders = {}


def get_tiktok_uploader(account_id: str = "default") -> TikTokUploader:
    """Get or create TikTok uploader instance"""
    global _uploaders
    
    if account_id not in _uploaders:
        _uploaders[account_id] = TikTokUploader(account_id)
    
    return _uploaders[account_id]


def upload_to_tiktok(
    video_path: str,
    title: str,
    script: str,
    account_id: str = "default",
    theme: str = "mystery",
    schedule_time: Optional[datetime] = None
) -> Optional[str]:
    """Convenience function to upload video"""
    uploader = get_tiktok_uploader(account_id)
    return uploader.upload_video(video_path, title, script, theme, schedule_time)
