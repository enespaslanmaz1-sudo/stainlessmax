"""
History Agent Scheduler - Daily Loop & Upload Scheduling (AsyncIO version)
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

from .history_video_producer import HistoryVideoProducer
from .unified_uploader import UnifiedUploader

class DailyHistoryScheduler:
    """Schedules the daily history video workflow using asyncio"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.producer = HistoryVideoProducer()
        self.uploader = UnifiedUploader()
        self.is_running = False
        
        # Scheduling Slots (Time objects)
        self.upload_slots = [
            dtime(15, 0), dtime(17, 0), dtime(19, 0), 
            dtime(21, 0), dtime(23, 0), dtime(1, 0)
        ]
        
        # Batch generation time
        self.batch_time = dtime(2, 0)

    async def start(self):
        """Starts the scheduler loop"""
        self.is_running = True
        self.logger.info("⏳ History Agent Scheduler Started (AsyncIO)...")
        
        # Initial run immediate
        self.logger.info("🆕 Initial run: Generating daily batch...")
        # Run in background task to not block loop
        asyncio.create_task(self.producer.generate_daily_batch(6))
        
        while self.is_running:
            now = datetime.now()
            
            # Check for batch generation
            # Implementation simplifiction: Just check every minute
            
            # Check for upload slots
            # This is a bit complex to implement perfectly with just sleep(60)
            # But sufficient for this agent.
            
            current_time = now.time()
            
            # Simple check: match hour and minute
            # Note: This might trigger multiple times if execution is fast, so we need a "last_run" check
            # Or just sleep 60s
            
            # Check Batch Generation (02:00)
            if current_time.hour == 2 and current_time.minute == 0:
                self.logger.info("🕑 Daily Batch Time Reached")
                asyncio.create_task(self.producer.generate_daily_batch(6))
                
            # Check Upload Slots
            for slot in self.upload_slots:
                if current_time.hour == slot.hour and current_time.minute == slot.minute:
                    self.logger.info(f"⏰ Upload Slot Reached: {slot}")
                    asyncio.create_task(self.upload_next_video(slot))
            
            # Wait for next minute
            await asyncio.sleep(60)

    async def upload_next_video(self, slot_time):
        """Uploads the next available video"""
        self.logger.info(f"🚀 Processing Upload Slot: {slot_time}")
        
        # Find a ready video
        video_dir = Path("videos/history")
        
        # Get all mp4s
        today_str = datetime.now().strftime("%Y%m%d")
        candidates = list(video_dir.glob(f"history_*_*.mp4"))
        
        # Filter out uploaded
        candidates = sorted([f for f in candidates if "uploaded" not in f.name])
        
        if not candidates:
            self.logger.warning(f"❌ No videos found for slot {slot_time}")
            return
            
        video_to_upload = candidates[0]
        self.logger.info(f"📤 Uploading: {video_to_upload.name}")
        
        # Metadata logic (reuse from previous)
        json_file = video_to_upload.with_suffix(".json")
        title = "Daily History Fact"
        desc = "#history #facts"
        
        if json_file.exists():
             try:
                 with open(json_file, 'r', encoding='utf-8') as f:
                     meta = json.load(f)
                     title = meta.get("title", title)
                     scenario = meta.get("scenario", {})
                     desc = scenario.get("description", desc)
             except Exception as e:
                 self.logger.error(f"Error reading metadata: {e}")
        
        # Upload
        result = self.uploader.upload_to_account(
            account_id="reddithistoryss", 
            video_path=video_to_upload,
            title=title,
            description=desc,
            tags=["#history", "#fyp", "#interesting"]
        )
        
        if result.get("success"):
            self.logger.info(f"✅ Upload Successful: {result.get('video_url')}")
            # Rename unique
            new_name = video_to_upload.with_suffix(f".uploaded_{int(time.time())}.mp4")
            try:
                video_to_upload.rename(new_name)
            except Exception as e:
                self.logger.error(f"Error renaming file: {e}")
        else:
            self.logger.error(f"❌ Upload Failed: {result.get('error')}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = DailyHistoryScheduler()
    asyncio.run(scheduler.start())
