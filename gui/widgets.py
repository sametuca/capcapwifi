"""
Reusable widget components for the CapCapWifi GUI.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional

import customtkinter as ctk


# ────────────────────────── colour palette ──────────────────────────

DARK_BG    = "#0D0D0D"
PANEL_BG   = "#161616"
CARD_BG    = "#1E1E1E"
ACCENT     = "#00E676"       # neon green
ACCENT2    = "#1DE9B6"       # teal
WARN       = "#FF6D00"       # orange
DANGER     = "#FF5252"       # red
MUTED      = "#616161"       # grey
TEXT_PRI   = "#EEEEEE"
TEXT_SEC   = "#9E9E9E"
BORDER     = "#2C2C2C"

FONT_MONO  = ("Courier New", 11)
FONT_MONO_S= ("Courier New", 10)
FONT_UI    = ("Segoe UI", 11)
FONT_UI_B  = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")


# ────────────────────────── Log Panel ───────────────────────────────

LEVEL_COLORS = {
    "info":    TEXT_SEC,
    "success": ACCENT,
    "warn":    WARN,
    "error":   DANGER,
    "raw":     MUTED,
}


class LogPanel(ctk.CTkFrame):
    """Scrollable log with colour-coded levels."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, **kw)
        header = ctk.CTkLabel(self, text="📋  CANLÍ LOG", font=FONT_TITLE,
                              text_color=ACCENT, anchor="w")
        header.pack(fill="x", padx=12, pady=(10, 4))

        self._text = tk.Text(
            self,
            bg=DARK_BG, fg=TEXT_PRI,
            font=FONT_MONO_S,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            state="disabled",
            wrap="word",
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        scrollbar = ctk.CTkScrollbar(self, command=self._text.yview)
        scrollbar.pack(side="right", fill="y")
        self._text.configure(yscrollcommand=scrollbar.set)

        for tag, colour in LEVEL_COLORS.items():
            self._text.tag_config(tag, foreground=colour)

    def append(self, msg: str, level: str = "info") -> None:
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n", level)
        self._text.configure(state="disabled")
        self._text.see("end")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")


# ────────────────────────── Network Table ───────────────────────────

COLUMNS = ("CH", "BSSID", "ESSID", "PWR", "QUALITY", "ENC", "CLIENTS")
COL_W   = (40, 150, 200, 50, 70, 80, 60)


class NetworkTable(ctk.CTkFrame):
    """Listbox-based table displaying scanned Wi-Fi networks."""

    def __init__(self, master, on_select: Callable = None, **kw):
        super().__init__(master, fg_color=PANEL_BG, **kw)
        self._on_select = on_select

        header = ctk.CTkLabel(self, text="📡  AĞ LİSTESİ", font=FONT_TITLE,
                              text_color=ACCENT, anchor="w")
        header.pack(fill="x", padx=12, pady=(10, 4))

        # Column headers (canvas-drawn)
        hdr_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=4)
        hdr_frame.pack(fill="x", padx=8, pady=(0, 2))
        for i, (col, w) in enumerate(zip(COLUMNS, COL_W)):
            lbl = ctk.CTkLabel(hdr_frame, text=col, font=FONT_UI_B,
                               text_color=ACCENT2, width=w, anchor="w")
            lbl.grid(row=0, column=i, padx=4, pady=2, sticky="w")

        # Listbox
        lb_frame = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=4)
        lb_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._lb = tk.Listbox(
            lb_frame,
            bg=DARK_BG, fg=TEXT_PRI,
            selectbackground="#1b3a2a",
            selectforeground=ACCENT,
            font=FONT_MONO_S,
            relief="flat", bd=0,
            activestyle="none",
            highlightthickness=0,
        )
        self._lb.pack(side="left", fill="both", expand=True)
        sb = ctk.CTkScrollbar(lb_frame, command=self._lb.yview)
        sb.pack(side="right", fill="y")
        self._lb.configure(yscrollcommand=sb.set)
        self._lb.bind("<<ListboxSelect>>", self._sel)

        self._candidates = []

    # ── public ──────────────────────────────────────────────────

    def load(self, candidates) -> None:
        self._candidates = list(candidates)
        self._lb.delete(0, "end")
        for c in self._candidates:
            row = self._fmt(c)
            self._lb.insert("end", row)
        # Colour-code by quality
        for i, c in enumerate(self._candidates):
            colour = c.signal_color
            self._lb.itemconfig(i, fg=colour)

    def selected(self):
        sel = self._lb.curselection()
        if sel:
            return self._candidates[sel[0]]
        return None

    def clear(self) -> None:
        self._lb.delete(0, "end")
        self._candidates = []

    # ── private ─────────────────────────────────────────────────

    @staticmethod
    def _fmt(c) -> str:
        essid = c.clean_essid[:24].ljust(24)
        bssid = c.bssid.ljust(17)
        ch    = str(c.channel).rjust(3)
        pwr   = str(c.power).rjust(4)
        qual  = c.quality.rjust(5)
        enc   = c.enc[:8].ljust(8)
        cli   = str(c.clients).rjust(3)
        hs    = "✔" if c.has_handshake else " "
        return f"  {ch}  {bssid}  {essid}  {pwr}  {qual}  {enc}  {cli}  {hs}"

    def _sel(self, _event) -> None:
        if self._on_select:
            c = self.selected()
            if c:
                self._on_select(c)


