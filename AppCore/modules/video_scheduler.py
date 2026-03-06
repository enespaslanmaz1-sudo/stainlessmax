"""
Video Scheduler - Gemini ile Akıllı Zamanlama Sistemi
Her hesap için optimal paylaşım saatini belirler
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from google import genai
import os
import json
from pathlib import Path


class VideoScheduler:
    """Gemini 2.5 Pro ile optimal video paylaşım zamanı belirle"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        
        # Gemma AI (new SDK - hafif görev)
        self.model_name = "gemini-2.5-flash"
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.logger.warning("GEMINI_API_KEY yok, varsayılan saatler kullanılacak")
            self.client = None
        
        # Varsayılan saatler (Gemini yoksa)
        self.default_times = {
            "tiktok": [
                {"hour": 9, "minute": 0},   # Sabah (işe giderken)
                {"hour": 15, "minute": 0},  # Öğleden sonra
                {"hour": 21, "minute": 0}   # Akşam (ev)
            ],
            "youtube": [
                {"hour": 10, "minute": 0},  # Sabah
                {"hour": 16, "minute": 0},  # Öğleden sonra
                {"hour": 20, "minute": 0}   # Akşam
            ]
        }
        
        # Schedule cache
        self.schedule_cache = {}
    
    async def get_optimal_post_time(
        self,
        account_id: str,
        platform: str = "tiktok",
        niche: str = "finance",
        target_audience: str = "18-35 yaş, Türkiye",
        force_refresh: bool = False
    ) -> Dict:
        """
        Gemini ile optimal paylaşım saatini hesapla
        
        Args:
            account_id: Hesap ID
            platform: Platform (tiktok, youtube)
            niche: İçerik kategorisi
            target_audience: Hedef kitle
            force_refresh: Cache'i yoksay
            
        Returns:
            Dict: {hour, minute, reason, estimated_engagement}
        """
        try:
            # Cache kontrolü
            cache_key = f"{account_id}_{platform}_{niche}"
            if not force_refresh and cache_key in self.schedule_cache:
                cached = self.schedule_cache[cache_key]
                # Cache 24 saatten eski değilse kullan
                if (datetime.now() - cached["timestamp"]).seconds < 86400:
                    self.logger.info(f"Cache'den optimal saat: {cached['time']}")
                    return cached["time"]
            
            # Gemini yoksa varsayılan
            if not self.client:
                return self._get_default_time(platform)
            
            # Gemini'den optimal saat iste
            prompt = self._create_scheduling_prompt(
                platform=platform,
                niche=niche,
                target_audience=target_audience
            )
            
            self.logger.info(f"Gemini'den optimal saat sorgulanıyor: {platform}/{niche}")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = self._parse_scheduling_response(response.text)
            
            if result:
                # Cache'le
                self.schedule_cache[cache_key] = {
                    "time": result,
                    "timestamp": datetime.now()
                }
                
                self.logger.info(
                    f"✅ Optimal saat: {result['hour']:02d}:{result['minute']:02d} "
                    f"(Engagement: {result.get('estimated_engagement', 'N/A')})"
                )
                
                return result
            else:
                self.logger.warning("Gemini response parse edilemedi, varsayılan kullanılıyor")
                return self._get_default_time(platform)
                
        except Exception as e:
            self.logger.error(f"Optimal saat hesaplama hatası: {e}")
            return self._get_default_time(platform)
    
    def _create_scheduling_prompt(
        self,
        platform: str,
        niche: str,
        target_audience: str
    ) -> str:
        """Gemini için scheduling prompt oluştur"""
        
        current_date = datetime.now()
        day_of_week = current_date.strftime("%A")  # Monday, Tuesday...
        
        prompt = f"""Sen sosyal medya uzmanısın. **{platform.upper()}** platformu için optimal video paylaşım saatini belirle.

**PLATFORM:** {platform.upper()}
**İÇERİK KATEGORİSİ:** {niche}
**HEDEF KİTLE:** {target_audience}
**GÜN:** {day_of_week}
**TARİH:** {current_date.strftime('%Y-%m-%d')}

**GÖREV:**
1. Bu platform, konu ve hedef kitle için BUGÜN hangi saatte video paylaşılırsa en çok izlenme alır?
2. Kullanıcı davranışlarını, platform algoritmalarını ve günlük rutinleri analiz et
3. Tek bir optimal saat öner (birden fazla değil, EN İYİ olanı)

**DİKKAT EDILECEKLER:**
- Türkiye saat dilimi (GMT+3)
- {platform} algoritması prime time saatleri
- {niche} içeriği tüketen kullanıcıların aktif olduğu saatler
- {day_of_week} gününün özellikleri
- Rekabet (çok içerik paylaşılıyorsa kaçın)

**ÖNEMLİ:** 
- Sadece JSON döndür, başka metin ekleme
- Saat 24 saat formatında (0-23)
- Dakika 0, 15, 30, 45 olmalı

**FORMAT:**
```json
{{
  "hour": 15,
  "minute": 30,
  "estimated_engagement": "Yüksek/Orta/Düşük",
  "reason": "Neden bu saat optimal (1-2 cümle)",
  "alternative_times": [
    {{"hour": 20, "minute": 0}},
    {{"hour": 9, "minute": 0}}
  ]
}}
```

Şimdi {platform} için bugün optimal saati belirle:"""
        
        return prompt
    
    def _parse_scheduling_response(self, response_text: str) -> Optional[Dict]:
        """Gemini scheduling yanıtını parse et"""
        try:
            import re
            
            # JSON bloğunu bul
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()
            
            result = json.loads(json_str)
            
            # Validasyon
            if "hour" not in result or "minute" not in result:
                return None
            
            # Saat kontrolü
            if not (0 <= result["hour"] <= 23):
                return None
            if not (0 <= result["minute"] <= 59):
                return None
            
            return result
            
        except Exception as e:
            self.logger.error(f"Scheduling response parse hatası: {e}")
            return None
    
    def _get_default_time(self, platform: str) -> Dict:
        """Varsayılan optimal saat (Gemini yoksa)"""
        times = self.default_times.get(platform, self.default_times["tiktok"])
        
        # Şu anki saate en yakın olanı seç
        current_hour = datetime.now().hour
        
        best_time = times[0]
        min_diff = abs(current_hour - best_time["hour"])
        
        for t in times:
            diff = abs(current_hour - t["hour"])
            if diff < min_diff:
                min_diff = diff
                best_time = t
        
        return {
            **best_time,
            "estimated_engagement": "Orta",
            "reason": "Varsayılan prime time saati",
            "alternative_times": times
        }
    
    async def schedule_daily_posts(
        self,
        account_id: str,
        videos_per_day: int = 3,
        min_interval_hours: int = 8
    ) -> List[Dict]:
        """
        Bir hesap için günlük paylaşım programı oluştur
        
        Args:
            account_id: Hesap ID
            videos_per_day: Günlük video sayısı
            min_interval_hours: Minimum aralık (saat)
            
        Returns:
            List[Dict]: [{hour, minute, video_index}, ...]
        """
        try:
            # İlk optimal saati al
            first_time = await self.get_optimal_post_time(account_id)
            
            schedule = []
            current_time = datetime.now().replace(
                hour=first_time["hour"],
                minute=first_time["minute"],
                second=0,
                microsecond=0
            )
            
            for i in range(videos_per_day):
                schedule.append({
                    "video_index": i,
                    "hour": current_time.hour,
                    "minute": current_time.minute,
                    "datetime": current_time.isoformat()
                })
                
                # Sonraki video için saat ekle
                current_time += timedelta(hours=min_interval_hours)
            
            self.logger.info(f"✅ Günlük program oluşturuldu: {len(schedule)} video")
            
            return schedule
            
        except Exception as e:
            self.logger.error(f"Günlük program oluşturma hatası: {e}")
            return []


