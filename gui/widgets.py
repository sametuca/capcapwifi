"""
CapCapWifi GUI – yeniden kullanılabilir arayüz bileşenleri.

Buradaki sınıfların hiçbiri ağ veya süreç işlemez; yalnızca görüntüler ve
kullanıcı etkileşimini callback olarak dışarı verir. Görünen tüm metinler
i18n üzerinden gelir, bu yüzden pencere yeniden kurulduğunda dil değişir.

Tasarım dili: koyu zemin, yumuşak köşeli kartlar, tek vurgu rengi (neon yeşil)
ve ikincil olarak camgöbeği. Sinyal gücü sayı yerine çubuklarla gösterilir.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import customtkinter as ctk

from i18n import t


# ────────────────────────── renk paleti ─────────────────────────────
# Katmanlı koyu zemin — en koyudan açığa: DARK_BG < PANEL_BG < CARD_BG <
# CARD_HOVER < ELEV_BG. Böylece derinlik gölge olmadan, yalnızca ton farkıyla
# okunur. Tek güçlü vurgu neon yeşil (ACCENT), ikincil camgöbeği (ACCENT2);
# her vurgunun yanında yumuşak dolgu (…_DIM) ve koyu hover (…_DK) tonu var, bu
# sayede rozet ve butonlarda dağınık hex kodu yerine tutarlı tema kullanılır.

DARK_BG     = "#090B0F"   # uygulama zemini – en derin kat
PANEL_BG    = "#0F1218"   # panel / sütun zemini
CARD_BG     = "#161A22"   # kart yüzeyi
CARD_HOVER  = "#1E232D"   # kart hover
CARD_SEL    = "#0E2619"   # seçili kart (yeşil tint)
ELEV_BG     = "#1F2630"   # yükseltilmiş küçük yüzeyler (rozet içi vb.)

ACCENT      = "#00E676"   # neon yeşil – birincil vurgu
ACCENT_DK   = "#00C46A"   # yeşil hover / basılı
ACCENT_DIM  = "#123324"   # yeşil yumuşak dolgu
ACCENT2     = "#38BDF8"   # gökyüzü camgöbeği – ikincil vurgu
ACCENT2_DIM = "#0C2A3C"   # camgöbeği yumuşak dolgu
WARN        = "#FBBF24"   # amber
WARN_DIM    = "#2E2611"   # amber yumuşak dolgu
DANGER      = "#FB7185"   # yumuşak kırmızı
DANGER_DIM  = "#2B1419"   # kırmızı yumuşak dolgu
MUTED       = "#6B7483"
TEXT_PRI    = "#F2F5F9"   # birincil metin
TEXT_SEC    = "#9AA4B2"   # ikincil metin
BORDER      = "#232935"   # ince kenarlık

FONT_MONO   = ("JetBrains Mono", 12)
FONT_MONO_S = ("JetBrains Mono", 11)
FONT_UI     = ("Inter", 12)
FONT_UI_S   = ("Inter", 11)
FONT_UI_B   = ("Inter", 12, "bold")
FONT_UI_SB  = ("Inter", 11, "bold")
FONT_TITLE  = ("Inter", 15, "bold")


def auto_wrap(label: "ctk.CTkLabel", minimum: int = 220,
              slack: int = 24) -> "ctk.CTkLabel":
    """Etiketi bulunduğu kapsayıcının genişliğine göre sar.

    Tkinter içinde döngüye (feedback loop) yol açmaması için:
      1) Event doğrudan etikete değil, kapsayıcısına (master) bağlanır;
         böylece wraplength değişimi yeni bir <Configure> tetiklemez.
      2) Yalnızca en az 12 piksellik genişlik değişimlerinde configure
         çağrılır, gereksiz yeniden hesaplamalar engellenir.
    """
    last_wrap = [0]
    parent = getattr(label, "master", None)

    def _resize(event) -> None:
        if parent is not None and event.widget != parent:
            return
        target = max(minimum, int(event.width) - slack)
        if abs(target - last_wrap[0]) >= 12:
            last_wrap[0] = target
            try:
                label.configure(wraplength=target)
            except Exception:
                pass

    if parent is not None:
        parent.bind("<Configure>", _resize, add="+")
    return label


# ────────────────────────── sinyal çubukları ────────────────────────

class SignalBars(tk.Canvas):
    """4 çubuklu sinyal göstergesi – rakam yerine görsel güç.

    Dolu çubuklar güce göre renklenir; boş çubuklar silinmek yerine soluk bir
    "ray" olarak kalır, böylece gösterge her zaman dört çubuk genişliğinde ve
    hizalı durur.
    """

    BAR_STEPS = (5, 8, 11, 14)   # her çubuğun yüksekliği
    BASELINE  = 15               # çubukların oturduğu taban

    def __init__(self, master, width: int = 36, height: int = 16,
                 bg: str = CARD_BG, **kw):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._percent = 0.0
        self._draw()

    def set(self, percent: float, colour: Optional[str] = None) -> None:
        self._percent = max(0.0, min(1.0, percent))
        self._draw(colour)

    def set_bg(self, colour: str) -> None:
        self.configure(bg=colour)
        self._draw()

    def _draw(self, colour: Optional[str] = None) -> None:
        self.delete("all")
        active = 0 if self._percent <= 0 else min(4, int(self._percent * 4) + 1)
        if colour is None:
            if self._percent >= 0.7:
                colour = ACCENT
            elif self._percent >= 0.4:
                colour = WARN
            else:
                colour = DANGER

        x = 2
        for index, bar_height in enumerate(self.BAR_STEPS):
            top = self.BASELINE - bar_height
            self.create_rectangle(
                x, top, x + 6, self.BASELINE,
                fill=colour if index < active else ELEV_BG,
                outline="",
            )
            x += 8


# ────────────────────────── Log Paneli ──────────────────────────────

LEVEL_COLORS = {
    "info":    TEXT_SEC,
    "success": ACCENT,
    "warn":    WARN,
    "error":   DANGER,
    "raw":     MUTED,
}


class LogPanel(ctk.CTkFrame):
    """Renk kodlu, kaydırılabilir canlı log."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(head, text="●", font=("Inter", 10),
                     text_color=ACCENT).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(head, text=t("log.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text=t("log.lines", count=0),
                                   font=FONT_UI_S, text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))
        ctk.CTkButton(head, text=t("log.clear"), width=64, height=26,
                      command=self.clear, fg_color="transparent",
                      hover_color=ELEV_BG, border_width=1,
                      border_color=BORDER, text_color=TEXT_SEC,
                      corner_radius=8, font=FONT_UI_SB).pack(side="right")

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
                                     width=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._text.configure(yscrollcommand=scrollbar.set)

        for tag, colour in LEVEL_COLORS.items():
            self._text.tag_config(tag, foreground=colour)

        self._lines = 0

    def append(self, msg: str, level: str = "info") -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", level)
        self._text.configure(state="disabled")
        self._text.see("end")
        self._lines += 1
        if self._lines % 10 == 0 or self._lines < 10:
            self._count.configure(text=t("log.lines", count=self._lines))

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._lines = 0
        self._count.configure(text=t("log.lines", count=0))


