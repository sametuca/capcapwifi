#!/usr/bin/env python3
"""Tek görünümlü arayüzün davranış testi (pencere açar, görüntü gerekir).

Basit/Detay ayrımı kaldırıldıktan sonra arayüzün sözleşmesi şu:
kullanıcı bir ağ seçer, kart sinyali/cihaz sayısını/yayınlanacak sayfayı
gösterir, "Başlat" gerisini halleder. Bu betik o sözleşmeyi gerçek widget
metinlerini okuyarak doğrular; ekran görüntüsüne bakmaz.
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

import controller  # noqa: E402

controller.CapWifiController.check_environment = lambda self, *a, **k: None
controller.CapWifiController.list_handshakes = lambda self: []
controller.CapWifiController.list_interfaces = lambda self: []
controller.CapWifiController.console_windows = lambda self: []
controller.CapWifiController.capture_console = lambda self, i: ""


class Portal:
    def __init__(self, site_id, name, lang, desc):
        self.site_id = site_id
        self.name = name
        self.lang = lang
        self._desc = desc

    @property
    def display_title(self):
        return f"{self.name} [{self.lang.upper()}]"

    @property
    def description(self):
        return self._desc


PORTALS = [
    Portal("Instagram_tur", "Instagram", "tur", "Kendi kayıt sayfası."),
    Portal("Facebook_en", "Facebook", "en", "Stok portal."),
]
controller.CapWifiController.list_portals = lambda self: list(PORTALS)

import updater  # noqa: E402
updater.check_for_update = lambda *a, **k: None
import app as app_module  # noqa: E402
import i18n  # noqa: E402
from models import AttackState, EnvironmentCheck, TargetCandidate  # noqa: E402

i18n.set_language("tr")
window = app_module.CapWifiApp()

CANDS = [
    TargetCandidate("AA:BB:CC:DD:EE:01", "6", -42, 3, "86%", "WPA2",
                    "TP-Link", "EvimFiber"),
    TargetCandidate("AA:BB:CC:DD:EE:02", "11", -58, 0, "62%", "WPA2",
                    "Asus", "KOMSU_5G"),
]

failures = []


def check(label, ok, detail=""):
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def labels(master):
    """Topla: bir kapsayıcı altındaki tüm CTkLabel metinleri."""
    out = []
    for child in master.winfo_children():
        try:
            text = child.cget("text")
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            out.append(text)
        out.extend(labels(child))
    return out


def body():
    try:
        window.update_idletasks()
        window.update()

        check("tek görünüm: mod düğmesi kaldırıldı",
              not hasattr(window, "_mode_switch"))
        check("eski ayar paneli kaldırıldı",
              not hasattr(window, "_config_panel"))
        check("seçili ağ kartı var", hasattr(window, "_summary"))

        # Hiç seçim yokken yönlendirme metni görünmeli.
        summary_text = " ".join(labels(window._summary))
        check("seçim yokken yönlendirme gösteriliyor",
              i18n.t("summary.none_title") in summary_text, summary_text[:120])
        check("üç sütun başlığı da var",
              all(k in summary_text for k in (i18n.t("summary.signal"),
                                              i18n.t("summary.clients"),
                                              i18n.t("summary.portal"))),
              summary_text[:160])

        # Portal listesi ilk açılışta dolmalı.
        check("portal listesi ilk açılışta dolu",
              window._summary.portal_title() != i18n.t(
                  "config.attack.portal_loading"),
              window._summary.portal_title())
        check("varsayılan portal Türkçe Instagram",
              window._summary.selected_portal() is PORTALS[0],
              window._summary.portal_title())

        # Ağ seçimi özet kartını doldurmalı.
        window._net_table.load(CANDS)
        window._net_table._select(CANDS[0])
        window.update_idletasks()
        summary_text = " ".join(labels(window._summary))
        check("seçilen ağın adı kartta", "EvimFiber" in summary_text)
        check("sinyal dBm olarak görünüyor", "-42 dBm" in summary_text,
              summary_text)
        check("cihaz sayısı görünüyor", "3 cihaz" in summary_text, summary_text)
        check("kanal rozeti var", "CH 6" in summary_text, summary_text)
        check("şifreleme rozeti var", "WPA2" in summary_text, summary_text)
        check("ayarlar hedefi aldı", window._settings.bssid() ==
              "AA:BB:CC:DD:EE:01")
        check("ayarlar portalı aldı",
              window._settings.portal is PORTALS[0])

        # Cihazsız ağ: cihaz sütunu "sonuç çıkmaz" demeli.
        window._net_table._select(CANDS[1])
        window.update_idletasks()
        summary_text = " ".join(labels(window._summary))
        check("cihazsız ağ uyarısı", i18n.t("summary.clients_none") in
              summary_text, summary_text)

        # Portal değişimi ayarlara yansımalı.
        window._summary.set_portal(PORTALS[1].display_title)
        window._refresh_hint()
        check("portal değişimi ayarlara yansıdı",
              window._settings.portal is PORTALS[1],
              str(window._settings.portal))

        # Saldırı hazırlığı: hedef cihazlıysa önce handshake.
        window._net_table._select(CANDS[0])
        ok = window._prepare_attack()
        check("hedef varsa hazırlık başarılı", ok)
        check("cihazlı WPA2 ağda handshake aşaması",
              not window._settings.is_portal, str(window._settings.attack_type))
        check("zincir kuruldu (handshake→portal)", window._basic_chain)

        # Handshake yakalanınca portal aşamasına geçilmeli.
        window._settings.use_portal()
        check("portal aşamasına geçilebiliyor", window._settings.is_portal)
        check("portal id'si motora gidiyor",
              window._settings.build_config().portal_site == PORTALS[1].site_id,
              window._settings.build_config().portal_site)

        # Temizle kartı sıfırlamalı.
        window._do_clear()
        window.update_idletasks()
        summary_text = " ".join(labels(window._summary))
        check("temizle kartı sıfırladı",
              i18n.t("summary.none_title") in summary_text, summary_text[:100])
        check("temizle hedefi bıraktı", not window._settings.has_target())

        # Detaylar penceresi açılıp kapanmalı.
        window._open_details()
        window.update_idletasks()
        check("detaylar penceresi açıldı", window._details_window is not None)
        window._details_window.close()
        window.update_idletasks()
        check("detaylar penceresi kapandı", window._details_window is None)

    except Exception:
        traceback.print_exc()
        failures.append("exception")
    finally:
        try:
            window.destroy()
        except Exception:
            pass


window.after(700, body)
window.mainloop()

if failures:
    print(f"\n{len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("\nSingle view OK")
