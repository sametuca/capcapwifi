#!/usr/bin/env python3
"""Tk smoke test: pencereyi gerçekten açar ve temel davranışları doğrular.

Statik testler (test_gui_imports.py) widget hatalarını yakalayamaz; bu betik
`mainloop()` içinde çalışarak şunları kontrol eder:

  * pencere ekranı dolduracak kadar geniş açılıyor (küçük pencere regresyonu),
  * adım çubuğu ve gömülü konsol sekmesi oluşuyor,
  * handshake yakalamada adım göstergesi sonuca taşınıyor,
  * EN → TR → EN dil değişimi durumu koruyarak traceback üretmeden çalışıyor,
  * konsol sekmesi dil değişiminde de doğru etiketi gösteriyor.

Görüntü sunucusu yoksa testi atlar (exit 0), böylece CI'da güvenli.
"""
import os
import sys
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "gui"))
sys.path.insert(0, GUI_DIR)

import importlib.util

for _mod in ("tkinter", "customtkinter"):
    if importlib.util.find_spec(_mod) is None:
        print(f"  [SKIP] {_mod} yok")
        sys.exit(0)

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") \
        and not os.environ.get("WAYLAND_DISPLAY"):
    print("  [SKIP] Görüntü sunucusu yok (DISPLAY boş)")
    sys.exit(0)

failures = []


def check(condition, message):
    if condition:
        print(f"  [OK] {message}")
    else:
        print(f"  [FAIL] {message}")
        failures.append(message)


original_pref = None
pref_file = None

try:
    import controller
    import i18n
    from models import HandshakeFile

    # Dil değişimi gerçek tercih dosyasına yazar; test sonunda geri koy.
    pref_file = i18n.CONFIG_FILE
    if pref_file.exists():
        original_pref = pref_file.read_text(encoding="utf-8")

    # Ortam taraması gerçek komut çalıştırır; bu test yalnızca arayüzü sınar.
    controller.CapCapWifiController.check_environment = lambda self: None
    controller.CapCapWifiController.list_handshakes = lambda self: []
    controller.CapCapWifiController.check_for_updates = (
        lambda self, *a, **k: None)

    import app as app_module

    window = app_module.CapCapWifiApp()
except Exception:
    traceback.print_exc()
    print("  [FAIL] uygulama oluşturulamadı")
    sys.exit(1)


screenshots = {"lang": [], "width": []}


def step_geometry():
    window.update_idletasks()
    width = window.winfo_width()
    screenshots["width"].append(width)
    check(width >= min(900, window.winfo_screenwidth() - 60),
          f"pencere geniş açıldı (genişlik={width}px)")
    check(getattr(window, "_guide", None) is not None,
          "adım çubuğu oluştu")
    check(getattr(window, "_mode", None) in ("basic", "detail"),
          "basit/detay modu okundu")
    check(getattr(window, "_console_text", None) is not None,
          "gömülü konsol sekmesi oluştu")
    placeholder = window._console_text.get("1.0", "end")
    check("console.empty" not in placeholder and placeholder.strip() != "",
          "konsol sekmesi başlangıç metnini gösteriyor")
    window.after(150, step_mode)


def step_mode():
    """Basit modda ayar paneli gizli, detay modda görünür olmalı."""
    basic = window._mode == "basic"
    # CTkScrollableFrame'in winfo_ismapped() değeri yerleştirilmese de 1
    # dönebiliyor; gerçek ölçüt grid_info().
    check(bool(window._config_panel.grid_info()) == (not basic),
          "basit modda ayar paneli gizli")
    other = "detail" if basic else "basic"
    window._on_mode_selected(i18n.t("mode.detail") if other == "detail"
                             else i18n.t("mode.basic"))
    window.update_idletasks()
    check(window._mode == other, f"mod {other} olarak değişti")
    check(bool(window._config_panel.grid_info()) == (other == "detail"),
          "mod değişiminde panel görünürlüğü güncellendi")
    if window._mode != "basic":
        window._on_mode_selected(i18n.t("mode.basic"))
        window.update_idletasks()
    window.after(150, step_handshake)


portal_starts = []


def step_handshake():
    # Basit modda handshake yakalanınca portal kendiliğinden başlamalı.
    # Gerçek saldırı sürecini başlatmamak için çağrı kaydedilir.
    window._basic_chain = True
    window._start_portal_for_handshake = portal_starts.append
    hf = HandshakeFile(
        filename="TestNet-AA:BB:CC:DD:EE:FF.cap",
        filepath="/tmp/capcapspace/handshakes/TestNet-AA:BB:CC:DD:EE:FF.cap",
        ssid="TestNet",
        bssid="AA:BB:CC:DD:EE:FF",
        size_bytes=20480,
        created_at="2026-10-31 12:00",
    )
    window._on_handshake(hf)
    window.update_idletasks()
    window.after(250, lambda: step_handshake_visible(hf))


def step_handshake_visible(hf):
    check(not hasattr(window, "_next_step_guide"),
          "handshake rehberlik kartı kaldırıldı")
    check(window._step == 4, "adım göstergesi sonuca taşındı")
    log_text = window._log_panel._text.get("1.0", "end")
    check(hf.filepath in log_text, "kaydedilen dosya yolu log panele yazıldı")
    check(portal_starts == [hf], "basit modda handshake sonrası portal tetiklendi")
    window.after(100, step_language_tr)


def step_language_tr():
    window._lang_switch.set("TR")
    window._on_language_selected("TR")
    window.update_idletasks()
    screenshots["lang"].append(i18n.get_language())
    check(i18n.get_language() == "tr", "dil TR'ye geçti")
    check("Başlat" in window._btn_attack.cget("text"),
          "düğme metni Türkçeleşti")
    check("Konsollar" in window._tab_names.get("consoles", ""),
          "konsol sekmesi etiketi Türkçeleşti")
    check(window._console_text.get("1.0", "end").strip() != "",
          "dil değişiminden sonra konsol sekmesi hâlâ dolu")
    window.after(150, step_language_en)


def step_language_en():
    window._lang_switch.set("EN")
    window._on_language_selected("EN")
    window.update_idletasks()
    screenshots["lang"].append(i18n.get_language())
    check(i18n.get_language() == "en", "dil EN'e döndü")
    check("Start" in window._btn_attack.cget("text"),
          "düğme metni İngilizceye döndü")
    check("Consoles" in window._tab_names.get("consoles", ""),
          "konsol sekmesi etiketi İngilizceye döndü")
    window.after(100, step_done)


def step_done():
    try:
        window.destroy()
    except Exception:
        pass

    if pref_file is not None:
        try:
            if original_pref is None:
                pref_file.unlink(missing_ok=True)
            else:
                pref_file.write_text(original_pref, encoding="utf-8")
        except OSError:
            pass


window.after(700, step_geometry)
window.mainloop()

check(screenshots["lang"] == ["tr", "en"], "dil değişimi sıralı tamamlandı")
if failures:
    print(f"\nGUI smoke FAILED ({len(failures)} sorun)")
    sys.exit(1)

print("\nGUI smoke OK")
