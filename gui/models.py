"""
CapCapWifi GUI - Veri Modelleri
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AttackType(str, Enum):
    HANDSHAKE_SNOOPER = "Handshake Snooper"
    CAPTIVE_PORTAL = "Captive Portal"


class AttackState(str, Enum):
    IDLE = "IDLE"
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
    def signal_color(self) -> str:
        try:
            val = int(self.quality.replace("%", "").replace("?", "0"))
            if val >= 70:
                return "#00E676"  # Çok İyi (Yeşil)
            elif val >= 40:
                return "#FFD600"  # Orta (Sarı)
            else:
                return "#FF5252"  # Zayıf (Kırmızı)
        except Exception:
            return "#9E9E9E"

    @property
    def signal_percent(self) -> float:
        try:
            return float(self.quality.replace("%", "").replace("?", "0")) / 100.0
        except Exception:
            return 0.1


@dataclass
class PortalSite:
    site_id: str
    name: str
    lang: str
    path: str
    has_submit: bool = False

    @property
    def display_title(self) -> str:
        flag_or_code = self.lang.upper()
        return f"{self.name} [{flag_or_code}]"


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
    client_ip: Optional[str] = None
    extra_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HandshakeFile:
    filename: str
    filepath: str
    ssid: str
    bssid: str
    size_bytes: int
    created_at: str
