"""
CapCapWifi – Python GUI Ana Penceresi

CustomTkinter tabanlı, karanlık temalı, hibrit denetleyici (capcapwifi.sh → --auto).

Arayüzün amacı tek bir soruya cevap vermek: "şu anda neredeyim, sırada ne var?"
Bu yüzden her ekranda kısa bir açıklama, üstte adım çubuğu ve altta dinamik
"şimdi ne yapmalıyım" satırı bulunur.

Arayüz dili (EN/TR) sağ üstten değiştirilir; pencere yeniden kurulur, çalışan
saldırı etkilenmez.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

import customtkinter as ctk

# Local modules
import i18n
from i18n import t
from controller import CapCapWifiController
from models import (
    AttackConfig,
    AttackState,
    AttackType,
    CapturedCredential,
    EnvironmentCheck,
    HandshakeFile,
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)
from widgets import (
    ACCENT, ACCENT_DK, ACCENT_DIM, ACCENT2, ACCENT2_DIM, CARD_BG, CARD_HOVER,
    DANGER, DANGER_DIM, DARK_BG, ELEV_BG, FONT_MONO_S, FONT_TITLE, FONT_UI,
    FONT_UI_B, FONT_UI_S, FONT_UI_SB, MUTED, PANEL_BG, TEXT_PRI, TEXT_SEC,
    WARN, WARN_DIM, BORDER,
    Checklist, CredentialsPanel, GuideBar, LogPanel, NetworkTable,
    NextStepGuideCard, SectionCard, StatusBadge,
)

# Üst/alt çubuk gibi "çerçeve" yüzeyleri için uygulama zemininden bir tık
# daha koyu ton; pencereye çerçeve hissi verir.
CHROME_BG = "#06080B"
FOOTER_FG = "#333A45"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

REPO_DIR = Path(__file__).resolve().parent.parent

BAND_CODES = ("bg", "a", "abg")

ATTACK_TYPES = (AttackType.CAPTIVE_PORTAL, AttackType.HANDSHAKE_SNOOPER)


def band_labels() -> Dict[str, str]:
    """Görünen etiket → CLI değeri, aktif dile göre."""
    return {t(f"band.{code}"): code for code in BAND_CODES}


def attack_labels() -> Dict[str, AttackType]:
    return {attack.label: attack for attack in ATTACK_TYPES}


# ─────────────────────── Left configuration panel ───────────────────


class AttackConfigPanel(ctk.CTkScrollableFrame):
    """Sol sütun: adaptör, tarama, hedef ve saldırı ayarları."""

    def __init__(self, master, ctrl: CapCapWifiController,
                 on_change=None, **kw):
        super().__init__(master, fg_color=PANEL_BG, **kw)
        self._ctrl = ctrl
        self._on_change = on_change
        self._ifaces: List[WirelessInterface] = []
        self._portals: List[PortalSite] = []
        self._portal_by_title: Dict[str, PortalSite] = {}
        self._attack_labels = attack_labels()
        self._band_labels = band_labels()

        self._build_interfaces()
        self._build_scan()
        self._build_target()
        self._build_attack()

        self._refresh_ifaces()
        self._load_portals()

    # ── sections ────────────────────────────────────────────────

    def _build_interfaces(self) -> None:
        sec = SectionCard(
            self, t("config.adapter.title"),
            t("config.adapter.desc"),
        )
        sec.pack(fill="x", padx=4, pady=(4, 4))
        body = sec.body()

        self._iface_var = self._combo_row(body, 0, t("config.adapter.primary"))
        self._jammer_var = self._combo_row(body, 1, t("config.adapter.jammer"))
        self._ap_iface_var = self._combo_row(body, 2, t("config.adapter.ap"))

        ctk.CTkLabel(
            body,
            text=t("config.adapter.note"),
            font=FONT_UI_S, text_color=MUTED, anchor="w",
            justify="left", wraplength=250,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ctk.CTkButton(body, text=f"🔄 {t('config.adapter.refresh')}",
                      command=self._refresh_ifaces,
                      fg_color=DARK_BG, border_color=ACCENT, border_width=1,
                      text_color=ACCENT, hover_color=ACCENT_DIM, font=FONT_UI,
                      height=26).grid(row=4, column=0, columnspan=2,
                                      sticky="ew", pady=(6, 0))

    def _build_scan(self) -> None:
        sec = SectionCard(
            self, t("config.scan.title"),
            t("config.scan.desc"),
        )
        sec.pack(fill="x", padx=4, pady=4)
        body = sec.body()

        ctk.CTkLabel(body, text=t("config.scan.time"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._scan_time = ctk.CTkEntry(body, width=80, fg_color=DARK_BG,
                                       border_color=BORDER, text_color=TEXT_PRI,
                                       font=FONT_UI)
        self._scan_time.insert(0, "30")
        self._scan_time.grid(row=0, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(body, text=t("config.scan.band"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._band_var = ctk.StringVar(value=t("band.bg"))
        ctk.CTkComboBox(body, variable=self._band_var, width=160,
                        values=list(self._band_labels),
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text=t("config.scan.channel"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._channel_e = ctk.CTkEntry(body, placeholder_text=t("config.scan.channel_ph"),
                                       width=80, fg_color=DARK_BG, border_color=BORDER,
                                       text_color=TEXT_PRI, font=FONT_UI)
        self._channel_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

    def _build_target(self) -> None:
        sec = SectionCard(
            self, t("config.target.title"),
            t("config.target.desc"),
        )
        sec.pack(fill="x", padx=4, pady=4)
        body = sec.body()

        ctk.CTkLabel(body, text=t("config.target.ssid"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._essid_e = ctk.CTkEntry(body, placeholder_text=t("config.target.ssid_ph"),
                                     width=200, fg_color=DARK_BG, border_color=BORDER,
                                     text_color=TEXT_PRI, font=FONT_UI)
        self._essid_e.grid(row=0, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text=t("config.target.bssid"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._bssid_e = ctk.CTkEntry(body, placeholder_text="AA:BB:CC:DD:EE:FF",
                                     width=200, fg_color=DARK_BG,
                                     border_color=BORDER, text_color=TEXT_PRI,
                                     font=FONT_UI)
        self._bssid_e.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text=t("config.target.channel"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._target_ch_e = ctk.CTkEntry(body, placeholder_text="6", width=80,
                                         fg_color=DARK_BG, border_color=BORDER,
                                         text_color=TEXT_PRI, font=FONT_UI)
        self._target_ch_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

        self._target_note = ctk.CTkLabel(
            body, text=t("config.target.none"), font=FONT_UI_S,
            text_color=MUTED, anchor="w", justify="left", wraplength=250,
        )
        self._target_note.grid(row=3, column=0, columnspan=2, sticky="w",
                               pady=(6, 0))

    def _build_attack(self) -> None:
        sec = SectionCard(
            self, t("config.attack.title"),
            t("config.attack.desc"),
        )
        sec.pack(fill="x", padx=4, pady=(4, 10))
        body = sec.body()

        ctk.CTkLabel(body, text=t("config.attack.type"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._attack_var = ctk.StringVar(value=list(self._attack_labels)[0])
        ctk.CTkComboBox(body, variable=self._attack_var, width=220,
                        values=list(self._attack_labels),
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI,
                        command=self._on_attack_change).grid(
            row=0, column=1, padx=(8, 0), pady=2)

        self._attack_desc = ctk.CTkLabel(
            body, text="", font=FONT_UI_S, text_color=TEXT_SEC, anchor="w",
            justify="left", wraplength=250,
        )
        self._attack_desc.grid(row=1, column=0, columnspan=2, sticky="w",
                               pady=(4, 6))

        ctk.CTkLabel(body, text=t("config.attack.portal"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._portal_var = ctk.StringVar(value=t("config.attack.portal_loading"))
        self._portal_cb = ctk.CTkComboBox(
            body, variable=self._portal_var, width=220,
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI, command=self._on_portal_change)
        self._portal_cb.grid(row=2, column=1, padx=(8, 0), pady=2)

        self._portal_desc = ctk.CTkLabel(
            body, text="", font=FONT_UI_S, text_color=MUTED, anchor="w",
            justify="left", wraplength=250,
        )
        self._portal_desc.grid(row=3, column=0, columnspan=2, sticky="w",
                               pady=(2, 6))

        ctk.CTkLabel(body, text=t("config.attack.ap_service"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=4, column=0, sticky="w", pady=2)
        self._ap_svc_var = ctk.StringVar(value="hostapd")
        self._ap_svc_cb = ctk.CTkComboBox(
            body, variable=self._ap_svc_var, width=160,
            values=["hostapd", "airbase-ng"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._ap_svc_cb.grid(row=4, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text=t("config.attack.deauth"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=5, column=0, sticky="w", pady=2)
        self._deauth_var = ctk.StringVar(value="aireplay-ng")
        ctk.CTkComboBox(body, variable=self._deauth_var, width=160,
                        values=["aireplay-ng", "mdk4"],
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=5, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text=t("config.attack.lang"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=6, column=0, sticky="w", pady=2)
        clipped_default = "tur" if i18n.get_language() == "tr" else "en"
        self._lang_var = ctk.StringVar(value=clipped_default)
        ctk.CTkComboBox(body, variable=self._lang_var, width=100,
                        values=self._get_languages(),
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=6, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(body, text=t("config.attack.timeout"), font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=7, column=0, sticky="w", pady=2)
        self._timeout_e = ctk.CTkEntry(body, placeholder_text=t("config.attack.timeout_ph"),
                                       width=80, fg_color=DARK_BG, border_color=BORDER,
                                       text_color=TEXT_PRI, font=FONT_UI)
        self._timeout_e.grid(row=7, column=1, padx=(8, 0), pady=2, sticky="w")

        self._on_attack_change(self._attack_var.get())

    # ── helpers ─────────────────────────────────────────────────

    def _combo_row(self, body, row: int, label: str) -> ctk.StringVar:
        ctk.CTkLabel(body, text=label, font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=row, column=0,
                                               sticky="w", pady=2)
        var = ctk.StringVar(value=t("config.auto"))
        ctk.CTkComboBox(body, variable=var, width=200,
                        values=[t("config.auto")],
                        fg_color=DARK_BG, border_color=BORDER,
                        button_color=ACCENT, text_color=TEXT_PRI,
                        font=FONT_UI).grid(row=row, column=1, padx=(8, 0), pady=2)
        var.trace_add("write", lambda *_: self._notify())
        return var

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    # ── language re-render support ──────────────────────────────

    def snapshot(self) -> Dict[str, str]:
        """Dil değişiminde kaybolmaması gereken tüm alanlar."""
        return {
            "iface": self._iface_var.get(),
            "jammer": self._jammer_var.get(),
            "ap_iface": self._ap_iface_var.get(),
            "scan_time": self._scan_time.get(),
            "band": self._band_labels.get(self._band_var.get(), "bg"),
            "channel": self._channel_e.get(),
            "essid": self._essid_e.get(),
            "bssid": self._bssid_e.get(),
            "target_channel": self._target_ch_e.get(),
            "attack": self.attack_type.value,
            "portal": self._portal_var.get(),
            "ap_service": self._ap_svc_var.get(),
            "deauth": self._deauth_var.get(),
            "cli_language": self._lang_var.get(),
            "timeout": self._timeout_e.get(),
            "target_note": self._target_note.cget("text"),
            "target_note_color": str(self._target_note.cget("text_color")),
        }

    def restore(self, data: Optional[Dict[str, str]]) -> None:
        if not data:
            return
        auto = t("config.auto")
        for var, key in (
            (self._iface_var, "iface"),
            (self._jammer_var, "jammer"),
            (self._ap_iface_var, "ap_iface"),
        ):
            value = data.get(key, "")
            var.set(value if value and value != auto else auto)

        self._scan_time.delete(0, "end")
        self._scan_time.insert(0, data.get("scan_time", "30"))

        band = data.get("band", "bg")
        self._band_var.set(t(f"band.{band}") if band in BAND_CODES
                           else t("band.bg"))

        entry_values = (
            (self._channel_e, "channel"),
            (self._essid_e, "essid"),
            (self._bssid_e, "bssid"),
            (self._target_ch_e, "target_channel"),
            (self._timeout_e, "timeout"),
        )
        for entry, key in entry_values:
            entry.delete(0, "end")
            value = data.get(key, "")
            if value:
                entry.insert(0, value)

        attack_value = data.get("attack", AttackType.CAPTIVE_PORTAL.value)
        attack = next((a for a in ATTACK_TYPES if a.value == attack_value),
                      AttackType.CAPTIVE_PORTAL)
        self._attack_var.set(attack.label)
        self._on_attack_change()

        portal = data.get("portal", "")
        if portal in self._portal_by_title:
            self._portal_var.set(portal)
        self._on_portal_change()

        self._ap_svc_var.set(data.get("ap_service", "hostapd"))
        self._deauth_var.set(data.get("deauth", "aireplay-ng"))

        cli_language = data.get("cli_language", "")
        if cli_language in self._get_languages():
            self._lang_var.set(cli_language)

        note = data.get("target_note", "")
        if note:
            self._target_note.configure(
                text=note,
                text_color=data.get("target_note_color", MUTED),
            )
        self._notify()

    # ── public ──────────────────────────────────────────────────

    def fill_from_target(self, target: TargetCandidate) -> None:
        for entry, value in (
            (self._bssid_e, target.bssid),
            (self._essid_e, target.essid),
            (self._target_ch_e, target.channel),
        ):
            entry.delete(0, "end")
            entry.insert(0, value)

        colour = WARN if target.is_dfs else (ACCENT if target.has_clients else MUTED)
        self._target_note.configure(text=target.recommendation, text_color=colour)
        self._notify()

    def clear_target(self) -> None:
        for entry in (self._bssid_e, self._essid_e, self._target_ch_e):
            entry.delete(0, "end")
        self._target_note.configure(text=t("config.target.none"), text_color=MUTED)
        self._notify()

    @property
    def attack_type(self) -> AttackType:
        return self._attack_labels.get(self._attack_var.get(),
                                       AttackType.CAPTIVE_PORTAL)

    @property
    def language(self) -> str:
        return self._lang_var.get() or ("tur" if i18n.get_language() == "tr" else "en")

    @property
    def selected_portal(self) -> Optional[PortalSite]:
        return self._portal_by_title.get(self._portal_var.get())

    def build_config(self) -> AttackConfig:
        timeout = None
        try:
            raw = self._timeout_e.get().strip()
            if raw:
                timeout = int(raw)
        except ValueError:
            timeout = None

        portal = self.selected_portal

        return AttackConfig(
            attack_type=self.attack_type,
            interface=self._value(self._iface_var),
            target_bssid=self._bssid_e.get().strip(),
            target_essid=self._essid_e.get().strip(),
            target_channel=self._target_ch_e.get().strip(),
            jammer_interface=self._value(self._jammer_var),
            ap_interface=self._value(self._ap_iface_var),
            ap_service=self._ap_svc_var.get(),
            deauth_method=self._deauth_var.get(),
            portal_site=portal.site_id if portal else "Instagram_tur",
            language=self._lang_var.get(),
            band=self._band_labels.get(self._band_var.get(), "bg"),
            timeout_minutes=timeout,
        )

    def get_scan_params(self):
        try:
            scan_time = int(self._scan_time.get().strip())
        except ValueError:
            scan_time = 30
        return (
            self._value(self._iface_var),
            scan_time,
            self._channel_e.get().strip(),
            self._band_labels.get(self._band_var.get(), "bg"),
        )

    # ── private ─────────────────────────────────────────────────

    @staticmethod
    def _value(var: ctk.StringVar) -> str:
        value = var.get().strip()
        return "" if value == t("config.auto") else value

    def _refresh_ifaces(self) -> None:
        def _load():
            ifaces = self._ctrl.list_interfaces()
            self._ifaces = ifaces
            names = [t("config.auto")] + [i.name for i in ifaces]
            for var in (self._iface_var, self._jammer_var, self._ap_iface_var):
                if var.get() not in names:
                    var.set(t("config.auto"))

        threading.Thread(target=_load, daemon=True).start()

    def _load_portals(self) -> None:
        portals = self._ctrl.list_portals()
        self._portals = portals
        self._portal_by_title = {p.display_title: p for p in portals}
        titles = [p.display_title for p in portals]
        self._portal_cb.configure(values=titles)

        for portal in portals:
            if "Instagram" in portal.name and portal.lang.lower() in ("tur", "tr"):
                self._portal_var.set(portal.display_title)
                break
        else:
            if titles:
                self._portal_var.set(titles[0])
        self._on_portal_change(self._portal_var.get())

    def _on_attack_change(self, _value: str = "") -> None:
        portal_attack = self.attack_type is AttackType.CAPTIVE_PORTAL
        state = "normal" if portal_attack else "disabled"
        self._portal_cb.configure(state=state)
        self._ap_svc_cb.configure(state=state)

        attack = self.attack_type
        self._attack_desc.configure(
            text=t("config.attack.desc_format",
                   summary=attack.summary,
                   need=attack.what_you_need,
                   next=attack.what_happens_next),
        )
        self._notify()

    def _on_portal_change(self, _value: str = "") -> None:
        portal = self.selected_portal
        if portal:
            self._portal_desc.configure(text=portal.description)
        else:
            self._portal_desc.configure(text="")
        self._notify()

    @staticmethod
    def _get_languages() -> List[str]:
        lang_dir = REPO_DIR / "language"
        if lang_dir.is_dir():
            return sorted(p.stem for p in lang_dir.iterdir() if p.suffix == ".sh")
        return ["en", "tur"]


# ─────────────────────────── Main Window ────────────────────────────


class CapCapWifiApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(t("app.title"))
        self._apply_window_geometry()
        self.configure(fg_color=DARK_BG)
        self.iconname("CapCapWifi")

        self._ctrl = CapCapWifiController()
        self._ctrl.on_state_change = self._on_state
        self._ctrl.on_log = self._on_log
        self._ctrl.on_candidates = self._on_candidates
        self._ctrl.on_credential = self._on_credential
        self._ctrl.on_handshake = self._on_handshake
        self._ctrl.on_environment = self._on_environment
        self._ctrl.on_dependency_install = self._on_dependency_install

        self._state = AttackState.IDLE
        self._target: Optional[TargetCandidate] = None
        self._env_checks: List[EnvironmentCheck] = []
        self._install_attempted = False
        self._install_visible = False
        self._step = 0
        self._active_tab = "networks"
        self._ui_ready = False

        self._build_ui()
        self._update_status(AttackState.IDLE)
        self._fade_in()
        self.after(150, self._maximize)
        self.after(200, lambda: self._ctrl.check_environment())
        self.after(500, self._refresh_handshake_archive)

    # ── Pencere yerleşimi / efektler ────────────────────────────

    def _apply_window_geometry(self) -> None:
        """Pencereyi ekrana sığdır ve büyük aç.

        Sabit 1360x860, 1024x768 bir ekranda pencerenin sağ/alt kısmını
        ekran dışında bırakıyordu: adım çubuğu ve eylem düğmeleri kesiliyordu.
        """
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1360, max(900, screen_w - 40))
        height = min(880, max(600, screen_h - 90))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(980, width), min(620, height))
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", lambda _e: self._set_fullscreen(False))

    def _maximize(self) -> None:
        """Açılışta ekranı doldur; küçük pencerede panel düzeni sıkışıyor."""
        try:
            if sys.platform.startswith("linux"):
                self.attributes("-zoomed", True)
            else:
                self.state("zoomed")
        except Exception:
            pass

    def _set_fullscreen(self, enabled: bool) -> None:
        try:
            self.attributes("-fullscreen", enabled)
        except Exception:
            pass

    def _toggle_fullscreen(self, _event=None) -> None:
        try:
            self._set_fullscreen(not self.attributes("-fullscreen"))
        except Exception:
            pass

    def _fade_in(self, step: int = 0) -> None:
        """Kısa açılış geçişi; alfa desteklenmiyorsa sessizce atlanır."""
        try:
            self.attributes("-alpha", min(1.0, 0.45 + step * 0.09))
        except Exception:
            return
        if step < 6:
            self.after(18, self._fade_in, step + 1)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self._ui_ready = False
        self.title(t("app.title"))

        top = ctk.CTkFrame(self, fg_color=CHROME_BG, height=64,
                           corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Logo: yuvarlak köşeli yeşil rozet içinde şimşek — markaya kimlik.
        logo = ctk.CTkLabel(top, text="⚡", font=("Inter", 18),
                            text_color=DARK_BG, fg_color=ACCENT,
                            corner_radius=9, width=32, height=32)
        logo.pack(side="left", padx=(18, 10), pady=16)
        ctk.CTkLabel(top, text="CapCapWifi", font=("Inter", 18, "bold"),
                     text_color=TEXT_PRI).pack(side="left", pady=8)
        ctk.CTkLabel(top, text=f"  {t('app.subtitle')}",
                     font=FONT_UI, text_color=MUTED).pack(side="left", pady=8)

        self._status_badge = StatusBadge(top)
        self._status_badge.pack(side="right", padx=(8, 18), pady=12)

        # Dil değiştirici: EN / TR, anında yeniden çizer.
        self._lang_switch = ctk.CTkSegmentedButton(
            top, values=["EN", "TR"], command=self._on_language_selected,
            font=FONT_UI_B, height=28, corner_radius=8,
            fg_color=CARD_BG, selected_color=ACCENT_DIM,
            selected_hover_color=ACCENT_DIM, unselected_color=CARD_BG,
            unselected_hover_color=CARD_HOVER, text_color=TEXT_PRI,
        )
        self._lang_switch.pack(side="right", padx=(0, 6), pady=12)
        self._lang_switch.set("TR" if i18n.get_language() == "tr" else "EN")

        ctk.CTkFrame(self, fg_color=ACCENT, height=2,
                     corner_radius=0).pack(fill="x")

        steps = tuple(t(f"step.{key}") for key in
                      ("adapter", "scan", "target", "attack", "result"))
        self._guide = GuideBar(self, steps)
        self._guide.pack(fill="x", padx=12, pady=(8, 0))
        self._guide.set_active(self._step)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=280)
        body.columnconfigure(1, weight=5, minsize=380)
        body.columnconfigure(2, weight=0, minsize=270)
        body.rowconfigure(0, weight=1)

        # Left: configuration
        self._config_panel = AttackConfigPanel(
            body, self._ctrl, on_change=self._refresh_hint)
        self._config_panel.grid(row=0, column=0, sticky="nsew",
                                padx=(12, 5), pady=10)

        # Centre: tabs
        centre = ctk.CTkFrame(body, fg_color="transparent")
        centre.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        centre.rowconfigure(1, weight=1)
        centre.columnconfigure(0, weight=1)

        # Handshake yakalandığında beliren dinamik rehberlik kartı
        self._next_step_guide = NextStepGuideCard(
            centre,
            on_start_portal=self._start_portal_from_guide,
            on_crack_wordlist=self._start_crack_from_guide,
            on_dismiss=self._dismiss_guide,
        )

        self._tabs = ctk.CTkTabview(
            centre, fg_color=PANEL_BG,
            segmented_button_fg_color=CARD_BG,
            segmented_button_selected_color=ACCENT_DIM,
            segmented_button_selected_hover_color=ACCENT_DIM,
            segmented_button_unselected_color=CARD_BG,
            segmented_button_unselected_hover_color=CARD_HOVER,
            text_color=TEXT_PRI,
            corner_radius=12,
        )
        self._tabs.grid(row=1, column=0, sticky="nsew")
        self._tab_names = {
            "networks": f"📡  {t('app.tab.networks')}",
            "credentials": f"🔑  {t('app.tab.credentials')}",
            "help": f"❓  {t('app.tab.help')}",
        }
        tab_nets = self._tabs.add(self._tab_names["networks"])
        tab_creds = self._tabs.add(self._tab_names["credentials"])
        tab_help = self._tabs.add(self._tab_names["help"])

        self._net_table = NetworkTable(tab_nets, on_select=self._on_target_select)
        self._net_table.pack(fill="both", expand=True)

        self._cred_panel = CredentialsPanel(
            tab_creds,
            on_use_portal=self._start_portal_from_guide,
            on_crack=self._start_crack_from_guide,
        )
        self._cred_panel.pack(fill="both", expand=True)

        help_box = ctk.CTkFrame(tab_help, fg_color="transparent")
        help_box.pack(fill="both", expand=True)
        help_text = ctk.CTkTextbox(help_box, fg_color=DARK_BG,
                                   text_color=TEXT_PRI, font=FONT_MONO_S,
                                   wrap="word", corner_radius=10,
                                   border_width=1, border_color=BORDER)
        help_text.pack(fill="both", expand=True, padx=6, pady=6)
        help_text.insert("1.0", t("help.text"))
        help_text.configure(state="disabled")

        # Action buttons
        btn_row = ctk.CTkFrame(centre, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            btn_row.columnconfigure(column, weight=1)

        self._btn_scan = ctk.CTkButton(
            btn_row, text=f"🔍  {t('app.btn.scan')}", command=self._do_scan,
            fg_color=ACCENT, text_color="#052012", hover_color=ACCENT_DK,
            font=FONT_UI_B, height=42, width=1, corner_radius=12)
        self._btn_scan.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._btn_attack = ctk.CTkButton(
            btn_row, text=f"⚡  {t('app.btn.attack')}", command=self._do_attack,
            fg_color=WARN, text_color="#201500", hover_color="#FFC44D",
            font=FONT_UI_B, height=42, width=1, corner_radius=12)
        self._btn_attack.grid(row=0, column=1, padx=5, sticky="ew")

        self._btn_stop = ctk.CTkButton(
            btn_row, text=f"⏹  {t('app.btn.stop')}", command=self._do_stop,
            fg_color="transparent", text_color=DANGER, hover_color=DANGER_DIM,
            border_width=1, border_color=DANGER, font=FONT_UI_B,
            height=42, width=1, corner_radius=12, state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=5, sticky="ew")

        self._btn_clear = ctk.CTkButton(
            btn_row, text=f"🗑  {t('app.btn.clear')}", command=self._do_clear,
            fg_color="transparent", text_color=TEXT_SEC, hover_color=CARD_HOVER,
            font=FONT_UI_B, height=42, width=1, border_color=BORDER,
            border_width=1, corner_radius=12)
        self._btn_clear.grid(row=0, column=3, padx=(5, 0), sticky="ew")

        # Right column: health card above log
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(5, 12), pady=10)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        health = ctk.CTkFrame(right, fg_color=CARD_BG, corner_radius=12,
                              border_width=1, border_color=BORDER)
        health.grid(row=0, column=0, sticky="ew")
        head = ctk.CTkFrame(health, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=f"🩺  {t('app.health.title')}", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(head, text="🔄", width=30, height=26,
                      command=lambda: self._ctrl.check_environment(),
                      fg_color="transparent", border_color=BORDER,
                      border_width=1, text_color=TEXT_SEC,
                      hover_color=CARD_HOVER,
                      font=FONT_UI).pack(side="right")
        self._btn_install = ctk.CTkButton(
            head, text=f"📦 {t('app.health.install')}", width=118, height=26,
            command=self._start_install, fg_color="transparent",
            border_color=WARN, border_width=1, text_color=WARN,
            hover_color=WARN_DIM, font=FONT_UI_S, corner_radius=10)
        self._btn_install.pack(side="right", padx=(0, 6))

        ctk.CTkLabel(
            health,
            text=t("app.health.desc"),
            font=FONT_UI_S, text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 4))

        self._install_bar = ctk.CTkProgressBar(health, height=6,
                                               progress_color=ACCENT2,
                                               fg_color=BORDER)
        self._install_label = ctk.CTkLabel(
            health, text="", font=FONT_UI_S, text_color=ACCENT2, anchor="w")

        self._health_scroll = ctk.CTkScrollableFrame(
            health, fg_color="transparent", height=230)
        self._health_scroll.pack(fill="x", padx=8, pady=(0, 8))
        self._checklist = Checklist(self._health_scroll)
        self._checklist.pack(fill="x")
        self._checklist.show([EnvironmentCheck(
            name=t("app.health.checking.name"), ok=False,
            detail=t("app.health.checking.detail"), hint="")])

        self._log_panel = LogPanel(right)
        self._log_panel.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        # Bottom hint bar
        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x")
        bar = ctk.CTkFrame(self, fg_color=CHROME_BG, height=34,
                           corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._bar_label = ctk.CTkLabel(
            bar, text="", font=FONT_UI_S, text_color=TEXT_SEC,
            anchor="w", justify="left")
        self._bar_label.pack(side="left", padx=16)
        ctk.CTkLabel(bar, text="github.com/sametuca/capcapwifi",
                     font=FONT_MONO_S,
                     text_color=FOOTER_FG).pack(side="right", padx=16)

        self._tabs.set(self._tab_names[self._active_tab])
        self._ui_ready = True
        self._refresh_hint()

    # ── Language switching ──────────────────────────────────────

    def _on_language_selected(self, value: str) -> None:
        code = "tr" if str(value).strip().upper() == "TR" else "en"
        if code == i18n.get_language():
            return
        self._apply_language(code)

    def _apply_language(self, code: str) -> None:
        """Dili değiştirip pencereyi yeniden kurar; saldırı süreci etkilenmez."""
        snapshot = self._config_panel.snapshot()
        candidates = self._net_table.candidates
        guide_hf = getattr(self._next_step_guide, "_hf", None)

        # Eski widget'lar yıkılmadan önce callback'lerin onlara dokunmasını kes.
        self._ui_ready = False
        i18n.set_language(code)
        i18n.save_language(code)

        for child in list(self.winfo_children()):
            child.destroy()

        self._install_visible = False
        self._build_ui()
        self._config_panel.restore(snapshot)

        if candidates:
            self._net_table.load(candidates)
        if self._env_checks:
            self._checklist.show(self._env_checks)

        for cred in self._ctrl.credentials:
            self._cred_panel.add(cred)
        self._refresh_handshake_archive()

        if guide_hf is not None:
            self._next_step_guide.set_handshake(guide_hf)
            self._next_step_guide.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self._set_step(self._step)
        self._update_status(self._state)

    def _set_step(self, index: int) -> None:
        self._step = index
        self._guide.set_active(index)

    def _show_tab(self, key: str) -> None:
        self._active_tab = key
        name = self._tab_names.get(key)
        if not name:
            return
        try:
            self._tabs.set(name)
        except ValueError:
            # A stray callback from before a language re-render must not dump a
            # traceback into the console; the next event selects the tab again.
            pass

    # ── Callbacks (background threads → GUI thread) ──────────────

    def _on_state(self, state: AttackState) -> None:
        self.after(0, self._update_status, state)

    def _on_log(self, msg: str, level: str) -> None:
        self.after(0, self._log_panel.append, msg, level)

    def _on_candidates(self, candidates) -> None:
        def _apply():
            self._net_table.load(candidates)
            self._show_tab("networks")
            if candidates:
                self._set_step(2)
                self._refresh_hint()
        self.after(0, _apply)

    def _on_credential(self, cred: CapturedCredential) -> None:
        def _apply():
            self._cred_panel.add(cred)
            self._show_tab("credentials")
            self._set_step(4)
            self._refresh_hint()
            try:
                self.bell()
            except Exception:
                pass
        self.after(0, _apply)

    def _on_environment(self, checks) -> None:
        def _apply():
            self._env_checks = list(checks)
            self._checklist.show(self._env_checks)
            missing = [c for c in self._env_checks if not c.ok and c.required]
            for check in self._env_checks:
                if not check.ok:
                    self._log_panel.append(
                        t("log.env_line", name=check.name,
                          detail=check.detail, hint=check.hint), "warn")

            # İlk açılışta zorunlu bir paket eksikse kendiliğinden kur.
            if missing and not self._install_attempted and not self._ctrl.is_busy:
                if self._ctrl.is_root:
                    self._install_attempted = True
                    self._start_install(auto=True)
                else:
                    self._log_panel.append(t("log.needs_root"), "error")
            self._refresh_hint()
        self.after(0, _apply)

    def _on_dependency_install(self, ok: bool) -> None:
        def _apply():
            self._set_install_busy(False)
            if ok:
                self._log_panel.append(t("log.install_done"), "success")
            else:
                self._log_panel.append(t("log.install_failed"), "error")
            self._ctrl.check_environment()
            self._refresh_hint()
        self.after(0, _apply)

    def _on_target_select(self, target: TargetCandidate) -> None:
        self._target = target
        self._config_panel.fill_from_target(target)
        self._log_panel.append(
            t("log.target_selected", ssid=target.clean_essid,
              bssid=target.bssid, channel=target.channel), "info")
        self._set_step(3)
        self._refresh_hint()

        # Eğer bu hedef için önceden kaydedilmiş handshake varsa kullanıcıya bildir
        if target.has_handshake:
            hf = HandshakeFile(
                filename=f"{target.clean_essid}-{target.bssid}.cap",
                filepath=str(REPO_DIR / "attacks" / "Handshake Snooper" / "handshakes" / f"{target.clean_essid}-{target.bssid}.cap"),
                ssid=target.clean_essid,
                bssid=target.bssid,
                size_bytes=0,
                created_at=t("hs.previous"),
            )
            self._next_step_guide.set_handshake(hf)
            self._next_step_guide.grid(row=0, column=0, sticky="ew", pady=(0, 8))

    def _on_handshake(self, hf: HandshakeFile) -> None:
        def _apply():
            self._next_step_guide.set_handshake(hf)
            self._next_step_guide.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            self._refresh_handshake_archive()
            self._show_tab("networks")
            self._set_step(4)
            self._refresh_hint()
            self._log_panel.append(
                t("log.handshake_captured", file=hf.filepath), "success")
            # Yakalama anını kaçırmasın: pencereyi öne al ve ses çıkar.
            try:
                self.bell()
                self.lift()
                self.focus_force()
            except Exception:
                pass
        self.after(0, _apply)

    def _dismiss_guide(self) -> None:
        self._next_step_guide.grid_forget()

    def _start_portal_from_guide(self, hf: Optional[HandshakeFile]) -> None:
        if hf is None:
            return
        self._next_step_guide.grid_forget()
        # Saldırı türünü Captive Portal'a geçir
        self._config_panel._attack_var.set(AttackType.CAPTIVE_PORTAL.label)
        self._config_panel._on_attack_change(None)
        if hf.bssid:
            self._config_panel._bssid_e.delete(0, "end")
            self._config_panel._bssid_e.insert(0, hf.bssid)
        if hf.ssid:
            self._config_panel._essid_e.delete(0, "end")
            self._config_panel._essid_e.insert(0, hf.ssid)

        self._show_tab("networks")
        self._set_step(3)
        self._log_panel.append(
            t("log.guide_portal_ready", ssid=hf.ssid, bssid=hf.bssid), "success")
        self._log_panel.append(t("log.guide_start_hint"), "info")
        self._refresh_hint()

    def _start_crack_from_guide(self, hf: Optional[HandshakeFile]) -> None:
        if hf is None:
            return
        self._show_tab("credentials")
        self._log_panel.append(
            t("log.crack_start", ssid=hf.ssid, bssid=hf.bssid), "info")
        self._ctrl.crack_handshake(hf.filepath, bssid=hf.bssid)

    def _refresh_handshake_archive(self) -> None:
        try:
            handshakes = self._ctrl.list_handshakes()
            self._cred_panel.load_handshakes(handshakes)
        except Exception as e:
            self._log_panel.append(
                t("log.handshake_archive_error", error=e), "warn")

    # ── Button handlers ─────────────────────────────────────────

    def _do_scan(self) -> None:
        if self._ctrl.is_busy:
            return
        iface, scan_time, channel, band = self._config_panel.get_scan_params()
        self._log_panel.append(
            t("log.scan_start", iface=iface or t("log.iface_auto"),
              seconds=scan_time), "info")
        self._set_step(1)
        self._ctrl.start_scan(interface=iface, scan_time=scan_time,
                              channel=channel, band=band)

    def _do_attack(self) -> None:
        if self._ctrl.is_busy:
            return

        config = self._config_panel.build_config()
        if not config.target_bssid and not config.target_essid:
            target = self._net_table.select_first_with_clients()
            if target:
                self._on_target_select(target)
                config.target_bssid = target.bssid
                config.target_essid = target.essid
                config.target_channel = target.channel

        if not config.target_bssid and not config.target_essid:
            self._net_table.set_hint(t("log.no_target_hint"), "warn")
            self._log_panel.append(t("log.no_target"), "warn")
            self._show_tab("networks")
            return

        if config.attack_type is AttackType.CAPTIVE_PORTAL:
            portal = self._config_panel.selected_portal
            if portal is None:
                self._log_panel.append(t("log.no_portal"), "warn")
                return
            self._log_panel.append(
                t("log.portal_info", title=portal.display_title,
                  desc=portal.description), "info")

        self._set_step(3)
        self._log_panel.append(
            t("log.attack_start", attack=config.attack_type.value,
              target=(config.target_essid or config.target_bssid)), "info")
        self._ctrl.start_attack(config)

    def _do_stop(self) -> None:
        self._ctrl.stop()

    def _start_install(self, auto: bool = False) -> None:
        if self._ctrl.is_busy:
            return
        self._install_attempted = True
        self._set_install_busy(True, t("app.health.installing"))
        if auto:
            self._log_panel.append(t("log.install_first"), "info")
        self._ctrl.install_dependencies(language=self._config_panel.language)

    def _set_install_busy(self, visible: bool, text: str = "") -> None:
        if visible and not self._install_visible:
            self._install_label.configure(text=text)
            self._install_label.pack(fill="x", padx=12, pady=(0, 2))
            self._install_bar.pack(fill="x", padx=12, pady=(0, 8))
            self._install_bar.configure(mode="indeterminate")
            self._install_bar.start()
            self._install_visible = True
        elif not visible and self._install_visible:
            self._install_bar.stop()
            self._install_bar.pack_forget()
            self._install_label.pack_forget()
            self._install_visible = False

    def _do_clear(self) -> None:
        self._log_panel.clear()
        self._net_table.clear()
        self._target = None
        self._config_panel.clear_target()
        self._set_step(1 if self._ctrl.candidates else 0)
        self._refresh_hint()

    # ── State / hint sync ───────────────────────────────────────

    def _update_status(self, state: AttackState) -> None:
        self._state = state
        self._status_badge.update_state(state.value)

        busy = state in (AttackState.INSTALLING, AttackState.SCANNING,
                         AttackState.STARTING, AttackState.RUNNING)
        self._btn_scan.configure(state="disabled" if busy else "normal")
        self._btn_attack.configure(state="disabled" if busy else "normal")
        self._btn_stop.configure(state="normal" if busy else "disabled")
        self._btn_install.configure(state="disabled" if busy else "normal")

        if state is AttackState.INSTALLING:
            self._set_install_busy(True, t("app.health.installing"))
            self._set_step(0)

        if state is AttackState.SCANNING:
            self._set_step(1)
        elif state in (AttackState.STARTING, AttackState.RUNNING):
            self._set_step(3)
        elif state in (AttackState.HANDSHAKE_CAPTURED, AttackState.CREDENTIALS_FOUND):
            self._set_step(4)
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        """Alttaki satır: kullanıcıya sıradaki tek adımı söyler.

        Ayar paneli kurulurken de çağrılır; alt bar o an henüz yok.
        """
        if not getattr(self, "_ui_ready", False):
            return
        if not hasattr(self, "_bar_label") or not hasattr(self, "_config_panel"):
            return
        state = self._state

        if state is AttackState.INSTALLING:
            text, colour = t("hint.installing"), ACCENT2
        elif state is AttackState.SCANNING:
            text, colour = t("hint.scanning"), ACCENT2
        elif state is AttackState.STARTING:
            text, colour = t("hint.starting"), WARN
        elif state is AttackState.RUNNING:
            if self._config_panel.attack_type is AttackType.CAPTIVE_PORTAL:
                text, colour = t("hint.running.portal"), ACCENT
            else:
                text, colour = t("hint.running.handshake"), ACCENT
        elif state is AttackState.CREDENTIALS_FOUND:
            text, colour = t("hint.credentials"), ACCENT
        elif state is AttackState.HANDSHAKE_CAPTURED:
            text, colour = t("hint.handshake"), ACCENT
        elif state is AttackState.ERROR:
            text, colour = t("hint.error"), DANGER
        elif state is AttackState.STOPPED:
            text, colour = t("hint.stopped"), MUTED
        else:
            missing = [c for c in self._env_checks if not c.ok and c.required]
            if not self._env_checks:
                text, colour = t("hint.env_checking"), MUTED
            elif missing:
                names = ", ".join(c.name for c in missing[:3])
                if len(missing) > 3:
                    text = t("hint.missing_more", names=names,
                             extra=len(missing) - 3)
                else:
                    text = t("hint.missing", names=names)
                colour = WARN
            elif not self._ctrl.candidates:
                text, colour = t("hint.ready_scan"), ACCENT2
            elif not (self._config_panel.build_config().target_bssid
                      or self._config_panel.build_config().target_essid):
                text, colour = t("hint.pick_row"), ACCENT2
            else:
                text, colour = t("hint.target_ready"), ACCENT

        self._bar_label.configure(text="▶  " + text, text_color=colour)


# ─────────────────────────── Entry point ────────────────────────────

if __name__ == "__main__":
    app = CapCapWifiApp()
    app.mainloop()
