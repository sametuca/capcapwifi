#!/usr/bin/env python3
"""Düğmeler gerçek fare tıklamasına tepki veriyor mu?

Bu testin varlık nedeni somut bir üretim hatası: ``FxButton``, customtkinter'ın
``_on_enter/_on_leave/_on_release`` metotlarını eziyordu. Tıklama komutunu
çağıran kod tam o metotların içinde olduğu için düğmeler **hiçbir iş
yapmıyordu**. Üstelik ``button.invoke()`` çalışmaya devam ettiği için mevcut
testler hatayı yakalamıyordu; kullanıcı "Scan'e basıyorum, hiçbir şey
olmuyor" diyordu.

Ders: bir düğmenin çalıştığını ``invoke()`` ile doğrulamak yetmez. Bu test
gerçek işaretçi tıklaması üretir (mümkünse xdotool ile, değilse Tk'nin kendi
``generate`` yoluyla) ve şunları arar:

  * düğme kendi tıklamasını alıyor mu (``_command`` çağrıldı mı),
  * hover durumu güncelleniyor mu,
  * uygulamadaki "Scan" düğmesi taramayı gerçekten başlatıyor mu.
"""
import os
import shutil
import subprocess
import sys
import time

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

import customtkinter as ctk  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

import app as app_module  # noqa: E402
import controller  # noqa: E402
import i18n  # noqa: E402
import updater  # noqa: E402
from effects import make_button  # noqa: E402
from models import AttackState  # noqa: E402
from theme import DARK_BG  # noqa: E402

XDOTOOL = shutil.which("xdotool")
failures = 0


def check(label, ok, detail=""):
    global failures
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


def real_click(widget, settle=0.45):
    """Widget'ın ortasına gerçek bir tıklama gönder."""
    cx = widget.winfo_rootx() + widget.winfo_width() // 2
    cy = widget.winfo_rooty() + widget.winfo_height() // 2
    if XDOTOOL:
        subprocess.run([XDOTOOL, "mousemove", str(cx), str(cy)],
                       capture_output=True)
        time.sleep(0.25)
        widget.update()
        subprocess.run([XDOTOOL, "click", "1"], capture_output=True)
    else:
        # xdotool yok: sentetik olaylar. Handler'ları çağırdığı için
        # yöntem çakışması hatasını yakalamaya yeter.
        part = getattr(widget, "_text_label", None) or widget._canvas
        x = part.winfo_width() // 2
        y = part.winfo_height() // 2
        part.event_generate("<Enter>", x=x, y=y)
        part.event_generate("<ButtonPress-1>", x=x, y=y)
        part.event_generate("<ButtonRelease-1>", x=x, y=y)
    time.sleep(settle)
    widget.update()


# ── 1. yöntem çakışması denetimi (statik) ───────────────────────────
from effects import FxButton  # noqa: E402

clashing = []
for name in ("_on_enter", "_on_leave", "_on_press", "_on_release"):
    base = getattr(ctk.CTkButton, name, None)
    ours = getattr(FxButton, name, None)
    # Yalnızca taban sınıfta VAR OLAN ve farklı bir fonksiyonla ezilen
    # metotlar sorundur. Tabanda olmayan bir isim çakışma sayılmaz.
    if base is not None and ours is not None and ours is not base:
        clashing.append(name)
check("FxButton, CTkButton'ın tıklama metotlarını ezmiyor", not clashing,
      f"ezilen: {clashing}")

root = ctk.CTk()
root.configure(fg_color=DARK_BG)
root.geometry("460x180+140+140")
hits = []
btn = make_button(root, "Scan", "primary", width=240, height=40,
                  command=lambda: hits.append("fx"))
plain = ctk.CTkButton(root, text="plain", width=240, height=40,
                      command=lambda: hits.append("plain"))
btn.pack(pady=(18, 10))
plain.pack(pady=(0, 12))
root.update_idletasks()
root.update()
time.sleep(0.4)
root.update()

