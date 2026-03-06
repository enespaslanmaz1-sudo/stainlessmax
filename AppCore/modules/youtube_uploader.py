"""
YouTube Uploader - OAuth 2.0 ile YouTube Data API v3
"""

import os
import pickle
import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import logging

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    print("[YouTubeUploader] Google API kütüphaneleri yüklü değil!")
    print("Yüklemek için: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")


class YouTubeUploader:
    """YouTube Data API v3 ile video yükleme"""
    
    # YouTube API scopes
    # Not: Kanal doğrulaması için channels().list(mine=True) çağrısı read scope ister.
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube.readonly'
    ]
    
    def __init__(self, credentials_dir: str = "credentials"):
        self.logger = logging.getLogger(__name__)
        self.credentials_dir = Path(credentials_dir)
        self.credentials_dir.mkdir(exist_ok=True)
        
        self.youtube = None
        self.current_account = None
    
    def authenticate(self, account_id: str, client_id: str, client_secret: str) -> bool:
        """
        YouTube hesabına OAuth ile bağlan
        
        Args:
            account_id: Hesap ID
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret
            
        Returns:
            bool: Başarılı mı?
        """
        if not GOOGLE_API_AVAILABLE:
            self.logger.error("Google API kütüphaneleri yüklü değil!")
            return False
        
        try:
            creds = None
            token_file = self.credentials_dir / f"{account_id}_token.pickle"
            
            # Önceden kaydedilmiş token var mı?
            if token_file.exists():
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)

                # Eski token yeni scope'ları içermiyorsa zorunlu re-auth
                creds_scopes = set((getattr(creds, 'scopes', None) or []))
                required_scopes = set(self.SCOPES)
                if not required_scopes.issubset(creds_scopes):
                    self.logger.warning(
                        f"Token scope yetersiz ({account_id}). Re-auth zorlanıyor. "
                        f"Mevcut: {sorted(creds_scopes)}, Gerekli: {sorted(required_scopes)}"
                    )
                    creds = None
                    try:
                        token_file.unlink(missing_ok=True)
                    except Exception as token_err:
                        self.logger.warning(f"Eski token silinemedi: {token_err}")
            
            # Token yoksa veya geçersizse, yeniden auth yap
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    self.logger.info("Token yenileniyor...")
                    creds.refresh(Request())
                else:
                    self.logger.info("Yeni OAuth akışı başlatılıyor...")
                    
                    # client_secrets.json oluştur
                    client_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "redirect_uris": ["http://localhost"],
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token"
                        }
                    }
                    
                    flow = InstalledAppFlow.from_client_config(
                        client_config,
                        scopes=self.SCOPES
                    )
                    
                    # Tarayıcıda auth yap
                    creds = flow.run_local_server(port=0)
                
                # Token'ı kaydet
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
                
                self.logger.info("Token kaydedildi")
            
            # YouTube service oluştur
            self.youtube = build('youtube', 'v3', credentials=creds)
            self.current_account = account_id
            
            self.logger.info(f"YouTube API bağlantısı başarılı: {account_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Authentication hatası: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def upload_video(self,
                    video_path: Path,
                    title: str,
                    description: str = "",
                    tags: list = None,
                    category_id: str = "22",  # People & Blogs
                    privacy_status: str = "public",
                    publishAt: str = None,
                    progress_callback=None) -> Optional[str]:
        """
        Video yükle
        
        Args:
            video_path: Video dosya yolu
            title: Video başlığı
            description: Video açıklaması
            tags: Etiketler
            category_id: YouTube kategori ID
            privacy_status: public, private, unlisted
            publishAt: ISO 8601 tarih formatı (örn: 2026-02-14T10:00:00.000Z)
            
        Returns:
            str: Video ID veya None
        """
        if not self.youtube:
            self.logger.error("YouTube API bağlantısı yok! authenticate() çağrısı yapın.")
            return None
        
        if not video_path.exists():
            self.logger.error(f"Video dosyası bulunamadı: {video_path}")
            return None
        
        try:
            self.logger.info(f"Video yükleniyor: {title[:50]}...")
            
            # SCHEDULED logic
            status_body = {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
            
            if publishAt:
                status_body['privacyStatus'] = 'private' # Scheduled must be private first
                status_body['publishAt'] = publishAt
                self.logger.info(f"📅 Video planlanıyor: {publishAt}")

            # Video metadata
            body = {
                'snippet': {
                    'title': title[:100],  # Maksimum 100 karakter
                    'description': description[:5000],  # Maksimum 5000 karakter
                    'tags': tags[:500] if tags else [],  # Maksimum 500 tag
                    'categoryId': category_id
                },
                'status': status_body
            }
            
            # Media upload
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/*',
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )
            
            # Upload request
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )
            
            # Yükleme
            response = None
            last_progress = -1
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress != last_progress:
                        self.logger.info(f"Yükleme: %{progress}")
                        if progress_callback:
                            try:
                                progress_callback(progress, f"YouTube Yükleniyor... %{progress}")
                            except Exception as cb_err:
                                self.logger.debug(f"YouTube progress callback hatası: {cb_err}")
                        last_progress = progress

            if progress_callback and last_progress < 100:
                try:
                    progress_callback(100, "YouTube Yükleniyor... %100")
                except Exception as cb_err:
                    self.logger.debug(f"YouTube final progress callback hatası: {cb_err}")
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            self.logger.info(f"✅ Video yüklendi: {video_url}")
            return video_id
            
        except Exception as e:
            self.logger.error(f"Video yükleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_channel_info(self) -> Optional[Dict]:
        """Kanal bilgilerini al"""
        if not self.youtube:
            return None
        
        try:
            request = self.youtube.channels().list(
                part='snippet,statistics',
                mine=True
            )
            response = request.execute()
            
            if response['items']:
                return response['items'][0]
            return None
            
        except Exception as e:
            self.logger.error(f"Kanal bilgisi alınamadı: {e}")
            return None


# Test için
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test hesabı - hesaplar.txt'den parse et
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    
    from AppCore.modules.hesaplar_parser import HesaplarParser
    
    parser = HesaplarParser("hesaplar.txt")
    if parser.parse():
        yt_accounts = parser.get_youtube_accounts()
        if yt_accounts:
            first_account = yt_accounts[0]
            print(f"\n=== Test: {first_account.name} ===")
            
            uploader = YouTubeUploader()
            
            # Authenticate
            success = uploader.authenticate(
                account_id=f"youtube_{first_account.name.lower().replace(' ', '_')}",
                client_id=first_account.client_id,
                client_secret=first_account.client_secret
            )
            
            if success:
                # Kanal bilgisi
                channel = uploader.get_channel_info()
                if channel:
                    print(f"Kanal: {channel['snippet']['title']}")
                    print(f"Abone: {channel['statistics'].get('subscriberCount', 0)}")
