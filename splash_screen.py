"""
StainlessMax Splash Screen - Premium Animated Intro with Sound
Tkinter tabanlı açılış ekranı + ses efekti
"""

import tkinter as tk
from tkinter import Canvas
import threading
import math
import os
import sys
import struct
import wave
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_startup_sound():
    """Synthesize a futuristic startup chime WAV (no external deps)"""
    try:
        sample_rate = 44100
        duration = 1.8  # seconds
        num_samples = int(sample_rate * duration)
        
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            
            # Layer 1: Rising sweep (200Hz -> 800Hz)
            freq1 = 200 + 600 * (t / duration)
            # Layer 2: Harmonic shimmer
            freq2 = 440 * (1 + 0.5 * math.sin(2 * math.pi * 3 * t))
            # Layer 3: Sub bass pulse
            freq3 = 80
            
            # Envelope: fade in (0.1s) + sustain + fade out (0.5s)
            if t < 0.1:
                env = t / 0.1
            elif t > duration - 0.5:
                env = (duration - t) / 0.5
            else:
                env = 1.0
            
            # Extra sparkle envelope for layer 2
            sparkle_env = max(0, 1 - t / duration) * 0.3
            
            # Mix layers
            val = (
                0.35 * math.sin(2 * math.pi * freq1 * t) * env +
                0.25 * math.sin(2 * math.pi * freq2 * t) * sparkle_env +
                0.15 * math.sin(2 * math.pi * freq3 * t) * env +
                0.10 * math.sin(2 * math.pi * freq1 * 2 * t) * env * 0.5  # Overtone
            )
            
            # Soft clip
            val = max(-0.95, min(0.95, val))
            
            # Convert to 16-bit int
            sample = int(val * 32767 * 0.7)
            samples.append(struct.pack('<h', sample))
        
        # Write WAV
        wav_path = os.path.join(tempfile.gettempdir(), "stainlessmax_startup.wav")
        with wave.open(wav_path, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(samples))
        
        return wav_path
    except Exception as e:
        print(f"Sound generation error: {e}")
        return None


def play_sound(wav_path):
    """Play WAV using winsound (Windows native, no deps)"""
    if not wav_path or not os.path.exists(wav_path):
        return
    try:
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


