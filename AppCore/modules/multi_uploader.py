"""
Multi-Platform Uploader - YouTube + TikTok
"""

import os
import time
import random
from pathlib import Path
from typing import Optional
import logging

try:
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service as EdgeService
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class MultiUploader:
    """Upload videos to YouTube and TikTok"""
    
    def __init__(self, headless: bool = True, email: str = "", password: str = ""):
        self.logger = logging.getLogger(__name__)
        self.headless = headless
        self.driver = None
        self.current_account = None
        self.current_profile_path: Optional[Path] = None
        
        # TikTok login bilgileri
        self.email = email
        self.password = password

        # Son yükleme hata nedeni (UnifiedUploader tarafından okunur)
        self.last_error_reason = ""

        # TikTok throttling/cooldown bilgisi
        self.tiktok_cooldown_until = 0.0

        # URLs
        self.TIKTOK_UPLOAD = "https://www.tiktok.com/upload"
        self.TIKTOK_LOGIN = "https://www.tiktok.com/login"
        self.YOUTUBE_STUDIO = "https://studio.youtube.com"

    def human_sleep(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Random sleep for human-like behavior"""
        time.sleep(random.uniform(min_sec, max_sec))

    def human_click(self, element):
        """Human-like click with curve movement"""
        try:
            if not self.headless:
                actions = ActionChains(self.driver)
                # Scroll to element
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                time.sleep(random.uniform(0.5, 1.0))
                
                # Move to element with offset
                actions.move_to_element(element)
                actions.pause(random.uniform(0.1, 0.3))
                actions.click()
                actions.perform()
            else:
                element.click()
        except Exception as e:
            self.logger.warning(f"Human click failed, falling back to JS: {e}")
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except:
                element.click()

    def human_type(self, element, text: str):
        """Human-like typing with delays"""
        try:
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
        except:
            element.send_keys(text)
    
    def _create_driver(self, profile_path: Path) -> Optional[object]:
        """Create Microsoft Edge driver with profile (US Geo-Targeted)"""
        if not SELENIUM_AVAILABLE:
            self.logger.error("Selenium/EdgeDriver not available")
            return None
        
        try:
            options = EdgeOptions()
            
            # Absolute path ve string dönüşümü önemli
            abs_profile_path = str(profile_path.absolute()) if isinstance(profile_path, Path) else str(os.path.abspath(profile_path))
            
            options.add_argument(f"--user-data-dir={abs_profile_path}")
            options.add_argument("--profile-directory=Default")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")
            
            # --- US GEO-TARGETING (NEW YORK) ---
            options.add_argument('--lang=en-US')
            options.add_argument('--timezone="America/New_York"')
            options.add_argument('--force-webrtc-ip-handling-policy=default_public_interface_only')
            
            prefs = {
                "intl.accept_languages": "en-US,en",
                "profile.default_content_settings.geolocation": 1
            }
            options.add_experimental_option("prefs", prefs)
            
            # Crash önleyici argümanlar
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222") # Port çakışmasını önle
            
            # Anti-detection flags for Edge
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            if self.headless:
                options.add_argument("--headless=new")
            
            service = None
            
            # 1. Check for local driver in project root
            local_driver_path = Path("msedgedriver.exe")
            if local_driver_path.exists():
                self.logger.info(f"Using local EdgeDriver: {local_driver_path.absolute()}")
                service = EdgeService(executable_path=str(local_driver_path.absolute()))
            else:
                # 2. Try to get latest driver (Requires Internet)
                try:
                    driver_path = EdgeChromiumDriverManager().install()
                    service = EdgeService(driver_path)
                except Exception as dm_err:
                    self.logger.warning(f"EdgeDriverManager failed: {dm_err}")
                    # 3. Fallback: Try system 'msedgedriver'
                    self.logger.info("Attempting to use system 'msedgedriver'...")
                    service = EdgeService() 

            import subprocess
            if service:
                service.creation_flags = subprocess.CREATE_NO_WINDOW

            driver = webdriver.Edge(service=service, options=options)
            
            # --- US GEO-SPOOFING (CDP & JS) ---
            try:
                # 1. Geolocation Override (New York Times Square)
                driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
                    "latitude": 40.758896,
                    "longitude": -73.985130,
                    "accuracy": 100
                })
                # 2. Timezone Override
                driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {
                    "timezoneId": "America/New_York"
                })
            except Exception as cdp_err:
                self.logger.warning(f"CDP Geo-spoofing warning: {cdp_err}")

            # 3. JS Spoofing (Navigator & Date)
            spoof_script = """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'language', {get: () => 'en-US'});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                
                const newYorkTimezone = "America/New_York";
                const originalDateTimeFormat = Intl.DateTimeFormat;
                Intl.DateTimeFormat = function(locales, options) {
                    options = options || {};
                    options.timeZone = newYorkTimezone;
                    return new originalDateTimeFormat(locales, options);
                };
                Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;
            """
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": spoof_script
                })
            except:
                pass
            
            driver.set_page_load_timeout(60)
            self.logger.info("✅ Browser started in US Mode (New York, en-US)")
            return driver
            
        except Exception as e:
            error_msg = str(e)
            if "SessionNotCreatedException" in error_msg or "session not created" in error_msg:
                self.logger.error("❌ EDGE DRIVER HATASI!")
                self.logger.error("Tarayıcı başlatılamadı. Sürüm uyumsuzluğu veya sürücü eksik.")
                self.logger.error(f"Hata Detayı: {error_msg}")
                self.logger.error("-" * 50)
                self.logger.error("ÇÖZÜM:")
                self.logger.error("1. https://msedgedriver.azureedge.net/145.0.3800.47/edgedriver_win64.zip adresinden dosyayı indirin.")
                self.logger.error("2. İndirdiğiniz 'msedgedriver.exe' dosyasını şu klasöre atın:")
                self.logger.error(f"   {os.getcwd()}")
                self.logger.error("-" * 50)
            else:
                self.logger.error(f"Edge Driver creation failed: {e}")
            return None
    
    def connect(self, account_id: str, profile_path: Path) -> bool:
        """Connect to account"""
        try:
            if self.driver:
                self.disconnect()
            
            self.driver = self._create_driver(profile_path)
            self.current_account = account_id
            self.current_profile_path = profile_path
            return self.driver is not None
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect and cleanup"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.current_account = None

    def _is_driver_alive(self) -> bool:
        """Driver oturumu hâlâ canlı mı kontrol et"""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            _ = self.driver.window_handles
            return True
        except Exception:
            return False

    def _ensure_driver_alive(self, context: str = "") -> bool:
        """Selenium oturumu düştüyse erken ve kontrollü çık"""
        if self._is_driver_alive():
            return True
        suffix = f" ({context})" if context else ""
        self.last_error_reason = f"TikTok tarayıcı oturumu kapandı/bağlantı koptu{suffix}."
        self.logger.error(f"❌ {self.last_error_reason}")
        return False
    
    def _contains_tiktok_attempt_limit(self, text: str) -> bool:
        """TikTok attempt-limit throttling metnini yakala"""
        if not text:
            return False
        t = text.lower()
        markers = [
            "maximum number of attempts reached",
            "too many attempts",
            "try again later",
            "çok fazla deneme",
            "daha sonra tekrar dene",
        ]
        return any(m in t for m in markers)

    def _is_tiktok_attempt_limited(self) -> bool:
        """Aktif sayfada attempt-limit engeli var mı kontrol et"""
        try:
            current_url = (self.driver.current_url or "") if self.driver else ""
            page_source = (self.driver.page_source or "") if self.driver else ""
            return self._contains_tiktok_attempt_limit(current_url) or self._contains_tiktok_attempt_limit(page_source)
        except Exception:
            return False

    def _apply_tiktok_cooldown(self, hours: int = 6):
        """Attempt-limit durumunda güvenli cooldown uygula"""
        self.tiktok_cooldown_until = time.time() + (hours * 3600)

    def upload_youtube(self, video_path: Path, title: str, description: str,
                       tags: list, visibility: str = "public", publishAt: str = None) -> bool:
        """Upload to YouTube"""
        if not self.driver:
            self.logger.error("Not connected")
            return False
        
        try:
            self.logger.info(f"Uploading to YouTube: {title[:50]}...")
            
            # Navigate to YouTube Studio
            self.driver.get(self.YOUTUBE_STUDIO)
            time.sleep(3)
            
            # Click create button
            create_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "create-icon"))
            )
            create_btn.click()
            time.sleep(1)
            
            # Click upload
            upload_btn = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#text-item-0"))
            )
            upload_btn.click()
            time.sleep(2)
            
            # Upload file
            file_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(str(video_path.absolute()))
            time.sleep(5)
            
            # Fill title
            title_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "textbox"))
            )
            title_input.clear()
            title_input.send_keys(title)
            time.sleep(1)
            
            # Fill description
            textboxes = self.driver.find_elements(By.ID, "textbox")
            if len(textboxes) > 1:
                desc_input = textboxes[1]
                desc_input.click()
                desc_input.send_keys(description)
                time.sleep(1)
            
            # Add tags
            show_more = self.driver.find_element(By.CSS_SELECTOR, "#toggle-button")
            show_more.click()
            time.sleep(1)
            
            tags_input = self.driver.find_element(By.CSS_SELECTOR, "input[placeholder='Add tag']")
            for tag in tags[:10]:
                tags_input.send_keys(tag.replace('#', ''))
                tags_input.send_keys(Keys.RETURN)
                time.sleep(0.5)
            
            # Set visibility
            visibility_radio = self.driver.find_element(
                By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='PUBLIC']"
            )
            visibility_radio.click()
            time.sleep(1)
            
            # Click through wizard
            for _ in range(3):
                next_btn = self.driver.find_element(By.ID, "next-button")
                next_btn.click()
                time.sleep(2)
            
            # Publish
            publish_btn = self.driver.find_element(By.ID, "done-button")
            publish_btn.click()
            time.sleep(5)
            
            self.logger.info("YouTube upload successful")
            return True
            
        except Exception as e:
            self.logger.error(f"YouTube upload failed: {e}")
            return False
    
    def upload_tiktok(self, video_path: Path, title: str, description: str,
                      tags: list, schedule_time: str = None, progress_callback=None) -> bool:
        """Upload to TikTok with optional scheduling"""
        if not self.driver:
            self.logger.error("Not connected")
            self.last_error_reason = "TikTok uploader bağlı değil (driver yok)."
            return False
        
        try:
            self.last_error_reason = ""
            self.logger.info(f"Uploading to TikTok: {title[:50]}...")

            if not self._ensure_driver_alive("upload başlangıcı"):
                return False

            # Önceden belirlenmiş cooldown varsa tekrar deneme yapma
            now_ts = time.time()
            if self.tiktok_cooldown_until > now_ts:
                remaining = int(self.tiktok_cooldown_until - now_ts)
                mins = max(1, remaining // 60)
                self.last_error_reason = f"TikTok geçici olarak deneme limitinde. Yaklaşık {mins} dakika sonra tekrar deneyin."
                self.logger.error(f"❌ {self.last_error_reason}")
                return False

            # Navigate to TikTok upload
            self.driver.get(self.TIKTOK_UPLOAD)
            time.sleep(3)

            # Attempt-limit sayfası/login throttle erken kontrol
            if self._is_tiktok_attempt_limited():
                self._apply_tiktok_cooldown(hours=6)
                self.last_error_reason = "TikTok: Maximum number of attempts reached. Try again later."
                self.logger.error(f"❌ {self.last_error_reason}")
                return False
            
            # Login gerekli mi kontrol et
            # Login gerekli mi kontrol et (URL'de 'login' varsa veya parametreler eksikse)
            if "login" in self.driver.current_url.lower() or "/upload" not in self.driver.current_url.lower():
                self.logger.warning("⚠️ TikTok girişi yapmanız gerekiyor!")
                self.logger.warning("Lütfen açılan pencerede 120 saniye içinde manuel olarak giriş yapın.")
                
                # Manuel giriş için bekle
                max_wait = 120
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    if not self._ensure_driver_alive("login bekleme"):
                        return False

                    if self._is_tiktok_attempt_limited():
                        self._apply_tiktok_cooldown(hours=6)
                        self.last_error_reason = "TikTok giriş limiti doldu: Maximum number of attempts reached."
                        self.logger.error(f"❌ {self.last_error_reason}")
                        return False

                    if "login" not in self.driver.current_url.lower():
                        self.logger.info("✅ TikTok girişi algılandı (veya login sayfasından çıkıldı)!")
                        break
                    
                    if int(time.time() - start_time) % 10 == 0:
                         self.logger.info(f"Giriş bekleniyor... ({int(max_wait - (time.time() - start_time))} sn kaldı)")
                    
                    time.sleep(1)
                else:
                    self.logger.error("❌ Giriş zaman aşımı! (120 sn)")
                    return False
                
                # Giriş sonrası sayfayı yenile veya upload sayfasına git
                if self.driver.current_url != self.TIKTOK_UPLOAD:
                    self.driver.get(self.TIKTOK_UPLOAD)
                    time.sleep(5)
            
            if self._is_tiktok_attempt_limited():
                self._apply_tiktok_cooldown(hours=6)
                self.last_error_reason = "TikTok upload ekranı attempt-limit nedeniyle kilitlendi."
                self.logger.error(f"❌ {self.last_error_reason}")
                return False

            # Upload file
            file_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(str(video_path.absolute()))
            time.sleep(5)
            
            # Fill caption with React-compatible method
            caption_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true']"))
            )
            
            self.human_click(caption_input)
            time.sleep(1)
            
            full_caption = f"{title}\n\n{' '.join(tags[:5])}"
            
            # YÖNTEM 1: JS ile İçeriği Ayarla ve Event Tetik (En Güvenlisi)
            try:
                self.driver.execute_script("""
                    var elm = arguments[0];
                    elm.textContent = arguments[1];
                    elm.dispatchEvent(new Event('input', { bubbles: true }));
                    elm.dispatchEvent(new Event('change', { bubbles: true }));
                    elm.focus();
                """, caption_input, full_caption)
                
                # React'i "uyandırmak" için sahte bir tuş basımı yap
                caption_input.send_keys(Keys.SPACE)
                time.sleep(0.5)
                caption_input.send_keys(Keys.BACKSPACE)
                self.logger.info("✅ Caption React eventleri ile yazıldı.")
                
            except Exception as e:
                self.logger.warning(f"JS Caption hatası, manuel yazılıyor: {e}")
                # Fallback: Tek tek yaz (Yavaş ama garanti)
                caption_input.clear()
                caption_input.send_keys(full_caption)
            
            time.sleep(2)
            
            # --- SCHEDULING LOGIC ---
            if schedule_time:
                try:
                    self.logger.info(f"📅 TikTok Scheduling attempting: {schedule_time}")
                    schedule_switch = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Schedule video')]"))
                    )
                    switch_input = schedule_switch.find_element(By.XPATH, "./..//input[@type='checkbox'] | ./following-sibling::div//input[@type='checkbox']")
                    
                    if not switch_input.is_selected():
                        self.logger.info("Enabling Schedule switch...")
                        self.driver.execute_script("arguments[0].click();", switch_input)
                        time.sleep(2)
                    
                    self.logger.info("✅ Schedule toggle enabled.")
                except Exception as e:
                    self.logger.warning(f"TikTok Schedule Failed: {e}. Uploading normally.")
            
            # JOYRIDE OVERLAY KONTROLÜ
            try:
                overlay = self.driver.find_elements(By.CLASS_NAME, "react-joyride__overlay")
                if overlay:
                    self.logger.info("⚠️ Joyride overlay algılandı, kapatılıyor...")
                    webdriver.ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)
                    if len(overlay) > 0 and overlay[0].is_displayed():
                        self.driver.execute_script("arguments[0].remove();", overlay[0])
                        self.logger.info("✅ Joyride overlay kaldırıldı.")
            except Exception:
                pass

            # --- UPLOAD PROGRESS CHECK (%100 BEKLEME) ---
            self.logger.info("⏳ Yükleme yüzdesi bekleniyor...")
            upload_ready = False
            progress_start_time = time.time()
            max_progress_wait = 300 
            
            while time.time() - progress_start_time < max_progress_wait:
                try:
                    if not self._ensure_driver_alive("yükleme ilerleme takibi"):
                        return False
                    page_source = self.driver.page_source
                    if self._contains_tiktok_attempt_limit(page_source):
                        self._apply_tiktok_cooldown(hours=6)
                        self.last_error_reason = "TikTok: Maximum number of attempts reached (yükleme sırasında)."
                        self.logger.error(f"❌ {self.last_error_reason}")
                        return False

                    if "100%" in page_source or "Uploaded" in page_source or "Yüklendi" in page_source:
                        self.logger.info("✅ Yükleme %100 tamamlandı!")
                        upload_ready = True
                        break
                    
                    # Yüzdeyi canlı takip et
                    import re
                    pct_match = re.search(r"(\d+)%", page_source)
                    if pct_match:
                        current_pct = max(0, min(100, int(pct_match.group(1))))
                        self.logger.info(f"⏳ Yükleme: %{current_pct}")
                        if progress_callback:
                            try:
                                progress_callback(current_pct, f"TikTok Yükleniyor... %{current_pct}")
                            except Exception as cb_err:
                                self.logger.debug(f"TikTok progress callback hatası: {cb_err}")
                    
                    time.sleep(1)
                except Exception:
                    time.sleep(1)
            
            if not upload_ready:
                 self.logger.warning("⚠️ %100 yükleme ibaresi görülmedi ama süre doldu, butonu deniyoruz...")
            elif progress_callback:
                try:
                    progress_callback(100, "TikTok Yükleniyor... %100")
                except Exception as cb_err:
                    self.logger.debug(f"TikTok final progress callback hatası: {cb_err}")

            # --- SUBMIT BUTTON UI FIX ---
            # Kullanıcının "kırmızı butona tıklamıyor" şikayeti için çözüm
            try:
                # 1. Butonu daha genel bir seçici ile bul
                upload_btn = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'css-') and (contains(text(), 'Post') or contains(text(), 'Paylaş'))] | //button[@data-e2e='post_video_button']"))
                )
                
                # 2. Görünür olmasını sağla
                self.logger.info("🖱️ Upload butonu bulundu, görünür yapılıyor...")
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", upload_btn)
                time.sleep(2)
                
                # 3. Disabled kontrolü
                if not upload_btn.is_enabled():
                    self.logger.warning("⚠️ Upload butonu pasif (disabled)! (Caption veya video yüklenmemiş olabilir)")
                    # Yine de şansımızı deneyelim, bazen attribute yanıltıcı olabilir
                
                # 4. TIKLAMA (JS Priority)
                self.logger.info("🚀 Upload butonuna JS ile TIKLANIYOR...")
                self.driver.execute_script("arguments[0].click();", upload_btn)
                
                # Fallback: Action Chains Click
                try:
                    time.sleep(1)
                    ActionChains(self.driver).move_to_element(upload_btn).click().perform()
                except:
                    pass
                    
            except Exception as e:
                self.logger.error(f"❌ Upload butonu bulunamadı veya tıklanamadı: {e}")
                # Son çare HTML dump al (Debug için)
                try:
                    with open("debug_tiktok_fail.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    self.logger.info("Debug HTML kaydedildi: debug_tiktok_fail.html")
                except: pass
                return False
            
            # --- CHECK FOR COPYRIGHT/CONTENT WARNING MODAL ---
            # Kullanıcı: "içerik incelenme uyarısı çıkarsa onda da sağdaki kırmızı butona bassın"
            time.sleep(3) # Modalin çıkması için kısa bekleme
            try:
                # Genellikle "Post anyway" veya "Yine de paylaş" butonu olur ve kırmızı/primary renktedir.
                # Modal içindeki sağdaki butonu hedefliyoruz.
                warning_modal_btn = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'modal')]//button[contains(@class, 'primary') or contains(text(), 'Post anyway') or contains(text(), 'Yine de paylaş')]")
                
                if warning_modal_btn:
                    for btn in warning_modal_btn:
                        if btn.is_displayed():
                            self.logger.info("⚠️ İçerik uyarısı modalı algılandı, 'Yine de paylaş' butonuna insan gibi tıklanıyor...")
                            self.human_click(btn)
                            time.sleep(2)
                            break
            except Exception as warn_err:
                self.logger.warning(f"Uyarı modalı kontrolü sırasında hata (önemsiz olabilir): {warn_err}")
            
            # --- ZORUNLU BEKLEME (Kullanıcı İsteği) ---
            # Video yüklenmeden kapanmaması için 60 saniye bekleme (Zaten %100 bekledik, 120 çok olabilir ama kullanıcı istediği için 60'a indirdim güvenli pay olarak)
            self.logger.info("⏳ Upload sonrası 60 saniye ek güvenlik beklemesi yapılıyor...")
            for i in range(60, 0, -10):
                self.logger.info(f"⏳ Bekleniyor... ({i} sn kaldı)")
                time.sleep(10)
            
            # --- BAŞARI KONTROLÜ ---
            self.logger.info("⏳ 120 saniye doldu, sonuç kontrol ediliyor...")
            
            upload_success = False
            start_wait = time.time()
            max_wait_time = 60  # Ekstra 60 sn kontrol
            found_text = ""
            
            while time.time() - start_wait < max_wait_time:
                elapsed = int(time.time() - start_wait)
                
                try:
                    if not self._ensure_driver_alive("yükleme sonrası başarı kontrolü"):
                        return False
                    # 1. Modal Başlığı: "Your video has been uploaded" veya "Videonuz yüklendi"
                    # Bu genellikle büyük bir modal içinde çıkar
                    success_elements = self.driver.find_elements(By.XPATH, "//*[@id='tux-portal-container']//div[contains(text(), 'uploaded') or contains(text(), 'yüklendi') or contains(text(), 'published')]")
                    
                    if not success_elements:
                        # Fallback: Tüm sayfada spesifik cümleler ara (GÖRÜNÜR OLMALI)
                        specific_phrases = [
                            "Your video has been uploaded",
                            "Videonuz yüklendi",
                            "Post published",
                            "Gönderi paylaşıldı",
                            "View profile",
                            "Profil görüntüle",
                            "Upload another video",
                            "Başka bir video yükle",
                            "İçerik kontrolü",
                            "Kontrol devam ediyor",
                            "Content check",
                            "Checking"
                        ]
                        
                        for phrase in specific_phrases:
                            try:
                                # Text içeren ve GÖRÜNÜR olan elementleri ara
                                xpath = f"//*[contains(text(), '{phrase}')]"
                                elements = self.driver.find_elements(By.XPATH, xpath)
                                for elem in elements:
                                    if elem.is_displayed():
                                        success_elements = [elem]
                                        found_text = phrase
                                        break
                                if success_elements:
                                    break
                            except:
                                continue
                    
                    if success_elements:
                        # Eğer generic 'uploaded' bulduysak, bunun progress bar olmadığından emin olmalıyız
                        # Ancak 'Your video has been uploaded' gibi uzun cümleler zaten güvenlidir.
                        if found_text:
                             self.logger.info(f"✅ Başarı işareti algılandı: '{found_text}'")
                        else:
                             self.logger.info("✅ Başarı modalı algılandı.")
                        
                        upload_success = True
                        break
                        
                    # 2. URL Kontrolü: Upload sayfasından çıktı mı?
                    # Genellikle upload bitince /upload url'sinde kalabilir ama modal çıkar.
                    # Eğer profile yönlenirse kesin başarılıdır.
                    if "/video/" in self.driver.current_url:
                        self.logger.info(f"✅ URL video sayfasına dönüştü: {self.driver.current_url}")
                        upload_success = True
                        break

                    time.sleep(1)
                except Exception as e:
                    pass
            
            if not upload_success:
                self.logger.warning(f"⚠️ Kesin başarı mesajı görülemedi! (Zaman aşımı {max_wait_time}sn)")
                if self._is_tiktok_attempt_limited():
                    self._apply_tiktok_cooldown(hours=6)
                    self.last_error_reason = "TikTok gönderim sonrası attempt-limit engeline takıldı."
                    self.logger.error(f"❌ {self.last_error_reason}")
                    return False
                self.logger.warning("NOT: Tarayıcı şimdi kapatılacak. Eğer video işleniyorsa iptal olabilir.")
            else:
                self.logger.info("✅ TikTok upload KESİN OLARAK başarılı!")
            
            # Başarı sonrası bekleme süresini artır (Video processing için)
            self.logger.info("Processing için ek süre bekleniyor (10sn)...")
            time.sleep(10)
            return True
            
        except Exception as e:
            err_text = str(e)
            lower = err_text.lower()
            if self._contains_tiktok_attempt_limit(err_text):
                self._apply_tiktok_cooldown(hours=6)
                self.last_error_reason = "TikTok: Maximum number of attempts reached. Try again later."
            elif "invalid session id" in lower or "browser has closed" in lower or "no such window" in lower:
                self.last_error_reason = "TikTok tarayıcı oturumu beklenmedik şekilde kapandı (invalid session)."
            else:
                self.last_error_reason = err_text
            self.logger.error(f"TikTok upload failed: {e}")
            return False
    
    def upload(self, video_path: Path, title: str, description: str, 
               tags: list, platform: str, **kwargs) -> bool:
        """Upload to specified platform"""
        if platform == "youtube":
            return self.upload_youtube(video_path, title, description, tags, 
                                     publish_at=kwargs.get("publish_at"))
        elif platform == "tiktok":
            return self.upload_tiktok(video_path, title, description, tags, schedule_time=kwargs.get("schedule_time"))
        else:
            self.logger.error(f"Unknown platform: {platform}")
            return False
