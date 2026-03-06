"""
Content Fetcher - Pexels'den Viral Klip İndirme
"""

import requests
import os
from pathlib import Path
from typing import List, Dict, Optional
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Disable SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# KANAL KİMLİKLERİ (Global Config)
CHANNEL_STYLES = {
    "Future Lab": {
        "visual_keywords": "cinematic, cyberpunk, neon lights, futuristic, sci-fi, robot, dark atmosphere, 4k",
        "script_tone": "Visionary, mysterious, high-tech, slightly scary. Like a Netflix Sci-Fi documentary.",
    },
    "The Power of Money": {
        "visual_keywords": "luxury, gold, money, wall street, dark suit, expensive car, mansion, aggressive, 4k",
        "script_tone": "Authoritative, aggressive, motivational. 'Break the Matrix' style. Short, punchy sentences.",
    },
    "Healthy Living": {
        "visual_keywords": "bright, sunlight, fresh, organic, nature, clean, happy people, green, 4k",
        "script_tone": "Encouraging, scientific, clear, calm, optimistic. Focus on longevity and health.",
    },
    "Information Repository": {
        "visual_keywords": "library, ancient, mystery, dark academia, history, cinematic, slow motion, 4k",
        "script_tone": "Deep, informative, detective-like, intellectual. Focus on hidden facts and history.",
    },
    "The Power of Money (TikTok)": {
        "visual_keywords": "abstract, human face, brain, dark psychology, shadow, moody, noir style, 4k, luxury, money",
        "script_tone": "Analytical, dark, psychological, manipulative. Focus on human behavior and mind tricks.",
    }
}