class SplashScreen:
    """Premium animated splash screen"""
    
    def __init__(self, duration_ms=3500):
        self.duration_ms = duration_ms
        self.root = None
        self.canvas = None
        self.width = 600
        self.height = 400
        self.animation_frame = 0
        self.particles = []
        self._closed = False
        
    def show(self):
        """Show splash screen (blocking until complete)"""
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # No title bar
        self.root.attributes('-topmost', True)
        
        # Center on screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - self.width) // 2
        y = (screen_h - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        # Transparency (Windows)
        try:
            self.root.attributes('-alpha', 0.0)
        except:
            pass
        
        # Canvas
        self.canvas = Canvas(
            self.root, 
            width=self.width, 
            height=self.height, 
            bg='#0a0a14',
            highlightthickness=0
        )
        self.canvas.pack()
        
        # Generate particles
        import random
        for _ in range(40):
            self.particles.append({
                'x': random.randint(0, self.width),
                'y': random.randint(0, self.height),
                'vx': random.uniform(-0.5, 0.5),
                'vy': random.uniform(-1.5, -0.3),
                'size': random.uniform(1, 3),
                'alpha': random.uniform(0.3, 1.0),
                'color': random.choice(['#6366f1', '#818cf8', '#a78bfa', '#c4b5fd', '#3b82f6'])
            })
        
        # Play sound
        wav_path = generate_startup_sound()
        play_sound(wav_path)
        
        # Start animation
        self._animate_fade_in()
        
        # Auto close timer
        self.root.after(self.duration_ms, self._close)
        
        # Click to skip
        self.canvas.bind('<Button-1>', lambda e: self._close())
        
        self.root.mainloop()
    
    def _animate_fade_in(self):
        """Fade in animation"""
        if self._closed:
            return
        alpha = min(1.0, self.animation_frame / 15)
        try:
            self.root.attributes('-alpha', alpha)
        except:
            pass
        
        self.animation_frame += 1
        
        if self.animation_frame <= 15:
            self.root.after(30, self._animate_fade_in)
        else:
            self._draw_frame()
    
    def _draw_frame(self):
        """Main animation loop"""
        if self._closed:
            return
            
        self.canvas.delete('all')
        
        cx, cy = self.width // 2, self.height // 2
        frame = self.animation_frame - 15
        
        # Background gradient effect (radial glow)
        for r in range(8, 0, -1):
            radius = r * 30
            alpha_hex = hex(int(20 + r * 3))[2:].zfill(2)
            color = f'#{alpha_hex}{alpha_hex}2a'
            try:
                self.canvas.create_oval(
                    cx - radius, cy - radius - 30,
                    cx + radius, cy + radius - 30,
                    fill=color, outline=''
                )
            except:
                pass
        
        # Animated particles
        for p in self.particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            if p['y'] < -10:
                p['y'] = self.height + 10
            if p['x'] < -10:
                p['x'] = self.width + 10
            
            pulse = 0.5 + 0.5 * math.sin(frame * 0.1 + p['x'] * 0.01)
            size = p['size'] * (0.5 + pulse * 0.5)
            
            self.canvas.create_oval(
                p['x'] - size, p['y'] - size,
                p['x'] + size, p['y'] + size,
                fill=p['color'], outline=''
            )
        
        # Glowing ring
        ring_radius = 80 + 10 * math.sin(frame * 0.08)
        ring_width = 2 + math.sin(frame * 0.05)
        self.canvas.create_oval(
            cx - ring_radius, cy - 30 - ring_radius,
            cx + ring_radius, cy - 30 + ring_radius,
            outline='#6366f1', width=ring_width
        )
        
        # Inner ring
        inner_r = 60 + 5 * math.sin(frame * 0.12 + 1)
        self.canvas.create_oval(
            cx - inner_r, cy - 30 - inner_r,
            cx + inner_r, cy - 30 + inner_r,
            outline='#818cf8', width=1
        )
        
        # Logo text - STAINLESS MAX
        # Main title with shadow
        self.canvas.create_text(
            cx + 2, cy - 28,
            text="STAINLESS MAX",
            font=("Segoe UI", 32, "bold"),
            fill='#1a1a2e'
        )
        self.canvas.create_text(
            cx, cy - 30,
            text="STAINLESS MAX",
            font=("Segoe UI", 32, "bold"),
            fill='#e0e7ff'
        )
        
        # Subtitle
        sub_alpha = min(1.0, max(0, (frame - 10) / 20))
        if sub_alpha > 0:
            sub_color = f'#{int(99*sub_alpha):02x}{int(102*sub_alpha):02x}{int(241*sub_alpha):02x}'
            self.canvas.create_text(
                cx, cy + 15,
                text="AI  Video  Production  Studio",
                font=("Segoe UI Light", 13),
                fill=sub_color
            )
        
        # Version badge
        if frame > 20:
            badge_alpha = min(1.0, (frame - 20) / 15)
            badge_color = f'#{int(129*badge_alpha):02x}{int(140*badge_alpha):02x}{int(248*badge_alpha):02x}'
            self.canvas.create_text(
                cx, cy + 50,
                text="v3.0  Enterprise",
                font=("Segoe UI", 10),
                fill=badge_color
            )
        
        # Loading bar
        bar_y = cy + 90
        bar_width = 300
        bar_x = cx - bar_width // 2
        
        # Bar background
        self.canvas.create_rectangle(
            bar_x, bar_y, bar_x + bar_width, bar_y + 4,
            fill='#1e1e3a', outline=''
        )
        
        # Bar progress (animated)
        progress = min(1.0, frame / 80)
        fill_width = int(bar_width * progress)
        
        # Gradient effect on bar
        if fill_width > 0:
            self.canvas.create_rectangle(
                bar_x, bar_y, bar_x + fill_width, bar_y + 4,
                fill='#6366f1', outline=''
            )
            # Glow tip
            self.canvas.create_rectangle(
                bar_x + max(0, fill_width - 20), bar_y,
                bar_x + fill_width, bar_y + 4,
                fill='#a78bfa', outline=''
            )
        
        # Status text
        if frame < 25:
            status = "Sistem Başlatılıyor..."
        elif frame < 50:
            status = "Modüller Yükleniyor..."
        elif frame < 70:
            status = "AI Engine Hazırlanıyor..."
        else:
            status = "Hazır!"
        
        status_alpha = min(1.0, max(0.3, 0.3 + 0.7 * math.sin(frame * 0.15)))
        sc = int(140 * status_alpha)
        self.canvas.create_text(
            cx, bar_y + 22,
            text=status,
            font=("Segoe UI", 9),
            fill=f'#{sc:02x}{sc:02x}{int(sc*1.2):02x}'
        )
        
        # Bottom credit
        self.canvas.create_text(
            cx, self.height - 15,
            text="Powered by Gemini AI  •  FFmpeg  •  Edge TTS",
            font=("Segoe UI", 8),
            fill='#3a3a5c'
        )
        
        self.animation_frame += 1
        
        if not self._closed:
            self.root.after(33, self._draw_frame)  # ~30fps
    
    def _close(self):
        """Fade out and close"""
        if self._closed:
            return
        self._closed = True
        self._fade_out(10)
    
    def _fade_out(self, steps):
        """Fade out animation"""
        if steps <= 0:
            try:
                self.root.destroy()
            except:
                pass
            return
        try:
            alpha = steps / 10
            self.root.attributes('-alpha', alpha)
            self.root.after(30, lambda: self._fade_out(steps - 1))
        except:
            try:
                self.root.destroy()
            except:
                pass


def show_splash():
    """Show splash screen (call from main thread before webview)"""
    splash = SplashScreen(duration_ms=3500)
    splash.show()


if __name__ == '__main__':
    show_splash()
    print("Splash done!")

