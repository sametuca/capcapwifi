"""
CapCapWifi GUI - Veri Modelleri

Bu dosyada GUI'nin kullandığı saf veri sınıfları var; hiçbiri ekran veya
süreç çağırmaz, bu yüzden test edilebilirler.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AttackType(str, Enum):
    HANDSHAKE_SNOOPER = "Handshake Snooper"
    CAPTIVE_PORTAL = "Captive Portal"

    @property
    def title(self) -> str:
        return {
            AttackType.HANDSHAKE_SNOOPER: "Handshake Snooper",
            AttackType.CAPTIVE_PORTAL: "Captive Portal",
        }[self]

    @property
    def summary(self) -> str:
        """Tek cümlelik açıklama – arayüzde başlığın altında gösterilir."""
        return {
            AttackType.HANDSHAKE_SNOOPER: (
                "Hedef ağa bağlı cihazları düşürüp yeniden bağlanmaya zorlar ve "
                "WPA/WPA2 handshake'ini yakalar. Sonuç .cap dosyasıdır."
            ),
            AttackType.CAPTIVE_PORTAL: (
                "Hedef ağın birebir kopyasını (sahte AP) açar, bağlanan cihaza "
                "giriş sayfası gösterir ve girilen bilgileri kaydeder."
            ),
        }[self]

    @property
    def what_you_need(self) -> str:
        return {
            AttackType.HANDSHAKE_SNOOPER: (
                "Monitor mode + paket enjeksiyonu destekleyen adaptör. Hedef ağda "
                "en az bir bağlı cihaz olmalı; cihaz yoksa handshake de gelmez."
            ),
            AttackType.CAPTIVE_PORTAL: (
                "Monitor mode + enjeksiyon destekleyen adaptör (ideali iki adaptör: "
                "biri sahte AP, diğeri deauth için). Portal seçilir, gerisini "
                "program kurar."
            ),
        }[self]

    @property
    def what_happens_next(self) -> str:
        return {
            AttackType.HANDSHAKE_SNOOPER: (
                "Saldırı başlar, seçtiğin süre boyunca handshake aranır. Bulunursa "
                "soldaki 'Ağlar' sekmesinde ✔ işareti ve logda 'Handshake yakalandı' "
                "satırı görünür."
            ),
            AttackType.CAPTIVE_PORTAL: (
                "Sahte AP açılır, hedef cihazlar düşürülür ve portal sayfası "
                "yayınlanır. Bir cihaz bağlanıp formu gönderdiğinde 'Şifreler' "
                "sekmesine satır düşer."
            ),
        }[self]


class AttackState(str, Enum):
    IDLE = "IDLE"
    INSTALLING = "INSTALLING"
    STARTING = "STARTING"
    SCANNING = "SCANNING"
    RUNNING = "RUNNING"
    HANDSHAKE_CAPTURED = "HANDSHAKE_CAPTURED"
    CREDENTIALS_FOUND = "CREDENTIALS_FOUND"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class WirelessInterface:
    name: str
    state: str = "DOWN"
    bands: str = "2.4 GHz"
    bus: str = "USB"
    driver: str = "unknown"
    chipset: str = "Generic Wireless"

    @property
    def display_text(self) -> str:
        return f"{self.name} [{self.bands}] - {self.chipset} ({self.state})"


@dataclass
class TargetCandidate:
    bssid: str
    channel: str
    power: int
    clients: int
    quality: str
    enc: str
    vendor: str
    essid: str
    has_handshake: bool = False

    @property
    def clean_essid(self) -> str:
        return self.essid.strip() or "<Gizli Ağ>"

    @property
    def is_dfs(self) -> bool:
        """52-64 ve 100-144 arası kanallar DFS: sahte AP orada açılamaz."""
        try:
            ch = int(str(self.channel).rstrip("!"))
        except ValueError:
            return False
        return 52 <= ch <= 64 or 100 <= ch <= 144

    @property
    def has_clients(self) -> bool:
        return self.clients > 0

    @property
    def signal_color(self) -> str:
        try:
            val = int(self.quality.replace("%", "").replace("?", "0"))
        except Exception:
            return "#9E9E9E"
        if val >= 70:
            return "#00E676"
        if val >= 40:
            return "#FFD600"
        return "#FF5252"

    @property
    def signal_percent(self) -> float:
        try:
            return float(self.quality.replace("%", "").replace("?", "0")) / 100.0
        except Exception:
            return 0.1

    @property
    def recommendation(self) -> str:
        """Tabloda seçili satır için tek satırlık gerekçe."""
        if self.is_dfs:
            return (
                "DFS kanalı: sahte AP bu kanalda açılamaz. Portal için başka ağ seç, "
                "handshake için uygun."
            )
        if self.has_clients:
            return (
                f"{self.clients} cihaz bağlı: deauth atınca handshake/portal için "
                "sonuç alma şansı en yüksek ağ."
            )
        return (
            "Bağlı cihaz görünmüyor: deauth atacak kimse yok, bu ağdan handshake "
            "veya portal ziyaretçisi gelmez."
        )


@dataclass
class PortalSite:
    site_id: str
    name: str
    lang: str
    path: str
    has_submit: bool = False

    @property
    def display_title(self) -> str:
        return f"{self.name} [{self.lang.upper()}]"

    @property
    def self_capturing(self) -> bool:
        """submit.php taşıyan portallar girdiyi kendisi kaydeder.

        Bunlarda 'handshake ile şifre doğrulama' adımı anlamsızdır; Fluxion'un
        hash akışı yalnızca stok portallar için gerekli.
        """
        return self.has_submit

    @property
    def description(self) -> str:
        if self.self_capturing:
            return (
                "Kendi kayıt sayfasını kullanır: ziyaretçinin yazdığı kullanıcı adı "
                "ve şifre doğrudan kaydedilir, handshake gerekmez."
            )
        return (
            "Stok portal: gönderilen şifreyi yakalanmış handshake ile doğrular, "
            "bu yüzden önce o ağın handshake'i gerekir."
        )


@dataclass
class AttackConfig:
    attack_type: AttackType = AttackType.CAPTIVE_PORTAL
    interface: str = ""
    target_bssid: str = ""
    target_essid: str = ""
    target_channel: str = ""
    jammer_interface: str = ""
    ap_interface: str = ""
    ap_channel: str = ""
    ap_service: str = "hostapd"
    deauth_method: str = "aireplay-ng"
    portal_site: str = "Instagram_tur"
    language: str = "tur"
    band: str = "bg"
    reg_domain: str = "TR"
    kill_processes: bool = True
    timeout_minutes: Optional[int] = None


@dataclass
class CapturedCredential:
    timestamp: str
    ssid: str
    bssid: str
    password: str
    username: str = ""
    client_ip: Optional[str] = None
    extra_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_username(self) -> str:
        return self.username or "-"


@dataclass
class HandshakeFile:
    filename: str
    filepath: str
    ssid: str
    bssid: str
    size_bytes: int
    created_at: str


@dataclass
class EnvironmentCheck:
    """Tek bir ortam kontrolünün sonucu (root, araç, adaptör...)."""

    name: str
    ok: bool
    detail: str = ""
    hint: str = ""
    required: bool = True

    @property
    def icon(self) -> str:
        return "✓" if self.ok else "✗"

    @property
    def color(self) -> str:
        if self.ok:
            return "#00E676"
        return "#FF5252" if self.detail else "#FFD600"
