"""
Account Manager - Multi-Platform Account Management
YouTube + TikTok account handling
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

HESAPLAR_AVAILABLE = True


@dataclass
class Account:
    """Account data model"""
    id: str
    platform: str  # youtube, tiktok
    niche: str = "general"
    email: str = ""
    password: str = ""
    profile_path: str = ""
    active: bool = True
    created_at: str = ""
    last_used: str = ""
    total_videos: int = 0
    total_views: int = 0  # Added for dashboard stats
    total_likes: int = 0  # Added for dashboard stats
    notes: str = ""
    # YouTube OAuth bilgileri
    client_id: str = ""
    client_secret: str = ""
    name: str = ""  # Hesap görünen adı
    username: str = "" # Added to support legacy parsers


class AccountManager:
    """Manage multiple accounts for YouTube and TikTok"""
    
    def __init__(self, config_path: str = "config/accounts.json"):
        self.config_path = Path(config_path)
        self.accounts: List[Account] = []
        self.load_accounts()
    
    def load_accounts(self):
        """Load accounts from JSON or hesaplar.txt"""
        # Önce hesaplar.txt'yi kontrol et
        base_dir = Path(__file__).parent.parent
        hesaplar_txt = base_dir / "hesaplar.txt"
        if hesaplar_txt.exists():
            print("[AccountManager] hesaplar.txt bulundu, parse ediliyor...")
            if self.load_from_hesaplar_txt():
                return
        
        # hesaplar.txt yoksa veya parse başarısızsa, JSON config kullan
        if not self.config_path.exists():
            self._create_default_accounts()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            accounts_data = data.get("accounts", [])
            self.accounts = []
            for acc_data in accounts_data:
                # Filter only valid accounts
                if all(k in acc_data for k in ["id", "platform", "niche", "email"]):
                    # Eksik alanları varsayılan değerlerle doldur
                    acc_data.setdefault("client_id", "")
                    acc_data.setdefault("client_secret", "")
                    acc_data.setdefault("name", "")
                    self.accounts.append(Account(**acc_data))
        except Exception as e:
            print(f"[AccountManager] Error loading accounts: {e}")
            self._create_default_accounts()
    
    def load_from_hesaplar_txt(self) -> bool:
        """Load accounts from hesaplar.txt file"""
        try:
            from .hesaplar_parser import HesaplarParser
            
            base_dir = Path(__file__).parent.parent
            hesaplar_txt_path = base_dir / "hesaplar.txt"
            
            parser = HesaplarParser(str(hesaplar_txt_path))
            if not parser.parse():
                return False
            
            # Parse edilen hesapları Account nesnelerine dönüştür
            self.accounts = []
            all_accounts = parser.get_all_accounts()
            
            for acc_data in all_accounts:
                # Eksik alanları ekle
                acc_data.setdefault("password", "")
                acc_data.setdefault("profile_path", "")
                acc_data.setdefault("client_id", "")
                acc_data.setdefault("client_secret", "")
                acc_data.setdefault("name", "")
                acc_data.setdefault("username", "")
                
                self.accounts.append(Account(**acc_data))
            
            # Config dosyasına da kaydet
            self.save_accounts()
            
            print(f"[AccountManager] {len(self.accounts)} hesap yüklendi (hesaplar.txt)")
            return True
            
        except Exception as e:
            print(f"[AccountManager] hesaplar.txt parse hatası: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_default_accounts(self):
        """Create default account configuration"""
        default_accounts = [
            {
                "id": "youtube_tech",
                "platform": "youtube",
                "niche": "technology",
                "email": "",
                "password": "",
                "active": False
            },
            {
                "id": "tiktok_main",
                "platform": "tiktok",
                "niche": "entertainment",
                "email": "",
                "password": "",
                "active": False
            }
        ]
        
        config = {
            "version": "2.0",
            "created_at": "2026-02-05",
            "accounts": default_accounts
        }
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        
        self.load_accounts()
    
    def save_accounts(self):
        """Save accounts to JSON"""
        try:
            config = {
                "version": "2.0",
                "updated_at": "2026-02-05",
                "accounts": [asdict(acc) for acc in self.accounts]
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[AccountManager] Error saving accounts: {e}")
            return False
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """Get account by ID"""
        return next((a for a in self.accounts if a.id == account_id), None)
    
    def get_active_accounts(self, platform: str = None) -> List[Account]:
        """Get all active accounts"""
        accounts = [a for a in self.accounts if a.active]
        if platform:
            accounts = [a for a in accounts if a.platform == platform]
        return accounts
    
    def add_account(self, account: Account) -> bool:
        """Add new account"""
        if self.get_account(account.id):
            return False
        
        self.accounts.append(account)
        return self.save_accounts()
    
    def toggle_account(self, account_id: str) -> bool:
        """Toggle account active status"""
        account = self.get_account(account_id)
        if account:
            account.active = not account.active
            return self.save_accounts()
        return False
    
    def delete_account(self, account_id: str) -> bool:
        """Delete account by ID"""
        initial_len = len(self.accounts)
        self.accounts = [a for a in self.accounts if a.id != account_id]
        
        if len(self.accounts) < initial_len:
            return self.save_accounts()
        return False
    
    def update_last_used(self, account_id: str):
        """Update account last used timestamp"""
        from datetime import datetime
        account = self.get_account(account_id)
        if account:
            account.last_used = datetime.now().isoformat()
            self.save_accounts()
    
    def increment_video_count(self, account_id: str):
        """Increment account video count"""
        account = self.get_account(account_id)
        if account:
            account.total_videos += 1
            self.save_accounts()
    
    def get_profile_path(self, account_id: str) -> Path:
        """Get Chrome profile path for account"""
        base_path = Path("profiles")
        return base_path / account_id
    
    def create_profile(self, account_id: str) -> bool:
        """Create profile directory for account"""
        profile_path = self.get_profile_path(account_id)
        try:
            profile_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"[AccountManager] Error creating profile: {e}")
            return False
