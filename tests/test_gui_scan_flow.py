#!/usr/bin/env python3
"""Tara/başlat akışı: düğmeler gerçekten iş yapıyor mu, hata kilitliyor mu?

Kullanıcı "Tara'ya basınca bir şey olmuyor, konsolda hatalar var" dediğinde
ortaya çıkan iki gerçek hata burada kilitleniyor:

1. Motorun koşu döngüsünde bir istisna olursa durum SCANNING'de kalıyordu:
   düğmeler pasif kalıyor, hiçbir iş başlamıyor, kullanıcıya "hiçbir şey
   olmuyor" gibi görünüyordu. Artık bitirme adımları her durumda çalışır.
2. Çalışma alanı izleyicisi izin hatasında sessizce ölüyordu; konsolda
   "Exception in thread" olarak görünüyor ve süreç boyunca hiçbir olay
   gelmiyordu. Artık tur bazında korunuyor.

Pencere açar; görüntü sunucusu yoksa atlar.
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

from pathlib import Path  # noqa: E402

import controller  # noqa: E402
import i18n  # noqa: E402
import updater  # noqa: E402
from models import AttackState, EnvironmentCheck, TargetCandidate  # noqa: E402

failures = 0


def check(label, ok, detail=""):
    global failures
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


# ── 1. tarama hattı (sahte script, gerçek controller) ───────────────
# Tablo basan bir script: gerçek donanım olmadan tüm hattı sınar.
FAKE = Path("/tmp/capcap_scanflow_fake.sh")
FAKE.write_text(
    "#!/usr/bin/env bash\n"
    "sleep 1\n"
    "printf '%-4s %-17s %-4s %-5s %-4s %-10s %-30.30s %s\\n' "
    "CH BSSID PWR STA QLTY ENC VENDOR ESSID\n"
    "printf '%-4s %-17s %-4s %-5s %-4s %-10s %-30.30s %s\\n' "
    "6 AA:BB:CC:DD:EE:01 -42 3 86% WPA2 TP-Link EvimFiber\n"
    "printf '%-4s %-17s %-4s %-5s %-4s %-10s %-30.30s %s\\n' "
    "11 AA:BB:CC:DD:EE:02 -58 0 62% WPA2 Asus KOMSU_5G\n"
    "exit 0\n",
    encoding="utf-8",
)
FAKE.chmod(0o755)

# Yalnızca yan etkisi olan çağrıları sabitliyoruz; taranan iş akışı gerçek.
controller.SCRIPT = FAKE
controller.CapCapWifiController.check_environment = lambda self, *a, **k: None
controller.CapCapWifiController.list_handshakes = lambda self: []
controller.CapCapWifiController.list_interfaces = lambda self: []
controller.CapCapWifiController.console_windows = lambda self: []
controller.CapCapWifiController.capture_console = lambda self, i: ""
controller.CapCapWifiController.list_portals = lambda self: []
updater.check_for_update = lambda *a, **k: None

i18n.set_language("tr")

import app as app_module  # noqa: E402

app_errors = []
window = app_module.CapCapWifiApp()
window.report_callback_exception = (
    lambda exc_type, exc, tb: app_errors.append(f"{exc_type.__name__}: {exc}"))


def step_scan():
    try:
        window.update_idletasks()
        window.update()

        check("uygulama oluşturuldu", window._state is AttackState.IDLE)
        check("Tara düğmesi basılabilir",
              window._btn_scan.cget("state") == "normal")

        # Gerçek tıklama: düğmenin kendi komutu.
        window._btn_scan.invoke()
        window.update_idletasks()
        window.update()

        check("tarama durumu SCANNING'e geçti",
              window._state is AttackState.SCANNING, window._state.value)
        check("tarama sırasında Tara pasif",
              window._btn_scan.cget("state") == "disabled")
        check("tarama sırasında düğme meşgul görünümünde",
              window._btn_scan.loading)
        log_text = window._log_panel._text.get("1.0", "end")
        check("log paneli tarama başlangıcını yazdı",
              t_scan_started(log_text), log_text[-160:])
    except Exception:
        traceback.print_exc()
        check("tarama adımı istisna atmadı", False)

    # Sahte script ~1 sn sürüyor; sonucu bekle.
    window.after(600, step_wait)


def t_scan_started(log_text: str) -> bool:
    return i18n.t("log.iface_auto") in log_text or "Tarama" in log_text


def step_wait(attempt: int = 0):
    window.update()
    if window._state is AttackState.SCANNING and attempt < 25:
        window.after(400, lambda: step_wait(attempt + 1))
        return
    step_result()


def step_result():
    try:
        check("tarama kendini kapattı (kilitlenmedi)",
              window._state is not AttackState.SCANNING, window._state.value)
        check("Tara düğmesi yeniden basılabilir",
              window._btn_scan.cget("state") == "normal")
        check("Tara düğmesi meşgul görünümünden çıktı",
              not window._btn_scan.loading)
        check("başlat düğmesi yeniden basılabilir",
              window._btn_attack.cget("state") == "normal")

        rows = len(window._net_table._rows)
        check("taranan ağlar tabloya geldi", rows == 2, f"rows={rows}")
        check("adım göstergesi hedefe ilerledi", window._step == 2,
              str(window._step))
        check("ağlar sekmesi açık", window._active_tab == "networks",
              window._active_tab)

        # Seçim yapılabilmeli ve özet kartı dolmalı.
        cands = window._net_table.candidates
        if cands:
            window._net_table._select(cands[0])
            window.update()
            check("seçim hedefi ayarladı",
                  window._settings.bssid() == cands[0].bssid,
                  window._settings.bssid())
    except Exception:
        traceback.print_exc()
        check("sonuç adımı istisna atmadı", False)
    window.after(150, step_empty_scan)


def step_empty_scan():
    """Ağ bulunamayan tarama kullanıcıya nedenini söylemeli."""
    try:
        empty = Path("/tmp/capcap_scanflow_empty.sh")
        empty.write_text("#!/usr/bin/env bash\nsleep 1\nexit 0\n", encoding="utf-8")
        empty.chmod(0o755)
        controller.SCRIPT = empty
        window._btn_scan.invoke()

        for _ in range(20):
            window.update()
            if window._state is not AttackState.SCANNING:
                break
            window.after(300)
            window.update()

        window.update_idletasks()
        window.update()
        check("boş tarama da sonuçlandı",
              window._state is AttackState.STOPPED, window._state.value)
        hint = window._net_table._hint.cget("text")
        check("boş taramada tablo yönlendirme veriyor",
              hint == i18n.t("networks.empty_after_scan"), hint[:100])
        log_text = window._log_panel._text.get("1.0", "end")
        check("boş taramada log sonraki adımı söylüyor",
              "Detaylar" in log_text or "Details" in log_text,
              log_text[-160:])
        try:
            empty.unlink()
        except OSError:
            pass
    except Exception:
        traceback.print_exc()
        check("boş tarama senaryosu istisna atmadı", False)
    window.after(150, step_crash_lock)


def step_crash_lock():
    """Motor döngüsü patlarsa arayüz kilitlenmemeli."""
    try:
        window._settings.set_target(None)
        original = controller.CapCapWifiController._handle_status_line

        def boom(self, line, mode):
            raise ValueError("simulated parse crash")

        controller.CapCapWifiController._handle_status_line = boom
        try:
            window._btn_scan.invoke()
            for _ in range(14):
                window.update()
                if window._state is not AttackState.SCANNING:
                    break
                window.after(250)
                window.update()
        finally:
            controller.CapCapWifiController._handle_status_line = original

        check("bozuk durum satırı arayüzü kilitlemedi",
              window._state is not AttackState.SCANNING, window._state.value)
        check("hata sonrası Tara yeniden basılabilir",
              window._btn_scan.cget("state") == "normal")
        log_text = window._log_panel._text.get("1.0", "end")
        check("bozuk satır loglandı",
              i18n.t("ctrl.error.parse", error="")[:12] in log_text
              or "atlandı" in log_text, log_text[-200:])
    except Exception:
        traceback.print_exc()
        check("kilitlenme senaryosu istisna atmadı", False)
    window.after(150, step_immediate_exit)


def step_immediate_exit():
    """Süreç hiç çıktı vermeden ölürse (sudo parola istiyor) kilitlenmemeli."""
    import subprocess

    original = subprocess.Popen

    class Dead:
        returncode = 1
        pid = 999999

        def __init__(self):
            self.stdout = _EmptyStream()

        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

    class _EmptyStream:
        def __iter__(self):
            return iter(())

        def peek(self, n=1):
            return b""

    def fake_popen(*a, **k):
        return Dead()

    try:
        subprocess.Popen = fake_popen
        window._btn_scan.invoke()
        for _ in range(10):
            window.update()
            if window._state is not AttackState.SCANNING:
                break
            window.after(200)
            window.update()
    finally:
        subprocess.Popen = original

    check("çıktısız ölen süreç arayüzü kilitlemedi",
          window._state is not AttackState.SCANNING, window._state.value)
    check("çıktısız ölümde durum hata",
          window._state is AttackState.ERROR, window._state.value)
    log_text = window._log_panel._text.get("1.0", "end")
    check("çıktısız ölümde root ipucu verildi",
          "sudo" in log_text and ("root" in log_text.lower()
                                  or "parola" in log_text
                                  or "password" in log_text),
          log_text[-200:])
    window.after(150, finish)


def finish():
    global window
    try:
        check("arayüz callback'i istisna sızdırmadı", not app_errors,
              "; ".join(app_errors[:3]))
    finally:
        try:
            window.destroy()
        except Exception:
            pass
        try:
            FAKE.unlink()
        except OSError:
            pass


window.after(700, step_scan)
window.mainloop()

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nScan flow OK")
