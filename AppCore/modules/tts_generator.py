"""
TTS Generator - Multi-Engine Ses Üretimi
Edge TTS (ücretsiz) + Gemini 2.5 Flash TTS (premium AI) desteği
"""

import os
import json
import asyncio
import edge_tts
from pathlib import Path
from typing import Optional, Literal
import logging
from datetime import datetime

# Gemini TTS (optional)
try:
    from .gemini_tts import GeminiTTS, GEMINI_VOICES, CONTENT_VOICE_MAP
    GEMINI_TTS_AVAILABLE = True
except ImportError:
    GEMINI_TTS_AVAILABLE = False

# VOICE_MAP Definition
VOICE_MAP = {
    # Turkish
    "finance_tr": "en-US-ChristopherNeural",
    "education_tr": "en-US-ChristopherNeural",
    "health_tr": "en-US-ChristopherNeural",
    "motivation_tr": "en-US-ChristopherNeural",
    "story_tr": "en-US-ChristopherNeural",
    "news_tr": "en-US-ChristopherNeural",
    # English
    "male_default": "en-US-ChristopherNeural",
    "female_default": "en-US-AriaNeural",
    "viral_mix": "en-US-EricNeural",
    "story": "en-US-MichelleNeural",
    "news": "en-US-RogerNeural"
}