# ────────────────────────── Adım çubuğu ─────────────────────────────

class GuideBar(ctk.CTkFrame):
    """Üstteki adım göstergesi: neredeyiz, sırada ne var.

    Tamamlanan adımlar camgöbeği, aktif adım yeşil dolgulu kapsül,
    sonraki adımlar gri kalır.
    """

    def __init__(self, master, steps: Sequence[str], **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._steps = list(steps)
        self._labels: List[ctk.CTkLabel] = []
        self._separators: List[ctk.CTkLabel] = []

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
                text_color=TEXT_SEC, fg_color=CARD_BG, corner_radius=15,
                height=30,
            )
            label.pack(side="left", padx=3, pady=8)
            self._labels.append(label)

    def set_active(self, index: int) -> None:
        for i, label in enumerate(self._labels):
            if i == index:
                # Aktif adım: dolu neon kapsül, belirgin.
                label.configure(text_color=DARK_BG, fg_color=ACCENT,
                                font=FONT_UI_B)
            elif i < index:
                # Tamamlanan adım: soluk camgöbeği dolgu.
                label.configure(text_color=ACCENT2, fg_color=ACCENT2_DIM,
                                font=FONT_UI_SB)
            else:
                # Sıradaki adımlar: sakin, geri planda.
                label.configure(text_color=MUTED, fg_color=CARD_BG,
                                font=FONT_UI_SB)

        for i, sep in enumerate(self._separators):
            sep.configure(text_color=ACCENT2 if i < index else BORDER)


