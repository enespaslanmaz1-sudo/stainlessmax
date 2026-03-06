"""
Instagram Uploader - Instagrapi ile otomatik Reels yükleme
Enhanced with IP rotation, retry logic, session management, and WARP support
"""

import logging
import time
import random
import subprocess
from pathlib import Path
from typing import Optional, Dict
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, ClientError

logger = logging.getLogger(__name__)


def check_warp_available():
    """WARP kurulu mu kontrol et"""
    try:
        result = subprocess.run(
            ["warp-cli", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_warp_connected():
    """WARP'ın bağlı olduğundan emin ol"""
    try:
        # Status kontrol
        result = subprocess.run(
            ["warp-cli", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if "connected" in result.stdout.lower():
            logger.info("✅ WARP zaten bağlı")
            return True
        
        # Bağlı değilse bağlan
        logger.info("🔄 WARP bağlantısı kuruluyor...")
        result = subprocess.run(
            ["warp-cli", "connect"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            time.sleep(3)  # Bağlantının kurulmasını bekle
            logger.info("✅ WARP bağlantısı kuruldu")
            return True
        else:
            logger.warning(f"⚠️ WARP bağlantı hatası: {result.stderr}")
            return False
            
    except Exception as e:
        logger.warning(f"WARP kontrol hatası: {e}")
        return False


class InstagramUploader:
    """
    Instagram Reels yükleyici
    
    Instagrapi kütüphanesi kullanır (resmî API değil)
    Enhanced features:
    - Session persistence
    - Retry logic with exponential backoff
    - User-agent rotation
    - Delay between requests
    - Challenge handling
    """
    
    def __init__(self, username: str, password: str, session_file: str = "data/instagram_session.json", use_warp: bool = True, proxy: str = None):
        """
        Args:
            username: Instagram kullanıcı adı
            password: Instagram şifre
            session_file: Session kaydı için dosya
            use_warp: WARP kullan (varsa)
            proxy: Proxy URL (örn: "http://user:pass@host:port" veya "socks5://host:port")
        """
        self.logger = logging.getLogger(__name__)
        self.username = username
        self.password = password
        self.session_file = Path(session_file)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.use_warp = use_warp
        self.proxy = proxy
        
        # Proxy varsa onu kullan, yoksa WARP dene
        if self.proxy:
            self.logger.info(f"🔒 Proxy kullanılıyor: {self._mask_proxy(self.proxy)}")
        elif self.use_warp and check_warp_available():
            self.logger.info("🔍 WARP tespit edildi, bağlantı kontrol ediliyor...")
            if ensure_warp_connected():
                self.logger.info("✅ WARP aktif - IP değiştirildi")
            else:
                self.logger.warning("⚠️ WARP bağlantısı kurulamadı, normal bağlantı kullanılacak")
        elif self.use_warp:
            self.logger.info("ℹ️ WARP kurulu değil, normal bağlantı kullanılacak")
        
        self.client = Client()
        
        # Proxy ayarla
        if self.proxy:
            self.client.set_proxy(self.proxy)
            self.logger.info("✅ Proxy configured")
        
        self._configure_client()
        self._login()
    
    def _mask_proxy(self, proxy_url: str) -> str:
        """Proxy URL'deki şifreyi maskele"""
        try:
            if '@' in proxy_url:
                # Format: protocol://user:pass@host:port
                parts = proxy_url.split('@')
                auth_part = parts[0].split('//')
                if len(auth_part) > 1 and ':' in auth_part[1]:
                    protocol = auth_part[0]
                    user = auth_part[1].split(':')[0]
                    host_port = parts[1]
                    return f"{protocol}//{user}:****@{host_port}"
            return proxy_url
        except Exception:
            return "****"
    
    def _configure_client(self):
        """Configure client with better settings to avoid detection"""
        # Set delays to mimic human behavior
        self.client.delay_range = [3, 7]  # Random delay between 3-7 seconds
        
        # Set realistic device settings using set_device method
        self.client.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": 28,
            "android_release": "9.0",
            "dpi": "480dpi",
            "resolution": "1080x2340",
            "manufacturer": "OnePlus",
            "device": "OnePlus 6T",
            "model": "ONEPLUS A6013",
            "cpu": "qcom",
            "version_code": "314665256"
        })
        
        self.logger.info("✅ Client configured with realistic device settings")
    
    def _login(self, max_retries: int = 3):
        """Instagram'a login with retry logic"""
        for attempt in range(max_retries):
            try:
                # Session yükle (varsa)
                if self.session_file.exists():
                    self.logger.info(f"Session yükleniyor: {self.session_file}")
                    try:
                        self.client.load_settings(str(self.session_file))
                        self.client.login(self.username, self.password)
                        
                        # Session'ı doğrula
                        self.client.get_timeline_feed()
                        self.logger.info("✅ Session geçerli, login başarılı")
                        return
                    except (LoginRequired, ClientError) as e:
                        self.logger.warning(f"Session geçersiz: {e}")
                        # Session dosyasını sil
                        self.session_file.unlink(missing_ok=True)
                
                # Yeni login - with delay
                self.logger.info(f"Instagram login (attempt {attempt + 1}/{max_retries}): {self.username}")
                
                # Add random delay before login
                delay = random.uniform(2, 5)
                self.logger.info(f"Waiting {delay:.1f}s before login...")
                time.sleep(delay)
                
                # Login
                self.client.login(self.username, self.password)
                
                # Verify login
                time.sleep(2)
                self.client.get_timeline_feed()
                
                # Session'ı kaydet
                self.client.dump_settings(str(self.session_file))
                self.logger.info("✅ Instagram login başarılı, session kaydedildi")
                return
                
            except ChallengeRequired as e:
                self.logger.error("⚠️ Instagram challenge gerekiyor (2FA/güvenlik)")
                self.logger.error("Çözüm: Instagram web/mobil'den giriş yap ve 'Bu benim' onayı ver")
                raise Exception("Instagram challenge - manuel onay gerekli") from e
            
            except ClientError as e:
                error_msg = str(e)
                
                # IP blacklist kontrolü
                if "blacklist" in error_msg.lower() or "ip address" in error_msg.lower():
                    self.logger.error("❌ IP adresi Instagram tarafından engellenmiş")
                    self.logger.error("Çözümler:")
                    self.logger.error("1. VPN kullan ve IP değiştir")
                    self.logger.error("2. 24 saat bekle")
                    self.logger.error("3. Instagram web'den giriş yap ve onay ver")
                    self.logger.error("4. Farklı network'e bağlan (mobil data, farklı WiFi)")
                    
                    # Son deneme değilse bekle
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 30  # 30, 60, 90 saniye
                        self.logger.info(f"⏳ {wait_time} saniye bekleniyor...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Instagram IP blacklist - {error_msg}") from e
                
                # Diğer hatalar
                self.logger.error(f"Login hatası: {error_msg}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    self.logger.info(f"⏳ {wait_time} saniye sonra tekrar denenecek...")
                    time.sleep(wait_time)
                else:
                    raise
            
            except Exception as e:
                self.logger.error(f"Login hatası: {e}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    self.logger.info(f"⏳ {wait_time} saniye sonra tekrar denenecek...")
                    time.sleep(wait_time)
                else:
                    raise
        
        raise Exception("Instagram login başarısız - tüm denemeler tükendi")
    
    def upload_reel(
        self,
        video_path: str,
        caption: str,
        thumbnail_path: Optional[str] = None,
        max_retries: int = 3
    ) -> Optional[str]:
        """
        Instagram Reels yükle with retry logic
        
        Args:
            video_path: Video dosya yolu
            caption: Açıklama + hashtag'ler
            thumbnail_path: Kapak resmi (opsiyonel)
            max_retries: Maksimum deneme sayısı
        
        Returns:
            Media code (ID) veya None
        """
        video_path = Path(video_path)
        
        if not video_path.exists():
            self.logger.error(f"Video bulunamadı: {video_path}")
            return None
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Instagram Reels yükleniyor (attempt {attempt + 1}/{max_retries}): {video_path}")
                
                # Add delay before upload to mimic human behavior
                if attempt > 0:
                    delay = random.uniform(5, 10)
                    self.logger.info(f"⏳ {delay:.1f}s bekleniyor...")
                    time.sleep(delay)
                
                # Thumbnail (yoksa None)
                thumb = Path(thumbnail_path) if thumbnail_path else None
                
                # Upload
                media = self.client.clip_upload(
                    path=str(video_path),
                    caption=caption,
                    thumbnail=str(thumb) if thumb and thumb.exists() else None
                )
                
                self.logger.info(f"✅ Instagram Reels yüklendi! Media ID: {media.pk}")
                
                # URL oluştur
                url = f"https://www.instagram.com/reel/{media.code}/"
                self.logger.info(f"🔗 URL: {url}")
                
                # Save session after successful upload
                self.client.dump_settings(str(self.session_file))
                
                return media.code
                
            except LoginRequired:
                self.logger.warning("Session expired, re-logging...")
                try:
                    self._login()
                    # Retry upload after re-login
                    continue
                except Exception as e:
                    self.logger.error(f"Re-login failed: {e}")
                    if attempt == max_retries - 1:
                        return None
            
            except ClientError as e:
                error_msg = str(e)
                self.logger.error(f"Upload error: {error_msg}")
                
                if "spam" in error_msg.lower() or "too many" in error_msg.lower():
                    self.logger.error("⚠️ Instagram spam koruması aktif")
                    self.logger.error("Çözüm: Birkaç saat bekle ve tekrar dene")
                    return None
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 15
                    self.logger.info(f"⏳ {wait_time} saniye sonra tekrar denenecek...")
                    time.sleep(wait_time)
                else:
                    return None
            
            except Exception as e:
                self.logger.error(f"Instagram upload hatası: {e}")
                import traceback
                traceback.print_exc()
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    self.logger.info(f"⏳ {wait_time} saniye sonra tekrar denenecek...")
                    time.sleep(wait_time)
                else:
                    return None
        
        return None
    
    def get_account_info(self) -> Dict:
        """Hesap bilgilerini al"""
        try:
            user = self.client.user_info(self.client.user_id)
            return {
                'username': user.username,
                'full_name': user.full_name,
                'followers': user.follower_count,
                'following': user.following_count,
                'media_count': user.media_count
            }
        except Exception as e:
            self.logger.error(f"Account info error: {e}")
            return {}
    
    def close(self):
        """Session'ı kaydet ve kapat"""
        try:
            self.client.dump_settings(str(self.session_file))
            self.logger.info("✅ Instagram session kaydedildi")
        except Exception as e:
            self.logger.error(f"Session save error: {e}")


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("INSTAGRAM UPLOADER TEST")
    print("="*60)
    
    # Not: Gerçek test için username/password gerekli
    print("\n⚠️ Test için gerçek Instagram hesap bilgileri gerekli")
    print("Kullanım:")
    print("""
uploader = InstagramUploader(
    username="your_username",
    password="your_password"
)

# Upload
media_code = uploader.upload_reel(
    video_path="video.mp4",
    caption="Viral content! #reels #viral"
)

uploader.close()
    """)
