"""
Otomatik Asset İndirici
Ses efektleri ve müzikleri otomatik indirir
"""

import requests
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class AssetDownloader:
    """Ücretsiz ses efekti ve müzik indirici"""
    
    def __init__(self):
        self.base_dir = Path("assets")
        self.sfx_dir = self.base_dir / "sound_effects"
        self.music_dir = self.base_dir / "music"
        self.backgrounds_dir = self.base_dir / "backgrounds"
        
        # Dizinleri oluştur
        for dir in [self.sfx_dir, self.music_dir, self.backgrounds_dir]:
            dir.mkdir(parents=True, exist_ok=True)
    
    def download_default_sfx(self) -> bool:
        """
        Varsayılan ses efektlerini indir
        Alternatif: Freesound.org veya placeholder oluştur
        """
        try:
            logger.info("🎵 Varsayılan ses efektleri indiriliyor...")
            
            # Freesound.org doğrudan erişilebilir ses efektleri (CC0 lisans)
            # Not: Bu linkler genel erişime açık public domain dosyalar
            sfx_urls = {
                # Basit sessizlik placeholder'ları (eğer indirme başarısız olursa)
                # Gerçek kullanımda manuel indirme önerilir
            }
            
            # Manuel indirme mesajı
            logger.info("ℹ️ Ses efektleri manuel indirme gerektirir:")
            logger.info("1. https://pixabay.com/sound-effects/search/whoosh/")
            logger.info("2. 3-4 whoosh dosyası indir")
            logger.info("3. 2-3 impact dosyası indir")
            logger.info(f"4. Kaydet: {self.sfx_dir}")
            
            # Placeholder ses dosyaları oluşturmaktayapayım (silent files)
            self._create_placeholder_sfx()
            
            return True
            
        except Exception as e:
            logger.error(f"Ses efekti indirme hatası: {e}")
            return False
    
    def _create_placeholder_sfx(self):
        """Placeholder (sessiz) ses efektleri oluştur"""
        try:
            from pydub import AudioSegment
            from pydub.generators import Sine
            
            logger.info("🔧 Placeholder ses efektleri oluşturuluyor...")
            
            # Basit sine wave efektleri
            # Whoosh: Yükselen frekanslı kısa ses
            whoosh = Sine(1000).to_audio_segment(duration=800)  # 800ms
            whoosh = whoosh.fade_in(100).fade_out(200) - 20  # Kademeli ve kısık
            
            for i in range(1, 4):
                output = self.sfx_dir / f"whoosh_{i}.mp3"
                if not output.exists():
                    whoosh.export(str(output), format="mp3")
                    logger.info(f"✅ Placeholder: {output.name}")
            
            # Impact: Düşük frekanslı vuruş sesi
            impact = Sine(200).to_audio_segment(duration=500)  # 500ms
            impact = impact.fade_out(400) - 15
            
            for i in range(1, 3):
                output = self.sfx_dir / f"impact_{i}.mp3"
                if not output.exists():
                    impact.export(str(output), format="mp3")
                    logger.info(f"✅ Placeholder: {output.name}")
            
            logger.info("ℹ️ Not: Gerçek kullanım için manuel ses efekti indirin!")
            
        except ImportError:
            logger.warning("pydub yok, placeholder oluşturulamadı")
        except Exception as e:
            logger.warning(f"Placeholder oluşturma hatası: {e}")
    
    def download_default_music(self) -> bool:
        """
        Varsayılan arka plan müziği indir
        Manuel indirme önerilir
        """
        try:
            logger.info("🎶 Arka plan müzikleri kontrol ediliyor...")
            
            music_files = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
            
            if len(music_files) < 1:
                logger.info("ℹ️ Arka plan müziği manuel indirme gerektirir:")
                logger.info("1. https://pixabay.com/music/search/dark%20ambient/")
                logger.info("2. 2-3 müzik indir")
                logger.info(f"3. Kaydet: {self.music_dir}")
                
                # Minimal placeholder oluştur
                self._create_placeholder_music()
            
            return True
            
        except Exception as e:
            logger.error(f"Müzik indirme hatası: {e}")
            return False
    
    def _create_placeholder_music(self):
        """Placeholder (minimal) müzik oluştur"""
        try:
            from pydub import AudioSegment
            from pydub.generators import Sine
            
            # Basit ambient drone (30 saniye)
            ambient = Sine(200).to_audio_segment(duration=30000) - 25  # Çok kısık
            ambient = ambient.fade_in(1000).fade_out(1000)
            
            output = self.music_dir / "placeholder_ambient.mp3"
            if not output.exists():
                ambient.export(str(output), format="mp3")
                logger.info(f"✅ Placeholder müzik: {output.name}")
                logger.info("⚠️ Gerçek kullanım için manuel müzik indirin!")
        
        except Exception as e:
            logger.warning(f"Placeholder müzik hatası: {e}")
    
    def ensure_assets_ready(self) -> bool:
        """
        Asset'lerin hazır olduğundan emin ol
        Yoksa otomatik indir
        
        Returns:
            bool: Asset'ler hazır mı?
        """
        try:
            # Ses efekti kontrolü
            sfx_files = list(self.sfx_dir.glob("*.mp3")) + list(self.sfx_dir.glob("*.wav"))
            
            if len(sfx_files) < 3:  # Minimum 3 ses efekti
                logger.info("⚠️ Yeterli ses efekti yok, indiriliyor...")
                self.download_default_sfx()
            else:
                logger.info(f"✅ {len(sfx_files)} ses efekti mevcut")
            
            # Müzik kontrolü
            music_files = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
            
            if len(music_files) < 2:  # Minimum 2 müzik
                logger.info("⚠️ Yeterli müzik yok, indiriliyor...")
                self.download_default_music()
            else:
                logger.info(f"✅ {len(music_files)} müzik mevcut")
            
            return True
            
        except Exception as e:
            logger.error(f"Asset kontrolü hatası: {e}")
            return False
    
    def download_pixabay_image(self, api_key: str, query: str = "dark", count: int = 5) -> bool:
        """
        Pixabay API ile resim indir (opsiyonel)
        """
        try:
            if not api_key or api_key == "YOUR_PEXELS_API_KEY":
                logger.warning("Pixabay API key yok, resim indirme atlandı")
                return False
            
            # Query temizle
            clean_query = self._clean_query_for_pixabay(query)
            logger.info(f"🖼️ Pixabay'den '{clean_query}' resimleri indiriliyor... (Org: {query})")
            
            url = f"https://pixabay.com/api/?key={api_key}&q={clean_query}&image_type=photo&per_page={max(3, count)}&orientation=vertical"
            
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Pixabay API hatası: {response.status_code}")
                return False
            
            data = response.json()
            hits = data.get('hits', [])
            
            if not hits:
                logger.warning("Pixabay'de resim bulunamadı")
                return False
            
            downloaded = 0
            
            for i, hit in enumerate(hits, 1):
                img_url = hit.get('largeImageURL')
                
                if not img_url:
                    continue
                
                output_path = self.backgrounds_dir / f"{query}_{i}.jpg"
                
                if output_path.exists():
                    continue
                
                try:
                    img_response = requests.get(img_url, timeout=30)
                    
                    if img_response.status_code == 200:
                        with open(output_path, 'wb') as f:
                            f.write(img_response.content)
                        
                        logger.info(f"✅ Resim indirildi: {output_path.name}")
                        downloaded += 1
                
                except Exception as e:
                    logger.warning(f"Resim indirme hatası: {e}")
                    continue
            
            if downloaded > 0:
                logger.info(f"🎉 {downloaded} resim başarıyla indirildi!")
            
            return True
            
        except Exception as e:
            logger.error(f"Pixabay resim indirme hatası: {e}")
            return False

    def download_pixabay_music(self, api_key: str, query: str = "ambient", duration_min: int = 30) -> Optional[Path]:
        """
        Pixabay API ile müzik indir
        """
        try:
            if not api_key or api_key == "YOUR_PIXABAY_API_KEY":
                logger.warning("Pixabay API key yok, müzik indirme atlandı")
                return None
            
            clean_query = self._clean_query_for_pixabay(query) or "ambient"
            logger.info(f"🎵 Pixabay Music: '{clean_query}' aranıyor...")

            def _fetch_music_hits(q: str):
                endpoints = [
                    "https://pixabay.com/api/audio/",  # güncel endpoint
                    "https://pixabay.com/api/music/"   # legacy fallback
                ]

                last_status = None
                for endpoint in endpoints:
                    url = f"{endpoint}?key={api_key}&q={q}"
                    response = requests.get(url, timeout=30)
                    last_status = response.status_code

                    if response.status_code == 200:
                        return response.json().get('hits', []), endpoint

                    # 404 vb. durumlarda diğer endpoint'e fallback yap
                    logger.warning(f"Pixabay music endpoint failed ({response.status_code}): {endpoint}")

                logger.error(f"Pixabay Music API error: {last_status}")
                return [], None

            hits, used_endpoint = _fetch_music_hits(clean_query)

            if not hits:
                # Fallback: Daha genel bir query ile dene
                logger.warning(f"'{clean_query}' için müzik bulunamadı, genel arama yapılıyor...")
                hits, used_endpoint = _fetch_music_hits("ambient")

            if not hits:
                return None

            logger.info(f"✅ Pixabay music source: {used_endpoint or 'unknown'}")

            # En uygun müziği seç (süresi yeterli olan)
            selected_hit = hits[0]
            for hit in hits:
                if hit.get('duration', 0) >= duration_min:
                    selected_hit = hit
                    break
            
            music_url = selected_hit.get('downloadURL') or selected_hit.get('audio')
            if not music_url:
                return None
                
            file_name = f"pixabay_{selected_hit['id']}.mp3"
            output_path = self.music_dir / file_name
            
            if output_path.exists():
                return output_path
                
            logger.info(f"📥 Müzik indiriliyor: {selected_hit.get('tags', 'music')}")
            music_resp = requests.get(music_url, timeout=60)
            if music_resp.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(music_resp.content)
                logger.info(f"✅ Müzik kaydedildi: {output_path.name}")
                return output_path
                
            return None
            
        except Exception as e:
            logger.error(f"Pixabay müzik indirme hatası: {e}")
            return None

    def _clean_query_for_pixabay(self, query: str) -> str:
        """Pixabay için sorguyu temizle (Helper)"""
        import unicodedata
        import re
        # Türkçe karakterleri temizle
        normalized = unicodedata.normalize('NFKD', query).encode('ASCII', 'ignore').decode('utf-8')
        # Sadece alfanümerik karakterler
        normalized = re.sub(r'[^a-zA-Z0-9\s]', '', normalized)
        words = normalized.split()
        if len(words) > 3:
            normalized = " ".join(words[:3])
        return normalized[:95].strip().lower()


# Kolay kullanım için helper fonksiyon
def ensure_assets_ready():
    """Asset'lerin hazır olduğundan emin ol"""
    downloader = AssetDownloader()
    return downloader.ensure_assets_ready()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("="*60)
    print("OTOMATIK ASSET İNDİRİCİ")
    print("="*60)
    
    downloader = AssetDownloader()
    
    # Ses efektleri
    print("\n[1/2] Ses Efektleri...")
    downloader.download_default_sfx()
    
    # Müzikler
    print("\n[2/2] Arka Plan Müzikleri...")
    downloader.download_default_music()
    
    print("\n" + "="*60)
    print("✅ TAMAMLANDI!")
    print("="*60)
    
    # Özet
    sfx_count = len(list(downloader.sfx_dir.glob("*.mp3")))
    music_count = len(list(downloader.music_dir.glob("*.mp3")))
    
    print(f"\n📊 Özet:")
    print(f"Ses Efekti: {sfx_count} dosya")
    print(f"Müzik: {music_count} dosya")
    print(f"\nAsset klasörleri:")
    print(f"- {downloader.sfx_dir}")
    print(f"- {downloader.music_dir}")
