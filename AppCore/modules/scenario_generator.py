"""
Scenario Generator - Gemini 2.5 Pro ile Viral İçerik Senaryoları
"""

from google import genai
from google.genai import types
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
import logging

# KANAL KİMLİKLERİ (Global Config) - Çift kopya olmaması için import edilebilir ama şimdilik duplicate ediyoruz
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
    },
    "Reddit History": {
        "visual_keywords": "historical map, ancient ruins, black and white photo, vintage, war footage, museum, artifact, 4k",
        "script_tone": "Intriguing, storytelling, fast-paced, 'Did you know' style. Focus on weird and fascinating historical facts.",
    }
}


class ScenarioGenerator:
    """Gemini 2.5 Pro ile viral video senaryoları oluştur"""
    
    def __init__(self, api_key: Optional[str] = None, oauth_client=None):
        """
        Args:
            api_key: Gemini API key (None ise .env'den alır)
            oauth_client: GeminiOAuth istemcisi (varsa API key yerine kullanılır)
        """
        self.logger = logging.getLogger(__name__)
        self.oauth_client = oauth_client
        self.model_name = "gemini-2.5-flash"
        
        # Eğer OAuth varsa API key gerekmez
        if self.oauth_client:
            self.logger.info("ScenarioGenerator: OAuth istemcisi kullanılıyor")
            self.api_key = None
            self.client = None
        else:
            # API key
            self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            
            if not self.api_key:
                self.logger.warning("GEMINI_API_KEY bulunamadı! (OAuth da yok)")
                self.client = None
            else:
                # Gemini Client (new SDK)
                self.client = genai.Client(api_key=self.api_key)
                self.logger.info(f"ScenarioGenerator: Gemini client ready ({self.model_name})")
    
    def generate_viral_scenario(
        self,
        topic: str,
        niche: str = "general",
        duration: int = 60,
        platform: str = "tiktok",
        language: str = "tr",
        viral_patterns: Optional[Dict] = None,
        channel_name: str = None,
        client: Optional[any] = None
    ) -> Optional[Dict]:
        """
        Viral video senaryosu oluştur
        
        Args:
            topic: Ana konu (örn: "Paranın gücü")
            niche: İçerik kategorisi (finance, health, education)
            duration: Video süresi (saniye)
            platform: Platform (tiktok, youtube)
            language: Dil (tr, en)
            viral_patterns: Öğrenilen viral pattern'ler (opsiyonel)
            
        Returns:
            Dict: Senaryo detayları veya None
        """
        try:
            # Prompt oluştur (viral patterns ile)
            prompt = self._create_viral_prompt(
                topic=topic,
                niche=niche,
                duration=duration,
                platform=platform,
                language=language,
                viral_patterns=viral_patterns,
                channel_name=channel_name
            )
            
            self.logger.info(f"Gemini'ye senaryo sorgusu gönderiliyor...")
            self.logger.info(f"Konu: {topic}, Kategori: {niche}, Süre: {duration}s")
            
            if viral_patterns and viral_patterns.get('winning_hooks'):
                self.logger.info(f"🔥 {len(viral_patterns['winning_hooks'])} viral pattern kullanılıyor!")
            
            # Gemini'den yanıt al
            response_text = self._generate_content(prompt, client=client)
            
            if not response_text:
                self.logger.error("Gemini yanıtı boş")
                return None
            
            # JSON çıkar
            scenario = self._parse_response(response_text)
            
            if scenario:
                self.logger.info(f"✅ Senaryo oluşturuldu: {scenario.get('hook', 'N/A')[:50]}...")
                return scenario
            else:
                self.logger.error("Senaryo parse edilemedi")
                return None
                
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "Quota exceeded" in error_str:
                raise e
            self.logger.error(f"Senaryo üretim hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _generate_content(self, prompt: str, client=None) -> Optional[str]:
        """İçerik üret (OAuth veya API Key ile)"""
        try:
            if self.oauth_client:
                # OAuth ile
                return self.oauth_client.generate_content(prompt, model=self.model_name)
            
            # Use passed client OR self.client
            active_client = client if client else self.client
            
            if active_client:
                # API Key ile (new SDK)
                response = active_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.9,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                return response.text
        except Exception as e:
            # Let 429 errors bubble up so KeyManager can rotate
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                raise e
            self.logger.error(f"İçerik üretim hatası: {e}")
            return None
    
    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Gemini yanıtını parse et - Gelişmiş markdown ve JSON temizleme"""
        try:
            import re
            
            # Boş yanıt kontrolü
            if not response_text or not response_text.strip():
                self.logger.error("AI yanıtı boş")
                return None
            
            # Yorumları kaldır (// ve /* */)
            text = response_text
            
            # ```json ... ``` veya ``` ... ``` bloğunu çıkar (case-insensitive)
            json_match = re.search(r'```\s*json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
            if not json_match:
                # Sadece ``` ... ``` bloğu var mı?
                json_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # JSON bloğu bulunamadı, direkt text'i dene
                json_str = text.strip()
            
            # JSON'dan önceki ve sonraki metinleri temizle
            # İlk { ve sonrasını bul
            start_idx = json_str.find('{')
            end_idx = json_str.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = json_str[start_idx:end_idx+1]
            
            # Trailing comma düzeltmeleri (JSON hatalarının yaygın nedeni)
            # Son elemandan sonra gelen virgülleri kaldır
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            
            # Parse et
            try:
                scenario = json.loads(json_str)
            except json.JSONDecodeError as e:
                # İlk deneme başarısız, daha agresif temizleme dene
                self.logger.warning(f"İlk JSON parse başarısız, temizleme deneniyor: {e}")
                
                # Yeni satırları ve fazla boşlukları normalize et
                json_str = re.sub(r'\n+', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                
                # Tekrar dene
                scenario = json.loads(json_str)
            
            # Validasyon ve varsayılan değerler
            if not isinstance(scenario, dict):
                self.logger.error(f"Parse edilen veri dict değil: {type(scenario)}")
                return None
            
            # Zorunlu alanlar için varsayılan değerler
            if "hook" not in scenario:
                scenario["hook"] = scenario.get("title", "Viral Video")
            if "scenes" not in scenario or not isinstance(scenario["scenes"], list):
                self.logger.warning("Sahne bilgisi eksik veya geçersiz")
                scenario["scenes"] = []
            if "title" not in scenario:
                scenario["title"] = scenario.get("hook", "Viral Video")
            if "description" not in scenario:
                scenario["description"] = scenario.get("hook", "")
            if "tags" not in scenario or not isinstance(scenario["tags"], list):
                scenario["tags"] = ["viral", "shorts"]
            if "visual_keywords" not in scenario:
                scenario["visual_keywords"] = []
            
            # Süre kontrolü
            try:
                total_duration = sum(
                    int(scene.get("duration", 0)) 
                    for scene in scenario.get("scenes", [])
                    if isinstance(scene, dict)
                )
                scenario["total_duration"] = total_duration
            except (ValueError, TypeError):
                scenario["total_duration"] = 60  # Varsayılan süre
            
            self.logger.info(f"✅ Senaryo başarıyla parse edildi: {scenario.get('title', 'N/A')[:50]}")
            return scenario
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse hatası: {e}")
            self.logger.error(f"Yanıt: {response_text[:1000]}...")
            return None
        except Exception as e:
            self.logger.error(f"Response parse hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _create_viral_prompt(
        self,
        topic: str,
        niche: str,
        duration: int,
        platform: str,
        language: str,
        viral_patterns: Optional[Dict] = None,
        channel_name: str = None
    ) -> str:
        """Prepare prompt for Gemini (Strictly English & Viral Patterns)"""
        
        # Platform Specs (English)
        platform_specs = {
            "tiktok": "For TikTok: High energy, fast-paced, visually grabbing. First 3 seconds are critical!",
            "youtube": "For YouTube Shorts: Slightly more detailed but still fast-paced and retaining."
        }
        
        # Niche Specs (English)
        niche_specs = {
            "finance": "Money, wealth, success, investment secrets. Motivational yet educational.",
            "health": "Health, fitness, life hacks. Reliable and practical.",
            "education": "Did you know facts, history, science. Curiosity inducing.",
            "motivation": "Inspiring, empowering, stoic. Emotional connection."
        }
        
        # Viral Pattern Feedback
        viral_feedback = ""
        if viral_patterns and viral_patterns.get('winning_hooks'):
            winning_hooks = viral_patterns['winning_hooks'][:5]
            
            viral_feedback = f"""
**🔥 VIRAL PATTERN FEEDBACK (USE THIS!):**
The following actual viral hooks have performed well previously:
{chr(10).join(f'  ✓ "{hook}"' for hook in winning_hooks)}

**IMPORTANT INSTRUCTION:** 
Analyze the structure, tone, and style of these winning hooks.
Do NOT copy them, but MIMIC their formula to create a NEW killer hook.
Did they use numbers? A question? A controversial statement? Use that pattern!
"""
        # KANAL TONU AYARI (Channel Persona)
        channel_tone_instruction = ""
        if channel_name and channel_name in CHANNEL_STYLES:
            style = CHANNEL_STYLES[channel_name]
            channel_tone_instruction = f"""
**CHANNEL PERSONA & TONE (STRICTLY FOLLOW THIS):**
Target Audience & Tone: {style['script_tone']}
This video MUST reflect this specific identity. Do not write a generic script.
"""
        
        prompt = f"""You are a world-class viral video scriptwriter. 
Your task is to write a generic, high-retention script for a {duration}-second {platform.upper()} video about: "{topic}".

**PLATFORM:** {platform.upper()}
{platform_specs.get(platform, "")}

**NICHE:** {niche}
{niche_specs.get(niche, "General viral content")}

{viral_feedback}

{channel_tone_instruction}

**REQUIREMENTS:**
1. **THE HOOK:** Start with a MANDATORY killer hook in the first 3 seconds (Curiosity gap, shock, or direct benefit).
2. **VISUALS:** Select highly relevant, specific, and search-friendly **ENGLISH** keywords for Pexels stock footage.
3. **SEO:** Create a clickbait title and SEO-optimized description.
4. **LANGUAGE:** Natural, fluid, spoken American English. Simple and engaging.
5. **TIMING:** Total duration must be {duration} seconds (approx. 130-150 words).
6. **OUTRO:** End with a strong Call-to-Action (CTA) like "Follow for more", "Like" or "Save this".

**SCRIPT FORMAT (JSON ONLY):**
```json
{{
  "title": "Viral Clickbait Title (e.g., 3 Secrets Millionaires Hide)",
  "description": "SEO optimized short description with keywords",
  "tags": ["tag1", "tag2", "tag3", "...(15 tags max)"],
  "hook": "The very first sentence shown on screen (must be catchy)",
  "total_duration": {duration},
  "scenes": [
    {{
      "id": 1,
      "narration": "Voiceover text in ENGLISH...",
      "visual_keywords": ["money stack", "luxury car", "man smiling"],
      "visual_prompt": "Brief description of the visual scene in English",
      "duration": 5
    }},
    {{
      "id": 2,
      "narration": "...",
      "visual_keywords": ["stock chart", "growth arrow", "green"],
      "duration": 5
    }}
  ],
  "cta": "Follow for more amazing content",
  "music_keywords": "Search terms for background music (e.g., dark ambient, motivational cinematic)",
  "viral_elements": ["List of viral techniques used"],
  "estimated_engagement": 9.2
}}
```

**IMPORTANT:** 
- Return ONLY valid JSON.
- `visual_keywords` must be concrete **ENGLISH** terms for video search (e.g., "sad man", "dark forest").
- `music_keywords` must be concrete **ENGLISH** terms for Pixabay music search.
- `narration` must be strictly in **ENGLISH**.
- Total scene duration must sum up to approx {duration} seconds.

Now, generate the viral script for: {topic}"""
        
        return prompt
    
    def create_scenario_for_account(
        self,
        account_id: str,
        account_topic: str,
        platform: str = "tiktok"
    ) -> Optional[Dict]:
        """
        Hesap için otomatik senaryo oluştur
        
        Args:
            account_id: Hesap ID
            account_topic: Hesap konusu
            platform: Platform
            
        Returns:
            Dict: Senaryo
        """
        # Konu'dan niche belirle
        niche_mapping = {
            "para": "finance",
            "finans": "finance",
            "zenginlik": "finance",
            "money": "finance",
            "wealth": "finance",
            "sağlık": "health",
            "yaşam": "health",
            "health": "health",
            "bilgi": "education",
            "eğitim": "education",
            "info": "education",
            "history": "education",
            "motivasyon": "motivation",
            "motivation": "motivation"
        }
        
        # Basit keyword matching
        niche = "general"
        for keyword, category in niche_mapping.items():
            if keyword.lower() in account_topic.lower():
                niche = category
                break
        
        return self.generate_viral_scenario(
            topic=account_topic,
            niche=niche,
            duration=60,
            platform=platform
        )

    def generate_viral_topic(self, niche: str, account_name: str = None) -> str:
        """
        Niş ve hesap ismi için viral olma potansiyeli yüksek bir konu önerir.
        """
        try:
            account_context = ""
            if account_name:
                account_context = f"This topic is for a social media account named '{account_name}'. The topic must be perfectly aligned with the concept this name promises (e.g., 'Money' -> finance, 'History' -> history, 'Comedy' -> entertainment)."

            prompt = f"""
            You are a world-class social media strategist. Suggest ONE video topic for the '{niche}' category that has high viral potential today. 
            The topic must be in **ENGLISH** and extremely catchy.
            
            {account_context}
            
            Categories & Expectations:
            - finance: Money, wealth, savings, investment mistakes.
            - health: Weight loss, healthy living, harmful foods.
            - education: Interesting facts, unknown truths, history.
            - motivation: Success stories, discipline, psychology.
            
            Only write the topic. Example output: "3 Spending Mistakes Millionaires Never Make"
            """
            
            response = self._generate_content(prompt)
            if response:
                topic = response.strip().replace('"', '')
                self.logger.info(f"🧠 AI Suggested Topic ({niche} - {account_name}): {topic}")
                return topic
            return f"Interesting fact about {niche}"
            
        except Exception as e:
            self.logger.error(f"Konu üretme hatası: {e}")
            return f"{niche} hakkında bilinmeyenler"


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("GEMINI SENARYO GENERATOR TEST")
    print("="*60)
    
    try:
        generator = ScenarioGenerator()
        
        # Test: Paranın gücü (TikTok)
        print("\n[Test] Paranın gücü - TikTok senaryosu")
        
        scenario = generator.generate_viral_scenario(
            topic="Paranın gücü",
            niche="finance",
            duration=60,
            platform="tiktok"
        )
        
        if scenario:
            print("\n✅ SENARYO BAŞARILI!")
            print(f"\nHook: {scenario.get('hook')}")
            print(f"\nToplam süre: {scenario.get('total_duration')} saniye")
            print(f"Sahne sayısı: {len(scenario.get('scenes', []))}")
            
            print("\n--- SAHNELER ---")
            for i, scene in enumerate(scenario.get("scenes", []), 1):
                print(f"\nSahne {i} ({scene.get('duration')}s):")
                print(f"  {scene.get('narration')}")
                print(f"  Visual Prompt: {scene.get('visual_prompt', 'N/A')}")
                print(f"  Keywords: {', '.join(scene.get('visual_keywords', []))}")
            
            print(f"\nCTA: {scenario.get('cta')}")
            
            # JSON olarak kaydet
            output_file = "test_scenario.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(scenario, f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 Senaryo kaydedildi: {output_file}")
            
        else:
            print("❌ Senaryo oluşturulamadı")
            
    except Exception as e:
        print(f"❌ HATA: {e}")
        import traceback
        traceback.print_exc()
