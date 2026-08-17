# Arctic Rust Clan Bot Updates

Bu depo Arctic Rust Clan Discord botunun `/guncelle` sistemi için otomatik güncelleme kaynağıdır.

Güncelleme adresi:
`https://github.com/metedyY/rust-clan-bot-update/archive/refs/heads/main.zip`

## Son güncelleme — Rust Kalıcı Ban
- Yeni komut: `/ban perma oyuncu_id sebep`.
- `oyuncu_id` 17 haneli Steam64ID olmalıdır.
- Komutu `👑 Clan Owner`, `🛠️ Moderator`, Discord sunucu sahibi veya Administrator kullanabilir.
- Rust RCON üzerinden Steam64ID için kalıcı `banid` uygulanır; oyuncu çevrimiçiyse ayrıca anında kicklenir.
- Oyuncunun IP adresi `playerlist` verisinden veya daha önce tutulan oyuncu/IP önbelleğinden bulunursa `data/ip_bans.json` içine kaydedilir.
- Aynı IP ile başka Steam hesabı bağlanırsa bot varsayılan olarak 15 saniyelik aralıklarla tespit edip yeni hesabı da kalıcı banlar ve sunucudan atar.
- IP adresi bulunamasa bile Steam64ID kalıcı banı uygulanır.

### Rust RCON ayarı
Botun kendi `.env` dosyasına aşağıdaki değerler eklenmelidir:

```env
RUST_RCON_HOST=127.0.0.1
RUST_RCON_PORT=28016
RUST_RCON_PASSWORD=RUST_RCON_SIFREN
RUST_RCON_SCHEME=ws
RUST_IP_BAN_CHECK_SECONDS=15
```

Rust dedicated server tarafında WebRCON açık olmalıdır (`+rcon.web 1`). RCON parolasını GitHub'a yüklemeyin; yalnızca botun yerel `.env` dosyasında tutun.

## Ses Log
- `ses-log` kanalı mevcut gerçek YÖNETİM kategorisine otomatik eklenir.
- Kanalı yalnızca `👑 Clan Owner` ve `🛠️ Moderator` rolleri görebilir.
- Tüm ses kanallarındaki girişler, çıkışlar ve kanal değiştirmeler embed olarak kaydedilir.
- Sistem mevcut bot eventlerini ezmeden `on_voice_state_update` listener'ı olarak çalışır.
- Yeni YÖNETİM kategorisi oluşturmaz; önceki hatalı sürümden kalan boş YÖNETİM kopyalarını temizler.
- `/guncelle` sonrasında otomatik olarak aktif olur.

## Wipe Monitor
- Otomatik Rust wipe takibi eklendi.
- Canlı takip: Rustafied US/EU Main, Rustopia US/EU Main, Rusty Moose US/EU Main ve Survivors.gg Main.
- Main sunucularda takvim tahmini yerine Rust sunucusunun canlı query verisindeki yeni dünya başlangıcı (`born`) izlenir.
- İlk çalıştırmada mevcut wipe başlangıç noktası olarak kaydedilir; eski wipe mesajı atılmaz.
- Duplicate engeli ve yeniden başlatmalarda kalıcı durum kaydı vardır.
- Survivors.gg resmi `Today's Wipes` bölümü ayrıca takip edilir; Main dışındaki Survivors wipe'ları da `wipe-katilim` kanalına gönderilir.
- Yeni komutlar: `/wipe-test`, `/wipe-durum`, `/wipe-kaynaklar`.
- Hedef kanal varsayılan olarak `wipe-katilim`. İstenirse `.env` içinde `WIPE_CHANNEL_ID=` ile kanal ID'si sabitlenebilir.
- Main sunucular varsayılan 90 saniyede, Survivors.gg wipe sayfası 5 dakikada bir kontrol edilir.

## Kadro
- `/kadro` Discord rollerine göre otomatik listeler: `Roamer`, `Builder`, `Farmer`.
- Eksiksiz üye listesi için Discord Developer Portal > Bot > Privileged Gateway Intents > **Server Members Intent** açık olmalıdır.
- `All Rounder` kaldırıldı.

`.env`, Discord bot tokenı, RCON parolası ve yerel `data/` durum dosyaları GitHub'a yüklenmez.
