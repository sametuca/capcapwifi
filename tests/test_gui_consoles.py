#!/usr/bin/env python3
"""Gömülü konsollar: çok panelli ızgara gerçekten doluyor mu?

Kullanıcı şikâyeti: "konsollar gömülü gelmiyor". Konsollar sekmesi vardı ama
boş kalıyordu; tek bir metin kutusu vardı ve hangi pencerenin gösterildiğini
bir açılır listeden seçmek gerekiyordu.

Yeni sözleşme:
  * saldırının açtığı her tmux penceresi için ayrı bir panel (en fazla 4),
  * paneller 2x2 ızgarada **aynı anda** görünür, ölçeklenmiş puntoyla,
  * her panel kendi başlığını ve kendi metnini taşır,
  * pencere yokken anlamlı bir yer tutucu görünür,
  * konsollar belirir belirmez Konsollar sekmesine otomatik geçilir.

Bu ortamda kablosuz donanım yok; controller'ın tmux metotları sahte veriyle
değiştirilerek gerçek çizim yolu sınanıyor.
"""
import os
import sys
import time
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

# Uygulama root ister; bu test root gerektirmeyen arayüz davranışını sınıyor.
os.environ.setdefault("CAPCAP_ALLOW_NONROOT", "1")

import customtkinter as ctk  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

import app as app_module  # noqa: E402
import controller  # noqa: E402
import i18n  # noqa: E402
import updater  # noqa: E402
from models import AttackState  # noqa: E402

i18n.set_language("tr")

failures = 0


def check(label, ok, detail=""):
    global failures
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


# ── sahte tmux pencereleri ──────────────────────────────────────────
WINDOWS = [("0", "portal"), ("1", "dns"), ("2", "deauth"), ("3", "ap")]
BODIES = {
    "0": "portal: waiting for client\r\nGET /index.php 200",
    "1": "dns: spoofing 192.168.254.1",
    "2": "deauth: aireplay-ng --deauth 5",
    "3": "ap: hostapd started on wlan0",
}

_state = {"windows": []}

controller.CapWifiController.check_environment = lambda self, *a, **k: None
controller.CapWifiController.list_handshakes = lambda self: []
controller.CapWifiController.list_interfaces = lambda self: []
controller.CapWifiController.list_portals = lambda self: []
controller.CapWifiController.console_windows = (
    lambda self: list(_state["windows"]))
controller.CapWifiController.capture_console = (
    lambda self, index: BODIES.get(str(index), ""))
updater.check_for_update = lambda *a, **k: None

window = app_module.CapWifiApp()
app_errors = []
window.report_callback_exception = (
    lambda t, v, tb: app_errors.append(f"{t.__name__}: {v}"))


def pane_text(index):
    pane = window._console_panes.get(index)
    if pane is None:
        return None
    try:
        return pane["body"].get("1.0", "end").strip()
    except Exception:
        return None


def drive():
    try:
        window.update_idletasks()
        window.update()
        time.sleep(0.3)
        window.update()

        # ── 1. hiç pencere yokken yer tutucu ────────────────────────
        check("pencere yokken panel oluşmadı",
              not window._console_panes, str(len(window._console_panes)))
        check("pencere yokken yer tutucu görünür",
              window._console_placeholder is not None)

        # ── 2. dört pencere birden ──────────────────────────────────
        _state["windows"] = list(WINDOWS)
        window._update_status(AttackState.RUNNING)
        window._start_console_poll()

        deadline = time.time() + 20
        while time.time() < deadline and len(window._console_panes) < 4:
            window.update()
            time.sleep(0.15)
        window.update()

        check("dört panel de kuruldu", len(window._console_panes) == 4,
              str(len(window._console_panes)))
        check("yer tutucu paneller gelince gizlendi",
              not window._console_placeholder.winfo_ismapped())

        # Başlıklar pencere adını taşımalı.
        titles = {i: window._console_panes[i]["title"].cget("text")
                  for i in window._console_panes}
        check("panel başlıkları pencere adlarını taşıyor",
              all(any(name in str(title) for name in
                      ("portal", "dns", "deauth", "ap"))
                  for title in titles.values()), str(titles))

        # Her panel KENDİ metnini göstermeli (kopyala-yapıştır değil).
        texts = {i: pane_text(i) for i in ("0", "1", "2", "3")}
        check("her panel dolu", all(t and t.strip() for t in texts.values()),
              str(texts))
        check("paneller birbirinin metnini tekrarlamıyor",
              len({t for t in texts.values()}) == 4, str(texts))
        check("portal paneli kendi gövdesini gösteriyor",
              "portal:" in (texts.get("0") or ""), texts.get("0"))

        # 2x2 ızgara: iki satır, iki sütun kullanılmalı.
        cells = {(int(p["frame"].grid_info()["row"]),
                  int(p["frame"].grid_info()["column"]))
                 for p in window._console_panes.values()}
        check("paneller 2x2 ızgaraya yerleşti", cells == {
            (0, 0), (0, 1), (1, 0), (1, 1)}, str(cells))

        # ── 3. otomatik sekme geçişi ────────────────────────────────
        check("konsollar belirince Konsollar sekmesine geçildi",
              window._active_tab == "consoles", window._active_tab)

        # ── 4. pencere kapanınca panel de gider ─────────────────────
        _state["windows"] = list(WINDOWS[:2])
        window._fetch_consoles()
        for _ in range(20):
            window.update()
            if len(window._console_panes) == 2:
                break
            time.sleep(0.15)
        window.update()
        check("ölü pencerelerin panelleri kaldırıldı",
              len(window._console_panes) == 2,
              str(list(window._console_panes)))

        # ── 5. hepsi kapanınca yer tutucu geri gelir ────────────────
        _state["windows"] = []
        window._fetch_consoles()
        for _ in range(20):
            window.update()
            if not window._console_panes:
                break
            time.sleep(0.15)
        window.update()
        check("tüm pencereler kapanınca yer tutucu geri geldi",
              not window._console_panes and window._console_placeholder,
              str(len(window._console_panes)))
    except Exception:
        traceback.print_exc()
        check("konsol senaryosu istisna atmadı", False)
    finally:
        try:
            for _ in range(6):
                window.update()
                time.sleep(0.1)
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass


window.after(900, drive)
window.mainloop()

if app_errors:
    print(f"\nTk callback hataları: {app_errors[:3]}")
    failures += 1

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nConsole grid OK")
