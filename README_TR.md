# Operasyon360 — Pano & Evrak V1.0

Instaboard'ın görsel pano/kart yaklaşımından esinlenilmiş, **şirket içi evrak ve duyuru paylaşımına** odaklanan bağımsız çalışan sunuculu uygulama. Resmî Instaboard yazılımı değildir; marka ve özel kod kullanmaz. Rentman tabanlı Operasyon360 projesine daha sonra modül olarak entegre edilebilir; şu an birbirine doğrudan bağlanmış değildir.

## Yetki modeli

| İşlem | Yönetici | Çalışan |
|---|---|---|
| Pano oluşturma / güncelleme / arşivleme | Evet | Hayır |
| Kart oluşturma, sürükleme, düzenleme, silme | Evet | Hayır |
| Kart içinden alt pano açma | Evet | Hayır |
| Evrak yükleme / yeni sürüm / arşiv | Evet | Hayır |
| Yetkili olduğu panoları/kartları/evrakları görme | Evet | Evet |
| PDF ve görsel önizleme, dosya indirme | Evet | Evet (yalnızca yetkili belgeler) |
| Çalışan ekleme, şifre sıfırlama, hesap devre dışı bırakma | Evet | Hayır |
| İşlem geçmişini görme | Evet | Hayır |

**Önemli:** Çalışanların veri değiştirmesi sunucu API'sinde 403 hatasıyla engellenir; yalnızca arayüz gizlemesi değildir. Özel panolara yalnızca yöneticinin yetki verdiği çalışan erişir. Alt panolar üst panonun erişimini miras alır.

## Mac'te çalıştır

1. ZIP paketini indir ve klasörü aç.
2. Python **3.11 veya üzeri** yüklü olmalı. Gerekirse python.org'dan kur.
3. `Mac_Baslat.command` dosyasını aç. macOS güvenlik uyarısı verirse dosyaya sağ tık → Aç; gerekli olursa Terminal'de `chmod +x Mac_Baslat.command` ve `./Mac_Baslat.command` kullan.
4. İlk çalıştırmada bağımlılıklar yüklenir. Tarayıcıda **http://127.0.0.1:8765** açılır.
5. Yönetici kullanıcı adı `admin@local`, **rastgele oluşturulan şifre** `data/ILK_GIRIS_BILGILERI.txt` içinde. Şifreyi girişten sonra **Çalışanlar & Yetkiler → Yönetici → Şifre** ekranından değiştir.
6. Yeni pano/evrak ekle; ardından **Çalışanlar & Yetkiler** alanından personel hesaplarını oluştur. Özel pano için **Pano Ayarları → Yalnızca seçtiğim çalışanlar** yolunu kullan.

Uygulama veritabanı ve yüklenen belgeler `data/` klasöründe kalır. Klasör silinmediği sürece sunucuyu kapatıp açınca bilgiler kaybolmaz. **HTML dosyasını çift tıklayıp açmak bu ürünü çalıştırmaz: gerçek bir yerel sunucu gereklidir.**

## Ubuntu'da çalıştır

```bash
sudo apt-get install -y python3 python3-venv
./Linux_Baslat.sh
```

Başka cihazlardan erişmek için işletim sistemi ağ yapılandırması ve güvenli bir HTTPS reverse proxy veya VPN gereklidir. Uygulama varsayılan olarak 127.0.0.1'e bağlanır. Dış erişim için sunucu üzerinde ayrı ağ/güvenlik kurulumu yapılmalıdır.

Docker seçeneği:

```bash
docker compose up -d --build
# aynı sunucudan: http://127.0.0.1:8765
```

Docker kalıcı verileri `pano_data` biriminde tutar. İlk giriş şifresini görmek için:

```bash
docker compose exec pano cat /data/ILK_GIRIS_BILGILERI.txt
```

## Modüller

