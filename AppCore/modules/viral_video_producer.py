"""
Viral Video Producer - Tüm sistemin orkestrasyonu
Gemini + TTS + Pexels + FFmpeg ile tam otomatik viral video üretimi
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, List
import json
from datetime import datetime
import time

# Modüller
# Projenin kök dizinini dinamik olarak bulur (System/modules/.. -> System/.. -> root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

from .scenario_generator import ScenarioGenerator
from .multi_stock_fetcher import MultiStockFetcher
from .tts_generator import TTSGenerator
from .video_assembler import VideoAssembler
from .affiliate_manager import AffiliateManager


import os
from .gemini_key_manager import GeminiKeyManager

class ViralVideoProducer:
    """60 saniyelik viral videolar üreten ana sistem"""
    
    def __init__(self, oauth_client=None):
        self.logger = logging.getLogger(__name__)
        
        # Modüller
        self.scenario_gen = ScenarioGenerator(oauth_client=oauth_client)
        self.content_fetcher = MultiStockFetcher()
        
        # TTS Generator'ı GeminiTTS ile değiştir (KeyManager destekli)
        from .gemini_tts import GeminiTTS
        self.tts_gen = GeminiTTS()
        
        self.video_assembler = VideoAssembler()
        self.affiliate_mgr = AffiliateManager()
        
        # Key Manager (Gemini API Rotation)
        self.key_manager = GeminiKeyManager()
        
        # Output dizinleri
        # Output dizinleri - STRICT PROJECT STRUCTURE
        # System/modules/.. -> System/outputs
        self.output_dir = BASE_DIR / "System_Data" / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"ViralVideoProducer initialized. Output dir: {self.output_dir}")

    def _optimize_scene_query(self, base_query: str, niche: str, account_topic: str, scene_narration: str) -> str:
        """Sahne arama sorgusunu nişe göre optimize et."""
        fallback_query = "cinematic abstract background"
        cleaned_base = (base_query or "").strip()

        if niche != "finance":
            return cleaned_base or fallback_query

        finance_signals = (
            "finance", "money", "investment", "invest", "wealth", "stock",
            "market", "trading", "budget", "economy", "cash", "bank", "business"
        )

        base_lower = cleaned_base.lower()
        if any(signal in base_lower for signal in finance_signals):
            return cleaned_base

        context_text = f"{scene_narration or ''} {account_topic or ''}".lower()

        if any(signal in context_text for signal in finance_signals):
            finance_boost = "finance money investment stock market wealth business"
        else:
            finance_boost = "finance money investment"

        if cleaned_base:
            return f"{cleaned_base} {finance_boost}".strip()

        return finance_boost
    
    async def create_viral_video(
        self,
        account_id: str,
        account_topic: str,
        niche: str = "finance",
        platform: str = "tiktok",
        progress_callback = None,
        aspect_ratio: str = "9:16",
        duration: int = 60
    ) -> Optional[Dict]:
        """
        Tam otomatik viral video üret
        """
        try:
            self.logger.info(f"🎬 Viral video üretimi başladı. Hesap: {account_id}, Konu: {account_topic}")
            if progress_callback: progress_callback(5, "Hesap Analiz Ediliyor...")
            
            # Account Manager kullanarak hesap bilgilerini al
            from .account_manager import AccountManager
            acc_mgr = AccountManager()
            account = acc_mgr.get_account(account_id)
            
            if not account:
                self.logger.warning(f"Hesap ID ile bulunamadı: {account_id}, isim ile aranıyor...")
                # Fallback: Hesap ismini kullanarak ara
                all_accounts = acc_mgr.get_active_accounts()
                for acc in all_accounts:
                    # ID veya name ile eşleşme kontrolü (Null-safety: ensure name/id is not None)
                    acc_name = getattr(acc, "name", "") or ""
                    acc_id_val = getattr(acc, "id", "") or ""
                    
                    if acc_name.lower() == str(account_id).lower() or acc_id_val.lower() == str(account_id).lower():
                        account = acc
                        self.logger.info(f"✅ Hesap isim ile bulundu: {acc_name} (ID: {acc_id_val})")
                        break
                
                if not account:
                    self.logger.error(f"Hesap bulunamadı: {account_id}")
                    # Fallback: Parametreleri kullan
                    final_niche = niche
                else:
                    final_niche = account.niche if account.niche else niche
            else:
                final_niche = account.niche if account.niche else niche
            
            # --- ACCOUNT CONFIGURATION & OPTIMIZATION ---
            # Default settings
            target_language = "en"
            add_subtitles = True
            is_future_lab = False
            
            if account:
                # Use account specific language if set
                if hasattr(account, 'language') and account.language:
                    target_language = account.language
                # if hasattr(account, 'language') and account.language: # Moved below
                #     target_language = account.language
                
                # Account niche/topic logic
                final_niche = account.niche if account.niche else niche
                
                # Subtitle logic (Check if account prefers no subtitles, e.g. Future Lab style)
                # We can use a property or a keyword in the name/id for legacy support
                account_name = getattr(account, "name", "") or ""

            # --- PLATFORM DEFAULTS ---
            if aspect_ratio == "9:16" and platform == "youtube":
                aspect_ratio = "9:16"  # Preserved logic if necessary
            elif not aspect_ratio:
                aspect_ratio = "9:16" if platform == "tiktok" else "16:9"
            
            # --- FUTURE LAB OPTIMIZATION ---
            is_future_lab = "Future Lab" in account_id or "Future Lab" in (account_topic or "")
            
            # Dil ve Altyazı Ayarları
            target_language = "en"  # Üretim tamamen İngilizce olmalı
            add_subtitles = False if is_future_lab else True   # Future Lab temiz (altyazısız)
            
            self.logger.info(f"🌍 Production Language: {target_language.upper()}")
            # -------------------------------
            
            # KANAL KİMLİĞİ (Channel Persona)
            # account.name değerini kullan (Örn: "The Power of Money")
            channel_name = account_name if account_name else account_id
            self.logger.info(f"🎭 Kanal Kimliği Aktif: {channel_name} (ID: {account_id})")
                
            # Konu boşsa otomatik üret (AUTO TOPIC)
            if not account_topic:
                self.logger.info(f"🧠 Konu belirtilmemiş, '{final_niche}' ({channel_name}) için otomatik konu üretiliyor...")
                account_topic = self.scenario_gen.generate_viral_topic(final_niche, account_name=channel_name)
                self.logger.info(f"✨ Belirlenen Konu: {account_topic}")

            # Define defaults
            # duration = 60 # Now controlled via function parameter
            # aspect_ratio parameter used instead of hardcoded default
            
            # 1. Senaryo Oluştur (Gemini 2.5 Pro)
            self.logger.info(f"📝 [1/4] Senaryo oluşturuluyor ({duration}s, {aspect_ratio})...")
            
            async def _generate_scenario_safe(client):
                 return self.scenario_gen.generate_viral_scenario(
                    topic=account_topic,
                    niche=final_niche,
                    duration=duration, # DYNAMIC DURATION
                    platform=platform,
                    language=target_language, 
                    channel_name=channel_name,
                    client=client
                )
            
            # Key manager ile retry mekanizması
            scenario = await self.key_manager.execute_with_retry(_generate_scenario_safe)
            
            if not scenario:
                self.logger.error("Senaryo oluşturulamadı")
                return None
            
            self.logger.info(f"✅ Senaryo hazır: {scenario.get('hook', '')[:50]}...")
            
            # DEBUG: Scenario yapısını logla
            self.logger.info(f"📋 Scenario İçeriği:")
            self.logger.info(f"  - Hook: {scenario.get('hook', 'YOK')}")
            self.logger.info(f"  - Sahne Sayısı: {len(scenario.get('scenes', []))}")
            for i, scene in enumerate(scenario.get('scenes', [])[:3], 1):  # İlk 3 sahne
                self.logger.info(f"  - Sahne {i}: {scene.get('narration', scene.get('description', 'BOŞ'))[:50]}...")
            if progress_callback: progress_callback(25, "Klipler İndiriliyor...")
            
            # --- MÜZİK HAZIRLIĞI ---
            from AppCore.modules.asset_downloader import AssetDownloader
            downloader = AssetDownloader()
            
            # Use os.getenv as GeminiKeyManager doesn't have get_key
            import os
            pixabay_key = os.getenv("PIXABAY_API_KEY")
            
            # Fallback to key_manager if we ever add get_key there (not currently present)
            if not pixabay_key and hasattr(self.key_manager, 'get_key'):
                pixabay_key = self.key_manager.get_key("PIXABAY_API_KEY")
            music_kw = scenario.get("music_keywords", account_topic)
            music_path = None
            
            if pixabay_key:
                self.logger.info(f"🎵 Pixabay Music: '{music_kw}' aranıyor...")
                music_path = downloader.download_pixabay_music(pixabay_key, music_kw)
            
            if not music_path:
                self.logger.info("🎶 Varsayılan müziklerden seçimi yapılıyor...")
                music_path = self.video_assembler._get_music_for_topic(account_topic)
            # -----------------------
            
            # 2. Klipleri İndir (Pexels + Pixabay + Gemini Validation)
            self.logger.info("🎥 [2/4] Video klipleri indiriliyor (Multi-Source + AI Validation)...")
            scene_clips = {}
            
            # Determine orientation from aspect ratio
            orientation = "landscape" if aspect_ratio == "16:9" else "portrait"
            
            scenes = scenario.get("scenes", [])
            for i, scene in enumerate(scenes):
                visual_prompt = scene.get("visual_prompt", "")
                keywords = scene.get("visual_keywords", [])
                scene_duration = scene.get("duration", 10)
                narration = scene.get("narration", "")
                
                # Search query: visual_prompt veya keywords
                if visual_prompt:
                    raw_search_query = visual_prompt
                elif keywords:
                    raw_search_query = " ".join(keywords[:3]) if isinstance(keywords, list) else keywords
                else:
                    raw_search_query = "cinematic abstract background"

                search_query = self._optimize_scene_query(
                    base_query=raw_search_query,
                    niche=final_niche,
                    account_topic=account_topic,
                    scene_narration=narration
                )
                
                self.logger.info(f"Sahne {i+1}: '{search_query}' aranıyor ({orientation})...")
                
                # Multi-source search with Gemini validation
                best_video = self.content_fetcher.search_and_validate(
                    query=search_query,
                    script_text=narration,
                    theme=final_niche,
                    orientation=orientation, # DYNAMIC ORIENTATION
                    min_duration=max(5, scene_duration - 5),
                    max_duration=scene_duration + 10
                )
                
                if best_video:
                    # Download the validated video
                    filename = f"scene_{i+1}_clip_1.mp4"
                    clip_path = self.content_fetcher.download_video(best_video, filename)
                    
                    if clip_path:
                        scene_clips[i] = [clip_path]
                        self.logger.info(f"✅ Sahne {i+1}: {best_video['source']} (skor: {best_video.get('validation_score', 0)})")
                    else:
                        self.logger.warning(f"⚠️ Sahne {i+1}: İndirme başarısız")
                else:
                    self.logger.warning(f"⚠️ Sahne {i+1}: Uygun video bulunamadı")
                
                # Rate limiting
                time.sleep(0.5)
            
            if not scene_clips:
                self.logger.warning("Klip bulunamadı, stok video kullanılacak")
            
            if progress_callback: progress_callback(50, "Seslendirme Yapılıyor...")
            
            # 3. Seslendirme (Gemini Audio + Key Rotation)
            self.logger.info("🎙️ [3/4] Seslendirme oluşturuluyor (Gemini Audio)...")
            
            # Ses seçimi
            if is_future_lab:
                voice = "Puck" if final_niche == "finance" or final_niche == "viral" else "Fenrir"
            else:
                # Diğer kanallar için
                from .gemini_tts import SmartVoiceSelector
                # Tüm metni birleştirip analiz edelim
                full_text = " ".join([s.get("narration", "") for s in scenario.get("scenes", [])])
                voice = SmartVoiceSelector.select_voice(full_text, content_type=final_niche, language=target_language)
            
            self.logger.info(f"🗣️ Seçilen Ses: {voice}")

            async def _generate_narration_safe(client):
                 full_text = ""
                 for scene in scenario.get("scenes", []):
                     full_text += scene.get("narration", "") + " "
                 full_text = full_text.strip()
                 
                 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                 return await self.tts_gen.text_to_speech(
                     text=full_text,
                     output_file=f"narration_{timestamp}.mp3",
                     voice=voice,
                     content_type=final_niche,
                     client=client
                 )
            
            audio_path, srt_path = await self.key_manager.execute_with_retry(_generate_narration_safe)
            
            if not audio_path:
                self.logger.error("Seslendirme oluşturulamadı (Gemini)")
                return None
            
            self.logger.info(f"✅ Ses hazır: {audio_path}")
            if progress_callback: progress_callback(75, "Video Birleştiriliyor...")
            
            # 4. Video Üret (FFmpeg)
            self.logger.info("⚙️ [4/4] Video birleştiriliyor...")
            
            # Klipleri list olarak hazırla
            clip_paths = []
            for scene_idx in sorted(scene_clips.keys()):
                if scene_clips[scene_idx]:
                    clip_paths.append(scene_clips[scene_idx][0])  # İlk klip
            
            if not clip_paths:
                self.logger.warning("Klip yok, sadece audio kullanılacak")
                # Klip yoksa placeholder video oluştur (siyah ekran)
                clip_paths = None
            
            # Video birleştir
            import re
            def sanitize_filename(name):
                # Remove invalid chars, keep spaces as is or replace with single space
                name = re.sub(r'[\\/*?:"<>|]', "", name)
                name = re.sub(r'\s+', " ", name).strip()
                return name

            sanitized_topic = sanitize_filename(account_topic)
            if not sanitized_topic:
                 sanitized_topic = f"video_{account_id}" # Fallback
            
            # User request: "bilgisayar _ sayı vs. kullanılmasın" -> Just the topic
            video_filename = f"{sanitized_topic}.mp4"
            
            if clip_paths:
                final_video = self.video_assembler.assemble_video(
                    clips=clip_paths,
                    audio_path=audio_path,
                    scenario=scenario,
                    output_filename=video_filename,
                    add_subtitles=add_subtitles,
                    external_srt_path=srt_path,
                    topic=account_topic,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                    music_path_override=music_path # PASS MUSIC
                )
            else:
                # Klip yoksa sadece audio'dan video oluştur
                final_video = None
                self.logger.warning("Klip bulunamadı, video oluşturulamadı")
            
            if final_video:
                self.logger.info(f"✅ VIDEO HAZIR: {final_video}")
            
            
            video_info = {
                "account_id": account_id,
                "account_topic": account_topic,
                "scenario": scenario,
                "audio_path": str(audio_path),
                "video_path": str(final_video) if final_video else None,
                "clips": {k: [str(p) for p in v] for k, v in scene_clips.items()},
                "status": "ready" if final_video else "audio_only",
                "created_at": datetime.now().isoformat(),
                "duration": scenario.get("total_duration", 60)
            }
            
            # JSON olarak kaydet
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"{account_id}_{timestamp}_info.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(video_info, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ Video bilgileri kaydedildi: {output_file}")
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"Video üretim hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    
    def create_viral_video_sync(self, **kwargs) -> Optional[Dict]:
        """Senkron wrapper"""
        # kwargs içinde progress_callback olabilir
        return asyncio.run(self.create_viral_video(**kwargs))
    
    async def create_and_upload_viral_video(
        self,
        account_id: str,
        account_topic: str,
        niche: str = "finance",
        platform: str = "tiktok",
        auto_upload: bool = True
    ) -> Optional[Dict]:
        """
        Viral video üret VE otomatik upload yap
        
        Args:
            account_id: Hesap ID
            account_topic: Hesap konusu
            niche: Kategori
            platform: Platform
            auto_upload: Otomatik yükleme yapılsın mı?
            
        Returns:
            Dict: Video info + upload sonucu
        """
        try:
            # 1. Video üret
            video_info = await self.create_viral_video(
                account_id=account_id,
                account_topic=account_topic,
                niche=niche,
                platform=platform
            )
            
            if not video_info:
                self.logger.error("Video üretilemedi, upload yapılmayacak")
                return None
            
            # 2. Video oluştu mu kontrol et
            if not video_info.get("video_path"):
                self.logger.warning("Video path yok, sadece audio - upload atlanıyor")
                return video_info
            
            # 3. Auto upload
            if not auto_upload:
                self.logger.info("Auto upload kapalı, manuel upload bekleniyor")
                return video_info
            
            self.logger.info("🚀 Otomatik upload başlıyor...")
                
            # UnifiedUploader'ı import et
            from .unified_uploader import UnifiedUploader
            from pathlib import Path
            
            uploader = UnifiedUploader()
            
            # Video bilgilerini hazırla
            video_path = Path(video_info["video_path"])
            scenario = video_info["scenario"]
            
            # Title ve description
            title = scenario.get("title", scenario.get("hook", account_topic))[:100]
            
            # Description oluştur (Gemini'den geleni kullan veya oluştur)
            if "description" in scenario and scenario["description"]:
                 description = scenario["description"]
            else:
                description_parts = []
                if "scenes" in scenario:
                    for i, scene in enumerate(scenario["scenes"][:3], 1):
                        description_parts.append(f"{i}. {scene.get('narration', '')[:100]}")
                description = "\n\n".join(description_parts)
            
            # CTA ekle (mevcut varsa)
            if scenario.get("cta"):
                description += f"\n\n{scenario['cta']}"
            
            # Hashtags
            tags = ["#shorts", "#viral", f"#{niche}", f"#{platform}"]
            if "tags" in scenario:
                 tags.extend(scenario["tags"])
            elif "viral_elements" in scenario:
                tags.extend(scenario["viral_elements"][:5])
            
            # AFFILIATE LINK ENTEGRASYONU
            # Konuya uygun affiliate link seç
            affiliate_link = self.affiliate_mgr.get_best_link_for_topic(
                account_id=account_id,
                topic=account_topic,
                niche=niche
            )
            
            if affiliate_link:
                # CTA üret
                cta = self.affiliate_mgr.generate_cta(affiliate_link, style="casual")
                description += f"\n\n{cta}"
                
                self.logger.info(f"✅ Affiliate link eklendi: {affiliate_link['url']}")
                
                # Track için kaydet
                video_info["affiliate_link"] = affiliate_link["url"]
                video_info["affiliate_cta"] = cta   
            
            # Upload!
            upload_result = uploader.upload_to_account(
                account_id=account_id,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags
            )
            
            # Sonuç
            if upload_result.get("success"):
                self.logger.info(f"✅ VIDEO YÜKLENDI: {upload_result.get('video_url', 'OK')}")
                
                video_info["upload_status"] = "success"
                video_info["upload_result"] = upload_result
                
                # JSON güncelle
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = self.output_dir / f"{account_id}_{timestamp}_complete.json"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)
                
            else:
                self.logger.error(f"❌ Upload başarısız: {upload_result.get('error')}")
                video_info["upload_status"] = "failed"
                video_info["upload_error"] = upload_result.get("error")
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"Create & upload hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def create_and_upload_sync(self, **kwargs) -> Optional[Dict]:
        """Senkron wrapper"""
        return asyncio.run(self.create_and_upload_viral_video(**kwargs))


# Test
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test_producer():
        """Producer test"""
        
        print("\n" + "="*60)
        print("VİRAL VIDEO PRODUCER TEST")
        print("="*60)
        
        producer = ViralVideoProducer()
        
        # Test: TikTok için "Paranın gücü" videosu
        print("\n🎬 Video üretiliyor...")
        print("Konu: Paranın gücü")
        print("Platform: TikTok")
        print("Süre: 60 saniye")
        
        result = await producer.create_viral_video(
            account_id="tiktok_main",
            account_topic="Paranın gücü - Zengin insanların sırları",
            niche="finance",
            platform="tiktok"
        )
        
        if result:
            print("\n" + "="*60)
            print("✅ VİDEO ÜRETİMİ BAŞARILI!")
            print("="*60)
            
            print(f"\nHesap: {result['account_id']}")
            print(f"Konu: {result['account_topic']}")
            
            scenario = result['scenario']
            print(f"\nHook: {scenario.get('hook')}")
            print(f"Toplam süre: {scenario.get('total_duration')}s")
            print(f"Sahne sayısı: {len(scenario.get('scenes', []))}")
            
            print(f"\nSes dosyası: {result['audio_path']}")
            print(f"İndirilen klip sayısı: {sum(len(v) for v in result['clips'].values())}")
            
            print("\n💡 Sonraki adım: FFmpeg ile video birleştirme")
            
        else:
            print("\n❌ Video üretimi başarısız!")
    
    # Test çalıştır
    asyncio.run(test_producer())
