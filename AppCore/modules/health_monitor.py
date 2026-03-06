"""
Health Monitor - Hesap Sağlığı ve Shadowban Kontrolü
"""

import logging
import time
import os
import random
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Selenium
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Hesapların ban/shadowban durumunu kontrol et"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.screenshots_dir = Path("logs/screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def _init_driver(self):
        """Selenium sürücüsünü başlat (Incognito + Headless) - Edge"""
        try:
            options = EdgeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            
            options.add_argument("--inprivate")  # Edge için Incognito
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--log-level=3")
            
            # Anti-detection flags for Edge
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # User-Agent Spoofing
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            ]
            options.add_argument(f"user-agent={random.choice(user_agents)}")
            
            service = EdgeService(EdgeChromiumDriverManager().install())
            import subprocess
            if service:
                service.creation_flags = subprocess.CREATE_NO_WINDOW
            self.driver = webdriver.Edge(service=service, options=options)
            
            # Additional anti-detection script
            try:
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        })
                    """
                })
            except Exception:
                pass

            logger.info("🕵️ HealthMonitor Edge Driver başlatıldı (InPrivate)")
            
        except Exception as e:
            logger.error(f"Driver başlatma hatası: {e}")
            raise

    def check_tiktok_account(self, username: str, last_video_id: str = None) -> str:
        """
        TikTok hesabını kontrol et
        
        Returns:
            str: Durum ('ACTIVE', 'SHADOWBANNED', 'BANNED', 'UNKNOWN')
        """
        if not self.driver:
            self._init_driver()
            
        url = f"https://www.tiktok.com/@{username}"
        logger.info(f"🔍 TikTok hesabı kontrol ediliyor: {username}")
        
        try:
            self.driver.get(url)
            time.sleep(random.uniform(3, 6))  # Bekle
            
            # 1. Sayfa başlığı kontrolü (404 veya Ban)
            title = self.driver.title
            page_source = self.driver.page_source
            
            if "Couldn't find this account" in page_source or "Hesap bulunamadı" in page_source:
                logger.warning(f"❌ Hesap bulunamadı (Olası Ban): {username}")
                return "BANNED"
                
            # 2. Video listesi kontrolü
            # Video container'ları genellikle 'div[data-e2e="user-post-item"]' selector'ı ile bulunur
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-e2e="user-post-item"]'))
                )
                videos = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-e2e="user-post-item"]')
                
                if not videos:
                    # Video yok ama hesap var -> Yeni hesap veya Shadowban (eğer video yüklendiyse)
                    if "No content" in page_source or "Henüz video yok" in page_source:
                        logger.info("ℹ️ Hesap aktif ama video yok.")
                        return "ACTIVE_NO_CONTENT"
                    else:
                        logger.warning("⚠️ Videolar yüklenemedi (Olası Shadowban)")
                        return "SHADOWBANNED_SUSPECT"
                
                logger.info(f"✅ Hesap aktif. {len(videos)} video görüldü.")
                
                # Son yüklenen video kontrolü (Last Video Check)
                if last_video_id:
                    found = False
                    for video in videos[:3]: # Son 3 videoya bak
                        try:
                            video_link = video.find_element(By.TAG_NAME, 'a').get_attribute('href')
                            if last_video_id in video_link:
                                found = True
                                logger.info(f"✅ Son yüklenen video doğrulandı: {last_video_id}")
                                break
                        except Exception:
                            pass
                            
                    if not found and len(videos) > 0:
                        logger.warning(f"⚠️ Son yüklenen video ({last_video_id}) profilde görünmüyor! (SHADOWBAN İHTİMALİ)")
                        return "SHADOWBANNED"
                
                return "ACTIVE"
                
            except Exception as e:
                # Video bulunamadı timeout
                if "No content" in page_source:
                     return "ACTIVE_NO_CONTENT"
                logger.warning(f"Video listesi alınamadı: {e}")
                return "UNKNOWN"

        except Exception as e:
            logger.error(f"Kontrol hatası: {e}")
            screenshot_path = self.screenshots_dir / f"error_{username}_{int(time.time())}.png"
            self.driver.save_screenshot(str(screenshot_path))
            return "ERROR"

    def mark_account_as_banned(self, account_data: str, file_path: str = "hesaplar.txt"):
        """hesaplar.txt dosyasına BANLI etiketini ekle"""
        try:
            target_path = Path(file_path)
            if not target_path.exists():
                return
            
            lines = target_path.read_text(encoding='utf-8').splitlines()
            new_lines = []
            updated = False
            
            for line in lines:
                new_lines.append(line)
                if account_data in line and "BANLI" not in line:
                    # Hesabın bulunduğu satırın altına veya yanına ekle
                    # Basitlik için altına ekliyoruz
                    new_lines.append(f"# ❌ BU HESAP BANLANDI ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
                    updated = True
            
            if updated:
                target_path.write_text('\n'.join(new_lines), encoding='utf-8')
                logger.info(f"✍️ hesaplar.txt güncellendi: {account_data} -> BANLI işaretlendi")
                
        except Exception as e:
            logger.error(f"Dosya güncelleme hatası: {e}")

    def close(self):
        if self.driver:
            self.driver.quit()
            logger.info("👋 Driver kapatıldı")

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    monitor = HealthMonitor(headless=False)
    try:
        # Örnek TikTok hesabı kontrolü (Mevcut bir hesap)
        status = monitor.check_tiktok_account("tiktok") # tiktok resmi hesabı
        print(f"Durum: {status}")
        
        # Olmayan hesap
        status_fake = monitor.check_tiktok_account("buhesapkesinyoktur123456")
        print(f"Durum (Fake): {status_fake}")
        
    finally:
        monitor.close()
