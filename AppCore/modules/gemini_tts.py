"""
Gemini TTS - Google Gemini 2.5 Flash ile Yüksek Kaliteli Ses Üretimi
Premium AI ses sentezi - Doğal, ifadeli ve kontrol edilebilir sesler
"""

import os
import wave
import asyncio
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Literal, Dict, Tuple
from datetime import datetime

# Gemini SDK (new google-genai package)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# ===== VOICE CONFIGURATION =====

# Gemini TTS desteklenen sesler ve karakteristikleri
GEMINI_VOICES = {
    # Erkek sesler
    "Puck": {"gender": "male", "style": "upbeat, energetic", "best_for": ["motivation", "finance", "viral"]},
    "Charon": {"gender": "male", "style": "deep, serious", "best_for": ["documentary", "mystery", "news"]},
    "Fenrir": {"gender": "male", "style": "authoritative, strong", "best_for": ["news", "education", "serious"]},
    "Orus": {"gender": "male", "style": "warm, authoritative", "best_for": ["education", "tutorial"]},
    "Zephyr": {"gender": "neutral", "style": "calm, neutral", "best_for": ["general", "meditation"]},
    "Enceladus": {"gender": "male", "style": "breathy, thoughtful", "best_for": ["story", "mystery"]},
    
    # Kadın sesler
    "Kore": {"gender": "female", "style": "clear, youthful", "best_for": ["general", "narration", "viral"]},
    "Aoede": {"gender": "female", "style": "warm, friendly", "best_for": ["story", "education", "health"]},
    "Leda": {"gender": "female", "style": "soft, gentle", "best_for": ["health", "wellness", "meditation"]},
    "Elara": {"gender": "female", "style": "composed, professional", "best_for": ["news", "business"]},
}

# İçerik türüne göre otomatik ses seçimi  
CONTENT_VOICE_MAP = {
    "finance": "Puck",
    "education": "Orus",
    "health": "Leda",
    "motivation": "Puck",
    "story": "Aoede",
    "news": "Fenrir",
    "mystery": "Charon",
    "documentary": "Charon",
    "viral": "Kore",
    "general": "Kore",
    "tutorial": "Orus",
    "meditation": "Zephyr",
}

# İçerik türüne göre stil prompt'ları
STYLE_PROMPTS = {
    "finance": "Speak with confidence and authority, like a financial expert sharing insider knowledge. Engaging and compelling.",
    "education": "Speak clearly and warmly, like an enthusiastic teacher. Well-paced and easy to follow.",
    "health": "Speak gently and reassuringly, like a caring health professional. Calm and trustworthy.",
    "motivation": "Speak with high energy and passion, like a motivational speaker on stage. Inspiring and powerful.",
    "story": "Speak with dramatic flair, like a master storyteller around a campfire. Captivating and immersive.",
    "news": "Speak with authority and clarity, like a professional news anchor. Serious and informative.",
    "mystery": "Speak with a mysterious, intriguing tone. Slow and suspenseful, drawing the listener in.",
    "documentary": "Speak with gravitas and wonder, like a nature documentary narrator. Rich and descriptive.",
    "viral": "Speak with energy and excitement, like a popular content creator. Fast-paced and attention-grabbing.",
    "general": "Speak naturally and engagingly, with clear pronunciation and good pacing.",
}


