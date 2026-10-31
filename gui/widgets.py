"""
CapWifi GUI – yeniden kullanılabilir arayüz bileşenleri.

Buradaki sınıfların hiçbiri ağ veya süreç işlemez; yalnızca görüntüler ve
kullanıcı etkileşimini callback olarak dışarı verir. Görünen tüm metinler
i18n üzerinden gelir, bu yüzden pencere yeniden kurulduğunda dil değişir.

Tasarım dili: koyu zemin, yumuşak köşeli kartlar, tek vurgu rengi (neon yeşil)
ve ikincil olarak camgöbeği. Renk tokenları ``theme.py``'de; her metin/zemin
çifti WCAG AA kontrastını geçer. Vurgu dolgularının üzerine hiçbir zaman beyaz
yazılmaz – her vurgunun kendi koyu "üstüne yazılacak" tonu var.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import customtkinter as ctk

from effects import (
    Animator,
    NotificationBar,
    SkeletonList,
    Spinner,
    ease_in_out,
    ease_out_cubic,
    make_button,
    quiet_button,
)
from i18n import t
from theme import (
    ACCENT,
    ACCENT2,
    ACCENT2_DIM,
    ACCENT_DK,
    ACCENT_ON,
    BORDER,
    BORDER_SOFT,
    CARD_BG,
    CARD_HOVER,
    CARD_SEL,
    DANGER,
    DARK_BG,
    ELEV_BG,
    FONT_MONO,
    FONT_MONO_S,
    FONT_TITLE,
    FONT_UI,
    FONT_UI_B,
    FONT_UI_S,
    FONT_UI_SB,
    FONT_UI_XS,
    MUTED,
    OFF_BG,
    OFF_BORDER,
    OFF_TEXT,
    PANEL_BG,
    TEXT_PRI,
    TEXT_SEC,
    WARN,
    mix_colour,
)


# ────────────────────────── yardımcılar ────────────────────────────

def auto_wrap(label: "ctk.CTkLabel", minimum: int = 220,
              slack: int = 24) -> "ctk.CTkLabel":
    """Etiketi kapsayıcısının genişliğine göre sar.

    Bağlama kapsayıcıya yapılır: etiketin kendi <Configure> olayına bağlanınca
    customtkinter'ın scrollbar çizimi ile birlikte sonsuz yerleşim döngüsü
    oluşabiliyordu. Karşılaştırma `str()` üzerinden yapılır çünkü CTk sarmalayıcı
    nesnesi ile Tk widget'ı `==` ile hiç eşleşmez.
    """
    last_wrap = [0]
    parent = getattr(label, "master", None)

    def _apply(width: int) -> None:
        target = max(minimum, int(width) - slack)
        if abs(target - last_wrap[0]) >= 12:
            last_wrap[0] = target
            try:
                label.configure(wraplength=target)
            except Exception:
                pass

    def _resize(event) -> None:
        if parent is not None and str(event.widget) != str(parent):
            return
        _apply(event.width)

    if parent is not None:
        parent.bind("<Configure>", _resize, add="+")

        def _initial() -> None:
            try:
                _apply(parent.winfo_width())
            except Exception:
                pass

        parent.after(60, _initial)
    return label


def hairline(master, colour: str = BORDER_SOFT) -> ctk.CTkFrame:
    """Tek piksellik ayırıcı çizgi."""
    return ctk.CTkFrame(master, fg_color=colour, height=1, corner_radius=0)


def pill(master, text: str, colour: str, *, fg: Optional[str] = None,
         font=FONT_UI_SB, height: int = 22, padx: int = 8,
         **kw) -> ctk.CTkLabel:
    """Renkli rozet: yumuşak dolgu + aynı rengin okunur metni.

    Metin rengi dolguya değil, rozetin kendi tonuna göre seçilir; koyu dolgu
    üzerinde açık renk, açık dolgu üzerinde koyu "on" tonu kullanılır.
    """
    kw.setdefault("corner_radius", 6)
    return ctk.CTkLabel(
        master, text=text, font=font, height=height, padx=padx,
        text_color=colour,
        fg_color=fg if fg else mix_colour(CARD_BG, colour, 0.14), **kw)


def solid_pill(master, text: str, colour: str, on_colour: str, *,
               font=FONT_UI_SB, height: int = 22, padx: int = 8,
               **kw) -> ctk.CTkLabel:
    """Dolu rozet: vurgu dolgusu + üzerine okunur koyu metin."""
    kw.setdefault("corner_radius", 6)
    return ctk.CTkLabel(
        master, text=text, font=font, height=height, padx=padx,
        fg_color=colour, text_color=on_colour, **kw)


# ────────────────────────── form kontrolleri ───────────────────────

def form_entry(master, placeholder: str = "", width: int = 200,
               **kw) -> ctk.CTkEntry:
    """Tek satırlık giriş: koyu zemin, odakta camgöbeği kenarlık.

    Placeholder mutlak MUTED yerine TEXT_SEC kullanır: ipucu metni de
    okunabilir olmalı, "boş alan" gibi görünmemeli.
    """
    kw.setdefault("height", 30)
    return ctk.CTkEntry(
        master, placeholder_text=placeholder, width=width,
        fg_color=DARK_BG, border_color=BORDER, border_width=1,
        text_color=TEXT_PRI, placeholder_text_color=MUTED,
        font=FONT_UI, corner_radius=8, **kw)


def form_combo(master, values, variable=None, width: int = 200,
               **kw) -> ctk.CTkComboBox:
    """Açılır seçim: koyu zemin, vurgu rengi ok, okunur pasif metin."""
    kw.setdefault("height", 30)
    return ctk.CTkComboBox(
        master, values=values, variable=variable, width=width,
        fg_color=DARK_BG, border_color=BORDER, border_width=1,
        button_color=mix_colour(DARK_BG, ACCENT2, 0.35),
        button_hover_color=mix_colour(DARK_BG, ACCENT2, 0.55),
        dropdown_fg_color=ELEV_BG, dropdown_hover_color=CARD_HOVER,
        dropdown_text_color=TEXT_PRI,
        text_color=TEXT_PRI, text_color_disabled=OFF_TEXT,
        font=FONT_UI, dropdown_font=FONT_UI_S, corner_radius=8, **kw)


def form_label(master, text: str, **kw) -> ctk.CTkLabel:
    """Form satırı etiketi – sabit genişlik, sağa yaslı değil."""
    return ctk.CTkLabel(master, text=text, font=FONT_UI, text_color=TEXT_SEC,
                        anchor="w", **kw)


def segmented(master, values, variable=None, command=None,
              height: int = 28, **kw) -> ctk.CTkSegmentedButton:
    """Segment düğmesi: seçili parça yeşil dolgu + koyu metin.

    customtkinter varsayılanı seçili parçayı soluk yeşile boyayıp üzerine
    beyaz yazıyor; bu ikili burada da okunur değil. Burada seçili parça
    ACCENT dolgusu + ACCENT_ON metni, seçili olmayan OFF_BG + OFF_TEXT.
    """
    return ctk.CTkSegmentedButton(
        master, values=values, variable=variable, command=command,
        height=height, corner_radius=8, border_width=1,
        fg_color=OFF_BG, selected_color=ACCENT, selected_hover_color=ACCENT_DK,
        unselected_color=OFF_BG, unselected_hover_color=CARD_HOVER,
        text_color=OFF_TEXT, text_color_disabled=OFF_BORDER,
        font=FONT_UI_SB, **kw)


def progress_bar(master, colour: str = ACCENT2,
                 height: int = 5) -> ctk.CTkProgressBar:
    """İnce ilerleme çubuğu: ray koyu, dolgu vurgu rengi."""
    return ctk.CTkProgressBar(master, height=height, corner_radius=3,
                              progress_color=colour,
                              fg_color=mix_colour(DARK_BG, BORDER, 0.7))


# ────────────────────────── sinyal çubukları ────────────────────────

class SignalBars(tk.Canvas):
    """4 çubuklu sinyal göstergesi – rakam yerine görsel güç.

    Dolu çubuklar güce göre renklenir; boş çubuklar silinmek yerine soluk bir
    "ray" olarak kalır, böylece gösterge her zaman dört çubuk genişliğinde ve
    hizalı durur. Zayıf sinyalde çubuklar kırmızıya döner, ama boş rayın
    kontrastı da korunur ki gösterge "boş" görünmesin.
    """

    BAR_STEPS = (5, 8, 11, 14)   # her çubuğun yüksekliği
    BASELINE = 15                # çubukların oturduğu taban
    WIDTH = 8                    # çubuk adımı

    def __init__(self, master, width: int = 36, height: int = 16,
                 bg: str = CARD_BG, **kw):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._percent = 0.0
        self._animator = Animator(self)
        self._draw()

    def set(self, percent: float, colour: Optional[str] = None,
            animate: bool = False) -> None:
        target = max(0.0, min(1.0, percent))
        if not animate or abs(target - self._percent) < 0.02:
            self._percent = target
            self._draw(colour)
            return
        start = self._percent
        self._animator.tween(
            "bars", 260,
            lambda p: self._interpolate(start, target, p, colour),
            ease=ease_out_cubic)

    def _interpolate(self, start: float, end: float, p: float,
                     colour: Optional[str]) -> None:
        self._percent = start + (end - start) * p
        self._draw(colour)

    def set_bg(self, colour: str) -> None:
        try:
            self.configure(bg=colour)
        except Exception:
            pass
        self._draw()

    def _strength_colour(self) -> str:
        if self._percent >= 0.7:
            return ACCENT
        if self._percent >= 0.4:
            return WARN
        return DANGER

    def _draw(self, colour: Optional[str] = None) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        active = 0 if self._percent <= 0 else min(
            4, int(self._percent * 4) + 1)
        if colour is None:
            colour = self._strength_colour()

        x = 2
        for index, bar_height in enumerate(self.BAR_STEPS):
            top = self.BASELINE - bar_height
            filled = index < active
            self.create_rectangle(
                x, top, x + 6, self.BASELINE,
                fill=colour if filled else ELEV_BG,
                outline="",
            )
            x += self.WIDTH


# ────────────────────────── Log Paneli ──────────────────────────────

LEVEL_COLORS = {
    "info":    TEXT_SEC,
    "success": ACCENT,
    "warn":    WARN,
    "error":   DANGER,
    "raw":     MUTED,
}


class LogPanel(ctk.CTkFrame):
    """Renk kodlu, kaydırılabilir canlı log.

    Başlıktaki nokta log akarken nefes alır: yeni satır geldiğinde panelin
    canlı olduğu tek bakışta anlaşılır. Nokta boştayken sönük kalır.
    """

    MAX_LINES = 1200   # uzun oturumlarda Text widget'ı şişmesin

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)
        self._animator = Animator(self)
        self._idle_job: Optional[str] = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        self._live_dot = ctk.CTkLabel(head, text="●", font=("Inter", 10),
                                      text_color=MUTED, width=10)
        self._live_dot.pack(side="left", padx=(0, 7))
        ctk.CTkLabel(head, text=t("log.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text=t("log.lines", count=0),
                                   font=FONT_UI_S, text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0), pady=(2, 0))
        self._clear_btn = quiet_button(head, t("log.clear"), width=64,
                                       command=self.clear)
        self._clear_btn.pack(side="right")

        wrap = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=10)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._text = tk.Text(
            wrap,
            bg=DARK_BG, fg=TEXT_PRI,
            font=FONT_MONO_S,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            state="disabled",
            wrap="word",
            padx=10, pady=8,
            spacing1=1, spacing3=2,
        )
        self._text.pack(side="left", fill="both", expand=True)
        scrollbar = ctk.CTkScrollbar(wrap, command=self._text.yview,
                                     width=10, button_color=ELEV_BG,
                                     button_hover_color=mix_colour(
                                         ELEV_BG, ACCENT2, 0.5))
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._text.configure(yscrollcommand=scrollbar.set)

        for tag, colour in LEVEL_COLORS.items():
            self._text.tag_config(tag, foreground=colour)
        self._text.tag_config("marker_success", foreground=ACCENT,
                              font=(FONT_MONO_S[0], FONT_MONO_S[1], "bold"))

        self._lines = 0

    # ── public ──────────────────────────────────────────────────

    def append(self, msg: str, level: str = "info") -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", level)
        self._trim()
        self._text.configure(state="disabled")
        self._text.see("end")
        self._lines += 1
        if self._lines % 10 == 0 or self._lines < 10:
            self._count.configure(text=t("log.lines", count=self._lines))
        self._blink()

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._lines = 0
        self._count.configure(text=t("log.lines", count=0))
        self._animator.cancel("dot")
        self._live_dot.configure(text_color=MUTED)

    # ── private ─────────────────────────────────────────────────

    def _trim(self) -> None:
        """Sınırsız büyümeyi engelle: en eski satırları at."""
        try:
            total = int(self._text.index("end-1c").split(".")[0])
        except Exception:
            return
        if total > self.MAX_LINES + 200:
            self._text.delete("1.0", f"{total - self.MAX_LINES}.0")

    def _blink(self) -> None:
        """Yeni satır geldiğinde canlı nokta kısa süre parlar."""
        self._animator.cancel("dot")
        self._live_dot.configure(text_color=ACCENT)
        if self._idle_job is not None:
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
        self._idle_job = self.after(700, self._go_idle)

    def _go_idle(self) -> None:
        self._idle_job = None
        self._animator.colour("dot", self._live_dot, "text_color",
                              ACCENT, mix_colour(MUTED, ACCENT, 0.45), 900)

    def destroy(self) -> None:
        self._animator.cancel()
        if self._idle_job is not None:
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
            self._idle_job = None
        super().destroy()


# ────────────────────────── Adım çubuğu ─────────────────────────────

class GuideBar(ctk.CTkFrame):
    """Üstteki adım göstergesi: neredeyiz, sırada ne var.

    Tamamlanan adımlar camgöbeği dolgulu, aktif adım yeşil dolgulu kapsül,
    sonraki adımlar sönük ama okunur bir "pasif" tintte durur. Adım
    değişiminde kapsüller anında değişmez, renkleri kısa bir geçişle döner;
    göz böylece nereye gittiğini takip eder.
    """

    def __init__(self, master, steps: Sequence[str], **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._steps = list(steps)
        self._labels: List[ctk.CTkLabel] = []
        self._separators: List[ctk.CTkLabel] = []
        self._animators: List[Animator] = []

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack()

        for index, step in enumerate(self._steps):
            if index:
                sep = ctk.CTkLabel(inner, text="───", font=FONT_UI_S,
                                   text_color=BORDER)
                sep.pack(side="left", padx=3)
                self._separators.append(sep)

            label = ctk.CTkLabel(
                inner, text=f"  {index + 1}   {step}  ", font=FONT_UI_SB,
                text_color=OFF_TEXT, fg_color=OFF_BG, corner_radius=15,
                height=30,
            )
            label.pack(side="left", padx=3, pady=8)
            self._labels.append(label)
            self._animators.append(Animator(label))

    def set_active(self, index: int) -> None:
        for i, label in enumerate(self._labels):
            animator = self._animators[i]
            if i == index:
                # Aktif adım: dolu neon kapsül + üzerine okunur koyu metin.
                self._paint(animator, label, ACCENT, ACCENT_ON, FONT_UI_B)
            elif i < index:
                # Tamamlanan adım: camgöbeği dolgu, sakin ama bitmiş.
                self._paint(animator, label, ACCENT2_DIM, ACCENT2, FONT_UI_SB)
            else:
                # Sıradaki adımlar: sönük tint, okunur etiket.
                self._paint(animator, label, OFF_BG, OFF_TEXT, FONT_UI_SB)

        for i, sep in enumerate(self._separators):
            target = ACCENT2 if i < index else mix_colour(BORDER, OFF_TEXT, 0.25)
            Animator(sep).colour("sep", sep, "text_color",
                                 str(sep.cget("text_color")), target, 200)

    @staticmethod
    def _paint(animator: Animator, label: ctk.CTkLabel, bg: str,
               fg: str, font) -> None:
        current_bg = label.cget("fg_color")
        current_fg = label.cget("text_color")
        animator.colour("bg", label, "fg_color", str(current_bg), bg, 220,
                        ease=ease_in_out)
        animator.colour("fg", label, "text_color", str(current_fg), fg, 220,
                        ease=ease_in_out)
        try:
            label.configure(font=font)
        except Exception:
            pass


# ────────────────────────── Ağ tablosu ──────────────────────────────

class SelectionSummary(ctk.CTkFrame):
    """Seçili ağ kartı: "ne seçtim, nasıl bir ağ?" sorusunu tek yerde yanıtlar.

    Tek görünüm kararı sonrası ortaya çıkan boşluk buradan doluyor: kullanıcı
    artık adaptör/kanal gibi alanları doldurmuyor, ama seçtiği ağın sinyalini,
    kaç cihaz bağlı olduğunu, şifrelemesini ve hangi portal sayfasının
    yayınlanacağını görmek istiyor. Hepsi burada, üç sütunda durur:

    * sol   – Sinyal: çubuklar + dBm + kalite yüzdesi
    * orta  – Bağlı cihaz: sayı + "deauth atılabilir mi" yorumu
    * sağ   – Yayınlanacak sayfa: portal seçimi ve tek satır açıklaması

    Ağ seçilmeden önce kart bir yönlendirme gösterir; seçim gelince değerler
    yumuşak bir geçişle dolar.
    """

    def __init__(self, master, on_portal_change: Optional[Callable] = None,
                 **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self._portal_callback = on_portal_change
        self._animator = Animator(self)
        self._candidate = None
        self._portals: List = []

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(11, 0))

        self._dot = ctk.CTkLabel(head, text="●", font=("Inter", 10),
                                 text_color=OFF_TEXT, width=10)
        self._dot.pack(side="left", padx=(0, 7))
        self._title = ctk.CTkLabel(head, text=t("summary.none_title"),
                                   font=FONT_UI_B, text_color=TEXT_SEC,
                                   anchor="w", justify="left")
        self._title.pack(side="left")

        self._channel_pill = pill(head, "", ACCENT2, width=44, height=20)
        self._enc_pill = pill(head, "", OFF_TEXT, fg=OFF_BG, height=20)

        hairline(self).pack(fill="x", padx=14, pady=(9, 8))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 12))
        for column in range(3):
            grid.columnconfigure(column, weight=1, uniform="summary")

        self._signal_cell = self._build_signal_cell(grid, 0)
        self._clients_cell = self._build_clients_cell(grid, 1)
        self._portal_cell = self._build_portal_cell(grid, 2)

        self.set_candidate(None, animate=False)

    # ── inşa ────────────────────────────────────────────────────

    def _caption(self, parent, key: str) -> ctk.CTkLabel:
        label = ctk.CTkLabel(parent, text=t(key), font=FONT_UI_XS,
                             text_color=MUTED, anchor="w")
        label.pack(anchor="w", pady=(0, 4))
        return label

    def _build_signal_cell(self, parent, column: int) -> dict:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="nw", padx=(0, 10))
        self._caption(cell, "summary.signal")

        row = ctk.CTkFrame(cell, fg_color="transparent")
        row.pack(anchor="w")
        bars = SignalBars(row, width=40, bg=CARD_BG)
        bars.pack(side="left", padx=(0, 7))
        value = ctk.CTkLabel(row, text="—", font=FONT_UI_B,
                             text_color=TEXT_PRI, anchor="w")
        value.pack(side="left")
        detail = ctk.CTkLabel(cell, text="", font=FONT_UI_XS,
                              text_color=MUTED, anchor="w")
        detail.pack(anchor="w", pady=(3, 0))
        return {"bars": bars, "value": value, "detail": detail}

    def _build_clients_cell(self, parent, column: int) -> dict:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="nw", padx=(0, 10))
        self._caption(cell, "summary.clients")
        value = ctk.CTkLabel(cell, text="—", font=FONT_UI_B,
                             text_color=TEXT_PRI, anchor="w")
        value.pack(anchor="w")
        detail = ctk.CTkLabel(cell, text="", font=FONT_UI_XS,
                              text_color=MUTED, anchor="w", justify="left",
                              wraplength=150)
        detail.pack(anchor="w", pady=(3, 0))
        return {"value": value, "detail": detail}

    def _build_portal_cell(self, parent, column: int) -> dict:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="new")
        self._caption(cell, "summary.portal")
        # StringVar'ı kendimiz tutuyoruz: CTkComboBox cget("variable") ile
        # değişkeni geri vermiyor (None döner), seçim de bu yüzden okunamıyordu.
        self._portal_var = ctk.StringVar(
            value=t("config.attack.portal_loading"))
        combo = form_combo(cell, [t("config.attack.portal_loading")],
                           self._portal_var, width=168,
                           command=self._on_portal_change)
        combo.pack(anchor="w")
        detail = ctk.CTkLabel(cell, text="", font=FONT_UI_XS,
                              text_color=MUTED, anchor="w", justify="left",
                              wraplength=180)
        detail.pack(anchor="w", pady=(3, 0))
        return {"combo": combo, "detail": detail}

    # ── portal seçimi ──────────────────────────────────────────

    @property
    def portal_var(self) -> ctk.StringVar:
        return self._portal_var

    def portal_title(self) -> str:
        return self._portal_var.get()

    def set_portal(self, title: str) -> None:
        try:
            self._portal_var.set(title)
            self._on_portal_change()
        except Exception:
            pass

    def _on_portal_change(self, _value: str = "") -> None:
        portal = self.selected_portal()
        if portal is not None:
            self._portal_cell["detail"].configure(text=portal.description)
        elif not self._portals:
            self._portal_cell["detail"].configure(
                text=t("summary.portal_missing_hint"))
        if self._portal_callback:
            self._portal_callback()

    # ── genel API ───────────────────────────────────────────────

    def load_portals(self, portals: List) -> None:
        """Portal listesini doldurur; mevcut seçim varsa korunur.

        Liste boşsa "Yükleniyor…" gibi sonsuz bir izlenim bırakmamak için
        açıkça "bulunamadı" denir: kullanıcı beklemek yerine ne yapacağını
        (Detaylar → ortam kontrolü) bilir.
        """
        self._portals = list(portals)
        titles = [p.display_title for p in portals]
        combo = self._portal_cell["combo"]
        if titles:
            combo.configure(values=titles)
            if self.portal_title() not in titles:
                self._portal_var.set(titles[0])
        else:
            combo.configure(values=[t("summary.portal_missing")])
            self._portal_var.set(t("summary.portal_missing"))
        self._on_portal_change()

    @property
    def portals(self) -> List:
        return list(self._portals)

    def selected_portal(self):
        title = self.portal_title()
        return next((p for p in self._portals if p.display_title == title),
                    None)

    def set_candidate(self, candidate, animate: bool = True) -> None:
        self._candidate = candidate

        if candidate is None:
            self._title.configure(text=t("summary.none_title"),
                                  text_color=TEXT_SEC)
            self._dot.configure(text_color=OFF_TEXT)
            self._channel_pill.pack_forget()
            self._enc_pill.pack_forget()
            self._signal_cell["bars"].set(0.0)
            self._signal_cell["value"].configure(text="—",
                                                 text_color=TEXT_PRI)
            self._signal_cell["detail"].configure(text=t("summary.none_detail"))
            self._clients_cell["value"].configure(text="—",
                                                  text_color=TEXT_PRI)
            self._clients_cell["detail"].configure(text="")
            return

        has_clients = candidate.has_clients
        self._title.configure(
            text=candidate.clean_essid,
            text_color=TEXT_PRI if has_clients else TEXT_SEC)
        self._dot.configure(
            text_color=ACCENT if has_clients else OFF_TEXT)

        self._channel_pill.configure(
            text=f"CH {candidate.channel}",
            text_color=WARN if candidate.is_dfs else ACCENT2,
            fg_color=mix_colour(CARD_BG, WARN if candidate.is_dfs else ACCENT2,
                                0.14))
        self._channel_pill.pack(side="left", padx=(10, 0))
        if candidate.enc:
            self._enc_pill.configure(text=candidate.enc)
            self._enc_pill.pack(side="left", padx=(6, 0))
        else:
            self._enc_pill.pack_forget()

        percent = max(0, min(100, int(round(candidate.signal_percent * 100))))
        quality = (candidate.quality or "").strip() or f"{percent}%"
        self._signal_cell["bars"].set(candidate.signal_percent,
                                      animate=animate)
        self._signal_cell["value"].configure(
            text=f"{candidate.power} dBm",
            text_color=ACCENT if percent >= 70 else
            (WARN if percent >= 40 else DANGER))
        self._signal_cell["detail"].configure(
            text=t("summary.signal_detail", quality=quality,
                   bssid=candidate.bssid))

        if has_clients:
            self._clients_cell["value"].configure(
                text=t("summary.clients_value", count=candidate.clients),
                text_color=ACCENT)
            self._clients_cell["detail"].configure(
                text=t("summary.clients_good"))
        else:
            self._clients_cell["value"].configure(
                text=t("networks.no_clients"), text_color=MUTED)
            self._clients_cell["detail"].configure(
                text=t("summary.clients_none"))

        if animate and has_clients:
            current = str(self.cget("border_color"))
            target = mix_colour(BORDER, ACCENT, 0.7)
            self._animator.colour(
                "flash", self, "border_color", current, target, 200,
                done=lambda: self._animator.colour(
                    "flash2", self, "border_color", target, BORDER, 320))


class NetworkRow(ctk.CTkFrame):
    """Tek bir ağın ferah iki satırlı satırı.

    Üst satır: kanal rozeti · AĞ ADI (SSID – asla sıkışmaz) · sinyal + dBm
    Alt satır: BSSID (MAC) · şifreleme · üretici · bağlı cihaz rozeti

    Tek görünüme geçtikten sonra "kompakt" varyant kaldırıldı: kullanıcı artık
    sinyal ve cihaz sayısını görmek istiyor, bunlar da yalnızca tam satırda
    vardı. Cihazı olmayan ağ satırı yine geri planda durur (seçilebilir ama
    sönük), böylece hangi satırların işe yarayacağı taramadan belli olur.
    """

    def __init__(self, master, candidate, on_click: Callable, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self.candidate = candidate
        self._on_click = on_click
        self._selected = False
        self._hovered = False
        self._dimmed = False
        self._animator = Animator(self)

        self.columnconfigure(1, weight=1)
        self._build()

    # ── inşa ────────────────────────────────────────────────────

    def _build(self) -> None:
        candidate = self.candidate
        strong = candidate.has_clients

        badge_text = f"{candidate.channel}"
        if candidate.is_dfs:
            badge_text += "!"
        pill(self, badge_text, WARN if candidate.is_dfs else ACCENT2,
             width=40, height=26, font=FONT_UI_B,
             corner_radius=8).grid(row=0, column=0, padx=(12, 10),
                                   pady=(10, 2), sticky="w")

        ctk.CTkLabel(
            self, text=candidate.clean_essid, font=FONT_UI_B,
            text_color=TEXT_PRI if strong else TEXT_SEC,
            anchor="w", justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 2))

        sig_frame = ctk.CTkFrame(self, fg_color="transparent")
        sig_frame.grid(row=0, column=2, padx=(0, 12), pady=(10, 2), sticky="e")

        self.bars = SignalBars(sig_frame)
        self.bars.set(candidate.signal_percent)
        self.bars.pack(side="left", padx=(0, 5))

        ctk.CTkLabel(
            sig_frame, text=f"{candidate.power} dBm",
            font=FONT_MONO_S, text_color=MUTED, width=54, anchor="e",
        ).pack(side="left")

        # ── 2. SATIR ──
        parts = [candidate.bssid]
        if candidate.enc:
            parts.append(candidate.enc)
        if candidate.vendor:
            parts.append(candidate.vendor)
        ctk.CTkLabel(
            self, text="  ·  ".join(parts), font=FONT_MONO_S,
            text_color=MUTED, anchor="w", justify="left",
        ).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 10))

        extra = ctk.CTkFrame(self, fg_color="transparent")
        extra.grid(row=1, column=2, padx=(0, 12), pady=(0, 10), sticky="e")

        clients_text = (t("networks.clients", count=candidate.clients)
                        if candidate.clients else t("networks.no_clients"))
        if strong:
            solid_pill(extra, clients_text, ACCENT, ACCENT_ON,
                       width=66).pack(side="left", padx=(0, 5))
        else:
            pill(extra, clients_text, OFF_TEXT, fg=OFF_BG,
                 width=66).pack(side="left", padx=(0, 5))

        if candidate.has_handshake:
            pill(extra, t("networks.handshake_badge"), ACCENT).pack(
                side="left", padx=(0, 5))
        if candidate.is_dfs:
            pill(extra, t("networks.dfs_badge"), WARN).pack(side="left")

        self._bind_events(self)
        self._apply_tone()

    # ── etkileşim ───────────────────────────────────────────────

    def _bind_events(self, widget) -> None:
        widget.bind("<Button-1>", self._click)
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)
        for child in widget.winfo_children():
            self._bind_events(child)

    def _click(self, _event=None) -> None:
        self._on_click(self.candidate)

    def _enter(self, _event=None) -> None:
        self._hovered = True
        if self._selected or getattr(self, "_dimmed", False):
            return
        self._paint(CARD_HOVER, mix_colour(BORDER, ACCENT2, 0.5), animate=True)

    def _leave(self, _event=None) -> None:
        self._hovered = False
        if self._selected or getattr(self, "_dimmed", False):
            return
        self._apply_tone(animate=True)

    def _tone(self):
        """(dolgu, kenarlık) – cihazı olmayan satırlar bir tık sönük."""
        if self._selected:
            return CARD_SEL, ACCENT
        if self.candidate.has_clients:
            return CARD_BG, BORDER
        return mix_colour(CARD_BG, DARK_BG, 0.45), BORDER_SOFT

    def _apply_tone(self, animate: bool = False) -> None:
        bg, border = self._tone()
        self._paint(bg, border, animate)

    def _paint(self, bg: str, border: str, animate: bool = False) -> None:
        if animate:
            self._animator.colour("bg", self, "fg_color",
                                  str(self.cget("fg_color")), bg, 150)
            self._animator.colour("border", self, "border_color",
                                  str(self.cget("border_color")), border, 150)
        else:
            self._animator.cancel("bg")
            self._animator.cancel("border")
            self.configure(fg_color=bg, border_color=border)
        self.bars.set_bg(bg)

    def set_selected(self, selected: bool) -> None:
        changed = selected != self._selected
        self._selected = selected
        self._apply_tone(animate=changed)

    def set_dimmed(self, dimmed: bool) -> None:
        """Yeniden tarama sürerken eski sonuçları geri plana atar.

        Satırlar silinmez (kullanıcı henüz yeni veri görmedi), yalnızca
        soluklaşır. Böylece "eski liste hâlâ burada, yenisi geliyor" fikri
        bozulmadan iletilir.
        """
        if dimmed == getattr(self, "_dimmed", False):
            return
        self._dimmed = dimmed
        if dimmed:
            self._animator.colour("dim", self, "fg_color",
                                  str(self.cget("fg_color")),
                                  mix_colour(CARD_BG, DARK_BG, 0.5), 200)
        else:
            self._apply_tone(animate=True)


class NetworkTable(ctk.CTkFrame):
    """Taranan ağları kart satırları hâlinde gösteren liste.

    Tarama sürerken boş bir "henüz ağ yok" yazısı yerine iskelet satırlar
    gösterilir; sonuç gelince satırlar sırayla belirir.
    """

    STAGGER_MS = 34   # satırların art arda belirme aralığı

    def __init__(self, master, on_select: Callable = None, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)
        self._on_select = on_select
        self._candidates: List = []
        self._rows: Dict[str, NetworkRow] = {}
        self._selected = None
        self._busy = False
        self._reveal_jobs: List[str] = []

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=t("networks.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0), pady=(2, 0))

        self._spinner = Spinner(head, size=16, bg=PANEL_BG, colour=ACCENT2)
        self._search = ctk.CTkEntry(
            head, placeholder_text=t("networks.search_ph"), width=220,
            height=28, fg_color=DARK_BG, border_color=BORDER,
            border_width=1, text_color=TEXT_PRI,
            placeholder_text_color=MUTED, font=FONT_UI_S)
        self._search.pack(side="right")
        self._search.bind("<KeyRelease>", lambda _e: self._apply_filter())

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=14, pady=(2, 8))
        auto_wrap(ctk.CTkLabel(
            legend, text=t("networks.legend"),
            font=FONT_UI_S, text_color=MUTED, anchor="w", justify="left",
        )).pack(side="left", fill="x", expand=True)

        self._list = ctk.CTkScrollableFrame(
            self, fg_color=DARK_BG, corner_radius=10,
            scrollbar_button_color=ELEV_BG,
            scrollbar_button_hover_color=mix_colour(ELEV_BG, ACCENT2, 0.5))
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self._empty = ctk.CTkLabel(
            self._list, text=t("networks.empty"),
            font=FONT_UI, text_color=MUTED, justify="center",
        )
        self._empty.pack(pady=40)

        self._skeleton = SkeletonList(self._list, rows=4)

        self._hint = auto_wrap(ctk.CTkLabel(
            self, text=t("networks.hint_initial"), font=FONT_UI_S,
            text_color=MUTED, anchor="w", justify="left",
        ))
        self._hint.pack(fill="x", padx=14, pady=(0, 12))

    # ── public ──────────────────────────────────────────────────

    @property
    def candidates(self) -> List:
        return list(self._candidates)

    def set_busy(self, busy: bool, text: str = "") -> None:
        """Tarama sürerken meşguliyet görünümü.

        Davranış, listede satır olup olmamasına göre değişir:

        * **Satır varsa** (yeniden tarama): satırlar korunur ama soluklaşır,
          üstte spinner döner. Eski sonuçları silip iskelet göstermek, ekranı
          boşaltıp "veri kayboldu" hissi veriyordu.
        * **Satır yoksa** (ilk tarama): içeriğin yerini alan iskelet satırlar
          belirir; boş bir "henüz ağ yok" yazısından çok daha anlaşılır.

        Sıralama da bilinçli: iskelet ``before=self._empty`` ile
        yerleştirilmiyor, çünkü boş durum etiketi paketli olmayabilir ve Tk
        "isn't packed" hatası verir.
        """
        self._busy = busy
        if busy:
            self._empty.pack_forget()
            if not self._spinner.winfo_ismapped():
                self._spinner.pack(side="left", padx=(8, 0), pady=(2, 0))
            self._spinner.start()
            if self._rows:
                for row in self._rows.values():
                    row.set_dimmed(True)
                self._skeleton.stop()
                self._skeleton.pack_forget()
            else:
                if not self._skeleton.winfo_ismapped():
                    self._skeleton.pack(fill="x", padx=4, pady=3)
                self._skeleton.start()
            if text:
                self._count.configure(text=text)
        else:
            self._skeleton.stop()
            self._skeleton.pack_forget()
            self._spinner.stop()
            self._spinner.pack_forget()
            for row in self._rows.values():
                row.set_dimmed(False)

    def load(self, candidates, animate: bool = True) -> None:
        self.set_busy(False)
        self._candidates = list(candidates)
        self._selected = None
        self._search.delete(0, "end")
        self._render(animate=animate)

        with_clients = sum(1 for c in self._candidates if c.has_clients)
        handshakes = sum(1 for c in self._candidates if c.has_handshake)
        if self._candidates:
            self._hint.configure(
                text=t("networks.summary", total=len(self._candidates),
                       clients=with_clients, handshakes=handshakes),
                text_color=TEXT_SEC)

    def selected(self):
        return self._selected

    def select_first_with_clients(self):
        for candidate in self._candidates:
            if candidate.has_clients and not candidate.is_dfs:
                self._select(candidate)
                return candidate
        return None

    def clear(self) -> None:
        self.set_busy(False)
        self._candidates = []
        self._selected = None
        self._search.delete(0, "end")
        self._render(animate=False)
        self._hint.configure(text=t("networks.hint_initial"),
                             text_color=MUTED)

    def set_hint(self, text: str, level: str = "info") -> None:
        colour = {"info": TEXT_SEC, "warn": WARN,
                  "success": ACCENT}.get(level, TEXT_SEC)
        self._hint.configure(text=text, text_color=colour)

    # ── private ─────────────────────────────────────────────────

    def _render(self, animate: bool = True) -> None:
        self._cancel_reveals()
        for row in self._rows.values():
            row.destroy()
        self._rows.clear()
        self._empty.pack_forget()

        if not self._candidates:
            self._empty.pack(pady=40)
            self._count.configure(text="")
            return

        # En işe yarar ağlar üstte: önce cihazı olanlar, sonra sinyal.
        ordered = sorted(
            self._candidates,
            key=lambda c: (c.has_clients, not c.is_dfs, c.signal_percent),
            reverse=True,
        )
        self._ordered = ordered
        for index, candidate in enumerate(ordered):
            row = NetworkRow(self._list, candidate, self._select)
            row.pack(fill="x", padx=4, pady=3)
            self._rows[candidate.bssid] = row
            if animate:
                self._reveal(row, index)

        self._count.configure(text=t("networks.count",
                                     count=len(self._candidates)))
        self._apply_filter()

    def _reveal(self, row: "NetworkRow", index: int) -> None:
        """Satırı belirginleştirerek göster (art arda).

        Zamanlayıcı mutlaka ``self.after`` ile kurulur: daha önce
        ``row.after(...)`` kullanılıyordu ama iptal ``self.after_cancel`` ile
        yapılıyordu. Bu dengesizlik satırın Tk komut tablosunu bozuk
        bırakıyor, sonraki ``destroy()`` "can't delete Tcl command" hatası
        veriyordu (liste temizlenirken ortaya çıkıyordu).
        """
        target_bg = str(row.cget("fg_color"))
        fade_from = mix_colour(target_bg, DARK_BG, 0.55)

        def _start() -> None:
            try:
                if not row.winfo_exists():
                    return
            except Exception:
                return
            row._paint(fade_from, BORDER_SOFT, animate=False)
            row._paint(target_bg, BORDER_SOFT, animate=True)

        job = self.after(min(600, index * self.STAGGER_MS), _start)
        self._reveal_jobs.append(job)

    def _cancel_reveals(self) -> None:
        for job in self._reveal_jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._reveal_jobs = []

    def _apply_filter(self) -> None:
        needle = self._search.get().strip().lower()
        for row in self._rows.values():
            row.pack_forget()

        visible = 0
        for candidate in getattr(self, "_ordered", []):
            row = self._rows.get(candidate.bssid)
            if row is None:
                continue
            match = (not needle
                     or needle in candidate.clean_essid.lower()
                     or needle in candidate.bssid.lower())
            if match:
                row.pack(fill="x", padx=4, pady=3)
                visible += 1

        if self._candidates:
            self._count.configure(
                text=t("networks.filtered_count", visible=visible,
                       total=len(self._candidates)) if needle
                else t("networks.count", count=len(self._candidates)))

    def _select(self, candidate) -> None:
        for bssid, row in self._rows.items():
            row.set_selected(bssid == candidate.bssid)
        self._selected = candidate
        self.set_hint(candidate.recommendation,
                      "warn" if candidate.is_dfs else "info")
        if self._on_select:
            self._on_select(candidate)


# ────────────────────────── Durum rozeti ────────────────────────────

STATE_ICONS = {
    "IDLE":                ("●", MUTED),
    "INSTALLING":          ("📦", ACCENT2),
    "STARTING":            ("◐", WARN),
    "SCANNING":            ("◉", ACCENT2),
    "RUNNING":             ("⚡", ACCENT),
    "HANDSHAKE_CAPTURED":  ("🤝", ACCENT),
    "CREDENTIALS_FOUND":   ("🔑", ACCENT),
    "STOPPED":             ("■", OFF_TEXT),
    "ERROR":               ("✕", DANGER),
}


class StatusBadge(ctk.CTkFrame):
    """Üst çubuktaki kapsül durum göstergesi.

    Meşgul durumlarda küçük bir spinner döner ve rozet kendi renginde nefes
    alır; boşta yalnızca sakin bir nokta kalır. Bu ayrım, saldırının gerçekten
    sürüp sürmediğini pencereye tek bakışta okutur.
    """

    BUSY_STATES = ("SCANNING", "STARTING", "RUNNING", "INSTALLING")

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=16,
                         border_width=1, border_color=BORDER, **kw)
        self._animator = Animator(self)
        self._state = ""

        self._spinner = Spinner(self, size=14, bg=CARD_BG, colour=MUTED,
                                thickness=2)
        self._icon = ctk.CTkLabel(self, text="●", font=("Inter", 13),
                                  text_color=MUTED, width=16)
        self._icon.pack(side="left", padx=(13, 5), pady=6)
        self._label = ctk.CTkLabel(self, text=t("state.IDLE"), font=FONT_UI_B,
                                   text_color=MUTED)
        self._label.pack(side="left", padx=(0, 15), pady=6)

    # ── public ──────────────────────────────────────────────────

    def update_state(self, text: str, colour: Optional[str] = None) -> None:
        icon, default_colour = STATE_ICONS.get(text, ("●", MUTED))
        colour = colour or default_colour
        previous = self._animator
        previous.cancel()
        for widget, attribute in ((self._icon, "text_color"),
                                  (self._label, "text_color")):
            previous.colour(f"fade-{attribute}", widget, attribute,
                            str(widget.cget(attribute)), colour, 220)

        self._icon.configure(text=icon)
        self._label.configure(text=t(f"state.{text}"))
        self.configure(border_color=mix_colour(BORDER, colour, 0.55))
        self._state = text

        busy = text in self.BUSY_STATES
        if busy:
            self._spinner.set_colours(colour=colour, bg=CARD_BG)
            if not self._spinner.winfo_ismapped():
                self._icon.pack_forget()
                self._spinner.pack(side="left", padx=(13, 6), pady=6)
            self._spinner.start()
            self._animator.pulse(
                "breath", self._label, "text_color",
                (colour, mix_colour(colour, CARD_BG, 0.55), colour),
                period_ms=1500)
        else:
            self._spinner.stop()
            if self._spinner.winfo_ismapped():
                self._spinner.pack_forget()
                self._icon.pack(side="left", padx=(13, 5), pady=6,
                                before=self._label)

    def set_text(self, label: str, icon: str = "●",
                 colour: str = MUTED) -> None:
        self._animator.cancel()
        self._spinner.stop()
        self._icon.configure(text=icon, text_color=colour)
        self._label.configure(text=label, text_color=colour)

    def destroy(self) -> None:
        self._animator.cancel()
        self._spinner.stop()
        super().destroy()


# ────────────────────────── Bölüm kartı ─────────────────────────────

class SectionCard(ctk.CTkFrame):
    """İlgili kontrolleri bir arada tutan kart."""

    def __init__(self, master, title: str, subtitle: str = "",
                 accent: str = ACCENT2, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(13, 0))
        # Başlığın solunda ince renk çubuğu – kartlara kimlik verir.
        ctk.CTkFrame(head, fg_color=accent, width=3, height=15,
                     corner_radius=2).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(head, text=title, font=FONT_UI_B, text_color=accent,
                     anchor="w").pack(side="left")

        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=FONT_UI_S, text_color=MUTED,
                         anchor="w", justify="left", wraplength=260).pack(
                fill="x", padx=14, pady=(3, 0))

        hairline(self).pack(fill="x", padx=14, pady=(9, 0))

    def body(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=14, pady=(10, 12))
        return frame


# ────────────────────────── Şifre paneli ────────────────────────────

class CredentialRow(ctk.CTkFrame):
    """Tek bir yakalanan giriş: kullanıcı adı, şifre, kopyala.

    Kopyala düğmesi tıklandığında metni "✓ Kopyalandı"ya döner; kullanıcı
    işlemin gerçekleştiğini görür, ayrı bir bildirim beklemez.
    """

    def __init__(self, master, cred, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=mix_colour(BORDER,
                                                                 ACCENT, 0.3),
                         **kw)
        self._cred = cred
        self.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(self, text=cred.timestamp or "--:--:--",
                     font=FONT_MONO_S, text_color=MUTED, width=62,
                     anchor="w").grid(row=0, column=0, rowspan=2,
                                      padx=(12, 8), pady=8)

        pill(self, str(cred.client_ip or "-"), ACCENT2, width=118,
             height=24, font=FONT_MONO_S).grid(
            row=0, column=1, rowspan=2, padx=(0, 10))

        ctk.CTkLabel(self, text=cred.display_username, font=FONT_UI_B,
                     text_color=TEXT_PRI, anchor="w").grid(
            row=0, column=2, sticky="w", pady=(8, 0))
        ctk.CTkLabel(self, text=cred.password or "-", font=FONT_MONO,
                     text_color=ACCENT, anchor="w").grid(
            row=1, column=2, sticky="w", pady=(0, 8))

        self._copy_btn = quiet_button(self, t("creds.copy"), width=88,
                                      command=self._copy)
        self._copy_btn.grid(row=0, column=3, rowspan=2, padx=(6, 12))

    def _copy(self) -> None:
        text = f"{self._cred.display_username}\t{self._cred.password}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self._copy_btn.set_text(t("creds.copied"))
        self._copy_btn.flash(ACCENT)
        self.after(1400, lambda: self._copy_btn.set_text(t("creds.copy")))


class HandshakeRow(ctk.CTkFrame):
    """Handshake (.cap) dosyasını ve aksiyon butonlarını gösteren satır."""

    def __init__(self, master, hf, on_use_portal: Callable = None,
                 on_crack: Callable = None, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1,
                         border_color=mix_colour(BORDER, ACCENT2, 0.35), **kw)
        self.hf = hf
        self._on_use_portal = on_use_portal
        self._on_crack = on_crack

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="🤝", font=("Segoe UI", 16), width=36).grid(
            row=0, column=0, rowspan=2, padx=(10, 6), pady=(8, 2))

        # Ağ adı ve alt bilgi. Butonlar alt satırda olduğu için metin
        # sıkışmıyor: eskiden sağdaki iki buton sütun 1'i sıfır genişliğe
        # indiriyordu ve satırlar boş görünüyordu.
        ctk.CTkLabel(
            self, text=f"{hf.ssid or t('hs.unknown_ssid')}", font=FONT_UI_B,
            text_color=TEXT_PRI, anchor="w", justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))

        sub_text = (f"{hf.bssid or '-'} · {Path(hf.filepath).name} · "
                    f"{hf.size_bytes}B · {hf.created_at}")
        auto_wrap(ctk.CTkLabel(
            self, text=sub_text, font=FONT_MONO_S, text_color=MUTED,
            anchor="w", justify="left",
        )).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 4))

        if on_use_portal or on_crack:
            buttons = ctk.CTkFrame(self, fg_color="transparent")
            buttons.grid(row=2, column=0, columnspan=2, sticky="ew",
                         padx=10, pady=(0, 10))

            if on_use_portal:
                make_button(buttons, t("hs.use_portal"), "primary",
                            height=28, width=1,
                            font=FONT_UI_S,
                            command=lambda: on_use_portal(hf)).pack(
                    side="left", fill="x", expand=True, padx=(0, 6))

            if on_crack:
                make_button(buttons, t("hs.crack"), "secondary", height=28,
                            width=1, font=FONT_UI_S,
                            command=lambda: on_crack(hf)).pack(
                    side="left", fill="x", expand=True)


class CredentialsPanel(ctk.CTkFrame):
    """Yakalanan giriş bilgilerini ve yakalanan Handshake arşivini gösterir."""

    def __init__(self, master, on_use_portal: Callable = None,
                 on_crack: Callable = None, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)
        self._on_use_portal = on_use_portal
        self._on_crack = on_crack

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=t("creds.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0), pady=(2, 0))

        auto_wrap(ctk.CTkLabel(
            self, text=t("creds.desc"), font=FONT_UI_S, text_color=MUTED,
            anchor="w", justify="left",
        )).pack(fill="x", padx=14, pady=(0, 8))

        self._list = ctk.CTkScrollableFrame(
            self, fg_color=DARK_BG, corner_radius=10,
            scrollbar_button_color=ELEV_BG,
            scrollbar_button_hover_color=mix_colour(ELEV_BG, ACCENT2, 0.5))
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._empty = ctk.CTkLabel(
            self._list, text=t("creds.empty"),
            font=FONT_UI, text_color=MUTED, justify="center",
        )
        self._empty.pack(pady=40)

        self._count_value = 0
        self._handshake_count = 0
        self._handshake_header = None

    def add(self, cred) -> None:
        if self._count_value == 0 and self._handshake_count == 0:
            self._empty.pack_forget()
        self._count_value += 1
        row = CredentialRow(self._list, cred)
        row.pack(fill="x", padx=4, pady=3)
        self._update_counter()
        self._pop_in(row)

    def load_handshakes(self, handshakes) -> None:
        # Mevcut handshake satırlarını ve başlığı yenile. Başlık her
        # yenilemede yeniden eklenirse aynı yazı üst üste birikiyordu.
        for child in list(self._list.winfo_children()):
            if isinstance(child, HandshakeRow) or child is self._handshake_header:
                child.destroy()
        self._handshake_header = None

        self._handshake_count = len(handshakes)
        if self._count_value == 0 and self._handshake_count == 0:
            self._empty.pack(pady=40)
        else:
            self._empty.pack_forget()

        if handshakes:
            header = auto_wrap(ctk.CTkLabel(
                self._list, text=t("creds.handshake_header"),
                font=FONT_UI_B, text_color=ACCENT2, anchor="w",
                justify="left",
            ))
            header.pack(fill="x", padx=4, pady=(6, 2))
            self._handshake_header = header

            for hf in handshakes:
                row = HandshakeRow(self._list, hf, self._on_use_portal,
                                   self._on_crack)
                row.pack(fill="x", padx=4, pady=3)

        self._update_counter()

    def _update_counter(self) -> None:
        parts = []
        if self._count_value:
            parts.append(t("creds.count_passwords", count=self._count_value))
        if self._handshake_count:
            parts.append(t("creds.count_handshakes",
                           count=self._handshake_count))
        self._count.configure(text=" · ".join(parts) if parts else "")

    def _pop_in(self, row) -> None:
        """Yeni giriş satırı belirginleşerek gelsin: göz oraya gider."""
        target_border = str(row.cget("border_color"))
        Animator(row).colour("in", row, "border_color", ACCENT,
                             target_border, 700, ease=ease_in_out)
        row.configure(border_color=ACCENT)
        Animator(row).colour("in2", row, "border_color", ACCENT,
                             target_border, 900, ease=ease_in_out)

    def clear(self) -> None:
        for child in self._list.winfo_children():
            if child is not self._empty:
                child.destroy()
        self._handshake_header = None
        self._count_value = 0
        self._handshake_count = 0
        self._count.configure(text="")
        self._empty.pack(pady=40)


# ────────────────────────── Kontrol listesi ─────────────────────────

class Checklist(ctk.CTkFrame):
    """Ortam kontrollerini ✓/✗ satırları olarak gösterir.

    Kontrol sürerken spinner döner; sonuç gelince satırlar birer birer
    belirir. Böylece "kontrol ediliyor…" ile "kontrol bitti" arasındaki
    farkı sadece metinden değil hareketten de okunur.
    """

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._rows: List[ctk.CTkFrame] = []
        self._busy: Optional[ctk.CTkFrame] = None
        self._spinner: Optional[Spinner] = None

    def show_loading(self, text: str) -> None:
        self._clear()
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", pady=2)
        spinner = Spinner(frame, size=15, bg=PANEL_BG, colour=ACCENT2,
                          thickness=2)
        spinner.pack(side="left", padx=(0, 8))
        spinner.start()
        ctk.CTkLabel(frame, text=text, font=FONT_UI_S,
                     text_color=ACCENT2, anchor="w").pack(side="left")
        self._busy = frame
        self._spinner = spinner
        self._rows.append(frame)

    def show(self, checks) -> None:
        self._clear()

        missing = [c for c in checks if not c.ok and c.required]
        optional_missing = [c for c in checks if not c.ok and not c.required]

        for index, check in enumerate(checks):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=check.icon, font=FONT_UI_B,
                         text_color=check.color, width=14).pack(side="left")
            ctk.CTkLabel(row, text=check.name, font=FONT_UI_S,
                         text_color=TEXT_PRI if check.ok else WARN,
                         width=140, anchor="w").pack(side="left", padx=(2, 6))
            ctk.CTkLabel(row, text=check.detail, font=FONT_UI_S,
                         text_color=MUTED, anchor="w", justify="left",
                         wraplength=180).pack(side="left", fill="x",
                                              expand=True)
            self._rows.append(row)
            row.after(min(500, index * 40),
                      lambda r=row: self._fade_in(r))

        if missing:
            text = t("checklist.missing", count=len(missing))
            colour = WARN
        elif optional_missing:
            text = t("checklist.optional", count=len(optional_missing))
            colour = ACCENT2
        else:
            text = t("checklist.ready")
            colour = ACCENT

        summary = ctk.CTkLabel(self, text=text, font=FONT_UI_S,
                               text_color=colour, anchor="w", justify="left",
                               wraplength=240)
        summary.pack(fill="x", pady=(6, 0))
        self._rows.append(summary)
        self.scroll_to_end()

    def scroll_to_end(self) -> None:
        """Kapsayıcı kaydırılabilirse yeni satırları görünür alana getir."""
        parent = self.master
        try:
            if isinstance(parent, ctk.CTkScrollableFrame):
                parent._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _fade_in(self, row) -> None:
        if not row.winfo_exists():
            return
        row.configure(fg_color=mix_colour(PANEL_BG, TEXT_PRI, 0.05))
        Animator(row).colour("fade", row, "fg_color",
                             str(row.cget("fg_color")), "transparent", 420,
                             ease=ease_in_out)

    def _clear(self) -> None:
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner = None
        self._busy = None
        for row in self._rows:
            try:
                row.destroy()
            except Exception:
                pass
        self._rows = []


# ────────────────────────── Bildirim katmanı ────────────────────────
class NotificationHost:
    """Bildirim şeridinin sahibi: arayüz yeniden kurulsa da aynı kalır.

    ``NotificationBar`` yerleşimi iterek açılan bir satırdır; bu sınıf onu
    yalnızca pencere kurulurken oluşturur ve ``_notify`` çağrılarını ona
    iletir. Böylece app.py bildirimleri tek satırla gönderebilir, yüzen bir
    katman da hiçbir düğmeyi örtmez.
    """

    def __init__(self, master, after_widget=None):
        self.bar = NotificationBar(master)
        self.bar._after_widget = after_widget
        self._master = master

    def show(self, text: str, kind: str = "info", timeout: int = 4500) -> None:
        self.bar.show(text, kind, timeout)

    def clear(self) -> None:
        self.bar.hide()

    @property
    def visible(self) -> bool:
        return self.bar.visible
