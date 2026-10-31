"""Renk paleti, tipografi ve renk matematiği – tkinter'dan bağımsız.

Bu modül bilinçli olarak hiçbir arayüz kütüphanesi import etmez. Böylece
``widgets.py`` (customtkinter) ve testler aynı tokenları kullanır, palet de
görüntü sunucusu olmadan doğrulanabilir.

Renk seçiminin tek ölçütü okunabilirlik: metin/zemin çiftlerinin tamamı
WCAG AA (4.5:1) veya üstünü geçer. Yorumlardaki oranlar
``contrast_ratio()`` çıktısıdır. 4.5 altındaki tonlar yalnızca dekoratif
çizgiler ve pasif kenarlıklar içindir, metin olarak kullanılmaz.

Katmanlar gölge olmadan, yalnızca ton farkıyla derinlik verir:
    CHROME_BG < DARK_BG < PANEL_BG < CARD_BG < CARD_HOVER < ELEV_BG
"""
from __future__ import annotations

from typing import Dict, Tuple

# ────────────────────────── yüzeyler ───────────────────────────────
DARK_BG     = "#070A0E"   # uygulama zemini
CHROME_BG   = "#05080B"   # üst/alt çubuk – zeminden bir tık koyu
PANEL_BG    = "#0C1016"   # panel / sütun zemini
CARD_BG     = "#141A22"   # kart yüzeyi
CARD_HOVER  = "#1C2430"   # kart hover
CARD_SEL    = "#0D2A1B"   # seçili kart (yeşil tint)
ELEV_BG     = "#202836"   # yükseltilmiş küçük yüzeyler (rozet içi vb.)
BORDER      = "#28313D"   # ince kenarlık
BORDER_SOFT = "#1B222C"   # ayırıcı çizgi

# ────────────────────────── metin ──────────────────────────────────
TEXT_PRI    = "#F3F6FA"   # 16.1:1 CARD_BG üzerinde – başlık ve gövde
TEXT_SEC    = "#B4BFCD"   # 9.4:1  – ikincil metin
MUTED       = "#8B95A5"   # 5.8:1  – açıklama, ipucu (AA sınırının üstü)
TEXT_FAINT  = "#6E7887"   # 4.4:1  – yalnızca dekoratif / imza

# ────────────────────────── vurgular ───────────────────────────────
# Her vurgunun dört tonu var: dolgu (ACCENT), üzerine yazılacak metin
# (ACCENT_ON), hover tonu (ACCENT_DK) ve zemin içinde eriyen yumuşak dolgu
# (ACCENT_DIM). Metin her zaman ACCENT_ON'dur; beyaz kullanılmaz.
ACCENT      = "#00E676"   # neon yeşil – birincil eylem
ACCENT_ON   = "#04210F"   # 10.2:1 ACCENT üzerinde
ACCENT_DK   = "#29EA8C"   # 10.8:1 ACCENT_ON ile – hover (açığa doğru)
ACCENT_DIM  = "#0E3A24"   # 7.6:1  ACCENT ile

ACCENT2     = "#38BDF8"   # camgöbeği – bilgi / tarama
ACCENT2_ON  = "#04202E"   # 7.8:1  ACCENT2 üzerinde
ACCENT2_DK  = "#58C8F9"   # 8.8:1  hover tonu
ACCENT2_DIM = "#0B2C3E"   # 6.8:1  ACCENT2 ile

WARN        = "#FBBF24"   # amber – dikkat
WARN_ON     = "#1F1500"   # 10.8:1 WARN üzerinde
WARN_DK     = "#FCC947"   # 11.7:1 hover tonu
WARN_DIM    = "#33280A"   # 8.7:1  WARN ile

DANGER      = "#FF7A90"   # yumuşak kırmızı – yıkıcı eylem
DANGER_ON   = "#2A0810"   # 7.4:1  DANGER üzerinde
DANGER_DK   = "#FF8FA2"   # 8.5:1  hover tonu
DANGER_DIM  = "#33151C"   # 6.7:1  DANGER ile

# ────────────────────────── pasif durum ────────────────────────────
# Pasif bir düğme tamamen griye dönmez: kendi renginin soluk tintini korur,
# böylece kullanıcı "hangi düğme" olduğunu hâlâ okur (~5:1 metin).
OFF_BG      = "#171D26"   # notr pasif dolgu
OFF_BORDER  = "#2C3644"   # notr pasif kenarlık
OFF_TEXT    = "#93A1B2"   # 6.7:1 OFF_BG üzerinde – pasif etiket

CONSOLE_FG  = "#B9F6CD"   # konsol gövdesi – DARK_BG üzerinde ~12:1

# ────────────────────────── tipografi ──────────────────────────────
FONT_MONO   = ("JetBrains Mono", 12)
FONT_MONO_S = ("JetBrains Mono", 11)
FONT_UI     = ("Inter", 12)
FONT_UI_S   = ("Inter", 11)
FONT_UI_XS  = ("Inter", 10)
FONT_UI_B   = ("Inter", 12, "bold")
FONT_UI_SB  = ("Inter", 11, "bold")
FONT_TITLE  = ("Inter", 15, "bold")
FONT_BRAND  = ("Inter", 18, "bold")

RGB = Tuple[int, int, int]