class TTSGenerator:
    """Multi-Engine TTS: Edge TTS (ücretsiz) + Gemini TTS (premium)"""
    
    def __init__(self, output_dir: str = "audio", engine: str = None):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Engine seçimi: settings.json'dan veya parametreden
        self.engine = engine or self._load_engine_preference()
        
        # Gemini TTS instance (lazy)
        self._gemini_tts = None
        
        self.logger.info(f"🎙️ TTS Engine: {self.engine.upper()}")
    
    def _load_engine_preference(self) -> str:
        """settings.json'dan TTS engine tercihini oku"""
        try:
            settings_path = Path(__file__).parent.parent.parent / "settings.json"
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings.get("tts", {}).get("engine", "gemini")
        except Exception:
            pass
        return "gemini"  # Default: Gemini TTS
    
    def _get_gemini_tts(self) -> Optional['GeminiTTS']:
        """Gemini TTS instance'ını lazy olarak oluştur"""
        if self._gemini_tts is None and GEMINI_TTS_AVAILABLE:
            self._gemini_tts = GeminiTTS(output_dir=str(self.output_dir))
        return self._gemini_tts
    
    async def text_to_speech(
        self,
        text: str,
        output_file: str,
        voice: str = "en-US-ChristopherNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "-5Hz"
    ) -> tuple[Optional[Path], Optional[Path]]:
        """
        TTS üretir ve SRT dosyası döndürür (Async)
        Returns: (audio_path, srt_path)
        """
        try:
            output_path = self.output_dir / output_file
            self.logger.info(f"TTS başlatılıyor (Edge-TTS) - Voice: {voice}")
            
            # Voice Mapping (Kısa kodlar için)
            if voice == "tr": voice = "en-US-ChristopherNeural" 
            elif voice == "en": voice = "en-US-ChristopherNeural"

            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
            submaker = edge_tts.SubMaker()
            
            # Stream ve ses verisini kaydet
            with open(output_path, 'wb') as audio_file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_file.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        # self.logger.debug(f"WordBoundary: {chunk['text']}")
                        start_time = chunk["offset"]
                        end_time = chunk["offset"] + chunk["duration"]
                        submaker.create_sub((start_time, end_time), chunk["text"])
            
            # SRT oluştur
            srt_path = self._create_srt_from_submaker(submaker, output_path, text)
            
            self.logger.info(f"✅ TTS başarılı: {output_path}")
            return output_path, srt_path
                
        except Exception as e:
            self.logger.error(f"TTS üretim hatası: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None, None

    def text_to_speech_sync(
        self,
        text: str,
        output_file: str,
        voice: str = "tr-TR-AhmetNeural",
        **kwargs
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Senkron wrapper - Mevcut yapıları bozmamak için"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            return loop.run_until_complete(self.text_to_speech(text, output_file, voice, **kwargs))
        except Exception as e:
            self.logger.error(f"TTS Sync hatası: {e}")
            return None, None
    
    def _create_srt_from_submaker(self, submaker, audio_path: Path, full_text: str = "") -> Optional[Path]:
        """SubMaker'dan SRT dosyası oluştur (Word grouping ile + Fallback)"""
        try:
            srt_path = audio_path.with_suffix('.srt')
            grouped_subs = []
            
            # 1. WordBoundary verisi varsa işle
            if hasattr(submaker, 'subs') and len(submaker.subs) > 0:
                current_group = []
                current_char_count = 0
                current_start_time = 0
                
                for i, (time_range, text) in enumerate(submaker.subs):
                    # Edge-TTS stores: ((start_100ns, end_100ns), text)
                    start_ms = time_range[0] / 10000
                    end_ms = time_range[1] / 10000
                    
                    if not current_group:
                        current_start_time = start_ms
                    
                    current_group.append(text)
                    current_char_count += len(text) + 1
                    
                    is_end_of_sentence = text.strip()[-1] in ".!?" if text.strip() else False
                    is_too_long = current_char_count > 30
                    is_last = (i == len(submaker.subs) - 1)
                    
                    if is_end_of_sentence or is_too_long or is_last:
                        group_text = " ".join(current_group)
                        grouped_subs.append({
                            "start": current_start_time,
                            "end": end_ms,
                            "text": group_text
                        })
                        current_group = []
                        current_char_count = 0
            
            # 2. FALLBACK: WordBoundary yoksa (Tek parça SRT oluştur)
            else:
                self.logger.warning("⚠️ WordBoundary verisi yok, Fallback SRT oluşturuluyor...")
                
                # Ses süresini tahmin et (MP3 dosya boyutu üzerinden)
                # 128kbps ~ 16KB/s (veya 32kbps olabilir, güvenli tahmin lazım)
                # Edge-TTS genellikle 24kHz mono ~32-48kbps döner ama değişebilir.
                # En güvenlisi: Ortalama okuma hızı (saniyede 15 karakter)
                if not full_text:
                    return None
                    
                estimated_duration_sec = len(full_text) / 15.0 # Çok kaba tahmin
                estimated_duration_ms = estimated_duration_sec * 1000
                
                # Metni cümlelere böl
                import re
                sentences = re.split(r'(?<=[.!?])\s+', full_text)
                
                start_ms = 0
                total_chars = len(full_text)
                
                for sentence in sentences:
                    if not sentence.strip(): continue
                    
                    # Bu cümlenin süresi (karakter oranına göre)
                    duration_ms = (len(sentence) / total_chars) * estimated_duration_ms
                    end_ms = start_ms + duration_ms
                    
                    grouped_subs.append({
                        "start": start_ms,
                        "end": end_ms,
                        "text": sentence
                    })
                    start_ms = end_ms

            # SRT Yaz
            with open(srt_path, 'w', encoding='utf-8') as f:
                for idx, item in enumerate(grouped_subs, start=1):
                    start_time = self._format_time_srt(int(item["start"]))
                    end_time = self._format_time_srt(int(item["end"]))
                    
                    f.write(f"{idx}\n{start_time} --> {end_time}\n{item['text']}\n\n")
            
            self.logger.info(f"✅ SRT oluşturuldu: {srt_path} ({len(grouped_subs)} satır)")
            return srt_path
            
        except Exception as e:
            self.logger.error(f"SRT oluşturma hatası: {e}")
            return None

    async def transcribe_with_whisper(self, audio_path: Path) -> Optional[Path]:
        """Whisper kullanarak sesi yazıya dök ve SRT oluştur"""
        try:
            self.logger.info(f"🎙️ Whisper transcription başlatılıyor: {audio_path.name}")
            
            # Modeli yükle (Base model hız/kalite dengesi için ideal)
            # Not: İlk kullanımda indirme yapabilir
            import whisper
            model = whisper.load_model("base")
            
            # Transcribe
            result = model.transcribe(str(audio_path), verbose=False)
            
            srt_path = audio_path.with_suffix('.srt')
            
            with open(srt_path, 'w', encoding='utf-8-sig') as f:
                for i, segment in enumerate(result['segments'], 1):
                    start_time = self._format_time_srt(int(segment['start'] * 1000))
                    end_time = self._format_time_srt(int(segment['end'] * 1000))
                    text = segment['text'].strip()
                    
                    # Satır bölme (Whisper bazen uzun döner)
                    if len(text) > 40:
                        words = text.split()
                        mid = len(words) // 2
                        text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
                    
                    f.write(f"{i}\n{start_time} --> {end_time}\n{text}\n\n")
            
            self.logger.info(f"✅ Whisper SRT oluşturuldu: {srt_path}")
            return srt_path
            
        except Exception as e:
            self.logger.error(f"Whisper transcription error: {e}")
            return None

    def _format_time_srt(self, milliseconds: int) -> str:
        """Milliseconds'ı SRT time formatına çevir (00:00:00,000)"""
        hours = milliseconds // 3600000
        milliseconds %= 3600000
        minutes = milliseconds // 60000
        milliseconds %= 60000
        seconds = milliseconds // 1000
        ms = milliseconds % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

    def get_voice_for_content(
        self,
        content_type: Literal["finance", "education", "health", "motivation", "story", "news"],
        language: Literal["tr", "en"] = "tr"
    ) -> str:
        """
        İçerik türüne göre en uygun sesi seç
        """
        if language == "tr":
            key = f"{content_type}_tr"
            return VOICE_MAP.get(key, "en-US-ChristopherNeural")
        else:
            # İngilizce için
            mapping = {
                "finance": "male_default",
                "education": "news",
                "health": "news",
                "motivation": "viral_mix",
                "story": "story",
                "news": "news"
            }
            key = mapping.get(content_type, "viral_mix")
            return VOICE_MAP.get(key, "en-US-AriaNeural")
            
    def _generate_sliding_window_srt(self, timings: list, output_path: Path):
        """
        Timings listesinden 'kayan pencere' (context) SRT oluştur
        Format: [Prev2] [Prev1] [Current] [Next1]
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, timing in enumerate(timings):
                    # Kayan pencere kelimelerini belirle
                    words = []
                    
                    # Previous 2
                    if i > 1: words.append(timings[i-2]["text"])
                    elif i > 0: words.append(timings[i-1]["text"])
                    
                    # Current
                    words.append(timings[i]["text"])
                    
                    # Next 1
                    if i < len(timings) - 1:
                        words.append(timings[i+1]["text"])
                    
                    line_text = " ".join(words)
                    
                    # Zamanlama
                    start_sec = timing["start"]
                    end_sec = timing["end"]
                    
                    # Format: 00:00:00,000
                    def sec_to_srt(sec):
                        m, s = divmod(sec, 60)
                        h, m = divmod(m, 60)
                        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")
                        
                    f.write(f"{i+1}\n")
                    f.write(f"{sec_to_srt(start_sec)} --> {sec_to_srt(end_sec)}\n")
                    f.write(f"{line_text}\n\n")
                    
            return True
        except Exception as e:
            self.logger.error(f"SRT Generation Error: {e}")
            return False
    
    async def create_narration_for_scenario(
        self,
        scenario: dict,
        account_topic: str = "finance",
        voice: str = None
    ) -> Optional[tuple[Path, Path]]:
        """
        Senaryo için tam seslendirme oluştur.
        Engine'e göre Gemini TTS veya Edge TTS kullanır.
        Gemini başarısız olursa Edge TTS'e fallback yapar.
        Returns: (audio_path, srt_path)
        """
        try:
            # ===== GEMINI TTS ENGINE =====
            if self.engine == "gemini":
                gemini = self._get_gemini_tts()
                if gemini and gemini.client:
                    self.logger.info("🎙️ Gemini TTS Engine kullanılıyor...")
                    result = await gemini.create_narration_for_scenario(
                        scenario=scenario,
                        account_topic=account_topic,
                        voice=voice
                    )
                    if result and result[0]:
                        self.logger.info(f"✅ Gemini Narration Hazır: {result[0]}")
                        return result
                    else:
                        self.logger.warning("⚠️ Gemini TTS başarısız, Edge TTS'e geçiliyor...")
                else:
                    self.logger.warning("⚠️ Gemini TTS kullanılamıyor, Edge TTS'e geçiliyor...")
            
            # ===== EDGE TTS ENGINE (Default / Fallback) =====
            self.logger.info("🎙️ Edge TTS Engine kullanılıyor...")
            
            # 1. Metni birleştir (SADECE SAHNELER)
            full_text = ""
            for scene in scenario.get("scenes", []):
                full_text += scene.get("narration", "") + " "
            
            full_text = full_text.strip()
            if not full_text: return None, None

            # 2. Ses Seç (Edge TTS)
            if not voice or voice in (GEMINI_VOICES if GEMINI_TTS_AVAILABLE else {}):
                voice = self.get_voice_for_content(account_topic, language="tr")
            
            # 3. Dosya yolları
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = self.output_dir / f"narration_{timestamp}.mp3"
            
            self.logger.info(f"Edge TTS Üretiliyor... Voice: {voice}")
            
            # 4. Edge TTS çağır
            audio_path_result, srt_path_result = await self.text_to_speech(
                text=full_text,
                output_file=audio_path.name,
                voice=voice,
                rate="+0%",
                pitch="-5Hz"
            )
            
            if audio_path_result:
                self.logger.info(f"✅ Edge Narration Hazır: {audio_path_result}")
                if srt_path_result:
                    self.logger.info(f"✅ SRT Hazır: {srt_path_result}")
                return audio_path_result, srt_path_result
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Senaryo seslendirme hatası: {e}")
            return None, None
    
    @staticmethod
    async def list_available_voices():
        """Kullanılabilir tüm sesleri listele"""
        voices = await edge_tts.list_voices()
        
        # Türkçe sesleri filtrele
        turkish_voices = [v for v in voices if v["Locale"].startswith("tr-TR")]
        
        print("\n🇹🇷 TÜRKÇE SESLER:")
        for v in turkish_voices:
            print(f"  - {v['ShortName']}: {v['FriendlyName']} ({v['Gender']})")
        
        # İngilizce Neural sesleri
        english_voices = [
            v for v in voices 
            if v["Locale"].startswith("en-US") and "Neural" in v["ShortName"]
        ][:10]
        
        print("\n🇺🇸 İNGİLİZCE SESLER (İlk 10 Neural):")
        for v in english_voices:
            print(f"  - {v['ShortName']}: {v['FriendlyName']} ({v['Gender']})")


# Test ve örnek kullanım
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    async def test_tts():
        """TTS test fonksiyonu"""
        
        print("="*60)
        print("EDGE TTS TEST")
        print("="*60)
        
        tts = TTSGenerator()
        
        # Test 1: Türkçe Erkek Ses (Finans)
        print("\n[Test 1] Türkçe erkek ses (Finans konusu)")
        test_text = "Zengin insanların asla söylemediği 3 sır! Para parayı sever, zenginler parasını hep çalıştırır."
        
        result = await tts.text_to_speech(
            text=test_text,
            output_file="test_turkish_male.mp3",
            voice=VOICE_MAP["finance_tr"],
            rate="+10%"
        )
        
        if result:
            print(f"✅ Başarılı: {result}")
        
        # Test 2: Türkçe Kadın Ses (Sağlık)
        print("\n[Test 2] Türkçe kadın ses (Sağlık konusu)")
        health_text = "Sağlıklı yaşam için her gün 30 dakika yürüyüş yapın ve bol su için."
        
        result = await tts.text_to_speech(
            text=health_text,
            output_file="test_turkish_female.mp3",
            voice=VOICE_MAP["health_tr"]
        )
        
        if result:
            print(f"✅ Başarılı: {result}")
        
        # Test 3: Otomatik ses seçimi
        print("\n[Test 3] Otomatik ses seçimi")
        auto_voice = tts.get_voice_for_content("motivation", language="tr")
        print(f"Motivasyon içeriği için seçilen ses: {auto_voice}")
        
        result = await tts.text_to_speech(
            text="Sen de başarabilirsin! Vazgeçme, devam et!",
            output_file="test_motivation.mp3",
            voice=auto_voice,
            rate="+15%",  # Motivasyon için daha hızlı
            pitch="+5Hz"  # Biraz daha yüksek ton
        )
        
        if result:
            print(f"✅ Başarılı: {result}")
        
        print("\n" + "="*60)
        print("TÜM TESTLER TAMAMLANDI")
        print("="*60)
        print("\nOluşturulan dosyalar 'audio/' klasöründe")
    
    # Async fonksiyonu çalıştır
    asyncio.run(test_tts())
