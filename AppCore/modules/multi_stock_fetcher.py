"""
Multi Stock Fetcher - Pexels + Pixabay + Gemini AI Validation
Stok görselleri ve videoları çoklu kaynaktan çeker ve Gemini ile uygunluğunu kontrol eder
"""

import os
import json
import hashlib
import requests
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import time

# Gemini SDK
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logger = logging.getLogger(__name__)


class MultiStockFetcher:
    """Pexels ve Pixabay'den stok içerik çeker, Gemini ile doğrular"""
    
    def __init__(self):
        """Initialize with API keys from environment"""
        self.pexels_key = os.getenv("PEXELS_API_KEY")
        self.pixabay_key = os.getenv("PIXABAY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        
        if not self.pexels_key:
            logger.warning("⚠️ PEXELS_API_KEY bulunamadı")
        if not self.pixabay_key:
            logger.warning("⚠️ PIXABAY_API_KEY bulunamadı")
        if not self.gemini_key:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı - Görsel kontrolü yapılamayacak")
        
        # Gemini client
        self.gemini_client = None
        if GENAI_AVAILABLE and self.gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
                logger.info("✅ Gemini client initialized for content validation")
            except Exception as e:
                logger.error(f"Gemini client init error: {e}")
        
        self.cache_dir = Path("System_Data/clips_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Haftalık tekrar engeli için kullanım geçmişi
        self.usage_history_file = Path("System_Data/upload_queue/stock_usage_history.json")
        self.usage_history_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_current_week_key(self) -> str:
        """ISO week formatında anahtar üretir: YYYY-Www"""
        now = datetime.now()
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    def _load_usage_history(self) -> Dict:
        """Klip kullanım geçmişini yükle"""
        try:
            if self.usage_history_file.exists():
                with open(self.usage_history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.warning(f"Klip kullanım geçmişi okunamadı, sıfırlanıyor: {e}")
        return {}

    def _save_usage_history(self, history: Dict):
        """Klip kullanım geçmişini kaydet"""
        try:
            with open(self.usage_history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Klip kullanım geçmişi kaydedilemedi: {e}")

    def _build_video_key(self, video: Dict) -> str:
        """Video için kaynak-bağımsız benzersiz anahtar üret"""
        source = str(video.get("source", "unknown"))
        raw_id = str(video.get("id", ""))
        download_url = str(video.get("download_url", ""))

        if raw_id and raw_id != "None":
            base = f"{source}:{raw_id}"
        elif download_url:
            digest = hashlib.sha1(download_url.encode("utf-8")).hexdigest()
            base = f"{source}:url:{digest}"
        else:
            digest = hashlib.sha1(str(video).encode("utf-8")).hexdigest()
            base = f"{source}:raw:{digest}"

        return base

    def _is_used_this_week(self, video: Dict) -> bool:
        """Video bu hafta kullanılmış mı?"""
        history = self._load_usage_history()
        week_key = self._get_current_week_key()
        used_keys = history.get(week_key, [])
        video_key = self._build_video_key(video)
        return video_key in used_keys

    def _mark_used_this_week(self, video: Dict):
        """Videoyu bu haftanın kullanım geçmişine ekle"""
        history = self._load_usage_history()
        week_key = self._get_current_week_key()

        # Sadece aktif haftaları tut (disk şişmesini önlemek için)
        active_keys = sorted(history.keys(), reverse=True)[:12]
        history = {k: history.get(k, []) for k in active_keys}

        used_keys = history.get(week_key, [])
        video_key = self._build_video_key(video)
        if video_key not in used_keys:
            used_keys.append(video_key)
            history[week_key] = used_keys
            self._save_usage_history(history)

    def search_videos(
        self,
        query: str,
        orientation: str = "portrait",
        min_duration: int = 5,
        max_duration: int = 30,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Hem Pexels hem Pixabay'den video ara (Hibrit & Dengeli)
        """
        results = []
        pexels_needed = max_results // 2
        pixabay_needed = max_results - pexels_needed
        
        # 1. Pexels'ten ara
        if self.pexels_key:
            pexels_results = self._search_pexels_videos(
                query, orientation, min_duration, max_duration, pexels_needed
            )
            results.extend(pexels_results)
            logger.info(f"📹 Pexels: {len(pexels_results)} video bulundu")
            
            # Eğer Pexels yetersiz geldiyse Pixabay'den daha fazla iste
            if len(pexels_results) < pexels_needed:
                pixabay_needed += (pexels_needed - len(pexels_results))
        
        # 2. Pixabay'den ara
        if self.pixabay_key:
            pixabay_results = self._search_pixabay_videos(
                query, orientation, min_duration, max_duration, pixabay_needed
            )
            results.extend(pixabay_results)
            logger.info(f"📹 Pixabay: {len(pixabay_results)} video bulundu")
            
            # Eğer toplam hala yetersizse ve Pexels'i eksik geçtiysek Pexels'ten tekrar dene (opsiyonel)
            # Ama genellikle Pixabay son duraktır.

        # 3. FALLBACK: Eğer hiç sonuç yoksa sorguyu basitleştirip tekrar dene
        if not results and " " in query:
            logger.warning(f"⚠️ Sonuç bulunamadı, sorgu basitleştiriliyor: {query}")
            simple_query = query.split()[0]
            return self.search_videos(simple_query, orientation, min_duration, max_duration, max_results)
            
        logger.info(f"✅ Toplam {len(results)} video bulundu")
        return results[:max_results]
    
    def _search_pexels_videos(
        self,
        query: str,
        orientation: str,
        min_duration: int,
        max_duration: int,
        per_page: int
    ) -> List[Dict]:
        """Pexels API'den video ara"""
        try:
            url = "https://api.pexels.com/videos/search"
            headers = {"Authorization": self.pexels_key}
            params = {
                "query": query,
                "per_page": per_page,
                "orientation": orientation
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            videos = data.get("videos", [])
            
            results = []
            for video in videos:
                duration = video.get("duration", 0)
                if min_duration <= duration <= max_duration:
                    # HD video dosyasını bul
                    video_files = video.get("video_files", [])
                    hd_file = next(
                        (vf for vf in video_files if vf.get("quality") == "hd"),
                        video_files[0] if video_files else None
                    )
                    
                    if hd_file:
                        results.append({
                            "source": "pexels",
                            "id": video["id"],
                            "duration": duration,
                            "width": video["width"],
                            "height": video["height"],
                            "download_url": hd_file["link"],
                            "preview_url": video.get("image"),
                            "tags": []  # Pexels doesn't provide tags
                        })
            
            return results
            
        except Exception as e:
            logger.error(f"Pexels search error: {e}")
            return []
    
    def _clean_query_for_pixabay(self, query: str) -> str:
        """
        Pixabay API için sorguyu temizle ve optimize et
        - Türkçe karakterleri dönüştür
        - Uzun sorguları kısalt (max 100 karakter, encoded)
        - Sadece anahtar kelimeleri al
        """
        import re
        import unicodedata

        source = (query or "").strip()
        if not source:
            return "nature"

        # 1. Türkçe karakterleri ASCII'ye dönüştür (örn: ş -> s)
        normalized = unicodedata.normalize('NFKD', source).encode('ASCII', 'ignore').decode('utf-8')

        # 2. Özel karakterleri temizle, birden fazla boşluğu tekilleştir
        normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()

        # 3. Kelimelere böl ve ilk 5-6 kelimeyi al
        words = normalized.split()
        if len(words) > 6:
            normalized = " ".join(words[:6])

        # 4. Max uzunluk kontrolü (Pixabay limiti 100 karakter)
        if len(normalized) > 95:
            normalized = normalized[:95].strip()

        return normalized or "nature"

    def _search_pixabay_videos(
        self,
        query: str,
        orientation: str,
        min_duration: int,
        max_duration: int,
        per_page: int
    ) -> List[Dict]:
        """Pixabay API'den video ara"""
        try:
            # 1. Optimize edilmiş sorgu
            clean_query = self._clean_query_for_pixabay(query)
            preview_q = (query or "")[:30]
            logger.info(f"🔍 Pixabay Query: '{clean_query}' (Original: '{preview_q}...')")

            url = "https://pixabay.com/api/videos/"
            base_params = {
                "key": self.pixabay_key,
                "per_page": max(3, per_page),  # Pixabay min limit is 3
                "video_type": "all"
            }

            # Çok adımlı fallback: tam sorgu -> ilk 3 kelime -> ilk kelime -> nature
            words = [w for w in clean_query.split() if w]
            candidate_queries = []
            if clean_query:
                candidate_queries.append(clean_query)
            if len(words) >= 3:
                candidate_queries.append(" ".join(words[:3]))
            if words:
                candidate_queries.append(words[0])
            candidate_queries.append("nature")

            # Tekrarlı adayları sırayı bozmadan kaldır
            dedup_queries = []
            seen = set()
            for q in candidate_queries:
                if q not in seen:
                    dedup_queries.append(q)
                    seen.add(q)

            response = None
            videos = []
            last_error = None

            for q in dedup_queries:
                params = dict(base_params)
                params["q"] = q
                try:
                    response = requests.get(url, params=params, timeout=15)
                    response.raise_for_status()
                    data = response.json()
                    videos = data.get("hits", [])
                    if videos:
                        if q != clean_query:
                            logger.warning(f"⚠️ Pixabay fallback query kullanıldı: '{q}'")
                        break
                except requests.exceptions.HTTPError as e:
                    last_error = e
                    status_code = e.response.status_code if e.response is not None else "unknown"
                    if status_code == 400:
                        logger.warning(f"⚠️ Pixabay 400 Error for query '{q}', next fallback deneniyor...")
                        continue
                    raise
                except requests.exceptions.RequestException as e:
                    last_error = e
                    logger.warning(f"⚠️ Pixabay request error for query '{q}': {e}")
                    continue

            if response is None and last_error:
                raise last_error
            
            results = []
            for video in videos:
                duration = video.get("duration", 0)
                if min_duration <= duration <= max_duration:
                    # En yüksek kaliteli videoyu bul
                    video_files = video.get("videos", {})
                    
                    # Öncelik sırası: large > medium > small
                    download_url = None
                    if "large" in video_files:
                        download_url = video_files["large"]["url"]
                    elif "medium" in video_files:
                        download_url = video_files["medium"]["url"]
                    elif "small" in video_files:
                        download_url = video_files["small"]["url"]
                    
                    if download_url:
                        results.append({
                            "source": "pixabay",
                            "id": video["id"],
                            "duration": duration,
                            "width": video.get("imageWidth", 1920),
                            "height": video.get("imageHeight", 1080),
                            "download_url": download_url,
                            "preview_url": video.get("userImageURL"),
                            "tags": video.get("tags", "").split(", ")
                        })
            
            return results
            
        except Exception as e:
            logger.error(f"Pixabay search error: {e}")
            return []
    
    def validate_content_with_gemini(
        self,
        video_url: str,
        script_text: str,
        theme: str
    ) -> Tuple[bool, str, float]:
        """
        Gemini AI ile video içeriğinin script'e uygunluğunu kontrol et
        
        Args:
            video_url: Video önizleme URL'i
            script_text: Video script metni
            theme: Video teması (finance, health, mystery, vb.)
            
        Returns:
            Tuple[bool, str, float]: (uygun_mu, açıklama, uygunluk_skoru)
        """
        if not self.gemini_client:
            logger.warning("Gemini client yok, validasyon atlandı")
            return True, "Gemini validation disabled", 1.0
        
        try:
            prompt = f"""
            Rol: Sen bir video içerik uzmanısın.
            
            Görev: Aşağıdaki video'nun script'e ve temaya uygun olup olmadığını değerlendir.
            
            Video Teması: {theme}
            Script Metni: {script_text[:500]}...
            
            Video URL: {video_url}
            
            Lütfen şunları değerlendir:
            1. Video içeriği script'e uygun mu?
            2. Görsel kalite yeterli mi?
            3. Telif hakkı sorunu var mı?
            4. Tema ile uyumlu mu?
            
            Yanıt formatı:
            UYGUN: [EVET/HAYIR]
            SKOR: [0.0-1.0]
            AÇIKLAMA: [Kısa açıklama]
            """
            
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            result_text = response.text.strip()
            
            # Parse response
            is_suitable = "EVET" in result_text.upper()
            
            # Skor çıkar
            score = 0.8  # Default
            if "SKOR:" in result_text:
                try:
                    score_line = [line for line in result_text.split("\n") if "SKOR:" in line][0]
                    parsed_score = float(score_line.split(":")[-1].strip())
                    score = max(0.0, min(1.0, parsed_score))
                except (ValueError, IndexError, TypeError) as parse_err:
                    logger.debug(f"Gemini score parse fallback kullanıldı: {parse_err}")
            
            # Açıklama çıkar
            explanation = result_text
            if "AÇIKLAMA:" in result_text:
                explanation = result_text.split("AÇIKLAMA:")[-1].strip()
            
            logger.info(f"✅ Gemini validation: {is_suitable} (score: {score})")
            return is_suitable, explanation, score
            
        except Exception as e:
            logger.error(f"Gemini validation error: {e}")
            return True, f"Validation error: {e}", 0.5
    
    def download_video(
        self,
        video_info: Dict,
        output_filename: str
    ) -> Optional[Path]:
        """
        Video'yu indir
        
        Args:
            video_info: search_videos'dan dönen video bilgisi
            output_filename: Kayıt dosya adı
            
        Returns:
            Path: İndirilen dosya yolu veya None
        """
        try:
            download_url = video_info.get("download_url")
            if not download_url:
                logger.error("Download URL bulunamadı")
                return None
            
            output_path = self.cache_dir / output_filename
            
            # Zaten varsa atla
            if output_path.exists():
                logger.info(f"✅ Video zaten mevcut: {output_filename}")
                return output_path
            
            logger.info(f"⬇️ İndiriliyor: {output_filename} ({video_info['source']})")
            
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"✅ İndirildi: {output_filename} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
            return output_path
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    def search_and_validate(
        self,
        query: str,
        script_text: str,
        theme: str,
        orientation: str = "portrait",
        min_duration: int = 5,
        max_duration: int = 30
    ) -> Optional[Dict]:
        """
        Video ara, Gemini ile doğrula ve en uygun olanı döndür
        
        Args:
            query: Arama sorgusu
            script_text: Video script metni
            theme: Video teması
            orientation: Video yönü
            min_duration: Minimum süre
            max_duration: Maksimum süre
            
        Returns:
            Dict: En uygun video bilgisi veya None
        """
        # Videoları ara
        videos = self.search_videos(
            query=query,
            orientation=orientation,
            min_duration=min_duration,
            max_duration=max_duration,
            max_results=5
        )
        
        if not videos:
            logger.warning(f"❌ '{query}' için video bulunamadı")
            return None
        
        # Gemini ile doğrula
        validated_videos = []

        for video in videos:
            preview_url = video.get("preview_url", "")

            is_suitable, explanation, score = self.validate_content_with_gemini(
                video_url=preview_url,
                script_text=script_text,
                theme=theme
            )

            if is_suitable:
                candidate = dict(video)
                candidate["validation_score"] = score
                candidate["validation_explanation"] = explanation
                validated_videos.append(candidate)

        if not validated_videos:
            logger.warning("⚠️ Gemini uygun klip bulamadı, haftalık tekrar kuralı nedeniyle seçim yapılmadı")
            return None

        # Skora göre sırala (yüksekten düşüğe)
        validated_videos.sort(key=lambda v: float(v.get("validation_score", 0.0)), reverse=True)

        # Haftalık tekrar kontrolü: bu hafta kullanılan klibi tekrar verme
        for candidate in validated_videos:
            if not self._is_used_this_week(candidate):
                self._mark_used_this_week(candidate)
                logger.info(
                    f"✅ En uygun video seçildi (haftalık benzersiz): {candidate['source']} "
                    f"(skor: {candidate.get('validation_score', 0.0):.2f})"
                )
                return candidate

        logger.warning(
            "⚠️ Bu hafta tüm uygun klipler daha önce kullanılmış. "
            "Tekrarı önlemek için seçim yapılmadı."
        )
        return None


# Global instance
_fetcher_instance = None

def get_multi_stock_fetcher() -> MultiStockFetcher:
    """Get or create global MultiStockFetcher instance"""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = MultiStockFetcher()
    return _fetcher_instance
