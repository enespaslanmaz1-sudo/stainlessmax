
import subprocess
import time
import logging
import requests

class WarpManager:
    """Manages Cloudflare WARP for IP Rotation"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def rotate_ip(self):
        """Disconnects and Reconnects WARP to get a new IP"""
        self.logger.info("🔄 Rotating IP via WARP...")
        
        try:
            # 1. Disconnect
            subprocess.run(["warp-cli", "disconnect"], check=True, capture_output=True)
            time.sleep(2)
            
            # 2. Connect
            subprocess.run(["warp-cli", "connect"], check=True, capture_output=True)
            time.sleep(5) # Wait for connection
            
            # 3. Verify
            new_ip = self.get_public_ip()
            self.logger.info(f"✅ New IP: {new_ip}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"❌ WARP Error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ IP Rotation Failed: {e}")
            return False

    def get_public_ip(self):
        """Gets current public IP"""
        try:
            return requests.get("https://api.ipify.org", timeout=5).text
        except Exception:
            return "Unknown"
