"""
Video Preview - GUI'de Video Oynatma
"""

import os
from pathlib import Path
from typing import Optional


class VideoPreview:
    """Video önizleme yöneticisi"""
    
    def __init__(self):
        self.current_video = None
        self.preview_window = None
    
    def open_video(self, video_path: str) -> bool:
        """Varsayılan player ile video aç"""
        try:
            path = Path(video_path)
            if not path.exists():
                print(f"[Preview] Video bulunamadı: {video_path}")
                return False
            
            self.current_video = str(path)
            
            # Windows'ta varsayılan player ile aç
            if os.name == 'nt':
                os.startfile(self.current_video)
            else:
                # Linux/Mac
                import subprocess
                subprocess.call(['open', self.current_video])
            
            return True
            
        except Exception as e:
            print(f"[Preview] Açma hatası: {e}")
            return False
    
    def get_video_info(self, video_path: str) -> dict:
        """Video bilgilerini al"""
        try:
            from moviepy import VideoFileClip
            
            with VideoFileClip(video_path) as clip:
                return {
                    'duration': int(clip.duration),
                    'fps': clip.fps,
                    'size': clip.size,
                    'file_size_mb': round(Path(video_path).stat().st_size / (1024 * 1024), 2)
                }
        except Exception as e:
            print(f"[Preview] Bilgi alma hatası: {e}")
            return {}
    
    def generate_thumbnail(self, video_path: str, time_seconds: int = 5) -> Optional[str]:
        """Video'dan thumbnail oluştur"""
        try:
            from moviepy import VideoFileClip
            
            video = VideoFileClip(video_path)
            frame = video.get_frame(time_seconds)
            
            from PIL import Image
            img = Image.fromarray(frame)
            
            thumbnail_path = str(Path(video_path).with_suffix('.jpg'))
            img.save(thumbnail_path)
            
            video.close()
            
            return thumbnail_path
            
        except Exception as e:
            print(f"[Preview] Thumbnail hatası: {e}")
            return None
    
    def extract_frames(self, video_path: str, num_frames: int = 5) -> list:
        """Videodan kareler çıkar"""
        try:
            from moviepy import VideoFileClip
            
            video = VideoFileClip(video_path)
            duration = video.duration
            interval = duration / (num_frames + 1)
            
            frames = []
            for i in range(1, num_frames + 1):
                time = interval * i
                frame = video.get_frame(time)
                frames.append({
                    'time': time,
                    'frame': frame
                })
            
            video.close()
            return frames
            
        except Exception as e:
            print(f"[Preview] Kare çıkarma hatası: {e}")
            return []


# Global instance
video_preview = VideoPreview()