class ContentFetcher:
    """Pexels API ile video klipleri bul ve indir"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Pexels API key (None ise .env'den alır)
        """
        self.logger = logging.getLogger(__name__)
        
        self.api_key = api_key or os.getenv("PEXELS_API_KEY")
        if not self.api_key:
            self.logger.warning("PEXELS_API_KEY bulunamadı! Klip indirme çalışmayacak.")
        
        self.base_url = "https://api.pexels.com/videos"
        self.headers = {"Authorization": self.api_key} if self.api_key else {}
        
        self.cache_dir = Path("clips_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        # SSL/Connection retry session
        self.session = self._create_retry_session()
    
    def _create_retry_session(self, retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504)):
        """Create requests session with retry strategy for SSL/connection errors"""
        retry_strategy = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def search_clips(
        self,
        keywords: List[str],
        min_duration: int = 5,
        max_duration: int = 30,
        per_page: int = 15,
        orientation: str = "portrait",  # TikTok için dikey
        channel_name: str = None        # Kanal stili için
    ) -> List[Dict]:
        """
        Keywords'e göre video klipleri ara
        
        Args:
            keywords: Arama kelimeleri
            min_duration: Minimum süre (saniye)
            max_duration: Maksimum süre (saniye)
            per_page: Sonuç sayısı
            orientation: portrait (dikey), landscape, square
            
        Returns:
            List[Dict]: Klip bilgileri
        """
        if not self.api_key:
            self.logger.error("API key yok, arama yapılamıyor")
            return []
        
        try:
            # Arama sorgusu oluştur
            if isinstance(keywords, str):
                query = keywords
            else:
                query = " ".join(keywords[:3])  # İlk 3 keyword
            
            params = {
                "query": query,
                "per_page": per_page,
                "orientation": orientation,
                "size": "medium"  # medium (HD), large (4K)
            }
            
            self.logger.info(f"Pexels araması: '{query}'")
            
            try:
                response = self.session.get(
                    f"{self.base_url}/search",
                    headers=self.headers,
                    params=params,
                    timeout=15,
                    verify=True  # SSL verification enabled
                )
                response.raise_for_status()
            except requests.exceptions.SSLError as ssl_err:
                self.logger.warning(f"SSL hatası, yeniden deneniyor (verify=False): {ssl_err}")
                # Fallback: SSL verification disabled
                response = self.session.get(
                    f"{self.base_url}/search",
                    headers=self.headers,
                    params=params,
                    timeout=15,
                    verify=False
                )
                response.raise_for_status()
            except requests.exceptions.ConnectionError as conn_err:
                self.logger.error(f"Bağlantı hatası: {conn_err}")
                return []
            
            data = response.json()
            
            videos = data.get("videos", [])
            
            # Süre filtreleme
            filtered_videos = []
            for video in videos:
                duration = video.get("duration", 0)
                if min_duration <= duration <= max_duration:
                    filtered_videos.append({
                        "id": video["id"],
                        "duration": duration,
                        "width": video["width"],
                        "height": video["height"],
                        "url": video["url"],
                        "image": video["image"],
                        "video_files": video["video_files"]
                    })
            
            self.logger.info(f"✅ {len(filtered_videos)} klip bulundu ({min_duration}-{max_duration}s)")
            return filtered_videos
            
        except Exception as e:
            self.logger.error(f"Pexels arama hatası: {e}")
            return []
    
    def download_clip(
        self,
        video_info: Dict,
        output_filename: str,
        quality: str = "hd"
    ) -> Optional[Path]:
        """
        Video klip indir
        
        Args:
            video_info: search_clips'den dönen video bilgisi
            output_filename: Kayıt dosya adı
            quality: hd, sd, mobile
            
        Returns:
            Path: İndirilen dosya yolu veya None
        """
        try:
            # Kaliteye göre video dosyası seç
            video_files = video_info.get("video_files", [])
            
            # HD tercih et
            selected_file = None
            for vf in video_files:
                if quality == "hd" and vf.get("quality") == "hd":
                    selected_file = vf
                    break
                elif quality == "sd" and vf.get("quality") == "sd":
                    selected_file = vf
                    break
            
            # Bulunamazsa ilk dosyayı al
            if not selected_file and video_files:
                selected_file = video_files[0]
            
            if not selected_file:
                self.logger.error("İndirilebilir video dosyası bulunamadı")
                return None
            
            download_url = selected_file.get("link")
            
            # İndir
            output_path = self.cache_dir / output_filename
            
            self.logger.info(f"Klip indiriliyor: {output_filename}")
            
            try:
                response = self.session.get(download_url, stream=True, timeout=30, verify=True)
                response.raise_for_status()
            except requests.exceptions.SSLError as ssl_err:
                self.logger.warning(f"SSL hatası, yeniden deneniyor (verify=False): {ssl_err}")
                response = self.session.get(download_url, stream=True, timeout=30, verify=False)
                response.raise_for_status()
            except requests.exceptions.ConnectionError as conn_err:
                self.logger.error(f"Bağlantı hatası: {conn_err}")
                return None
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = output_path.stat().st_size / (1024 * 1024)  # MB
            self.logger.info(f"✅ Klip indirildi: {output_path} ({file_size:.1f} MB)")
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Klip indirme hatası: {e}")
            return None
    
    def fetch_clips_for_scenario(
        self,
        scenario: Dict,
        clips_per_scene: int = 1,
        channel_name: str = None
    ) -> Dict[int, List[Path]]:
        """
        Senaryo için tüm klipleri bul ve indir
        
        Args:
            scenario: Senaryo dict'i
            clips_per_scene: Her sahne için kaç klip
            
        Returns:
            Dict[int, List[Path]]: {scene_index: [clip_paths]}
        """
        scene_clips = {}
        
        scenes = scenario.get("scenes", [])
        
        for i, scene in enumerate(scenes):
            visual_prompt = scene.get("visual_prompt")
            keywords = scene.get("visual_keywords", [])
            duration = scene.get("duration", 10)
            
            # Smart Search: Visual Prompt varsa onu kullan (String olarak)
            search_query = visual_prompt if visual_prompt else keywords
            
            # DÜZELTME 4: Eğer keyword/prompt boşsa veya yetersizse güvenli/soyut bir arama yap
            if not search_query or (isinstance(search_query, list) and not any(search_query)):
                self.logger.warning(f"Sahne {i+1}: Görsel keyword yok, varsayılan aramaya geçiliyor.")
                search_query = "cinematic abstract background, dark atmosphere"
            
            # Klip ara
            # Klip ara
            clips = self.search_clips(
                keywords=search_query,
                min_duration=max(5, duration - 5),
                max_duration=duration + 10,
                per_page=max(3, clips_per_scene * 2),
                channel_name=channel_name 
            )
            
            if not clips:
                self.logger.warning(f"Sahne {i+1}: Klip bulunamadı")
                continue
            
            # İlk N klip indir
            downloaded = []
            for j, clip in enumerate(clips[:clips_per_scene]):
                filename = f"scene_{i+1}_clip_{j+1}.mp4"
                path = self.download_clip(clip, filename)
                
                if path:
                    downloaded.append(path)
                
                # Rate limiting
                time.sleep(0.5)
            
            scene_clips[i] = downloaded
        
        return scene_clips


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("PEXELS CONTENT FETCHER TEST")
    print("="*60)
    
    fetcher = ContentFetcher()
    
    # Test: Para konulu klip ara
    print("\n[Test] 'para', 'zenginlik', 'başarı' araması")
    
    clips = fetcher.search_clips(
        keywords=["money", "success", "wealth"],
        min_duration=10,
        max_duration=20,
        per_page=5
    )
    
    if clips:
        print(f"\n✅ {len(clips)} klip bulundu!")
        
        for i, clip in enumerate(clips, 1):
            print(f"\nKlip {i}:")
            print(f"  Süre: {clip['duration']}s")
            print(f"  Çözünürlük: {clip['width']}x{clip['height']}")
        
        # İlk klip indir
        if clips:
            print("\n[Test] İlk klip indiriliyor...")
            path = fetcher.download_clip(clips[0], "test_money_clip.mp4")
            
            if path:
                print(f"✅ Başarılı: {path}")
    else:
        print("❌ Klip bulunamadı")
