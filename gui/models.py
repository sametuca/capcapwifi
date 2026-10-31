"""
CapCapWifi GUI - Veri Modelleri

Bu dosyada GUI'nin kullandığı saf veri sınıfları var; hiçbiri ekran veya
süreç çağırmaz, bu yüzden test edilebilirler. Görünen metinler i18n'den
gelir; bu modül aktif dile göre çalışır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from i18n import t


class AttackType(str, Enum):
    HANDSHAKE_SNOOPER = "Handshake Snooper"
    CAPTIVE_PORTAL = "Captive Portal"

    @property
    def key(self) -> str:
        """i18n anahtar parçası: captive_portal / handshake_snooper."""
        return self.name.lower()

    @property
    def title(self) -> str:
        return self.value

    @property
    def label(self) -> str:
        """Açılır listede görünen, dile göre değişen ad."""
        return t(f"attack.{self.key}.label")

    @property
    def summary(self) -> str:
        """Tek cümlelik açıklama – arayüzde başlığın altında gösterilir."""
        return t(f"attack.{self.key}.summary")

    @property
    def what_you_need(self) -> str:
        return t(f"attack.{self.key}.need")

    @property
    def what_happens_next(self) -> str:
        return t(f"attack.{self.key}.next")


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
        return self.essid.strip() or t("target.hidden_ssid")

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
            return t("target.rec.dfs")
        if self.has_clients:
            return t("target.rec.clients", clients=self.clients)
        return t("target.rec.no_clients")


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

        Bunlarda 'handshake ile şifre doğrulama' adımı anlamsızdır; hash akışı
        yalnızca stok portallar için gerekli.
        """
        return self.has_submit

    @property
    def description(self) -> str:
        if self.self_capturing:
            return t("portal.desc.self_capturing")
        return t("portal.desc.stock")


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
