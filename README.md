# Sekiz360 — Pano ve Evrak

Bu depo Operasyon360 pano ve evrak portalının dağıtım kodunu içerir.

- Railway üzerinde `pano-evrak-web` servisine dağıtılır.
- Yönetici panoları, çalışanları ve evrakları yönetir. Çalışanlar yalnızca yetkili oldukları panoları görüntüler.
- `/data` kalıcı disktir: belge dosyaları, SQLite veritabanı ve ilk yönetici bilgileri burada saklanır.
- Git deposuna hiçbir gerçek evrak, parola veya kullanıcı verisi konulmaz.

**Uyarı:** Kaynak kodu geçici olarak sıkıştırılmış `source-part-*.b64` dosyalarından Docker imajına açılır. Kaynak dosyalarının düzenlenebilir sürümü ayrıca ZIP paketinde sunulmuştur.
