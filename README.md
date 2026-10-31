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
./run_gui.sh          # bağımlılıkları otomatik kurar ve GUI'yi açar
```

### GUI Özellikleri

| Özellik | Açıklama |
|---|---|
| 📡 Ağ Tarama | Belirtilen süre boyunca airodump-ng ile yakındaki WPA ağlarını tarar |
| ⚡ Captive Portal Saldırısı | Sahte AP + phishing sayfası ile şifre yakalamak |
| 🤝 Handshake Snooper | WPA handshake yakalamak için pasif dinleme |
| 🔍 61+ Portal Şablonu | ARRIS, TP-Link, Instagram, HUAWEI ve daha fazlası |
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
> `fluxion_status` satırlarını parse ederek durum güncellemelerini gerçek zamanlı  
> olarak arayüze yansıtır.
