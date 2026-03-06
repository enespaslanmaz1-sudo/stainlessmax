"""
Analytics Engine - Detaylı İstatistik ve Raporlama
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict


class AnalyticsEngine:
    """Detaylı analiz ve raporlama motoru"""
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        self.reports_path = Path("analytics/reports")
        self.reports_path.mkdir(parents=True, exist_ok=True)
    
    def generate_daily_report(self, date: str = None) -> Dict:
        """Günlük rapor oluştur"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        if not self.db:
            return {}
        
        # Bugünkü videolar
        with self.db.db_path as conn:
            cursor = conn.cursor()
            
            # Video istatistikleri
            cursor.execute("""
                SELECT platform, status, COUNT(*) as count
                FROM videos
                WHERE DATE(created_at) = ?
                GROUP BY platform, status
            """, (date,))
            
            platform_stats = defaultdict(lambda: defaultdict(int))
            for row in cursor.fetchall():
                platform_stats[row[0]][row[1]] = row[2]
            
            # Saatlik dağılım
            cursor.execute("""
                SELECT strftime('%H', created_at) as hour, COUNT(*)
                FROM videos
                WHERE DATE(created_at) = ?
                GROUP BY hour
            """, (date,))
            
            hourly_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Hesap bazında
            cursor.execute("""
                SELECT account_id, COUNT(*) as count
                FROM videos
                WHERE DATE(created_at) = ?
                GROUP BY account_id
            """, (date,))
            
            account_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        report = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_videos': sum(sum(p.values()) for p in platform_stats.values()),
                'successful_uploads': sum(p.get('uploaded', 0) for p in platform_stats.values()),
                'failed_uploads': sum(p.get('failed', 0) for p in platform_stats.values()),
                'pending': sum(p.get('pending', 0) for p in platform_stats.values())
            },
            'platform_breakdown': dict(platform_stats),
            'hourly_distribution': hourly_distribution,
            'account_performance': account_stats
        }
        
        # Raporu kaydet
        self._save_report(f"daily_{date}.json", report)
        
        return report
    
    def generate_weekly_report(self) -> Dict:
        """Haftalık rapor oluştur"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        if not self.db:
            return {}
        
        with self.db.db_path as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM videos
                WHERE DATE(created_at) BETWEEN ? AND ?
                GROUP BY date
            """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            
            daily_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        report = {
            'period': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}",
            'daily_counts': daily_counts,
            'total': sum(daily_counts.values()),
            'average_per_day': sum(daily_counts.values()) / 7
        }
        
        self._save_report(f"weekly_{end_date.strftime('%Y%m%d')}.json", report)
        
        return report
    
    def get_performance_metrics(self) -> Dict:
        """Performans metrikleri"""
        if not self.db:
            return {}
        
        with self.db.db_path as conn:
            cursor = conn.cursor()
            
            # Son 30 gün
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'uploaded' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM videos
                WHERE DATE(created_at) >= ?
            """, (thirty_days_ago,))
            
            row = cursor.fetchone()
            
            success_rate = (row[1] / row[0] * 100) if row[0] > 0 else 0
            
            return {
                'total_videos_30d': row[0],
                'successful_uploads': row[1],
                'failed_uploads': row[2],
                'success_rate': round(success_rate, 2),
                'average_daily': round(row[0] / 30, 2)
            }
    
    def get_best_performing_accounts(self, limit: int = 5) -> List[Dict]:
        """En iyi performans gösteren hesaplar"""
        if not self.db:
            return []
        
        with self.db.db_path as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    account_id,
                    platform,
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'uploaded' THEN 1 ELSE 0 END) as success
                FROM videos
                GROUP BY account_id
                ORDER BY success DESC
                LIMIT ?
            """, (limit,))
            
            return [
                {
                    'account_id': row[0],
                    'platform': row[1],
                    'total': row[2],
                    'successful': row[3],
                    'success_rate': round(row[3] / row[2] * 100, 2) if row[2] > 0 else 0
                }
                for row in cursor.fetchall()
            ]
    
    def _save_report(self, filename: str, data: Dict):
        """Raporu kaydet"""
        filepath = self.reports_path / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def export_csv(self, start_date: str = None, end_date: str = None) -> str:
        """CSV formatında dışa aktar"""
        import csv
        
        if not self.db:
            return ""
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        csv_path = self.reports_path / f"export_{start_date}_to_{end_date}.csv"
        
        with self.db.db_path as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT account_id, platform, title, status, created_at, published_at
                FROM videos
                WHERE DATE(created_at) BETWEEN ? AND ?
                ORDER BY created_at DESC
            """, (start_date, end_date))
            
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['Hesap', 'Platform', 'Başlık', 'Durum', 'Oluşturulma', 'Yayınlanma'])
                writer.writerows(cursor.fetchall())
        
        return str(csv_path)


# Global instance
analytics_engine = AnalyticsEngine()
