# 🚀 Stainless Max - Kurulum Rehberi

**AI Destekli Viral Video Üretim Stüdyosu**  
*Versiyon: 2.1.0*

---

## 📋 Sistem Gereksinimleri

| Gereksinim | Minimum |
|---|---|
| İşletim Sistemi | Windows 10 64-bit veya üstü |
| RAM | 8 GB (16 GB önerilir) |
| Disk | 5 GB boş alan |
| GPU | NVIDIA GPU (isteğe bağlı - hız artırır) |
| İnternet | Sürekli bağlantı gerekli |
| Tarayıcı | Google Chrome veya Microsoft Edge |

---

## ⚡ Hızlı Kurulum

### 1. Kurulum Dosyasını Çalıştırın
`StainlessMax_Setup_v2.1.0.exe` dosyasına çift tıklayın.

> Güvenlik uyarısı gelebilir, **"Daha fazla bilgi" → "Yine de çalıştır"** deyin.

### 2. API Key'leri Ayarlayın
Kurulumdan sonra masaüstündeki **Stainless Max** ikonuna tıklayın.

Dashboard açıldığında **Ayarlar** sayfasına gidin ve aşağıdaki key'leri girin:

---

## 🔑 API Key Alma Rehberi

### Gemini API Key (Zorunlu)
1. [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) adresine gidin
2. **"Create API key"** butonuna tıklayın
3. Oluşan key'i kopyalayın → Ayarlar'a yapıştırın

### Pexels API Key (Video stok için)
1. [https://www.pexels.com/api/](https://www.pexels.com/api/) adresine gidin
2. Ücretsiz hesap oluşturun → **"Get Started"**
3. API key'inizi kopyalayın

### Pixabay API Key (İkinci video kaynağı)
1. [https://pixabay.com/api/docs/](https://pixabay.com/api/docs/) adresine gidin
2. Ücretsiz kayıt olun
3. API key'inizi alın

### Telegram Bot (Bildirimler için - İsteğe bağlı)
1. Telegram'da **@BotFather**'a mesaj atın
2. `/newbot` yazın ve talimatları takip edin
3. Bot token'ınızı alın
4. **@userinfobot**'tan kendi Telegram ID'nizi öğrenin

---

## 📺 YouTube Hesabı Bağlama

1. Dashboard → **Hesaplar** → **YouTube Ekle**
2. Google Cloud Console'dan OAuth 2.0 credentials alın:
   - [https://console.cloud.google.com/](https://console.cloud.google.com/) 
   - Yeni proje oluşturun
   - **APIs & Services** → **YouTube Data API v3** etkinleştirin
   - **Credentials** → **OAuth 2.0 Client ID** oluşturun
3. Client ID ve Secret'ı girin → Yetkilendirin

---

## 🎬 İlk Video Üretimi

1. Dashboard'da **Hesap Seçin**
2. **Platform** (YouTube/TikTok) seçin
3. **Üret** butonuna tıklayın
4. Video otomatik üretilip yüklenir ✅

---

## 🔄 Otomatik Güncelleme

Uygulama yeni versiyon çıktığında size bildirim gösterir.

**Manuel kontrol:** Dashboard → Ayarlar → Güncelleme Kontrol Et

---

## 🛠️ Sorun Giderme

### Uygulama açılmıyor
- `stainless_max.log` dosyasına bakın (kurulum klasöründe)
- Chrome veya Edge kurulu mu kontrol edin
- Antivirüs programı engelliyor olabilir → dışlama listesine ekleyin

### Video üretilmiyor
- Gemini API key doğru mu kontrol edin
- FFmpeg kurulu mu: `ffmpeg -version` komutunu çalıştırın
- İnternet bağlantısını kontrol edin

### Yükleme başarısız
- Hesap token'larının geçerli olduğunu kontrol edin
- YouTube/TikTok kota limitlerini kontrol edin

---

## 📞 Destek

- Website: [https://stainlessmax.com](https://stainlessmax.com)
- Log dosyası: `AppData\Local\Programs\Stainless Max\stainless_max.log`

---

*Stainless Max v2.1.0 © 2026 StainlessMax Inc.*
