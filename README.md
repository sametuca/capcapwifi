# capcapwifi

- Kali Linux (rolling) or another Linux with the same tooling; root is required.
- A wireless adapter that supports monitor mode and frame injection.
- `hostapd`, `lighttpd`, `php-cgi`, `kea-dhcp4`, `dnsspoof`, `aircrack-ng`,
  `iptables`, `xterm` (or `tmux` with `-m`). The dependency check offers to
  install whatever is missing.

## CLI Kullanımı

```bash
git clone https://github.com/sametuca/capcapwifi.git capcapwifi
cd capcapwifi
sudo ./capcapwifi.sh
```

## 🖥️ Python GUI Kullanımı

Projeye **CustomTkinter** tabanlı, karanlık temalı bir Python GUI eklendi.  
CLI komutlarını bilmenize gerek kalmadan tüm işlemleri grafik arayüzden yönetebilirsiniz.

### Gereksinimler

- Python 3.9+
- Kali Linux (saldırı modları için); arayüz macOS/Linux'ta da açılır

### Başlatma

```bash
cd capcapwifi
./run_gui.sh          # eksik sistem paketlerini kurar, venv hazırlar, GUI'yi root olarak açar
```

İlk açılışta olanlar (hepsi ekranda görünür, hiçbir şeyi elle kurmanız gerekmez):

1. `run_gui.sh` `python3`, `python3-tk` ve `python3-venv` paketlerini kontrol eder,
   eksikse `apt` ile kurar ve satır satır ilerlemeyi basar.
2. Python paketleri (`customtkinter`, `pillow`) sanal ortama indirilir.
3. Script kendini `sudo` ile yeniden başlatır (monitor mode + hostapd root ister).
4. GUI açılır, sağdaki **Ortam Kontrolü** kartı tüm araçları ✓/✗ olarak listeler.
   Zorunlu bir araç eksikse kurulum kendiliğinden başlar: ilerleme çubuğu döner,
   `apt` çıktısı canlı log paneline akar, bitince kontrol otomatik yenilenir.
   Aynı işi elle tetiklemek için karttaki **📦 Eksikleri kur** düğmesi,
   terminalden yapmak için `sudo ./capcapwifi.sh --install-deps --auto -m`.

### GUI Özellikleri

| Özellik | Açıklama |
|---|---|
| 🧭 Adım çubuğu | Adaptör → Tara → Hedef seç → Saldır → Sonuç; hangi adımda olduğunuz vurgulanır |
| 🩺 Ortam Kontrolü | Root, adaptör, monitor mode ve tüm araçlar ✓/✗ olarak; eksikse tek tuşla kurulum |
| 📡 Ağ Tarama | Belirtilen süre boyunca airodump-ng ile yakındaki WPA ağlarını tarar |
| ⚡ Captive Portal Saldırısı | Sahte AP + phishing sayfası ile şifre yakalamak |
| 🤝 Handshake Snooper | WPA handshake yakalamak için pasif dinleme |
| 🔍 61+ Portal Şablonu | ARRIS, TP-Link, Instagram, HUAWEI ve daha fazlası |
| 💬 "Şimdi ne yapmalıyım" satırı | Alt barda her durumda sıradaki tek adım yazar |
| ❓ Nasıl kullanılır sekmesi | 5 adımlık kullanım rehberi ve dosya yolları |
| 🎨 Canlı Log | Renkli gerçek zamanlı log akışı |
| 🔑 Şifre Paneli | Yakalanan şifreler anında ekranda gösterilir |

### GUI Dosya Yapısı

```
capcapwifi/
├── gui/
│   ├── app.py          # Ana pencere (CustomTkinter)
│   ├── controller.py   # Hibrit backend (capcapwifi.sh → --auto)
│   ├── widgets.py      # Yeniden kullanılabilir widget bileşenleri
│   └── models.py       # Veri modelleri (dataclass)
├── run_gui.sh          # Tek komutla GUI başlatıcı
└── venv/               # Python sanal ortamı (otomatik oluşturulur)
```

> **Not:** GUI, `capcapwifi.sh`'yi `--auto` modunda arka planda çalıştırır ve  
> `capcap_status` satırlarını parse ederek durum güncellemelerini gerçek zamanlı  
> olarak arayüze yansıtır.
