import logging
from pathlib import Path
from typing import List, Dict, Optional, TYPE_CHECKING

# Type hints için import (runtime'da yüklenmez, sadece type checking için)
if TYPE_CHECKING:
    from moviepy.editor import TextClip, VideoClip

logger = logging.getLogger(__name__)


class WhisperCaptioner:
    """
    OpenAI Whisper ile kelime bazlı altyazı üretici
    
    Features:
    - Kelime kelime timestamp çıkarma
    - Karaoke efekti (sarı highlight + zoom)
    - Otomatik emoji ekleme
    - Hormozi tarzı dinamik altyazılar
    """
    
    def __init__(self, model_size: str = 'base'):
        """
        Args:
            model_size: 'tiny', 'base', 'small', 'medium', 'large'
                - tiny: En hızlı, düşük doğruluk (~1GB RAM)
                - base: Hızlı ve yeterince doğru (~1GB RAM) [ÖNERİLEN]
                - small: Dengeli (~2GB RAM)
                - medium: Yüksek doğruluk (~5GB RAM)
                - large: En iyi doğruluk (~10GB RAM)
        """
        self.logger = logger
        self.model_size = model_size
        self.model = None # Lazy load
        
        # Lazy load libraries
        try:
            global whisper, torch
            import whisper
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.logger.info(f"🖥️ Device: {self.device.upper()}")
        except ImportError as e:
            self.device = "cpu"
            self.logger.warning(f"PyTorch veya Whisper yok, CPU fallback (Error: {e})")
            
    def load_model(self):
        """Modeli yükle (kullanılacağı zaman çağrılır)"""
        if self.model:
            return

        try:
            import whisper
            self.logger.info(f"Whisper model yükleniyor: {self.model_size} ({self.device})...")
            self.model = whisper.load_model(self.model_size, device=self.device)
            self.logger.info(f"✅ Whisper {self.model_size} model yüklendi ({self.device})")
        except Exception as e:
            self.logger.error(f"Whisper model yükleme hatası: {e}")
            raise
        
        # Emoji mapping (Türkçe kelimeler)
        self.emoji_map = {
            # Para & Zenginlik
            'para': '💰', 'dolar': '💵', 'euro': '💶', 'zengin': '💎', 'zenginlik': '💎',
            'milyoner': '🤑', 'milyar': '💰', 'servet': '💰', 'yatırım': '📈',
            
            # Başarı & Motivasyon
            'başarı': '🏆', 'kazanmak': '🏆', 'hedef': '🎯', 'başarmak': '✨',
            'inanılmaz': '🤯', 'şok': '😱', 'harika': '⭐', 'mükemmel': '💯',
            
            # Dikkat & Uyarı
            'dikkat': '⚠️', 'tehlike': '⚠️', 'önemli': '❗', 'acil': '🚨',
            
            # Şehir & Yaşam
            'ev': '🏠', 'araba': '🚗', 'ferrari': '🏎️', 'uçak': '✈️',
            'seyahat': '✈️', 'tatil': '🏖️', 'dünya': '🌍',
            
            # Sağlık & Fitness
            'sağlık': '💪', 'fitness': '🏋️', 'kilo': '⚖️', 'diyet': '🥗',
            'spor': '⚽', 'kas': '💪', 'fit': '💪',
            
            # Duygular
            'mutlu': '😊', 'üzgün': '😢', 'kızgın': '😠', 'aşk': '❤️',
            'sevgi': '💕', 'korku': '😨', 'şaşkın': '😲',
            
            # Eğitim & Bilgi
            'kitap': '📚', 'okul': '🎓', 'öğren': '📖', 'bilgi': '💡',
            'fikir': '💡', 'akıl': '🧠', 'zeka': '🧠',
            
            # Teknoloji
            'telefon': '📱', 'bilgisayar': '💻', 'internet': '🌐',
            'video': '🎥', 'kamera': '📸',
            
            # Sayılar & Simgeler
            '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣', '5': '5️⃣',
            'birinci': '🥇', 'ikinci': '🥈', 'üçüncü': '🥉',
            
            # Diğer
            'ateş': '🔥', 'yıldız': '⭐', 'güneş': '☀️', 'ay': '🌙',
            'kalp': '❤️', 'göz': '👁️', 'el': '✋', 'ok': '➡️'
        }
    
    def transcribe_with_timestamps(self, audio_path: str, language: str = 'tr') -> List[Dict]:
        """
        Sesli içeriği kelime kelime timestamp'leriyle çevir
        
        Args:
            audio_path: Audio dosya yolu
            language: Dil kodu ('tr', 'en')
        
        Returns:
            [
                {'word': 'Zengin', 'start': 0.12, 'end': 0.58},
                {'word': 'insanların', 'start': 0.60, 'end': 1.05},
                ...
            ]
        """
        try:
            self.logger.info(f"Transcribing: {audio_path}")
            
            # CPU kullanıyorsa fp16=False yapılmalı (ÇOK ÖNEMLİ!)
            fp16_enabled = (self.device == "cuda")
            
            if not fp16_enabled:
                self.logger.info("⚠️ CPU kullanılıyor, fp16 devre dışı")
            
            # Load model if not loaded
            if not self.model:
                self.load_model()
            
            # Whisper transcribe (word timestamps ile)
            result = self.model.transcribe(
                str(audio_path),
                language=language,
                word_timestamps=True,  # Kelime bazlı timing (ZORUNLU!)
                fp16=fp16_enabled,  # CPU için False, GPU için True
                verbose=False
            )
            
            # Kelime listesi oluştur
            words = []
            for segment in result.get('segments', []):
                for word_data in segment.get('words', []):
                    words.append({
                        'word': word_data['word'].strip(),
                        'start': word_data['start'],
                        'end': word_data['end']
                    })
            
            self.logger.info(f"✅ {len(words)} kelime çevrildi")
            return words
            
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            return []
    
    def add_emojis(self, words: List[Dict]) -> List[Dict]:
        """
        Kelimelere otomatik emoji ekle
        
        Args:
            words: Kelime listesi
        
        Returns:
            Emoji'li kelime listesi
        """
        enriched_words = []
        
        for word_data in words:
            word = word_data['word'].lower().strip('.,!?')
            
            # Emoji varsa ekle
            if word in self.emoji_map:
                word_data['emoji'] = self.emoji_map[word]
                self.logger.debug(f"Emoji added: {word} → {self.emoji_map[word]}")
            
            enriched_words.append(word_data)
        
        return enriched_words
    
    def create_karaoke_clips(
        self,
        words: List[Dict],
        video_size: tuple = (1080, 1920),
        font: str = 'Impact',
        fontsize: int = 70
    ) -> List["TextClip"]:
        """
        Hormozi tarzı karaoke altyazı klipleri oluştur
        ...
        """
        text_clips = []
        
        # ... (rest of method)

    def add_captions_to_video(
        self,
        video_clip: "VideoClip",
        audio_path: str,
        language: str = 'tr'
    ) -> "VideoClip":
        """
        Video'ya Whisper altyazıları ekle (tek fonksiyon)
        ...
        """
        """
        Video'ya Whisper altyazıları ekle (tek fonksiyon)
        
        Args:
            video_clip: Ana video clip
            audio_path: Ses dosyası yolu
            language: Dil
        
        Returns:
            Altyazılı video clip
        """
        try:
            # 1. Transcribe (kelime timestamps)
            self.logger.info("Step 1: Transcribing audio...")
            words = self.transcribe_with_timestamps(audio_path, language)
            
            if not words:
                self.logger.warning("Kelime bulunamadı, altyazısız devam ediliyor")
                return video_clip
            
            # 2. Emoji ekle
            self.logger.info("Step 2: Adding emojis...")
            words_with_emoji = self.add_emojis(words)
            
            # 3. Karaoke klipleri oluştur
            self.logger.info("Step 3: Creating karaoke clips...")
            video_size = video_clip.size
            text_clips = self.create_karaoke_clips(
                words_with_emoji,
                video_size=video_size
            )
            
            # 4. Video ile birleştir
            self.logger.info("Step 4: Compositing...")
            from moviepy.editor import CompositeVideoClip
            final_video = CompositeVideoClip([video_clip] + text_clips)
            
            self.logger.info("✅ Altyazılar eklendi!")
            return final_video
            
        except Exception as e:
            self.logger.error(f"Caption ekleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return video_clip  # Hata olursa orijinal video döndür


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("WHISPER CAPTIONER TEST")
    print("="*60)
    
    try:
        # Model yükle
        print("\n[1] Whisper model yükleniyor...")
        captioner = WhisperCaptioner(model_size='base')
        print("✅ Model yüklendi")
        
        # Test: Emoji mapping
        print("\n[2] Emoji mapping test...")
        test_words = [
            {'word': 'Para', 'start': 0.0, 'end': 0.5},
            {'word': 'kazanmanın', 'start': 0.5, 'end': 1.0},
            {'word': '3', 'start': 1.0, 'end': 1.2},
            {'word': 'sırrı', 'start': 1.2, 'end': 1.5}
        ]
        
        enriched = captioner.add_emojis(test_words)
        for w in enriched:
            emoji = w.get('emoji', '')
            print(f"  {w['word']} {emoji if emoji else ''}")
        
        print("\n✅ Whisper Captioner hazır!")
        print("\nKullanım:")
        print("  captioner = WhisperCaptioner()")
        print("  video_with_captions = captioner.add_captions_to_video(video, audio_path)")
        
    except Exception as e:
        print(f"\n❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()
