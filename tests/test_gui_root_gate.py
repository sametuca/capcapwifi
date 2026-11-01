#!/usr/bin/env python3
"""Root kapısı testi: rootsuz uygulama açılmıyor mu?

Neden alt süreç: kapı ``SystemExit`` atıyor. Aynı süreçte yakalamak test
koşucusunu da öldürürdü; bu yüzden her senaryo ayrı bir Python sürecinde
çalışıyor ve yalnızca çıkış kodu + stdout ile geri dönüyor.

Senaryolar
----------
1. root değil, kaçış kapısı kapalı  → uyarı görünür, ana arayüz HİÇ kurulmaz,
   süreç sıfırdan farklı kodla çıkar.
2. root değil, CAPCAP_ALLOW_NONROOT=1 → arayüz normal kurulur (test kaçış kapısı).
3. root (zorlanmış)                   → arayüz normal kurulur.
4. EN ve TR metinleri                 → ikisinde de "sudo ./run_gui.sh" var.

Ek olarak uyarı penceresinin ekran görüntüsünü alır (/tmp/root_gate.png).
"""
import importlib.util
import json
import os
import subprocess
import sys
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "gui"))
sys.path.insert(0, GUI_DIR)

SHOT_PATH = "/tmp/root_gate.png"
COMMAND = "sudo ./run_gui.sh"

failures = []


def check(label, ok, detail=""):
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


# ───────────────────────── alt süreç senaryoları ────────────────────

def scenario(name: str) -> int:
    """Tek bir senaryoyu çalıştır; sonucu JSON olarak stdout'a yaz."""
    import controller  # noqa: E402
    import i18n  # noqa: E402
    import root_gate  # noqa: E402
    import updater  # noqa: E402

    # Ağ/süreç taraması yapan yan etkileri sabitle: bu test yalnızca kapıyı
    # sınıyor, ortam kontrolünün gerçek komut çalıştırmasına gerek yok.
    controller.CapWifiController.check_environment = lambda self, *a, **k: None
    controller.CapWifiController.list_handshakes = lambda self: []
    controller.CapWifiController.list_interfaces = lambda self: []
    controller.CapWifiController.console_windows = lambda self: []
    controller.CapWifiController.capture_console = lambda self, i: ""
    controller.CapWifiController.list_portals = lambda self: []
    updater.check_for_update = lambda *a, **k: None

    forced_root = name == "root"
    # is_root'u sabitliyoruz: gerçek kullanıcı (uid 1000) root değil, ama
    # kapının her iki dalını da aynı makinede sınamak istiyoruz.
    root_gate.is_root = lambda: forced_root

    import app as app_module  # noqa: E402

    built = {"ui": False, "labels": []}
    original_build_ui = app_module.CapWifiApp._build_ui

    def _tracking_build_ui(self):
        built["ui"] = True
        original_build_ui(self)

    app_module.CapWifiApp._build_ui = _tracking_build_ui

    # Diyalog gerçekten kurulsun ama test sonsuza kadar beklemesin: metinleri
    # toplayıp kendini kapatan bir "wait" koyuyoruz. Üretimde bu fonksiyon
    # kullanıcı düğmeye basana kadar bekler.
    original_wait = root_gate.RootWarningDialog.wait

    def _collecting_wait(self):
        try:
            for _ in range(8):
                self.update()
                time.sleep(0.05)
            built["labels"] = _labels(self)
            built["title"] = self.title()
        finally:
            self.close()

    root_gate.RootWarningDialog.wait = _collecting_wait

    result = {"scenario": name, "exit": 0, "built_ui": False, "labels": []}
    try:
        window = app_module.CapWifiApp()
        result["built_ui"] = built["ui"]
        result["has_scan_button"] = hasattr(window, "_btn_scan")
        try:
            window.destroy()
        except Exception:
            pass
    except SystemExit as exc:
        result["exit"] = exc.code if exc.code is not None else 0
        result["built_ui"] = built["ui"]
        result["labels"] = built["labels"]
        result["title"] = built.get("title", "")
    finally:
        root_gate.RootWarningDialog.wait = original_wait

    print("RESULT " + json.dumps(result, ensure_ascii=False))
    # Alt sürecin çıkış kodu kapının gerçek çıkış kodunu yansıtsın: kabuk
    # betiği ve CI, JSON'a bakmadan da "başarısız" olduğunu görebilmeli.
    return int(result["exit"] or 0)


