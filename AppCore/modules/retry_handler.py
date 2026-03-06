"""
Retry Handler - Otomatik Tekrar Deneme Mekanizması
"""

import time
import random
import functools
from typing import Callable, Optional, Type
from enum import Enum


class RetryStrategy(Enum):
    """Tekrar deneme stratejileri"""
    FIXED = "fixed"          # Sabit bekleme
    EXPONENTIAL = "exp"      # Üstel bekleme
    LINEAR = "linear"        # Lineer bekleme
    RANDOM = "random"        # Rastgele bekleme


class RetryHandler:
    """Tekrar deneme yöneticisi"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 60.0, strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
                 exceptions: tuple = (Exception,), on_retry: Callable = None):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.strategy = strategy
        self.exceptions = exceptions
        self.on_retry = on_retry
        self.retry_count = 0
    
    def calculate_delay(self, attempt: int) -> float:
        """Bekleme süresini hesapla"""
        if self.strategy == RetryStrategy.FIXED:
            return self.base_delay
        
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** attempt)
            return min(delay, self.max_delay)
        
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * (attempt + 1)
            return min(delay, self.max_delay)
        
        elif self.strategy == RetryStrategy.RANDOM:
            delay = random.uniform(self.base_delay, self.base_delay * (2 ** attempt))
            return min(delay, self.max_delay)
        
        return self.base_delay
    
    def execute(self, func: Callable, *args, **kwargs):
        """Fonksiyonu çalıştır ve gerekirse tekrar dene"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            
            except self.exceptions as e:
                last_exception = e
                self.retry_count = attempt + 1
                
                if attempt < self.max_retries:
                    delay = self.calculate_delay(attempt)
                    
                    if self.on_retry:
                        self.on_retry(attempt + 1, self.max_retries, delay, e)
                    
                    print(f"[Retry] Deneme {attempt + 1}/{self.max_retries} başarısız. {delay:.1f}s bekleniyor...")
                    time.sleep(delay)
                else:
                    print(f"[Retry] Tüm denemeler başarısız!")
                    raise last_exception
        
        raise last_exception
    
    def reset(self):
        """Sayaçları sıfırla"""
        self.retry_count = 0


def retry(max_retries: int = 3, base_delay: float = 1.0, 
          strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
          exceptions: tuple = (Exception,)):
    """Dekoratör olarak kullan"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            handler = RetryHandler(
                max_retries=max_retries,
                base_delay=base_delay,
                strategy=strategy,
                exceptions=exceptions
            )
            return handler.execute(func, *args, **kwargs)
        return wrapper
    return decorator


# Özel retry handler'lar
class NetworkRetryHandler(RetryHandler):
    """Ağ işlemleri için retry"""
    
    def __init__(self, max_retries: int = 5):
        super().__init__(
            max_retries=max_retries,
            base_delay=2.0,
            max_delay=30.0,
            strategy=RetryStrategy.EXPONENTIAL,
            exceptions=(ConnectionError, TimeoutError, Exception)
        )


class UploadRetryHandler(RetryHandler):
    """Yükleme işlemleri için retry"""
    
    def __init__(self, max_retries: int = 3):
        super().__init__(
            max_retries=max_retries,
            base_delay=5.0,
            max_delay=60.0,
            strategy=RetryStrategy.LINEAR,
            exceptions=(Exception,)
        )


# Global kullanım için fonksiyonlar
def with_retry(func: Callable, max_retries: int = 3, **kwargs):
    """Fonksiyonu retry ile çalıştır"""
    handler = RetryHandler(max_retries=max_retries, **kwargs)
    return handler.execute(func)
