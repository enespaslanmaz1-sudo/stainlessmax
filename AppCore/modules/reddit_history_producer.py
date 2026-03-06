"""
Reddit History Video Producer
reddithistoriyss hesabı için özel video üretici
- Gameplay videolarından klip çeker (assets/gameplay/)
- İnternetten hikaye bulur
- AI ile kontrol eder
"""
import os
import json
import random
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict
from google import genai
from google.genai import types
import asyncio
logger = logging.getLogger(__name__)

REDDIT_HISTORY_AVAILABLE = True

from .gemini_key_manager import GeminiKeyManager





class RedditHistoryProducer:
    """Reddit History videoları için özel producer"""
    
    def __init__(self, base_dir: Path = None):
        """Initialize producer"""
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        
        import sys, os
        if sys.platform == 'darwin':
            appdata_base = Path(os.path.expanduser('~/Library/Application Support/StainlessMax'))
            self.gameplay_dir = appdata_base / "assets" / "gameplay"
            self.output_dir = Path(os.path.expanduser('~/Movies/StainlessMax'))
            self.history_file = appdata_base / "db" / "reddit_history.json"
        else:
            self.gameplay_dir = self.base_dir / "assets" / "gameplay"
            self.output_dir = self.base_dir / "outputs"
            self.history_file = self.base_dir / "db" / "reddit_history.json"
        
        # Klasörleri oluştur
        self.gameplay_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Gemini AI setup (Key Manager)
        self.model_name = "gemini-2.5-flash"
        self.key_manager = GeminiKeyManager()
        
        logger.info(f"RedditHistoryProducer initialized: {self.gameplay_dir}")
    
    def get_gameplay_videos(self) -> List[Path]:
        """Gameplay klasöründeki videoları getir"""
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv']
        videos = []
        
        if not self.gameplay_dir.exists():
            logger.warning(f"Gameplay directory not found: {self.gameplay_dir}")
            return videos
        
        for ext in video_extensions:
            videos.extend(self.gameplay_dir.glob(f"*{ext}"))
        
        logger.info(f"Found {len(videos)} gameplay videos")
        return videos
    
    def load_history(self) -> Dict:
        """Üretim geçmişini yükle"""
        if not self.history_file.exists():
            return {
                "produced_videos": [], 
                "used_stories": [], 
                "used_story_urls": [],  # Yeni: URL'leri takip et
                "last_production": None
            }
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                # Eski formattan yeni formata geçiş
                if "used_story_urls" not in history:
                    history["used_story_urls"] = []
                return history
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return {
                "produced_videos": [], 
                "used_stories": [], 
                "used_story_urls": [],
                "last_production": None
            }
    
    def save_history(self, history: Dict):
        """Üretim geçmişini kaydet"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            logger.info("History saved successfully")
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    async def find_reddit_story(self) -> Optional[Dict]:
        """İnternetten gerçek Reddit hikayesi bul"""
        try:
            import requests
            
            # Geçmişi yükle (kullanılmış URL'leri kontrol için)
            history = self.load_history()
            used_urls = set(history.get("used_story_urls", []))
            
            # Reddit'in en popüler hikaye subreddit'leri
            subreddits = [
                'tifu',           # Today I F***ed Up
                'confession',     # Confessions
                'relationship_advice',
                'AmItheAsshole',
                'TrueOffMyChest',
                'stories',
                'shortstories',
                'nosleep'         # Korku hikayeleri
            ]
            
            # Rastgele bir subreddit seç
            subreddit = random.choice(subreddits)
            
            # Reddit JSON API kullan (authentication gerektirmez)
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=50"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            logger.info(f"Fetching stories from r/{subreddit}...")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Reddit API error ({response.status_code}): {response.text[:200]}")
                return None
            
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            if not posts:
                logger.warning("No posts found")
                return None
            
            # Uygun hikayeleri filtrele
            suitable_stories = []
            
            for post in posts:
                post_data = post.get('data', {})
                title = post_data.get('title', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('score', 0)
                permalink = post_data.get('permalink', '')
                post_url = f"https://reddit.com{permalink}"
                
                # Daha önce kullanıldı mı kontrol et
                if post_url in used_urls:
                    continue
                
                # Hikaye metni
                story_text = f"{title}\n\n{selftext}".strip()
                
                # Filtreler:
                # 1. En az 100 karakter (çok kısa değil)
                # 2. En fazla 1500 karakter (1 dakikalık okuma ~200-250 kelime ~1000-1500 karakter)
                # 3. En az 10 upvote (kaliteli içerik)
                # 4. Selftext var (sadece başlık değil)
                
                if (len(story_text) >= 100 and 
                    len(story_text) <= 1500 and 
                    score >= 10 and 
                    len(selftext) > 50):
                    
                    suitable_stories.append({
                        'text': story_text,
                        'title': title,
                        'subreddit': subreddit,
                        'score': score,
                        'url': post_url,
                        'source': 'reddit',
                        'timestamp': datetime.now().isoformat()
                    })
            
            if not suitable_stories:
                logger.warning("No suitable stories found")
                return None
            
            # En yüksek score'lu hikayeyi seç
            story = max(suitable_stories, key=lambda x: x['score'])
            
            logger.info(f"Found story from r/{story['subreddit']}: {story['title'][:50]}... (score: {story['score']})")
            
            return story
            
        except Exception as e:
            logger.error(f"Error fetching Reddit story: {e}")
            return None
    
    async def validate_story_with_ai(self, story_dict: Dict) -> bool:
        """Hikayeyi AI ile kontrol et"""
        if not self.key_manager.keys:
            return True  # AI yoksa geç
        
        try:
            story_text = story_dict.get('text', '')
            
            prompt = f"""
            Bu Reddit hikayesi TikTok'ta "Reddit Hikayeleri" konsepti için uygun mu? 
            
            Hikaye: {story_text[:500]}...
            
            Kontrol:
            1. İlgi çekici ve merak uyandırıcı mı?
            2. TikTok topluluk kurallarını ihlal eden AŞIRI cinsellik, nefret söylemi veya vahşet içeriyor mu? (Hafif itiraflar sorun değil)
            3. Ortalama 1 dakikada okunabilir mi?
            
            Eğer hikaye genel olarak uygunsa "EVET", değilse "HAYIR" cevap ver.
            """
            
            import asyncio
            
            async def _api_call(client):
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                )
            
            response = await self.key_manager.execute_with_retry(_api_call)
            
            if not response:
                return True # API failed, default to True
                
            result = response.text.strip().upper()
            
            is_valid = "EVET" in result or "YES" in result
            logger.info(f"Story validation: {is_valid}")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error validating story: {e}")
            return True  # Hata durumunda geç
    
    async def localize_story(self, story_dict: Dict) -> Optional[Dict]:
        """Hikayeyi Türkçe'ye çevir ve Hook oluştur"""
        if not self.key_manager.keys:
            return story_dict # AI yoksa olduğu gibi döndür
            
        try:
            story_text = story_dict.get('text', '')
            title = story_dict.get('title', '')
            
            prompt = f"""
            Refine this Reddit story for a Viral TikTok video (English).
            
            Original Title: {title}
            Original Text: {story_text}
            
            Requirements:
            1. Keep it in **ENGLISH**. clean up any grammar issues but keep the "Reddit" vibe (casual, storytelling).
            2. Generate a **Viral Hook** (intro sentence). It must be catchy (e.g., "I made a huge mistake...", "You won't believe what I found...").
            3. Ensure the text is under 1 minute (approx 150-160 words). Summarize if necessary on the boring parts, keep the juice.
            4. Remove any "Edit:", "Update:" meta text unless it's crucial part of the story flow.
            5. Respond in JSON format: {{ "hook": "...", "text": "..." }}
            """
            
            import asyncio
            
            async def _api_call(client):
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                )
            
            response = await self.key_manager.execute_with_retry(_api_call)
            
            if not response:
                return story_dict # API failed, return original
            
            import json
            result = json.loads(response.text)
            
            # Merge with original
            new_story = story_dict.copy()
            new_story['text'] = result.get('text', story_text)
            new_story['hook'] = result.get('hook', '')
            # Save original for reference
            new_story['original_text'] = story_text
            
            logger.info(f"🇹🇷 Story localized. Hook: {new_story['hook']}")
            return new_story
            
        except Exception as e:
            logger.error(f"Error localizing story: {e}")
            return story_dict # Fallback to original

    def select_gameplay_clip(self) -> Optional[Path]:
        """Rastgele gameplay videosu seç"""
        videos = self.get_gameplay_videos()
        
        if not videos:
            logger.warning("No gameplay videos available")
            return None
        
        selected = random.choice(videos)
        logger.info(f"Selected gameplay: {selected.name}")
        
        return selected
    
    async def create_video(self, progress_callback=None, aspect_ratio="9:16", duration: int = 60) -> Dict:
        """
        Reddit History videosu oluştur
        
        Returns:
            Dict: {
                "success": bool,
                "video_path": str,
                "story": str,
                "gameplay": str
            }
        """
        try:
            if progress_callback:
                progress_callback(10, "Hikaye aranıyor...")
            
            # 1. Hikaye bul ve doğrula (5 deneme)
            story = None
            max_retries = 5
            
            for attempt in range(max_retries):
                if progress_callback:
                    progress_callback(10 + (attempt * 5), f"Hikaye aranıyor ({attempt + 1}/{max_retries})...")
                
                # Hikaye bul
                candidate_story = await self.find_reddit_story()
                if not candidate_story:
                    logger.warning(f"Attempt {attempt + 1}: No story found.")
                    continue
                
                if progress_callback:
                    progress_callback(20 + (attempt * 5), "Hikaye doğrulanıyor...")
                
                # Hikayeyi doğrula
                is_valid = await self.validate_story_with_ai(candidate_story)
                if is_valid:
                    story = candidate_story
                    break
                else:
                    logger.warning(f"Attempt {attempt + 1}: Story validation failed.")
            
            if not story:
                return {"success": False, "error": "5 denemede geçerli hikaye bulunamadı"}
            
            # --- LOCALIZATION START ---
            if progress_callback:
                progress_callback(40, "Refining story & generating hook (English)...")
            
            story = await self.localize_story(story)
            # --- LOCALIZATION END ---
            
            logger.info(f"Story selected: {story['title']}")
            
            if progress_callback:
                progress_callback(50, "Gameplay seçiliyor...")
            
            # 3. Gameplay seç
            gameplay = self.select_gameplay_clip()
            if not gameplay:
                return {"success": False, "error": "Gameplay videosu bulunamadı"}
            
            if progress_callback:
                progress_callback(60, "Seslendirme yapılıyor...")

            # 4. Seslendirme (Gemini Audio)
            if progress_callback:
                progress_callback(60, "Seslendirme yapılıyor (Gemini Audio)...")
            
            # Import GeminiTTS locally
            try:
                from .gemini_tts import GeminiTTS
            except ImportError:
                import sys
                if str(Path(__file__).parent) not in sys.path:
                    sys.path.append(str(Path(__file__).parent))
                from gemini_tts import GeminiTTS
            
            tts = GeminiTTS()
            
            # Timestamp generated locally
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Hook'u metnin başına ekle (Seslendirme için)
            hook_text = story.get("hook", "").strip()
            body_text = story.get("text", "").strip()
            
            # Eğer text zaten hook ile başlıyorsa tekrar ekleme (Basit kontrol)
            if hook_text and not body_text.startswith(hook_text[:10]):
                full_text = f"{hook_text}. {body_text}"
            else:
                full_text = body_text
                
            story_clean_text = full_text.replace("\n", " ").replace("..", ".")
            
            # Gemini Voice Selection (Smart Selector)
            try:
                # Use SmartVoiceSelector from GeminiTTS module
                from .gemini_tts import SmartVoiceSelector
                
                # Check for "Future Lab" account (English)
                is_future_lab = "Future Lab" in story.get("account", "")
                
                if is_future_lab:
                    voice = "Puck" # Future Lab -> English / Tech / Viral
                else:
                    # Reddithistoriyss -> Smart Gender Detection (English)
                    voice = SmartVoiceSelector.select_voice(story_clean_text, content_type="story", language="en")
                    logger.info(f"🧠 Smart Voice Selected: {voice} (Gender detected)")
            except Exception as e:
                logger.error(f"Smart Voice Error: {e}")
                voice = "Charon" # Fallback
            
            # Wrapper for KeyManager
            async def _generate_audio(client):
                return await tts.text_to_speech(
                    text=story_clean_text,
                    output_file=f"reddit_{timestamp}.mp3",
                    voice=voice,
                    content_type="mystery", # Sets the style
                    client=client # Pass rotated client
                )
            
            # Execute with retry logic
            audio_path, srt_path = await self.key_manager.execute_with_retry(_generate_audio)
            
            if not audio_path:
                 return {"success": False, "error": "Seslendirme oluşturulamadı (Gemini Audio)"}

            if progress_callback:
                progress_callback(80, "Video birleştiriliyor...")

            # 5. Video Birleştirme (VideoAssembler)
            try:
                from .video_assembler import VideoAssembler
            except ImportError:
                # If sys.path was not modified yet (if TTS succeeded via relative import)
                import sys
                if str(Path(__file__).parent) not in sys.path:
                    sys.path.append(str(Path(__file__).parent))
                from video_assembler import VideoAssembler
                
            assembler = VideoAssembler()
            
            # Scenario dict for assembler
            scenario = {
                "total_duration": duration, # Tahmini
                "hook": story.get("hook", ""), # Hook eklendi
                "scenes": [
                    {
                        "start": 0,
                        "duration": duration, # Ses dosyası belirleyecek
                        "text": story["text"]
                    }
                ]
            }
            
            # Timestamp generated locally to avoid re-defining if it was missing or moved
            # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # Already defined above
            video_filename = f"reddit_{timestamp}.mp4"
            
            final_video_path = assembler.assemble_video(
                clips=[gameplay],
                audio_path=audio_path,
                scenario=scenario,
                output_filename=video_filename,
                add_subtitles=True, # Subtitles enabled for English
                external_srt_path=srt_path,
                logo_path=Path("redditlogo.png") if Path("redditlogo.png").exists() else None,
                topic=story.get('subreddit', ''),
                aspect_ratio=aspect_ratio,
                duration=duration
            )
            
            if not final_video_path:
                return {"success": False, "error": "Video birleştirilemedi"}
            
            result = {
                "success": True,
                "video_path": str(final_video_path),
                "story": story["text"],
                "story_title": story.get("title", ""),
                "story_url": story.get("url", ""),
                "subreddit": story.get("subreddit", ""),
                "score": story.get("score", 0),
                "gameplay": str(gameplay),
                "account": "reddithistoriyss",
                "platform": "tiktok",
                "timestamp": datetime.now().isoformat()
            }
            
            # 6. Geçmişe kaydet
            history = self.load_history()
            history["produced_videos"].append(result)
            # URL'yi kaydet (aynı hikaye tekrar kullanılmasın)
            if "used_story_urls" not in history:
                history["used_story_urls"] = []
            history["used_story_urls"].append(story.get("url", ""))
            history["used_stories"].append(story["text"][:100])
            history["last_production"] = datetime.now().isoformat()
            self.save_history(history)
            
            if progress_callback:
                progress_callback(100, "Tamamlandı!")
            
            logger.info(f"✅ Reddit History video created successfully: {final_video_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating video: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def get_stats(self) -> Dict:
        """İstatistikleri getir"""
        gameplay_videos = self.get_gameplay_videos()
        history = self.load_history()
        
        return {
            "account": "reddithistoriyss",
            "platform": "tiktok",
            "gameplay_videos": len(gameplay_videos),
            "produced_videos": len(history.get("produced_videos", [])),
            "last_production": history.get("last_production"),
            "gameplay_dir": str(self.gameplay_dir)
        }


# Test
if __name__ == "__main__":
    import asyncio
    import os
    try:
        from dotenv import load_dotenv
        # Load environment variables from project root
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded .env from {env_path}")
        else:
            print(f"Warning: .env not found at {env_path}")
    except ImportError:
        print("python-dotenv not installed, skipping .env load")
    
    logging.basicConfig(level=logging.INFO)
    
    producer = RedditHistoryProducer()
    
    print("=" * 60)
    print("Reddit History Producer - Test")
    print("=" * 60)
    
    # İstatistikler
    stats = producer.get_stats()
    print(f"\n📊 İstatistikler:")
    print(f"  Hesap: {stats['account']}")
    print(f"  Platform: {stats['platform']}")
    print(f"  Gameplay Videos: {stats['gameplay_videos']}")
    print(f"  Üretilen: {stats['produced_videos']}")
    print(f"  Klasör: {stats['gameplay_dir']}")
    
    # Test video oluştur
    print("\n🎬 Test video oluşturuluyor...")
    
    async def test():
        with open("producer_debug.log", "w", encoding="utf-8") as debug_file:
            debug_file.write("Starting test...\n")
            try:
                result = await producer.create_video()
                debug_file.write(f"Result keys: {list(result.keys())}\n")
                if result.get("success"):
                    print(f"\n✅ Başarılı!")
                    print(f"  Hikaye: {result['story'][:100]}...")
                    print(f"  Gameplay: {result['gameplay']}")
                    debug_file.write(f"SUCCESS: {result['video_path']}\n")
                else:
                    print(f"\n❌ Hata: {result.get('error')}")
                    debug_file.write(f"FAILURE: {result.get('error')}\n")
            except Exception as e:
                import traceback
                traceback.print_exc()
                debug_file.write(f"EXCEPTION: {e}\n")
    
    asyncio.run(test())
    
    print("\n" + "=" * 60)
