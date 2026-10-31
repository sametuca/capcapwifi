"""
CapCapWifi GUI - interface languages.

The GUI ships with English and Turkish. All user-facing text lives in the
tables below; widgets call :func:`t` at render time, so switching language
re-renders the window without restarting the attack engine.

The choice is persisted in ``~/.config/capcapwifi/gui.json`` and can be
overridden per run with ``CAPCAP_GUI_LANG=en|tr``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_LANGUAGE = "en"

#: Display name shown in the language switch.
LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("en", "English"),
    ("tr", "Türkçe"),
)

CONFIG_DIR = Path.home() / ".config" / "capcapwifi"
CONFIG_FILE = CONFIG_DIR / "gui.json"

EN: Dict[str, str] = {
    # ── window chrome ───────────────────────────────────────────
    "app.title": "CapCapWifi – Wi-Fi Security Auditor",
    "app.subtitle": "Wi-Fi security auditor",
    "app.tab.networks": "Networks",
    "app.tab.credentials": "Passwords",
    "app.tab.consoles": "Consoles",
    "app.tab.help": "How to use",
    "app.btn.scan": "Scan",
    "app.btn.attack": "Start",
    "app.btn.stop": "Stop",
    "app.btn.clear": "Clear",
    "app.health.title": "Environment check",
    "app.health.install": "Install missing",
    "app.health.desc": "Everything the attack needs is listed here. ✗ = missing.",
    "app.health.checking.name": "Checking…",
    "app.health.checking.detail": "scanning tools and adapter",
    "app.health.installing": "Installing – apt output appears in the log panel…",
    "app.language.label": "Language",

    # ── basit / detay mod ──────────────────────────────────────
    "mode.basic": "Basic",
    "mode.detail": "Detail",
    "basic.need_target": ("Pick a network from the list first – tap the row whose signal "
                          "is strongest."),
    "basic.phase.handshake": ("Step 1/2 – disconnecting devices and listening for a "
                              "handshake…"),
    "basic.phase.portal": ("Step 2/2 – handshake captured. Opening the fake network and "
                           "the login page…"),
    "basic.hint.captured": ("Handshake captured – opening the fake network and the "
                            "login page, no action needed."),
    "basic.portal_ready": ("Ready: the network \"{ssid}\" is now broadcast by this computer. "
                           "On the phone open Wi-Fi and pick that name."),
    "basic.learning": ("Everything is automatic: adapter, channel, portal and deauth "
                       "method are chosen for you."),

    # ── workflow steps ──────────────────────────────────────────
    "step.adapter": "Adapter",
    "step.scan": "Scan",
    "step.target": "Select target",
    "step.attack": "Attack",
    "step.result": "Result",

    # ── configuration panel ─────────────────────────────────────
    "config.auto": "Automatic (let the program choose)",
    "config.adapter.title": "1 · ADAPTER",
    "config.adapter.desc": "Which wireless card to use. Leave it on automatic if unsure.",
    "config.adapter.primary": "Primary (scan):",
    "config.adapter.jammer": "Deauth card:",
    "config.adapter.ap": "Rogue AP card:",
    "config.adapter.note": ("With two adapters: one for the rogue AP, one for deauth. "
                            "A single adapter works too, just slower."),
    "config.adapter.refresh": "Refresh list",

    "config.scan.title": "2 · SCAN",
    "config.scan.desc": "Short is quick; long also sees connected clients.",
    "config.scan.time": "Duration (s):",
    "config.scan.band": "Band:",
    "config.scan.channel": "Channel:",
    "config.scan.channel_ph": "All",
    "band.bg": "bg (2.4 GHz)",
    "band.a": "a (5 GHz)",
    "band.abg": "abg (both)",

    "config.target.title": "3 · TARGET",
    "config.target.desc": "Clicking a table row fills these fields automatically.",
    "config.target.ssid": "SSID:",
    "config.target.ssid_ph": "Network name",
    "config.target.bssid": "BSSID:",
    "config.target.channel": "Channel:",
    "config.target.none": "No target selected yet.",

    "config.attack.title": "4 · ATTACK",
    "config.attack.desc": "There are two methods; the description of the selected one appears below.",
    "config.attack.type": "Type:",
    "config.attack.portal": "Portal:",
    "config.attack.portal_loading": "Loading…",
    "config.attack.ap_service": "AP service:",
    "config.attack.deauth": "Deauth:",
    "config.attack.lang": "Language:",
    "config.attack.timeout": "Timeout (min):",
    "config.attack.timeout_ph": "Unlimited",
    "config.attack.desc_format": "{summary}\n\nNEEDED: {need}\n\nNEXT: {next}",

    # ── attack types ────────────────────────────────────────────
    "attack.captive_portal.label": "Captive Portal – fake login page",
    "attack.captive_portal.summary": (
        "Opens an exact copy of the target network (rogue AP), shows a login page "
        "to the device that connects and records what is typed in."
    ),
    "attack.captive_portal.need": (
        "An adapter that supports monitor mode + injection (ideally two adapters: "
        "one for the rogue AP, one for deauth). Pick a portal; the program sets up "
        "the rest."
    ),
    "attack.captive_portal.next": (
        "The rogue AP goes up, target devices are dropped and the portal page is "
        "served. When a device submits the form, a row appears on the Passwords tab."
    ),
    "attack.handshake_snooper.label": "Handshake Snooper – handshake capture",
    "attack.handshake_snooper.summary": (
        "Drops the devices connected to the target network so they reconnect, then "
        "captures the WPA/WPA2 handshake. The result is a .cap file."
    ),
    "attack.handshake_snooper.need": (
        "An adapter that supports monitor mode + injection. The target network must "
        "have at least one connected client; no client means no handshake."
    ),
    "attack.handshake_snooper.next": (
        "The attack starts and looks for a handshake for the chosen duration. If one "
        "is found, a ✔ mark appears on the Networks tab and the log says so."
    ),

    # ── target / portal helpers ─────────────────────────────────
    "target.hidden_ssid": "<Hidden network>",
    "target.rec.dfs": (
        "DFS channel: the rogue AP cannot start here. Pick another network for the "
        "portal; it is fine for a handshake."
    ),
    "target.rec.clients": (
        "{clients} clients connected: best chance to get a result from deauth for a "
        "handshake or portal."
    ),
    "target.rec.no_clients": (
        "No connected client visible: there is nobody to deauth, so this network "
        "yields neither a handshake nor a portal visitor."
    ),
    "portal.desc.self_capturing": (
        "Uses its own submission page: the username and password the visitor types "
        "are recorded directly; no handshake needed."
    ),
    "portal.desc.stock": (
        "Stock portal: verifies the submitted password against a captured handshake, "
        "so that network's handshake is needed first."
    ),

    # ── help tab ───────────────────────────────────────────────
    "help.text": """HOW TO USE – 5 STEPS