# ── 2. izole düğme: gerçek tıklama komutu çalıştırıyor mu ───────────
real_click(btn)
check("FxButton gerçek tıklamayı alıyor", "fx" in hits, str(hits))
check("FxButton hover durumu güncellendi", getattr(btn, "_hovered", None) is True,
      str(getattr(btn, "_hovered", None)))

hits.clear()
real_click(plain)
check("referans CTkButton de tıklamayı alıyor", "plain" in hits, str(hits))

# Programatik invoke hâlâ çalışmalı (regresyon değil).
hits.clear()
btn.invoke()
check("FxButton.invoke() çalışmaya devam ediyor", hits == ["fx"], str(hits))

# İzole penceriyi de bekleyen işler boşalttıktan sonra kapat.
for _ in range(5):
    root.update()
    time.sleep(0.1)
root.destroy()

# ── 3. gerçek uygulamada Scan düğmesi ───────────────────────────────
from pathlib import Path  # noqa: E402

fake = Path("/tmp/capcap_click_fake.sh")
fake.write_text("#!/usr/bin/env bash\nsleep 1\nexit 0\n", encoding="utf-8")
fake.chmod(0o755)

controller.SCRIPT = fake
controller.CapCapWifiController.check_environment = lambda self, *a, **k: None
controller.CapCapWifiController.list_handshakes = lambda self: []
controller.CapCapWifiController.list_interfaces = lambda self: []
controller.CapCapWifiController.console_windows = lambda self: []
controller.CapCapWifiController.capture_console = lambda self, i: ""
controller.CapCapWifiController.list_portals = lambda self: []
updater.check_for_update = lambda *a, **k: None

i18n.set_language("en")
window = app_module.CapCapWifiApp()
app_errors = []
window.report_callback_exception = (
    lambda t, v, tb: app_errors.append(f"{t.__name__}: {v}"))


def drive():
    try:
        window.update_idletasks()
        window.update()
        time.sleep(0.4)
        window.update()

        check("uygulama açılışta boşta",
              window._state is AttackState.IDLE, window._state.value)

        real_click(window._btn_scan, settle=0.6)
        check("Scan'e gerçek tıklama taramayı başlattı",
              window._state is not AttackState.IDLE, window._state.value)

        # Tarama bitene kadar bekle.
        for _ in range(24):
            window.update()
            if window._state is not AttackState.SCANNING:
                break
            time.sleep(0.3)
            window.update()
        check("tarama kendini kapattı",
              window._state is not AttackState.SCANNING, window._state.value)

        log = window._log_panel._text.get("1.0", "end")
        check("log'da tarama satırı var",
              "Scan starting" in log or "Scan started" in log, log[-140:])

        # Aynı şey Başlat için de geçerli olmalı: hedef yoksa uyarı verir,
        # ama düğme en azından komutu çalıştırmalı.
        window._state = AttackState.IDLE
        window._update_status(AttackState.IDLE)
        before = window._log_panel._text.get("1.0", "end")
        real_click(window._btn_attack, settle=0.6)
        after = window._log_panel._text.get("1.0", "end")
        check("Start düğmesi de komutu çalıştırdı", after != before,
              "log değişmedi")
        check("tıklamalar Tk hatası sızdırmadı", not app_errors,
              "; ".join(app_errors[:3]))
    finally:
        # Kapanıştan önce bekleyen Tk işlerini boşalt: aksi hâlde
        # customtkinter'ın kendi _click_animation/check_dpi_scaling
        # zamanlayıcıları yıkılan pencereye ateş edip "invalid command name"
        # basıyor ve test çıktısını kirletiyor.
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
        try:
            fake.unlink()
        except OSError:
            pass


window.after(900, drive)
window.mainloop()

if not XDOTOOL:
    print("  [i] xdotool yok; sentetik olaylarla test edildi")

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nButton click OK")

# Not: kapanışta customtkinter'ın kendi global zamanlayıcıları
# (check_dpi_scaling gibi) birkaç "invalid command name" satırı basabilir.
# Bunlar pencere yıkımının kaçınılmaz artefaktıdır ve uygulama çalışırken
# oluşmaz (gerçek uygulamada doğrulandı), bu yüzden çıkış kodunu etkilemez.
