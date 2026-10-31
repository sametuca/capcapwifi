#!/usr/bin/env python3
"""Güncelleme modalının davranış testi (pencere açar, görüntü gerekir).

Kullanıcı şikâyeti: güncelleme sırasında uygulama kilitlenmiyordu. Şerit
yalnızca iki log satırı basıyor, kullanıcı altındaki arayüzle saldırı
başlatmaya devam edebiliyor ve güncelleme bitince "yeniden başlat" uyarısı
kapatılıp eski kodla çalışmaya devam ediliyordu.

Bu test sözleşmeyi gerçek widget'lar üzerinde doğrular:

  * güncelleme başlayınca pencerenin tamamını kaplayan bir katman çıkıyor ve
    Tk'nin girdi kilidini (``grab_current``) elinde tutuyor,
  * ilerleme çubuğu var ve gerçek adım eşiklerine doğru ilerliyor,
  * başarıda kapatma yolu yok: Escape ve pencere kapatma isteği katmanı
    kaldırmıyor,
  * "Yeniden başlat" gerçekten yeniden başlatma kancasını çağırıyor
    (``os.execv`` taklit edilir, süreç gerçekten değiştirilmez),
  * hata durumunda kullanıcı kilitli kalmıyor ve hata metni görünüyor,
  * güncelleme metinlerinin hiçbirinde "GitHub" geçmiyor.

Görüntü sunucusu yoksa testi atlar (exit 0).
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

os.environ.setdefault("CAPCAP_ALLOW_NONROOT", "1")

import customtkinter as ctk  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

import app as app_module  # noqa: E402
import controller  # noqa: E402
import i18n  # noqa: E402
import updater  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


# ── 0. statik: güncelleme metinlerinde marka adı yok ────────────────
# Kullanıcı "artık GitHub'dan bahsetmeyin" dedi; kullanıcıya görünen
# güncelleme metinlerinin hiçbiri markayı taşımamalı.
branded = sorted(
    key for key in set(i18n.EN) | set(i18n.TR)
    if key.startswith("update.")
    and ("github" in i18n.EN.get(key, "").lower()
         or "github" in i18n.TR.get(key, "").lower())
)
check("hiçbir update.* metni GitHub adını geçmiyor", not branded,
      ", ".join(branded))

# ── 1. sahte ortam: ağ/komut çalıştırmayan denetleyici ──────────────
controller.CapWifiController.check_environment = lambda self, *a, **k: None
controller.CapWifiController.list_handshakes = lambda self: []
controller.CapWifiController.list_interfaces = lambda self: []
controller.CapWifiController.console_windows = lambda self: []
controller.CapWifiController.capture_console = lambda self, i: ""
controller.CapWifiController.list_portals = lambda self: []
updater.check_for_update = lambda *a, **k: None

i18n.set_language("tr")

app_errors = []
window = None


def pump(seconds: float) -> None:
    """Olay döngüsünü gerçekten çalıştır (after/thread callback'leri için)."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            window.update()
        except Exception:
            return
        time.sleep(0.02)


def wait_for(predicate, timeout: float = 8.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        pump(0.05)
    return predicate()


def overlay():
    return getattr(window, "_update_overlay", None)


def texts_of(widget, kind=None):
    """Katman ağacındaki düğme/etiket metinleri."""
    found = []

    def walk(node):
        for child in node.winfo_children():
            if kind is None or isinstance(child, kind):
                try:
                    value = child.cget("text")
                except Exception:
                    value = ""
                if isinstance(value, str) and value:
                    found.append((child, value))
            walk(child)

    walk(widget)
    return found


def buttons_of(widget):
    return [b for b, _text in texts_of(widget, ctk.CTkButton)]


# ── 2. başarılı güncelleme: kilit + ilerleme + zorunlu yeniden başlatma ──
def scenario_success(w):
    steps_seen = []
    execv_calls = []

    def fake_apply(on_progress=None):
        # Gerçek git çağrısı yerine aynı geri bildirim sırasını üret.
        # UPDATE_STEPS girdileri (i18n anahtarı, yüzde) sırasındadır.
        for key, pct in updater.UPDATE_STEPS:
            steps_seen.append(pct)
            if on_progress:
                on_progress(pct, key)
            time.sleep(0.1)
        return updater.UpdateStatus(is_repo=True, ok=True, behind=0,
                                    local="abc1234", remote="abc1234")

    def fake_execv(path, argv):
        execv_calls.append((path, list(argv)))
        # Gerçekten exec etmiyoruz; süreç devam etsin ki testler koşsun.

    updater.apply_update = fake_apply
    app_module.messagebox.askyesno = lambda *a, **k: True
    app_module.os.execv = fake_execv

    w._do_update()
    pump(0.4)

    ov = overlay()
    check("güncelleme başlayınca modal katman açıldı", ov is not None)
    if ov is None:
        return

    check("katman pencerenin tamamını kaplıyor",
          ov.frame.winfo_ismapped() == 1
          and ov.frame.winfo_width() >= w.winfo_width() - 2
          and ov.frame.winfo_height() >= w.winfo_height() - 2,
          f"{ov.frame.winfo_width()}x{ov.frame.winfo_height()} "
          f"pencere {w.winfo_width()}x{w.winfo_height()}")
    check("girdi kilidi katmanda (grab_set)",
          w.grab_current() == ov.frame, str(w.grab_current()))
    check("kart pencerenin ortasında",
          abs((ov.card.winfo_rootx() + ov.card.winfo_width() // 2)
              - (w.winfo_rootx() + w.winfo_width() // 2)) < 40
          and abs((ov.card.winfo_rooty() + ov.card.winfo_height() // 2)
                  - (w.winfo_rooty() + w.winfo_height() // 2)) < 60,
          f"kart orta noktası {ov.card.winfo_rootx() + ov.card.winfo_width() // 2},"
          f"{ov.card.winfo_rooty() + ov.card.winfo_height() // 2}")

    bar = ov.progress
    check("ilerleme çubuğu widget'ı var",
          isinstance(bar, ctk.CTkProgressBar), str(type(bar)))
    check("çubuk geçerli bir değerde", 0.0 <= float(bar.get()) <= 1.0,
          str(bar.get()))
    check("durum satırı bir adım metni gösteriyor",
          ov.status_label.cget("text").strip() != "",
          ov.status_label.cget("text"))
    check("'kilitli' bilgisi kullanıcıya gösteriliyor",
          ov.body_label.cget("text").strip() != "",
          ov.body_label.cget("text"))

    ok = wait_for(lambda: ov.state == ov.SUCCESS, 12.0)
    check("güncelleme tamamlanınca başarı durumuna geçti", ok,
          f"state={ov.state} hatalar={app_errors[:2]}")
    check("gerçek adımlar sırayla bildirildi",
          steps_seen == [pct for _key, pct in updater.UPDATE_STEPS],
          str(steps_seen))
    check("çubuk sonunda dolu", float(bar.get()) > 0.99, str(bar.get()))

    # ── başarı: kaçış yok ──────────────────────────────────────────
    # Yalnızca düğmeler sayılır: customtkinter düğmeleri metni kendi iç
    # etiketlerinde tuttuğu için tüm ağacı gezmek aynı metni iki kez sayar.
    buttons = buttons_of(ov.actions)
    action_texts = [b.cget("text") for b in buttons]
    dismiss_words = ("sonra", "later", "vazgeç", "kapat", "close", "iptal",
                     "cancel")
    has_dismiss = any(
        any(word in text.lower() for word in dismiss_words)
        for text in action_texts
    )
    check("başarı ekranında kapat/vazgeç düğmesi yok", not has_dismiss,
          str(action_texts))
    check("başarı ekranında tek eylem düğmesi var", len(action_texts) == 1,
          str(action_texts))
    check("başarı ekranında yeniden başlatma uyarısı var",
          "başlat" in (ov.title_label.cget("text")
                       + ov.body_label.cget("text")).lower(),
          ov.title_label.cget("text"))

    # Escape katmanı kaldırmamalı.
    for target in (ov.frame, w):
        try:
            target.event_generate("<Escape>")
        except Exception:
            pass
    pump(0.3)
    check("Escape başarı ekranını kapatmıyor",
          overlay() is not None and overlay().state == ov.SUCCESS,
          str(overlay() and overlay().state))

    # Pencere kapatma isteği de katmanı kaldırmamalı.
    try:
        w.tk.call(w.protocol("WM_DELETE_WINDOW"))
    except Exception:
        pass
    pump(0.3)
    check("pencere kapatma isteği başarı ekranını kaldırmıyor",
          overlay() is not None, "katman kayboldu")
    check("başarı ekranında da grab korunuyor",
          overlay() is not None and w.grab_current() == overlay().frame,
          str(w.grab_current()))

    buttons = buttons_of(ov.actions)
    check("yeniden başlat düğmesi bulundu", len(buttons) == 1,
          str([b.cget("text") for b in buttons]))
    if buttons:
        buttons[0].invoke()
    pump(0.3)
    check("yeniden başlat düğmesi os.execv'yi çağırdı", execv_calls != [],
          str(execv_calls))
    check("execv çalışan Python ile yeniden başlatıyor",
          bool(execv_calls) and execv_calls[0][0] == sys.executable,
          str(execv_calls[:1]))
    check("execv argv bu betiği taşıyor",
          bool(execv_calls)
          and any("test_gui_update_modal" in a for a in execv_calls[0][1]),
          str(execv_calls[:1]))


# ── 3. başarısız güncelleme: kullanıcı kilitli kalmıyor ─────────────
def scenario_failure(w):
    if overlay() is not None:
        w._close_update_overlay()

    def failing_apply(on_progress=None):
        if on_progress:
            on_progress(10, "update.step.check")
        raise RuntimeError("simulated git failure")

    updater.apply_update = failing_apply
    w._do_update()
    pump(0.4)
    ov = overlay()
    check("ikinci güncellemede katman yeniden açıldı", ov is not None)
    if ov is None:
        return

    ok = wait_for(lambda: ov.state == ov.FAILED, 8.0)
    check("hata durumuna geçti", ok, f"state={ov.state}")
    detail = ov.status_label.cget("text")
    check("hata metni gösteriliyor",
          "failure" in detail.lower() or "başarısız" in detail.lower(), detail)
    check("hata durumunda grab bırakıldı", w.grab_current() is None,
          str(w.grab_current()))

    action_texts = [text for _b, text in texts_of(ov.actions)]
    joined = " | ".join(action_texts).lower()
    check("hata ekranında çıkış yolu var",
          any(word in joined for word in ("kapat", "quit", "close")), joined)
    check("hata ekranında yeniden deneme var",
          any(word in joined for word in ("dene", "retry", "again")), joined)

    buttons = buttons_of(ov.actions)
    quit_buttons = [b for b in buttons
                    if any(word in b.cget("text").lower()
                           for word in ("kapat", "quit", "close"))]

    # "Kapat" gerçekten uygulamayı kapatır, bu yüzden en sona bırakıldı:
    # önce yeniden deneme yolunu doğrulayalım.
    calls = []

    def retry_apply(on_progress=None):
        calls.append(1)
        return updater.UpdateStatus(is_repo=True, ok=False,
                                    message="still failing")

    updater.apply_update = retry_apply
    w._retry_update()
    pump(0.5)
    check("yeniden deneme işi tekrar başlattı", len(calls) == 1, str(calls))
    wait_for(lambda: overlay() is not None and overlay().state == "failed", 6.0)
    check("yeniden deneme de hata durumunda kaldı",
          overlay() is not None and overlay().state == "failed",
          str(overlay() and overlay().state))
    if overlay() is not None:
        w._dismiss_failed_update()
    pump(0.2)
    check("yeniden denemeden sonra da çıkış mümkün", overlay() is None)


# ── 4. ekran görüntüleri ────────────────────────────────────────────
def capture(name):
    import shutil
    import subprocess

    path = f"/tmp/{name}.png"
    ffmpeg = shutil.which("ffmpeg")
    display = os.environ.get("DISPLAY", ":1")
    if not ffmpeg:
        return path, False
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    wpx = window.winfo_width()
    hpx = window.winfo_height()
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "x11grab",
         "-video_size", f"{wpx}x{hpx}", "-i", f"{display}+{x},{y}",
         "-frames:v", "1", path],
        capture_output=True,
    )
    return path, os.path.exists(path)


def scenario_screenshots(w):
    if overlay() is not None:
        w._close_update_overlay()

    def slow_apply(on_progress=None):
        for key, pct in updater.UPDATE_STEPS:
            if on_progress:
                on_progress(pct, key)
            time.sleep(0.8)
        return updater.UpdateStatus(is_repo=True, ok=True, behind=0,
                                    local="abc1234", remote="abc1234")

    updater.apply_update = slow_apply
    app_module.os.execv = lambda *a, **k: None
    w._do_update()
    pump(1.1)

    path, ok = capture("update_progress")
    check("ilerleme ekran görüntüsü alındı", ok, path)

    wait_for(lambda: overlay() is not None and overlay().state == "success", 14.0)
    pump(0.5)
    path2, ok2 = capture("update_done")
    check("bitiş ekran görüntüsü alındı", ok2, path2)


# ── 4b. hata ekranındaki "Kapat" kullanıcıyı uygulamaya döndürüyor mu? ──
def scenario_close_button(w):
    """Kapat düğmesi katmanı kaldırıp uygulamayı kullanılabilir bırakıyor mu?

    Başarısız güncelleme kullanıcıyı uygulamadan koparmamalı: "Kapat" tam
    olarak "eski sürümle devam et" demektir, süreci öldürmek değil.
    """
    # Önceki senaryo başarı ekranında bitiyor; kapatma kilidi açık olduğu
    # için yeni bir güncelleme başlatılamaz. Test kurulumu olarak kaldır.
    if overlay() is not None:
        w._close_update_overlay()
    updater.apply_update = lambda on_progress=None: updater.UpdateStatus(
        is_repo=True, ok=False, message="boom")
    w._do_update()
    pump(0.4)
    ov = overlay()
    check("hata ekranı açıldı (kapat testi)", ov is not None)
    if ov is None:
        return
    wait_for(lambda: ov.state == ov.FAILED, 6.0)

    buttons = buttons_of(ov.actions)
    quit_buttons = [b for b in buttons
                    if any(word in b.cget("text").lower()
                           for word in ("kapat", "quit", "close"))]
    check("çıkış düğmesi bulundu (kapat testi)", bool(quit_buttons),
          str([b.cget("text") for b in buttons]))
    if quit_buttons:
        quit_buttons[0].invoke()
    pump(0.4)
    check("çıkış düğmesi katmanı kaldırdı (kapat testi)", overlay() is None)
    alive = True
    try:
        alive = bool(w.winfo_exists())
    except Exception:
        alive = False
    check("çıkış düğmesi uygulamayı kapatmadı (eski sürümle devam)", alive)
    # Kilit tamamen kalktı mı? Uygulama yeniden kullanılabilir olmalı.
    check("kilit tamamen kalktı (grab yok)", w.grab_current() is None,
          str(w.grab_current()))
    check("dil değişimi yeniden çalışıyor",
          (w._apply_language("en"), i18n.get_language())[1] == "en",
          i18n.get_language())


# ── 5. çalıştır ────────────────────────────────────────────────────
# Test gövdesi mainloop İÇİNDE koşmalı: güncelleme işi bir thread'de
# çalışıyor ve sonucu ``after(0, ...)`` ile ana iş parçacığına taşıyor.
# mainloop aktif değilken bu çağrı "main thread is not in main loop"
# hatası verir, yani gerçek uygulama akışını taklit etmemiş oluruz.
def run_all():
    try:
        scenario_success(window)
        scenario_failure(window)
        scenario_screenshots(window)

        if app_errors:
            check("Tk callback hatası sızmadı", False, "; ".join(app_errors[:3]))
        else:
            check("Tk callback hatası sızmadı", True)

        scenario_close_button(window)
    except Exception:
        traceback.print_exc()
        check("test akışı hatasız tamamlandı", False, "traceback yukarıda")
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


try:
    window = app_module.CapWifiApp()
    window.report_callback_exception = (
        lambda t, v, tb: app_errors.append(f"{t.__name__}: {v}"))
    window.geometry("1180x780+40+40")
    window.after(600, run_all)
    window.mainloop()
except Exception:
    traceback.print_exc()
    check("uygulama oluşturulamadı", False, "traceback yukarıda")

if failures:
    print(f"\n{failures} check(s) failed: " + "; ".join(failures))
    sys.exit(1)
print("\nGüncelleme modalı OK")