1) ADAPTER
   Look at the "Environment check" card on the right. A red ✗
   means the attack cannot start: the adapter must support
   monitor mode + packet injection and the program must run
   as root.

2) SCAN
   The "Scan" button lists nearby networks. A longer duration
   shows more networks and collects the connected client counts
   over that period. No clients means there is nobody to deauth.

3) SELECT TARGET
   A green row in the table means at least one client is connected.
   Click the row; the program fills SSID/BSSID/channel itself and
   explains below why that network is (or is not) suitable.

4) ATTACK
   Captive Portal: opens an exact copy of the target network, shows
   the selected portal page to the device that connects and records
   what is typed into the form. If the portal records submissions
   itself (Instagram templates), the extra password verification
   step is skipped.
   Handshake Snooper: drops the clients so they reconnect and
   captures the WPA/WPA2 handshake; the result is a .cap file.

5) RESULT
   Captive Portal → "Passwords" tab
   Handshake Snooper → a green panel opens above the tabs. It shows the
   full path of the saved .cap file and offers two buttons: continue with
   Captive Portal, or crack the file with a wordlist. The network keeps a
   ✔ mark so you can find it later.

FILES
   Live status : /tmp/capcapspace/capcap.status
   Logins      : /tmp/capcapspace/instagram_credentials.log
   Handshakes  : attacks/Handshake Snooper/handshakes/

NOTES
   • Channels marked ! are DFS: the rogue AP cannot start there.
   • The deauth method is automatic (aireplay-ng); mdk4 is the exception.
   • While an attack runs, "Stop" closes everything cleanly.
   • Switch the interface language with EN / TR at the top right.