# ────────────────────────── Ağ tablosu ──────────────────────────────

class NetworkRow(ctk.CTkFrame):
    """Tek bir ağın modern satırı: ferah 2 satırlı düzen.

    Üst satır: Kanal rozeti · AĞ ADI (SSID - asla sıkışmaz) · Sinyal & Rozetler
    Alt satır: BSSID (MAC) · Şifreleme · Üretici · Bağlı cihaz & Handshake rozetleri
    """

    def __init__(self, master, candidate, on_click: Callable, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self.candidate = candidate
        self._on_click = on_click
        self._selected = False

        self.columnconfigure(1, weight=1)

        # ── 1. SATIR: Kanal Rozeti, Ağ Adı (SSID), Sinyal ──
        badge_text = f"{candidate.channel}"
        if candidate.is_dfs:
            badge_text += "!"
        badge = ctk.CTkLabel(
            self, text=badge_text, width=40, height=26, font=FONT_UI_B,
            text_color=ACCENT2 if not candidate.is_dfs else WARN,
            fg_color=ACCENT2_DIM if not candidate.is_dfs else WARN_DIM,
            corner_radius=8,
        )
        badge.grid(row=0, column=0, padx=(12, 10), pady=(10, 2), sticky="w")

        # SSID: Kalın, belirgin ve tam genişlikte ana başlık
        name = ctk.CTkLabel(
            self, text=candidate.clean_essid, font=FONT_UI_B,
            text_color=TEXT_PRI, anchor="w", justify="left"
        )
        name.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 2))

        # Sağ taraf: Sinyal çubukları + dBm
        sig_frame = ctk.CTkFrame(self, fg_color="transparent")
        sig_frame.grid(row=0, column=2, padx=(0, 12), pady=(10, 2), sticky="e")

        self.bars = SignalBars(sig_frame)
        self.bars.set(candidate.signal_percent)
        self.bars.pack(side="left", padx=(0, 4))

        signal = ctk.CTkLabel(
            sig_frame, text=f"{candidate.power} dBm",
            font=FONT_MONO_S, text_color=TEXT_SEC, width=54, anchor="e"
        )
        signal.pack(side="left")

        # ── 2. SATIR: BSSID (MAC), Şifreleme, Üretici ve Durum Rozetleri ──
        info_parts = [candidate.bssid]
        if candidate.enc:
            info_parts.append(candidate.enc)
        if candidate.vendor:
            info_parts.append(candidate.vendor)
        sub_text = "  ·  ".join(info_parts)

        sub = ctk.CTkLabel(
            self, text=sub_text, font=FONT_MONO_S,
            text_color=MUTED, anchor="w", justify="left"
        )
        sub.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 10))

        # Alt sağ: Bağlı cihaz rozeti, Handshake rozeti ve DFS etiketi
        extra_frame = ctk.CTkFrame(self, fg_color="transparent")
        extra_frame.grid(row=1, column=2, padx=(0, 12), pady=(0, 10), sticky="e")

        if candidate.clients:
            clients_text = t("networks.clients", count=candidate.clients)
        else:
            clients_text = t("networks.no_clients")
        clients_badge = ctk.CTkLabel(
            extra_frame, text=clients_text, font=FONT_UI_SB, width=66, height=22,
            corner_radius=7,
            text_color=DARK_BG if candidate.has_clients else MUTED,
            fg_color=ACCENT if candidate.has_clients else ELEV_BG,
        )
        clients_badge.pack(side="left", padx=(0, 5))

        if candidate.has_handshake:
            ctk.CTkLabel(
                extra_frame, text=t("networks.handshake_badge"), font=FONT_UI_SB,
                text_color=ACCENT, fg_color=ACCENT_DIM, corner_radius=7,
                height=22, padx=8
            ).pack(side="left", padx=(0, 5))

        if candidate.is_dfs:
            ctk.CTkLabel(
                extra_frame, text=t("networks.dfs_badge"), font=FONT_UI_SB,
                text_color=WARN, fg_color=WARN_DIM, corner_radius=7,
                height=22, padx=8
            ).pack(side="left")

        self._bind_events(self)

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
        if not self._selected:
            self._paint(CARD_HOVER, BORDER)

    def _leave(self, _event=None) -> None:
        if not self._selected:
            self._paint(CARD_BG, BORDER)

    def _paint(self, bg: str, border: str) -> None:
        self.configure(fg_color=bg, border_color=border)
        self.bars.set_bg(bg)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self._paint(CARD_SEL, ACCENT)
        else:
            self._paint(CARD_BG, BORDER)