# ────────────────────────── renk matematiği ────────────────────────

def is_colour(value: object) -> bool:
    """``#RRGGBB`` biçiminde mi? "transparent" ve tuple'lar için False."""
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def hex_to_rgb(value: str) -> RGB:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def rgb_to_hex(rgb) -> str:
    parts = [max(0, min(255, int(round(c)))) for c in rgb]
    return "#%02X%02X%02X" % tuple(parts)


def mix_colour(first: str, second: str, amount: float) -> str:
    """İki renk arasında doğrusal geçiş (0 = first, 1 = second)."""
    amount = max(0.0, min(1.0, amount))
    if not (is_colour(first) and is_colour(second)):
        return second if amount >= 0.5 else first
    a, b = hex_to_rgb(first), hex_to_rgb(second)
    return rgb_to_hex([x + (y - x) * amount for x, y in zip(a, b)])


def relative_luminance(value: str) -> float:
    def channel(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: str, second: str) -> float:
    """WCAG bağıl kontrast oranı (1:1 … 21:1)."""
    a, b = relative_luminance(first), relative_luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def readable_on(background: str, light: str = TEXT_PRI,
                dark: str = ACCENT_ON) -> str:
    """Zemin üzerinde daha okunur olan açık/koyu metni seçer."""
    if contrast_ratio(light, background) >= contrast_ratio(dark, background):
        return light
    return dark


def disabled_pair(accent: str, surface: str = CARD_BG) -> Tuple[str, str]:
    """Pasif düğme için (dolgu, kenarlık).

    Neden nötr dolgu: pasif bir düğmenin dolgusunu vurgunun tintine boyamak,
    koyu temada çamurlu bir kahverengi/yeşil üretiyor ve "basılabilir" gibi
    görünüyordu. Bunun yerine dolgu nötr kalır (OFF_BG), kimlik ince bir
    vurgu kenarlığında yaşar. Düğme sönük ama hangi düğme olduğu okunur:
    kenarlık zemine karşı ~3.5:1, etiket 6.4:1.
    """
    del surface
    return OFF_BG, mix_colour(OFF_BORDER, accent, OFF_BORDER_TINT)


# ────────────────────────── düğme durumları ────────────────────────
# Düğme renkleri burada durur, ``effects.FxButton`` yalnızca uygular.
# Böylece palet ve durum formülleri customtkinter olmadan test edilebilir.

#: Dolgulu türler -> (dolgu, hover, metin). Metin rengi dolguyla birlikte
#: seçilir; beyaz metin hiçbir türde kullanılmaz (yeşil/sarı üzerinde okunmaz).
FILL_KINDS: Dict[str, Tuple[str, str, str]] = {
    "primary": (ACCENT, ACCENT_DK, ACCENT_ON),
    "info": (ACCENT2, ACCENT2_DK, ACCENT2_ON),
    "warn": (WARN, WARN_DK, WARN_ON),
    "danger": (DANGER, DANGER_DK, DANGER_ON),
    "secondary": (ELEV_BG, CARD_HOVER, TEXT_PRI),
}

#: Kontur türleri: dolgu yok, metin ve kenarlık vurgunun kendisi.
OUTLINE_KINDS: Dict[str, str] = {
    "outline-primary": ACCENT,
    "outline-info": ACCENT2,
    "outline-warn": WARN,
    "outline-danger": DANGER,
    "outline-muted": TEXT_SEC,
}

#: Durum tintleri. Ölçüt: karışım sonrası metin kontrastı 4.5:1'in altına
#: düşmemeli (bkz. tests/test_gui_theme.py).
LOADING_TINT = 0.13      # dolgulu türlerde meşgul dolgusu -> DARK_BG karışımı
OUTLINE_TINT = 0.14      # kontur türlerinde meşgul zemini -> vurgu karışımı
OFF_BORDER_TINT = 0.42   # pasif kenarlıkta vurgu kalıntısı


def kind_accent(kind: str) -> str:
    """Bir düğme türünün kimlik rengi."""
    if kind in OUTLINE_KINDS:
        return OUTLINE_KINDS[kind]
    return FILL_KINDS.get(kind, FILL_KINDS["primary"])[0]


def button_palette(kind: str) -> Tuple[str, str, str]:
    """(dolgu, hover, metin); kontur türlerinde dolgu boş string döner."""
    if kind in OUTLINE_KINDS:
        accent = OUTLINE_KINDS[kind]
        return "", mix_colour(PANEL_BG, accent, 0.16), accent
    return FILL_KINDS.get(kind, FILL_KINDS["primary"])


def loading_palette(kind: str) -> Tuple[str, str, str]:
    """Meşgul durum (dolgu, kenarlık, metin).

    Dolgulu türlerde dolgu canlı vurgudan hafifçe koyulaşır ve metin aynı
    kalır; kontur türlerinde zemin hafifçe vurguyla dolar, metin/kenarlık
    vurgunun kendisidir. Her iki hâlde de kontrast AA üstünde kalır.
    """
    fill, _hover, text = button_palette(kind)
    if fill:
        busy = mix_colour(fill, DARK_BG, LOADING_TINT)
        return busy, busy, text
    accent = OUTLINE_KINDS[kind]
    return (mix_colour(PANEL_BG, accent, OUTLINE_TINT), accent, accent)