""",

    # ── log panel ──────────────────────────────────────────────
    "log.title": "Live log",
    "log.clear": "Clear",
    "log.lines": "{count} lines",
    "log.env_line": "[env] {name}: {detail} → {hint}",
    "log.needs_root": "[!] Installation needs root: sudo ./run_gui.sh",
    "log.install_done": "[+] Installation finished. Re-checking environment…",
    "log.install_failed": ("[!] Installation could not finish. Check the apt output in the log; "
                           "if needed run `sudo ./capcapwifi.sh --install-deps` in a terminal."),
    "log.install_first": ("[i] First install: missing packages are being fetched automatically. "
                          "This can take a few minutes; do not close the window."),
    "log.handshake_archive_error": "[!] Error scanning the handshake archive: {error}",
    "log.handshake_captured": "[+] HANDSHAKE CAPTURED → saved to {file}.",
    "log.handshake_next": ("Handshake Snooper closed itself because it was done. Open the Passwords "
                           "tab, find the handshake and press \"Use with portal\" to start the "
                           "Captive Portal for that network."),
    "log.target_selected": "[+] Target: {ssid} ({bssid}) CH{channel}",
    "log.target_has_handshake": "ℹ️ A saved handshake already exists for this network; you can start Captive Portal directly.",
    "log.pmf_target": ("⚠️ {ssid} uses WPA3/PMF. Deauthentication is protected on this "
                       "network, so the phone will not disconnect; the captive portal "
                       "step also cannot pull clients over. Try a WPA2 network."),
    "log.scan_start": "[*] Scan starting – interface {iface}, {seconds}s",
    "log.iface_auto": "automatic",
    "log.no_target": "[!] No target. Pick a network from the table or enter a BSSID/SSID.",
    "log.no_target_hint": "First pick a target from the table: click a row or scan again.",
    "log.no_portal": "[!] No portal template selected.",
    "log.portal_info": "[i] Portal: {title} – {desc}",
    "log.attack_start": "[*] {attack} → {target}",
    "log.guide_portal_ready": ("[*] Captive Portal prepared: target {ssid} ({bssid}). "
                               "The same SSID is broadcast with the portal page attached."),
    "log.guide_portal_autostart": "[*] Starting the Captive Portal now – the portal page appears once a device joins.",
    "log.guide_start_hint": "[*] Press the 'Start' button at the bottom to begin.",
    "log.crack_start": "[*] Starting aircrack-ng wordlist attack… Target: {ssid} ({bssid})",

    # ── network table ──────────────────────────────────────────
    "networks.title": "Nearby networks",
    "networks.search_ph": "Search network name or BSSID…",
    "networks.legend": ("Green badge = connected clients (deauth possible)   ·   "
                        "✔ = handshake saved   ·   DFS = rogue AP cannot start"),
    "networks.empty": ("No networks yet.\n\nNext step: set a duration on the left and "
                       "press “Scan”."),
    "networks.hint_initial": "First list the networks with “Scan”.",
    "networks.summary": ("{total} networks, {clients} with connected clients, "
                         "{handshakes} with a saved handshake. Click a row; the fields "
                         "below fill themselves."),
    "networks.count": "{count} networks",
    "networks.filtered_count": "{visible}/{total} networks",
    "networks.clients": "{count} clients",
    "networks.no_clients": "no clients",
    "networks.clients_short": "✓ device connected",
    "networks.handshake_badge": "✔ Handshake",
    "networks.dfs_badge": "DFS",

    # ── credentials / handshakes ───────────────────────────────
    "creds.title": "Captured logins & handshake archive",
    "console.title": "Attack consoles (embedded)",
    "console.hint": ("Every window the attack opens (DHCP, DNS, access point, deauth, "
                     "portal) is shown here. This is the same output that used to appear "
                     "in separate terminal windows."),
    "console.empty": "No console yet. Start an attack and the windows will appear here.",
    "console.waiting": "Waiting for the attack window…",
    "console.not_found": ("No attack console found yet. If this stays empty, the attack has not "
                          "started yet – check the log panel on the right."),
    "console.buffer": "{name} · live tail",
    "creds.desc": ("Passwords typed into the web portals and WPA .cap handshakes "
                   "captured by listening are archived here."),
    "creds.empty": ("No logins or handshakes yet.\n\n"
                    "• A device shows up here after it connects to the fake portal and "
                    "submits a password.\n"
                    "• Captured WPA handshake files are listed here too."),
    "creds.copy": "Copy",
    "creds.handshake_header": "── Captured WPA handshake (.cap) files ──",
    "creds.count_passwords": "{count} passwords",
    "creds.count_handshakes": "{count} handshake",
    "hs.unknown_ssid": "<Unknown network>",
    "hs.use_portal": "Use with portal",
    "hs.crack": "Crack with aircrack",
    "hs.previous": "Previously saved",

    # ── environment checklist ──────────────────────────────────
    "checklist.missing": ("{count} required components missing – the install command is "
                          "written in the log panel"),
    "checklist.optional": ("Ready. {count} optional tools are missing, core flows still work."),
    "checklist.ready": "Everything is ready.",

    # ── status badge ───────────────────────────────────────────
    "state.IDLE": "Ready",
    "state.INSTALLING": "Installing",
    "state.STARTING": "Starting",
    "state.SCANNING": "Scanning",
    "state.RUNNING": "Running",
    "state.HANDSHAKE_CAPTURED": "Handshake captured",
    "state.CREDENTIALS_FOUND": "Credentials found",
    "state.STOPPED": "Stopped",
    "state.ERROR": "Error",

    # ── bottom hint bar ────────────────────────────────────────
    "hint.installing": ("Required packages are being installed. The check refreshes "
                        "automatically when it finishes; do not close the window."),
    "hint.scanning": "Scanning networks… The table fills when it finishes, then pick a target.",
    "hint.starting": ("Preparing the attack: the adapter is put into monitor mode and "
                      "services are starting."),
    "hint.running.portal": ("Rogue AP is on air. When a device connects and submits the form, "
                            "a row appears on the Passwords tab."),
    "hint.running.handshake": ("Deauth is running, waiting for a handshake. When it is "
                               "captured the snooper closes itself – that is normal."),
    "hint.credentials": "Login captured! Copy it from the Passwords tab.",
    "hint.handshake": ("Handshake captured! Open the Passwords tab: \"Use with portal\" "
                       "starts the Captive Portal, \"Crack with aircrack\" tries the wordlist."),
    "hint.error": "Error: check the log panel and environment card on the right.",
    "hint.stopped": "Stopped. Start a new scan or change the target whenever you like.",
    "hint.env_checking": "Checking the environment…",
    "hint.missing": "Missing: {names} – see the hint in the card on the right.",
    "hint.missing_more": "Missing: {names} (+{extra} more)",
    "hint.ready_scan": "Everything is ready. Next step: find networks with “Scan”.",
    "hint.pick_row": ("Click a green row (one with connected clients) in the table; "
                      "the fields fill themselves."),
    "hint.target_ready": "Target is ready. Continue with “Start”.",
    "hint.pmf_target": ("This network uses WPA3/PMF: deauthentication frames are ignored, "
                        "so clients will not drop. Pick a WPA2 network instead."),

    # ── controller: environment checks ─────────────────────────
    "env.root.name": "Root privileges",
    "env.root.ok": "running as administrator",
    "env.root.missing": "running without sudo",
    "env.root.hint": ("Start with sudo ./run_gui.sh; monitor mode and hostapd require root."),
    "env.tool.missing": "not installed",
    "env.optional.name": "{tool} (optional)",
    "env.optional.missing": "missing – this feature is unavailable",
    "env.adapter.name": "Wireless adapter",
    "env.adapter.found": "{names}",
    "env.adapter.none": "not found",
    "env.adapter.hint": ("Is the adapter plugged in? If you are in a VM, did you pass the "
                         "USB device through? It must show up in `iw dev`."),
    "env.monitor.name": "Monitor mode",
    "env.monitor.ready": "ready",
    "env.monitor.pending": "not enabled yet (turned on when the attack starts)",
    "env.monitor.hint": "If it fails: sudo airmon-ng start <interface>",

    "purpose.aircrack-ng": "handshake verification / .cap handling",
    "purpose.airmon-ng": "putting the adapter into monitor mode",
    "purpose.hostapd": "rogue access point",
    "purpose.lighttpd": "portal web server",
    "purpose.php-cgi": "portal PHP endpoints",
    "purpose.kea-dhcp4": "portal DHCP server",
    "purpose.dnsspoof": "redirecting every domain to the portal",
    "purpose.mdk4": "deauth (alternative method)",
    "purpose.iw": "channel / interface information",
    "purpose.xterm": "separate windows (tmux with -m if missing)",
    "purpose.tmux": "window backend the GUI uses to run attacks",
    "purpose.cowpatty": "password verification for stock portals",
    "purpose.pyrit": "alternative password verification",

    # ── controller: log messages ──────────────────────────────
    "ctrl.busy": "Something is already running; stop it first.",
    "ctrl.install.busy": "Install/attack already running.",
    "ctrl.install.start": ("Checking packages. Anything missing is installed automatically "
                           "(can take a few minutes the first time)."),
    "ctrl.crack.missing_file": "Handshake file not found: {path}",
    "ctrl.crack.missing_wordlist": ("Wordlist not found: {path}. On Kali you can run "
                                    "'sudo gzip -d /usr/share/wordlists/rockyou.txt.gz'."),
    "ctrl.crack.started": "Starting aircrack-ng wordlist attack…",
    "ctrl.crack.handshake": "   Handshake: {name}",
    "ctrl.crack.wordlist": "   Wordlist: {path}",
    "ctrl.crack.found": "{line}",
    "ctrl.crack.solved": "PAROLA ÇÖZÜLDÜ: {password}",
    "ctrl.crack.not_found": "Password not found in this wordlist.",
    "ctrl.crack.error": "aircrack-ng error: {error}",
    "ctrl.scan.busy": "Another operation is running; stop it first.",
    "ctrl.scan.start": "Scan started – interface: {iface}, duration: {seconds}s",
    "ctrl.attack.busy": "Another operation is running; stop it first.",
    "ctrl.attack.start": "Starting attack: {attack} → {target}",
    "ctrl.attack.none": "no target selected",
    "ctrl.stop.done": "Process stopped.",
    "ctrl.error.script_missing": ("capcapwifi.sh not found or sudo is asking for a password. "
                                  "Start the GUI with `sudo ./run_gui.sh`."),
    "ctrl.error.spawn": "Could not start the process: {error}",
    "ctrl.dep.check": "Checking packages…",
    "ctrl.dep.missing": "Installing missing packages: {tools}",
    "ctrl.dep.ok": "All required packages are ready.",
    "ctrl.dep.failed": "Package installation failed.",
    "ctrl.scan.complete": "Scan complete – {count} networks found.",
    "ctrl.scan.found": "{count} networks listed.",
    "ctrl.scan.empty": ("No networks found in the scan output. Does the adapter support "
                        "monitor mode? Try a longer duration."),
    "ctrl.target": "Target: {ssid} ({bssid}) channel {channel}",
    "ctrl.timeout": "Time limit reached ({minutes} min), closing the attack.",
    "ctrl.handshake.congrats": "WPA 4-way handshake captured and verified!",
    "ctrl.handshake.location": "Saved to: {path}",
    "ctrl.handshake.whatnow": "WHAT TO DO NOW?",
    "ctrl.handshake.option1": ("   1. (Recommended) Start a Captive Portal attack for this "
                               "network. When the visitor types a password, the captured "
                               "handshake confirms it automatically!"),
    "ctrl.portal.join_hint": ("On the phone open Wi-Fi settings and pick \"{ssid}\" by hand – "
                              "a saved network does not join the open twin on its own. The "
                              "portal page appears right after the device connects."),
    "ctrl.attack.failed": ("Attack stopped itself: {reason}"),
    "ctrl.ap_channel_fallback": ("The AP card cannot broadcast on channel {frm}; "
                                 "the fake access point moved to channel {to}."),
    "ctrl.finish.handshake": ("Handshake Snooper stopped itself because the handshake was saved. "
                              "You did not stop it. Start the Captive Portal from the saved "
                              "handshake in the Passwords tab."),
    "ctrl.finish.credentials": ("Captive Portal captured a login, so it stopped itself. "
                                "Check the Passwords tab."),
    "ctrl.handshake.autostop": ("Handshake Snooper stops itself once the handshake is saved: you did "
                                "not stop anything, and nothing is left running. The Captive Portal "
                                "needs a separate start."),
    "ctrl.handshake.option2": ("   2. Or start an aircrack-ng wordlist attack from the "
                               "Passwords tab."),
    "ctrl.credential.new": "New login captured: {username} ({ip})",

    # ── stream humanizing ─────────────────────────────────────
    "humanize.deauth_directed": "⚡ [Deauth] Sending a disconnect packet to the client… ({line})",
    "humanize.tracker": "🎯 Target tracker active: following channel changes.",
    "humanize.aireplay": "⚡ [Deauth] aireplay-ng is briefly disconnecting the target devices…",
    "humanize.airodump": "📡 airodump-ng started listening on the target channel…",
    "humanize.cleanup": "✓ Cleanup finished: attack processes were closed and the adapter is back in normal mode.",
}

TR: Dict[str, str] = {
    # ── basit / detay mod ──────────────────────────────────────
    "mode.basic": "Basit",
    "mode.detail": "Detay",
    "basic.need_target": ("Önce listeden bir ağ seç – sinyali en güçlü satıra dokun."),
    "basic.phase.handshake": ("1/2 – cihazlar ağdan düşürülüyor ve handshake "
                              "bekleniyor…"),
    "basic.phase.portal": ("2/2 – handshake alındı. Sahte ağ ve giriş sayfası "
                           "açılıyor…"),
    "basic.hint.captured": ("Handshake alındı – sahte ağ ve giriş sayfası açılıyor, "
                            "senin bir şey yapmana gerek yok."),
    "basic.portal_ready": ("Hazır: \"{ssid}\" ağı artık bu bilgisayardan yayınlanıyor. "
                           "Telefonda Wi-Fi listesini aç ve bu adı seç."),
    "basic.learning": ("Her şey otomatik: adaptör, kanal, portal ve deauth yöntemi "
                       "senin yerine seçilir."),

    "app.title": "CapCapWifi – Wi-Fi Güvenlik Denetleyicisi",
    "app.subtitle": "Wi-Fi güvenlik denetleyicisi",
    "app.tab.networks": "Ağlar",
    "app.tab.credentials": "Şifreler",
    "app.tab.consoles": "Konsollar",
    "app.tab.help": "Nasıl kullanılır",
    "app.btn.scan": "Tara",
    "app.btn.attack": "Başlat",
    "app.btn.stop": "Durdur",
    "app.btn.clear": "Temizle",
    "app.health.title": "Ortam kontrolü",
    "app.health.install": "Eksikleri kur",
    "app.health.desc": "Saldırı için gereken her şey burada listelenir. ✗ = eksik.",
    "app.health.checking.name": "Kontrol ediliyor…",
    "app.health.checking.detail": "araçlar ve adaptör taranıyor",
    "app.health.installing": "Kurulum sürüyor – apt çıktısı log panelinde…",
    "app.language.label": "Dil",

    "step.adapter": "Adaptör",
    "step.scan": "Tara",
    "step.target": "Hedef seç",
    "step.attack": "Saldır",
    "step.result": "Sonuç",

    "config.auto": "Otomatik (program seçsin)",
    "config.adapter.title": "1 · ADAPTÖR",
    "config.adapter.desc": "Hangi kablosuz kart kullanılacak. Emin değilsen otomatik bırak.",
    "config.adapter.primary": "Birincil (tarama):",
    "config.adapter.jammer": "Deauth kartı:",
    "config.adapter.ap": "Sahte AP kartı:",
    "config.adapter.note": ("İki adaptör varsa: biri sahte AP, diğeri deauth için. "
                            "Tek adaptörle de çalışır ama daha yavaş."),
    "config.adapter.refresh": "Listeyi yenile",

    "config.scan.title": "2 · TARAMA",
    "config.scan.desc": "Kısa süre hızlıdır, uzun süre bağlı cihazları da görür.",
    "config.scan.time": "Süre (sn):",
    "config.scan.band": "Bant:",
    "config.scan.channel": "Kanal:",
    "config.scan.channel_ph": "Tümü",
    "band.bg": "bg (2.4 GHz)",
    "band.a": "a (5 GHz)",
    "band.abg": "abg (Her ikisi)",

    "config.target.title": "3 · HEDEF",
    "config.target.desc": "Tablo satırına tıklarsan bu alanlar kendiliğinden dolar.",
    "config.target.ssid": "SSID:",
    "config.target.ssid_ph": "Ağ adı",
    "config.target.bssid": "BSSID:",
    "config.target.channel": "Kanal:",
    "config.target.none": "Henüz hedef seçilmedi.",

    "config.attack.title": "4 · SALDIRI",
    "config.attack.desc": "İki yöntem var; hangisini seçtiğinin açıklaması altında yazar.",
    "config.attack.type": "Tür:",
    "config.attack.portal": "Portal:",
    "config.attack.portal_loading": "Yükleniyor…",
    "config.attack.ap_service": "AP servisi:",
    "config.attack.deauth": "Deauth:",
    "config.attack.lang": "Dil:",
    "config.attack.timeout": "Timeout (dk):",
    "config.attack.timeout_ph": "Süresiz",
    "config.attack.desc_format": "{summary}\n\nGEREKEN: {need}\n\nSONRA: {next}",

    "attack.captive_portal.label": "Captive Portal – sahte giriş sayfası",
    "attack.captive_portal.summary": (
        "Hedef ağın birebir kopyasını (sahte AP) açar, bağlanan cihaza giriş sayfası "
        "gösterir ve girilen bilgileri kaydeder."
    ),
    "attack.captive_portal.need": (
        "Monitor mode + enjeksiyon destekleyen adaptör (ideali iki adaptör: biri sahte "
        "AP, diğeri deauth için). Portal seçilir, gerisini program kurar."
    ),
    "attack.captive_portal.next": (
        "Sahte AP açılır, hedef cihazlar düşürülür ve portal sayfası yayınlanır. Bir "
        "cihaz bağlanıp formu gönderdiğinde Şifreler sekmesine satır düşer."
    ),
    "attack.handshake_snooper.label": "Handshake Snooper – el sıkışma yakalama",
    "attack.handshake_snooper.summary": (
        "Hedef ağa bağlı cihazları düşürüp yeniden bağlanmaya zorlar ve WPA/WPA2 "
        "handshake'ini yakalar. Sonuç .cap dosyasıdır."
    ),
    "attack.handshake_snooper.need": (
        "Monitor mode + paket enjeksiyonu destekleyen adaptör. Hedef ağda en az bir "
        "bağlı cihaz olmalı; cihaz yoksa handshake de gelmez."
    ),
    "attack.handshake_snooper.next": (
        "Saldırı başlar, seçtiğin süre boyunca handshake aranır. Bulunursa Ağlar "
        "sekmesinde ✔ işareti ve logda 'Handshake yakalandı' satırı görünür."
    ),

    "target.hidden_ssid": "<Gizli Ağ>",
    "target.rec.dfs": (
        "DFS kanalı: sahte AP bu kanalda açılamaz. Portal için başka ağ seç, "
        "handshake için uygun."
    ),
    "target.rec.clients": (
        "{clients} cihaz bağlı: deauth atınca handshake/portal için sonuç alma şansı "
        "en yüksek ağ."
    ),
    "target.rec.no_clients": (
        "Bağlı cihaz görünmüyor: deauth atacak kimse yok, bu ağdan handshake veya "
        "portal ziyaretçisi gelmez."
    ),
    "portal.desc.self_capturing": (
        "Kendi kayıt sayfasını kullanır: ziyaretçinin yazdığı kullanıcı adı ve şifre "
        "doğrudan kaydedilir, handshake gerekmez."
    ),
    "portal.desc.stock": (
        "Stok portal: gönderilen şifreyi yakalanmış handshake ile doğrular, bu yüzden "
        "önce o ağın handshake'i gerekir."
    ),

    "help.text": """NASIL KULLANILIR – 5 ADIM

