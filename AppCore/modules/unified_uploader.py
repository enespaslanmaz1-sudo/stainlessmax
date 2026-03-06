"""
Unified Uploader - YouTube ve TikTok için yükleme orchestrator
"""

import logging
import re
from pathlib import Path
from typing import Optional, Dict
from .account_manager import AccountManager
from .youtube_uploader import YouTubeUploader
from .multi_uploader import MultiUploader

# Try importing socket manager safely
try:
    from AppCore.lib.socket_manager import emit_safe
except ImportError:
    # Fallback if run standalone
    def emit_safe(event, data): pass


class UnifiedUploader:
    """YouTube ve TikTok için birleşik yükleme sistemi"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.account_manager = AccountManager()
        
        self.youtube_uploader = YouTubeUploader()
        self.tiktok_uploader = None
        
        self.authenticated_youtube = {}  # account_id -> bool

    def _normalize_channel_name(self, value: str) -> str:
        """Kanal adını güvenli karşılaştırma için normalize et"""
        if not value:
            return ""
        normalized = value.strip().lower()
        normalized = re.sub(r"[^a-z0-9çğıöşü\s]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _get_expected_channel_name(self, account) -> str:
        """Hesaptan beklenen kanal adını çıkar"""
        if getattr(account, "name", ""):
            return account.name.strip()

        notes = (getattr(account, "notes", "") or "").strip()
        if ":" in notes:
            return notes.split(":", 1)[1].strip()

        return notes

    def _validate_youtube_channel(self, account) -> Dict:
        """Auth olan YouTube kanalının doğru hesaba ait olduğunu doğrula"""
        channel_info = self.youtube_uploader.get_channel_info()
        if not channel_info:
            return {
                "success": False,
                "error": "YouTube kanal bilgisi alınamadı."
            }

        actual_title = (channel_info.get("snippet", {}) or {}).get("title", "")
        actual_id = channel_info.get("id", "")
        expected_title = self._get_expected_channel_name(account)

        norm_actual = self._normalize_channel_name(actual_title)
        norm_expected = self._normalize_channel_name(expected_title)

        is_match = True
        if norm_expected:
            is_match = (
                norm_expected == norm_actual
                or norm_expected in norm_actual
                or norm_actual in norm_expected
            )

        if not is_match:
            token_file = self.youtube_uploader.credentials_dir / f"{account.id}_token.pickle"
            try:
                if token_file.exists():
                    token_file.unlink()
                    self.logger.warning(f"Yanlış token silindi: {token_file}")
            except Exception as token_err:
                self.logger.warning(f"Token silinemedi ({account.id}): {token_err}")

            self.authenticated_youtube.pop(account.id, None)

            error_msg = (
                f"Yanlış YouTube hesabı ile giriş yapıldı. "
                f"Beklenen kanal: '{expected_title}', aktif kanal: '{actual_title}' (ID: {actual_id}). "
                f"Lütfen {account.id} için doğru Google hesabıyla tekrar OAuth yapın."
            )
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "expected_channel": expected_title,
                "actual_channel": actual_title,
                "actual_channel_id": actual_id
            }

        self.logger.info(
            f"YouTube kanal doğrulandı: account={account.id}, channel='{actual_title}' ({actual_id})"
        )
        return {
            "success": True,
            "channel_title": actual_title,
            "channel_id": actual_id
        }
    
    def upload_to_account(self,
                         account_id: str,
                         video_path: Path,
                         title: str,
                         description: str = "",
                         tags: list = None,
                         schedule_time: str = None,
                         progress_callback=None) -> Dict:
        """
        Belirli bir hesaba video yükle
        
        Args:
            account_id: Hesap ID
            video_path: Video dosya yolu
            title: Video başlığı
            description: Açıklama
            tags: Etiketler
            schedule_time: ISO formatında planlanan zaman (Opsiyonel)
            
        Returns:
            Dict: Sonuç bilgisi
        """
        account = self.account_manager.get_account(account_id)
        
        if not account:
            return {
                "success": False,
                "error": f"Hesap bulunamadı: {account_id}"
            }
        
        if not account.active:
            return {
                "success": False,
                "error": f"Hesap pasif: {account_id}"
            }
        
        # Platform'a göre yönlendir
        if account.platform == "youtube":
            return self._upload_youtube(account, video_path, title, description, tags, schedule_time, progress_callback)
        elif account.platform == "tiktok":
            return self._upload_tiktok(account, video_path, title, description, tags, schedule_time, progress_callback)
        else:
            return {
                "success": False,
                "error": f"Bilinmeyen platform: {account.platform}"
            }
    
    def _upload_youtube(self, account, video_path, title, description, tags, schedule_time=None, progress_callback=None):
        """YouTube'a yükle"""
        try:
            # OAuth auth gerekli mi?
            needs_auth = (
                account.id not in self.authenticated_youtube
                or self.youtube_uploader.current_account != account.id
                or self.youtube_uploader.youtube is None
            )

            if needs_auth:
                if not account.client_id or not account.client_secret:
                    return {
                        "success": False,
                        "error": "YouTube OAuth bilgileri eksik"
                    }

                self.logger.info(f"YouTube auth başlatılıyor: {account.id}")

                success = self.youtube_uploader.authenticate(
                    account_id=account.id,
                    client_id=account.client_id,
                    client_secret=account.client_secret
                )

                if not success:
                    return {
                        "success": False,
                        "error": "YouTube authentication başarısız"
                    }

                self.authenticated_youtube[account.id] = True

            # Yanlış kanala yükleme riskini engelle
            channel_validation = self._validate_youtube_channel(account)
            if not channel_validation.get("success"):
                return channel_validation

            # Video yükle
            video_id = self.youtube_uploader.upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags or [],
                publishAt=schedule_time,
                progress_callback=progress_callback
            )
            
            if video_id:
                # Hesap istatistiklerini güncelle
                self.account_manager.update_last_used(account.id)
                self.account_manager.increment_video_count(account.id)
                
                # Emit Success Notification
                emit_safe('notification', {
                    "type": "upload",
                    "title": "Video Yüklendi! 🚀",
                    "message": f"YouTube: {title}",
                    "platform": "youtube",
                    "timestamp": "Şimdi"
                })
                
                return {
                    "success": True,
                    "platform": "youtube",
                    "account_id": account.id,
                    "video_id": video_id,
                    "video_url": f"https://www.youtube.com/watch?v={video_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "YouTube yükleme başarısız"
                }
                
        except Exception as e:
            self.logger.error(f"YouTube yükleme hatası: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def _upload_tiktok(self, account, video_path, title, description, tags, schedule_time=None, progress_callback=None):
        """TikTok'a yükle"""
        try:
            # TikTok uploader'ı oluştur (email/password ile)
            if not self.tiktok_uploader:
                self.tiktok_uploader = MultiUploader(
                    headless=True,  # Arka planda görünmez tarayıcı
                    email=account.email,
                    password=account.password
                )
            
            # Profile path oluştur
            profile_path = self.account_manager.get_profile_path(account.id)
            self.account_manager.create_profile(account.id)
            
            # Bağlan
            if not self.tiktok_uploader.connect(account.id, profile_path):
                return {
                    "success": False,
                    "error": "TikTok bağlantısı başarısız"
                }
            
            # Yükle
            success = self.tiktok_uploader.upload_tiktok(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags or [],
                schedule_time=schedule_time, # YENİ
                progress_callback=progress_callback
            )
            
            # Disconnect
            self.tiktok_uploader.disconnect()
            
            if success:
                # Hesap istatistiklerini güncelle
                self.account_manager.update_last_used(account.id)
                self.account_manager.increment_video_count(account.id)
                
                # Emit Success Notification
                emit_safe('notification', {
                    "type": "upload",
                    "title": "Video Yüklendi! 🎵",
                    "message": f"TikTok: {title}",
                    "platform": "tiktok",
                    "timestamp": "Şimdi"
                })
                
                return {
                    "success": True,
                    "platform": "tiktok",
                    "account_id": account.id
                }
            else:
                detailed_error = "TikTok yükleme başarısız"
                try:
                    if getattr(self.tiktok_uploader, "last_error_reason", ""):
                        detailed_error = self.tiktok_uploader.last_error_reason
                except Exception:
                    pass

                return {
                    "success": False,
                    "error": detailed_error
                }
                
        except Exception as e:
            self.logger.error(f"TikTok yükleme hatası: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            
            # Emit error to socket if available
            try:
                from AppCore.lib.socket_manager import emit_safe
                emit_safe('log', {'data': f'❌ TikTok Upload Hatası: {str(e)}'})
            except Exception:
                pass
            
            # Cleanup
            if self.tiktok_uploader:
                self.tiktok_uploader.disconnect()
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def upload_to_all_active(self, video_path: Path, title: str, 
                            description: str = "", tags: list = None) -> list:
        """
        Tüm aktif hesaplara yükle
        
        Returns:
            list: Her hesap için sonuç dict'i
        """
        results = []
        active_accounts = self.account_manager.get_active_accounts()
        
        self.logger.info(f"{len(active_accounts)} aktif hesaba yükleme başlatılıyor...")
        
        for account in active_accounts:
            self.logger.info(f"Yükleniyor: {account.name or account.id} ({account.platform})")
            
            result = self.upload_to_account(
                account_id=account.id,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags
            )
            
            result["account_name"] = account.name or account.id
            results.append(result)
        
        return results


# Test için
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    uploader = UnifiedUploader()
    
    # Aktif hesapları göster
    active_accounts = uploader.account_manager.get_active_accounts()
    print(f"\n=== {len(active_accounts)} Aktif Hesap ===")
    for acc in active_accounts:
        print(f"  - {acc.name or acc.id} ({acc.platform})")