# Test
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    logging.basicConfig(level=logging.INFO)
    
    async def test_scheduler():
        print("="*60)
        print("GEMINI VIDEO SCHEDULER TEST")
        print("="*60)
        
        scheduler = VideoScheduler()
        
        # Test 1: TikTok optimal saat
        print("\n[Test 1] TikTok - Paranın gücü içeriği")
        optimal = await scheduler.get_optimal_post_time(
            account_id="tiktok_main",
            platform="tiktok",
            niche="finance",
            target_audience="18-35 yaş, Türkiye, para kazanma ilgisi"
        )
        
        print(f"\n✅ Optimal Saat: {optimal['hour']:02d}:{optimal['minute']:02d}")
        print(f"   Engagement: {optimal.get('estimated_engagement', 'N/A')}")
        print(f"   Sebep: {optimal.get('reason', 'N/A')}")
        
        if "alternative_times" in optimal:
            print(f"\n  Alternatif saatler:")
            for alt in optimal["alternative_times"]:
                print(f"    - {alt['hour']:02d}:{alt['minute']:02d}")
        
        # Test 2: Günlük program
        print("\n[Test 2] Günlük 3 video programı")
        daily_schedule = await scheduler.schedule_daily_posts(
            account_id="tiktok_main",
            videos_per_day=3,
            min_interval_hours=8
        )
        
        for item in daily_schedule:
            print(f"  Video {item['video_index']+1}: {item['hour']:02d}:{item['minute']:02d}")
    
    asyncio.run(test_scheduler())