class SmartVoiceSelector:
    """Metin içeriğine göre akıllı ses seçimi"""
    
    # Kelime Havuzları (Tr & En)
    KEYWORDS = {
        "female": [
            "22 yaşında bir kadınım", "ben bir kadınım", "ben bir kızım", "kocam", "eşim", "sevgilim", "erkek arkadaşım", 
            "annem", "kız kardeşim", "teyzem", "halam", "gelinim", "kaynanam",
            "i am a woman", "i'm a girl", "my husband", "my boyfriend", "i am a 22 year old woman"
        ],
        "male": [
            "ben bir erkeğim", "ben bir adamım", "karım", "eşim", "sevgilim", "kız arkadaşım",
            "babam", "erkek kardeşim", "amcam", "dayım", "damadım",
            "i am a man", "i'm a boy", "my wife", "my girlfriend"
        ]
    }
    
    @staticmethod
    def detect_gender(text: str) -> str:
        """Metindeki ipuçlarından cinsiyet tahmini yap"""
        text_lower = text.lower()
        
        female_score = 0
        male_score = 0
        
        for k in SmartVoiceSelector.KEYWORDS["female"]:
            if k in text_lower:
                female_score += 1
                
        for k in SmartVoiceSelector.KEYWORDS["male"]:
            if k in text_lower:
                male_score += 1
        
        if female_score > male_score:
            return "female"
        elif male_score > female_score:
            return "male"
        return "neutral"

    @staticmethod
    def select_voice(text: str, content_type: str = "story", language: str = "tr") -> str:
        """En uygun Gemini sesini seç"""
        gender = SmartVoiceSelector.detect_gender(text)
        
        # SESE ÖZEL SEÇİMLER
        if gender == "female":
            return "Aoede" # Warm, friendly
        elif gender == "male":
             return "Charon" # Deep, serious
        else:
            if content_type == "finance":
                return "Puck"
            elif content_type in ["news", "mystery", "documentary"]:
                return "Charon"
            else:
                return "Fenrir"