1) ADAPTÖR
   Ekranın sağındaki "Ortam Kontrolü" kartına bak. Kırmızı ✗ varsa
   saldırı başlamaz: adaptör monitor mode + paket enjeksiyonu
   desteklemeli ve program root yetkisiyle çalışmalı.

2) TARA
   "Tara" düğmesi yakındaki ağları listeler. Süre uzadıkça
   daha çok ağ görünür ama bağlı cihaz sayısı da o sürede toplanır.
   Cihaz yoksa deauth atacak kimse yok demektir.

3) HEDEF SEÇ
   Tabloda yeşil satır = en az bir cihaz bağlı. Satıra tıkla;
   program SSID/BSSID/kanal alanlarını kendisi doldurur ve
   altındaki satırda o ağın neden uygun (ya da uygun olmadığını)
   yazar.

4) SALDIR
   Captive Portal: hedef ağın birebir kopyasını açar, bağlanan
   cihaza seçtiğin portal sayfasını gösterir ve forma yazılanları
   kaydeder. Portalın kendisi kayıt yapıyorsa (Instagram şablonları)
   ayrıca şifre doğrulama adımı atlanır.
   Handshake Snooper: cihazları düşürüp yeniden bağlanmaya zorlar
   ve WPA/WPA2 handshake'ini yakalar; sonuç .cap dosyasıdır.

