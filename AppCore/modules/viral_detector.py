"""
Viral Detector - Viral videoları tespit et ve pattern'leri öğren
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ViralDetector:
    """Viral videoları tespit eden sistem"""
    
    # Viral threshold'ları (platform bazlı)
    VIRAL_THRESHOLDS = {
        'tiktok': {
            'views': 10000,  # 10K+ izlenme
            'engagement_rate': 0.05,  # %5 (likes/views)
            'watch_time': 0.70  # %70 tamamlanma
        },
        'youtube': {
            'views': 5000,  # 5K+ izlenme (shorts için daha düşük)
            'engagement_rate': 0.04,  # %4
            'watch_time': 0.65  # %65
        },
        'instagram': {
            'views': 8000,  # 8K+ izlenme
            'engagement_rate': 0.06,  # %6 (daha yüksek engage)
            'watch_time': 0.75  # %75
        }
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def is_viral(self, stats: Dict, platform: str) -> bool:
        """
        Video viral oldu mu?
        
        Args:
            stats: {'views': 15000, 'likes': 1200, 'watch_time': 0.85}
            platform: 'tiktok', 'youtube', 'instagram'
        
        Returns:
            bool: Viral ise True
        """
        if platform not in self.VIRAL_THRESHOLDS:
            logger.warning(f"Unknown platform: {platform}, using tiktok thresholds")
            platform = 'tiktok'
        
        threshold = self.VIRAL_THRESHOLDS[platform]
        
        # Minimum views kontrolü
        views = stats.get('views', 0)
        if views < threshold['views']:
            logger.debug(f"Not viral: views {views} < {threshold['views']}")
            return False
        
        # Engagement rate kontrolü
        likes = stats.get('likes', 0)
        engagement_rate = (likes / views) if views > 0 else 0
        
        if engagement_rate < threshold['engagement_rate']:
            logger.debug(f"Not viral: engagement {engagement_rate:.2%} < {threshold['engagement_rate']:.2%}")
            return False
        
        # Watch time kontrolü (opsiyonel)
        watch_time = stats.get('watch_time', 1.0)  # Default 100%
        if watch_time < threshold['watch_time']:
            logger.debug(f"Not viral: watch_time {watch_time:.2%} < {threshold['watch_time']:.2%}")
            return False
        
        # Tüm kriterleri geçti!
        logger.info(f"🔥 VIRAL DETECTED! {views:,} views, {engagement_rate:.2%} engagement")
        return True
    
    def get_viral_score(self, stats: Dict, platform: str) -> float:
        """
        Video viral skoru (0.0 - 1.0)
        
        Threshold'a göre normalize edilmiş skor
        1.0 = threshold'un 3 katı
        """
        threshold = self.VIRAL_THRESHOLDS.get(platform, self.VIRAL_THRESHOLDS['tiktok'])
        
        views = stats.get('views', 0)
        likes = stats.get('likes', 0)
        engagement_rate = (likes / views) if views > 0 else 0
        watch_time = stats.get('watch_time', 0.85)
        
        # Her metrik için skor (0-1)
        view_score = min(views / (threshold['views'] * 3), 1.0)
        engagement_score = min(engagement_rate / (threshold['engagement_rate'] * 2), 1.0)
        watch_score = min(watch_time / threshold['watch_time'], 1.0)
        
        # Ağırlıklı ortalama
        total_score = (
            view_score * 0.5 +  # Views en önemli
            engagement_score * 0.3 +  # Engagement ikinci
            watch_score * 0.2  # Watch time üçüncü
        )
        
        return total_score
    
    def extract_winning_patterns(self, viral_videos: List[Dict]) -> Dict:
        """
        Viral videoların ortak özelliklerini çıkar
        
        Args:
            viral_videos: [{
                'hook': 'Zenginlerin 3 sırrı!',
                'niche': 'finance',
                'topic': 'zenginlik',
                'duration': 45,
                'views': 25000,
                'upload_hour': 18
            }]
        
        Returns:
            {
                'winning_hooks': ['Hook 1', 'Hook 2'],
                'winning_topics': ['topic1', 'topic2'],
                'optimal_duration': 45,
                'best_posting_hours': [18, 19, 20]
            }
        """
        if not viral_videos:
            return {
                'winning_hooks': [],
                'winning_topics': [],
                'optimal_duration': 60,
                'best_posting_hours': []
            }
        
        # Hook'ları topla (en çok views alanlar)
        hooks = sorted(
            [(v['hook'], v.get('views', 0)) for v in viral_videos if v.get('hook')],
            key=lambda x: x[1],
            reverse=True
        )
        winning_hooks = [h[0] for h in hooks[:10]]  # Top 10
        
        # Topic frequency
        topic_count = {}
        for v in viral_videos:
            topic = v.get('topic', '')
            if topic:
                topic_count[topic] = topic_count.get(topic, 0) + 1
        
        winning_topics = sorted(topic_count.keys(), key=lambda x: topic_count[x], reverse=True)[:5]
        
        # Optimal duration (ortalama)
        durations = [v.get('duration', 60) for v in viral_videos if v.get('duration')]
        optimal_duration = int(sum(durations) / len(durations)) if durations else 60
        
        # Best posting hours (frequency)
        hour_count = {}
        for v in viral_videos:
            upload_time = v.get('upload_time')
            if upload_time:
                if isinstance(upload_time, str):
                    from datetime import datetime
                    upload_time = datetime.fromisoformat(upload_time)
                
                hour = upload_time.hour
                hour_count[hour] = hour_count.get(hour, 0) + 1
        
        best_hours = sorted(hour_count.keys(), key=lambda x: hour_count[x], reverse=True)[:4]
        
        return {
            'winning_hooks': winning_hooks,
            'winning_topics': winning_topics,
            'optimal_duration': optimal_duration,
            'best_posting_hours': best_hours
        }
    
    def analyze_hook_structure(self, hook: str) -> Dict:
        """
        Hook'un yapısını analiz et (Gemini için)
        
        Returns:
            {
                'has_number': True,  # "3 sır" gibi
                'has_question': False,
                'has_urgency': True,  # "hemen", "şimdi"
                'word_count': 5,
                'starts_with_capital': True
            }
        """
        import re
        
        return {
            'has_number': bool(re.search(r'\d+', hook)),
            'has_question': '?' in hook,
            'has_urgency': any(word in hook.lower() for word in ['hemen', 'şimdi', 'acil', 'son', 'sınırlı']),
            'has_secret': any(word in hook.lower() for word in ['sır', 'gizli', 'kimse bilmiyor', 'özel']),
            'word_count': len(hook.split()),
            'starts_with_capital': hook[0].isupper() if hook else False,
            'length': len(hook)
        }


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("VIRAL DETECTOR TEST")
    print("="*60)
    
    detector = ViralDetector()
    
    # Test stats
    test_stats = [
        {'views': 5000, 'likes': 100, 'watch_time': 0.60, 'label': 'Not Viral'},
        {'views': 15000, 'likes': 1200, 'watch_time': 0.85, 'label': 'VIRAL!'},
        {'views': 50000, 'likes': 5000, 'watch_time': 0.92, 'label': 'SUPER VIRAL!'},
    ]
    
    for stats in test_stats:
        label = stats.pop('label')
        is_viral = detector.is_viral(stats, 'tiktok')
        score = detector.get_viral_score(stats, 'tiktok')
        
        print(f"\n{label}")
        print(f"  Stats: {stats}")
        print(f"  Is Viral: {is_viral}")
        print(f"  Score: {score:.2%}")
    
    # Pattern extraction test
    viral_videos = [
        {
            'hook': 'Zenginlerin gizlediği 3 sır!',
            'niche': 'finance',
            'topic': 'zenginlik',
            'duration': 45,
            'views': 25000
        },
        {
            'hook': 'Para kazanmanın 5 yolu!',
            'niche': 'finance',
            'topic': 'para',
            'duration': 50,
            'views': 18000
        }
    ]
    
    patterns = detector.extract_winning_patterns(viral_videos)
    
    print(f"\n\n💎 Winning Patterns:")
    print(f"Hooks: {patterns['winning_hooks']}")
    print(f"Topics: {patterns['winning_topics']}")
    print(f"Optimal Duration: {patterns['optimal_duration']}s")
