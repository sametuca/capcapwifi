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

# ── Çizim yöntemi uyumluluğu ────────────────────────────────────
# CustomTkinter varsayılan olarak yuvarlak köşeleri özel bir TTF fontuyla
# ("font_shapes") çizer. Python 3.14 altında bu yol, kaydırma çubuğu her
# güncellendiğinde (scrollbar.set → draw_rounded_scrollbar → canvas.coords)
# "Exception in Tkinter callback" hatası veriyor. Fonta ihtiyaç duymayan
# "circle_shapes" yöntemine geçmek sorunu giderir; köşeler yine yuvarlak
# kalır, yalnızca çizim arka ucu değişir. Her widget kurulmadan ÖNCE,
# uygulama başlatılmadan çalışması gerektiği için modül en üstünde yapılır.
try:
    from customtkinter.windows.widgets.core_rendering.draw_engine import (
        DrawEngine,
    )
    DrawEngine.preferred_drawing_method = "circle_shapes"
except Exception:
    pass

# Local modules
import i18n
import updater
from tkinter import messagebox
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
)
from widgets import (
    Checklist, CredentialsPanel, GuideBar, LogPanel, NetworkTable,
    NotificationHost, SectionCard, SelectionSummary, StatusBadge, auto_wrap,
    form_combo, form_entry, form_label, hairline, segmented,
)

