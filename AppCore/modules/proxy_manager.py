"""
Proxy Manager - Proxy Rotasyonu ve Yönetimi
"""

import random
import requests
from typing import List, Optional, Dict
from pathlib import Path
import json


class ProxyManager:
    """Proxy yönetimi"""
    
    def __init__(self, config_path: str = "config/proxies.json"):
        self.config_path = Path(config_path)
        self.proxies: List[Dict] = []
        self.current_index = 0
        self.enabled = False
        
        self.load_proxies()
    
    def load_proxies(self):
        """Proxy listesini yükle"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.proxies = data.get('proxies', [])
                    self.enabled = data.get('enabled', False)
            except Exception as e:
                print(f"[Proxy] Yükleme hatası: {e}")
    
    def save_proxies(self):
        """Proxy listesini kaydet"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump({
                    'enabled': self.enabled,
                    'proxies': self.proxies
                }, f, indent=4)
        except Exception as e:
            print(f"[Proxy] Kaydetme hatası: {e}")
    
    def add_proxy(self, host: str, port: int, username: str = None, 
                  password: str = None, proxy_type: str = "http") -> bool:
        """Yeni proxy ekle"""
        proxy = {
            'host': host,
            'port': port,
            'username': username,
            'password': password,
            'type': proxy_type,
            'working': True,
            'last_tested': None
        }
        
        self.proxies.append(proxy)
        self.save_proxies()
        return True
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Sonraki proxy'yi al"""
        if not self.proxies or not self.enabled:
            return None
        
        # Round-robin
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        
        return proxy
    
    def get_random_proxy(self) -> Optional[Dict]:
        """Rastgele proxy al"""
        if not self.proxies or not self.enabled:
            return None
        
        return random.choice(self.proxies)
    
    def get_proxy_dict(self, proxy: Dict) -> Dict:
        """Proxy'yi requests formatına çevir"""
        if not proxy:
            return {}
        
        host = proxy['host']
        port = proxy['port']
        proxy_type = proxy.get('type', 'http')
        
        if proxy.get('username') and proxy.get('password'):
            auth = f"{proxy['username']}:{proxy['password']}@"
        else:
            auth = ""
        
        proxy_url = f"{proxy_type}://{auth}{host}:{port}"
        
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    def test_proxy(self, proxy: Dict) -> bool:
        """Proxy çalışıyor mu test et"""
        try:
            proxy_dict = self.get_proxy_dict(proxy)
            response = requests.get(
                'https://api.ipify.org',
                proxies=proxy_dict,
                timeout=10
            )
            
            if response.status_code == 200:
                proxy['working'] = True
                proxy['last_tested'] = __import__('datetime').datetime.now().isoformat()
                return True
            
        except Exception:
            pass
        
        proxy['working'] = False
        return False
    
    def test_all_proxies(self) -> Dict:
        """Tüm proxy'leri test et"""
        results = {'working': 0, 'failed': 0}
        
        for proxy in self.proxies:
            if self.test_proxy(proxy):
                results['working'] += 1
            else:
                results['failed'] += 1
        
        self.save_proxies()
        return results
    
    def remove_proxy(self, index: int) -> bool:
        """Proxy sil"""
        if 0 <= index < len(self.proxies):
            self.proxies.pop(index)
            self.save_proxies()
            return True
        return False
    
    def toggle(self) -> bool:
        """Proxy kullanımını aç/kapat"""
        self.enabled = not self.enabled
        self.save_proxies()
        return self.enabled
    
    def get_stats(self) -> Dict:
        """Proxy istatistikleri"""
        working = sum(1 for p in self.proxies if p.get('working', False))
        return {
            'total': len(self.proxies),
            'working': working,
            'failed': len(self.proxies) - working,
            'enabled': self.enabled
        }


# Global instance
proxy_manager = ProxyManager()
