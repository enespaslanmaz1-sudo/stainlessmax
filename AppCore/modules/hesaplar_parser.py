"""
hesaplar.txt Parser - YouTube ve TikTok hesap bilgilerini parse eder
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class YouTubeAccount:
    """YouTube hesap bilgileri"""
    name: str
    client_id: str
    client_secret: str
    platform: str = "youtube"
    active: bool = True
    created_at: str = ""
    
    def to_dict(self):
        # ID'yi URL-safe hale getir (boşlukları alt çizgi ile değiştir, küçük harf)
        safe_id = self.name.lower().replace(" ", "_").replace("'", "")
        return {
            "id": f"youtube_{safe_id}",  # youtube_future_lab
            "name": self.name,
            "platform": self.platform,
            "niche": "general",
            "email": "",
            "username": "",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "active": self.active,
            "created_at": self.created_at or datetime.now().isoformat(),
            "last_used": "",
            "total_videos": 0,
            "notes": f"YouTube kanal: {self.name}"
        }


@dataclass
class TikTokAccount:
    """TikTok hesap bilgileri"""
    email: str
    password: str
    name: str = "The Power of Money" # Default name
    platform: str = "tiktok"
    active: bool = True
    created_at: str = ""
    
    def to_dict(self):
        # ID'yi URL-safe hale getir
        safe_id = self.name.lower().replace(" ", "_").replace("'", "")
        return {
            "id": f"tiktok_{safe_id}",  # tiktok_the_power_of_money
            "name": self.name,
            "platform": self.platform,
            "niche": "finance", # Updated niche to finance
            "email": self.email,
            "password": self.password,
            "username": self.email.split('@')[0] if '@' in self.email else self.name,
            "active": self.active,
            "created_at": self.created_at or datetime.now().isoformat(),
            "last_used": "",
            "total_videos": 0,
            "notes": f"TikTok hesabı - {self.name}"
        }


class HesaplarParser:
    """hesaplar.txt dosyasını parse eder"""
    
    def __init__(self, filepath: str = "hesaplar.txt"):
        self.filepath = Path(filepath)
        self.youtube_accounts: List[YouTubeAccount] = []
        self.tiktok_accounts: List[TikTokAccount] = []
    
    def parse(self) -> bool:
        """
        hesaplar.txt dosyasını parse et
        
        Returns:
            bool: Parse işlemi başarılı mı?
        """
        if not self.filepath.exists():
            print(f"[HesaplarParser] Dosya bulunamadı: {self.filepath}")
            return False
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # YouTube hesaplarını parse et
            self._parse_youtube(content)
            
            # TikTok hesabını parse et
            self._parse_tiktok(content)
            
            print(f"[HesaplarParser] Parse başarılı: {len(self.youtube_accounts)} YouTube, "
                  f"{len(self.tiktok_accounts)} TikTok")
            
            return True
            
        except Exception as e:
            print(f"[HesaplarParser] Parse hatası: {e}")
            return False
    
    def _parse_youtube(self, content: str):
        """YouTube hesaplarını parse et"""
        # YouTube bölümünü bul
        youtube_section = re.search(r'youtube:(.*?)(?:tiktok:|$)', content, re.DOTALL | re.IGNORECASE)
        
        if not youtube_section:
            print("[HesaplarParser] YouTube bölümü bulunamadı")
            return
        
        youtube_text = youtube_section.group(1)
        
        # Her hesabı bul (isim, id, secret üçlüsü)
        # Pattern: herhangi bir text -> ıd: -> secret: formatı
        lines = youtube_text.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Boş satırları atla
            if not line:
                i += 1
                continue
            
            # Eğer bu satır 'ıd:' veya 'secret:' başlıyorsa, atla (bu bir hesap adı değil)
            if line.startswith('ıd:') or line.startswith('id:') or line.startswith('secret:'):
                i += 1
                continue
            
            # Bu bir hesap adı olabilir
            account_name = line
            
            # Sonraki satırları kontrol et (id ve secret)
            client_id = None
            client_secret = None
            
            # İleriye bak
            j = i + 1
            while j < len(lines) and j < i + 5:  # Maksimum 5 satır ileriye bak
                next_line = lines[j].strip()
                
                # ID satırı mı?
                id_match = re.search(r'^[ıi]d:\s*(.+)$', next_line, re.IGNORECASE)
                if id_match:
                    client_id = id_match.group(1).strip()
                
                # Secret satırı mı?
                secret_match = re.search(r'^secret:\s*(.+)$', next_line, re.IGNORECASE)
                if secret_match:
                    client_secret = secret_match.group(1).strip()
                
                # Her ikisi de bulunduysa, hesabı ekle
                if client_id and client_secret:
                    youtube_account = YouTubeAccount(
                        name=account_name,
                        client_id=client_id,
                        client_secret=client_secret
                    )
                    self.youtube_accounts.append(youtube_account)
                    print(f"[HesaplarParser] YouTube hesabı eklendi: {account_name}")
                    i = j  # İmleci ilerlet
                    break
                
                j += 1
            
            i = j + 1 if client_id and client_secret else i + 1 # Move i past the found account or just to the next line if not found
    
    def _parse_tiktok(self, content: str):
        """TikTok hesaplarını parse et"""
        # TikTok bölümünü bul
        # Sıralama: YouTube -> TikTok (End of file)
        tiktok_section = re.search(r'tiktok:(.*?)$', content, re.DOTALL | re.IGNORECASE)
        
        if not tiktok_section:
            print("[HesaplarParser] TikTok bölümü bulunamadı")
            return
        
        tiktok_text = tiktok_section.group(1)
        lines = tiktok_text.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Boş satırları atla
            if not line:
                i += 1
                continue
                
            # E-posta veya şifre satırıysa atla (bunlar hesap adı değil)
            if line.lower().startswith('e-posta:') or line.lower().startswith('şifre:') or line.lower().startswith('sifre:'):
                i += 1
                continue
                
            # Bu bir hesap adı olabilir
            account_name = line
            
            email = None
            password = None
            
            # İleriye bak (max 5 satır)
            j = i + 1
            while j < len(lines) and j < i + 6:
                next_line = lines[j].strip()
                
                # E-posta
                if not email:
                    email_match = re.search(r'e-posta:\s*(.+)', next_line, re.IGNORECASE)
                    if email_match:
                        email = email_match.group(1).strip()
                    
                # Şifre
                if not password:
                    pass_match = re.search(r'[şs]ifre:\s*(.+)', next_line, re.IGNORECASE)
                    if pass_match:
                        password = pass_match.group(1).strip()
                    
                if email and password:
                    account = TikTokAccount(
                        name=account_name,
                        email=email,
                        password=password
                    )
                    self.tiktok_accounts.append(account)
                    print(f"[HesaplarParser] TikTok hesabı eklendi: {account.name}")
                    i = j
                    break
                j += 1
            
            i = j + 1 if email and password else i + 1 # Move i past the found account or just to the next line if not found

    def get_all_accounts(self) -> List[Dict]:
        """
        Tüm hesapları dict formatında döndür
        
        Returns:
            List[Dict]: Account manager için uygun formatta hesap listesi
        """
        accounts = []
        
        # YouTube hesaplarını ekle
        for yt_account in self.youtube_accounts:
            accounts.append(yt_account.to_dict())
        
        # TikTok hesaplarını ekle
        for tt_account in self.tiktok_accounts:
            accounts.append(tt_account.to_dict())
        
        return accounts
    
    def get_youtube_accounts(self) -> List[YouTubeAccount]:
        """YouTube hesaplarını döndür"""
        return self.youtube_accounts
    
    def get_tiktok_accounts(self) -> List[TikTokAccount]:
        """Tüm TikTok hesaplarını döndür"""
        return self.tiktok_accounts


# Test için
if __name__ == "__main__":
    import os
    
    # Ana dizine git
    os.chdir(Path(__file__).parent.parent.parent)
    
    parser = HesaplarParser("hesaplar.txt")
    if parser.parse():
        print("\n=== PARSE SONUÇLARI ===")
        print(f"YouTube hesapları: {len(parser.youtube_accounts)}")
        for yt in parser.youtube_accounts:
            print(f"  - {yt.name}")
        
        if parser.tiktok_accounts:
            for tt in parser.tiktok_accounts:
                print(f"TikTok: {tt.email}")
        
        print("\n=== TÜM HESAPLAR (DICT) ===")
        import json
        print(json.dumps(parser.get_all_accounts(), indent=2, ensure_ascii=False))
