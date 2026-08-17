# Arctic Rust Clan Bot Updates

Bu depo Arctic Rust Clan Discord botunun `/guncelle` sistemi için otomatik güncelleme kaynağıdır.

Güncelleme adresi:
`https://github.com/metedyY/rust-clan-bot-update/archive/refs/heads/main.zip`

## Son güncelleme — Ses Log
- `ses-log` kanalı YÖNETİM kategorisine otomatik eklenir.
- Kanalı yalnızca `👑 Clan Owner` ve `🛠️ Moderator` rolleri görebilir.
- Tüm ses kanallarındaki girişler, çıkışlar ve kanal değiştirmeler embed olarak kaydedilir.
- Sistem mevcut bot eventlerini ezmeden `on_voice_state_update` listener'ı olarak çalışır.
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

`.env`, Discord bot tokenı ve yerel `data/wipe_state.json` GitHub'a yüklenmez.
