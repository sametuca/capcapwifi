"""
CapCapWifi – Python GUI Ana Penceresi

CustomTkinter tabanlı, karanlık temalı, hibrit denetleyici (capcapwifi.sh → --auto).

Arayüzün amacı tek bir soruya cevap vermek: "şu anda neredeyim, sırada ne var?"
Bu yüzden her ekranda kısa bir açıklama, üstte adım çubuğu ve altta dinamik
"şimdi ne yapmalıyım" satırı bulunur.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Dict, List, Optional

import customtkinter as ctk

# Local modules
from controller import CapCapWifiController
from models import (
    AttackConfig,
    AttackState,
    AttackType,
    CapturedCredential,
    EnvironmentCheck,
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)
from widgets import (
    ACCENT, ACCENT2, CARD_BG, CARD_HOVER, DANGER, DARK_BG, FONT_MONO_S,
    FONT_TITLE, FONT_UI, FONT_UI_B, FONT_UI_S, MUTED, PANEL_BG, TEXT_PRI,
    TEXT_SEC, WARN, BORDER,
    Checklist, CredentialsPanel, GuideBar, LogPanel, NetworkTable,
    SectionCard, StatusBadge,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

REPO_DIR = Path(__file__).resolve().parent.parent

STEPS = ("Adaptör", "Tara", "Hedef seç", "Saldır", "Sonuç")

AUTO = "Otomatik (program seçsin)"

BAND_LABELS = {
    "bg (2.4 GHz)": "bg",
    "a (5 GHz)": "a",
    "abg (Her ikisi)": "abg",
}

ATTACK_LABELS = {
    "Captive Portal – sahte giriş sayfası": AttackType.CAPTIVE_PORTAL,
    "Handshake Snooper – el sıkışma yakalama": AttackType.HANDSHAKE_SNOOPER,
}

HELP_TEXT = """NASIL KULLANILIR – 5 ADIM

1) ADAPTÖR
   Ekranın sağındaki "Ortam Kontrolü" kartına bak. Kırmızı ✗ varsa
   saldırı başlamaz: adaptör monitor mode + paket enjeksiyonu
   desteklemeli ve program root yetkisiyle çalışmalı.

2) TARA
   "🔍 Tara" düğmesi yakındaki ağları listeler. Süre uzadıkça
   daha çok ağ görünür ama bağlı cihaz sayısı da o sürede toplanır.
   Cihaz yoksa deauth atacak kimse yok demektir.

3) HEDEF SEÇ
   Tabloda yeşil satır = en az bir cihaz bağlı. Satıra tıkla;
   program SSID/BSSID/kanal alanlarını kendisi doldurur ve
   altındaki satırda o ağın neden uygun (ya da uygun olmadığını)
   yazar.

4) SALDIR
   Captive Portal: hedef ağın birebir kopyasını açar, bağlanan
   cihaza seçtiğin portal sayfasını gösterir ve forma yazılanları
   kaydeder. Portalın kendisi kayıt yapıyorsa (Instagram şablonları)
   ayrıca şifre doğrulama adımı atlanır.
   Handshake Snooper: cihazları düşürüp yeniden bağlanmaya zorlar
   ve WPA/WPA2 handshake'ini yakalar; sonuç .cap dosyasıdır.

5) SONUÇ
   Captive Portal → "🔑 Şifreler" sekmesi
   Handshake Snooper → "📡 Ağlar" sekmesinde ✔ işareti

DOSYALAR
   Canlı durum : /tmp/capcapspace/capcap.status
   Girişler    : /tmp/capcapspace/instagram_credentials.log
   Handshake   : attacks/Handshake Snooper/handshakes/

NOTLAR
   • ! işaretli kanallar DFS: sahte AP orada açılamaz.
   • Deauth yöntemi otomatik seçilir (aireplay-ng); mdk4 istisnadır.
   • Saldırı sürerken "⏹ Durdur" ile her şey temiz kapatılır.