5) SONUÇ
   Captive Portal → "Şifreler" sekmesi
   Handshake Snooper → sekmelerin üstünde yeşil bir panel açılır. Kaydedilen
   .cap dosyasının tam yolunu gösterir ve iki düğme sunar: Captive Portal ile
   devam et ya da dosyayı sözlükle kır. Ağ, sonradan bulabilmen için ✔ işaretli
   kalır.

DOSYALAR
   Canlı durum : /tmp/capcapspace/capcap.status
   Girişler    : /tmp/capcapspace/instagram_credentials.log
   Handshake   : attacks/Handshake Snooper/handshakes/

NOTLAR
   • ! işaretli kanallar DFS: sahte AP orada açılamaz.
   • Deauth yöntemi otomatik seçilir (aireplay-ng); mdk4 istisnadır.
   • Saldırı sürerken "Durdur" ile her şey temiz kapatılır.
   • Arayüz dilini sağ üstteki EN / TR ile değiştirebilirsin.
""",

    "log.title": "Canlı log",
    "log.clear": "Temizle",
    "log.lines": "{count} satır",
    "log.env_line": "[ortam] {name}: {detail} → {hint}",
    "log.needs_root": "[!] Kurulum için root gerekli: sudo ./run_gui.sh",
    "log.install_done": "[+] Kurulum tamamlandı. Ortam yeniden kontrol ediliyor…",
    "log.install_failed": ("[!] Kurulum tamamlanamadı. Log'daki apt çıktısına bak; gerekirse "
                           "terminalde `sudo ./capcapwifi.sh --install-deps` çalıştır."),
    "log.install_first": ("[i] İlk kurulum: eksik paketler otomatik yükleniyor. Bu işlem birkaç "
                          "dakika sürebilir, pencereyi kapatmayın."),
    "log.handshake_archive_error": "[!] Handshake arşivi taranırken hata: {error}",
    "log.handshake_captured": "[+] HANDSHAKE YAKALANDI → {file} dosyasına kaydedildi.",
    "log.handshake_next": ("Handshake Snooper işi bitince kendini kapattı. Şifreler sekmesine geç, "
                           "handshake satırındaki \"Portal'da Kullan\" düğmesine bas: o ağ için "
                           "Captive Portal başlasın."),
    "log.target_selected": "[+] Hedef: {ssid} ({bssid}) CH{channel}",
    "log.target_has_handshake": "ℹ️ Bu ağ için önceden yakalanmış handshake mevcut; doğrudan Captive Portal başlatabilirsiniz.",
    "log.pmf_target": ("⚠️ {ssid} WPA3/PMF kullanıyor. Bu ağda deauth çerçeveleri "
                       "korunuyor; telefon ağdan düşmez ve captive portal adımı da "
                       "istemcileri çekemez. WPA2 bir ağ deneyin."),
    "log.scan_start": "[*] Tarama başlıyor – arayüz {iface}, {seconds} sn",
    "log.iface_auto": "otomatik",
    "log.no_target": "[!] Hedef yok. Tablodan bir ağ seç veya BSSID/SSID gir.",
    "log.no_target_hint": "Önce tablodan bir hedef seç: satıra tıkla ya da yeniden tara.",
    "log.no_portal": "[!] Portal şablonu seçilmedi.",
    "log.portal_info": "[i] Portal: {title} – {desc}",
    "log.attack_start": "[*] {attack} → {target}",
    "log.guide_portal_ready": ("[*] Captive Portal hazırlandı: Hedef {ssid} ({bssid}). "
                               "Aynı ağ adı, portal sayfasıyla birlikte yayınlanacak."),
    "log.guide_portal_autostart": "[*] Captive Portal şimdi başlatılıyor – bir cihaz bağlanınca portal sayfası açılır.",
    "log.guide_start_hint": "[*] Başlamak için alttaki 'Başlat' düğmesine basın.",
    "log.crack_start": "[*] Aircrack-ng wordlist kırma başlatılıyor… Hedef: {ssid} ({bssid})",

    "networks.title": "Yakındaki ağlar",
    "networks.search_ph": "Ağ adı veya BSSID ara…",
    "networks.legend": ("Yeşil rozet = bağlı cihaz var (deauth atılabilir)   ·   "
                        "✔ = handshake kayıtlı   ·   DFS = sahte AP açılamaz"),
    "networks.empty": ("Henüz ağ yok.\n\nSıradaki adım: sol panelden süreyi seç ve "
                       "“Tara” düğmesine bas."),
    "networks.hint_initial": "Önce “Tara” ile ağları listeleyin.",
    "networks.summary": ("{total} ağ, {clients} tanesinde bağlı cihaz, {handshakes} tanesinde "
                         "kayıtlı handshake. Bir satıra tıkla; alttaki alanlar kendiliğinden "
                         "dolar."),
    "networks.count": "{count} ağ",
    "networks.filtered_count": "{visible}/{total} ağ",
    "networks.clients": "{count} cihaz",
    "networks.no_clients": "cihaz yok",
    "networks.clients_short": "✓ cihaz bağlı",
    "networks.handshake_badge": "✔ Handshake",
    "networks.dfs_badge": "DFS",

    "creds.title": "Yakalanan Girişler & Handshake Arşivi",
    "console.title": "Saldırı konsolları (gömülü)",
    "console.hint": ("Saldırının açtığı tüm pencereler (DHCP, DNS, sahte AP, deauth, "
                     "portal) burada görünür. Daha önce ayrı terminal pencerelerinde "
                     "açılan çıktının aynısı."),
    "console.empty": "Henüz konsol yok. Saldırıyı başlatınca pencereler burada listelenir.",
    "console.waiting": "Saldırı penceresi bekleniyor…",
    "console.not_found": ("Henüz saldırı konsolu bulunamadı. Uzun süre boş kalırsa saldırı "
                          "başlamamış olabilir – sağdaki log paneline bak."),
    "console.buffer": "{name} · canlı akış",
    "creds.desc": ("Web portallarına yazılan şifreler ve dinleme ile yakalanan WPA .cap "
                   "el sıkışma dosyaları burada arşivlenir."),
    "creds.empty": ("Henüz giriş veya handshake yok.\n\n"
                    "• Bir cihaz sahte portala bağlanıp şifre girdiğinde burada belirir.\n"
                    "• Yakalanan WPA handshake dosyaları da burada listelenir."),
    "creds.copy": "Kopyala",
    "creds.handshake_header": "── Yakalanan WPA handshake (.cap) dosyaları ──",
    "creds.count_passwords": "{count} şifre",
    "creds.count_handshakes": "{count} handshake",
    "hs.unknown_ssid": "<Bilinmeyen Ağ>",
    "hs.use_portal": "Portal'da Kullan",
    "hs.crack": "Aircrack ile Kır",
    "hs.previous": "Önceden kayıtlı",

    "checklist.missing": ("{count} zorunlu bileşen eksik – log panelinde kurulum komutu "
                          "yazıyor"),
    "checklist.optional": "Hazır. {count} opsiyonel araç yok, temel akışlar çalışır.",
    "checklist.ready": "Her şey hazır.",

    "state.IDLE": "Hazır",
    "state.INSTALLING": "Kuruluyor",
    "state.STARTING": "Başlatılıyor",
    "state.SCANNING": "Taranıyor",
    "state.RUNNING": "Çalışıyor",
    "state.HANDSHAKE_CAPTURED": "Handshake yakalandı",
    "state.CREDENTIALS_FOUND": "Giriş yakalandı",
    "state.STOPPED": "Durduruldu",
    "state.ERROR": "Hata",

    "hint.installing": ("Gerekli paketler kuruluyor. Bitince kontrol otomatik yenilenecek; "
                        "pencereyi kapatmayın."),
    "hint.scanning": "Ağlar taranıyor… Bitince tablo dolacak, sonra hedef seç.",
    "hint.starting": ("Saldırı hazırlanıyor: adaptör monitor moda alınıyor, servisler "
                      "başlatılıyor."),
    "hint.running.portal": ("Sahte AP yayında. Cihaz bağlanıp formu gönderdiğinde Şifreler "
                            "sekmesine satır düşecek."),
    "hint.running.handshake": ("Deauth atılıyor, handshake bekleniyor. Yakalanınca dinleyici "
                               "kendini kapatır – bu normal."),
    "hint.credentials": "Giriş yakalandı! Şifreler sekmesinden kopyalayabilirsin.",
    "hint.handshake": ("Handshake yakalandı! Şifreler sekmesine geç: \"Portal'da Kullan\" ile "
                       "Captive Portal başlar, \"Aircrack ile Kır\" sözlük denemesi yapar."),
    "hint.error": "Hata: sağdaki log paneli ve ortam kontrolü kartına bak.",
    "hint.stopped": ("Durduruldu. Yeni bir tarama başlatabilir ya da hedefi "
                     "değiştirebilirsin."),
    "hint.env_checking": "Ortam kontrol ediliyor…",
    "hint.missing": "Eksik: {names} – sağdaki karttan ipucuna bak.",
    "hint.missing_more": "Eksik: {names} (+{extra} daha)",
    "hint.ready_scan": "Her şey hazır. Sıradaki adım: “Tara” ile ağları bul.",
    "hint.pick_row": ("Tabloda yeşil (bağlı cihazı olan) bir satıra tıkla; alanlar "
                      "kendiliğinden dolar."),
    "hint.target_ready": "Hedef hazır. “Başlat” ile devam et.",
    "hint.pmf_target": ("Bu ağ WPA3/PMF kullanıyor: deauth çerçeveleri yok sayılır, "
                        "cihazlar ağdan düşmez. WPA2 bir ağ seçin."),

    "env.root.name": "Root yetkisi",
    "env.root.ok": "yönetici olarak çalışıyor",
    "env.root.missing": "sudo olmadan çalışıyor",
    "env.root.hint": ("sudo ./run_gui.sh ile başlatın; monitor mode ve hostapd root ister."),
    "env.tool.missing": "kurulu değil",
    "env.optional.name": "{tool} (opsiyonel)",
    "env.optional.missing": "yok – bu özellik kullanılamaz",
    "env.adapter.name": "Kablosuz adaptör",
    "env.adapter.found": "{names}",
    "env.adapter.none": "bulunamadı",
    "env.adapter.hint": ("Adaptör takılı mı? VM kullanıyorsan USB passthrough yapılmış mı? "
                         "`iw dev` çıktısında görünmesi gerekir."),
    "env.monitor.name": "Monitor mode",
    "env.monitor.ready": "hazır",
    "env.monitor.pending": "henüz açılmadı (saldırı başında açılır)",
    "env.monitor.hint": "Sorun çıkarsa: sudo airmon-ng start <arayüz>",

    "purpose.aircrack-ng": "handshake doğrulama / .cap işleme",
    "purpose.airmon-ng": "adaptörü monitor moduna alma",
    "purpose.hostapd": "sahte access point",
    "purpose.lighttpd": "portal web sunucusu",
    "purpose.php-cgi": "portalın PHP uçları",
    "purpose.kea-dhcp4": "portalın DHCP sunucusu",
    "purpose.dnsspoof": "tüm alan adlarını portala yönlendirme",
    "purpose.mdk4": "deauth (alternatif yöntem)",
    "purpose.iw": "kanal / arayüz bilgisi",
    "purpose.xterm": "ayrı pencereler (yoksa -m/tmux kullanılır)",
    "purpose.tmux": "saldırıyı arka planda çalıştıran pencere altyapısı",
    "purpose.cowpatty": "stok portallar için şifre doğrulama",
    "purpose.pyrit": "alternatif şifre doğrulama",

    "ctrl.busy": "Zaten çalışan bir işlem var, önce durdurun.",
    "ctrl.install.busy": "Kurulum/saldırı zaten çalışıyor.",
    "ctrl.install.start": ("Paket kontrolü başlıyor. Eksik varsa otomatik kurulacak "
                           "(ilk seferde birkaç dakika sürebilir)."),
    "ctrl.crack.missing_file": "Handshake dosyası bulunamadı: {path}",
    "ctrl.crack.missing_wordlist": ("Wordlist bulunamadı: {path}. Kali'de "
                                    "'sudo gzip -d /usr/share/wordlists/rockyou.txt.gz' "
                                    "çalıştırabilirsiniz."),
    "ctrl.crack.started": "Aircrack-ng ile sözlük saldırısı başlatıldı…",
    "ctrl.crack.handshake": "   Handshake: {name}",
    "ctrl.crack.wordlist": "   Wordlist: {path}",
    "ctrl.crack.found": "{line}",
    "ctrl.crack.solved": "PAROLA ÇÖZÜLDÜ: {password}",
    "ctrl.crack.not_found": "Parola bu sözlük içinde bulunamadı.",
    "ctrl.crack.error": "Aircrack-ng hatası: {error}",
    "ctrl.scan.busy": "Zaten çalışan bir işlem var, önce durdurun.",
    "ctrl.scan.start": "Tarama başladı – arayüz: {iface}, süre: {seconds}s",
    "ctrl.attack.busy": "Zaten çalışan bir işlem var, önce durdurun.",
    "ctrl.attack.start": "Saldırı başlatılıyor: {attack} → {target}",
    "ctrl.attack.none": "hedef seçilmedi",
    "ctrl.stop.done": "İşlem durduruldu.",
    "ctrl.error.script_missing": ("capcapwifi.sh bulunamadı ya da sudo parola soruyor. "
                                  "GUI'yi `sudo ./run_gui.sh` ile başlatın."),
    "ctrl.error.spawn": "İşlem başlatılamadı: {error}",
    "ctrl.dep.check": "Paketler kontrol ediliyor…",
    "ctrl.dep.missing": "Eksik paketler kuruluyor: {tools}",
    "ctrl.dep.ok": "Tüm gerekli paketler hazır.",
    "ctrl.dep.failed": "Paket kurulumu başarısız oldu.",
    "ctrl.scan.complete": "Tarama tamamlandı – {count} ağ bulundu.",
    "ctrl.scan.found": "{count} ağ listelendi.",
    "ctrl.scan.empty": ("Tarama çıktısında ağ bulunamadı. Adaptör monitor mode destekliyor "
                        "mu? Süreyi artırmayı deneyin."),
    "ctrl.target": "Hedef: {ssid} ({bssid}) kanal {channel}",
    "ctrl.timeout": "Süre doldu ({minutes} dk), saldırı kapatılıyor.",
    "ctrl.handshake.congrats": "WPA 4-yönlü handshake başarıyla yakalandı ve doğrulandı!",
    "ctrl.handshake.location": "Kayıt konumu: {path}",
    "ctrl.handshake.whatnow": "ŞİMDİ NE YAPILMALI?",
    "ctrl.handshake.option1": ("   1. (Önerilen) Bu ağ için Captive Portal saldırısı başlatın. "
                               "Kurban şifre girdiğinde sistem yakalanan bu handshake ile "
                               "şifrenin doğruluğunu otomatik teyit eder!"),
    "ctrl.portal.join_hint": ("Telefonda Wi-Fi ayarlarını aç ve \"{ssid}\" ağını elle seç – kayıtlı "
                              "bir ağ, açık kopyasına kendiliğinden geçmez. Cihaz bağlanınca "
                              "portal sayfası açılır."),
    "ctrl.attack.failed": ("Saldırı kendini kapattı: {reason}"),
    "ctrl.ap_channel_fallback": ("AP kartı {frm}. kanalda yayın yapamıyor; sahte erişim "
                                 "noktası {to}. kanala alındı."),
    "ctrl.finish.handshake": ("Handshake Snooper handshake kaydedildiği için kendini kapattı. "
                              "Sen durdurmadın. Kayıtlı handshake'i Şifreler sekmesinden seçip "
                              "Captive Portal'ı başlatabilirsin."),
    "ctrl.finish.credentials": ("Captive Portal bir giriş yakaladığı için kendini kapattı. "
                                "Şifreler sekmesine bak."),
    "ctrl.handshake.autostop": ("Handshake kaydedilince Handshake Snooper kendini kapatır: sen bir şey "
                                "durdurmadın ve arkada çalışan işlem kalmadı. Captive Portal ayrıca "
                                "başlatılır."),
    "ctrl.handshake.option2": ("   2. Veya Şifreler sekmesinden aircrack-ng ile wordlist kırma "
                               "işlemi başlatabilirsiniz."),
    "ctrl.credential.new": "Yeni giriş yakalandı: {username} ({ip})",

    "humanize.deauth_directed": ("⚡ [Deauth] Kurban cihaza bağlantı kesme paketi "
                                 "gönderiliyor… ({line})"),
    "humanize.tracker": "🎯 Hedef takipçisi aktif: Kanal değişiklikleri izleniyor.",
    "humanize.aireplay": ("⚡ [Deauth] Aireplay-ng ile hedef cihazların bağlantısı geçici "
                          "kesiliyor…"),
    "humanize.airodump": "📡 Airodump-ng hedef kanalda dinlemeye başladı…",
    "humanize.cleanup": "✓ Temizlik tamamlandı: saldırı süreçleri kapatıldı, adaptör normal moda döndü.",
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {"en": EN, "tr": TR}

# ── updater (git tabanlı güncelleme) metinleri ──────────────────────
EN.update({
    "update.available": "Update available – {count} new commit(s) on GitHub",
    "update.btn_now": "Update now",
    "update.btn_later": "Later",
    "update.checking": "Checking for updates…",
    "update.uptodate": "You're on the latest version.",
    "update.not_repo": "Auto-update needs a git clone; this folder isn't a git repo.",
    "update.error": "Update check failed: {msg}",
    "update.doing": "Updating from GitHub…",
    "update.done": "Updated to the latest version. Please restart the app.",
    "update.failed": "Update failed: {msg}",
    "update.confirm.title": "Update",
    "update.confirm.body": "This resets the app to the latest GitHub version and discards any local changes in this folder. Continue?",
})
TR.update({
    "update.available": "Güncelleme mevcut – GitHub'da {count} yeni commit",
    "update.btn_now": "Şimdi güncelle",
    "update.btn_later": "Sonra",
    "update.checking": "Güncellemeler kontrol ediliyor…",
    "update.uptodate": "En güncel sürümdesin.",
    "update.not_repo": "Otomatik güncelleme için git klonu gerekir; bu klasör bir git deposu değil.",
    "update.error": "Güncelleme kontrolü başarısız: {msg}",
    "update.doing": "GitHub'dan güncelleniyor…",
    "update.done": "En son sürüme güncellendi. Lütfen uygulamayı yeniden başlat.",
    "update.failed": "Güncelleme başarısız: {msg}",
    "update.confirm.title": "Güncelle",
    "update.confirm.body": "Bu işlem uygulamayı GitHub'daki en son sürüme sıfırlar ve bu klasördeki yerel değişiklikleri siler. Devam edilsin mi?",
})

_current: str = DEFAULT_LANGUAGE


# ────────────────────────── API ─────────────────────────────────────


def available_languages() -> List[Tuple[str, str]]:
    return list(LANGUAGES)


def language_codes() -> List[str]:
    return [code for code, _neutral in LANGUAGES]


def read_pref(key: str, default: str = "") -> str:
    """Kayıtlı bir tercihi okur; bozuk/eksik dosya varsayılanı döndürür."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    value = str(data.get(key, "")).strip()
    return value or default


