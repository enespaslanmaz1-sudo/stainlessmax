"""
Disk Cleaner - Gereksiz Dosyaları Temizleme
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timedelta


class DiskCleaner:
    """Disk temizlik yöneticisi"""
    
    def __init__(self):
        self.cleaned_size = 0
        self.files_removed = 0
        self.folders_removed = 0
        
        # Temizlenecek klasörler
        self.temp_folders = [
            Path(tempfile.gettempdir()),
            Path.home() / "AppData" / "Local" / "Temp",
            Path.home() / ".cache",
        ]
        
        # Temizlenecek uzantılar
        self.temp_extensions = [
            '.tmp', '.temp', '.log', '.cache',
            '.old', '.bak', '.backup', '.dmp'
        ]
        
        # Edge cache
        self.edge_cache = Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"
    
    def clean_all(self) -> Dict:
        """Tüm temizliği yap"""
        self.cleaned_size = 0
        self.files_removed = 0
        self.folders_removed = 0
        
        results = {
            'temp_files': self._clean_temp_files(),
            'edge_cache': self._clean_edge_cache(),
            'old_logs': self._clean_old_logs(),
            'recycle_bin': self._empty_recycle_bin(),
            'total_cleaned_mb': 0,
            'total_files': 0
        }
        
        results['total_cleaned_mb'] = round(self.cleaned_size / (1024 * 1024), 2)
        results['total_files'] = self.files_removed
        
        return results
    
    def _clean_temp_files(self) -> int:
        """Geçici dosyaları temizle"""
        removed = 0
        
        for folder in self.temp_folders:
            if not folder.exists():
                continue
            
            try:
                for item in folder.iterdir():
                    try:
                        if item.is_file():
                            # 7 günden eski dosyaları sil
                            if self._is_old_file(item, days=7):
                                size = item.stat().st_size
                                item.unlink()
                                self.cleaned_size += size
                                self.files_removed += 1
                                removed += 1
                        
                        elif item.is_dir() and item.name.startswith('tmp'):
                            size = self._get_folder_size(item)
                            shutil.rmtree(item)
                            self.cleaned_size += size
                            self.folders_removed += 1
                            removed += 1
                    except Exception:
                        pass
            except Exception:
                pass
        
        return removed
    
    def _clean_edge_cache(self) -> int:
        """Edge cache temizle"""
        if not self.edge_cache.exists():
            return 0
        
        removed = 0
        try:
            for item in self.edge_cache.iterdir():
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink()
                        self.cleaned_size += size
                        self.files_removed += 1
                        removed += 1
                except Exception:
                    pass
        except Exception:
            pass
        
        return removed
    
    def _clean_old_logs(self) -> int:
        """Eski log dosyalarını temizle"""
        removed = 0
        
        log_paths = [
            Path("logs"),
            Path("temp"),
            Path("__pycache__"),
        ]
        
        for path in log_paths:
            if not path.exists():
                continue
            
            try:
                for item in path.rglob('*'):
                    try:
                        if item.is_file() and self._is_old_file(item, days=30):
                            size = item.stat().st_size
                            item.unlink()
                            self.cleaned_size += size
                            self.files_removed += 1
                            removed += 1
                        elif item.is_dir() and item.name == '__pycache__':
                            size = self._get_folder_size(item)
                            shutil.rmtree(item)
                            self.cleaned_size += size
                            removed += 1
                    except Exception:
                        pass
            except Exception:
                pass
        
        return removed
    
    def _empty_recycle_bin(self) -> int:
        """Çöp kutusunu boşalt"""
        try:
            import winshell
            winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
            return 1
        except Exception:
            return 0
    
    def _is_old_file(self, filepath: Path, days: int = 7) -> bool:
        """Dosya eski mi kontrol et"""
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            return (datetime.now() - mtime) > timedelta(days=days)
        except Exception:
            return False
    
    def _get_folder_size(self, folder: Path) -> int:
        """Klasör boyutunu hesapla"""
        total = 0
        try:
            for item in folder.rglob('*'):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total
    
    def clean_project_files(self) -> Dict:
        """Proje klasörünü temizle"""
        removed_items = []
        
        # Silinecek desenler
        patterns_to_remove = [
            '*.pyc',
            '__pycache__',
            '*.log.old',
            '*.bak',
            'temp/*',
        ]
        
        for pattern in patterns_to_remove:
            for item in Path('.').rglob(pattern):
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink()
                        self.cleaned_size += size
                        removed_items.append(str(item))
                    elif item.is_dir():
                        shutil.rmtree(item)
                        removed_items.append(str(item))
                except Exception:
                    pass
        
        return {
            'removed_count': len(removed_items),
            'removed_items': removed_items[:20],  # İlk 20
            'space_freed_mb': round(self.cleaned_size / (1024 * 1024), 2)
        }
    
    def get_disk_info(self) -> Dict:
        """Disk bilgilerini getir"""
        disk = shutil.disk_usage('/')
        return {
            'total_gb': round(disk.total / (1024**3), 2),
            'used_gb': round(disk.used / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2),
            'usage_percent': round((disk.used / disk.total) * 100, 1)
        }


# Global instance
disk_cleaner = DiskCleaner()
