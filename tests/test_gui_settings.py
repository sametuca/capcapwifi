#!/usr/bin/env python3
"""AttackSettings birim testi – görüntü ve customtkinter gerekmez.

Tek görünüme geçtikten sonra arayüzün topladığı kararlar üçe indi: hedef,
saldırı türü ve portal sayfası. Bu nesne onları motorun beklediği
``AttackConfig``'e çevirir; otomatik seçimler tek yerde durur.
"""
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
GUI_DIR = TESTS_DIR.parent / "gui"
sys.path.insert(0, str(GUI_DIR))

# app.py modül düzeyinde tema/customtkinter import ediyor; ayarları ondan
# almadan önce yalnızca sınıfı yüklemek için modülü import ediyoruz.
import importlib.util  # noqa: E402

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"  [OK] {label}")
    else:
        failures += 1
        print(f"  [FAIL] {label}" + (f"  ->  {detail}" if detail else ""))


have_ctk = importlib.util.find_spec("customtkinter") is not None
if not have_ctk:
    print("  [SKIP] customtkinter yok; AttackSettings app.py içinde")
    print("\nAttackSettings OK (atlandı)")
    sys.exit(0)

import app as gui_app  # noqa: E402
from models import (  # noqa: E402
    AttackConfig,
    AttackType,
    PortalSite,
    TargetCandidate,
)

AttackSettings = gui_app.AttackSettings


def make_target(**kw) -> TargetCandidate:
    base = dict(bssid="AA:BB:CC:DD:EE:01", channel="6", power=-42, clients=3,
                quality="86%", enc="WPA2", vendor="TP-Link", essid="EvimFiber")
    base.update(kw)
    return TargetCandidate(**base)


def make_portal(site_id: str, name: str, lang: str) -> PortalSite:
    return PortalSite(site_id=site_id, name=name, lang=lang, path="/tmp/p")


# ── başlangıç durumu ────────────────────────────────────────────────
s = AttackSettings()
check("başlangıçta hedef yok", not s.has_target())
check("başlangıçta portal saldırısı", s.is_portal)
check("başlangıçta bssid boş", s.bssid() == "")
check("başlangıçta essid boş", s.essid() == "")
check("başlangıçta kanal boş", s.target_channel() == "")

# ── hedef ───────────────────────────────────────────────────────────
target = make_target()
s.set_target(target)
check("hedef atanınca has_target True", s.has_target())
check("bssid hedeften geliyor", s.bssid() == "AA:BB:CC:DD:EE:01", s.bssid())
check("essid hedeften geliyor", s.essid() == "EvimFiber", s.essid())
check("kanal hedeften geliyor", s.target_channel() == "6", s.target_channel())
s.set_target(None)
check("hedef temizlenebiliyor", not s.has_target())

# ── saldırı türü ────────────────────────────────────────────────────
s.use_handshake()
check("handshake türü seçildi",
      s.attack_type is AttackType.HANDSHAKE_SNOOPER, str(s.attack_type))
check("is_portal False", not s.is_portal)
s.use_portal()
check("portal türüne dönüldü", s.is_portal)

# ── portal ──────────────────────────────────────────────────────────
check("portalsız varsayılan site", s.portal_site_id() == "Instagram_tur",
      s.portal_site_id())
tr_portal = make_portal("Instagram_tur", "Instagram", "tur")
s.set_portal(tr_portal)
check("portal başlığı portal nesnesinden", s.portal_title() == "Instagram [TUR]",
      s.portal_title())
check("portal id'si motora gidiyor", s.portal_site_id() == "Instagram_tur")

# Varsayılan seçim: Türkçe Instagram tercih edilir.
portals = [make_portal("Facebook_en", "Facebook", "en"), tr_portal]
check("varsayılan portal Türkçe Instagram",
      AttackSettings.default_portal(portals) is tr_portal)
check("Türkçe Instagram yoksa ilk portal",
      AttackSettings.default_portal([make_portal("Facebook_en", "Facebook", "en")])
      is not None)
check("boş listede varsayılan None", AttackSettings.default_portal([]) is None)

# ── tarama süresi ───────────────────────────────────────────────────
s.set_scan_time("45")
check("geçerli süre okunuyor", s.scan_time == 45, str(s.scan_time))
s.set_scan_time("abc")
check("geçersiz süre 30'a düşüyor", s.scan_time == 30, str(s.scan_time))
s.set_scan_time("")
check("boş süre 30'a düşüyor", s.scan_time == 30, str(s.scan_time))
s.set_scan_time(None)
check("None süre 30'a düşüyor", s.scan_time == 30, str(s.scan_time))
s.set_scan_time("2")
check("alt sınır 5 sn", s.scan_time == 5, str(s.scan_time))
s.set_scan_time("99999")
check("üst sınır 600 sn", s.scan_time == 600, str(s.scan_time))

# ── motor yapılandırması ────────────────────────────────────────────
s = AttackSettings()
s.set_target(make_target())
s.set_portal(tr_portal)
s.band = "abg"
s.set_scan_time("40")
s.language = "tur"
config = s.build_config()
check("AttackConfig üretiliyor", isinstance(config, AttackConfig),
      type(config).__name__)
check("config hedefi taşıyor", config.target_bssid == "AA:BB:CC:DD:EE:01",
      config.target_bssid)
check("config essid taşıyor", config.target_essid == "EvimFiber", config.target_essid)
check("config kanal taşıyor", config.target_channel == "6", config.target_channel)
check("config portal taşıyor", config.portal_site == "Instagram_tur",
      config.portal_site)
check("config bant taşıyor", config.band == "abg", config.band)
check("config dil taşıyor", config.language == "tur", config.language)
check("config saldırı türü", config.attack_type is AttackType.CAPTIVE_PORTAL)
check("jammer otomatik (boş)", config.jammer_interface == "",
      config.jammer_interface)
check("ap servisi varsayılan hostapd", config.ap_service == "hostapd",
      config.ap_service)
check("deauth varsayılan aireplay-ng", config.deauth_method == "aireplay-ng",
      config.deauth_method)

s.use_handshake()
check("handshake config'i",
      s.build_config().attack_type is AttackType.HANDSHAKE_SNOOPER)

# Tarama parametreleri controller.start_scan sözleşmesine uyar.
s.interface = "wlan0mon"
s.channel = "11"
params = s.scan_params()
check("scan_params 4'lü demet", len(params) == 4, str(params))
check("scan_params sırası (arayüz, süre, kanal, bant)",
      params == ("wlan0mon", 40, "11", "abg"), str(params))

# Dil listesi dil klasöründen gelir.
langs = AttackSettings.languages(GUI_DIR.parent)
check("dil listesi dolu", bool(langs), str(langs))
check("en ve tur listede", "en" in langs and "tur" in langs, str(langs))
check("olmayan klasörde varsayılan",
      AttackSettings.languages(GUI_DIR / "nope") == ["en", "tur"])

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nAttackSettings OK")
