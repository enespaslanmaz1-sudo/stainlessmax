"""
Jarvis AI - Gelişmiş Asistan Modülü
Dosya analizi, Tool Calling ve Sistem Entegrasyonu
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any
from google import genai
from google.genai import types

class JarvisAI:
    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-2.5-flash"
        
        if not self.api_key:
            self.logger.warning("JarvisAI: GEMINI_API_KEY bulunamadı!")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            self.logger.info(f"JarvisAI: Gemini client hazır ({self.model_name})")

        self.system_prompt = """Sen Jarvis adında, Stainless Max video otomasyon sisteminin beyni olan gelişmiş bir AI asistansın.
        Stainless Max; YouTube Shorts ve TikTok için otomatik video üreten, Gemini, Pexels, Pixabay ve FFmpeg kullanan bir platformdur.
        
        YETENEKLERİN:
        1. Dosya Analizi: Sana gönderilen resim, video ve belgeleri en ince ayrıntısına kadar inceleyebilirsin.
        2. Video Üretimi: Kullanıcının isteği üzerine sistem araçlarını kullanarak video üretimini başlatabilirsin.
        3. Sistem Bilgisi: Proje yapısını ve modülleri bilirsin.
        
        KURALLARIN:
        - Her zaman Türkçe yanıt ver.
        - Profesyonel, nazik ve çözüm odaklı ol.
        - Yanıtların net ve "nokta atışı" olsun. Gereksiz uzatma.
        - Video üretimi istendiğinde eğer konu, kanal veya süre eksikse kullanıcıya sor.
        - Teknik konularda derinlemesine bilgi ver.
        
        Sistem Fonksiyonları (Tools):
        - create_video: Video üretimini başlatır.
        - list_accounts: Aktif kanalları listeler.
        - get_system_status: Sistem sağlığını kontrol eder.
        """

    def _get_tools(self) -> List[Dict]:
        """Gemini için kullanılabilir fonksiyon tanımları"""
        return [
            {
                "name": "create_video",
                "description": "Belirlenen konu ve platform için video üretimini başlatır.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "topic": {"type": "STRING", "description": "Videonun konusu veya başlığı"},
                        "platform": {"type": "STRING", "description": "youtube veya tiktok", "enum": ["youtube", "tiktok"]},
                        "account_id": {"type": "STRING", "description": "Üretim yapılacak hesap ID'si"},
                        "duration": {"type": "INTEGER", "description": "Saniye cinsinden süre (varsayılan 60)"},
                        "aspect_ratio": {"type": "STRING", "description": "9:16 veya 16:9", "enum": ["9:16", "16:9"]}
                    },
                    "required": ["topic", "platform", "account_id"]
                }
            },
            {
                "name": "list_accounts",
                "description": "Sistemde kayıtlı aktif sosyal medya hesaplarını listeler.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "get_system_status",
                "description": "Sistem kaynaklarını ve modüllerin durumunu kontrol eder.",
                "parameters": {"type": "OBJECT", "properties": {}}
            }
        ]

    async def chat(self, message: str, history: List[Dict] = None, files: List[str] = None) -> Dict:
        """Kullanıcı mesajını işle, dosya analizi ve tool calling yap"""
        if not self.client:
            return {"response": "API anahtarı eksik."}

        try:
            # 1. Mesaj içeriğini hazırla
            contents = []
            
            # Sistem mesajını geçmişe dahil etmiyoruz, config'de veriyoruz
            # Dosyaları yükle ve içeriğe ekle
            if files:
                for file_path in files:
                    p = Path(file_path)
                    if p.exists():
                        # Dosya tipine göre yükleme
                        mime_type = self._get_mime_type(p.suffix)
                        with open(p, "rb") as f:
                            file_data = f.read()
                        contents.append(types.Part.from_bytes(data=file_data, mime_type=mime_type))
            
            contents.append(types.Part.from_text(text=message))

            # 2. Gemini sorgusu
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    tools=[types.Tool(function_declarations=[
                        types.FunctionDeclaration(**t) for t in self._get_tools()
                    ])],
                    temperature=0.7
                )
            )

            # 3. Yanıtı işle (Tool calling kontrolü)
            full_response = ""
            tool_calls = []

            for part in response.candidates[0].content.parts:
                if part.text:
                    full_response += part.text
                if part.function_call:
                    tool_calls.append({
                        "name": part.function_call.name,
                        "args": part.function_call.args
                    })

            return {
                "response": full_response,
                "tool_calls": tool_calls
            }

        except Exception as e:
            self.logger.error(f"Jarvis Chat Error: {e}")
            return {"response": f"Bir hata oluştu: {str(e)}"}

    def _get_mime_type(self, extension: str) -> str:
        """Dosya uzantısına göre MIME type dön"""
        ext = extension.lower()
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".mp4": "video/mp4",
            ".pdf": "application/pdf",
            ".txt": "text/plain"
        }
        return mapping.get(ext, "application/octet-stream")

# Singleton instance
jarvis = JarvisAI()
