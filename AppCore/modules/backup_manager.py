"""
Backup Manager - Hesap ve Veri Yedekleme
"""

import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Optional


class BackupManager:
    """Yedekleme yöneticisi"""
    
    def __init__(self, backup_path: str = "backup"):
        self.backup_path = Path(backup_path)
        self.backup_path.mkdir(parents=True, exist_ok=True)
        
        self.items_to_backup = [
            "config/accounts.json",
            "config/scheduler.json",
            "database",
            "profiles"
        ]
    
    def create_backup(self, name: str = None) -> str:
        """Yedek oluştur"""
        if not name:
            name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_file = self.backup_path / f"{name}.zip"
        
        try:
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for item in self.items_to_backup:
                    item_path = Path(item)
                    if item_path.exists():
                        if item_path.is_dir():
                            for file_path in item_path.rglob("*"):
                                if file_path.is_file():
                                    arcname = file_path.relative_to(Path.cwd())
                                    zf.write(file_path, arcname)
                        else:
                            zf.write(item_path, item_path)
            
            print(f"[Backup] Yedek oluşturuldu: {backup_file}")
            return str(backup_file)
            
        except Exception as e:
            print(f"[Backup] Hata: {e}")
            return None
    
    def restore_backup(self, backup_file: str) -> bool:
        """Yedekten geri yükle"""
        try:
            backup_path = Path(backup_file)
            if not backup_path.exists():
                print(f"[Backup] Dosya bulunamadı: {backup_file}")
                return False
            
            with zipfile.ZipFile(backup_path, 'r') as zf:
                # Önce mevcutları yedekle
                self._backup_current()
                
                # Yeni yedeği çıkar
                zf.extractall(Path.cwd())
            
            print(f"[Backup] Geri yükleme tamamlandı: {backup_file}")
            return True
            
        except Exception as e:
            print(f"[Backup] Geri yükleme hatası: {e}")
            return False
    
    def _backup_current(self):
        """Mevcut durumu yedekle"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"auto_before_restore_{timestamp}"
        self.create_backup(backup_name)
    
    def list_backups(self) -> List[dict]:
        """Yedekleri listele"""
        backups = []
        
        for backup_file in self.backup_path.glob("*.zip"):
            stat = backup_file.stat()
            backups.append({
                'name': backup_file.stem,
                'path': str(backup_file),
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'created': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        return sorted(backups, key=lambda x: x['created'], reverse=True)
    
    def delete_backup(self, backup_name: str) -> bool:
        """Yedek sil"""
        try:
            backup_file = self.backup_path / f"{backup_name}.zip"
            if backup_file.exists():
                backup_file.unlink()
                return True
            return False
        except Exception as e:
            print(f"[Backup] Silme hatası: {e}")
            return False
    
    def auto_backup(self):
        """Otomatik yedekleme"""
        # Her gün bir yedek
        daily_backup = f"daily_{datetime.now().strftime('%Y%m%d')}"
        
        # Maksimum 7 günlük yedek tut
        self._cleanup_old_backups(7)
        
        return self.create_backup(daily_backup)
    
    def _cleanup_old_backups(self, keep_days: int):
        """Eski yedekleri temizle"""
        cutoff = datetime.now() - __import__('datetime').timedelta(days=keep_days)
        
        for backup_file in self.backup_path.glob("daily_*.zip"):
            modified = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if modified < cutoff:
                backup_file.unlink()
                print(f"[Backup] Eski yedek silindi: {backup_file.name}")


# Global instance
backup_manager = BackupManager()
