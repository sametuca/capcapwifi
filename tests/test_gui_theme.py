#!/usr/bin/env python3
"""Palet, kontrast ve düğme durumlarının statik doğrulaması (görüntü gerekmez).

Kullanıcı geri bildirimi "tuş renkleri ve yazılar okunaklı olsun, pasif tuşlar
daha iyi görünsün" idi. Bu test o isteği ölçülebilir hâle getirir:

  * her metin/zemin çifti WCAG AA (4.5:1) veya üstünü geçer,
  * vurgu dolgularının üzerine beyaz yazılmaz,
  * pasif düğme kendi rengini korur (griye dönmez) ama söner,
  * meşgul düğme pasif düğmeden ayırt edilebilir ve okunur kalır.
"""
import os
import sys
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"
sys.path.insert(0, str(GUI_DIR))

import theme  # noqa: E402

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"  [OK] {label}")
    else:
        failures += 1
        print(f"  [FAIL] {label}" + (f"  ->  {detail}" if detail else ""))


AA = 4.5

# ── metin/zemin çiftleri ────────────────────────────────────────────
SURFACES = {
    "DARK_BG": theme.DARK_BG,
    "CHROME_BG": theme.CHROME_BG,
    "PANEL_BG": theme.PANEL_BG,
    "CARD_BG": theme.CARD_BG,
    "CARD_HOVER": theme.CARD_HOVER,
    "CARD_SEL": theme.CARD_SEL,
    "ELEV_BG": theme.ELEV_BG,
    "OFF_BG": theme.OFF_BG,
}

TEXT_TOKENS = {
    "TEXT_PRI": theme.TEXT_PRI,
    "TEXT_SEC": theme.TEXT_SEC,
    "MUTED": theme.MUTED,
    "OFF_TEXT": theme.OFF_TEXT,
}

for text_name, text_colour in TEXT_TOKENS.items():
    worst = min(theme.contrast_ratio(text_colour, bg)
                for bg in SURFACES.values())
    check(f"{text_name} okunur (en kötü {worst:.2f}:1 ≥ {AA})", worst >= AA,
          f"{worst:.2f}")

# Vurgu renkleri metin olarak da kullanılıyor (rozet, bağlantı, etiket).
for name in ("ACCENT", "ACCENT2", "WARN", "DANGER"):
    colour = getattr(theme, name)
    worst = min(theme.contrast_ratio(colour, bg) for bg in SURFACES.values())
    check(f"{name} metin olarak okunur (en kötü {worst:.2f}:1)", worst >= AA,
          f"{worst:.2f}")

# ── vurgu dolguları: üzerine yazılan metin ──────────────────────────
for name in ("ACCENT", "ACCENT2", "WARN", "DANGER"):
    fill = getattr(theme, name)
    on = getattr(theme, f"{name}_ON")
    ratio = theme.contrast_ratio(on, fill)
    check(f"{name}_ON / {name} okunur ({ratio:.2f}:1 ≥ {AA})", ratio >= AA,
          f"{ratio:.2f}")

    hover = getattr(theme, f"{name}_DK")
    hover_ratio = theme.contrast_ratio(on, hover)
    check(f"{name}_ON / {name}_DK okunur ({hover_ratio:.2f}:1)", hover_ratio >= AA,
          f"{hover_ratio:.2f}")

    dim = getattr(theme, f"{name}_DIM")
    dim_ratio = theme.contrast_ratio(fill, dim)
    check(f"{name} / {name}_DIM okunur ({dim_ratio:.2f}:1)", dim_ratio >= AA,
          f"{dim_ratio:.2f}")

# Eski tasarımın hatası: açık vurgu üzerine beyaz yazmak.
for name in ("ACCENT", "ACCENT2", "WARN", "DANGER"):
    fill = getattr(theme, name)
    white_ratio = theme.contrast_ratio("#FFFFFF", fill)
    check(f"{name} üzerine beyaz yazılmıyor ({white_ratio:.2f}:1 < {AA})",
          white_ratio < AA, f"{white_ratio:.2f}")

# ── renk matematiği ─────────────────────────────────────────────────
check("mix_colour kimlik döndürür",
      theme.mix_colour(theme.ACCENT, theme.ACCENT, 0.5) == theme.ACCENT)
check("mix_colour 0 = first, 1 = second",
      theme.mix_colour("#000000", "#FFFFFF", 0.0) == "#000000"
      and theme.mix_colour("#000000", "#FFFFFF", 1.0) == "#FFFFFF")
check("mix_colour kırpar", theme.mix_colour("#FF0000", "#000000", 5.0)
      == "#000000")
check("transparent renk sayılmaz", not theme.is_colour("transparent"))
check("kısa hex sayılmaz", not theme.is_colour("#FFF"))
check("tuple sayılmaz", not theme.is_colour(("#FFFFFF", "#000000")))
check("kontrast aynı renkte 1:1",
      abs(theme.contrast_ratio("#123456", "#123456") - 1.0) < 0.001)
