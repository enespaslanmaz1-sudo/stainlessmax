"""
Affiliate Manager - Otomatik Affiliate Link Sistemi
Video konusuna göre ilgili affiliate linkleri ekler
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional
from google import genai
import os


class AffiliateManager:
    """Affiliate link yönetimi ve otomatik CTA üretimi"""
    
    def __init__(self, config_file: str = "config/affiliate_links.json"):
        self.logger = logging.getLogger(__name__)
        self.config_file = Path(config_file)
        self.links = {}
        
        # Gemma AI (new SDK - hafif görev)
        self.model_name = "gemini-2.5-flash"
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
        
        # Load existing links
        self._load_links()
    
    def _load_links(self):
        """Affiliate linkleri yükle"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.links = json.load(f)
                self.logger.info(f"✅ {len(self.links)} hesap için affiliate link yüklendi")
            except Exception as e:
                self.logger.error(f"Link yükleme hatası: {e}")
                self.links = {}
        else:
            self.logger.warning("Affiliate link config bulunamadı, boş başlatılıyor")
            self.links = {}
    
    def _save_links(self):
        """Affiliate linkleri kaydet"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.links, f, ensure_ascii=False, indent=2)
            self.logger.info("✅ Affiliate linkler kaydedildi")
        except Exception as e:
            self.logger.error(f"Link kaydetme hatası: {e}")
    
    def add_affiliate_link(
        self,
        account_id: str,
        url: str,
        category: str,
        discount_code: Optional[str] = None,
        description: str = ""
    ):
        """
        Hesaba affiliate link ekle
        
        Args:
            account_id: Hesap ID
            url: Affiliate URL
            category: Kategori (finance, health, education, vb.)
            discount_code: İndirim kodu (opsiyonel)
            description: Link açıklaması
        """
        if account_id not in self.links:
            self.links[account_id] = []
        
        link_data = {
            "url": url,
            "category": category,
            "discount_code": discount_code,
            "description": description,
            "clicks": 0,
            "added_at": str(Path(__file__).stat().st_mtime)
        }
        
        self.links[account_id].append(link_data)
        self._save_links()
        
        self.logger.info(f"✅ Affiliate link eklendi: {account_id} -> {category}")
    
    def get_best_link_for_topic(
        self,
        account_id: str,
        topic: str,
        niche: str
    ) -> Optional[Dict]:
        """
        Konuya en uygun affiliate linki seç
        
        Args:
            account_id: Hesap ID
            topic: Video konusu
            niche: İçerik kategorisi
            
        Returns:
            Dict: Seçilen link bilgisi veya None
        """
        if account_id not in self.links or not self.links[account_id]:
            self.logger.warning(f"Hesap için affiliate link yok: {account_id}")
            return None
        
        account_links = self.links[account_id]
        
        # Aynı kategoriden link var mı?
        matching_links = [l for l in account_links if l["category"] == niche]
        
        if matching_links:
            # Gemini ile en uygun olanı seç
            if self.client and len(matching_links) > 1:
                best_link = self._select_best_with_ai(topic, matching_links)
                if best_link:
                    return best_link
            
            # Fallback: ilk eşleşen
            return matching_links[0]
        else:
            # Kategori eşleşmezse ilk linki döndür
            self.logger.warning(f"Tam eşleşme yok, genel link kullanılıyor")
            return account_links[0]
    
    def _select_best_with_ai(self, topic: str, links: List[Dict]) -> Optional[Dict]:
        """Gemini ile en uygun linki seç"""
        try:
            prompt = f"""Sen affiliate marketing uzmanısın.

**VİDEO KONUSU:** {topic}

**MEV­CUT AFFILIATE LİNKLER:**
{json.dumps(links, indent=2, ensure_ascii=False)}

**GÖREV:** Bu video konusuna EN UYGUN affiliate linki seç.

