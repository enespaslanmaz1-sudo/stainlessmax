"""
Video Assembler - FFmpeg ile Viral Video Birleştirme
Klipler + Audio + Altyazılar → Final 1080x1920 Video
ÇÖZÜM: SRT dosyasını C:/stainless_temp klasörüne taşıma + Path Formatı Düzeltme + Boş SRT Koruması
"""

import ffmpeg
import json
import logging
import os
import random
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import subprocess
import sys

# Windows'ta CMD penceresi açılmasını engelle
_NO_WINDOW = 0
if sys.platform == 'win32':
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW

class VideoAssembler:
    """FFmpeg kullanarak klipleri birleştirip viral video oluştur"""
    
    def __init__(self, output_dir: str = "videos"):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Asset dizinleri
        self.sfx_dir = Path("assets") / "sound_effects"
        self.music_dir = Path("assets") / "music"
        
        for d in [self.sfx_dir, self.music_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # Video özellikleri
        self.width = 1080
        self.height = 1920
        self.fps = 30
        
        # GPU ACCELERATION CHECK (Dinamik önceliklendirme)
        try:
            import subprocess
            enc_check = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, creationflags=_NO_WINDOW)
            encoders = enc_check.stdout
            
            if 'h264_nvenc' in encoders:
                self.video_codec = "h264_nvenc"
                self.preset = "p1"
                self.logger.info("🚀 NVIDIA GPU Acceleration (NVENC) ALGILANDI")
            elif 'h264_qsv' in encoders:
                # Testlerde QSV'nin çalıştığı doğrulandı
                self.video_codec = "h264_qsv"
                self.preset = "veryfast"
                self.logger.info("🚀 Intel GPU Acceleration (QSV) ALGILANDI (Öncelikli)")
            elif 'h264_amf' in encoders:
                self.video_codec = "h264_amf"
                self.preset = "speed"
                self.logger.info("🚀 AMD GPU Acceleration (AMF) ALGILANDI")
            else:
                self.video_codec = "libx264"
                self.preset = "ultrafast"
                self.logger.info("💻 CPU Encoding kullanılıyor (Uyumlu GPU bulunamadı)")
        except Exception as e:
            self.logger.warning(f"FFmpeg encoder check failed: {e}")
            self.video_codec = "libx264"
            self.preset = "ultrafast"

        self.audio_codec = "aac"
        self.crf = 28 # CPU mode quality
 
    
    def _get_codec_params(self) -> dict:
        """Get codec-specific parameters for FFmpeg"""
        params = {
            'vcodec': self.video_codec,
            'acodec': self.audio_codec
        }
        
        if self.video_codec == "h264_nvenc":
            params.update({
                'cq': 24,
                'rc': 'vbr',
                'preset': 'p1',
                'pix_fmt': 'nv12'
            })
        elif self.video_codec == "h264_amf":
            params.update({
                'usage': 'transcoding',
                'quality': 'speed',
                'rc': 'cqp',
                'qp_i': 24,
                'qp_p': 24,
                'pix_fmt': 'nv12'
            })
        elif self.video_codec == "h264_qsv":
            params.update({
                'global_quality': 24,
                'preset': 'veryfast',
                # QSV için nv12 en uyumlu formattır
                'pix_fmt': 'nv12'
            })
        else:
            params.update({
                'crf': 22, # Kaliteyi artır (Düşük kalite uyarısı için)
                'preset': self.preset,
                'tune': 'fastdecode',
                'pix_fmt': 'yuv420p'
            })
        return params

    def _get_music_for_topic(self, topic: str) -> Optional[Path]:
        """Konuya göre müzik türü seç"""
        topic = topic.lower()
        
        # Tür eşleşmeleri
        genres = {
            "horror": ["korku", "cin", "ruh", "paranormal", "horror", "creepy", "scary", "ölüm", "death"],
            "sad": ["üzücü", "sad", "emotional", "dram", "drama", "ayrılık", "aşk", "love", "yalnız", "alone"],
            "upbeat": ["eğlenceli", "mutlu", "funny", "happy", "hızlı", "fast", "komik", "comedy"]
        }
        
        selected_genre = "upbeat"  # Varsayılan
        for genre, keywords in genres.items():
            if any(k in topic for k in keywords):
                selected_genre = genre
                break
        
        genre_dir = self.music_dir / selected_genre
        if not genre_dir.exists():
            return None
            
        music_files = list(genre_dir.glob("*.mp3")) + list(genre_dir.glob("*.wav"))
        if not music_files:
            return None
            
        return random.choice(music_files)

    def _mix_audio_with_ducking(self, tts_path: Path, output_path: Path, topic: str = "", music_path_override: Optional[Path] = None, target_duration: float = 60.0) -> Path:
        """
        FFmpeg sidechaincompress kullanarak profesyonel ses miksajı (ducking)
        """
        try:
            music_path = music_path_override if music_path_override else self._get_music_for_topic(topic)
            
            if not music_path or not music_path.exists():
                self.logger.warning("Uygun müzik bulunamadı veya geçersiz yol, sadece TTS kullanılacak.")
                return tts_path
                
            self.logger.info(f"🎵 Profesyonel Ses Miksajı (Ducking) -> {music_path.name}")
            
            import subprocess
            cmd = [
                'ffmpeg', '-i', str(tts_path), '-stream_loop', '-1', '-i', str(music_path),
                '-filter_complex', 
                '[1:a]volume=0.25[music];' # Müziği biraz kıs
                '[music][0:a]sidechaincompress=threshold=0.1:ratio=20:attack=100:release=1000[bg];' # Ducking uygula
                f'[bg][0:a]amix=inputs=2:duration=longest:weights=1 1.5[out]', # Mix (Longest to fill duration)
                '-t', str(target_duration), # FORCE TOTAL DURATION
                '-acodec', 'aac', '-y', str(output_path)
            ]
            
            process = subprocess.run(cmd, capture_output=True, check=True, text=True, creationflags=_NO_WINDOW)
            self.logger.info("✅ Ses miksajı (Sync & Ducking) tamamlandı.")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Audio ducking hatası: {e}")
            return tts_path

    def assemble_video(self, clips: List[Path], audio_path: Path, scenario: Dict, 
                       output_filename: str, add_subtitles: bool = False, 
                       external_srt_path: Optional[Path] = None,
                       logo_path: Optional[Path] = None,
                       topic: str = "",
                       aspect_ratio: str = "9:16",
                       duration: int = 60,
                       music_path_override: Optional[Path] = None) -> Optional[Path]:
        # Geçici klasör ve dosya değişkenlerini tanımla (Finally bloğu için)
        safe_temp_dir = Path("C:/stainless_temp")
        safe_srt_file = None
        
        try:
            # Set dimensions based on aspect ratio
            if aspect_ratio == "16:9":
                self.width, self.height = 1920, 1080
            else:
                self.width, self.height = 1080, 1920
                
            output_path = self.output_dir / output_filename
            self.logger.info(f"🎬 Video birleştirme başladı: {output_filename} ({aspect_ratio}, {duration}s)")
            
            # 1. Ses Süresini Al (Limit kontrolü için)
            total_duration = float(duration)
            
            # 2. Müzik Miksajı (Topic bazlı + Sync)
            mixed_audio_output = audio_path.parent / f"mixed_{audio_path.name}"
            mixed_audio_path = self._mix_audio_with_ducking(audio_path, mixed_audio_output, topic, music_path_override, total_duration)
            prepared_clips = self._prepare_clips(clips, scenario)
            
            if not prepared_clips:
                self.logger.error("Klipler hazırlanamadı")
                return None
            
            concat_file = self._create_concat_file(prepared_clips)
            
            self.logger.info("FFmpeg ile montajlanıyor...")
            
            video_stream = (
                ffmpeg
                .input(str(concat_file), format='concat', safe=0, stream_loop=20)
                .video
                .filter('scale', self.width, self.height, force_original_aspect_ratio='decrease')
                .filter('pad', self.width, self.height, '(ow-iw)/2', '(oh-ih)/2')
            )
            
            audio_stream = ffmpeg.input(str(mixed_audio_path)).audio
            
            # --- LIGHTNING-FAST ANTI-DETECTION (ÖZGÜNLEŞTİRME) ---
            # Hız kaybı olmadan TikTok algoritmasını şaşırtacak filtreler
            import random
            
            # 1. Rastgele Aynalama (Mirroring) - %50 şans
            mirror = random.choice([True, False])
            if mirror:
                self.logger.info("🔄 Anti-Detection: Video aynalandı (hflip)")
                video_stream = video_stream.filter('hflip')
            
            # 2. Mikro Hız Değişimi (1.01x) - Hash'i tamamen değiştirir
            # setpts=0.99*PTS -> %1 hızlanma
            # Mikro Hız Değişimi uygulandı (Anti-Detection)
            video_stream = video_stream.filter('setpts', '0.99*PTS')
            
            # --- SUBTITLES (HARDCODED) ---
            if add_subtitles and external_srt_path and external_srt_path.exists():
                self.logger.info(f"📝 Altyazı ekleniyor (Burn-in): {external_srt_path}")
                # Windows path fix for FFmpeg filter
                srt_path_str = str(external_srt_path).replace("\\", "/").replace(":", "\\\\:")
                
                # Style adjustment based on resolution
                font_size = 16 if self.width == 1080 else 24
                margin_v = 250 if self.width == 1080 else 100
                
                style = f"Fontname=Arial,Fontsize={font_size},PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=3,Shadow=0,Alignment=2,MarginV={margin_v},Bold=1"
                
                video_stream = video_stream.filter('subtitles', srt_path_str, force_style=style)

            # --- LOGO OVERLAY (SUBTLE) ---
            if logo_path and logo_path.exists():
                self.logger.info(f"🎨 Logo ekleniyor (Sol Üst): {logo_path}")
                logo_input = ffmpeg.input(str(logo_path)).filter('scale', 100, -1)
                video_stream = ffmpeg.overlay(video_stream, logo_input, x=40, y=40, eof_action='repeat')

            import uuid
            unique_id = str(uuid.uuid4())[:8]

            # GPU/Codec Params
            ffmpeg_params = self._get_codec_params()
            ffmpeg_params.update({
                'metadata': f'comment=StainlessMax_{unique_id}',
                'r': '30',
                't': str(duration) # DYNAMIC DURATION
            })

            # --- FFmpeg Execution with Robust Fallback ---
            def run_ffmpeg(params, timeout_sec=720):
                # params içinde vcodec zaten var
                # KESİN SÜRE KONTROLÜ (t)
                if 't' not in params:
                    params['t'] = str(duration)
                
                output = ffmpeg.output(
                    video_stream,
                    audio_stream,
                    str(output_path),
                    threads=0, # Auto-threads for max performance
                    **params
                )
                cmd = ffmpeg.compile(output, overwrite_output=True)
                codec_name = params.get('vcodec', 'unknown')
                self.logger.info(f"🎬 FFmpeg başlatılıyor... (Codec: {codec_name}, Timeout: {timeout_sec}s, Duration: {params['t']}s)")
                return subprocess.run(cmd, capture_output=True, timeout=timeout_sec, text=True, creationflags=_NO_WINDOW)

            try:
                import subprocess
                process = run_ffmpeg(ffmpeg_params)
                
                if process.returncode != 0:
                    raise Exception(f"FFmpeg Error: {process.stderr[:200]}")

            except (Exception, subprocess.TimeoutExpired) as e:
                # NVENC hata verirse QSV dene (User'da ikisi de olabilir)
                if self.video_codec == "h264_nvenc":
                    self.logger.warning(f"⚠️ NVENC başarısız oldu, QSV deneniyor...")
                    self.video_codec = "h264_qsv"
                    ffmpeg_params = self._get_codec_params()
                    ffmpeg_params.update({'metadata': f'comment=StainlessMax_{unique_id}', 'r': '30', 't': str(duration)})
                    try:
                        process = run_ffmpeg(ffmpeg_params)
                        if process.returncode == 0: return output_path
                    except Exception as fallback_err: 
                        self.logger.warning(f"QSV Fallback also failed: {fallback_err}")

                if self.video_codec != "libx264":
                    self.logger.warning(f"⚠️ Donanım hızlandırma başarısız oldu: {e}")
                    self.logger.info("🔄 CPU moduna (libx264) geri dönülüyor...")
                    
                    # Fallback parameters for CPU
                    cpu_params = {
                        'vcodec': 'libx264',
                        'acodec': self.audio_codec,
                        'pix_fmt': 'yuv420p',
                        'crf': 28,
                        'preset': 'ultrafast',
                        'tune': 'fastdecode',
                        'metadata': f'comment=StainlessMax_{unique_id}',
                        'r': '30',
                        't': str(duration)
                    }
                    
                    # Re-run with CPU (More timeout for safety)
                    process = run_ffmpeg(cpu_params, timeout_sec=900)
                    if process.returncode != 0:
                         raise Exception(f"CPU Fallback da başarısız: {process.stderr[:200]}")
                else:
                    raise e

            self._cleanup_temp_files([concat_file, mixed_audio_path])
            
            if output_path.exists():
                size_mb = output_path.stat().st_size / (1024 * 1024)
                self.logger.info(f"✅ Video oluşturuldu: {output_path} ({size_mb:.1f} MB)")
                return output_path
            
            return None
            
        except Exception as e:
            self.logger.error(f"Video assembly hatası: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            # Temizlik: Güvenli bölgedeki dosyayı ve klasörü sil
            if safe_srt_file and safe_srt_file.exists():
                try:
                    safe_srt_file.unlink()
                    self.logger.info(f"🧹 Temizlendi: {safe_srt_file}")
                except Exception as e:
                    self.logger.warning(f"Temizlik hatası (srt): {e}")
            
            if safe_temp_dir.exists():
                try:
                    shutil.rmtree(safe_temp_dir)
                    self.logger.info(f"🧹 Temizlendi: {safe_temp_dir}")
                except Exception as e:
                    self.logger.warning(f"Temizlik hatası (dir): {e}")
    
    def _prepare_clips(self, clips: List[Path], scenario: Dict) -> List[Path]:
        prepared = []
        temp_dir = Path("temp_clips")
        temp_dir.mkdir(exist_ok=True)
        scenes = scenario.get("scenes", [])
        
        # Ensure we have clips
        if not clips:
            self.logger.error("No clips provided for preparation")
            return []

        for i in range(len(scenes)):
            # Klip döngüsü (Eğer klip azsa başa dön)
            if not clips: break
            clip_path = clips[i % len(clips)]
            
            # Verify input clip exists and has content
            if not clip_path.exists() or clip_path.stat().st_size == 0:
                self.logger.warning(f"Input clip missing or empty: {clip_path}")
                continue

            scene_duration = scenes[i].get("duration", 5) # Default 5s
            output_clip = temp_dir / f"prepared_{i}.mp4"
            
            try:
                # KESİNLİKLE RASTGELE BAŞLANGIÇ (Anti-Detection)
                import subprocess
                prob = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(clip_path)], capture_output=True, text=True, creationflags=_NO_WINDOW)
                
                try:
                    duration_in = float(prob.stdout.strip())
                    max_start = max(0, duration_in - scene_duration - 5)
                    start_time = random.uniform(0, max_start) if max_start > 0 else 0
                    self.logger.info(f"🎞️ Offset: {clip_path.name} -> {start_time:.1f}s start")
                except:
                    start_time = 0
                    self.logger.warning(f"Süre alınamadı, ss=0 kullanılacak: {clip_path}")

                stream = ffmpeg.input(str(clip_path), ss=start_time)
                # Klipleri hazırlarken CPU kullanmak (libx264) daha kararlıdır.
                # Asıl hız kazancı final montajda Hardware kullanılarak alınacaktır.
                prepare_params = {
                    'vcodec': 'libx264',
                    'acodec': self.audio_codec,
                    't': scene_duration,
                    'vf': f'scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                    'r': self.fps,
                    'preset': 'ultrafast',
                    'pix_fmt': 'yuv420p'
                }

                stream = ffmpeg.output(
                    stream, 
                    str(output_clip), 
                    **prepare_params
                )
                
                # Timeout ile çalıştır (max 60 saniye per clip)
                import subprocess
                cmd = ffmpeg.compile(stream, overwrite_output=True)
                
                try:
                    process = subprocess.run(cmd, capture_output=True, timeout=60, text=True, creationflags=_NO_WINDOW)
                    
                    if process.returncode != 0:
                        self.logger.warning(f"❌ Klip {i} FFmpeg hatası: {process.stderr[:500]}")
                        print(f"DEBUG FFmpeg Error Clip {i}: {process.stderr[:500]}")
                        continue

                except subprocess.TimeoutExpired:
                    self.logger.error(f"Klip {i} timeout (60s aşıldı)")
                    continue
                
                # Verify output integrity
                if output_clip.exists():
                    file_size = output_clip.stat().st_size
                    if file_size > 1000:  # Min 1KB
                        # Additional check: Try to probe the file
                        try:
                            probe = ffmpeg.probe(str(output_clip))
                            if probe and 'streams' in probe and len(probe['streams']) > 0:
                                prepared.append(output_clip)
                                self.logger.info(f"✅ Klip {i} hazır: {output_clip.name} ({file_size / 1024:.1f} KB)")
                            else:
                                self.logger.warning(f"Prepared clip has no valid streams: {output_clip}")
                                output_clip.unlink(missing_ok=True)
                        except Exception as probe_err:
                            self.logger.warning(f"Prepared clip probe failed: {output_clip} - {probe_err}")
                            output_clip.unlink(missing_ok=True)
                    else:
                        self.logger.warning(f"Prepared clip too small ({file_size} bytes): {output_clip}")
                        output_clip.unlink(missing_ok=True)
                else:
                    self.logger.warning(f"Prepared clip not created: {output_clip}")
                    
            except Exception as e:
                self.logger.warning(f"Klip {i} hazırlanamadı: {e}")
                continue
                
        return prepared
    
    def _create_concat_file(self, clips: List[Path]) -> Path:
        concat_path = Path("temp_concat.txt")
        with open(concat_path, 'w', encoding='utf-8') as f:
            for clip in clips:
                safe_path = str(clip.absolute()).replace("\\", "/")
                f.write(f"file '{safe_path}'\n")
        return concat_path
    
    def _create_subtitles(self, scenario: Dict, audio_path: Path) -> Optional[Path]:
        try:
            # ===== DEBUG BAŞLANGIÇ =====
            self.logger.info("=" * 60)
            self.logger.info("🔍 _create_subtitles METODU ÇAĞRILDI")
            self.logger.info(f"📋 Scenario Keys: {list(scenario.keys())}")
            self.logger.info(f"📝 Hook Değeri: '{scenario.get('hook', 'YOK')}'")
            self.logger.info(f"📊 Sahne Sayısı: {len(scenario.get('scenes', []))}")
            
            if scenario.get('scenes'):
                for i, scene in enumerate(scenario['scenes'][:3], 1):  # İlk 3 sahne
                    self.logger.info(f"🎬 Sahne {i} Keys: {list(scene.keys())}")
                    self.logger.info(f"   İçerik: {json.dumps(scene, ensure_ascii=False)[:200]}")
            self.logger.info("=" * 60)
            # ===== DEBUG BİTİŞ =====
            
            srt_path = Path("temp_subtitles.srt")
            scenes = scenario.get("scenes", [])
            
            # Tüm metinleri topla
            all_texts = []
            
            # Hook varsa ekle
            if "hook" in scenario and scenario.get("hook"):
                hook_text = str(scenario["hook"]).strip()
                if hook_text:
                    all_texts.append({
                        "start": 0,
                        "duration": 3,
                        "text": hook_text
                    })
            
            # Sahneleri ekle
            current_time = 3 if all_texts else 0
            for idx, scene in enumerate(scenes, 1):
                duration = float(scene.get("duration", 10))
                
                # Narration'ı bul - GENİŞLETİLMİŞ ARAMA
                narration = None
                
                # 1. Standart alanlar
                for key in ["narration", "text", "description", "script", "voice_over", "speech"]:
                    if key in scene and scene[key]:
                        narration = scene[key]
                        break
                
                # 2. Eğer hala bulunamadıysa, tüm string değerleri kontrol et
                if not narration:
                    for key, value in scene.items():
                        if isinstance(value, str) and len(value) > 10:  # 10 karakterden uzun string
                            narration = value
                            self.logger.info(f"⚠️ Narration '{key}' alanında bulundu (non-standard)")
                            break
                
                if narration:
                    text = str(narration).strip()
                    
                    # --- TEXT WRAPPING FIX ---
                    # Çok uzun satırları (örn 40 karakterden fazla) böl
                    words = text.split()
                    wrapped_lines = []
                    current_line = []
                    current_len = 0
                    
                    for word in words:
                        if current_len + len(word) > 40: # Max karakter
                            wrapped_lines.append(" ".join(current_line))
                            current_line = [word]
                            current_len = len(word)
                        else:
                            current_line.append(word)
                            current_len += len(word) + 1
                    
                    if current_line:
                        wrapped_lines.append(" ".join(current_line))
                        
                    final_text = "\n".join(wrapped_lines)
                    # -------------------------

                    if final_text:
                        all_texts.append({
                            "start": current_time,
                            "duration": duration,
                            "text": final_text
                        })
                        self.logger.info(f"✅ Sahne {idx} eklendi: {final_text[:50]}...")
                else:
                    self.logger.warning(f"⚠️ Sahne {idx} için narration bulunamadı! Keys: {list(scene.keys())}")
                
                current_time += duration
            
            # Fallback: Eğer hala boşsa, scenario başlığını kullan
            if not all_texts and "title" in scenario:
                all_texts.append({
                    "start": 0,
                    "duration": 5,
                    "text": scenario["title"]
                })
            
            # Eğer hala boşsa, uyarı ver
            if not all_texts:
                self.logger.warning("❌ Altyazı için metin bulunamadı!")
                self.logger.warning(f"Scenario yapısı: {json.dumps(scenario, indent=2, ensure_ascii=False)[:500]}...")
                return None
            
            # SRT dosyasını yaz
            with open(srt_path, 'w', encoding='utf-8') as f:
                for idx, item in enumerate(all_texts, start=1):
                    start_ms = int(item["start"] * 1000)
                    end_ms = int((item["start"] + item["duration"]) * 1000)
                    
                    start_srt = self._ms_to_srt_time(start_ms)
                    end_srt = self._ms_to_srt_time(end_ms)
                    
                    f.write(f"{idx}\n")
                    f.write(f"{start_srt} --> {end_srt}\n")
                    f.write(f"{item['text']}\n\n")
            
            # Doğrulama
            if srt_path.exists():
                size = srt_path.stat().st_size
                self.logger.info(f"✅ Altyazı oluşturuldu: {srt_path} ({size} bytes, {len(all_texts)} satır)")
                
                # İlk birkaç satırı logla (debug)
                with open(srt_path, 'r', encoding='utf-8') as f:
                    preview = f.read(300)
                    self.logger.info(f"📄 SRT Önizleme:\n{preview}")
                
                return srt_path
            
            return None
                
        except Exception as e:
            self.logger.error(f"Altyazı oluşturma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _convert_to_reddit_style_srt(self, input_srt: Path) -> Path:
        """VideoAssembler Extension: Standart SRT'yi Reddit Stili (Sayfalı Akış) SRT'ye çevir"""
        try:
            output_srt = input_srt.parent / f"reddit_paged_{input_srt.name}"
            
            with open(input_srt, 'r', encoding='utf-8') as f:
                content = f.read().replace('\r\n', '\n')
            
            # Daha sağlam SRT Parser (Index, Zaman, Text)
            import re
            # Segmentleri bul: Sayı + Zaman + Metin (Bir sonraki sayıya kadar)
            segments = []
            raw_segments = re.split(r'\n\n+', content.strip())
            
            for seg in raw_segments:
                lines = seg.strip().split('\n')
                if len(lines) >= 3:
                    time_line = lines[1]
                    if ' --> ' in time_line:
                        times = time_line.split(' --> ')
                        start = times[0].strip()
                        end = times[1].strip()
                        text = " ".join(lines[2:]).strip()
                        segments.append({'start': start, 'end': end, 'text': text})
            
            if not segments:
                self.logger.warning(f"⚠️ SRT parçalanamadı: {input_srt}")
                return input_srt
            
            self.logger.info(f"🔍 SRT {len(segments)} parça olarak yüklendi. Reddit stiline çevriliyor...")
            
            new_segments = []
            page_buffer = []
            max_lines = 10 
            
            for seg in segments:
                clean_text = seg['text']
                
                # Mevcut sayfadaki satır sayısını kabaca hesapla
                visual_lines = 1 + len(clean_text) // 50
                current_page_lines = sum([1 + len(t) // 50 for t in page_buffer])
                
                if current_page_lines + visual_lines > max_lines:
                    page_buffer = [clean_text]
                else:
                    page_buffer.append(clean_text)
                
                page_content = "\n".join(page_buffer)
                new_segments.append((seg['start'], seg['end'], page_content))
            
            # Yeni SRT'yi yaz (UTF-8 with BOM for better compatibility)
            with open(output_srt, 'w', encoding='utf-8-sig') as f:
                for i, (start, end, text) in enumerate(new_segments, 1):
                    f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
            
            return output_srt
            
        except Exception as e:
            self.logger.error(f"Reddit SRT conversion error: {e}")
            return input_srt

    def _ms_to_srt_time(self, ms: int) -> str:
        hours = ms // 3600000
        ms %= 3600000
        minutes = ms // 60000
        ms %= 60000
        seconds = ms // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def _cleanup_temp_files(self, files: List[Path]):
        """Clean up temporary files with retries for Windows file locking"""
        import time
        max_retries = 3
        
        for file in files:
            for attempt in range(max_retries):
                try:
                    if file.exists(): 
                        file.unlink()
                        self.logger.info(f"🧹 Temizlendi: {file}")
                    break # Success, move to next file
                except PermissionError:
                    if attempt < max_retries - 1:
                        time.sleep(1.0) # Wait a bit
                    else:
                        self.logger.warning(f"⚠️ Dosya silinemedi (PermissionError): {file}")
                except Exception as e:
                    self.logger.warning(f"Temizlik hatası: {e}")
                    break

if __name__ == "__main__":
    print("Video Assembler - Robust SRT Creation + Safe Zone Fix")