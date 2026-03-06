"""
Reddit Content Fetcher - No-API access to Reddit stories
"""

import requests
import logging
import json
import random
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

class RedditContentFetcher:
    """Fetches stories from Reddit JSON endpoints (No-API)"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        self.headers = {"User-Agent": self.user_agent}
        
        # Database to track used stories
        self.db_path = Path("config/history_agent_db.json")
        self.used_ids = self._load_used_ids()

    def _load_used_ids(self) -> List[str]:
        if not self.db_path.exists():
            return []
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("used_reddit_ids", [])
        except Exception as e:
            self.logger.error(f"Error loading DB: {e}")
            return []

    def save_used_id(self, post_id: str):
        self.used_ids.append(post_id)
        try:
            data = {"used_reddit_ids": self.used_ids, "updated_at": datetime.now().isoformat()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving DB: {e}")

    def fetch_daily_top(self, subreddits: List[str] = None, limit: int = 50) -> List[Dict]:
        """Fetch top posts from subreddits"""
        if not subreddits:
            subreddits = ["history", "Damnthatsinteresting", "todayilearned"]
            
        all_posts = []
        
        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}"
                self.logger.info(f"Fetching {url}...")
                
                response = requests.get(url, headers=self.headers, timeout=10)
                
                if response.status_code == 429:
                    self.logger.warning(f"Rate limited on r/{sub}")
                    continue
                    
                if response.status_code != 200:
                    self.logger.error(f"Failed to fetch r/{sub}: {response.status_code}")
                    continue
                    
                data = response.json()
                children = data.get("data", {}).get("children", [])
                
                for child in children:
                    post = child.get("data", {})
                    
                    # Basic filtering
                    if post.get("stickied") or post.get("is_video"):
                        continue
                        
                    # Must be text-heavy or interesting title
                    title = post.get("title", "")
                    selftext = post.get("selftext", "")
                    
                    # Combine title and text for processing
                    content = f"{title}\n{selftext}".strip()
                    
                    if len(content) < 50: # Too short
                        continue
                        
                    all_posts.append({
                        "id": post.get("id"),
                        "subreddit": sub,
                        "title": title,
                        "text": selftext,
                        "content": content,
                        "score": post.get("score", 0),
                        "url": post.get("url"),
                        "author": post.get("author")
                    })
                    
            except Exception as e:
                self.logger.error(f"Error fetching r/{sub}: {e}")
                
        # Deduplicate
        fresh_posts = [p for p in all_posts if p["id"] not in self.used_ids]
        self.logger.info(f"Fetched {len(all_posts)} posts, {len(fresh_posts)} are fresh.")
        
        # Sort by score
        fresh_posts.sort(key=lambda x: x["score"], reverse=True)
        
        return fresh_posts

    def select_best_stories(self, count: int = 6) -> List[Dict]:
        """Select top stories"""
        posts = self.fetch_daily_top()
        return posts[:count]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetcher = RedditContentFetcher()
    stories = fetcher.select_best_stories(3)
    for i, s in enumerate(stories, 1):
        print(f"{i}. [{s['subreddit']}] {s['title']} (Score: {s['score']})")
