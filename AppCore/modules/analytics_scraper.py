"""
Analytics Scraper - TikTok/YouTube video istatistiklerini çek
Apify API ve Selenium fallback ile
"""

import os
import logging
import requests
import time
import random
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TikTokAnalyticsScraper:
    """
    TikTok video stats çekici
    
    Öncelik Sırası:
    1. Apify API (hızlı, güvenilir)
    2. Selenium fallback (API fail olursa)
    """
    
    def __init__(self):
        self.apify_token = os.getenv("APIFY_API_TOKEN")
    
    def get_video_stats(self, video_url: str) -> Dict:
        """
        TikTok video istatistiklerini çek
        
        Returns:
            {
                'views': 15000,
                'likes': 1200,
                'comments': 45,
                'shares': 30,
                'watch_time': 0.85
            }
        """
        # Önce Apify dene
        if self.apify_token and self.apify_token != "YOUR_APIFY_API_TOKEN":
            logger.info("Trying Apify API...")
            stats = self._fetch_via_apify(video_url)
            if stats:
                return stats
        
        # Fallback: Selenium
        logger.info("Apify failed, using Selenium fallback...")
        return self._fetch_via_selenium(video_url)
    
    def _fetch_via_apify(self, video_url: str) -> Optional[Dict]:
        """Apify TikTok Scraper API kullan"""
        try:
            # Apify TikTok Scraper actor
            actor_id = "clockworks~free-tiktok-scraper"
            
            # Run input
            run_input = {
                "postURLs": [video_url],
                "resultsPerPage": 1
            }
            
            # Actor'ı başlat
            headers = {"Authorization": f"Bearer {self.apify_token}"}
            
            response = requests.post(
                f"https://api.apify.com/v2/acts/{actor_id}/runs",
                json=run_input,
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 201:
                logger.warning(f"Apify run failed: {response.status_code}")
                return None
            
            run_id = response.json()['data']['id']
            
            # Sonuç bekle (max 60 saniye)
            for _ in range(30):
                time.sleep(2)
                
                status_response = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=headers
                )
                
                status = status_response.json()['data']['status']
                
                if status == 'SUCCEEDED':
                    # Dataset'ten sonuçları al
                    dataset_id = status_response.json()['data']['defaultDatasetId']
                    
                    items_response = requests.get(
                        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                        headers=headers
                    )
                    
                    items = items_response.json()
                    
                    if items and len(items) > 0:
                        video_data = items[0]
                        
                        return {
                            'views': video_data.get('playCount', 0),
                            'likes': video_data.get('diggCount', 0),
                            'comments': video_data.get('commentCount', 0),
                            'shares': video_data.get('shareCount', 0),
                            'watch_time': 0.85  # TikTok API doesn't provide this
                        }
                
                elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                    logger.warning(f"Apify run {status}")
                    return None
            
            logger.warning("Apify timeout")
            return None
            
        except Exception as e:
            logger.error(f"Apify API error: {e}")
            return None
    
    def _fetch_via_selenium(self, video_url: str) -> Dict:
        """
        Selenium ile TikTok stats çek
        
        Not: Bu basit bir implementasyon, anti-ban için
        HumanizedBrowser kullanılabilir
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            from selenium.webdriver.chrome.service import Service as ChromeService
            from webdriver_manager.chrome import ChromeDriverManager
            import subprocess
            
            service = ChromeService(ChromeDriverManager().install())
            service.creation_flags = subprocess.CREATE_NO_WINDOW
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(video_url)
            
            # Sayaçların yüklenmesini bekle
            time.sleep(random.uniform(3, 6))
            
            # Stats çek (TikTok HTML structure'a göre)
            try:
                # Views (strong tag içinde)
                views_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "strong[data-e2e='browse-video-views']"))
                )
                views_text = views_element.text.strip()
                
                # Likes
                likes_element = driver.find_element(By.CSS_SELECTOR, "strong[data-e2e='browse-like-count']")
                likes_text = likes_element.text.strip()
                
                # Comments
                comments_element = driver.find_element(By.CSS_SELECTOR, "strong[data-e2e='browse-comment-count']")
                comments_text = comments_element.text.strip()
                
                # Shares (bazen olmayabilir)
                try:
                    shares_element = driver.find_element(By.CSS_SELECTOR, "strong[data-e2e='undefined-count']")
                    shares_text = shares_element.text.strip()
                except Exception:
                    shares_text = "0"
                
                driver.quit()
                
                # Parse (K, M dönüşümü)
                return {
                    'views': self._parse_count(views_text),
                    'likes': self._parse_count(likes_text),
                    'comments': self._parse_count(comments_text),
                    'shares': self._parse_count(shares_text),
                    'watch_time': 0.85
                }
                
            except Exception as e:
                logger.error(f"Selenium parsing error: {e}")
                driver.quit()
                return self._get_placeholder_stats()
            
        except Exception as e:
            logger.error(f"Selenium error: {e}")
            return self._get_placeholder_stats()
    
    def _parse_count(self, text: str) -> int:
        """K, M notasyonunu sayıya çevir"""
        text = text.upper().replace(',', '')
        
        if 'K' in text:
            return int(float(text.replace('K', '')) * 1000)
        elif 'M' in text:
            return int(float(text.replace('M', '')) * 1000000)
        else:
            try:
                return int(text)
            except Exception:
                return 0
    
    def _get_placeholder_stats(self) -> Dict:
        """Scraping başarısız olursa fallback"""
        return {
            'views': 0,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'watch_time': 0
        }


class YouTubeShortsAnalytics:
    """
    YouTube Shorts video stats çekici
    YouTube Data API v3 kullanır
    """
    
    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
    
    def get_video_stats(self, video_url: str) -> Dict:
        """
        YouTube Shorts video istatistiklerini çek
        
        Args:
            video_url: https://youtube.com/shorts/VIDEO_ID
        """
        # URL'den video ID çıkar
        video_id = self._extract_video_id(video_url)
        
        if not video_id:
            logger.error(f"Invalid YouTube URL: {video_url}")
            return self._get_placeholder_stats()
        
        if not self.api_key or self.api_key == "YOUR_YOUTUBE_API_KEY":
            logger.warning("YouTube API key yok, placeholder stats")
            return self._get_placeholder_stats()
        
        try:
            from googleapiclient.discovery import build
            
            youtube = build('youtube', 'v3', developerKey=self.api_key)
            
            response = youtube.videos().list(
                part='statistics',
                id=video_id
            ).execute()
            
            if 'items' not in response or len(response['items']) == 0:
                logger.warning(f"Video not found: {video_id}")
                return self._get_placeholder_stats()
            
            stats = response['items'][0]['statistics']
            
            return {
                'views': int(stats.get('viewCount', 0)),
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)),
                'shares': 0,  # YouTube API doesn't provide shares
                'watch_time': 0.70  # Estimate
            }
            
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return self._get_placeholder_stats()
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """URL'den video ID çıkar"""
        # Shorts URL: https://youtube.com/shorts/VIDEO_ID
        if '/shorts/' in url:
            parts = url.split('/shorts/')
            if len(parts) > 1:
                return parts[1].split('?')[0]
        
        # Normal URL: https://youtube.com/watch?v=VIDEO_ID
        if 'v=' in url:
            parts = url.split('v=')
            if len(parts) > 1:
                return parts[1].split('&')[0]
        
        return None
    
    def _get_placeholder_stats(self) -> Dict:
        """API başarısız olursa fallback"""
        return {
            'views': 0,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'watch_time': 0
        }


# Factory function
def get_scraper(platform: str):
    """Platform'a göre scraper döndür"""
    if platform == 'tiktok':
        return TikTokAnalyticsScraper()
    elif platform == 'youtube':
        return YouTubeShortsAnalytics()
    else:
        raise ValueError(f"Unsupported platform: {platform}")


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("ANALYTICS SCRAPER TEST")
    print("="*60)
    
    # TikTok testi
    tiktok_scraper = TikTokAnalyticsScraper()
    
    # Test URL (gerçek TikTok videosu olmalı)
    test_url = "https://www.tiktok.com/@user/video/123456789"
    
    print(f"\nTest URL: {test_url}")
    stats = tiktok_scraper.get_video_stats(test_url)
    
    print(f"\n📊 Stats:")
    print(f"Views: {stats['views']:,}")
    print(f"Likes: {stats['likes']:,}")
    print(f"Comments: {stats['comments']:,}")
    print(f"Shares: {stats['shares']:,}")