"""


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

        self._build_interfaces()
        self._build_scan()
        self._build_target()
        self._build_attack()

        self._refresh_ifaces()
        self._load_portals()

    # ── sections ────────────────────────────────────────────────

    def _build_interfaces(self) -> None:
        sec = SectionCard(
            self, "1 · ADAPTÖR",
            "Hangi kablosuz kart kullanılacak. Emin değilsen otomatik bırak.",
        )
        sec.pack(fill="x", padx=4, pady=(4, 4))
        body = sec.body()

        self._iface_var = self._combo_row(body, 0, "Birincil (tarama):")
        self._jammer_var = self._combo_row(body, 1, "Deauth kartı:")
        self._ap_iface_var = self._combo_row(body, 2, "Sahte AP kartı:")

        ctk.CTkLabel(
            body,
            text=("İki adaptör varsa: biri sahte AP, diğeri deauth için. "
                  "Tek adaptörle de çalışır ama daha yavaş."),
            font=FONT_UI_S, text_color=MUTED, anchor="w",
            justify="left", wraplength=250,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ctk.CTkButton(body, text="🔄 Listeyi yenile", command=self._refresh_ifaces,
                      fg_color=DARK_BG, border_color=ACCENT, border_width=1,
                      text_color=ACCENT, hover_color="#1b3a2a", font=FONT_UI,
                      height=26).grid(row=4, column=0, columnspan=2,
                                      sticky="ew", pady=(6, 0))

    def _build_scan(self) -> None:
        sec = SectionCard(
            self, "2 · TARAMA",
            "Kısa süre hızlıdır, uzun süre bağlı cihazları da görür.",
        )
        sec.pack(fill="x", padx=4, pady=4)
        body = sec.body()

        ctk.CTkLabel(body, text="Süre (sn):", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._scan_time = ctk.CTkEntry(body, width=80, fg_color=DARK_BG,
                                       border_color=BORDER, text_color=TEXT_PRI,
                                       font=FONT_UI)
        self._scan_time.insert(0, "30")
        self._scan_time.grid(row=0, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(body, text="Bant:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._band_var = ctk.StringVar(value="bg (2.4 GHz)")
        ctk.CTkComboBox(body, variable=self._band_var, width=160,
                        values=list(BAND_LABELS),
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text="Kanal:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._channel_e = ctk.CTkEntry(body, placeholder_text="Tümü", width=80,
                                       fg_color=DARK_BG, border_color=BORDER,
                                       text_color=TEXT_PRI, font=FONT_UI)
        self._channel_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

    def _build_target(self) -> None:
        sec = SectionCard(
            self, "3 · HEDEF",
            "Tablo satırına tıklarsan bu alanlar kendiliğinden dolar.",
        )
        sec.pack(fill="x", padx=4, pady=4)
        body = sec.body()

        ctk.CTkLabel(body, text="SSID:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._essid_e = ctk.CTkEntry(body, placeholder_text="Ağ adı", width=200,
                                     fg_color=DARK_BG, border_color=BORDER,
                                     text_color=TEXT_PRI, font=FONT_UI)
        self._essid_e.grid(row=0, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text="BSSID:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=2)
        self._bssid_e = ctk.CTkEntry(body, placeholder_text="AA:BB:CC:DD:EE:FF",
                                     width=200, fg_color=DARK_BG,
                                     border_color=BORDER, text_color=TEXT_PRI,
                                     font=FONT_UI)
        self._bssid_e.grid(row=1, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text="Kanal:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._target_ch_e = ctk.CTkEntry(body, placeholder_text="6", width=80,
                                         fg_color=DARK_BG, border_color=BORDER,
                                         text_color=TEXT_PRI, font=FONT_UI)
        self._target_ch_e.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")

        self._target_note = ctk.CTkLabel(
            body, text="Henüz hedef seçilmedi.", font=FONT_UI_S,
            text_color=MUTED, anchor="w", justify="left", wraplength=250,
        )
        self._target_note.grid(row=3, column=0, columnspan=2, sticky="w",
                               pady=(6, 0))

    def _build_attack(self) -> None:
        sec = SectionCard(
            self, "4 · SALDIRI",
            "İki yöntem var; hangisini seçtiğinin açıklaması altında yazar.",
        )
        sec.pack(fill="x", padx=4, pady=(4, 10))
        body = sec.body()

        ctk.CTkLabel(body, text="Tür:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=2)
        self._attack_var = ctk.StringVar(value=list(ATTACK_LABELS)[0])
        ctk.CTkComboBox(body, variable=self._attack_var, width=220,
                        values=list(ATTACK_LABELS),
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

        ctk.CTkLabel(body, text="Portal:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=2, column=0, sticky="w", pady=2)
        self._portal_var = ctk.StringVar(value="Yükleniyor…")
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

        ctk.CTkLabel(body, text="AP servisi:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=4, column=0, sticky="w", pady=2)
        self._ap_svc_var = ctk.StringVar(value="hostapd")
        self._ap_svc_cb = ctk.CTkComboBox(
            body, variable=self._ap_svc_var, width=160,
            values=["hostapd", "airbase-ng"],
            fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
            text_color=TEXT_PRI, font=FONT_UI)
        self._ap_svc_cb.grid(row=4, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text="Deauth:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=5, column=0, sticky="w", pady=2)
        self._deauth_var = ctk.StringVar(value="aireplay-ng")
        ctk.CTkComboBox(body, variable=self._deauth_var, width=160,
                        values=["aireplay-ng", "mdk4"],
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=5, column=1, padx=(8, 0), pady=2)

        ctk.CTkLabel(body, text="Dil:", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=6, column=0, sticky="w", pady=2)
        self._lang_var = ctk.StringVar(value="tur")
        ctk.CTkComboBox(body, variable=self._lang_var, width=100,
                        values=self._get_languages(),
                        fg_color=DARK_BG, border_color=BORDER, button_color=ACCENT,
                        text_color=TEXT_PRI, font=FONT_UI).grid(
            row=6, column=1, padx=(8, 0), pady=2, sticky="w")

        ctk.CTkLabel(body, text="Timeout (dk):", font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=7, column=0, sticky="w", pady=2)
        self._timeout_e = ctk.CTkEntry(body, placeholder_text="Süresiz", width=80,
                                       fg_color=DARK_BG, border_color=BORDER,
                                       text_color=TEXT_PRI, font=FONT_UI)
        self._timeout_e.grid(row=7, column=1, padx=(8, 0), pady=2, sticky="w")

        self._on_attack_change(self._attack_var.get())

    # ── helpers ─────────────────────────────────────────────────

    def _combo_row(self, body, row: int, label: str) -> ctk.StringVar:
        ctk.CTkLabel(body, text=label, font=FONT_UI,
                     text_color=TEXT_SEC).grid(row=row, column=0,
                                               sticky="w", pady=2)
        var = ctk.StringVar(value=AUTO)
        ctk.CTkComboBox(body, variable=var, width=200,
                        values=[AUTO],
                        fg_color=DARK_BG, border_color=BORDER,
                        button_color=ACCENT, text_color=TEXT_PRI,
                        font=FONT_UI).grid(row=row, column=1, padx=(8, 0), pady=2)
        var.trace_add("write", lambda *_: self._notify())
        return var

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

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
        self._target_note.configure(text="Henüz hedef seçilmedi.", text_color=MUTED)
        self._notify()

    @property
    def attack_type(self) -> AttackType:
        return ATTACK_LABELS.get(self._attack_var.get(), AttackType.CAPTIVE_PORTAL)

    @property
    def language(self) -> str:
        return self._lang_var.get() or "tur"

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
            band=BAND_LABELS.get(self._band_var.get(), "bg"),
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
            BAND_LABELS.get(self._band_var.get(), "bg"),
        )

    # ── private ─────────────────────────────────────────────────

    @staticmethod
    def _value(var: ctk.StringVar) -> str:
        value = var.get().strip()
        return "" if value.startswith("Otomatik") else value

    def _refresh_ifaces(self) -> None:
        def _load():
            ifaces = self._ctrl.list_interfaces()
            self._ifaces = ifaces
            names = [AUTO] + [i.name for i in ifaces]
            for var in (self._iface_var, self._jammer_var, self._ap_iface_var):
                if var.get() not in names:
                    var.set(AUTO)

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
            text=f"{attack.summary}\n\nGEREKEN: {attack.what_you_need}\n\n"
                 f"SONRA: {attack.what_happens_next}",
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
        self.title("CapCapWifi – Wi-Fi Güvenlik Denetleyicisi")
        self.geometry("1360x860")
        self.minsize(1100, 720)
        self.configure(fg_color=DARK_BG)
        self.iconname("CapCapWifi")

        self._ctrl = CapCapWifiController()
        self._ctrl.on_state_change = self._on_state
        self._ctrl.on_log = self._on_log
        self._ctrl.on_candidates = self._on_candidates
        self._ctrl.on_credential = self._on_credential
        self._ctrl.on_environment = self._on_environment
        self._ctrl.on_dependency_install = self._on_dependency_install

        self._state = AttackState.IDLE
        self._target: Optional[TargetCandidate] = None
        self._env_checks: List[EnvironmentCheck] = []
        self._install_attempted = False

        self._build_ui()
        self._update_status(AttackState.IDLE)
        self.after(200, lambda: self._ctrl.check_environment())

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="#08090B", height=60,
                           corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="⚡", font=("Inter", 20),
                     text_color=ACCENT).pack(side="left", padx=(18, 2), pady=8)
        ctk.CTkLabel(top, text="CapCapWifi", font=("Inter", 18, "bold"),
                     text_color=TEXT_PRI).pack(side="left", pady=8)
        ctk.CTkLabel(top, text="  Wi-Fi güvenlik denetleyicisi",
                     font=FONT_UI, text_color=MUTED).pack(side="left", pady=8)

        self._status_badge = StatusBadge(top)
        self._status_badge.pack(side="right", padx=18, pady=10)

        ctk.CTkFrame(self, fg_color=ACCENT, height=2,
                     corner_radius=0).pack(fill="x")

        self._guide = GuideBar(self, STEPS)
        self._guide.pack(fill="x", padx=12, pady=(8, 0))
        self._guide.set_active(0)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=330)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2, minsize=360)
        body.rowconfigure(0, weight=1)

        # Left: configuration
        self._config_panel = AttackConfigPanel(
            body, self._ctrl, on_change=self._refresh_hint)
        self._config_panel.grid(row=0, column=0, sticky="nsew",
                                padx=(12, 5), pady=10)

        # Centre: tabs
        centre = ctk.CTkFrame(body, fg_color="transparent")
        centre.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        centre.rowconfigure(0, weight=1)
        centre.columnconfigure(0, weight=1)

        self._tabs = ctk.CTkTabview(
            centre, fg_color=PANEL_BG,
            segmented_button_fg_color=CARD_BG,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color="#00c86a",
            segmented_button_unselected_color=CARD_BG,
            segmented_button_unselected_hover_color=CARD_HOVER,
            text_color=TEXT_PRI,
            corner_radius=12,
        )
        self._tabs.grid(row=0, column=0, sticky="nsew")
        tab_nets = self._tabs.add("📡  Ağlar")
        tab_creds = self._tabs.add("🔑  Şifreler")
        tab_help = self._tabs.add("❓  Nasıl kullanılır")

        self._net_table = NetworkTable(tab_nets, on_select=self._on_target_select)
        self._net_table.pack(fill="both", expand=True)

        self._cred_panel = CredentialsPanel(tab_creds)
        self._cred_panel.pack(fill="both", expand=True)

        help_box = ctk.CTkFrame(tab_help, fg_color="transparent")
        help_box.pack(fill="both", expand=True)
        help_text = ctk.CTkTextbox(help_box, fg_color=DARK_BG,
                                   text_color=TEXT_PRI, font=FONT_MONO_S,
                                   wrap="word", corner_radius=10,
                                   border_width=1, border_color=BORDER)
        help_text.pack(fill="both", expand=True, padx=6, pady=6)
        help_text.insert("1.0", HELP_TEXT)
        help_text.configure(state="disabled")

        # Action buttons
        btn_row = ctk.CTkFrame(centre, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            btn_row.columnconfigure(column, weight=1)

        self._btn_scan = ctk.CTkButton(
            btn_row, text="🔍  Tara", command=self._do_scan,
            fg_color=ACCENT, text_color="#052012", hover_color="#00C86A",
            font=FONT_UI_B, height=44, corner_radius=12)
        self._btn_scan.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._btn_attack = ctk.CTkButton(
            btn_row, text="⚡  Saldırıyı başlat", command=self._do_attack,
            fg_color=WARN, text_color="#201500", hover_color="#FFC44D",
            font=FONT_UI_B, height=44, corner_radius=12)
        self._btn_attack.grid(row=0, column=1, padx=5, sticky="ew")

        self._btn_stop = ctk.CTkButton(
            btn_row, text="⏹  Durdur", command=self._do_stop,
            fg_color="transparent", text_color=DANGER, hover_color="#2A1218",
            border_width=1, border_color=DANGER, font=FONT_UI_B,
            height=44, corner_radius=12, state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=5, sticky="ew")

        self._btn_clear = ctk.CTkButton(
            btn_row, text="🗑  Temizle", command=self._do_clear,
            fg_color="transparent", text_color=TEXT_SEC, hover_color=CARD_HOVER,
            font=FONT_UI_B, height=44, border_color=BORDER, border_width=1,
            corner_radius=12)
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
        ctk.CTkLabel(head, text="🩺  Ortam kontrolü", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(head, text="🔄", width=30, height=26,
                      command=lambda: self._ctrl.check_environment(),
                      fg_color="transparent", border_color=BORDER,
                      border_width=1, text_color=TEXT_SEC,
                      hover_color=CARD_HOVER,
                      font=FONT_UI).pack(side="right")
        self._btn_install = ctk.CTkButton(
            head, text="📦 Eksikleri kur", width=118, height=26,
            command=self._start_install, fg_color="transparent",
            border_color=WARN, border_width=1, text_color=WARN,
            hover_color="#2A2110", font=FONT_UI_S, corner_radius=10)
        self._btn_install.pack(side="right", padx=(0, 6))

        ctk.CTkLabel(
            health,
            text="Saldırı için gereken her şey burada listelenir. ✗ = eksik.",
            font=FONT_UI_S, text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 4))

        self._install_bar = ctk.CTkProgressBar(health, height=6,
                                               progress_color=ACCENT2,
                                               fg_color=BORDER)
        self._install_label = ctk.CTkLabel(
            health, text="", font=FONT_UI_S, text_color=ACCENT2, anchor="w")
        self._install_visible = False

        self._health_scroll = ctk.CTkScrollableFrame(
            health, fg_color="transparent", height=230)
        self._health_scroll.pack(fill="x", padx=8, pady=(0, 8))
        self._checklist = Checklist(self._health_scroll)
        self._checklist.pack(fill="x")
        self._checklist.show([EnvironmentCheck(
            name="Kontrol ediliyor…", ok=False,
            detail="araçlar ve adaptör taranıyor", hint="")])

        self._log_panel = LogPanel(right)
        self._log_panel.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        # Bottom hint bar
        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x")
        bar = ctk.CTkFrame(self, fg_color="#08090B", height=34,
                           corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._bar_label = ctk.CTkLabel(
            bar, text="", font=FONT_UI_S, text_color=TEXT_SEC,
            anchor="w", justify="left")
        self._bar_label.pack(side="left", padx=16)
        ctk.CTkLabel(bar, text="github.com/sametuca/capcapwifi",
                     font=FONT_MONO_S,
                     text_color="#2F343B").pack(side="right", padx=16)

        self._refresh_hint()

    # ── Callbacks (background threads → GUI thread) ──────────────

    def _on_state(self, state: AttackState) -> None:
        self.after(0, self._update_status, state)

    def _on_log(self, msg: str, level: str) -> None:
        self.after(0, self._log_panel.append, msg, level)

    def _on_candidates(self, candidates) -> None:
        def _apply():
            self._net_table.load(candidates)
            self._tabs.set("📡 Ağlar")
            if candidates:
                self._guide.set_active(2)
                self._refresh_hint()
        self.after(0, _apply)

    def _on_credential(self, cred: CapturedCredential) -> None:
        def _apply():
            self._cred_panel.add(cred)
            self._tabs.set("🔑 Şifreler")
            self._guide.set_active(4)
            self._refresh_hint()
        self.after(0, _apply)

    def _on_environment(self, checks) -> None:
        def _apply():
            self._env_checks = list(checks)
            self._checklist.show(self._env_checks)
            missing = [c for c in self._env_checks if not c.ok and c.required]
            for check in self._env_checks:
                if not check.ok:
                    self._log_panel.append(
                        f"[ortam] {check.name}: {check.detail} → {check.hint}", "warn")

            # İlk açılışta zorunlu bir paket eksikse kendiliğinden kur.
            if missing and not self._install_attempted and not self._ctrl.is_busy:
                if self._ctrl.is_root:
                    self._install_attempted = True
                    self._start_install(auto=True)
                else:
                    self._log_panel.append(
                        "[!] Kurulum için root gerekli: sudo ./run_gui.sh", "error")
            self._refresh_hint()
        self.after(0, _apply)

    def _on_dependency_install(self, ok: bool) -> None:
        def _apply():
            self._set_install_busy(False)
            if ok:
                self._log_panel.append(
                    "[+] Kurulum tamamlandı. Ortam yeniden kontrol ediliyor…", "success")
            else:
                self._log_panel.append(
                    "[!] Kurulum tamamlanamadı. Log'daki apt çıktısına bak; "
                    "gerekirse terminalde `sudo ./capcapwifi.sh --install-deps` çalıştır.",
                    "error")
            self._ctrl.check_environment()
            self._refresh_hint()
        self.after(0, _apply)

    def _on_target_select(self, target: TargetCandidate) -> None:
        self._target = target
        self._config_panel.fill_from_target(target)
        self._log_panel.append(
            f"[+] Hedef: {target.clean_essid} ({target.bssid}) CH{target.channel}", "info")
        self._guide.set_active(3)
        self._refresh_hint()

    # ── Button handlers ─────────────────────────────────────────

    def _do_scan(self) -> None:
        if self._ctrl.is_busy:
            return
        iface, scan_time, channel, band = self._config_panel.get_scan_params()
        self._log_panel.append(
            f"[*] Tarama başlıyor – arayüz {iface or 'otomatik'}, {scan_time} sn", "info")
        self._guide.set_active(1)
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
            self._net_table.set_hint(
                "Önce tablodan bir hedef seç: satıra tıkla ya da yeniden tara.",
                "warn")
            self._log_panel.append(
                "[!] Hedef yok. Tablodan bir ağ seç veya BSSID/SSID gir.", "warn")
            self._tabs.set("📡 Ağlar")
            return

        if config.attack_type is AttackType.CAPTIVE_PORTAL:
            portal = self._config_panel.selected_portal
            if portal is None:
                self._log_panel.append("[!] Portal şablonu seçilmedi.", "warn")
                return
            self._log_panel.append(
                f"[i] Portal: {portal.display_title} – {portal.description}", "info")

        self._guide.set_active(3)
        self._log_panel.append(
            f"[*] {config.attack_type.value} → "
            f"{config.target_essid or config.target_bssid}", "info")
        self._ctrl.start_attack(config)

    def _do_stop(self) -> None:
        self._ctrl.stop()

    def _start_install(self, auto: bool = False) -> None:
        if self._ctrl.is_busy:
            return
        self._install_attempted = True
        self._set_install_busy(
            True, "Kurulum sürüyor – apt çıktısı log panelinde…")
        if auto:
            self._log_panel.append(
                "[i] İlk kurulum: eksik paketler otomatik yükleniyor. "
                "Bu işlem birkaç dakika sürebilir, pencereyi kapatmayın.", "info")
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
        self._guide.set_active(1 if self._ctrl.candidates else 0)
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
            self._set_install_busy(
                True, "Kurulum sürüyor – apt çıktısı log panelinde…")
            self._guide.set_active(0)

        if state is AttackState.SCANNING:
            self._guide.set_active(1)
        elif state in (AttackState.STARTING, AttackState.RUNNING):
            self._guide.set_active(3)
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        """Alttaki satır: kullanıcıya sıradaki tek adımı söyler.

        Ayar paneli kurulurken de çağrılır; alt bar o an henüz yok.
        """
        if not hasattr(self, "_bar_label") or not hasattr(self, "_config_panel"):
            return
        state = self._state

        if state is AttackState.INSTALLING:
            text, colour = ("Gerekli paketler kuruluyor. Bitince kontrol otomatik "
                            "yenilenecek; pencereyi kapatmayın.", ACCENT2)
        elif state is AttackState.SCANNING:
            text, colour = ("Ağlar taranıyor… Bitince tablo dolacak, sonra hedef seç.", ACCENT2)
        elif state is AttackState.STARTING:
            text, colour = ("Saldırı hazırlanıyor: adaptör monitor moda alınıyor, "
                            "servisler başlatılıyor.", WARN)
        elif state is AttackState.RUNNING:
            if self._config_panel.attack_type is AttackType.CAPTIVE_PORTAL:
                text, colour = ("Sahte AP yayında. Cihaz bağlanıp formu gönderdiğinde "
                                "'Şifreler' sekmesine satır düşecek.", ACCENT)
            else:
                text, colour = ("Deauth atılıyor, handshake bekleniyor. Yakalanınca "
                                "ağ listesinde ✔ görünecek.", ACCENT)
        elif state is AttackState.CREDENTIALS_FOUND:
            text, colour = ("Giriş yakalandı! '🔑 Şifreler' sekmesinden kopyalayabilirsin.", ACCENT)
        elif state is AttackState.HANDSHAKE_CAPTURED:
            text, colour = ("Handshake yakalandı. Dosya: attacks/Handshake Snooper/handshakes/", ACCENT)
        elif state is AttackState.ERROR:
            text, colour = ("Hata: sağdaki log paneli ve ortam kontrolü kartına bak.", DANGER)
        elif state is AttackState.STOPPED:
            text, colour = ("Durduruldu. Yeni bir tarama başlatabilir ya da hedefi "
                            "değiştirebilirsin.", MUTED)
        else:
            missing = [c for c in self._env_checks if not c.ok and c.required]
            if not self._env_checks:
                text, colour = ("Ortam kontrol ediliyor…", MUTED)
            elif missing:
                names = ", ".join(c.name for c in missing[:3])
                text, colour = (f"Eksik: {names} (+{len(missing) - 3} daha)" if len(missing) > 3
                                else f"Eksik: {names} – sağdaki karttan ipucuna bak.", WARN)
            elif not self._ctrl.candidates:
                text, colour = ("Her şey hazır. Sıradaki adım: “🔍 Tara” ile ağları bul.", ACCENT2)
            elif not (self._config_panel.build_config().target_bssid
                      or self._config_panel.build_config().target_essid):
                text, colour = ("Tabloda yeşil (bağlı cihazı olan) bir satıra tıkla; "
                                "alanlar kendiliğinden dolar.", ACCENT2)
            else:
                text, colour = ("Hedef hazır. “⚡ Saldırıyı başlat” ile devam et.", ACCENT)

        self._bar_label.configure(text="▶  " + text, text_color=colour)


# ─────────────────────────── Entry point ────────────────────────────

if __name__ == "__main__":
    app = CapCapWifiApp()
    app.mainloop()
