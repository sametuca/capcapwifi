"""
CapCapWifi GUI – yeniden kullanılabilir arayüz bileşenleri.

Buradaki sınıfların hiçbiri ağ veya süreç işlemez; yalnızca görüntüler ve
kullanıcı etkileşimini callback olarak dışarı verir.

Tasarım dili: koyu zemin, yumuşak köşeli kartlar, tek vurgu rengi (neon yeşil)
ve ikincil olarak camgöbeği. Sinyal gücü sayı yerine çubuklarla gösterilir.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Sequence

import customtkinter as ctk


# ────────────────────────── renk paleti ─────────────────────────────

DARK_BG    = "#0A0B0D"
PANEL_BG   = "#101216"
CARD_BG    = "#171A1F"
CARD_HOVER = "#1D2127"
CARD_SEL   = "#12261B"
ACCENT     = "#00E676"
ACCENT2    = "#22D3EE"
WARN       = "#FFB020"
DANGER     = "#FF5370"
MUTED      = "#6B7280"
TEXT_PRI   = "#EDF0F4"
TEXT_SEC   = "#9AA3AF"
BORDER     = "#242830"

FONT_MONO  = ("JetBrains Mono", 11)
FONT_MONO_S= ("JetBrains Mono", 10)
FONT_UI    = ("Inter", 11)
FONT_UI_S  = ("Inter", 10)
FONT_UI_B  = ("Inter", 11, "bold")
FONT_TITLE = ("Inter", 14, "bold")


# ────────────────────────── sinyal çubukları ────────────────────────

class SignalBars(tk.Canvas):
    """4 çubuklu sinyal göstergesi – rakam yerine görsel güç."""

    BAR_STEPS = (4, 7, 10, 13)   # her çubuğun yüksekliği

    def __init__(self, master, width: int = 34, height: int = 15,
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
            top = 14 - bar_height
            self.create_rectangle(
                x, top, x + 5, 14,
                fill=colour if index < active else BORDER,
                outline="",
            )
            x += 7


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
        ctk.CTkLabel(head, text="Canlı log", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="0 satır", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))
        ctk.CTkButton(head, text="Temizle", width=64, height=24,
                      command=self.clear, fg_color="transparent",
                      hover_color=CARD_HOVER, border_width=1,
                      border_color=BORDER, text_color=TEXT_SEC,
                      font=FONT_UI_S).pack(side="right")

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
            self._count.configure(text=f"{self._lines} satır")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._lines = 0
        self._count.configure(text="0 satır")


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
                sep = ctk.CTkLabel(inner, text="──", font=FONT_UI_S,
                                   text_color=BORDER)
                sep.pack(side="left", padx=2)
                self._separators.append(sep)

            label = ctk.CTkLabel(
                inner, text=f"  {index + 1}  {step}  ", font=FONT_UI_S,
                text_color=TEXT_SEC, fg_color=CARD_BG, corner_radius=14,
                height=26,
            )
            label.pack(side="left", padx=2, pady=6)
            self._labels.append(label)

    def set_active(self, index: int) -> None:
        for i, label in enumerate(self._labels):
            if i == index:
                label.configure(text_color=DARK_BG, fg_color=ACCENT,
                                font=FONT_UI_B)
            elif i < index:
                label.configure(text_color=ACCENT2, fg_color=CARD_BG,
                                font=FONT_UI_S)
            else:
                label.configure(text_color=MUTED, fg_color=CARD_BG,
                                font=FONT_UI_S)

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
            self, text=badge_text, width=38, height=24, font=FONT_UI_B,
            text_color=ACCENT2 if not candidate.is_dfs else WARN,
            fg_color=DARK_BG, corner_radius=6,
        )
        badge.grid(row=0, column=0, padx=(10, 8), pady=(8, 2), sticky="w")

        # SSID: Kalın, belirgin ve tam genişlikte ana başlık
        name = ctk.CTkLabel(
            self, text=candidate.clean_essid, font=FONT_UI_B,
            text_color=TEXT_PRI, anchor="w", justify="left"
        )
        name.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 2))

        # Sağ taraf: Sinyal çubukları + dBm
        sig_frame = ctk.CTkFrame(self, fg_color="transparent")
        sig_frame.grid(row=0, column=2, padx=(0, 10), pady=(8, 2), sticky="e")

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
        sub.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

        # Alt sağ: Bağlı cihaz rozeti, Handshake rozeti ve DFS etiketi
        extra_frame = ctk.CTkFrame(self, fg_color="transparent")
        extra_frame.grid(row=1, column=2, padx=(0, 10), pady=(0, 8), sticky="e")

        clients_text = f"{candidate.clients} cihaz" if candidate.clients else "cihaz yok"
        clients_badge = ctk.CTkLabel(
            extra_frame, text=clients_text, font=FONT_UI_S, width=64, height=20,
            corner_radius=6,
            text_color=DARK_BG if candidate.has_clients else MUTED,
            fg_color=ACCENT if candidate.has_clients else DARK_BG,
        )
        clients_badge.pack(side="left", padx=(0, 4))

        if candidate.has_handshake:
            ctk.CTkLabel(
                extra_frame, text="✔ Handshake", font=FONT_UI_S,
                text_color=ACCENT, fg_color="#102A1E", corner_radius=6,
                height=20, padx=6
            ).pack(side="left", padx=(0, 4))

        if candidate.is_dfs:
            ctk.CTkLabel(
                extra_frame, text="DFS", font=FONT_UI_S,
                text_color=WARN, fg_color="#33260F", corner_radius=6,
                height=20, padx=6
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
        ctk.CTkLabel(head, text="Yakındaki ağlar", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))

        self._search = ctk.CTkEntry(
            head, placeholder_text="Ağ adı veya BSSID ara…", width=220,
            height=28, fg_color=DARK_BG, border_color=BORDER,
            text_color=TEXT_PRI, font=FONT_UI_S)
        self._search.pack(side="right")
        self._search.bind("<KeyRelease>", lambda _e: self._apply_filter())

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=14, pady=(2, 8))
        ctk.CTkLabel(
            legend,
            text=("Yeşil rozet = bağlı cihaz var (deauth atılabilir)   ·   "
                  "✔ = handshake kayıtlı   ·   DFS = sahte AP açılamaz"),
            font=FONT_UI_S, text_color=MUTED, anchor="w", justify="left",
            wraplength=760,
        ).pack(side="left")

        self._list = ctk.CTkScrollableFrame(self, fg_color=DARK_BG,
                                            corner_radius=10)
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 2))

        # Alttaki yatay scroll çubuğu (dar ekranlarda yatay gezinme sağlar)
        self._x_scroll = ctk.CTkScrollbar(
            self, orientation="horizontal",
            command=self._list._parent_canvas.xview,
            height=10
        )
        self._list._parent_canvas.configure(xscrollcommand=self._x_scroll.set)
        self._x_scroll.pack(fill="x", padx=12, pady=(0, 6))

        self._empty = ctk.CTkLabel(
            self._list,
            text="Henüz ağ yok.\n\nSıradaki adım: sol panelden süreyi seç ve "
                 "“🔍 Tara” düğmesine bas.",
            font=FONT_UI, text_color=MUTED, justify="center",
        )
        self._empty.pack(pady=40)

        self._hint = ctk.CTkLabel(
            self, text="Önce “🔍 Tara” ile ağları listeleyin.", font=FONT_UI_S,
            text_color=MUTED, anchor="w", justify="left", wraplength=760,
        )
        self._hint.pack(fill="x", padx=14, pady=(0, 12))

    # ── public ──────────────────────────────────────────────────

    def load(self, candidates) -> None:
        self._candidates = list(candidates)
        self._selected = None
        self._search.delete(0, "end")
        self._render()

        with_clients = sum(1 for c in self._candidates if c.has_clients)
        handshakes = sum(1 for c in self._candidates if c.has_handshake)
        if self._candidates:
            self._hint.configure(
                text=(f"{len(self._candidates)} ağ, {with_clients} tanesinde "
                      f"bağlı cihaz, {handshakes} tanesinde kayıtlı handshake. "
                      "Bir satıra tıkla; alttaki alanlar kendiliğinden dolar."),
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
        self._hint.configure(text="Önce “🔍 Tara” ile ağları listeleyin.",
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

        self._count.configure(text=f"{len(self._candidates)} ağ")
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
                text=f"{visible}/{len(self._candidates)} ağ" if needle
                else f"{len(self._candidates)} ağ")

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
        self._label = ctk.CTkLabel(self, text="Hazır", font=FONT_UI_B,
                                   text_color=MUTED)
        self._label.pack(side="left", padx=(0, 14), pady=6)

    def update_state(self, text: str, colour: Optional[str] = None) -> None:
        icon, default_colour = STATE_ICONS.get(text, ("●", MUTED))
        self._icon.configure(text=icon, text_color=colour or default_colour)
        self._label.configure(
            text=text.replace("_", " ").title(),
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
        super().__init__(master, fg_color=CARD_BG, corner_radius=12, **kw)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(head, text=title, font=FONT_UI_B, text_color=accent,
                     anchor="w").pack(side="left")

        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=FONT_UI_S, text_color=MUTED,
                         anchor="w", justify="left", wraplength=260).pack(
                fill="x", padx=14, pady=(2, 0))

        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(
            fill="x", padx=14, pady=(8, 0))

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
            text_color=ACCENT2, fg_color=DARK_BG, corner_radius=6,
            width=118, height=22,
        ).grid(row=0, column=1, rowspan=2, padx=(0, 10))

        ctk.CTkLabel(self, text=cred.display_username, font=FONT_UI_B,
                     text_color=TEXT_PRI, anchor="w").grid(
            row=0, column=2, sticky="w", pady=(8, 0))
        ctk.CTkLabel(self, text=cred.password or "-", font=FONT_MONO,
                     text_color=ACCENT, anchor="w").grid(
            row=1, column=2, sticky="w", pady=(0, 8))

        ctk.CTkButton(self, text="Kopyala", width=72, height=26,
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
        title_text = f"{hf.ssid or '<Bilinmeyen Ağ>'}"
        ctk.CTkLabel(
            self, text=title_text, font=FONT_UI_B, text_color=TEXT_PRI, anchor="w"
        ).grid(row=0, column=1, sticky="w", pady=(6, 0))

        sub_text = f"{hf.bssid or '-'}  ·  {Path(hf.filepath).name}  ·  {hf.size_kb if hasattr(hf, 'size_kb') else f'{hf.size_bytes}B'}  ·  {hf.created_at}"
        ctk.CTkLabel(
            self, text=sub_text, font=FONT_MONO_S, text_color=MUTED, anchor="w"
        ).grid(row=1, column=1, sticky="w", pady=(0, 6))

        # Aksiyon Butonları
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=0, column=2, rowspan=2, padx=(6, 10), pady=6, sticky="e")

        if on_use_portal:
            ctk.CTkButton(
                btn_f, text="⚡ Portal'da Kullan", width=120, height=26,
                font=FONT_UI_S, fg_color=ACCENT, text_color=DARK_BG,
                hover_color="#00C86A", command=lambda: on_use_portal(hf)
            ).pack(side="left", padx=(0, 6))

        if on_crack:
            ctk.CTkButton(
                btn_f, text="🔑 Aircrack ile Kır", width=110, height=26,
                font=FONT_UI_S, fg_color=CARD_BG, text_color=TEXT_PRI,
                hover_color=CARD_HOVER, border_width=1, border_color=BORDER,
                command=lambda: on_crack(hf)
            ).pack(side="left")


class NextStepGuideCard(ctk.CTkFrame):
    """Handshake yakalandığında kullanıcıya sırada ne olduğunu anlatan
    ve tek tıkla Captive Portal veya Aircrack başlatan rehberlik kartı."""

    def __init__(self, master, on_start_portal: Callable = None, on_crack_wordlist: Callable = None, on_dismiss: Callable = None, **kw):
        super().__init__(master, fg_color="#0C2417", corner_radius=12,
                         border_width=2, border_color=ACCENT, **kw)
        self._on_start_portal = on_start_portal
        self._on_crack_wordlist = on_crack_wordlist
        self._on_dismiss = on_dismiss
        self._hf = None

        # Üst Başlık & Kapatma Butonu
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))

        title_lbl = ctk.CTkLabel(
            head, text="🎉 TEBRİKLER! WPA HANDSHAKE BAŞARIYLA YAKALANDI",
            font=FONT_TITLE, text_color=ACCENT, anchor="w"
        )
        title_lbl.pack(side="left")

        if on_dismiss:
            ctk.CTkButton(
                head, text="✕", width=26, height=22,
                command=on_dismiss, fg_color="transparent",
                hover_color="#1E3E2E", text_color=TEXT_SEC, font=FONT_UI_B
            ).pack(side="right")

        # Hedef Ağ & Dosya Bilgisi Banner
        self._info_lbl = ctk.CTkLabel(
            self, text="Hedef Ağ: - · Dosya: -",
            font=FONT_UI_B, text_color=TEXT_PRI, anchor="w", justify="left"
        )
        self._info_lbl.pack(fill="x", padx=14, pady=(0, 6))

        # Açıklama
        guide_box = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=10, border_width=1, border_color=BORDER)
        guide_box.pack(fill="x", padx=14, pady=(0, 8))

        desc_text = (
            "💡 ŞİMDİ NE YAPMALISINIZ? İKİ SEÇENEĞİNİZ VAR:\n\n"
            "1. YOL (ÖNERİLEN): CAPTIVE PORTAL (SAHTE GİRİŞ EKRANI) BAŞLATIN\n"
            "   Elinizde doğrulanmış handshake olduğu için artık sahte AP açtığınızda kurbanın gireceği parola\n"
            "   bu dosya ile %100 otomatik doğrulanır. Sahte şifre girerse reddedilir, doğru girerse anında ekrana düşer!\n\n"
            "2. YOL (OFFLINE): AIRCRACK-NG İLE SÖZLÜK (WORDLIST) SALDIRISI YAPIN\n"
            "   Handshake (.cap) dosyası kaydedildi. Hedef ağ ile bağlantıyı kesip wordlist (rockyou.txt vb.) ile\n"
            "   bilgisayarınızda internetsiz çevrimdışı kırmayı deneyebilirsiniz."
        )
        ctk.CTkLabel(
            guide_box, text=desc_text, font=FONT_UI_S, text_color=TEXT_SEC,
            justify="left", anchor="w", padx=12, pady=8
        ).pack(fill="x")

        # Aksiyon Butonları
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=(0, 10))

        self._btn_portal = ctk.CTkButton(
            btn_bar, text="⚡ Bu Ağ İçin Captive Portal Başlat (Önerilen)",
            command=self._portal_clicked, fg_color=ACCENT, text_color=DARK_BG,
            hover_color="#00C86A", font=FONT_UI_B, height=36
        )
        self._btn_portal.pack(side="left", padx=(0, 8), expand=True, fill="x")

        self._btn_crack = ctk.CTkButton(
            btn_bar, text="🔑 Aircrack-ng ile Kırmayı Dene",
            command=self._crack_clicked, fg_color=CARD_BG, text_color=TEXT_PRI,
            hover_color=CARD_HOVER, border_width=1, border_color=BORDER,
            font=FONT_UI, height=36
        )
        self._btn_crack.pack(side="left")

    def set_handshake(self, hf) -> None:
        self._hf = hf
        self._info_lbl.configure(
            text=f"Hedef Ağ: {hf.ssid}  ·  BSSID: {hf.bssid}  ·  Dosya: {Path(hf.filepath).name}"
        )

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
        ctk.CTkLabel(head, text="Yakalanan Girişler & Handshake Arşivi", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        self._count = ctk.CTkLabel(head, text="", font=FONT_UI_S,
                                   text_color=MUTED)
        self._count.pack(side="left", padx=(8, 0))

        # Sekme seçici: Portaldan Girişler / Handshake Arşivi
        self._view_mode = "all"

        ctk.CTkLabel(
            self,
            text=("Web portallarına yazılan şifreler ve dinleme ile yakalanan WPA .cap "
                  "el sıkışma dosyaları burada arşivlenir."),
            font=FONT_UI_S, text_color=MUTED, anchor="w", justify="left",
            wraplength=760,
        ).pack(fill="x", padx=14, pady=(0, 8))

        self._list = ctk.CTkScrollableFrame(self, fg_color=DARK_BG,
                                            corner_radius=10)
        self._list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._empty = ctk.CTkLabel(
            self._list,
            text=("Henüz giriş veya handshake yok.\n\n"
                  "• Bir cihaz sahte portala bağlanıp şifre girdiğinde burada belirir.\n"
                  "• Yakalanan WPA handshake dosyaları da burada listelenir."),
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
                self._list, text="── 🤝 Yakalanan WPA Handshake (.cap) Dosyaları ──",
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
            parts.append(f"{self._count_value} şifre")
        if self._handshake_count:
            parts.append(f"{self._handshake_count} handshake")
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
            text = (f"{len(missing)} zorunlu bileşen eksik – "
                    "log panelinde kurulum komutu yazıyor")
            colour = WARN
        elif optional_missing:
            text = (f"Hazır. {len(optional_missing)} opsiyonel araç yok, "
                    "temel akışlar çalışır.")
            colour = ACCENT2
        else:
            text = "Her şey hazır."
            colour = ACCENT

        summary = ctk.CTkLabel(self, text=text, font=FONT_UI_S,
                               text_color=colour, anchor="w", justify="left",
                               wraplength=240)
        summary.pack(fill="x", pady=(6, 0))
        self._rows.append(summary)
