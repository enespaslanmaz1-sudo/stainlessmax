"""
Upload Checker - Gemini AI ile Paylaşım Kontrolü
Tüm platformlardaki (YouTube, TikTok, Instagram) son paylaşımları kontrol eder
"""
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from google import genai

logger = logging.getLogger(__name__)


class UploadChecker:
    """
    Gemini AI ile paylaşım kontrolcüsü
    
    Özellikler:
    - YouTube kanallarını tara
    - TikTok hesaplarını tara
    - Instagram hesaplarını tara
    - Son 24 saatteki paylaşımları listele
    """
    
    def __init__(self):
        """Initialize checker"""
        self.logger = logging.getLogger(__name__)
        self.model_name = "gemini-2.5-flash" 
        
        # Gemini AI setup (new SDK)
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
            self.logger.warning("Gemini API key not found")
    
    def check_youtube_channel(self, channel_name: str, channel_id: str) -> Dict:
        """
        YouTube kanalındaki son videoları kontrol et
        
        Args:
            channel_name: Kanal adı
            channel_id: Kanal ID
            
        Returns:
            Dict: {
                "platform": "youtube",
                "account": channel_name,
                "videos": [
                    {
                        "title": "Video başlığı",
                        "url": "https://youtube.com/watch?v=...",
                        "published": "2 hours ago",
                        "views": "1.2K"
                    }
                ],
                "total": 5,
                "last_24h": 2
            }
        """
        try:
            # Gemini AI ile YouTube kanalını analiz et
            if self.client:
                prompt = f"""
YouTube kanalı: {channel_name}
Kanal ID: {channel_id}

Bu YouTube kanalının son 24 saatteki videolarını listele.
Her video için:
- Başlık
- URL (https://youtube.com/watch?v=VIDEO_ID formatında)
- Yayınlanma zamanı (örn: "2 hours ago", "1 day ago")
- İzlenme sayısı

JSON formatında döndür:
{{
    "videos": [
        {{
            "title": "Video başlığı",
            "url": "https://youtube.com/watch?v=...",
            "published": "2 hours ago",
            "views": "1.2K"
        }}
    ],
    "total": 5,
    "last_24h": 2
}}

NOT: Eğer kanal bilgilerine erişemiyorsan veya video yoksa boş liste döndür.
"""
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                
                # Parse response (simplified - gerçek implementasyonda JSON parse et)
                return {
                    "platform": "youtube",
                    "account": channel_name,
                    "videos": [],  # Gemini response'undan parse edilecek
                    "total": 0,
                    "last_24h": 0,
                    "raw_response": response.text if response else "No response"
                }
            else:
                return {
                    "platform": "youtube",
                    "account": channel_name,
                    "error": "Gemini API not available"
                }
                
        except Exception as e:
            self.logger.error(f"YouTube check error for {channel_name}: {e}")
            return {
                "platform": "youtube",
                "account": channel_name,
                "error": str(e)
            }
    
    def check_tiktok_account(self, username: str) -> Dict:
        """
        TikTok hesabındaki son videoları kontrol et
        
        Args:
            username: TikTok kullanıcı adı
            
        Returns:
            Dict: Paylaşım bilgileri
        """
        try:
            if self.client:
                prompt = f"""
TikTok hesabı: @{username}

Bu TikTok hesabının son 24 saatteki videolarını listele.
Her video için:
- Başlık/Caption
- URL (https://tiktok.com/@{username}/video/VIDEO_ID formatında)
- Yayınlanma zamanı
- İzlenme sayısı
- Beğeni sayısı

JSON formatında döndür:
{{
    "videos": [
        {{
            "title": "Video caption",
            "url": "https://tiktok.com/@{username}/video/...",
            "published": "3 hours ago",
            "views": "15.2K",
            "likes": "1.2K"
        }}
    ],
    "total": 3,
    "last_24h": 1
}}

NOT: Eğer hesap bilgilerine erişemiyorsan veya video yoksa boş liste döndür.
"""
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                
                return {
                    "platform": "tiktok",
                    "account": f"@{username}",
                    "videos": [],
                    "total": 0,
                    "last_24h": 0,
                    "raw_response": response.text if response else "No response"
                }
            else:
                return {
                    "platform": "tiktok",
                    "account": f"@{username}",
                    "error": "Gemini API not available"
                }
                
        except Exception as e:
            self.logger.error(f"TikTok check error for @{username}: {e}")
            return {
                "platform": "tiktok",
                "account": f"@{username}",
                "error": str(e)
            }
    
    def check_instagram_account(self, username: str) -> Dict:
        """
        Instagram hesabındaki son reels'leri kontrol et
        
        Args:
            username: Instagram kullanıcı adı
            
        Returns:
            Dict: Paylaşım bilgileri
        """
        try:
            if self.client:
                prompt = f"""
Instagram hesabı: @{username}

Bu Instagram hesabının son 24 saatteki Reels videolarını listele.
Her video için:
- Caption
- URL (https://instagram.com/reel/REEL_ID formatında)
- Yayınlanma zamanı
- İzlenme sayısı
- Beğeni sayısı

JSON formatında döndür:
{{
    "videos": [
        {{
            "title": "Reel caption",
            "url": "https://instagram.com/reel/...",
            "published": "5 hours ago",
            "views": "8.5K",
            "likes": "650"
        }}
    ],
    "total": 2,
    "last_24h": 1
}}

NOT: Eğer hesap bilgilerine erişemiyorsan veya video yoksa boş liste döndür.
"""
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                
                return {
                    "platform": "instagram",
                    "account": f"@{username}",
                    "videos": [],
                    "total": 0,
                    "last_24h": 0,
                    "raw_response": response.text if response else "No response"
                }
            else:
                return {
                    "platform": "instagram",
                    "account": f"@{username}",
                    "error": "Gemini API not available"
                }
                
        except Exception as e:
            self.logger.error(f"Instagram check error for @{username}: {e}")
            return {
                "platform": "instagram",
                "account": f"@{username}",
                "error": str(e)
            }
    
    def check_all_accounts(self, accounts: Dict) -> Dict:
        """
        Tüm hesapları kontrol et
        
        Args:
            accounts: {
                "youtube": [{"name": "...", "id": "..."}],
                "tiktok": [{"username": "..."}],
                "instagram": [{"username": "..."}]
            }
            
        Returns:
            Dict: {
                "timestamp": "2026-02-09T23:30:00",
                "youtube": [...],
                "tiktok": [...],
                "instagram": [...],
                "summary": {
                    "total_accounts": 8,
                    "total_videos_24h": 15,
                    "youtube_videos": 8,
                    "tiktok_videos": 4,
                    "instagram_videos": 3
                }
            }
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "youtube": [],
            "tiktok": [],
            "instagram": [],
            "summary": {
                "total_accounts": 0,
                "total_videos_24h": 0,
                "youtube_videos": 0,
                "tiktok_videos": 0,
                "instagram_videos": 0
            }
        }
        
        # YouTube kanallarını kontrol et
        for channel in accounts.get("youtube", []):
            result = self.check_youtube_channel(
                channel.get("name", "Unknown"),
                channel.get("id", "")
            )
            results["youtube"].append(result)
            results["summary"]["youtube_videos"] += result.get("last_24h", 0)
        
        # TikTok hesaplarını kontrol et
        for account in accounts.get("tiktok", []):
            result = self.check_tiktok_account(account.get("username", "unknown"))
            results["tiktok"].append(result)
            results["summary"]["tiktok_videos"] += result.get("last_24h", 0)
        
        # Instagram hesaplarını kontrol et
        for account in accounts.get("instagram", []):
            result = self.check_instagram_account(account.get("username", "unknown"))
            results["instagram"].append(result)
            results["summary"]["instagram_videos"] += result.get("last_24h", 0)
        
        # Özet hesapla
        results["summary"]["total_accounts"] = (
            len(accounts.get("youtube", [])) +
            len(accounts.get("tiktok", [])) +
            len(accounts.get("instagram", []))
        )
        results["summary"]["total_videos_24h"] = (
            results["summary"]["youtube_videos"] +
            results["summary"]["tiktok_videos"] +
            results["summary"]["instagram_videos"]
        )
        
        return results


# Global instance
_upload_checker = None

def get_upload_checker() -> UploadChecker:
    """Get global upload checker instance"""
    global _upload_checker
    if _upload_checker is None:
        _upload_checker = UploadChecker()
    return _upload_checker