# ────────────────────────── Status Badge ────────────────────────────

STATE_ICONS = {
    "IDLE":                ("⬛", MUTED),
    "STARTING":            ("🔄", WARN),
    "SCANNING":            ("🔍", ACCENT2),
    "RUNNING":             ("⚡", ACCENT),
    "HANDSHAKE_CAPTURED":  ("🤝", ACCENT),
    "CREDENTIALS_FOUND":   ("🔑", "#FFD600"),
    "STOPPED":             ("⏹", MUTED),
    "ERROR":               ("❌", DANGER),
}


class StatusBadge(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=8, **kw)
        self._icon = ctk.CTkLabel(self, text="⬛", font=("Segoe UI", 20))
        self._icon.pack(side="left", padx=(12, 4), pady=8)
        self._label = ctk.CTkLabel(self, text="Hazır", font=FONT_UI_B,
                                   text_color=MUTED)
        self._label.pack(side="left", pady=8, padx=(0, 12))

    def update_state(self, state_name: str) -> None:
        icon, colour = STATE_ICONS.get(state_name, ("⬛", MUTED))
        self._icon.configure(text=icon, text_color=colour)
        self._label.configure(text=state_name.replace("_", " "), text_color=colour)


# ────────────────────────── Section Card ────────────────────────────

class SectionCard(ctk.CTkFrame):
    """A labelled card grouping related controls."""

    def __init__(self, master, title: str, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=8, **kw)
        ctk.CTkLabel(self, text=title, font=FONT_UI_B, text_color=ACCENT2,
                     anchor="w").pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=12)

    def body(self) -> ctk.CTkFrame:
        """Returns a content frame inside the card."""
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=12, pady=8)
        return f


# ────────────────────────── Credentials Panel ───────────────────────

class CredentialsPanel(ctk.CTkFrame):
    """Shows captured credentials in a treeview-like list."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, **kw)
        ctk.CTkLabel(self, text="🔑  BULUNAN ŞİFRELER", font=FONT_TITLE,
                     text_color=ACCENT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        hf = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=4)
        hf.pack(fill="x", padx=8, pady=(0, 2))
        for txt, w in [("Saat", 60), ("SSID", 160), ("BSSID", 150), ("Şifre", 200)]:
            ctk.CTkLabel(hf, text=txt, font=FONT_UI_B, text_color=ACCENT2,
                         width=w, anchor="w").pack(side="left", padx=4, pady=2)

        lb_f = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=4)
        lb_f.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._lb = tk.Listbox(lb_f, bg=DARK_BG, fg=ACCENT,
                              font=FONT_MONO_S, relief="flat", bd=0,
                              highlightthickness=0, selectbackground="#2a3a1a")
        self._lb.pack(side="left", fill="both", expand=True)
        sb = ctk.CTkScrollbar(lb_f, command=self._lb.yview)
        sb.pack(side="right", fill="y")
        self._lb.configure(yscrollcommand=sb.set)

    def add(self, cred) -> None:
        row = (f"  {cred.timestamp:<8}  {cred.ssid[:20]:<20}  "
               f"{cred.bssid:<17}  {cred.password}")
        self._lb.insert("end", row)
        self._lb.see("end")

    def clear(self) -> None:
        self._lb.delete(0, "end")