def write_pref(key: str, value: str) -> None:
    """Tek bir tercihi yazar; diğer anahtarlar korunur."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[key] = value
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        # A read-only HOME must not break the window; the choice simply is
        # not remembered.
        pass


def _read_preference() -> Optional[str]:
    """Saved choice, or None. Unreadable/corrupt files are ignored."""
    code = read_pref("language").lower()
    return code if code in TRANSLATIONS else None


def save_language(code: str) -> None:
    if code not in TRANSLATIONS:
        return
    write_pref("language", code)


def detect_language() -> str:
    """CAPCAP_GUI_LANG > saved preference > system locale > English."""
    override = os.environ.get("CAPCAP_GUI_LANG", "").strip().lower()
    if override in TRANSLATIONS:
        return override

    saved = _read_preference()
    if saved:
        return saved

    locale = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    ).strip().lower()
    if locale.startswith("tr"):
        return "tr"
    return DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def set_language(code: str) -> str:
    global _current
    code = (code or "").strip().lower()
    _current = code if code in TRANSLATIONS else DEFAULT_LANGUAGE
    return _current


def t(key: str, **kwargs) -> str:
    """Look a key up in the active language, falling back to English."""
    table = TRANSLATIONS.get(_current, EN)
    text = table.get(key)
    if text is None:
        text = EN.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


# The preference is applied as soon as the module is imported, so widgets
# created before any explicit set_language() call already render correctly.
set_language(detect_language())
