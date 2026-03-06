"""
Gemini Key Manager - Centralized API Key Management
Singleton pattern for shared key rotation state across modules.
"""

import os
import logging
import asyncio
import threading
from typing import Optional, List
from google import genai

logger = logging.getLogger(__name__)

class GeminiKeyManager:
    """
    Manages multiple Gemini API keys with rotation on exhaustion.
    Implemented as a Singleton to share state.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GeminiKeyManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.keys: List[str] = []
        
        # 1. Load from ENV
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            self.keys.append(env_key)
            
        # 2. Load Backup Keys (Provided by User)
        backup_keys = [
            "GEMINI_KEY_1",
            "GEMINI_KEY_2",
            "GEMINI_KEY_3",
            "GEMINI_KEY_4", 
            "GEMINI_KEY_5"
        ]
        
        for k in backup_keys:
            if k and k not in self.keys:
                self.keys.append(k)
        
        self.current_index = 0
        self._sync_lock = threading.Lock()
        self._initialized = True
        
        logger.info(f"🔑 GeminiKeyManager (Singleton) initialized with {len(self.keys)} keys")
        
    def get_client(self) -> Optional[genai.Client]:
        """Get current client"""
        if not self.keys:
            return None
        return genai.Client(api_key=self.keys[self.current_index])
        
    def rotate_key(self):
        """Switch to next key (Thread-safe)"""
        if not self.keys:
            return
        with self._sync_lock:
            prev_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.keys)
            logger.warning(f"🔄 Rotating API Key: {prev_index} -> {self.current_index} (Thread-safe)")
        
    async def execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with key rotation on 429 errors"""
        if not self.keys:
            logger.error("No API keys available")
            return None
            
        max_retries = len(self.keys) * 3 # Try all keys 3 times
        
        for attempt in range(max_retries):
            try:
                # Get client for current attempt
                client = self.get_client()
                
                # Execute function
                # func is expected to be an async function accepting 'client' as first arg
                return await func(client, *args, **kwargs)
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "Quota exceeded" in error_str:
                    logger.warning(f"⚠️ Quota exceeded for key {self.current_index}. Rotating and waiting...")
                    self.rotate_key()  # Sync call
                    await asyncio.sleep(10) # Increased delay for 100+ video production
                    continue
                else:
                    raise e # Re-raise other errors
        
        logger.error("❌ All API keys exhausted after multiple retries.")
        return None
        
    def get_status(self):
        """Debug status"""
        return {
            "total_keys": len(self.keys),
            "current_index": self.current_index,
            "current_key_masked": f"{self.keys[self.current_index][:5]}...{self.keys[self.current_index][-5:]}" if self.keys else "None"
        }
