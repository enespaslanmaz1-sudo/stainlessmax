"""
Scheduler - Zamanlanmış Görevler
Belirli saatlerde otomatik üretim
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Callable, List
import json
from pathlib import Path


class ScheduledTask:
    """Zamanlanmış görev"""
    
    def __init__(self, task_id: str, name: str, schedule_type: str, 
                 schedule_time: str, action: str, enabled: bool = True):
        self.task_id = task_id
        self.name = name
        self.schedule_type = schedule_type  # daily, weekly, once
        self.schedule_time = schedule_time  # HH:MM format
        self.action = action  # produce_all, produce_youtube, produce_tiktok
        self.enabled = enabled
        self.last_run = None
        self.next_run = None
        self.calculate_next_run()
    
    def calculate_next_run(self):
        """Sonraki çalışma zamanını hesapla"""
        now = datetime.now()
        hour, minute = map(int, self.schedule_time.split(':'))
        
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if next_run <= now:
            if self.schedule_type == 'daily':
                next_run += timedelta(days=1)
            elif self.schedule_type == 'weekly':
                next_run += timedelta(weeks=1)
        
        self.next_run = next_run
    
    def should_run(self) -> bool:
        """Çalışma zamanı geldi mi?"""
        if not self.enabled:
            return False
        
        if self.next_run is None:
            self.calculate_next_run()
        
        return datetime.now() >= self.next_run
    
    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'name': self.name,
            'schedule_type': self.schedule_type,
            'schedule_time': self.schedule_time,
            'action': self.action,
            'enabled': self.enabled,
            'last_run': self.last_run,
            'next_run': self.next_run.isoformat() if self.next_run else None
        }


class Scheduler:
    """Görev zamanlayıcı"""
    
    def __init__(self, config_path: str = "config/scheduler.json"):
        self.config_path = Path(config_path)
        self.tasks: Dict[str, ScheduledTask] = {}
        self.callbacks: Dict[str, Callable] = {}
        self.running = False
        self.thread = None
        self.load_tasks()
    
    def load_tasks(self):
        """Görevleri yükle"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for task_data in data.get('tasks', []):
                    task = ScheduledTask(
                        task_data['task_id'],
                        task_data['name'],
                        task_data['schedule_type'],
                        task_data['schedule_time'],
                        task_data['action'],
                        task_data.get('enabled', True)
                    )
                    task.last_run = task_data.get('last_run')
                    self.tasks[task.task_id] = task
            except Exception as e:
                print(f"[Scheduler] Yükleme hatası: {e}")
        
        # Varsayılan görevler ekle
        if not self.tasks:
            self.add_default_tasks()
    
    def add_default_tasks(self):
        """Varsayılan görevleri ekle"""
        default_tasks = [
            ScheduledTask(
                'morning_production',
                'Sabah Üretimi',
                'daily',
                '08:00',
                'produce_all'
            ),
            ScheduledTask(
                'evening_production',
                'Akşam Üretimi',
                'daily',
                '20:00',
                'produce_all'
            )
        ]
        
        for task in default_tasks:
            self.tasks[task.task_id] = task
        
        self.save_tasks()
    
    def save_tasks(self):
        """Görevleri kaydet"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'tasks': [task.to_dict() for task in self.tasks.values()]
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Scheduler] Kaydetme hatası: {e}")
    
    def register_callback(self, action: str, callback: Callable):
        """Aksiyon için callback kaydet"""
        self.callbacks[action] = callback
    
    def add_task(self, name: str, schedule_type: str, schedule_time: str, 
                 action: str) -> str:
        """Yeni görev ekle"""
        task_id = f"task_{int(time.time())}"
        task = ScheduledTask(task_id, name, schedule_type, schedule_time, action)
        self.tasks[task_id] = task
        self.save_tasks()
        return task_id
    
    def remove_task(self, task_id: str) -> bool:
        """Görev sil"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.save_tasks()
            return True
        return False
    
    def toggle_task(self, task_id: str) -> bool:
        """Görev aç/kapat"""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = not self.tasks[task_id].enabled
            self.save_tasks()
            return self.tasks[task_id].enabled
        return False
    
    def start(self):
        """Zamanlayıcıyı başlat"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("[Scheduler] Zamanlayıcı başlatıldı")
    
    def stop(self):
        """Zamanlayıcıyı durdur"""
        self.running = False
    
    def _run_loop(self):
        """Ana döngü"""
        while self.running:
            try:
                for task in self.tasks.values():
                    if task.should_run():
                        self._execute_task(task)
                
                time.sleep(30)  # 30 saniyede bir kontrol et
            except Exception as e:
                print(f"[Scheduler] Döngü hatası: {e}")
                time.sleep(60)
    
    def _execute_task(self, task: ScheduledTask):
        """Görevi çalıştır"""
        print(f"[Scheduler] Görev çalıştırılıyor: {task.name}")
        
        if task.action in self.callbacks:
            try:
                self.callbacks[task.action]()
                task.last_run = datetime.now().isoformat()
                task.calculate_next_run()
                self.save_tasks()
            except Exception as e:
                print(f"[Scheduler] Görev hatası: {e}")
    
    def get_all_tasks(self) -> List[dict]:
        """Tüm görevleri getir"""
        return [task.to_dict() for task in self.tasks.values()]
    
    def get_next_run(self) -> str:
        """Sonraki çalışma zamanını getir"""
        upcoming = []
        for task in self.tasks.values():
            if task.enabled and task.next_run:
                upcoming.append((task.next_run, task.name))
        
        if upcoming:
            upcoming.sort()
            return f"{upcoming[0][1]} - {upcoming[0][0].strftime('%H:%M')}"
        return "Yok"


# Global instance
scheduler = Scheduler()
