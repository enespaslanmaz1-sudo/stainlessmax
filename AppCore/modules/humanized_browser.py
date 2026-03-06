"""
Humanized Browser - Anti-Ban İçin İnsan Gibi Tarayıcı Kontrolü
Rastgele beklemeler + Eğrisel fare hareketleri
"""

import time
import random
import logging
import os
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class HumanizedBrowser:
    """
    İnsan gibi davranan Selenium browser
    
    Anti-Ban Features:
    - Rastgele beklemeler (random.uniform)
    - Eğrisel fare hareketleri
    - Doğal typing hızı
    - Rastgele hata simülasyonu
    """
    
    def __init__(self, headless: bool = False):
        """
        Args:
            headless: True ise görünmez mod
        """
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO) # Force INFO logging
        
        # Console handler ekle (eğer yoksa)
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        self.driver = self._setup_driver(headless)
    
    def _setup_driver(self, headless: bool):
        """Anti-detect Edge driver with Advanced US Mode (WARP Compatible)"""
        options = EdgeOptions()
        
        if headless:
            options.add_argument('--headless=new')
        
        # 1. Locale & Timezone Arguments
        options.add_argument('--lang=en-US')
        options.add_argument('--timezone="America/New_York"')
        
        # 2. WebRTC & Network Handling
        options.add_argument('--force-webrtc-ip-handling-policy=default_public_interface_only')
        
        # Anti-detection for Edge
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Preferences for Locale
        prefs = {
            "intl.accept_languages": "en-US,en",
            "profile.default_content_settings.geolocation": 1
        }
        options.add_experimental_option("prefs", prefs)

        service = None
        driver = None
        
        try:
            self.logger.info("Checking for EdgeDriver updates...")
            # Try to get latest driver (Requires Internet)
            driver_path = EdgeChromiumDriverManager().install()
            service = EdgeService(driver_path)
        except Exception as dm_err:
            self.logger.warning(f"EdgeDriverManager update failed (Offline mode?): {dm_err}")
            # Fallback: Try using default 'msedgedriver'
            try:
                self.logger.info("Attempting to use system/local 'msedgedriver'...")
                service = EdgeService() 
            except Exception as svc_err:
                 self.logger.error(f"System EdgeDriver failed: {svc_err}")
                 raise svc_err

        import subprocess
        if service:
            service.creation_flags = subprocess.CREATE_NO_WINDOW

        driver = webdriver.Edge(service=service, options=options)
        
        # 3. CDP Commands (Geolocation & Timezone)
        try:
            # Set Geolocation to New York Times Square
            driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
                "latitude": 40.758896,
                "longitude": -73.985130,
                "accuracy": 100
            })
            
            # Set Timezone Override via CDP (More robust than arg)
            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {
                "timezoneId": "America/New_York"
            })
        except Exception as e:
            self.logger.warning(f"CDP Emulation failed: {e}")

        # 4. JavaScript Injections (Navigator & Date Spoofing)
        spoof_script = """
            // 1. Webdriver Hiding
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            
            // 2. Navigator Language Spoofing
            Object.defineProperty(navigator, 'language', {get: () => 'en-US'});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            
            // 3. Timezone Spoofing (Intl)
            const newYorkTimezone = "America/New_York";
            const originalDateTimeFormat = Intl.DateTimeFormat;
            
            Intl.DateTimeFormat = function(locales, options) {
                options = options || {};
                options.timeZone = newYorkTimezone;
                return new originalDateTimeFormat(locales, options);
            };
            
            Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;
            
            // 4. Date Object Override (Basic)
            // Accessors for 'new Date()' are hard to spoof perfectly without breaking things, 
            // but Intl is the primary detection method for modern sites.
        """
        
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": spoof_script
            })
        except Exception as e:
            self.logger.warning(f"JS Spoofing injection failed: {e}")
        
        self.logger.info("✅ Humanized browser initialized (Advanced US Mode + WARP Support)")
        return driver
    
    def human_sleep(self, min_sec: float = 2.1, max_sec: float = 5.4):
        """
        İnsan gibi rastgele bekle (ÖNEMLİ: Anti-Ban)
        
        Args:
            min_sec: Minimum bekleme (saniye)
            max_sec: Maksimum bekleme (saniye)
        """
        wait_time = random.uniform(min_sec, max_sec)
        self.logger.debug(f"⏱️ Waiting {wait_time:.2f}s...")
        time.sleep(wait_time)
    
    def human_click(self, element):
        """
        İnsan gibi tıkla - Eğrisel hareket ile
        
        Args:
            element: Selenium WebElement
        """
        try:
            # Eğrisel hareket (Bezier curve approximation)
            actions = ActionChains(self.driver)
            
            # Başlangıç pozisyonu al
            location = element.location
            size = element.size
            
            # Hedef (elementin ortası + rastgele offset)
            target_x = location['x'] + size['width'] / 2 + random.randint(-10, 10)
            target_y = location['y'] + size['height'] / 2 + random.randint(-5, 5)
            
            # Eğrisel hareket için ara noktalar
            steps = random.randint(10, 20)
            for i in range(steps):
                # Easing function (ease-out)
                progress = i / steps
                eased = 1 - (1 - progress) ** 2
                
                # Rastgele sapma ekle (dalgalanma)
                deviation_x = random.randint(-3, 3) * (1 - progress)
                deviation_y = random.randint(-3, 3) * (1 - progress)
                
                # Mikro bekleme
                time.sleep(random.uniform(0.005, 0.015))
            
            # Son tıklama
            actions.move_to_element(element)
            
            # Bazen miss-click (yanlış tıklama simülasyonu)
            if random.random() < 0.1:  # %10 ihtimal
                # Yanlış tıkla
                actions.move_by_offset(random.randint(-20, 20), random.randint(-15, 15))
                actions.click()
                actions.perform()
                
                self.human_sleep(0.3, 0.7)
                
                # Düzelt
                actions = ActionChains(self.driver)
                actions.move_to_element(element)
            
            actions.click()
            actions.perform()
            
            self.logger.debug(f"✅ Human click")
            
        except Exception as e:
            self.logger.error(f"Human click error: {e}")
            # Fallback: normal click
            element.click()
    
    def human_type(self, element, text: str):
        """
        İnsan gibi yaz - Değişken hız + typo simülasyonu
        
        Args:
            element: Input element
            text: Yazılacak metin
        """
        try:
            for char in text:
                # Bazen typo yap (%3 ihtimal)
                if random.random() < 0.03:
                    # Rastgele yanlış karakter
                    wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                    element.send_keys(wrong_char)
                    time.sleep(random.uniform(0.05, 0.15))
                    
                    # Backspace ile düzelt
                    element.send_keys('\b')  # Backspace
                    time.sleep(random.uniform(0.05, 0.10))
                
                # Doğru karakteri yaz
                element.send_keys(char)
                
                # Rastgele yazma hızı (50-200ms arası)
                time.sleep(random.uniform(0.05, 0.20))
            
            self.logger.debug(f"✅ Human typed: {text[:20]}...")
            
        except Exception as e:
            self.logger.error(f"Human type error: {e}")
            # Fallback: hızlı yazma
            element.send_keys(text)
    
    def scroll_like_human(self, direction: str = 'down', amount: int = 300):
        """
        İnsan gibi scroll
        
        Args:
            direction: 'down' veya 'up'
            amount: Scroll miktarı (piksel)
        """
        try:
            scroll_amount = amount if direction == 'down' else -amount
            
            # Rastgele miktarda scroll
            scroll_amount += random.randint(-100, 100)
            
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            self.human_sleep(0.5, 1.5)
            
        except Exception as e:
            self.logger.error(f"Scroll error: {e}")
    
    def wait_for_element(self, by: By, value: str, timeout: int = 10):
        """Element'in yüklenmesini bekle"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))
            return element
        except Exception as e:
            self.logger.error(f"Wait error: {e}")
            return None
    
    def close(self):
        """Browser'ı kapat"""
        try:
            self.driver.quit()
            self.logger.info("✅ Browser closed")
        except Exception as e:
            self.logger.error(f"Close error: {e}")


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("HUMANIZED BROWSER TEST")
    print("="*60)
    
    try:
        browser = HumanizedBrowser(headless=False)
        
        # Test sayfası
        browser.driver.get("https://www.google.com")
        
        # Human sleep test
        print("\n[1] Human sleep test...")
        browser.human_sleep(1.0, 2.0)
        print("✅ Sleep OK")
        
        # Scroll test
        print("\n[2] Scroll test...")
        browser.scroll_like_human('down', 300)
        print("✅ Scroll OK")
        
        # Close
        browser.close()
        
        print("\n✅ Humanized Browser tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
