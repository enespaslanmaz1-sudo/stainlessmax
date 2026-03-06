"""
History Video Producer - Specialized producer for Reddit History content
"""

import asyncio
import logging
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# Core modules
from .reddit_content_fetcher import RedditContentFetcher
from .gameplay_manager import GameplayManager
from .scenario_generator import ScenarioGenerator
from .tts_generator import TTSGenerator
from .video_assembler import VideoAssembler
from .unified_uploader import UnifiedUploader
from .warp_manager import WarpManager

class HistoryVideoProducer:
    """Orchestrates the creation of Viral History Videos"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Initialize modules
        self.reddit_fetcher = RedditContentFetcher()
        self.gameplay_mgr = GameplayManager()
        self.scenario_gen = ScenarioGenerator() # Uses Gemini
        self.tts_gen = TTSGenerator() # Will use Edge TTS
        self.video_assembler = VideoAssembler()
        self.uploader = UnifiedUploader()
        self.warp_mgr = WarpManager()
        
        # Output dizinleri - STRICT PROJECT STRUCTURE
        self.base_dir = Path(__file__).resolve().parent.parent
        import sys, os
        if sys.platform == 'darwin':
            self.output_dir = Path(os.path.expanduser('~/Movies/StainlessMax'))
        else:
            self.output_dir = self.base_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_daily_batch(self, count: int = 6):
        """Generates a batch of 6 videos for the day"""
        self.logger.info(f"📅 Starting Daily Batch Generation ({count} videos)...")
        
        # 0. Rotate IP (WARP)
        if self.warp_mgr.rotate_ip():
            self.logger.info("✅ IP Rotated successfully")
        else:
            self.logger.warning("⚠️ IP Rotation failed, continuing with current IP")

        # 1. Fetch Content
        stories = self.reddit_fetcher.select_best_stories(count)
        if not stories:
            self.logger.error("No stories found!")
            return
            
        generated_count = 0
        
        for i, story in enumerate(stories, 1):
            self.logger.info(f"🎬 Processing Story {i}/{count}: {story['title'][:30]}...")
            
            try:
                # 2. Process Story
                result = await self.produce_single_video(story)
                if result:
                    generated_count += 1
                    self.reddit_fetcher.save_used_id(story['id'])
                    
            except Exception as e:
                self.logger.error(f"Error processing story {story['id']}: {e}")
                import traceback
                traceback.print_exc()
                
        self.logger.info(f"✅ Batch Complete. Generated {generated_count}/{count} videos.")

    async def produce_single_video(self, story: Dict) -> Optional[Dict]:
        """Produces a single video from a Reddit story"""
        
        # 1. Generate Script (Gemini)
        # We need a specific prompt for History Style
        prompt_topic = f"A fascinating fact/story about: {story['title']}\nContent: {story['content']}"
        
        self.logger.info("writing script...")
        scenario = self.scenario_gen.generate_viral_scenario(
            topic=prompt_topic,
            niche="history",
            duration=45, # Target 45s avg
            channel_name="Reddit History"
        )
        
        if not scenario:
            self.logger.error("Failed to generate scenario")
            return None
            
        # 2. Audio (TTS) - Edge TTS (Christopher)
        self.logger.info("Generating TTS...")
        # Force specific voice for history
        # Note: TTSGenerator might need a patch to accept voice arg if not present,
        # but standard is usually handled in config. Let's assume standard for now or patch tts_gen.
        
        audio_path, srt_path = await self.tts_gen.create_narration_for_scenario(
            scenario=scenario,
            voice="en-US-ChristopherNeural" # Pass voice if supported, else default
        )
        
        if not audio_path:
            return None

        # Verify Duration (35-55s)
        try:
            import ffmpeg
            probe = ffmpeg.probe(str(audio_path))
            audio_dur = float(probe['format']['duration'])
            
            if audio_dur < 30 or audio_dur > 59:
                self.logger.warning(f"Audio duration {audio_dur}s out of ideal range (35-55s)")
        except Exception as e:
            self.logger.warning(f"Failed to check audio duration: {e}")
            
        # 3. Visuals (Gameplay)
        self.logger.info("Extracting Gameplay Background...")
        bg_video = self.gameplay_mgr.get_random_segment(duration=audio_dur)
        
        if not bg_video:
            self.logger.error("Failed to get background video")
            return None
            
        # 4. Assembly
        self.logger.info("Assembling Video...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"history_{story['id']}_{timestamp}.mp4"
        
        # Custom mix with music
        # We need to manually handle music mixing since VideoAssembler mixes randomly
        # Use dark_ambient_1.mp3 if available
        # Actually, VideoAssembler has _mix_audio_with_ducking which picks random music. 
        # We want specific music.
        
        # Let's override the music dir temporarily or ensure our music is there.
        # assets/music/dark_ambient_1.mp3 exists.
        
        final_video = self.video_assembler.assemble_video(
            clips=[bg_video], # Use background as the "clip"
            audio_path=audio_path,
            scenario=scenario,
            output_filename=output_filename,
            add_subtitles=True, # We WANT subtitles for this agent
            external_srt_path=srt_path
        )
        
        if final_video:
            self.logger.info(f"✅ Video Ready: {final_video}")
            
            # Metadata
            result = {
                "video_path": str(final_video),
                "title": story['title'],
                "scenario": scenario,
                "story_id": story['id'],
                "created_at": datetime.now().isoformat()
            }
            
            # Save JSON sidecar
            json_path = final_video.with_suffix(".json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # CSV Log
            self._log_to_csv(
                video_id=story['id'],
                subreddit=story.get('subreddit', 'unknown'),
                hook=scenario.get('hook', 'N/A'),
                bg_segment=str(bg_video.name) if bg_video else "N/A",
                viral_score=scenario.get('estimated_engagement', 0),
                status="SCHEDULED"
            )
                
            return result
            
        return None

    def _log_to_csv(self, video_id, subreddit, hook, bg_segment, viral_score, status):
        """Logs production details to CSV"""
        csv_file = Path("production_history.csv")
        file_exists = csv_file.exists()
        
        try:
            import csv
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        "timestamp", "video_id", "reddit_source_sub", 
                        "hook_text", "background_segment", 
                        "predicted_viral_score", "status"
                    ])
                
                # Write data
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    video_id,
                    subreddit,
                    hook,
                    bg_segment,
                    viral_score,
                    status
                ])
                self.logger.info(f"📝 Logged to CSV: {video_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to log to CSV: {e}")

if __name__ == "__main__":
    import sys
    # sys.path hack for testing
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        producer = HistoryVideoProducer()
        # Test fetch
        stories = producer.reddit_fetcher.select_best_stories(1)
        if stories:
             await producer.produce_single_video(stories[0])
             
    asyncio.run(test())
