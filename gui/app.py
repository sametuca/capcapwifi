"""
CapCapWifi – Python GUI Ana Penceresi
CustomTkinter tabanlı, karanlık temalı, hibrit (capcapwifi.sh → --auto) denetleyici.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk

# Local modules
from controller import CapCapWifiController
from models import (
    AttackConfig,
    AttackState,
    AttackType,
    CapturedCredential,
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)
from widgets import (
    ACCENT, ACCENT2, CARD_BG, DARK_BG, DANGER, FONT_MONO_S, FONT_TITLE,
    FONT_UI, FONT_UI_B, MUTED, PANEL_BG, TEXT_PRI, TEXT_SEC, WARN, BORDER,
    CredentialsPanel, LogPanel, NetworkTable, SectionCard, StatusBadge,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

REPO_DIR = Path(__file__).resolve().parent.parent
LOGO_ASCII = r"""
 ██████╗ █████╗ ██████╗  ██████╗ █████╗ ██████╗     ██╗    ██╗██╗███████╗██╗
██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗    ██║    ██║██║██╔════╝██║
██║     ███████║██████╔╝██║     ███████║██████╔╝    ██║ █╗ ██║██║█████╗  ██║
██║     ██╔══██║██╔═══╝ ██║     ██╔══██║██╔═══╝     ██║███╗██║██║██╔══╝  ██║
╚██████╗██║  ██║██║     ╚██████╗██║  ██║██║         ╚███╔███╔╝██║██║     ██║
 ╚═════╝╚═╝  ╚═╝╚═╝      ╚═════╝╚═╝  ╚═╝╚═╝          ╚══╝╚══╝ ╚═╝╚═╝     ╚═╝
