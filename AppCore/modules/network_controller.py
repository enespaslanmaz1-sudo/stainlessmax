"""
Network Controller - IP Rotation with Cloudflare WARP
"""

import subprocess
import time
import requests
import logging
from typing import Optional


class NetworkController:
    """Manage Cloudflare WARP for IP rotation"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.last_ip: Optional[str] = None
        self.stats = {
            "total_rotations": 0,
            "successful_rotations": 0,
            "failed_rotations": 0
        }
    
    def _warp_command(self, command: str) -> bool:
        """Execute WARP CLI command"""
        try:
            result = subprocess.run(
                ["warp-cli", command],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"WARP command failed: {e}")
            return False
    
    def _get_current_ip(self) -> Optional[str]:
        """Get current public IP"""
        try:
            response = requests.get("https://api.ipify.org", timeout=10)
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"Failed to get IP: {e}")
            return None
    
    def verify_connection(self) -> bool:
        """Check internet connectivity"""
        try:
            requests.get("https://1.1.1.1", timeout=5)
            return True
        except Exception:
            return False
    
    def rotate_ip(self, max_retries: int = 3) -> bool:
        """Rotate IP address"""
        self.stats["total_rotations"] += 1
        
        for attempt in range(max_retries):
            try:
                old_ip = self._get_current_ip()
                
                # Disconnect and reconnect WARP
                self._warp_command("disconnect")
                time.sleep(5)
                self._warp_command("connect")
                time.sleep(3)
                
                new_ip = self._get_current_ip()
                
                if new_ip and new_ip != old_ip:
                    self.last_ip = new_ip
                    self.stats["successful_rotations"] += 1
                    self.logger.info(f"IP rotated: {new_ip}")
                    return True
                
                if attempt < max_retries - 1:
                    time.sleep(10)
                    
            except Exception as e:
                self.logger.error(f"IP rotation error: {e}")
                time.sleep(10)
        
        self.stats["failed_rotations"] += 1
        return False
    
    def get_warp_status(self) -> dict:
        """Get WARP status"""
        try:
            result = subprocess.run(
                ["warp-cli", "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout.lower()
            
            return {
                "connected": "connected" in output,
                "status_output": result.stdout,
                "last_ip": self.last_ip,
                "stats": self.stats
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "stats": self.stats
            }
    
    def quick_ip_check(self) -> Optional[str]:
        """Quick IP check"""
        return self._get_current_ip()