class NetworkTable(ctk.CTkFrame):
    """Taranan ağları kart satırları hâlinde gösteren liste."""

    def __init__(self, master, on_select: Callable = None, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)
        self._on_select = on_select
        self._candidates: List = []
        self._rows: Dict[str, NetworkRow] = {}
        self._selected = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=t("networks.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))

        self._search = ctk.CTkEntry(
            head, placeholder_text=t("networks.search_ph"), width=220,
            height=28, fg_color=DARK_BG, border_color=BORDER,
            text_color=TEXT_PRI, font=FONT_UI_S)
        self._search.pack(side="right")
        self._search.bind("<KeyRelease>", lambda _e: self._apply_filter())

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=14, pady=(2, 8))
        auto_wrap(ctk.CTkLabel(
            legend,
            text=t("networks.legend"),
            font=FONT_UI_S, text_color=MUTED, anchor="w", justify="left",
        )).pack(side="left", fill="x", expand=True)

        self._list = ctk.CTkScrollableFrame(self, fg_color=DARK_BG,
                                            corner_radius=10)
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self._empty = ctk.CTkLabel(
            self._list,
            text=t("networks.empty"),
            font=FONT_UI, text_color=MUTED, justify="center",
        )
        self._empty.pack(pady=40)

        self._hint = auto_wrap(ctk.CTkLabel(
            self, text=t("networks.hint_initial"), font=FONT_UI_S,
            text_color=MUTED, anchor="w", justify="left",
        ))
        self._hint.pack(fill="x", padx=14, pady=(0, 12))

    # ── public ──────────────────────────────────────────────────

    @property
    def candidates(self) -> List:
        return list(self._candidates)

    def load(self, candidates) -> None:
        self._candidates = list(candidates)
        self._selected = None
        self._search.delete(0, "end")
        self._render()

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
        self._candidates = []
        self._selected = None
        self._search.delete(0, "end")
        self._render()
        self._hint.configure(text=t("networks.hint_initial"),
                             text_color=MUTED)

    def set_hint(self, text: str, level: str = "info") -> None:
        colour = {"info": TEXT_SEC, "warn": WARN,
                  "success": ACCENT}.get(level, TEXT_SEC)
        self._hint.configure(text=text, text_color=colour)

    # ── private ─────────────────────────────────────────────────

    def _render(self) -> None:
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
        for candidate in ordered:
            row = NetworkRow(self._list, candidate, self._select)
            row.pack(fill="x", padx=4, pady=3)
            self._rows[candidate.bssid] = row

        self._count.configure(text=t("networks.count",
                                     count=len(self._candidates)))
        self._apply_filter()

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
    "STOPPED":             ("■", MUTED),
    "ERROR":               ("✕", DANGER),
}