"""


class AttackConfigPanel(ctk.CTkScrollableFrame):
    """Left panel – all attack configuration controls."""

    def __init__(self, master, ctrl: CapCapWifiController, **kw):
        super().__init__(master, fg_color=PANEL_BG, **kw)
        self._ctrl = ctrl
        self._ifaces: List[WirelessInterface] = []
        self._portals: List[PortalSite] = []

        # ── Interface section ────────────────────────────────────
        sec1 = SectionCard(self, "🖧  AĞ ARAYÜZLERİ")
        sec1.pack(fill="x", padx=8, pady=(8, 4))
        b1 = sec1.body()

        ctk.CTkLabel(b1, text="Tarama/Birincil Arayüz:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._iface_var = ctk.StringVar(value="Otomatik")
        self._iface_cb = ctk.CTkComboBox(b1, variable=self._iface_var, width=200,
                                          fg_color=DARK_BG, border_color=BORDER,
                                          button_color=ACCENT, text_color=TEXT_PRI,
                                          font=FONT_UI)
        self._iface_cb.grid(row=0, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b1, text="Jammer Arayüzü:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._jammer_var = ctk.StringVar(value="Otomatik")
        self._jammer_cb = ctk.CTkComboBox(b1, variable=self._jammer_var, width=200,
                                           fg_color=DARK_BG, border_color=BORDER,
                                           button_color=ACCENT, text_color=TEXT_PRI,
                                           font=FONT_UI)
        self._jammer_cb.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b1, text="AP Arayüzü:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._ap_iface_var = ctk.StringVar(value="Otomatik")
        self._ap_iface_cb = ctk.CTkComboBox(b1, variable=self._ap_iface_var, width=200,
                                             fg_color=DARK_BG, border_color=BORDER,
                                             button_color=ACCENT, text_color=TEXT_PRI,
                                             font=FONT_UI)
        self._ap_iface_cb.grid(row=2, column=1, padx=(8, 0), pady=2)

        ctk.CTkButton(b1, text="🔄 Yenile", command=self._refresh_ifaces,
                      fg_color=DARK_BG, border_color=ACCENT, border_width=1,
                      text_color=ACCENT, hover_color="#1b3a2a", font=FONT_UI,
                      width=80).grid(row=3, column=0, columnspan=2, pady=(6, 0))

        # ── Scan section ─────────────────────────────────────────
        sec2 = SectionCard(self, "📡  TARAMA AYARLARI")
        sec2.pack(fill="x", padx=8, pady=4)
        b2 = sec2.body()

        ctk.CTkLabel(b2, text="Süre (sn):", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._scan_time = ctk.CTkEntry(b2, placeholder_text="30", width=80,
                                        fg_color=DARK_BG, border_color=BORDER,
                                        text_color=TEXT_PRI, font=FONT_UI)
        self._scan_time.insert(0, "30")
        self._scan_time.grid(row=0, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(b2, text="Bant:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._band_var = ctk.StringVar(value="bg (2.4 GHz)")
        self._band_cb = ctk.CTkComboBox(
            b2, variable=self._band_var, width=160,
            values=["bg (2.4 GHz)", "a (5 GHz)", "abg (Her İkisi)"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._band_cb.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b2, text="Kanal:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._channel_e = ctk.CTkEntry(b2, placeholder_text="Tümü", width=80,
                                        fg_color=DARK_BG, border_color=BORDER,
                                        text_color=TEXT_PRI, font=FONT_UI)
        self._channel_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

        # ── Target section ───────────────────────────────────────
        sec3 = SectionCard(self, "🎯  HEDEF")
        sec3.pack(fill="x", padx=8, pady=4)
        b3 = sec3.body()

        ctk.CTkLabel(b3, text="SSID:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._essid_e = ctk.CTkEntry(b3, placeholder_text="Boş = Tablodan seç",
                                      width=200, fg_color=DARK_BG,
                                      border_color=BORDER, text_color=TEXT_PRI,
                                      font=FONT_UI)
        self._essid_e.grid(row=0, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b3, text="BSSID:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._bssid_e = ctk.CTkEntry(b3, placeholder_text="AA:BB:CC:DD:EE:FF",
                                      width=200, fg_color=DARK_BG,
                                      border_color=BORDER, text_color=TEXT_PRI,
                                      font=FONT_UI)
        self._bssid_e.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b3, text="CH:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._target_ch_e = ctk.CTkEntry(b3, placeholder_text="6", width=80,
                                          fg_color=DARK_BG, border_color=BORDER,
                                          text_color=TEXT_PRI, font=FONT_UI)
        self._target_ch_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

        # ── Attack section ───────────────────────────────────────
        sec4 = SectionCard(self, "⚡  SALDIRI AYARLARI")
        sec4.pack(fill="x", padx=8, pady=4)
        b4 = sec4.body()

        ctk.CTkLabel(b4, text="Saldırı Türü:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._attack_var = ctk.StringVar(value="Captive Portal")
        self._attack_cb = ctk.CTkComboBox(
            b4, variable=self._attack_var, width=200,
            values=["Captive Portal", "Handshake Snooper"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI,
            command=self._on_attack_change)
        self._attack_cb.grid(row=0, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b4, text="Portal Şablonu:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._portal_var = ctk.StringVar(value="Yükleniyor...")
        self._portal_cb = ctk.CTkComboBox(b4, variable=self._portal_var, width=200,
                                           fg_color=DARK_BG, border_color=BORDER,
                                           button_color=ACCENT, text_color=TEXT_PRI,
                                           font=FONT_UI)
        self._portal_cb.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b4, text="AP Servisi:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._ap_svc_var = ctk.StringVar(value="hostapd")
        self._ap_svc_cb = ctk.CTkComboBox(
            b4, variable=self._ap_svc_var, width=160,
            values=["hostapd", "airbase-ng"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._ap_svc_cb.grid(row=2, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b4, text="Deauth Yöntemi:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=3, column=0, sticky="w", pady=2)
        self._deauth_var = ctk.StringVar(value="aireplay-ng")
        self._deauth_cb = ctk.CTkComboBox(
            b4, variable=self._deauth_var, width=160,
            values=["aireplay-ng", "mdk4"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._deauth_cb.grid(row=3, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(b4, text="Dil:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=4, column=0, sticky="w", pady=2)
        self._lang_var = ctk.StringVar(value="en")
        self._lang_cb = ctk.CTkComboBox(
            b4, variable=self._lang_var, width=100,
            values=self._get_languages(),
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._lang_cb.grid(row=4, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(b4, text="Timeout (dk):", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=5, column=0, sticky="w", pady=2)
        self._timeout_e = ctk.CTkEntry(b4, placeholder_text="Süresiz", width=80,
                                        fg_color=DARK_BG, border_color=BORDER,
                                        text_color=TEXT_PRI, font=FONT_UI)
        self._timeout_e.grid(row=5, column=1, padx=(8, 0), pady=2, sticky="w")

        # Load data
        self._refresh_ifaces()
        self._load_portals()

    # ── public ──────────────────────────────────────────────────

    def fill_from_target(self, target: TargetCandidate) -> None:
        self._bssid_e.delete(0, "end")
        self._bssid_e.insert(0, target.bssid)
        self._essid_e.delete(0, "end")
        self._essid_e.insert(0, target.essid)
        self._target_ch_e.delete(0, "end")
        self._target_ch_e.insert(0, target.channel)

    def build_config(self) -> AttackConfig:
        band_map = {"bg (2.4 GHz)": "bg", "a (5 GHz)": "a", "abg (Her İkisi)": "abg"}
        band = band_map.get(self._band_var.get(), "bg")

        attack_map = {"Captive Portal": AttackType.CAPTIVE_PORTAL,
                      "Handshake Snooper": AttackType.HANDSHAKE_SNOOPER}
        attack = attack_map.get(self._attack_var.get(), AttackType.CAPTIVE_PORTAL)

        iface = self._iface_var.get()
        if iface == "Otomatik":
            iface = ""

        jammer = self._jammer_var.get()
        if jammer == "Otomatik":
            jammer = ""

        ap_iface = self._ap_iface_var.get()
        if ap_iface == "Otomatik":
            ap_iface = ""

        timeout = None
        try:
            t = self._timeout_e.get().strip()
            if t:
                timeout = int(t)
        except ValueError:
            pass

        # Extract portal stem
        portal = self._portal_var.get().split(" [")[0] if self._portals else ""

        return AttackConfig(
            attack_type=attack,
            interface=iface,
            target_bssid=self._bssid_e.get().strip(),
            target_essid=self._essid_e.get().strip(),
            target_channel=self._target_ch_e.get().strip(),
            jammer_interface=jammer,
            ap_interface=ap_iface,
            ap_service=self._ap_svc_var.get(),
            deauth_method=self._deauth_var.get(),
            portal_site=portal,
            language=self._lang_var.get(),
            band=band,
            timeout_minutes=timeout,
        )

    def get_scan_params(self):
        iface = self._iface_var.get()
        if iface == "Otomatik":
            iface = ""
        try:
            st = int(self._scan_time.get().strip())
        except ValueError:
            st = 30
        ch = self._channel_e.get().strip()
        band_map = {"bg (2.4 GHz)": "bg", "a (5 GHz)": "a", "abg (Her İkisi)": "abg"}
        band = band_map.get(self._band_var.get(), "bg")
        return iface, st, ch, band

    # ── private ─────────────────────────────────────────────────

    def _refresh_ifaces(self) -> None:
        def _load():
            ifaces = self._ctrl.list_interfaces()
            self._ifaces = ifaces
            names = ["Otomatik"] + [i.name for i in ifaces]
            self._iface_cb.configure(values=names)
            self._jammer_cb.configure(values=names)
            self._ap_iface_cb.configure(values=names)

        threading.Thread(target=_load, daemon=True).start()

    def _load_portals(self) -> None:
        portals = self._ctrl.list_portals()
        self._portals = portals
        names = [p.display_title for p in portals]
        self._portal_cb.configure(values=names)
        # Default: prefer Turkish Instagram portal
        for i, p in enumerate(portals):
            if "Instagram" in p.name and p.lang.lower() in ("tur", "tr"):
                self._portal_var.set(names[i])
                return
        if names:
            self._portal_var.set(names[0])

    def _on_attack_change(self, _val) -> None:
        is_portal = self._attack_var.get() == "Captive Portal"
        state = "normal" if is_portal else "disabled"
        self._portal_cb.configure(state=state)
        self._ap_svc_cb.configure(state=state)

    @staticmethod
    def _get_languages() -> List[str]:
        lang_dir = REPO_DIR / "language"
        if lang_dir.is_dir():
            return sorted(
                p.stem for p in lang_dir.iterdir() if p.suffix == ".sh"
            )
        return ["en", "tr", "de", "fr", "es", "it", "ru", "pt", "pl", "zh"]


# ─────────────────────────── Main Window ────────────────────────────

class CapCapWifiApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CapCapWifi GUI  –  Wi-Fi Security Auditor")
        self.geometry("1280x820")
        self.minsize(1024, 680)
        self.configure(fg_color=DARK_BG)
        self.iconname("CapCapWifi")

        self._ctrl = CapCapWifiController()
        self._ctrl.on_state_change = self._on_state
        self._ctrl.on_log = self._on_log
        self._ctrl.on_candidates = self._on_candidates
        self._ctrl.on_credential = self._on_credential

        self._build_ui()
        self._update_status(AttackState.IDLE)

        # Poll state for button enable/disable
        self._poll()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Top bar ──────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="#080808", height=52)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="⚡ CapCapWifi", font=("Courier New", 18, "bold"),
                     text_color=ACCENT).pack(side="left", padx=16, pady=8)
        ctk.CTkLabel(top, text="Wi-Fi Security Auditor – Python GUI",
                     font=FONT_UI, text_color=MUTED).pack(side="left")

        # Status badge – right side
        self._status_badge = StatusBadge(top)
        self._status_badge.pack(side="right", padx=16, pady=4)

        # ── Body (3-column layout) ───────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=0)
        body.columnconfigure(0, weight=0, minsize=310)
        body.columnconfigure(1, weight=2)
        body.columnconfigure(2, weight=1, minsize=320)
        body.rowconfigure(0, weight=1)

        # Left: config panel
        self._config_panel = AttackConfigPanel(body, self._ctrl)
        self._config_panel.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)

        # Centre: tab view (Networks / Credentials)
        centre = ctk.CTkFrame(body, fg_color="transparent")
        centre.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        centre.rowconfigure(0, weight=1)
        centre.rowconfigure(1, weight=0)
        centre.columnconfigure(0, weight=1)

        self._tabs = ctk.CTkTabview(centre, fg_color=PANEL_BG,
                                    segmented_button_fg_color=CARD_BG,
                                    segmented_button_selected_color=ACCENT,
                                    segmented_button_selected_hover_color="#00b35a",
                                    segmented_button_unselected_color=CARD_BG,
                                    text_color=TEXT_PRI)
        self._tabs.grid(row=0, column=0, sticky="nsew")
        self._tabs.add("📡 Ağlar")
        self._tabs.add("🔑 Şifreler")

        # Network table
        self._net_table = NetworkTable(
            self._tabs.tab("📡 Ağlar"),
            on_select=self._on_target_select)
        self._net_table.pack(fill="both", expand=True)

        # Credentials panel
        self._cred_panel = CredentialsPanel(self._tabs.tab("🔑 Şifreler"))
        self._cred_panel.pack(fill="both", expand=True)

        # Action buttons
        btn_row = ctk.CTkFrame(centre, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        btn_row.columnconfigure((0, 1, 2, 3), weight=1)

        self._btn_scan = ctk.CTkButton(
            btn_row, text="🔍 Tara", command=self._do_scan,
            fg_color=ACCENT, text_color="#000", hover_color="#00b35a",
            font=FONT_UI_B, height=38)
        self._btn_scan.grid(row=0, column=0, padx=4, sticky="ew")

        self._btn_attack = ctk.CTkButton(
            btn_row, text="⚡ Saldır", command=self._do_attack,
            fg_color=WARN, text_color="#000", hover_color="#e65100",
            font=FONT_UI_B, height=38)
        self._btn_attack.grid(row=0, column=1, padx=4, sticky="ew")

        self._btn_stop = ctk.CTkButton(
            btn_row, text="⏹ Durdur", command=self._do_stop,
            fg_color=DANGER, text_color="#fff", hover_color="#c62828",
            font=FONT_UI_B, height=38, state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=4, sticky="ew")

        self._btn_clear = ctk.CTkButton(
            btn_row, text="🗑 Temizle", command=self._do_clear,
            fg_color=CARD_BG, text_color=MUTED, hover_color="#2a2a2a",
            font=FONT_UI_B, height=38, border_color=BORDER, border_width=1)
        self._btn_clear.grid(row=0, column=3, padx=4, sticky="ew")

        # Right: log panel
        self._log_panel = LogPanel(body)
        self._log_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)

        # ── Bottom status bar ────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="#080808", height=24)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._bar_label = ctk.CTkLabel(bar, text="Hazır  |  Kali Linux üzerinde root olarak çalıştırın",
                                        font=("Courier New", 9), text_color=MUTED)
        self._bar_label.pack(side="left", padx=12)
        ctk.CTkLabel(bar, text="github.com/sametuca/capcapwifi",
                     font=("Courier New", 9), text_color="#333").pack(side="right", padx=12)

    # ── Callbacks (called from background threads → schedule GUI) ─

    def _on_state(self, state: AttackState) -> None:
        self.after(0, self._update_status, state)

    def _on_log(self, msg: str, level: str) -> None:
        self.after(0, self._log_panel.append, msg, level)

    def _on_candidates(self, candidates) -> None:
        self.after(0, self._net_table.load, candidates)
        self.after(0, self._tabs.set, "📡 Ağlar")

    def _on_credential(self, cred: CapturedCredential) -> None:
        self.after(0, self._cred_panel.add, cred)
        self.after(0, self._tabs.set, "🔑 Şifreler")

    def _on_target_select(self, target: TargetCandidate) -> None:
        self._config_panel.fill_from_target(target)
        self._log_panel.append(
            f"[+] Hedef seçildi: {target.clean_essid} ({target.bssid})  CH{target.channel}",
            "info")

    # ── Button handlers ─────────────────────────────────────────

    def _do_scan(self) -> None:
        iface, st, ch, band = self._config_panel.get_scan_params()
        self._log_panel.append(f"[*] Tarama başlatılıyor... ({st} sn)", "info")
        self._ctrl.start_scan(interface=iface, scan_time=st, channel=ch, band=band)

    def _do_attack(self) -> None:
        cfg = self._config_panel.build_config()
        if not cfg.target_bssid and not cfg.target_essid:
            tgt = self._net_table.selected()
            if tgt:
                cfg.target_bssid = tgt.bssid
                cfg.target_essid = tgt.essid
                cfg.target_channel = tgt.channel
            else:
                self._log_panel.append(
                    "[!] Önce tablodan bir hedef seçin veya BSSID/SSID girin.", "warn")
                return
        self._log_panel.append(
            f"[*] Saldırı: {cfg.attack_type.value}  →  {cfg.target_essid or cfg.target_bssid}",
            "info")
        self._ctrl.start_attack(cfg)

    def _do_stop(self) -> None:
        self._ctrl.stop()

    def _do_clear(self) -> None:
        self._log_panel.clear()
        self._net_table.clear()

    # ── Polling / state sync ─────────────────────────────────────

    def _update_status(self, state: AttackState) -> None:
        self._status_badge.update_state(state.value)
        busy = state in (AttackState.SCANNING, AttackState.STARTING, AttackState.RUNNING)
        idle = state in (AttackState.IDLE, AttackState.STOPPED,
                         AttackState.ERROR, AttackState.CREDENTIALS_FOUND,
                         AttackState.HANDSHAKE_CAPTURED)
        self._btn_scan.configure(state="disabled" if busy else "normal")
        self._btn_attack.configure(state="disabled" if busy else "normal")
        self._btn_stop.configure(state="normal" if busy else "disabled")

        labels = {
            AttackState.IDLE: "Hazır",
            AttackState.SCANNING: "Ağlar taranıyor...",
            AttackState.STARTING: "Saldırı başlatılıyor...",
            AttackState.RUNNING: "Saldırı devam ediyor...",
            AttackState.HANDSHAKE_CAPTURED: "Handshake yakalandı!",
            AttackState.CREDENTIALS_FOUND: "Şifre bulundu!",
            AttackState.STOPPED: "Durduruldu",
            AttackState.ERROR: "Hata – log'u kontrol edin",
        }
        self._bar_label.configure(text=labels.get(state, ""))

    def _poll(self) -> None:
        """Periodic sanity-check (nothing heavy – just keeps state in sync)."""
        self.after(2000, self._poll)


# ─────────────────────────── Entry point ────────────────────────────

if __name__ == "__main__":
    app = CapCapWifiApp()
    app.mainloop()
