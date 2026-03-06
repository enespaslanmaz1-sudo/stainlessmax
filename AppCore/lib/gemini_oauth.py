"""
Gemini OAuth Manager - Google OAuth2 ile Gemini API erişimi
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# OAuth token cache
_oauth_client = None


class GeminiOAuth:
    """Gemini API OAuth2 yöneticisi"""
    
    def __init__(self):
        self.token_path = Path("config/gemini_oauth_token.json")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = None
        self._api_key = os.getenv("GEMINI_API_KEY")
    
    def get_client(self):
        """Gemini client'ını döndür (OAuth veya API key)"""
        if self.client:
            return self.client
        
        try:
            from google import genai
            
            # Önce API key ile dene
            if self._api_key:
                self.client = genai.Client(api_key=self._api_key)
                logger.info("✅ Gemini client (API Key) hazır")
                return self.client
            
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı")
            return None
            
        except Exception as e:
            logger.error(f"❌ Gemini client oluşturulamadı: {e}")
            return None
    
    def is_authenticated(self) -> bool:
        """OAuth ile kimlik doğrulanmış mı?"""
        return self.client is not None or bool(self._api_key)
    
    def is_token_valid(self) -> bool:
        """Token geçerli mi?"""
        return self.is_authenticated()
    
    def generate_content(self, prompt: str, model: str = "gemini-2.5-flash") -> str:
        """İçerik üret - ScenarioGenerator uyumu için proxy metod"""
        client = self.get_client()
        if not client:
            return None
        try:
            from google.genai import types
            response = client.models.generate_content(
                model=model,
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
            logger.error(f"generate_content hatası: {e}")
            raise


def setup_gemini_oauth() -> bool:
    """Gemini OAuth kurulumunu başlat"""
    global _oauth_client
    try:
        _oauth_client = GeminiOAuth()
        client = _oauth_client.get_client()
        if client:
            logger.info("✅ Gemini OAuth/API kurulumu tamamlandı")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Gemini OAuth kurulumu başarısız: {e}")
        return False


def get_gemini_oauth() -> Optional[GeminiOAuth]:
    """Global Gemini OAuth instance'ını döndür"""
    global _oauth_client
    if _oauth_client is None:
        setup_gemini_oauth()
    return _oauth_client