class GeminiTTS:
    """
    Gemini 2.5 Flash TTS ile yüksek kaliteli ses üretimi.
    
    Özellikler:
    - 30+ doğal ses seçeneği
    - Stil/ton/hız kontrolü (prompt ile)
    - Multi-speaker desteği
    - 24 dil desteği
    - Edge TTS fallback
    """
    
    MODEL = "gemini-2.5-flash-preview-tts"  # TTS destekli model (Preview)
    SAMPLE_RATE = 24000
    SAMPLE_WIDTH = 2  # 16-bit
    CHANNELS = 1  # Mono
    
    def __init__(self, output_dir: str = "audio", api_key: str = None):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # API Key
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        
        # Gemini Client
        self.client = None
        if GENAI_AVAILABLE and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.logger.info("✅ Gemini TTS client initialized")
            except Exception as e:
                self.logger.error(f"Gemini TTS client init failed: {e}")
        else:
            if not GENAI_AVAILABLE:
                self.logger.warning("⚠️ google-genai package not installed")
            if not self.api_key:
                self.logger.warning("⚠️ GEMINI_API_KEY not found")
        
        # FFmpeg path (WAV → MP3 dönüşümü için)
        self.ffmpeg_path = self._find_ffmpeg()
    
    def _find_ffmpeg(self) -> Optional[str]:
        """FFmpeg yolunu bul"""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        
        # Windows fallback paths
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _save_wav(self, filename: Path, pcm_data: bytes) -> Path:
        """PCM verisini WAV dosyasına kaydet"""
        with wave.open(str(filename), "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(pcm_data)
        return filename
    
    def _convert_wav_to_mp3(self, wav_path: Path, mp3_path: Path = None) -> Optional[Path]:
        """WAV dosyasını MP3'e dönüştür (FFmpeg)"""
        if not self.ffmpeg_path:
            self.logger.warning("FFmpeg not found, keeping WAV format")
            return wav_path
        
        if mp3_path is None:
            mp3_path = wav_path.with_suffix('.mp3')
        
        try:
            cmd = [
                self.ffmpeg_path,
                "-y",  # Overwrite
                "-i", str(wav_path),
                "-codec:a", "libmp3lame",
                "-qscale:a", "2",  # High quality
                "-ar", "44100",
                str(mp3_path)
            ]
            
            import sys
            _no_win = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=_no_win
            )
            
            if result.returncode == 0 and mp3_path.exists():
                # WAV dosyasını sil
                wav_path.unlink(missing_ok=True)
                self.logger.info(f"✅ Converted to MP3: {mp3_path.name}")
                return mp3_path
            else:
                self.logger.error(f"FFmpeg error: {result.stderr[:200]}")
                return wav_path
                
        except Exception as e:
            self.logger.error(f"WAV→MP3 conversion failed: {e}")
            return wav_path
    
    def get_voice_for_content(
        self,
        content_type: str,
        language: str = "en"
    ) -> str:
        """İçerik türüne göre en uygun Gemini sesini seç"""
        content_lower = content_type.lower()
        return CONTENT_VOICE_MAP.get(content_lower, "Kore")
    
    def get_style_prompt(self, content_type: str) -> str:
        """İçerik türüne göre stil prompt'u döndür"""
        return STYLE_PROMPTS.get(content_type.lower(), STYLE_PROMPTS["general"])
    
    async def text_to_speech(
        self,
        text: str,
        output_file: str,
        voice: str = "Kore",
        style: str = None,
        content_type: str = "general",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "-5Hz",
        client = None 
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Gemini TTS ile metin → ses dönüşümü.
        
        Args:
            text: Seslendirilecek metin
            output_file: Çıktı dosya adı
            voice: Gemini ses adı (Kore, Puck, Charon vb.)
            style: Özel stil prompt'u (None ise content_type'a göre seçilir)
            content_type: İçerik türü (finance, education, story vb.)
            rate/volume/pitch: Edge TTS uyumluluğu için (Gemini'de kullanılmaz)
            client: Optional external genai.Client instance (for rotation)
        
        Returns:
            (audio_path, srt_path) - SRT Gemini'de None döner
        """
        # Use provided client or internal client
        active_client = client or self.client
        
        if not active_client:
            self.logger.error("❌ Gemini TTS client not available")
            return None, None
        
        try:
            # Çıktı yolu
            output_path = self.output_dir / output_file
            wav_path = output_path.with_suffix('.wav')
            
            # Ses seçimi
            if voice not in GEMINI_VOICES:
                voice = self.get_voice_for_content(content_type)
            
            # Stil prompt'u
            if not style:
                style = self.get_style_prompt(content_type)
            
            # Prompt oluştur: stil + metin
            prompt = f"{style}\n\n{text}"
            
            self.logger.info(f"🎙️ Gemini TTS başlatılıyor - Voice: {voice}, Style: {content_type}")
            self.logger.info(f"   Metin uzunluğu: {len(text)} karakter")
            
            # Gemini TTS API çağrısı
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: active_client.models.generate_content(
                    model=self.MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            )
                        ),
                    )
                )
            )
            
            # PCM veriyi çıkar
            if (response.candidates and 
                response.candidates[0].content and 
                response.candidates[0].content.parts):
                
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                
                if not pcm_data or len(pcm_data) < 100:
                    raise Exception("Gemini TTS returned empty or too short audio data")
                
                # WAV olarak kaydet
                self._save_wav(wav_path, pcm_data)
                
                # MP3'e dönüştür
                final_path = self._convert_wav_to_mp3(wav_path)
                
                duration_sec = len(pcm_data) / (self.SAMPLE_RATE * self.SAMPLE_WIDTH * self.CHANNELS)
                self.logger.info(f"✅ Gemini TTS başarılı: {final_path.name} ({duration_sec:.1f}s)")
                
                # Gemini TTS harici SRT üretmiyor → None
                return final_path, None
            else:
                raise Exception("Gemini TTS returned no audio content")
                
        except Exception as e:
            # If client was provided externally, re-raise to allow rotation handling
            if client:
                raise e
            
            self.logger.error(f"❌ Gemini TTS hatası: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None, None
    
    def text_to_speech_sync(
        self,
        text: str,
        output_file: str,
        voice: str = "Kore",
        **kwargs
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Senkron wrapper"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.text_to_speech(text, output_file, voice, **kwargs)
                )
            finally:
                loop.close()
        except Exception as e:
            self.logger.error(f"Gemini TTS Sync hatası: {e}")
            return None, None
    
    async def create_narration_for_scenario(
        self,
        scenario: dict,
        account_topic: str = "general",
        voice: str = None,
        style: str = None
    ) -> Optional[Tuple[Path, Optional[Path]]]:
        """
        Senaryo için tam seslendirme oluştur.
        
        Args:
            scenario: Video senaryosu dict'i (scenes, hook, cta)
            account_topic: İçerik konusu (finance, education vb.)
            voice: Gemini ses adı (None ise otomatik seçilir)
            style: Stil prompt'u (None ise otomatik)
        
        Returns:
            (audio_path, srt_path) veya None
        """
        try:
            # 1. Metni birleştir (SADECE SAHNELER - Hook hariç)
            full_text = ""
            for scene in scenario.get("scenes", []):
                full_text += scene.get("narration", "") + " "
            
            full_text = full_text.strip()
            if not full_text:
                self.logger.warning("⚠️ Senaryo metni boş")
                return None, None
            
            # 2. Ses seç
            if not voice:
                voice = self.get_voice_for_content(account_topic)
            
            # 3. Dosya yolları
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"narration_{timestamp}.mp3"
            
            self.logger.info(f"🎙️ Gemini Narration - Voice: {voice}, Topic: {account_topic}")
            self.logger.info(f"   Metin: {full_text[:80]}...")
            
            # 4. TTS üret
            audio_path, srt_path = await self.text_to_speech(
                text=full_text,
                output_file=output_file,
                voice=voice,
                style=style,
                content_type=account_topic
            )
            
            if audio_path:
                self.logger.info(f"✅ Gemini Narration hazır: {audio_path}")
                return audio_path, srt_path
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Gemini Narration hatası: {e}")
            return None, None
    
    @staticmethod
    def list_voices() -> Dict:
        """Mevcut Gemini TTS seslerini listele"""
        return GEMINI_VOICES
    
    @staticmethod
    def list_styles() -> Dict:
        """Mevcut stil prompt'larını listele"""
        return STYLE_PROMPTS


# ===== TEST =====
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test_gemini_tts():
        """Gemini TTS test"""
        print("=" * 60)
        print("GEMINI TTS TEST")
        print("=" * 60)
        
        tts = GeminiTTS()
        
        if not tts.client:
            print("❌ Gemini TTS client not available!")
            print("   Check GEMINI_API_KEY in .env")
            return
        
        # Test 1: Basic English TTS
        print("\n[Test 1] English narration (Finance)")
        result = await tts.text_to_speech(
            text="Three secrets rich people never tell you! Money loves money, and the wealthy always keep their money working.",
            output_file="test_gemini_finance.mp3",
            voice="Puck",
            content_type="finance"
        )
        if result[0]:
            print(f"✅ Success: {result[0]}")
        else:
            print("❌ Failed")
        
        # Test 2: Story narration
        print("\n[Test 2] Story narration")
        result = await tts.text_to_speech(
            text="In the dead of night, a mysterious light appeared over the abandoned lighthouse. No one dared to investigate.",
            output_file="test_gemini_story.mp3",
            voice="Charon",
            content_type="mystery"
        )
        if result[0]:
            print(f"✅ Success: {result[0]}")
        else:
            print("❌ Failed")
        
        # Test 3: Scenario narration
        print("\n[Test 3] Scenario narration")
        test_scenario = {
            "hook": "You won't believe what happens next!",
            "scenes": [
                {"narration": "Every morning, successful people follow a specific routine."},
                {"narration": "First, they wake up before sunrise and meditate for ten minutes."},
                {"narration": "Then, they exercise for at least thirty minutes to boost their energy."},
            ],
            "cta": "Follow for more life-changing tips!"
        }
        result = await tts.create_narration_for_scenario(
            scenario=test_scenario,
            account_topic="motivation",
            voice="Puck"
        )
        if result and result[0]:
            print(f"✅ Success: {result[0]}")
        else:
            print("❌ Failed")
        
        # List voices
        print("\n" + "=" * 60)
        print("AVAILABLE VOICES:")
        for name, info in GEMINI_VOICES.items():
            print(f"  {name}: {info['gender']} - {info['style']} ({', '.join(info['best_for'])})")
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
    
    asyncio.run(test_gemini_tts())