check("kontrast simetrik",
      abs(theme.contrast_ratio(theme.ACCENT, theme.DARK_BG)
          - theme.contrast_ratio(theme.DARK_BG, theme.ACCENT)) < 0.001)
check("siyah/beyaz 21:1",
      abs(theme.contrast_ratio("#000000", "#FFFFFF") - 21.0) < 0.01)
check("readable_on açık zeminde koyu seçer",
      theme.readable_on("#F0F0F0") == theme.ACCENT_ON)
check("readable_on koyu zeminde açık seçer",
      theme.readable_on("#101010") == theme.TEXT_PRI)

# ── pasif düğme kimliği ─────────────────────────────────────────────
for name in ("ACCENT", "ACCENT2", "WARN", "DANGER"):
    fill = getattr(theme, name)
    off_bg, off_border = theme.disabled_pair(fill, theme.CARD_BG)
    text_ratio = theme.contrast_ratio(theme.OFF_TEXT, off_bg)
    check(f"pasif {name} etiketi okunur ({text_ratio:.2f}:1)", text_ratio >= AA,
          f"{text_ratio:.2f}")

    # Kimlik kenarlıkta yaşar: kenarlık zeminden ayrılmalı (≥3:1) ki düğme
    # hangi eylem olduğunu söylesin.
    border_ratio = theme.contrast_ratio(off_border, theme.PANEL_BG)
    check(f"pasif {name} kenarlığı görünür ({border_ratio:.2f}:1 ≥ 3)",
          border_ratio >= 3.0, f"{border_ratio:.2f}")

    # Kenarlık hâlâ kendi rengini taşımalı (saf gri değil).
    r = int(off_border[1:3], 16)
    g = int(off_border[3:5], 16)
    b = int(off_border[5:7], 16)
    spread = max(r, g, b) - min(r, g, b)
    check(f"pasif {name} kenarlığı rengini koruyor (kanal farkı {spread} ≥ 6)",
          spread >= 6, off_border)

    # Pasif düğme normal düğmeden belirgin biçimde sönük olmalı.
    dimmer = theme.contrast_ratio(fill, theme.CARD_BG) > theme.contrast_ratio(
        off_bg, theme.CARD_BG)
    check(f"pasif {name} normalden sönük", dimmer)

    # Dolgu nötr olmalı: pasif düğme renkli bir blok gibi görünmemeli.
    check(f"pasif {name} dolgusu nötr", off_bg == theme.OFF_BG, off_bg)

# ── düğme durumları (customtkinter gerekmez: formüller theme içinde) ──
for kind, (fill, hover, text) in theme.FILL_KINDS.items():
    normal = theme.contrast_ratio(text, fill)
    check(f"{kind} normal okunur ({normal:.2f}:1)", normal >= AA, f"{normal:.2f}")

    busy_fill, _busy_border, busy_text = theme.loading_palette(kind)
    busy = theme.contrast_ratio(busy_text, busy_fill)
    check(f"{kind} meşgul okunur ({busy:.2f}:1)", busy >= AA, f"{busy:.2f}")

    disabled_fill = theme.disabled_pair(fill, theme.CARD_BG)[0]
    disabled = theme.contrast_ratio(theme.OFF_TEXT, disabled_fill)
    check(f"{kind} pasif okunur ({disabled:.2f}:1)", disabled >= AA,
          f"{disabled:.2f}")

    # Meşgul düğme pasiften ayrılmalı: aynı görünmemeli.
    check(f"{kind} meşgul ≠ pasif", busy_fill != disabled_fill)

    # Meşgul dolgu hâlâ canlı olmalı: nötr griye düşmemeli.
    saturation = (max(theme.hex_to_rgb(busy_fill))
                  - min(theme.hex_to_rgb(busy_fill)))
    check(f"{kind} meşgul dolgusu canlı (kanal farkı {saturation} ≥ 20)",
          saturation >= 20, busy_fill)

for kind, accent in theme.OUTLINE_KINDS.items():
    normal = theme.contrast_ratio(accent, theme.PANEL_BG)
    check(f"{kind} normal okunur ({normal:.2f}:1)", normal >= AA, f"{normal:.2f}")

    busy_fill, _busy_border, busy_text = theme.loading_palette(kind)
    busy = theme.contrast_ratio(busy_text, busy_fill)
    check(f"{kind} meşgul okunur ({busy:.2f}:1)", busy >= AA, f"{busy:.2f}")

    off = theme.contrast_ratio(theme.OFF_TEXT, theme.disabled_pair(accent)[0])
    check(f"{kind} pasif okunur ({off:.2f}:1)", off >= AA, f"{off:.2f}")

    check(f"{kind} kimlik rengi doğru", theme.kind_accent(kind) == accent)

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nGUI theme OK")