from effects import (
    ActivityBar, Spinner, icon_button, make_button,
)
from theme import (
    ACCENT, ACCENT2, ACCENT2_DIM, ACCENT_DIM, ACCENT_DK, ACCENT_ON,
    BORDER, BORDER_SOFT, CARD_BG, CARD_HOVER, CHROME_BG, CONSOLE_FG, DANGER,
    DARK_BG, ELEV_BG, FONT_BRAND, FONT_MONO_S, FONT_TITLE, FONT_UI,
    FONT_UI_B, FONT_UI_S, FONT_UI_SB, FONT_UI_XS, MUTED, OFF_TEXT, PANEL_BG,
    TEXT_FAINT, TEXT_PRI, TEXT_SEC, WARN, mix_colour,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

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


#: Form satırları arası dikey boşluk (ayrıntılar penceresindeki alanlar).
ROW_PAD = 3


# ─────────────────────── ayar nesnesi (arayüzsüz) ──────────────────

class AttackSettings:
    """Kullanıcının gördüğü üç karar: hedef, saldırı türü ve portal sayfası.

    Tek görünüme geçince adaptör/kanal/deauth alanları arayüzden kalktı ama
    motor hâlâ onlara ihtiyaç duyuyor. Bu nesne, arayüzün topladığı az sayıda
    kararı motorun beklediği :class:`AttackConfig`'e çevirir ve otomatik
    seçimleri tek yerde yapar. Arayüz çağırmaz, böylece test edilebilir.
    """

    #: Saldırı türü -> (etiket anahtarı). Arayüz bu iki türü sunar.
    ATTACKS = (AttackType.CAPTIVE_PORTAL, AttackType.HANDSHAKE_SNOOPER)

    def __init__(self):
        self.attack_type: AttackType = AttackType.CAPTIVE_PORTAL
        self.portal: Optional[PortalSite] = None
        self.target: Optional[TargetCandidate] = None
        self.scan_time: int = 30
        self.band: str = "bg"
        self.channel: str = ""
        self.language: str = "tur"
        self.interface: str = ""
        self.timeout_minutes: Optional[int] = None

    # ── hedef ───────────────────────────────────────────────────

    def set_target(self, target: Optional[TargetCandidate]) -> None:
        self.target = target

    def has_target(self) -> bool:
        return self.target is not None

    def bssid(self) -> str:
        return self.target.bssid if self.target is not None else ""

    def essid(self) -> str:
        return self.target.essid if self.target is not None else ""

    def target_channel(self) -> str:
        return self.target.channel if self.target is not None else ""

    # ── saldırı türü ────────────────────────────────────────────

    def use_portal(self) -> None:
        self.attack_type = AttackType.CAPTIVE_PORTAL

    def use_handshake(self) -> None:
        self.attack_type = AttackType.HANDSHAKE_SNOOPER

    @property
    def is_portal(self) -> bool:
        return self.attack_type is AttackType.CAPTIVE_PORTAL

    def portal_title(self) -> str:
        return self.portal.display_title if self.portal is not None else ""

    def set_portal(self, portal: Optional[PortalSite]) -> None:
        self.portal = portal

    # ── tarama ──────────────────────────────────────────────────

    def set_scan_time(self, raw: object) -> None:
        """Geçersiz girişi 30 sn'ye düşürür; arayüz asla hata göstermez."""
        try:
            self.scan_time = max(5, min(600, int(str(raw).strip())))
        except (TypeError, ValueError):
            self.scan_time = 30

    def scan_params(self):
        """(arayüz, süre, kanal, bant) – controller.start_scan sözleşmesi."""
        return (self.interface, self.scan_time, self.channel, self.band)

    # ── motor yapılandırması ────────────────────────────────────

    def portal_site_id(self) -> str:
        if self.portal is not None:
            return self.portal.site_id
        return "Instagram_tur"

    def build_config(self) -> AttackConfig:
        """Motora verilecek tam yapılandırma; alanların hepsi burada dolar."""
        return AttackConfig(
            attack_type=self.attack_type,
            interface=self.interface,
            target_bssid=self.bssid(),
            target_essid=self.essid(),
            target_channel=self.target_channel(),
            jammer_interface="",
            ap_interface="",
            ap_service="hostapd",
            deauth_method="aireplay-ng",
            portal_site=self.portal_site_id(),
            language=self.language,
            band=self.band,
            timeout_minutes=self.timeout_minutes,
        )

    # ── portal listesi ──────────────────────────────────────────

    @staticmethod
    def default_portal(portals: List[PortalSite]) -> Optional[PortalSite]:
        """Türkçe Instagram şablonu varsa onu, yoksa listeyi baştan seçer."""
        for portal in portals:
            if "Instagram" in portal.name and portal.lang.lower() in ("tur", "tr"):
                return portal
        return portals[0] if portals else None

    @staticmethod
    def languages(repo_dir: Path) -> List[str]:
        lang_dir = repo_dir / "language"
        if lang_dir.is_dir():
            codes = sorted(p.stem for p in lang_dir.iterdir()
                           if p.suffix == ".sh")
            if codes:
                return codes
        return ["en", "tur"]


# ─────────────────────── ayrıntılar penceresi ───────────────────────

class DetailsWindow(ctk.CTkToplevel):
    """Ortam kontrolü + nadiren gereken ayarlar; ana ekranı kalabalıklaştırmaz.

    Tek görünüm kararının anahtarı bu pencere: adaptör, kanal, deauth yöntemi
    ve dil gibi alanlar silinmedi, ana ekrandan çıkarıldı. Kullanıcı yalnızca
    "Detaylar"a bastığında açılır; otomatik seçimler zaten yapıldığı için
    buraya bakmak zorunda kalmaz.
    """

    def __init__(self, master, settings: AttackSettings, controller,
                 env_checks: List[EnvironmentCheck],
                 on_install: Callable[[], None],
                 on_refresh: Callable[[], None],
                 on_close: Callable[[], None] = None, **kw):
        super().__init__(master, fg_color=DARK_BG, **kw)
        self.title(t("details.title"))
        self.geometry("560x620")
        self.minsize(480, 520)
        self.configure(fg_color=DARK_BG)
        self.transient(master)
        self._settings = settings
        self._ctrl = controller
        self._on_install = on_install
        self._on_refresh = on_refresh
        self._on_close = on_close
        self.protocol("WM_DELETE_WINDOW", self.close)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(head, text=t("details.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(head, text="✕", width=28, height=26,
                      fg_color="transparent", hover_color=CARD_HOVER,
                      text_color=TEXT_SEC, border_width=0,
                      command=self.close).pack(side="right")

        ctk.CTkLabel(self, text=t("details.desc"), font=FONT_UI_S,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=500).pack(fill="x", padx=18, pady=(2, 10))

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=ELEV_BG,
            scrollbar_button_hover_color=mix_colour(ELEV_BG, ACCENT2, 0.5))
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._build_environment(body, env_checks)
        self._build_manual(body)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        make_button(footer, t("details.done"), "primary",
                    command=self.close, height=34).pack(side="right")

        self.after(120, self._focus)

    # ── bölümler ────────────────────────────────────────────────

    def _build_environment(self, parent, checks) -> None:
        sec = SectionCard(parent, t("app.health.title"),
                          t("app.health.desc"), accent=ACCENT2)
        sec.pack(fill="x", padx=6, pady=(4, 6))
        body = sec.body()

        missing = [c for c in checks if not c.ok and c.required]
        if missing:
            make_button(body, f"📦  {t('app.health.install')}", "warn",
                        command=self._on_install, height=30).pack(
                anchor="w", pady=(0, 8))

        checklist = Checklist(body)
        checklist.pack(fill="x")
        if checks:
            checklist.show(checks)
        else:
            checklist.show_loading(t("app.health.checking.detail"))

        make_button(body, f"🔄  {t('config.adapter.refresh')}", "outline-info",
                    command=self._on_refresh, height=28,
                    font=FONT_UI_S).pack(anchor="w", pady=(10, 0))

    def _build_manual(self, parent) -> None:
        sec = SectionCard(parent, t("details.manual.title"),
                          t("details.manual.desc"), accent=WARN)
        sec.pack(fill="x", padx=6, pady=(0, 6))
        body = sec.body()
        body.columnconfigure(1, weight=1)

        form_label(body, t("config.scan.channel")).grid(
            row=0, column=0, sticky="w", pady=ROW_PAD)
        self._channel = form_entry(body, t("config.scan.channel_ph"), width=90,
                                   height=30)
        self._channel.insert(0, str(self._settings.channel or ""))
        self._channel.grid(row=0, column=1, sticky="w", pady=ROW_PAD)

        form_label(body, t("config.attack.deauth")).grid(
            row=1, column=0, sticky="w", pady=ROW_PAD)
        form_combo(body, ["aireplay-ng", "mdk4"], width=150,
                   height=30).grid(row=1, column=1, sticky="w", pady=ROW_PAD)

        form_label(body, t("config.attack.lang")).grid(
            row=2, column=0, sticky="w", pady=ROW_PAD)
        self._cli_lang = ctk.StringVar(value=self._settings.language)
        form_combo(body, AttackSettings.languages(REPO_DIR),
                   self._cli_lang, width=110, height=30).grid(
            row=2, column=1, sticky="w", pady=ROW_PAD)

        ctk.CTkLabel(body, text=t("details.manual.note"), font=FONT_UI_XS,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=440).grid(row=3, column=0, columnspan=2,
                                          sticky="w", pady=(8, 0))

    # ── kapanış ─────────────────────────────────────────────────

    def _focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._settings.channel = self._channel.get().strip()
            self._settings.language = (self._cli_lang.get() or "tur")
        except Exception:
            pass
        if self._on_close:
            self._on_close()
        try:
            self.destroy()
        except Exception:
            pass

    def refresh_checklist(self, checks) -> None:
        for child in list(self.winfo_children()):
            if isinstance(child, ctk.CTkScrollableFrame):
                for section in child.winfo_children():
                    for inner in getattr(section, "winfo_children", list)():
                        if isinstance(inner, Checklist):
                            inner.show(checks)
                return


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

        # Tek görünüm: kullanıcı yalnızca ağ seçer ve Başlat'a basar.
        # Adaptör/kanal/deauth otomatik; nadiren gereken alanlar Detaylar
        # penceresinde. Handshake yakalanınca portal kendiliğinden açılır.
        self._settings = AttackSettings()
        self._settings.language = "tur" if i18n.get_language() == "tr" else "en"
        self._basic_chain = False
        self._details_window: Optional[DetailsWindow] = None

        self._state = AttackState.IDLE
        self._target: Optional[TargetCandidate] = None
        self._env_checks: List[EnvironmentCheck] = []
        self._install_attempted = False
        self._install_visible = False
        self._step = 0
        self._active_tab = "networks"
        self._ui_ready = False
        # Gömülü konsol sekmesi durumu
        self._console_job = None
        self._console_busy = False
        self._console_sel: Optional[str] = None
        self._console_windows: List[tuple] = []
        # Saldırı başlarken sekme yalnızca bir kez otomatik değişsin.
        self._console_autoswitched = False
        self._console_misses = 0
        self._console_last = ""

        self._build_ui()
        self._update_status(AttackState.IDLE)
        self._fade_in()
        self.after(150, self._maximize)
        self.after(200, lambda: self._ctrl.check_environment())
        self.after(500, self._refresh_handshake_archive)
        self._upd_status = None
        self.after(900, lambda: self._check_updates(manual=False))

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
        self.configure(fg_color=DARK_BG)

        self._build_topbar()
        self._build_activity_strip()
        self._build_update_bar()

        self._build_centre(body=None)

        self._build_footer()

        # Bildirim şeridi: üst şeridin altında, yerleşimi iterek açılır.
        # Yüzen bir katman olsaydı altındaki düğmeleri örterdi.
        self._notify_host = NotificationHost(self, after_widget=self._step_row)
        self._toast_host = self._notify_host

        self._tabs.set(self._tab_names[self._active_tab])
        self._ui_ready = True
        self._load_portals()
        self._refresh_hint()
        self._sync_action_buttons()

    # ── üst çubuk ───────────────────────────────────────────────

    def _build_topbar(self) -> None:
        """Marka, mod/dil geçişleri ve durum rozeti."""
        top = ctk.CTkFrame(self, fg_color=CHROME_BG, height=64,
                           corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Logo: yuvarlak köşeli yeşil rozet içinde şimşek — markaya kimlik.
        ctk.CTkLabel(top, text="⚡", font=("Inter", 18),
                     text_color=ACCENT_ON, fg_color=ACCENT,
                     corner_radius=9, width=32, height=32).pack(
            side="left", padx=(18, 10), pady=16)
        ctk.CTkLabel(top, text="CapCapWifi", font=FONT_BRAND,
                     text_color=TEXT_PRI).pack(side="left", pady=8)
        ctk.CTkLabel(top, text=f"  {t('app.subtitle')}",
                     font=FONT_UI, text_color=MUTED).pack(side="left", pady=9)

        self._status_badge = StatusBadge(top)
        self._status_badge.pack(side="right", padx=(8, 18), pady=13)

        # Dil değiştirici: EN / TR, anında yeniden çizer. Tek görünüme
        # geçtikten sonra Basit/Detay geçişi kaldırıldı; burada yalnızca
        # dil kalıyor.
        self._lang_switch = segmented(
            top, ["EN", "TR"], command=self._on_language_selected)
        self._lang_switch.pack(side="right", padx=(0, 4), pady=13)
        self._lang_switch.set("TR" if i18n.get_language() == "tr" else "EN")

    def _build_activity_strip(self) -> None:
        """Vurgu çizgisi + meşguliyet şeridi.

        Boştayken yalnızca ince yeşil çizgi görünür (marka vurgusu). Bir iş
        başladığında aynı yerden süpüren bir ışık geçer; pencereye nereden
        bakılırsa bakılsın "çalışıyor" bilgisi görünür olur.
        """
        self._accent_line = ctk.CTkFrame(self, fg_color=ACCENT, height=2,
                                         corner_radius=0)
        self._accent_line.pack(fill="x")
        self._activity = ActivityBar(self, height=3, bg=CHROME_BG)
        self._activity_visible = False

    def _set_activity(self, busy: bool) -> None:
        """Meşguliyet şeridini aç/kapat – tekrarlı çağrılara dayanıklı."""
        if busy == self._activity_visible:
            return
        self._activity_visible = busy
        if busy:
            self._activity.pack(fill="x", after=self._accent_line)
            self._activity.start()
        else:
            self._activity.stop()
            self._activity.pack_forget()

    # ── tek görünüm: adımlar · özet · sekmeler · log ────────────

    def _build_centre(self, body=None) -> None:
        """Tek görünümlü ana yerleşim.

        Basit/Detay ayrımı kaldırıldı: tek görünüm var ve kullanımı eski
        "Basit" mod kadar kolay. Kullanıcı yalnızca bir ağ satırına dokunur
        ve "Başlat"a basar; adaptör, kanal ve deauth yöntemi otomatik seçilir.

        Yukarıdan aşağıya:
          1. adım şeridi (tek satır, yer kaplamaz)
          2. seçili ağ özeti (sinyal / bağlı cihaz / yayınlanacak sayfa)
          3. tarama kontrolleri + eylem düğmeleri
          4. sekmeler (Ağlar, Şifreler, Konsollar, Nasıl kullanılır)
          5. canlı log şeridi

        Detay modunda sol/sağ sütunlarda duran her şey korunur, ama yalnızca
        gerektiğinde açılır: ortam kontrolü sağ üstteki düğmeden bir pencerede,
        adaptör/kanal gibi nadiren gereken alanlar aynı pencerenin altında.
        """
        del body

        steps = tuple(t(f"step.{key}") for key in
                      ("adapter", "scan", "target", "attack", "result"))
        self._guide = GuideBar(self, steps)
        self._guide.pack(fill="x", padx=12, pady=(10, 0))
        self._guide.set_active(self._step)

        # ── 2. seçili ağ özeti ──
        self._summary = SelectionSummary(self, on_portal_change=self._refresh_hint)
        self._summary.pack(fill="x", padx=12, pady=(8, 0))

        # ── 3. tarama + eylemler ──
        self._step_row = ctk.CTkFrame(self, fg_color="transparent")
        self._step_row.pack(fill="x", padx=12, pady=(8, 0))
        self._build_action_bar(self._step_row)
        self._build_scan_controls(self._step_row)

        # ── 4. sekmeler ──
        centre = ctk.CTkFrame(self, fg_color="transparent")
        centre.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        centre.rowconfigure(0, weight=1)
        centre.columnconfigure(0, weight=1)

        self._tabs = ctk.CTkTabview(
            centre, fg_color=PANEL_BG,
            segmented_button_fg_color=CARD_BG,
            segmented_button_selected_color=ACCENT_DIM,
            segmented_button_selected_hover_color=mix_colour(ACCENT_DIM,
                                                             ACCENT, 0.22),
            segmented_button_unselected_color=CARD_BG,
            segmented_button_unselected_hover_color=CARD_HOVER,
            text_color=TEXT_PRI,
            corner_radius=12,
        )
        self._tabs.grid(row=0, column=0, sticky="nsew")
        self._tab_names = {
            "networks": f"📡  {t('app.tab.networks')}",
            "credentials": f"🔑  {t('app.tab.credentials')}",
            "consoles": f"🖥  {t('app.tab.consoles')}",
            "help": f"❓  {t('app.tab.help')}",
        }
        tab_nets = self._tabs.add(self._tab_names["networks"])
        tab_creds = self._tabs.add(self._tab_names["credentials"])
        tab_consoles = self._tabs.add(self._tab_names["consoles"])
        tab_help = self._tabs.add(self._tab_names["help"])

        self._net_table = NetworkTable(tab_nets, on_select=self._on_target_select)
        self._net_table.pack(fill="both", expand=True)

        self._cred_panel = CredentialsPanel(
            tab_creds,
            on_use_portal=self._start_portal_for_handshake,
            on_crack=self._start_crack_for_handshake,
        )
        self._cred_panel.pack(fill="both", expand=True)

        self._build_console_tab(tab_consoles)

        help_box = ctk.CTkFrame(tab_help, fg_color="transparent")
        help_box.pack(fill="both", expand=True)
        help_text = ctk.CTkTextbox(help_box, fg_color=DARK_BG,
                                   text_color=TEXT_PRI, font=FONT_MONO_S,
                                   wrap="word", corner_radius=10,
                                   border_width=1, border_color=BORDER,
                                   scrollbar_button_color=ELEV_BG,
                                   scrollbar_button_hover_color=mix_colour(
                                       ELEV_BG, ACCENT2, 0.5))
        help_text.pack(fill="both", expand=True, padx=6, pady=6)
        help_text.insert("1.0", t("help.text"))
        help_text.configure(state="disabled")

        # ── 5. canlı log şeridi ──
        strip = ctk.CTkFrame(self, fg_color="transparent", height=150)
        strip.pack(fill="x", padx=12, pady=(8, 8))
        strip.pack_propagate(False)
        self._log_panel = LogPanel(strip)
        self._log_panel.pack(fill="both", expand=True)

    def _build_scan_controls(self, parent) -> None:
        """Tarama süresi/bant/kanal – özetin sağ üstünde, ferah tek satır.

        Bunlar tek görünümde de gerekli (tarama süresi saldırıyı etkiliyor),
        ama form gibi görünmemeleri için küçük ve ikincil tutuldu.
        """
        bar = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10,
                           border_width=1, border_color=BORDER)
        bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(inner, text=t("config.scan.time_short"),
                     font=FONT_UI_S, text_color=MUTED).pack(
            side="left", padx=(0, 6))
        self._scan_time = form_entry(inner, width=64, height=28)
        self._scan_time.insert(0, "30")
        self._scan_time.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text=t("config.scan.band"), font=FONT_UI_S,
                     text_color=MUTED).pack(side="left", padx=(0, 6))
        self._band_var = ctk.StringVar(value=t("band.bg"))
        form_combo(inner, list(band_labels()), self._band_var, width=118,
                   height=28).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text=t("config.scan.channel"), font=FONT_UI_S,
                     text_color=MUTED).pack(side="left", padx=(0, 6))
        self._channel_e = form_entry(inner, t("config.scan.channel_ph"),
                                     width=64, height=28)
        self._channel_e.pack(side="left", padx=(0, 16))

        # Sağda: ortam kontrolü ve dil-bağımsız yardımcı eylemler.
        self._btn_health = make_button(
            inner, f"🩺  {t('app.health.title')}", "outline-muted",
            command=self._open_details, height=28, font=FONT_UI_S)
        self._btn_health.pack(side="right")
        self._btn_update = icon_button(
            inner, "⬆", "outline-info",
            command=lambda: self._check_updates(manual=True))
        self._btn_update.pack(side="right", padx=(0, 6))

        auto_wrap(ctk.CTkLabel(
            inner, text=t("summary.action_hint"), font=FONT_UI_XS,
            text_color=MUTED, anchor="w", justify="left",
        )).pack(side="left", fill="x", expand=True, padx=(4, 10))

    def _build_action_bar(self, parent) -> None:
        """Dört ana eylem: tara, başlat, durdur, temizle.

        Her düğmenin kendi rengi var (yeşil / amber / kırmızı kontur / gri
        kontur) ve pasif halleri o renge ait nötr bir yüzeye döner. Metin hiç
        bir türde beyaz değil: açık vurgu dolgularının üzerinde beyaz okunmaz.
        """
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=0, column=0, columnspan=4, sticky="ew")
        for column in range(4):
            btn_row.columnconfigure(column, weight=1)

        self._btn_scan = make_button(
            btn_row, f"🔍  {t('app.btn.scan')}", "primary",
            command=self._do_scan, height=42, corner_radius=12, width=1)
        self._btn_scan.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self._btn_attack = make_button(
            btn_row, f"⚡  {t('app.btn.attack')}", "warn",
            command=self._do_attack, height=42, corner_radius=12, width=1)
        self._btn_attack.grid(row=0, column=1, padx=5, sticky="ew")

        self._btn_stop = make_button(
            btn_row, f"⏹  {t('app.btn.stop')}", "outline-danger",
            command=self._do_stop, height=42, corner_radius=12, width=1,
            state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=5, sticky="ew")

        self._btn_clear = make_button(
            btn_row, f"🗑  {t('app.btn.clear')}", "outline-muted",
            command=self._do_clear, height=42, corner_radius=12, width=1)
        self._btn_clear.grid(row=0, column=3, padx=(5, 0), sticky="ew")

    def _build_footer(self) -> None:
        hairline(self).pack(fill="x")
        bar = ctk.CTkFrame(self, fg_color=CHROME_BG, height=36,
                           corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # Yönlendirme satırı: kullanıcıya sıradaki tek adımı söyler. Meşgul
        # durumda soldaki spinner döner, böylece statik metin "takıldı mı"
        # sorusunu doğurmaz.
        self._bar_spinner = Spinner(bar, size=13, bg=CHROME_BG,
                                    colour=ACCENT2, thickness=2)
        self._bar_label = ctk.CTkLabel(
            bar, text="", font=FONT_UI_S, text_color=TEXT_SEC,
            anchor="w", justify="left")
        self._bar_label.pack(side="left", padx=(16, 10))
        ctk.CTkLabel(bar, text="github.com/sametuca/capcapwifi",
                     font=FONT_MONO_S,
                     text_color=TEXT_FAINT).pack(side="right", padx=16)

    # ── Language switching ──────────────────────────────────────

    def _on_language_selected(self, value: str) -> None:
        code = "tr" if str(value).strip().upper() == "TR" else "en"
        if code == i18n.get_language():
            return
        self._apply_language(code)

    def _apply_language(self, code: str) -> None:
        """Dili değiştirip pencereyi yeniden kurar; saldırı süreci etkilenmez."""
        i18n.set_language(code)
        i18n.save_language(code)
        self._settings.language = "tur" if code == "tr" else "en"
        self._rebuild()

    def _rebuild(self) -> None:
        """Pencereyi (dil değişiminde) durumu koruyarak yeniden kurar."""
        candidates = self._net_table.candidates
        selected = self._net_table.selected()
        # Eski widget'lar yıkılmadan önce callback'lerin onlara dokunmasını kes.
        self._ui_ready = False
        if self._console_job is not None:
            try:
                self.after_cancel(self._console_job)
            except Exception:
                pass
            self._console_job = None
        self._console_last = ""
        self._close_details()

        for child in list(self.winfo_children()):
            child.destroy()

        self._install_visible = False
        self._build_ui()

        if candidates:
            self._net_table.load(candidates)
            if selected is not None:
                self._net_table._select(selected)
        elif self._env_checks:
            self._summary.set_candidate(None, animate=False)
        self._load_portals()
        self._refresh_handshake_archive()

        if self._upd_status is not None and getattr(self._upd_status, "behind", 0) > 0:
            self._update_bar_label.configure(
                text="⬆  " + t("update.available", count=self._upd_status.behind))
            self._show_update_bar()
        self._set_step(self._step)
        self._update_status(self._state)

    # ── Gömülü konsollar ────────────────────────────────────────

    def _build_console_tab(self, tab) -> None:
        """Saldırının tmux pencerelerini ayrı terminallere bakmadan gösterir."""
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(head, text=t("console.title"), font=FONT_UI_B,
                     text_color=TEXT_PRI).pack(side="left")

        # Yeni pencere geldiğinde başlıkta kısa bir parıltı: sekme açıkken
        # bile "yeni bir konsol bağlandı" bilgisi görünür.
        self._console_spinner = Spinner(head, size=14, bg=PANEL_BG,
                                        colour=ACCENT2, thickness=2)
        self._console_picker = ctk.CTkOptionMenu(
            head, values=[t("console.waiting")],
            command=self._on_console_pick, width=240, height=30,
            font=FONT_UI_S, corner_radius=8,
            fg_color=CARD_BG, button_color=mix_colour(CARD_BG, ACCENT2, 0.4),
            button_hover_color=mix_colour(CARD_BG, ACCENT2, 0.6),
            dropdown_fg_color=ELEV_BG, dropdown_hover_color=CARD_HOVER,
            dropdown_text_color=TEXT_PRI,
            text_color=TEXT_PRI, text_color_disabled=OFF_TEXT,
        )
        self._console_picker.pack(side="right")

        auto_wrap(ctk.CTkLabel(
            tab, text=t("console.hint"), font=FONT_UI_S, text_color=MUTED,
            justify="left", anchor="w",
        )).pack(fill="x", padx=10, pady=(0, 6))

        self._console_text = ctk.CTkTextbox(
            tab, fg_color=DARK_BG, text_color=CONSOLE_FG, font=FONT_MONO_S,
            wrap="none", corner_radius=10, border_width=1,
            border_color=BORDER_SOFT,
            scrollbar_button_color=ELEV_BG,
            scrollbar_button_hover_color=mix_colour(ELEV_BG, ACCENT2, 0.5),
        )
        self._console_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._render_console("")
        self._console_text.configure(state="disabled")

    def _on_console_pick(self, label: str) -> None:
        for index, name in self._console_windows:
            if label == f"{name}  (#{index})":
                self._console_sel = index
                self._console_last = ""
                self._start_console_poll()
                return

    def _start_console_poll(self) -> None:
        if self._console_job is None and getattr(self, "_ui_ready", False):
            self._console_job = self.after(300, self._console_tick)

    def _console_tick(self) -> None:
        self._console_job = None
        if not self._ui_ready or not hasattr(self, "_console_text"):
            return
        # Yavaş bir sudo çağrısı arayüzü dondurmasın: ayrı iş parçacığında oku.
        if not self._console_busy:
            self._console_busy = True
            threading.Thread(target=self._fetch_consoles, daemon=True).start()
        if self._ctrl.is_busy:
            self._console_job = self.after(1800, self._console_tick)

    def _fetch_consoles(self) -> None:
        try:
            windows = self._ctrl.console_windows()
            index = self._console_sel
            if not index and windows:
                index = windows[0][0]
            text = self._ctrl.capture_console(index) if index else ""
        except Exception:
            windows, index, text = [], None, ""
        finally:
            self._console_busy = False
        try:
            self.after(0, lambda: self._apply_consoles(windows, index, text))
        except Exception:
            pass

    def _apply_consoles(self, windows, index, text) -> None:
        if not getattr(self, "_ui_ready", False) or not hasattr(self, "_console_text"):
            return
        if windows:
            self._console_misses = 0
            self._console_windows = list(windows)
            labels = [f"{name}  (#{i})" for i, name in windows]
            if index:
                self._console_sel = index
            current = next((label for label, (i, _n) in zip(labels, windows)
                            if i == self._console_sel), None)
            try:
                self._console_picker.configure(values=labels)
                if current:
                    self._console_picker.set(current)
            except Exception:
                pass
        if not windows and not text:
            # Saldırı sürerken pencere yoksa kullanıcı boş ekranla kalmasın.
            self._console_misses += 1
        if text != self._console_last:
            self._console_last = text
            self._render_console(text)
        elif not text:
            if self._console_misses >= 3:
                self._render_console(t("console.not_found"))
            else:
                self._render_console(t("console.waiting"))

    def _render_console(self, text: str) -> None:
        if not hasattr(self, "_console_text"):
            return
        body = text or t("console.empty")
        self._console_text.configure(state="normal")
        self._console_text.delete("1.0", "end")
        self._console_text.insert("1.0", body)
        self._console_text.see("end")
        self._console_text.configure(state="disabled")

    def _set_step(self, index: int) -> None:
        self._step = index
        self._guide.set_active(index)

    def _show_tab(self, key: str) -> None:
        self._active_tab = key
        if key == "consoles":
            # Sekme açıldığı anda akış başlasın; saldırı bitmişse son kare kalır.
            self._start_console_poll()
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
            else:
                # Boş sonuç "hiçbir şey olmadı" gibi görünmesin: tablo ve alt
                # satır neden boş olduğunu ve ne yapılacağını söylesin.
                self._net_table.set_hint(t("networks.empty_after_scan"), "warn")
                self._notify(t("toast.scan_empty"), "warn", 6000)
                self._refresh_hint()
        self.after(0, _apply)

    def _on_credential(self, cred: CapturedCredential) -> None:
        def _apply():
            self._cred_panel.add(cred)
            self._show_tab("credentials")
            self._set_step(4)
            self._refresh_hint()
            self._notify(t("toast.credential", ssid=cred.ssid or "-"),
                         "success", 6000)
            for button in self._scan_buttons():
                button.flash(ACCENT)
            try:
                self.bell()
            except Exception:
                pass
        self.after(0, _apply)

    def _on_environment(self, checks) -> None:
        def _apply():
            self._env_checks = list(checks)
            self._refresh_details_checklist()
            button = getattr(self, "_btn_health", None)
            if button is not None:
                button.set_loading(False)
            missing = [c for c in self._env_checks if not c.ok and c.required]
            for check in self._env_checks:
                if not check.ok:
                    self._log_panel.append(
                        t("log.env_line", name=check.name,
                          detail=check.detail, hint=check.hint), "warn")

            if missing:
                self._notify(t("toast.env_missing", count=len(missing)),
                             "warn", 5200)
            else:
                self._notify(t("checklist.ready"), "success", 3600)

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
        self._settings.set_target(target)
        # Seçili ağ kartı sinyali, cihaz sayısını ve yayınlanacak sayfayı
        # gösterir; kullanıcı başka yere bakmak zorunda kalmaz.
        self._summary.set_candidate(target)
        self._log_panel.append(
            t("log.target_selected", ssid=target.clean_essid,
              bssid=target.bssid, channel=target.channel), "info")
        self._set_step(3)
        self._refresh_hint()
        # Seçim yapıldığını göz kaçırmasın: "Başlat" kısa süre parlar.
        if hasattr(self, "_btn_attack") and self._btn_attack.cget("state") == "normal":
            self._btn_attack.flash(WARN)

        if target.has_handshake:
            self._log_panel.append(t("log.target_has_handshake"), "info")
        if target.uses_pmf:
            self._log_panel.append(
                t("log.pmf_target", ssid=target.clean_essid), "warn")

    def _on_handshake(self, hf: HandshakeFile) -> None:
        def _apply():
            self._refresh_handshake_archive()
            # Kart yok: kaydedilen dosya ve "Portal'da Kullan" düğmesi
            # Şifreler sekmesindeki handshake arşivinde. Kullanıcı oraya
            # doğrudan getirilir; sıradaki adım böylece görünür olur.
            self._show_tab("credentials")
            self._log_panel.append(
                t("log.handshake_captured", file=hf.filepath), "success")
            self._log_panel.append(t("log.handshake_next"), "info")
            self._set_step(4)
            self._refresh_hint()
            self._notify(t("toast.handshake", ssid=hf.ssid or "-"),
                         "success", 6500)
            if self._basic_chain:
                self._log_panel.append(t("basic.phase.portal"), "success")
                self._start_portal_after_handshake(hf)
            try:
                self.bell()
                self.lift()
                self.focus_force()
            except Exception:
                pass
        self.after(0, _apply)

    def _start_portal_after_handshake(self, hf, attempt: int = 0) -> None:
        """Yakalanan handshake ile portalı kendiliğinden aç.

        Handshake Snooper kendini kapatırken süreç hâlâ meşgul olabilir; bu
        yüzden kısa aralıklarla boşalmasını bekleriz.
        """
        if not self._basic_chain:
            return
        if self._ctrl.is_busy:
            if attempt < 30:
                self.after(1000, lambda: self._start_portal_after_handshake(
                    hf, attempt + 1))
            return
        self._basic_chain = False
        self._start_portal_for_handshake(hf)

    def _start_portal_for_handshake(self, hf: Optional[HandshakeFile]) -> None:
        """Handshake arşivinden tek tıkla portal başlat.

        Satır formu doldurmakla kalmıyor, saldırıyı gerçekten başlatıyor.
        Meşgulse yalnızca yönlendirme metni gösterilir.
        """
        if hf is None:
            return

        self._settings.use_portal()
        # Handshake dosyası bir ağın kopyasıdır: hedefi o ağa taşı ki özet
        # kartı da doğru ağı göstersin.
        target = self._target
        if target is None or target.bssid.upper() != (hf.bssid or "").upper():
            target = self._find_candidate(hf.bssid, hf.ssid)
            if target is not None:
                self._on_target_select(target)

        self._show_tab("networks")
        self._set_step(3)
        self._log_panel.append(t("basic.portal_ready", ssid=hf.ssid), "success")

        if self._ctrl.is_busy:
            self._log_panel.append(t("log.guide_start_hint"), "info")
        else:
            self._log_panel.append(t("log.guide_portal_autostart"), "info")
            # _do_attack değil: o, handshake aşamasına geri dönerdi.
            self.after(250, self._start_current_attack)
        self._refresh_hint()

    def _find_candidate(self, bssid: str, ssid: str) -> Optional[TargetCandidate]:
        """Taranan ağlar arasında BSSID (yoksa SSID) ile eşleşen satırı bulur."""
        wanted_bssid = (bssid or "").upper()
        for candidate in self._ctrl.candidates:
            if wanted_bssid and candidate.bssid.upper() == wanted_bssid:
                return candidate
        for candidate in self._ctrl.candidates:
            if ssid and candidate.essid.strip() == ssid.strip():
                return candidate
        return None

    def _start_crack_for_handshake(self, hf: Optional[HandshakeFile]) -> None:
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

    # ── portal listesi ──────────────────────────────────────────

    def _load_portals(self) -> None:
        """Portal listesini seçili ağ kartına doldurur."""
        portals = self._ctrl.list_portals()
        self._summary.load_portals(portals)
        self._settings.set_portal(
            AttackSettings.default_portal(portals) or self._summary.selected_portal())
        if self._settings.portal is not None:
            self._summary.set_portal(self._settings.portal.display_title)
        self._refresh_hint()

    def _selected_portal(self) -> Optional[PortalSite]:
        """Özet kartındaki seçim tek doğru kaynaktır."""
        return self._summary.selected_portal()

    # ── Button handlers ─────────────────────────────────────────

    def _do_scan(self) -> None:
        if self._ctrl.is_busy:
            return
        self._settings.set_scan_time(self._scan_time.get())
        self._settings.band = band_labels().get(self._band_var.get(), "bg")
        self._settings.channel = (self._channel_e.get() or "").strip()
        iface, scan_time, channel, band = self._settings.scan_params()
        self._log_panel.append(
            t("log.scan_start", iface=iface or t("log.iface_auto"),
              seconds=scan_time), "info")
        self._set_step(1)
        self._ctrl.start_scan(interface=iface, scan_time=scan_time,
                              channel=channel, band=band)

    def _do_attack(self) -> None:
        """Tek eylem: hedefi hazırla, sonra saldırıyı başlat.

        Kullanıcı tek bir "Başlat" görür. Arka planda iki aşama var:
        handshake yakalamak ve (yakalanınca) portalı açmak. WPA3/PMF ağlarda
        deauth işe yaramadığı için doğrudan portala geçilir.
        """
        if self._ctrl.is_busy:
            return
        if not self._prepare_attack():
            return
        self._start_current_attack()

    def _prepare_attack(self) -> bool:
        """Hedefi ve saldırı türünü belirler; başlatılabilir mi sorusunu yanıtlar."""
        target = self._target
        if target is None:
            target = self._net_table.select_first_with_clients()
            if target is None:
                self._net_table.set_hint(t("log.no_target_hint"), "warn")
                self._log_panel.append(t("basic.need_target"), "warn")
                self._show_tab("networks")
                return False
            self._on_target_select(target)

        self._settings.set_target(target)

        if target.uses_pmf:
            # WPA3/PMF: deauth çerçeveleri yok sayılır, handshake beklemek
            # boşa zaman. Doğrudan sahte ağ + portal açılır.
            self._log_panel.append(
                t("log.pmf_target", ssid=target.clean_essid), "warn")
            self._settings.use_portal()
            self._basic_chain = False
            return True

        self._settings.use_handshake()
        self._basic_chain = True
        self._log_panel.append(t("basic.phase.handshake"), "info")
        return True

    def _start_current_attack(self) -> None:
        """Hazırlanmış saldırıyı başlatır (portal aşaması da bunu kullanır)."""
        if self._ctrl.is_busy:
            return

        if not self._settings.has_target():
            target = self._net_table.select_first_with_clients()
            if target is None:
                self._net_table.set_hint(t("log.no_target_hint"), "warn")
                self._log_panel.append(t("log.no_target"), "warn")
                self._show_tab("networks")
                return
            self._on_target_select(target)

        self._settings.set_target(self._target)
        if self._settings.is_portal:
            portal = self._selected_portal()
            if portal is None:
                self._log_panel.append(t("log.no_portal"), "warn")
                return
            self._settings.set_portal(portal)

        config = self._settings.build_config()
        self._set_step(3)
        self._console_autoswitched = False
        self._console_misses = 0
        self._console_last = ""
        if self._settings.is_portal:
            self._log_panel.append(
                t("log.portal_info", title=self._settings.portal_title(),
                  desc=(self._settings.portal.description
                        if self._settings.portal else "")), "info")
        self._log_panel.append(
            t("log.attack_start", attack=config.attack_type.value,
              target=(config.target_essid or config.target_bssid)), "info")
        self._ctrl.start_attack(config)

    def _do_stop(self) -> None:
        self._basic_chain = False
        self._ctrl.stop()

    def _start_install(self, auto: bool = False) -> None:
        if self._ctrl.is_busy:
            return
        self._install_attempted = True
        self._set_install_busy(True, t("app.health.installing"))
        if auto:
            self._log_panel.append(t("log.install_first"), "info")
        self._ctrl.install_dependencies(language=self._settings.language)

    def _set_install_busy(self, visible: bool, text: str = "") -> None:
        """Kurulum sürerken üstteki meşguliyet şeridini ve bildirimi yönetir.

        Ana ekranda ilerleme çubuğu ve etiket için yer yok; kurulum ilerlemesi
        Detaylar penceresindeki checklist'te ve bildirim şeridinde görünür.
        """
        if not visible:
            if self._install_visible:
                self._install_visible = False
                self._set_activity(self._state_busy())
            return
        if self._install_visible:
            return
        self._install_visible = True
        self._set_activity(True)
        self._notify(text or t("app.health.installing"), "info", 6000)

    def _do_clear(self) -> None:
        self._log_panel.clear()
        self._net_table.clear()
        self._target = None
        self._settings.set_target(None)
        self._summary.set_candidate(None, animate=False)
        self._set_step(1 if self._ctrl.candidates else 0)
        self._refresh_hint()

    # ── ayrıntılar penceresi ────────────────────────────────────

    def _open_details(self) -> None:
        """Ortam kontrolü ve nadiren gereken ayarları ayrı pencerede aç."""
        if self._details_window is not None:
            try:
                if self._details_window.winfo_exists():
                    self._details_window.lift()
                    self._details_window.focus_force()
                    return
            except Exception:
                pass
            self._details_window = None

        self._details_window = DetailsWindow(
            self, self._settings, self._ctrl, self._env_checks,
            on_install=self._start_install,
            on_refresh=self._recheck_environment,
            on_close=self._on_details_closed,
        )

    def _on_details_closed(self) -> None:
        self._details_window = None
        self._refresh_hint()

    def _close_details(self) -> None:
        window = self._details_window
        self._details_window = None
        if window is None:
            return
        try:
            window.destroy()
        except Exception:
            pass

    def _refresh_details_checklist(self) -> None:
        window = self._details_window
        if window is None:
            return
        try:
            window.refresh_checklist(self._env_checks)
        except Exception:
            pass

    # ── Güncelleme (git) ─────────────────────────────────────────

    def _build_update_bar(self) -> None:
        """Üstteki güncelleme bildirim şeridi — yalnızca güncelleme varken görünür."""
        self._update_bar = ctk.CTkFrame(self, fg_color=ACCENT2_DIM,
                                        corner_radius=0)
        inner = ctk.CTkFrame(self._update_bar, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=7)
        self._update_bar_label = ctk.CTkLabel(
            inner, text="", font=FONT_UI_B, text_color=ACCENT2, anchor="w")
        self._update_bar_label.pack(side="left")
        ctk.CTkButton(
            inner, text=t("update.btn_later"), width=76, height=26,
            command=self._hide_update_bar, fg_color="transparent",
            hover_color=CARD_HOVER, border_width=1, border_color=BORDER,
            text_color=TEXT_SEC, corner_radius=8,
            font=FONT_UI_SB).pack(side="right")
        ctk.CTkButton(
            inner, text=t("update.btn_now"), width=130, height=26,
            command=self._do_update, fg_color=ACCENT, text_color=DARK_BG,
            hover_color=ACCENT_DK, corner_radius=8,
            font=FONT_UI_B).pack(side="right", padx=(0, 8))
        # başlangıçta gizli; _apply_update_status/_show_update_bar gösterir

    def _show_update_bar(self) -> None:
        try:
            self._update_bar.pack(fill="x", after=self._accent_line)
        except Exception:
            self._update_bar.pack(fill="x")

    def _hide_update_bar(self) -> None:
        try:
            self._update_bar.pack_forget()
        except Exception:
            pass

    def _check_updates(self, manual: bool = True) -> None:
        if manual:
            self._log_panel.append(t("update.checking"), "info")

        def _work():
            status = updater.check_for_update()
            self.after(0, self._apply_update_status, status, manual)

        threading.Thread(target=_work, daemon=True).start()

    def _apply_update_status(self, status, manual: bool = False) -> None:
        self._upd_status = status
        if not getattr(self, "_ui_ready", False) or status is None:
            return
        # Güncelleme kontrolü arka planda çalışır; pencere bu arada yeniden
        # kurulmuşsa eski widget'lara dokunmak "invalid command name" üretir.
        try:
            bar_ok = bool(self._update_bar_label.winfo_exists())
        except Exception:
            bar_ok = False
        if not status.is_repo:
            if manual:
                self._log_panel.append(t("update.not_repo"), "warn")
            return
        if not status.ok:
            if manual:
                self._log_panel.append(t("update.error", msg=status.message), "warn")
            return
        if status.behind > 0:
            if bar_ok:
                self._update_bar_label.configure(
                    text="⬆  " + t("update.available", count=status.behind))
            self._show_update_bar()
            self._log_panel.append(t("update.available", count=status.behind), "info")
        else:
            self._hide_update_bar()
            if manual:
                self._log_panel.append(t("update.uptodate"), "success")

    def _do_update(self) -> None:
        if self._ctrl.is_busy:
            return
        if not messagebox.askyesno(t("update.confirm.title"),
                                   t("update.confirm.body")):
            return
        self._hide_update_bar()
        self._log_panel.append(t("update.doing"), "info")

        def _work():
            result = updater.apply_update()
            self.after(0, self._after_update, result)

        threading.Thread(target=_work, daemon=True).start()

    def _after_update(self, result) -> None:
        if result.ok:
            self._log_panel.append(t("update.done"), "success")
            try:
                messagebox.showinfo(t("update.confirm.title"), t("update.done"))
            except Exception:
                pass
        else:
            self._log_panel.append(t("update.failed", msg=result.message), "error")
            try:
                messagebox.showerror(t("update.confirm.title"),
                                     t("update.failed", msg=result.message))
            except Exception:
                pass

    # ── State / hint sync ───────────────────────────────────────

    def _sync_action_buttons(self) -> None:
        """Eylet düğmelerinin durumunu tek yerden yönetir.

        Kural: meşgulken yalnızca "Durdur" basılabilir; boştayken "Tara" ve
        "Başlat" aktif. Bu ayrım hem düğme durumuna hem de pasif tint
        görünümüne yansır (FxButton pasifikte kendi rengini soluklaştırır).
        """
        if not getattr(self, "_ui_ready", False):
            return
        busy = self._state in (AttackState.INSTALLING, AttackState.SCANNING,
                               AttackState.STARTING, AttackState.RUNNING)
        idle_state = "disabled" if busy else "normal"
        for button in self._scan_buttons():
            button.configure(state=idle_state)
        self._btn_attack.configure(state=idle_state)
        self._btn_stop.configure(state="normal" if busy else "disabled")
        if hasattr(self, "_btn_health"):
            self._btn_health.configure(state=idle_state)

        activity = self._state in (AttackState.INSTALLING,
                                   AttackState.SCANNING,
                                   AttackState.STARTING,
                                   AttackState.RUNNING,
                                   AttackState.CREDENTIALS_FOUND)
        self._set_activity(activity or self._install_visible)
        self._sync_scan_loading()

    def _state_busy(self) -> bool:
        return self._state in (AttackState.INSTALLING, AttackState.SCANNING,
                               AttackState.STARTING, AttackState.RUNNING)

    def _scan_buttons(self) -> List:
        return [self._btn_scan]

    def _sync_scan_loading(self) -> None:
        """Tarama sürerken düğme "aranıyor" görünsün, boştayken normale dönsün."""
        scanning = self._state is AttackState.SCANNING
        for button in self._scan_buttons():
            button.set_loading(scanning)
        if hasattr(self, "_net_table"):
            self._net_table.set_busy(
                scanning, t("hint.scanning") if scanning else "")

    def _update_status(self, state: AttackState) -> None:
        self._state = state
        self._status_badge.update_state(state.value)
        self._sync_action_buttons()

        if state is AttackState.INSTALLING:
            self._set_install_busy(True, t("app.health.installing"))
            self._set_step(0)

        if state is AttackState.SCANNING:
            self._set_step(1)
        elif state in (AttackState.STARTING, AttackState.RUNNING):
            self._set_step(3)
        elif state in (AttackState.HANDSHAKE_CAPTURED, AttackState.CREDENTIALS_FOUND):
            self._set_step(4)
        if state in (AttackState.INSTALLING, AttackState.SCANNING,
                     AttackState.STARTING, AttackState.RUNNING):
            self._start_console_poll()
        if state is AttackState.RUNNING and not self._console_autoswitched:
            self._console_autoswitched = True
            # Kullanıcı konsolları ayrı pencerelerde aramak zorunda kalmasın:
            # saldırı başlar başlamaz gömülü konsol sekmesi açılır.
            self._show_tab("consoles")
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        """Alttaki satır: kullanıcıya sıradaki tek adımı söyler."""
        if not getattr(self, "_ui_ready", False):
            return
        # Portal seçimi özet kartında yaşar; motor ayarları onu buradan alır.
        if hasattr(self, "_summary"):
            self._settings.set_portal(self._summary.selected_portal())
        if not hasattr(self, "_bar_label"):
            return
        state = self._state

        if state is AttackState.INSTALLING:
            text, colour = t("hint.installing"), ACCENT2
        elif state is AttackState.SCANNING:
            text, colour = t("hint.scanning"), ACCENT2
        elif state is AttackState.STARTING:
            text, colour = t("hint.starting"), WARN
        elif state is AttackState.RUNNING:
            if self._settings.is_portal:
                text, colour = t("hint.running.portal"), ACCENT
            else:
                text, colour = t("hint.running.handshake"), ACCENT
        elif state is AttackState.CREDENTIALS_FOUND:
            text, colour = t("hint.credentials"), ACCENT
        elif state is AttackState.HANDSHAKE_CAPTURED:
            text, colour = t("basic.hint.captured"), ACCENT
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
            elif not self._settings.has_target():
                text, colour = t("hint.pick_row"), ACCENT2
            else:
                text, colour = t("hint.target_ready"), ACCENT
                target = self._target
                if target is not None and target.uses_pmf:
                    text, colour = t("hint.pmf_target"), WARN

        # Meşgul durumlarda öne eklenen ▶ yerine spinner çalışsın: durağan oku
        # "takıldı mı" diye okunur.
        busy = state in (AttackState.INSTALLING, AttackState.SCANNING,
                         AttackState.STARTING, AttackState.RUNNING)
        self._set_hint(text, colour, busy)

    def _set_hint(self, text: str, colour: str, busy: bool = False) -> None:
        """Alt satırdaki yönlendirmeyi ve soldaki meşguliyet noktasını ayarlar."""
        if not hasattr(self, "_bar_label"):
            return
        self._bar_label.configure(text=text, text_color=colour)
        spinner = getattr(self, "_bar_spinner", None)
        if spinner is None:
            return
        if busy:
            spinner.set_colours(colour=colour, bg=CHROME_BG)
            if not spinner.winfo_ismapped():
                spinner.pack(side="left", padx=(16, 8))
            spinner.start()
        else:
            spinner.stop()
            if spinner.winfo_ismapped():
                spinner.pack_forget()

    # ── yardımcı eylemler ───────────────────────────────────────

    def _notify(self, text: str, kind: str = "info",
                timeout: int = 4500) -> None:
        """Üst şeritte kısa bir bildirim göster (log panelini bölmeden)."""
        host = getattr(self, "_notify_host", None)
        if host is None:
            return
        try:
            host.show(text, kind, timeout)
        except Exception:
            pass

    def _recheck_environment(self) -> None:
        """Ortam kontrolünü yeniden başlat; düğme meşgul görünümüne geçsin."""
        button = getattr(self, "_btn_health", None)
        if button is not None:
            if button.loading:
                return
            button.set_loading(True)
            self.after(6000, lambda: button.set_loading(False))
        self._ctrl.check_environment()
        self._notify(t("app.health.checking.detail"), "info", 2200)


# ─────────────────────────── Entry point ────────────────────────────

if __name__ == "__main__":
    app = CapCapWifiApp()
    app.mainloop()