**CEVAP FORMATI (sadece JSON):**
```json
{{
  "selected_index": 0,
  "reason": "Neden bu link seçildi (1 cümle)"
}}
```"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
            
            selected_idx = result.get("selected_index", 0)
            if 0 <= selected_idx < len(links):
                self.logger.info(f"Gemini link seçti: {result.get('reason')}")
                return links[selected_idx]
            
        except Exception as e:
            self.logger.error(f"AI link seçimi hatası: {e}")
        
        return None
    
    def generate_cta(
        self,
        link_data: Dict,
        style: str = "casual"
    ) -> str:
        """
        CTA mesajı üret
        
        Args:
            link_data: Link bilgisi
            style: CTA stili (casual, urgent, subtle)
            
        Returns:
            str: CTA metni
        """
        discount_code = link_data.get("discount_code")
        
        # Stil bazlı CTA şablonları
        templates = {
            "casual": [
                "Link bio'da 👆 {discount}",
                "Detaylar için bio'ma bak 👆 {discount}",
                "Linkten hemen göz at 👆 {discount}"
            ],
            "urgent": [
                "HEMEN linkten faydalın! 🔥 {discount}",
                "Kaçırmayın! Bio'daki link 👆 {discount}",
                "SON ŞANS! Bio'da link var 👆 {discount}"
            ],
            "subtle": [
                "Daha fazla bilgi bio'da {discount}",
                "👆 Linkten devamını öğren {discount}",
                "Bio'daki linkten inceleyebilirsin {discount}"
            ]
        }
        
        style_templates = templates.get(style, templates["casual"])
        
        # Random seç
        import random
        template = random.choice(style_templates)
        
        # Discount code varsa ekle
        if discount_code:
            discount_text = f"Kod: {discount_code}"
        else:
            discount_text = ""
        
        cta = template.format(discount=discount_text)
        
        # Gemini ile customize et (opsiyonel)
        if self.client:
            try:
                refined_cta = self._refine_cta_with_ai(cta, link_data.get("description", ""))
                if refined_cta:
                    return refined_cta
            except Exception:
                pass
        
        return cta
    
    def _refine_cta_with_ai(self, base_cta: str, product_desc: str) -> Optional[str]:
        """Gemini ile CTA'yı geliştir"""
        try:
            prompt = f"""Sen copywriting uzmanısın.

**MEVCUT CTA:** {base_cta}
**ÜRÜN:** {product_desc}

**GÖREV:** Bu CTA'yı daha çekici ve kısa yap (max 100 karakter).

Sadece düzenlenmiş CTA'yı döndür, başka açıklama ekleme."""

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            refined = response.text.strip()
            
            if len(refined) <= 100:
                return refined
            
        except Exception as e:
            self.logger.error(f"CTA refinement hatası: {e}")
        
        return None
    
    def track_click(self, account_id: str, url: str):
        """Affiliate link tıklamasını kaydet"""
        if account_id in self.links:
            for link in self.links[account_id]:
                if link["url"] == url:
                    link["clicks"] = link.get("clicks", 0) + 1
                    self._save_links()
                    break


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("AFFILIATE MANAGER TEST")
    print("="*60)
    
    manager = AffiliateManager()
    
    # Test: Link ekle
    print("\n[Test 1] Affiliate link ekleme...")
    manager.add_affiliate_link(
        account_id="tiktok_main",
        url="https://bit.ly/para-kitabi",
        category="finance",
        discount_code="VIRAL50",
        description="Para kazanma rehberi kitabı"
    )
    
    # Test: Konuya uygun link seç
    print("\n[Test 2] Konuya uygun link seçimi...")
    selected = manager.get_best_link_for_topic(
        account_id="tiktok_main",
        topic="Zengin insanların 5 alışkanlığı",
        niche="finance"
    )
    
    if selected:
        print(f"✅ Seçilen link: {selected['url']}")
        print(f"   Kategori: {selected['category']}")
        print(f"   İndirim kodu: {selected.get('discount_code')}")
    
    # Test: CTA üret
    if selected:
        print("\n[Test 3] CTA mesajı üretme...")
        cta = manager.generate_cta(selected, style="casual")
        print(f"✅ CTA: {cta}")
    
    print("\n✅ Tüm testler tamamlandı!")