class StatusBadge(ctk.CTkFrame):
    """Üst çubuktaki kapsül durum göstergesi."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=16, **kw)
        self._icon = ctk.CTkLabel(self, text="●", font=("Inter", 14),
                                  text_color=MUTED, width=18)
        self._icon.pack(side="left", padx=(14, 4), pady=6)
        self._label = ctk.CTkLabel(self, text=t("state.IDLE"), font=FONT_UI_B,
                                   text_color=MUTED)
        self._label.pack(side="left", padx=(0, 14), pady=6)

    def update_state(self, text: str, colour: Optional[str] = None) -> None:
        icon, default_colour = STATE_ICONS.get(text, ("●", MUTED))
        self._icon.configure(text=icon, text_color=colour or default_colour)
        self._label.configure(
            text=t(f"state.{text}"),
            text_color=colour or default_colour,
        )

    def set_text(self, label: str, icon: str = "●", colour: str = MUTED) -> None:
        self._icon.configure(text=icon, text_color=colour)
        self._label.configure(text=label, text_color=colour)


# ────────────────────────── Bölüm kartı ─────────────────────────────

class SectionCard(ctk.CTkFrame):
    """İlgili kontrolleri bir arada tutan kart."""

    def __init__(self, master, title: str, subtitle: str = "",
                 accent: str = ACCENT2, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(13, 0))
        # Başlığın solunda ince renk çubuğu — kartlara kimlik verir.
        ctk.CTkFrame(head, fg_color=accent, width=3, height=15,
                     corner_radius=2).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(head, text=title, font=FONT_UI_B, text_color=accent,
                     anchor="w").pack(side="left")

        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=FONT_UI_S, text_color=MUTED,
                         anchor="w", justify="left", wraplength=260).pack(
                fill="x", padx=14, pady=(3, 0))

        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(
            fill="x", padx=14, pady=(9, 0))

    def body(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=14, pady=(10, 12))
        return frame


# ────────────────────────── Şifre paneli ────────────────────────────

class CredentialRow(ctk.CTkFrame):
    """Tek bir yakalanan giriş: kullanıcı adı, şifre, kopyala."""

    def __init__(self, master, cred, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self._cred = cred
        self.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(self, text=cred.timestamp or "--:--:--",
                     font=FONT_MONO_S, text_color=MUTED, width=60,
                     anchor="w").grid(row=0, column=0, rowspan=2,
                                      padx=(12, 8), pady=8)

        ctk.CTkLabel(
            self, text=str(cred.client_ip or "-"), font=FONT_MONO_S,
            text_color=ACCENT2, fg_color=ACCENT2_DIM, corner_radius=7,
            width=118, height=24,
        ).grid(row=0, column=1, rowspan=2, padx=(0, 10))

        ctk.CTkLabel(self, text=cred.display_username, font=FONT_UI_B,
                     text_color=TEXT_PRI, anchor="w").grid(
            row=0, column=2, sticky="w", pady=(8, 0))
        ctk.CTkLabel(self, text=cred.password or "-", font=FONT_MONO,
                     text_color=ACCENT, anchor="w").grid(
            row=1, column=2, sticky="w", pady=(0, 8))

        ctk.CTkButton(self, text=t("creds.copy"), width=72, height=26,
                      font=FONT_UI_S, fg_color="transparent",
                      hover_color=CARD_HOVER, border_width=1,
                      border_color=BORDER, text_color=TEXT_SEC,
                      command=self._copy).grid(row=0, column=3, rowspan=2,
                                               padx=(6, 12))

    def _copy(self) -> None:
        text = f"{self._cred.display_username}\t{self._cred.password}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()


class HandshakeRow(ctk.CTkFrame):
    """Handshake (.cap) dosyasını ve aksiyon butonlarını gösteren satır."""

    def __init__(self, master, hf, on_use_portal: Callable = None, on_crack: Callable = None, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        self.hf = hf
        self._on_use_portal = on_use_portal
        self._on_crack = on_crack

        self.grid_columnconfigure(1, weight=1)

        # İkon / Rozet
        ctk.CTkLabel(
            self, text="🤝", font=("Segoe UI", 16), width=36
        ).grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=6)

        # Ağ Adı ve BSSID
        title_text = f"{hf.ssid or t('hs.unknown_ssid')}"
        ctk.CTkLabel(
            self, text=title_text, font=FONT_UI_B, text_color=TEXT_PRI, anchor="w"
        ).grid(row=0, column=1, sticky="w", pady=(6, 0))

        sub_text = f"{hf.bssid or '-'}  ·  {Path(hf.filepath).name}  ·  {hf.size_bytes}B  ·  {hf.created_at}"
        ctk.CTkLabel(
            self, text=sub_text, font=FONT_MONO_S, text_color=MUTED, anchor="w"
        ).grid(row=1, column=1, sticky="w", pady=(0, 6))

        # Aksiyon Butonları
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=0, column=2, rowspan=2, padx=(6, 10), pady=6, sticky="e")

        if on_use_portal:
            ctk.CTkButton(
                btn_f, text=t("hs.use_portal"), width=120, height=26,
                font=FONT_UI_S, fg_color=ACCENT, text_color=DARK_BG,
                hover_color=ACCENT_DK, command=lambda: on_use_portal(hf)
            ).pack(side="left", padx=(0, 6))

        if on_crack:
            ctk.CTkButton(
                btn_f, text=t("hs.crack"), width=110, height=26,
                font=FONT_UI_S, fg_color=CARD_BG, text_color=TEXT_PRI,
                hover_color=CARD_HOVER, border_width=1, border_color=BORDER,
                command=lambda: on_crack(hf)
            ).pack(side="left")


class NextStepGuideCard(ctk.CTkFrame):
    """Handshake yakalandığında kullanıcıya sırada ne olduğunu anlatan
    ve tek tıkla Captive Portal veya Aircrack başlatan rehberlik kartı."""

    def __init__(self, master, on_start_portal: Callable = None, on_crack_wordlist: Callable = None, on_dismiss: Callable = None, **kw):
        super().__init__(master, fg_color=CARD_SEL, corner_radius=12,
                         border_width=2, border_color=ACCENT, **kw)
        self._on_start_portal = on_start_portal
        self._on_crack_wordlist = on_crack_wordlist
        self._on_dismiss = on_dismiss
        self._hf = None

        # Üst Başlık & Kapatma Butonu
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))

        title_lbl = ctk.CTkLabel(
            head, text=f"🎉 {t('guide.title')}",
            font=FONT_TITLE, text_color=ACCENT, anchor="w"
        )
        title_lbl.pack(side="left")

        if on_dismiss:
            ctk.CTkButton(
                head, text="✕", width=26, height=22,
                command=on_dismiss, fg_color="transparent",
                hover_color=ACCENT_DIM, text_color=TEXT_SEC, font=FONT_UI_B
            ).pack(side="right")

        # Hedef Ağ & Dosya Bilgisi Banner
        self._info_lbl = ctk.CTkLabel(
            self, text=t("guide.info", ssid="-", bssid="-", file="-"),
            font=FONT_UI_B, text_color=TEXT_PRI, anchor="w", justify="left"
        )
        self._info_lbl.pack(fill="x", padx=14, pady=(0, 6))

        # Kaydedilen dosyanın tam yolu — kullanıcı dosyayı nerede bulacağını
        # aramadan görsün.
        self._saved_lbl = auto_wrap(ctk.CTkLabel(
            self, text="", font=FONT_UI_S, text_color=ACCENT2,
            anchor="w", justify="left",
        ))
        self._saved_lbl.pack(fill="x", padx=14, pady=(0, 8))

        # Açıklama
        guide_box = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=10, border_width=1, border_color=BORDER)
        guide_box.pack(fill="x", padx=14, pady=(0, 8))

        auto_wrap(ctk.CTkLabel(
            guide_box, text=t("guide.body"), font=FONT_UI_S, text_color=TEXT_SEC,
            justify="left", anchor="w", padx=12, pady=8
        )).pack(fill="x")

        # Aksiyon Butonları
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=(0, 10))

        self._btn_portal = ctk.CTkButton(
            btn_bar, text=t("guide.btn_portal"),
            command=self._portal_clicked, fg_color=ACCENT, text_color=DARK_BG,
            hover_color=ACCENT_DK, font=FONT_UI_B, height=36
        )
        self._btn_portal.pack(side="left", padx=(0, 8), expand=True, fill="x")

        self._btn_crack = ctk.CTkButton(
            btn_bar, text=t("guide.btn_crack"),
            command=self._crack_clicked, fg_color=CARD_BG, text_color=TEXT_PRI,
            hover_color=CARD_HOVER, border_width=1, border_color=BORDER,
            font=FONT_UI, height=36
        )
        self._btn_crack.pack(side="left")

    def set_handshake(self, hf) -> None:
        self._hf = hf
        self._info_lbl.configure(
            text=t("guide.info", ssid=hf.ssid, bssid=hf.bssid,
                   file=Path(hf.filepath).name)
        )
        if hf.filepath:
            self._saved_lbl.configure(text=t("guide.saved", path=hf.filepath))
        else:
            self._saved_lbl.configure(text="")

    def _portal_clicked(self) -> None:
        if self._on_start_portal:
            self._on_start_portal(self._hf)

    def _crack_clicked(self) -> None:
        if self._on_crack_wordlist:
            self._on_crack_wordlist(self._hf)


class CredentialsPanel(ctk.CTkFrame):
    """Yakalanan giriş bilgilerini ve yakalanan Handshake arşivini gösterir."""

    def __init__(self, master, on_use_portal: Callable = None, on_crack: Callable = None, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=12, **kw)
        self._on_use_portal = on_use_portal
        self._on_crack = on_crack

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=t("creds.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))

        auto_wrap(ctk.CTkLabel(
            self,
            text=t("creds.desc"),
            font=FONT_UI_S, text_color=MUTED, anchor="w", justify="left",
        )).pack(fill="x", padx=14, pady=(0, 8))

        self._list = ctk.CTkScrollableFrame(self, fg_color=DARK_BG,
                                            corner_radius=10)
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._empty = ctk.CTkLabel(
            self._list,
            text=t("creds.empty"),
            font=FONT_UI, text_color=MUTED, justify="center",
        )
        self._empty.pack(pady=40)

        self._count_value = 0
        self._handshake_count = 0

    def add(self, cred) -> None:
        if self._count_value == 0 and self._handshake_count == 0:
            self._empty.pack_forget()
        self._count_value += 1
        CredentialRow(self._list, cred).pack(fill="x", padx=4, pady=3)
        self._update_counter()

    def load_handshakes(self, handshakes) -> None:
        # Mevcut handshake satırlarını yenile
        for child in list(self._list.winfo_children()):
            if isinstance(child, HandshakeRow):
                child.destroy()

        self._handshake_count = len(handshakes)
        if self._count_value == 0 and self._handshake_count == 0:
            self._empty.pack(pady=40)
        else:
            self._empty.pack_forget()

        if handshakes:
            hdr = ctk.CTkLabel(
                self._list, text=t("creds.handshake_header"),
                font=FONT_UI_B, text_color=ACCENT2
            )
            hdr.pack(fill="x", padx=4, pady=(6, 2))

            for hf in handshakes:
                row = HandshakeRow(self._list, hf, self._on_use_portal, self._on_crack)
                row.pack(fill="x", padx=4, pady=3)

        self._update_counter()

    def _update_counter(self) -> None:
        parts = []
        if self._count_value:
            parts.append(t("creds.count_passwords", count=self._count_value))
        if self._handshake_count:
            parts.append(t("creds.count_handshakes", count=self._handshake_count))
        self._count.configure(text=" · ".join(parts) if parts else "")

    def clear(self) -> None:
        for child in self._list.winfo_children():
            if child is not self._empty:
                child.destroy()
        self._count_value = 0
        self._handshake_count = 0
        self._count.configure(text="")
        self._empty.pack(pady=40)


# ────────────────────────── Kontrol listesi ─────────────────────────

class Checklist(ctk.CTkFrame):
    """Ortam kontrollerini ✓/✗ satırları olarak gösterir."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._rows: List[ctk.CTkFrame] = []

    def show(self, checks) -> None:
        for row in self._rows:
            row.destroy()
        self._rows = []

        missing = [c for c in checks if not c.ok and c.required]
        optional_missing = [c for c in checks if not c.ok and not c.required]

        for check in checks:
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
