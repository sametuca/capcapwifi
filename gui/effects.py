"""Animasyon, yükleme ve düğme yardımcıları.

Buradaki her şey görsel: ağ, süreç veya dosya işlemez. Amaç, arayüzün
"durdu mu, çalışıyor mu?" sorusunu renk ve hareketle cevaplaması.

Tasarım kuralları
-----------------
* Her animasyon iptal edilebilir. Widget yıkıldığında ``after`` zinciri
  sessizce durur, ``TclError`` sızdırmaz.
* Süreler kısa: hover 150 ms, durum geçişi 200 ms. Uzun animasyon kullanıcıyı
  bekletir, kısa animasyon akıcı hissettirir.
* Meşgul düğme metni değişmez, rengi nefes alır. Böylece etiket genişliği
  sabit kalır ve çevresindeki düzen kaymaz.
"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Dict, Optional, Tuple

import customtkinter as ctk

import theme
from theme import (
    ACCENT,
    ACCENT2,
    ACCENT2_DK,
    ACCENT2_ON,
    ACCENT_DK,
    ACCENT_ON,
    BORDER,
    BORDER_SOFT,
    CARD_BG,
    CARD_HOVER,
    DANGER,
    DANGER_DK,
    DANGER_ON,
    DARK_BG,
    ELEV_BG,
    FONT_UI_S,
    MUTED,
    OFF_BG,
    OFF_BORDER,
    OFF_TEXT,
    PANEL_BG,
    TEXT_PRI,
    TEXT_SEC,
    WARN,
    WARN_DK,
    WARN_ON,
    disabled_pair,
    is_colour,
    mix_colour,
)

# ───────────────────────────── easing ──────────────────────────────


def ease_out_cubic(t: float) -> float:
    """Hızlı başlar, yavaşlar – hover ve açılış geçişleri için doğal."""
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    """Yumuşak giriş/çıkış – yer değiştiren nesneler için."""
    return 3 * t * t - 2 * t * t * t


# ──────────────────────────── animatör ─────────────────────────────

class Animator:
    """Bir widget üzerinde isimlendirilmiş ``after`` zincirlerini yönetir.

    Aynı isimle yeni bir animasyon başlatılırsa eskisi iptal edilir, böylece
    hızlı hover giriş/çıkışlarında zincirler birikmez.
    """

    def __init__(self, widget: tk.Misc):
        self._widget = widget
        self._jobs: Dict[str, str] = {}

    def alive(self) -> bool:
        try:
            return bool(self._widget.winfo_exists())
        except Exception:
            return False

    def cancel(self, key: Optional[str] = None) -> None:
        for name in (list(self._jobs) if key is None else [key]):
            job = self._jobs.pop(name, None)
            if job is None:
                continue
            try:
                self._widget.after_cancel(job)
            except Exception:
                pass

    def tween(self, key: str, duration_ms: int,
              apply: Callable[[float], None],
              done: Optional[Callable[[], None]] = None,
              ease: Callable[[float], float] = ease_out_cubic) -> None:
        """``apply(0..1)`` çağrılarını zaman içinde yayarak çalıştırır."""
        self.cancel(key)
        frames = max(4, min(20, duration_ms // 16))
        delay = max(8, duration_ms // frames)
        step = [0]

        def _frame() -> None:
            if not self.alive():
                self._jobs.pop(key, None)
                return
            step[0] += 1
            progress = min(1.0, step[0] / frames)
            try:
                apply(ease(progress))
            except Exception:
                self._jobs.pop(key, None)
                return
            if progress >= 1.0:
                self._jobs.pop(key, None)
                if done is not None:
                    try:
                        done()
                    except Exception:
                        pass
                return
            try:
                self._jobs[key] = self._widget.after(delay, _frame)
            except Exception:
                self._jobs.pop(key, None)

        _frame()

    def colour(self, key: str, target: tk.Misc, attribute: str,
               start: str, end: str, duration_ms: int = 150,
               done: Optional[Callable[[], None]] = None,
               ease: Callable[[float], float] = ease_out_cubic) -> None:
        """``target`` üzerinde tek bir renk özelliğini yumuşakça değiştirir."""
        if is_colour(start) and is_colour(end) and start != end:
            def _apply(p: float) -> None:
                target.configure(**{attribute: mix_colour(start, end, p)})

            self.tween(key, duration_ms, _apply, done, ease)
            return
        self.cancel(key)
        try:
            target.configure(**{attribute: end})
        except Exception:
            pass
        if done is not None:
            done()

    def pulse(self, key: str, target: tk.Misc, attribute: str,
              colours: Tuple[str, ...], period_ms: int = 1100) -> None:
        """İki (veya daha fazla) renk arasında sonsuz yumuşak nefes."""
        self.cancel(key)
        if len(colours) < 2:
            return
        steps = len(colours) - 1
        phase = [0.0]
        increment = 60.0 / period_ms * 2 * math.pi

        def _tick() -> None:
            if not self.alive():
                self._jobs.pop(key, None)
                return
            phase[0] += increment
            position = ((math.sin(phase[0]) + 1) / 2) * steps
            index = min(int(position), steps - 1)
            local = position - index
            try:
                target.configure(**{
                    attribute: mix_colour(colours[index],
                                          colours[index + 1], local)})
            except Exception:
                self._jobs.pop(key, None)
                return
            try:
                self._jobs[key] = self._widget.after(60, _tick)
            except Exception:
                self._jobs.pop(key, None)

        _tick()


# ──────────────────────────── yükleyiciler ─────────────────────────

class Spinner(tk.Canvas):
    """Dönen halka: "işlem sürüyor" bilgisini tek bakışta verir.

    Çizim 10 kısa çizgiden oluşur; her çizgi kuyruğa doğru eriyen bir tonda
    boyanır, faz kaydıkça iz dönüyormuş gibi görünür. Yay çizmekten ucuz,
    bu yüzden her durum değişiminde yeniden çizilmesi sorun değil.
    """

    TICKS = 10

    def __init__(self, master, size: int = 18, bg: str = DARK_BG,
                 colour: str = ACCENT, thickness: int = 2,
                 interval: int = 55, **kw):
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._size = size
        self._bg = bg
        self._colour = colour
        self._thickness = thickness
        self._interval = interval
        self._phase = 0
        self._job: Optional[str] = None
        self.bind("<Destroy>", lambda _e: self.stop(), add="+")
        self._draw()

    def start(self) -> None:
        if self._job is None:
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def set_colours(self, colour: Optional[str] = None,
                    bg: Optional[str] = None) -> None:
        if colour:
            self._colour = colour
        if bg:
            self._bg = bg
            try:
                self.configure(bg=bg)
            except Exception:
                pass
        self._draw()

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % self.TICKS
        self._draw()
        try:
            self._job = self.after(self._interval, self._tick)
        except Exception:
            self._job = None

    def _draw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        centre = self._size / 2.0
        inner = max(1.5, centre - self._thickness * 1.9)
        outer = centre - self._thickness * 0.5
        for i in range(self.TICKS):
            strength = ((i + self._phase) % self.TICKS) / float(self.TICKS)
            colour = mix_colour(self._bg, self._colour, 0.12 + 0.88 * strength)
            angle = (i / self.TICKS) * 2 * math.pi
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            self.create_line(
                centre + cos_a * inner, centre + sin_a * inner,
                centre + cos_a * outer, centre + sin_a * outer,
                fill=colour, width=self._thickness, capstyle="round",
            )


class PulseLabel(ctk.CTkLabel):
    """Rengi yumuşakça nefes alan etiket – "meşgul" metinleri için.

    Harf ekleyip çıkarmak yerine rengi döndürür: etiketin genişliği sabit
    kalır, çevresindeki düzen kaymaz.
    """

    def __init__(self, master, text: str = "",
                 colours: Tuple[str, ...] = (MUTED, ACCENT2, MUTED), **kw):
        kw.setdefault("font", ("Inter", 11))
        super().__init__(master, text=text, text_color=colours[0], **kw)
        self._colours = colours
        self._animator = Animator(self)
        self._active = False
        self.bind("<Destroy>", lambda _e: self.stop_pulse(), add="+")

    def start_pulse(self, text: Optional[str] = None,
                    colours: Optional[Tuple[str, ...]] = None) -> None:
        if text is not None:
            self.configure(text=text)
        if colours is not None:
            self._colours = colours
        if self._active:
            return
        self._active = True
        self._animator.pulse("pulse", self, "text_color", self._colours)

    def stop_pulse(self, text: Optional[str] = None,
                   colour: Optional[str] = None) -> None:
        self._active = False
        self._animator.cancel("pulse")
        if text is not None:
            self.configure(text=text)
        if colour is not None:
            try:
                self.configure(text_color=colour)
            except Exception:
                pass


class SkeletonList(ctk.CTkFrame):
    """Liste yüklenirken içeriğin yerini tutan, nefes alan satırlar.

    Boş bir "henüz ağ yok" yazısı yerine satır iskeleti göstermek, taramanın
    gerçekten sürdüğünü ve listenin birazdan dolacağını anlatır.
    """

    def __init__(self, master, rows: int = 4, accent: str = ACCENT2, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._accent = accent
        self._rows = []
        self._phase = 0.0
        self._job: Optional[str] = None

        for index in range(rows):
            row = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10,
                               border_width=1, border_color=BORDER_SOFT,
                               height=56)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)

            bar = ctk.CTkFrame(row, fg_color=ELEV_BG, width=3, corner_radius=2)
            bar.pack(side="left", fill="y", padx=(10, 0), pady=11)

            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(side="left", fill="x", expand=True, padx=(12, 14),
                       pady=11)
            ctk.CTkFrame(inner, fg_color=ELEV_BG, height=10, width=54,
                         corner_radius=4).pack(anchor="w", pady=(0, 8))
            ctk.CTkFrame(inner, fg_color=ELEV_BG, height=9,
                         width=150 + index * 34,
                         corner_radius=4).pack(anchor="w")

            self._rows.append((row, bar))
        self.bind("<Destroy>", lambda _e: self.stop(), add="+")

    def start(self) -> None:
        if self._job is None:
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self) -> None:
        self._phase += 0.10
        wave = (math.sin(self._phase) + 1.0) / 2.0
        fill = mix_colour(CARD_BG, self._accent, 0.03 + 0.09 * wave)
        bar = mix_colour(ELEV_BG, self._accent, 0.12 + 0.40 * wave)
        for row, accent_bar in self._rows:
            try:
                row.configure(fg_color=fill)
                accent_bar.configure(fg_color=bar)
            except Exception:
                return
        try:
            self._job = self.after(70, self._tick)
        except Exception:
            self._job = None


class ActivityBar(tk.Canvas):
    """İnce, süpüren ışık şeridi – uygulama genelinde "meşgul" göstergesi.

    Durum rozeti hangi işin döndüğünü söyler; bu şerit pencerenin herhangi bir
    yerinden bakıldığında "bir şey oluyor" bilgisini taşır. Yalnızca meşgulken
    görünür, boştayken tamamen kaybolur.
    """

    TAIL = 8
    SPAN = 0.22   # kuyruğun şerit uzunluğuna oranı

    def __init__(self, master, height: int = 3, bg: str = DARK_BG, **kw):
        super().__init__(master, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._height = height
        self._position = -self.SPAN
        self._job: Optional[str] = None
        self.bind("<Configure>", lambda _e: self._draw(), add="+")
        self.bind("<Destroy>", lambda _e: self.stop(), add="+")

    def start(self) -> None:
        if self._job is None:
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self.delete("all")
        except Exception:
            pass

    def _tick(self) -> None:
        self._position += 0.014
        if self._position > 1.0:
            self._position = -self.SPAN
        self._draw()
        try:
            self._job = self.after(30, self._tick)
        except Exception:
            self._job = None

    def _draw(self) -> None:
        try:
            width = max(1, self.winfo_width())
            self.delete("all")
            head = self._position * width
            span = max(60.0, self.SPAN * width)
            for i in range(self.TAIL):
                offset = i / float(self.TAIL)
                x0 = head - span + span * offset
                x1 = x0 + max(2.0, span / self.TAIL * 1.6)
                x0 = max(0.0, min(float(width), x0))
                x1 = max(0.0, min(float(width), x1))
                if x1 - x0 < 1:
                    continue
                colour = mix_colour(ACCENT, ACCENT2, offset)
                self.create_rectangle(x0, 0, x1, self._height,
                                      fill=colour, outline="")
        except Exception:
            pass


class NotificationBar(ctk.CTkFrame):
    """Üst şeridin altında beliren, kendiliğinden kaybolan tek satırlık bildirim.

    Neden yüzen (overlay) değil de satır içi: yüzen bir katman, altındaki
    düğmeleri örter — kullanıcı tam da "Temizle"ye basacakken düğme kaybolur.
    Bu şerit düzeni iterek açılır, hiçbir kontrolü gizlemez ve bir iş
    bittiğinde göz zaten üstte olduğu için fark edilir.

    Türü renk ve simge taşır; metin her durumda TEXT_PRI kalır: okunabilirlik
    ton oyununa kurban edilmez.
    """

    KINDS = {
        "info": (ACCENT2, "i"),
        "success": (ACCENT, "✓"),
        "warn": (WARN, "!"),
        "error": (DANGER, "✕"),
    }

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=CARD_BG, corner_radius=0,
                         border_width=0, **kw)
        self._animator = Animator(self)
        self._hide_job: Optional[str] = None
        self._visible = False
        self._after_widget = None

        self._stripe = tk.Frame(self, bg=ACCENT2, width=3)
        self._stripe.pack(side="left", fill="y")

        self._icon = ctk.CTkLabel(self, text="i", font=("Inter", 11, "bold"),
                                  text_color=ACCENT2, width=16)
        self._icon.pack(side="left", padx=(12, 6), pady=7)
        self._label = ctk.CTkLabel(self, text="", font=FONT_UI_S,
                                   text_color=TEXT_PRI, anchor="w",
                                   justify="left")
        self._label.pack(side="left", fill="x", expand=True, pady=7)

    @property
    def visible(self) -> bool:
        return self._visible

    def show(self, text: str, kind: str = "info", timeout: int = 4500) -> None:
        colour, icon = self.KINDS.get(kind, self.KINDS["info"])
        self._label.configure(text=text)
        self._icon.configure(text=icon, text_color=colour)
        try:
            self._stripe.configure(bg=colour)
        except Exception:
            pass
        self.configure(fg_color=mix_colour(CARD_BG, colour, 0.10))
        if not self._visible:
            self._visible = True
            # Yerleşimi iterek aç: hiçbir kontrolün üstüne binmez.
            self.pack(fill="x", after=getattr(self, "_after_widget", None))
        self._animator.colour("glow", self, "fg_color",
                              mix_colour(CARD_BG, colour, 0.26),
                              mix_colour(CARD_BG, colour, 0.10), 520,
                              ease=ease_in_out)
        self._schedule_hide(timeout)

    def hide(self) -> None:
        if self._hide_job is not None:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        self._animator.cancel("glow")
        self._visible = False
        try:
            self.pack_forget()
        except Exception:
            pass

    def _schedule_hide(self, timeout: int) -> None:
        if self._hide_job is not None:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = self.after(timeout, self.hide)

    def destroy(self) -> None:
        self._animator.cancel()
        if self._hide_job is not None:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
        super().destroy()


# ───────────────────────────── düğmeler ────────────────────────────
# Renk tabloları ve durum formülleri ``theme`` içinde: bu modül yalnızca
# onları customtkinter düğmesine uygular. Böylece palet, görüntü sunucusu
# veya customtkinter olmadan test edilebilir (tests/test_gui_theme.py).

FILL_KINDS = theme.FILL_KINDS
OUTLINE_KINDS = theme.OUTLINE_KINDS
LOADING_TINT = theme.LOADING_TINT
OUTLINE_TINT = theme.OUTLINE_TINT
OFF_BORDER_TINT = theme.OFF_BORDER_TINT


class FxButton(ctk.CTkButton):
    """Hover'da rengi yumuşak geçen, pasifken kimliğini koruyan düğme.

    Neden ayrı sınıf: customtkinter pasif düğmede yalnızca metni soluklaştırır,
    dolguyu olduğu gibi bırakır. Bu yüzden pasif bir "Tara" düğmesi hâlâ
    parlak neon yeşil görünüp "basılabilir" izlenimi veriyordu. Burada pasif
    durum, vurgunun zemine karışmış soluk tintine geçer: düğme sönük, ama
    hangi düğme olduğu hâlâ okunur (etiket ~5:1 kontrast).
    """

    def __init__(self, master, text: str = "", kind: str = "primary", **kw):
        self._kind = kind
        self._accent = self._resolve_accent(kind)
        # _draw() sırasında (super().__init__ içinde) kullanıldığı için
        # hover bağlarının defteri kurucudan ÖNCE hazır olmalı.
        self._pointer_targets: set = set()
        self._hovered = False
        self._loading = False
        fill, hover, fg_text = self._palette(kind, self._accent)
        bordered = not fill

        kw.setdefault("corner_radius", 10)
        kw.setdefault("font", ("Inter", 12, "bold"))
        kw.setdefault("height", 34)
        super().__init__(
            master, text=text,
            fg_color=fill if fill else "transparent",
            hover_color=hover or fill or PANEL_BG,
            text_color=fg_text,
            text_color_disabled=OFF_TEXT,
            # Kenarlık her zaman 1 px: dolu türlerde normal durumda dolguyla
            # aynı renkte olduğu için görünmez, pasif durumda ise düğmenin
            # kimliğini taşıyan ince vurgu çizgisi olur. border_width=0
            # bırakılırsa pasif düğme kimliksiz gri bir bloğa dönüşüyordu.
            border_width=1,
            border_color=self._accent if bordered else fill,
            **kw,
        )
        self._animator = Animator(self)
        self._base_text = text
        self._watch_pointer()
        self._style()

    # ── renk seçimi ─────────────────────────────────────────────
    # Tüm durum renkleri theme içinde hesaplanır; burada yalnızca uygulanır.

    @staticmethod
    def _resolve_accent(kind: str) -> str:
        return theme.kind_accent(kind)

    def _palette(self, kind: str, accent: str) -> Tuple[str, str, str]:
        """(dolgu, hover, metin); kontur türlerinde dolgu boş string."""
        del accent
        return theme.button_palette(kind)

    def _resting(self) -> Tuple[str, str]:
        """(dolgu, kenarlık) – normal durumdaki somut renkler."""
        fill, _hover, _text = self._palette(self._kind, self._accent)
        return fill, (self._accent if not fill else fill)

    def _resting(self) -> Tuple[str, str]:
        """(dolgu, kenarlık) – normal durumdaki somut renkler."""
        fill, _hover, _text = self._palette(self._kind, self._accent)
        return fill, (self._accent if not fill else fill)

    # ── public ──────────────────────────────────────────────────

    @property
    def loading(self) -> bool:
        return self._loading

    def set_loading(self, loading: bool, text: Optional[str] = None) -> None:
        """Meşgul görünümü: vurgunun soluk dolgusu + nefes alan etiket.

        Pasiflikten farkı: metin canlı vurgu rengini korur ve nefes alır,
        dolgu ise düğmenin "hangi düğme" olduğunu hatırlatan bir tinttir.
        Böylece kullanıcı "çalışıyor" ile "kullanılamaz" arasındaki farkı
        tek bakışta ayırır.
        """
        if text is not None and text != self._base_text:
            self._base_text = text
            self._apply_text(text)
        if loading == self._loading:
            return
        self._loading = loading
        self._style(animate=True)

    def set_text(self, text: str) -> None:
        self._base_text = text
        self._apply_text(text)

    def flash(self, colour: Optional[str] = None) -> None:
        """Tek seferlik dikkat çekmesi (ör. yakalama anında)."""
        highlight = colour or ACCENT
        fill, _border = self._resting()
        base = fill or PANEL_BG
        lit = mix_colour(base, highlight, 0.45)
        self._animator.colour("flash", self, "fg_color", lit, base, 520,
                              ease=ease_in_out)

    def destroy(self) -> None:
        self._animator.cancel()
        super().destroy()

    # ── görünüm ─────────────────────────────────────────────────

    def _apply_text(self, text: str) -> None:
        # Doğrudan temel sınıfın configure'ı: kendi configure'ımızı çağırırsak
        # _style -> configure -> _style döngüsü oluşur.
        try:
            ctk.CTkButton.configure(self, text=text)
        except Exception:
            pass

    def _style(self, animate: bool = False) -> None:
        """Durum -> renk eşlemesini uygular (renkler theme içinde hesaplanır).

        Üç durum, üç ayrı görsel dil — hepsi ölçülmüş kontrastla:

        * ``normal``   dolu vurgu + üzerine okunur koyu metin (7–11:1).
        * ``loading``  dolgu canlı kalır, hafifçe koyulaşıp nefes alır; metin
                       normalin aynısı (≥5:1). "Çalışıyor" canlı görünür.
        * ``disabled`` nötr dolgu + ince vurgu kenarlığı + OFF_TEXT (~6:1).
                       Sönük ama hangi düğme olduğu hâlâ okunur.
        """
        fill, border = self._resting()
        _f, hover, text = self._palette(self._kind, self._accent)

        if self._loading:
            target_fill, target_border, target_text = theme.loading_palette(
                self._kind)
        elif self.cget("state") == "disabled":
            target_fill, target_border = disabled_pair(self._accent, CARD_BG)
            target_text = OFF_TEXT
        else:
            target_fill = hover if self._hovered else fill
            target_border = border
            target_text = text

        try:
            ctk.CTkButton.configure(self, text_color=target_text,
                                    text_color_disabled=target_text,
                                    border_color=target_border)
        except Exception:
            pass

        if not target_fill:                       # kontur düğmesi (normal)
            self._animator.cancel("fill")
            try:
                ctk.CTkButton.configure(self, fg_color="transparent")
            except Exception:
                pass
        elif animate:
            current = self.cget("fg_color")
            start = current if is_colour(current) else target_fill
            self._animator.colour("fill", self, "fg_color", start,
                                  target_fill, 170)
        else:
            self._animator.cancel("fill")
            try:
                ctk.CTkButton.configure(self, fg_color=target_fill)
            except Exception:
                pass

        if self._loading and target_fill:
            # Nefes: dolgu koyulaşıp geri döner. Metin sabit kalır, böylece
            # okunabilirlik animasyona kurban edilmez.
            self._animator.pulse(
                "breath", self, "fg_color",
                (target_fill, mix_colour(target_fill, DARK_BG, 0.10),
                 target_fill), period_ms=1500)
        else:
            self._animator.cancel("breath")

    # ── etkileşim ───────────────────────────────────────────────

    def _interactive(self) -> bool:
        return self.cget("state") == "normal" and not self._loading

    def configure(self, require_redraw: bool = False, **kwargs):
        if "text" in kwargs:
            self._base_text = kwargs["text"]
        result = super().configure(require_redraw=require_redraw, **kwargs)
        if kwargs.keys() & {"state", "hover_color"}:
            self._style()
        return result

    def _watch_pointer(self) -> None:
        """Hover/basılı geri bildirimini metin ve görsel katmanına da bağlar.

        İki incelik var, ikisi de bir kez üretimde kırıldı:

        1. CTkButton yalnızca kendi canvas'ını dinler. Metin etiketi canvas'ın
           ÜZERİNDE durduğu için imleç yazıya geldiğinde olay canvas'a ulaşmaz;
           bu yüzden etikete de bağlanıyoruz.
        2. Handler adları ``CTkButton._on_enter/_on_leave/_on_release`` ile
           çakışmamalı. Daha önce aynı adları kullanıyordum ve taban sınıfın
           metotlarını eziyordum; CTkButton'ın **tıklama komutunu çağıran kod
           tam o metotların içinde** olduğu için düğmeler hiçbir iş yapmıyordu
           (``invoke()`` çalışıyor, gerçek fare tıklaması çalışmıyordu).
        """
        parts = [self._canvas]
        for attribute in ("_text_label", "_image_label"):
            part = getattr(self, attribute, None)
            if part is not None:
                parts.append(part)
        for part in parts:
            key = str(part)
            if key in self._pointer_targets:
                continue
            self._pointer_targets.add(key)
            part.bind("<Enter>", self._pointer_enter, add="+")
            part.bind("<Leave>", self._pointer_leave, add="+")
            part.bind("<ButtonPress-1>", self._pointer_press, add="+")
            part.bind("<ButtonRelease-1>", self._pointer_release, add="+")

    def _pointer_enter(self, _event=None) -> None:
        self._hovered = True
        if self._interactive():
            self._style(animate=True)

    def _pointer_leave(self, _event=None) -> None:
        self._hovered = False
        if self._interactive():
            self._style(animate=True)

    def _pointer_press(self, _event=None) -> None:
        if not self._interactive():
            return
        fill, _border = self._resting()
        _f, hover, _text = self._palette(self._kind, self._accent)
        base = fill or hover or PANEL_BG
        self._animator.colour("press", self, "fg_color",
                              base, mix_colour(base, DARK_BG, 0.28), 70)

    def _pointer_release(self, _event=None) -> None:
        if self._interactive():
            self._style(animate=True)

    def _draw(self, no_color_updates: bool = False):
        super()._draw(no_color_updates)
        # Metin etiketi ilk çizimde oluşur; bağları o an eklemek gerekir.
        self._watch_pointer()


def make_button(master, text: str, kind: str = "primary", **kw) -> FxButton:
    """Kısa yol: tutarlı yükseklik ve köşe yarıçapıyla düğme üretir."""
    kw.setdefault("height", 34)
    kw.setdefault("corner_radius", 10)
    return FxButton(master, text=text, kind=kind, **kw)


def icon_button(master, text: str, kind: str = "outline-muted", **kw) -> FxButton:
    """Kare, sessiz yardımcı düğme (🔄 / ⬆)."""
    kw.setdefault("width", 30)
    kw.setdefault("height", 26)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", ("Inter", 11, "bold"))
    return FxButton(master, text=text, kind=kind, **kw)


def quiet_button(master, text: str, **kw) -> FxButton:
    """Küçük metin düğmesi (Temizle / Kopyala / Yenile)."""
    kw.setdefault("height", 26)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", ("Inter", 11, "bold"))
    return FxButton(master, text=text, kind="outline-muted", **kw)