def _labels(widget):
    """Bir widget ağacındaki tüm CTkLabel metinleri."""
    out = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            out.append(text)
        out.extend(_labels(child))
    return out


def scenario_shot() -> int:
    """Uyarı penceresini ekranda tut; üst süreç görüntü alacak."""
    import customtkinter as ctk  # noqa: E402

    import root_gate  # noqa: E402

    root = ctk.CTk()
    root.withdraw()
    dialog = root_gate.RootWarningDialog(root)
    for _ in range(10):
        dialog.update()
        time.sleep(0.05)
    # Geometriyi üst sürece veriyoruz: kare yalnızca uyarı penceresini
    # kırpsın, aynı ekranda açık başka pencereler görüntüye girmesin.
    print("READY %d %d %d %d" % (
        dialog.winfo_rootx(), dialog.winfo_rooty(),
        dialog.winfo_width(), dialog.winfo_height()), flush=True)
    deadline = time.time() + 12
    while time.time() < deadline and not dialog._closed:
        try:
            dialog.update()
        except Exception:
            break
        time.sleep(0.05)
    try:
        root.destroy()
    except Exception:
        pass
    return 0


# ───────────────────────────── koşucu ───────────────────────────────

def _child_env(**overrides) -> dict:
    env = dict(os.environ)
    env.pop("CAPCAP_ALLOW_NONROOT", None)
    env.pop("CAPCAP_ROOT_GATE_AUTO_ACK", None)
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


def run_scenario(name: str, **env_overrides) -> tuple:
    """Senaryoyu ayrı süreçte çalıştır: (exit_code, sonuç_dict|None, stderr)."""
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--scenario", name],
        capture_output=True, text=True, timeout=180,
        env=_child_env(**env_overrides),
    )
    result = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
    return proc.returncode, result, proc.stderr


def take_screenshot() -> bool:
    """Uyarı penceresini x11grab ile tek kareye al."""
    env = _child_env()
    child = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--scenario", "shot"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    try:
        deadline = time.time() + 20
        geometry = None
        while time.time() < deadline:
            line = child.stdout.readline()
            if not line:
                break
            if line.startswith("READY"):
                parts = line.split()
                if len(parts) == 5:
                    geometry = tuple(int(v) for v in parts[1:])
                break
        if geometry is None:
            print("  [FAIL] uyarı penceresi açılmadı; ekran görüntüsü alınamadı")
            return False

        x, y, w, h = geometry
        # Kenarları biraz taşıralım: pencere gölgesi/çerçevesi de görünsün.
        pad = 12
        x, y = max(0, x - pad), max(0, y - pad)
        display = os.environ.get("DISPLAY", ":1")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab",
             "-video_size", "%dx%d" % (w + pad * 2, h + pad * 2),
             "-i", "%s+%d,%d" % (display, x, y), "-frames:v", "1", SHOT_PATH],
            capture_output=True, text=True,
        )
        ok = proc.returncode == 0 and os.path.getsize(SHOT_PATH) > 0
        if not ok:
            print(f"  [FAIL] ffmpeg hata verdi: {proc.stderr[-200:]}")
        return ok
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()