- **Panolarım:** Görsel kart panoları, arama, proje referansı, tüm personele açık veya yalnızca seçilen personele özel panolar.
- **Görsel Pano:** Yalnızca yöneticinin sürükleyebildiği kartlar; ayrıntı, durum, etiket, hedef tarih ve çalışan adı.
- **Görev Akışı:** Aynı kartların üç durum sütununda görünümü (salt-okunur çalışanlar için durum değişikliği yok).
- **Alt pano:** Bir karttan yeni pano oluşturma ve içeriğine geçme.
- **Evrak Kütüphanesi:** Pano/kart bağlantılı PDF, JPG, PNG, TXT, DOCX, XLSX, en fazla 20 MB; görüntüleme, indirme, eski sürümler.
- **Çalışanlar & Yetkiler:** Görüntüleyici hesabı oluşturma, aktif/pasif, şifre değiştirme.
- **İşlem Geçmişi:** Yönetim işlemleri, oturum açma ve evrak dosyası görüntülemeleri.

## Testler

`tests/test_api.py` içinde gerçek çalışan sunucuya HTTP istekleriyle yetki ve işlem doğrulaması yapılabilir. Test veri oluşturur, bu nedenle **ayrı bir test verisi klasörü** kullanın. UI görselleri Chromium'da HTML/CSS/JS render edilerek kontrol edildi. Bu çalışma ortamında Chromium'un ağ sayfalarını doğrudan açması engellendiğinden, arayüz görsel testi API örnek yanıtlarıyla yapıldı; sunuculu API işlemleri gerçek HTTP üzerinden test edildi. Mac/Safari ve Ubuntu üretim sunucusunda kapsamlı canlı testler henüz yapılmadı.

## Üretim güvenliği / eksikler

Bu **çalışan bir ilk sürüm** ama henüz ticari üretim ve internete açılmaya hazır bir servis olarak sunulmuyor. İnternet üzerinden erişim sağlamadan önce HTTPS, `APP_SECURE_COOKIE=true`, domain/reverse proxy, güvenlik duvarı, düzenli şifreli yedekler, log saklama politikası, yüklenen dosyalar için zararlı içerik taraması, çok faktörlü kimlik doğrulama, üretim izleme, hız sınırlamanın merkezi hale getirilmesi ve KVKK değerlendirmesi gerekir.

- Kullanıcı şifreleri scrypt ile hashlenir; oturum cookie'leri imzalı ve HttpOnly'dir. CSRF koruması ve pano bazlı sunucu yetki denetimi vardır.
- SQLite tek kuruluş / sınırlı eşzamanlı kullanım için yeterlidir; yüksek eşzamanlı veya çok kiracılı SaaS için PostgreSQL, nesne depolama ve kapsamlı oturum yönetimi gerekir.
- **Evrakları görmesini istemediğin çalışan için panoyu "Özel" yapmalısın.** "Tüm Ekip" açık panolar bütün aktif çalışanlara görünür.
- Kullanıcılar yetkili evrakı indirme hakkına sahiptir; indirilmiş dosyanın başka yere kopyalanmasını teknik olarak engelleyemeyiz.
- Silme yerine arşiv kullanılır; fiziksel dosyaların otomatik silinmesi ve geri yükleme ekranı bu ilk sürümde yoktur.
- Instaboard'ın video görüşmesi, kalem çizimi, çevrimdışı senkronizasyonu, gerçek zamanlı eşdüzenleme ve native mobil uygulaması **henüz yoktur**.

## Yedek

Sunucu kapalıyken **`data/` klasörünün tamamının** yedeğini alın (`database.sqlite3`, `.appsecret`, `uploads/`). `.appsecret` silinirse açık oturumlar geçersiz olur; şifreler veritabanında kalır. İlk giriş şifresini içeren dosyayı başkalarıyla paylaşmayın.

## Sonraki entegrasyon

Rentman referanslı Operasyon360 içindeki projeleri pano `project_ref` alanına eşleştirerek evrak/talimatların proje bağlantılarını oluşturabiliriz. Şu anki `project_ref` alanı yalnızca metin referanstır; otomatik Rentman proje senkronizasyonu olmadığı net olarak belirtilmiştir.
