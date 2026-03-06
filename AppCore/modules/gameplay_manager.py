"""
Gameplay Manager - Manages gameplay background assets
"""

import ffmpeg
import logging
import random
import json
import os
from pathlib import Path
from typing import Optional, Tuple

class GameplayManager:
    """Manages background gameplay footage"""
    
    def __init__(self, assets_dir: str = "assets/gameplay"):
        self.logger = logging.getLogger(__name__)
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path("temp_clips")
        self.temp_dir.mkdir(exist_ok=True)
        
        self.db_path = Path("config/gameplay_usage.json")
        self.usage_db = self._load_db()

    def _load_db(self) -> dict:
        if not self.db_path.exists():
            return {}
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_db(self):
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.usage_db, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving DB: {e}")

    def get_random_segment(self, duration: float = 60.0) -> Optional[Path]:
        """
        Extracts a random 9:16 segment from gameplay footage.
        Returns path to the extracted segment.
        """
        # 1. Find all video files
        video_files = list(self.assets_dir.glob("*.mp4")) + list(self.assets_dir.glob("*.mkv"))
        if not video_files:
            self.logger.error(f"No gameplay files found in {self.assets_dir}")
            return None
            
        # 2. Select a file
        # Try to pick one deemed "compatible" or random
        selected_file = random.choice(video_files)
        
        try:
            # 3. Get video duration
            probe = ffmpeg.probe(str(selected_file))
            file_duration = float(probe['format']['duration'])
            
            if file_duration < duration:
                self.logger.warning(f"File {selected_file.name} is too short ({file_duration}s < {duration}s)")
                return None # Or loop it
                
            # 4. Pick random start time
            # Max start time = duration - desired_duration
            max_start = file_duration - duration
            
            # Smart selection: Try to avoid recently used segments (Logic TBA)
            # For now: Random
            start_time = random.uniform(0, max_start)
            
            output_filename = f"bg_{selected_file.stem}_{int(start_time)}_{int(duration)}.mp4"
            output_path = self.temp_dir / output_filename
            
            if output_path.exists():
                return output_path
                
            self.logger.info(f"Extracting {duration}s from {selected_file.name} at {start_time:.1f}s")
            
            # 5. Extract and Crop to 9:16
            # Use ffmpeg to cut and crop
            # Crop logic: w=ih*(9/16), h=ih, x=(iw-ow)/2, y=0
            
            stream = ffmpeg.input(str(selected_file), ss=start_time, t=duration)
            stream = ffmpeg.filter(stream, 'crop', 'ih*(9/16)', 'ih', '(iw-ow)/2', '0')
            stream = ffmpeg.filter(stream, 'scale', 1080, 1920) # Ensure 1080x1920
            
            # Remove audio from background
            stream = ffmpeg.output(stream, str(output_path), an=None, c='libx264', preset='ultrafast', crf=23)
            
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Error processing gameplay: {e}")
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = GameplayManager()
    path = mgr.get_random_segment(10)
    print(f"Segment: {path}")