def verify_texts() -> None:
    """Uyarı metinleri iki dilde de var ve komutu birebir içeriyor mu?"""
    import i18n  # noqa: E402

    keys = ("root.required.title", "root.required.body",
            "root.required.hint", "root.required.terminal",
            "root.required.exit")
    for code in ("en", "tr"):
        table = i18n.TRANSLATIONS[code]
        missing = [k for k in keys if k not in table or not table[k].strip()]
        check(f"{code}: tüm root anahtarları tanımlı", not missing, str(missing))
        blob = " ".join(table.get(k, "") for k in keys)
        check(f"{code}: uyarıda 'sudo ./run_gui.sh' komutu var",
              COMMAND in blob, blob[:160])

    # t() dil değişimini gerçekten uyguluyor mu (tablo doğru bağlı mı)?
    i18n.set_language("tr")
    tr_title = i18n.t("root.required.title")
    i18n.set_language("en")
    en_title = i18n.t("root.required.title")
    check("t() TR başlığı döndürüyor", tr_title == i18n.TR["root.required.title"],
          tr_title)
    check("t() EN başlığı döndürüyor", en_title == i18n.EN["root.required.title"],
          en_title)
    check("TR ve EN başlıkları farklı", tr_title != en_title,
          f"{tr_title} / {en_title}")


def main() -> int:
    if "--scenario" in sys.argv:
        name = sys.argv[sys.argv.index("--scenario") + 1]
        return scenario_shot() if name == "shot" else scenario(name)

    for _mod in ("tkinter", "customtkinter"):
        if importlib.util.find_spec(_mod) is None:
            print(f"  [SKIP] {_mod} yok")
            return 0

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") \
            and not os.environ.get("WAYLAND_DISPLAY"):
        print("  [SKIP] Görüntü sunucusu yok (DISPLAY boş)")
        return 0

    # 1) root değil, kaçış kapısı yok: uyarı + çıkış, arayüz kurulmaz.
    code, result, stderr = run_scenario("nonroot")
    check("root değilken süreç 0 dışı kodla çıkıyor", code != 0, str(code))
    check("çıkış kodu 77 (EX_NOPERM)",
          result is not None and result.get("exit") == 77,
          str(result and result.get("exit")))
    check("ana arayüz (build_ui) hiç kurulmadı",
          result is not None and result.get("built_ui") is False,
          str(result and result.get("built_ui")))
    check("uyarı penceresi gösterildi",
          bool(result and result.get("labels")), str(result and result.get("labels")))
    warning_text = " ".join(result.get("labels", [])) if result else ""
    check("uyarıda 'sudo ./run_gui.sh' yazıyor", COMMAND in warning_text,
          warning_text[:200])
    check("uyarıda root nedeni anlatılıyor", "root" in warning_text.lower(),
          warning_text[:120])
    check("stderr'de aynı talimat var", COMMAND in stderr, stderr[-200:])

    # 2) kaçış kapısı açık: arayüz normal kurulur.
    code, result, stderr = run_scenario("nonroot", CAPCAP_ALLOW_NONROOT="1")
    check("CAPCAP_ALLOW_NONROOT=1 ile uygulama açılıyor", code == 0, stderr[-300:])
    check("kaçış kapısında arayüz kuruldu",
          result is not None and result.get("built_ui") is True, str(result))
    check("kaçış kapısında ana düğmeler var",
          result is not None and result.get("has_scan_button") is True, str(result))

    # 3) root: kapı hiç devreye girmez.
    code, result, stderr = run_scenario("root")
    check("root iken uygulama açılıyor", code == 0, stderr[-300:])
    check("root iken arayüz kuruldu",
          result is not None and result.get("built_ui") is True, str(result))
    check("root iken uyarı yok", not (result and result.get("labels")),
          str(result and result.get("labels")))

    # 4) metinler
    verify_texts()

    # 5) ekran görüntüsü
    check("uyarı penceresi ekran görüntüsü alındı (/tmp/root_gate.png)",
          take_screenshot())

    print()
    if failures:
        print(f"{len(failures)} kontrol başarısız: {failures}")
        return 1
    print("Root kapısı testleri geçti")
    return 0


if __name__ == "__main__":
    sys.exit(main())
