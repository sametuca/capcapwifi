"""
CapWifi GUI – Backend Controller

capwifi.sh'i `--auto` modunda bir alt süreç olarak çalıştırır, çıktısını
okur ve GUI'ye callback'lerle aktarır. Arayüz hiçbir zaman doğrudan süreç veya
dosya işlemez; her şey buradan geçer.

İki veri kanalı var:
  * stdout/stderr  – taranan ağ listesi, hata mesajları, ilerleme satırları
  * çalışma alanı  – $CAPCAPWorkspacePath/capcap.status (yapılandırılmış
                     olaylar) ve instagram_credentials.log (yakalanan girdiler)

Kullanıcıya gösterilen metinler i18n üzerinden gelir; GUI dili değişince
sonraki mesajlar da yeni dilde yazılır.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from i18n import get_language, t
from models import (
    AttackConfig,
    AttackState,
    AttackType,
    CapturedCredential,
    EnvironmentCheck,
    HandshakeFile,
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPT = REPO_DIR / "capwifi.sh"

#: capwifi.sh ile aynı varsayılan (capwifi.sh:19).
WORKSPACE = Path(os.environ.get("CAPCAPWorkspacePath", "/tmp/capcapspace"))
STATUS_FILE = WORKSPACE / "capcap.status"
CREDENTIAL_LOG = WORKSPACE / "instagram_credentials.log"

ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
TMUX_BAR_RE = re.compile(r"^\[CAPCAPWIF\d+:.*\]")
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

# `--scan-only` çıktısı sabit genişlikli sütunlar basar:
#   %-4s %-17s %-4s %-5s %-4s %-10s %-30.30s %s
# Alanları boşlukla ayırmak ESSID içindeki çift boşluklarda kayar, bu yüzden
# dilimliyoruz.
_SCAN_SLICES = {
    "channel": (0, 4),
    "bssid": (5, 22),
    "power": (23, 27),
    "clients": (28, 33),
    "quality": (34, 38),
    "enc": (39, 49),
    "vendor": (50, 80),
    "essid": (81, None),
}

#: Doğrulama için gerekli araçlar; açıklamaları "purpose.<tool>" anahtarında.
REQUIRED_TOOLS = (
    "aircrack-ng",
    "airmon-ng",
    "hostapd",
    "lighttpd",
    "php-cgi",
    "kea-dhcp4",
    "dnsspoof",
    "mdk4",
    "iw",
    # Attack runs are launched with `-m`, so tmux is the window backend.
    "tmux",
)

OPTIONAL_TOOLS = (
    "xterm",
    "cowpatty",
    "pyrit",
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def clean_log_line(raw: str) -> str:
    """Terminal kontrol karakterlerini ve gereksiz tmux alt bant gürültüsünü temizler."""
    line = strip_ansi(raw).strip()
    if not line:
        return ""
    # Ham tmux bar veya xterm başlık satırlarını temizle
    if TMUX_BAR_RE.match(line) and not any(k in line for k in ("Hedef", "WPA", "Handshake", "BSSID", "ESSID", "Deauth", "aireplay")):
        return ""
    # Terminal escape kırıntıları
    if line.startswith(("\033", "(B", "[?12l", "[?25h", "[?25l")):
        return ""
    # CLI veda/kapanış banner'ı ve teşekkür satırlarını GUI logundan filtrele
    if any(k in line for k in ("CAPWIFI 6.", "Capture The WiFi", "~~~~~", "tercih ettiğiniz için teşekkürler", "Thank you for using")):
        return ""
    return line


def humanize_log(line: str) -> tuple[str, str]:
    """Teknik terminal satırlarını son kullanıcının anlayabileceği açıklamalarla zenginleştirir."""
    if "Sending 64 directed Deauth" in line or "WPA handshake:" in line:
        return t("humanize.deauth_directed", line=line), "warn"
    if "Notice: Target tracker" in line:
        return t("humanize.tracker"), "info"
    if "aireplay-ng" in line and "deauth" in line:
        return t("humanize.aireplay"), "warn"
    if "airodump-ng" in line:
        return t("humanize.airodump"), "info"
    if "Temizlik başarıyla tamamlandı" in line or "Cleanup completed successfully" in line:
        return t("humanize.cleanup"), "success"
    return line, "raw"


def _int_or(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_scan_table(lines: List[str]) -> List[TargetCandidate]:
    """`--scan-only` çıktısındaki tabloyu TargetCandidate listesine çevirir."""
    candidates: List[TargetCandidate] = []
    started = False

    for raw in lines:
        line = strip_ansi(raw)
        if not started:
            # Başlık satırı: "CH BSSID PWR CLNT QLTY ENC VENDOR ESSID"
            if line.lstrip().startswith("CH") and "BSSID" in line:
                started = True
            continue

        # Ayırıcı satır ve boş satırlar atlanır.
        if not line.strip() or line.lstrip().startswith("---"):
            continue
        if "network(s) found" in line:
            break

        fields = {}
        for name, (start, end) in _SCAN_SLICES.items():
            fields[name] = line[start:end].strip() if end else line[start:].strip()

        if not MAC_RE.match(fields["bssid"]):
            continue

        candidates.append(
            TargetCandidate(
                bssid=fields["bssid"],
                channel=fields["channel"].rstrip("!"),
                power=_int_or(fields["power"], -100),
                clients=_int_or(fields["clients"], 0),
                quality=fields["quality"] or "??",
                enc=fields["enc"],
                vendor=fields["vendor"] if fields["vendor"] != "-" else "",
                essid=fields["essid"],
            )
        )

    return candidates


def parse_interface_table(lines: List[str]) -> List[WirelessInterface]:
    """`--list-interfaces` tablosunu ayrıştırır (başlık satırını atlar)."""
    ifaces: List[WirelessInterface] = []
    started = False
    for raw in lines:
        line = strip_ansi(raw)
        if not started:
            if line.lstrip().startswith("INTERFACE"):
                started = True
            continue
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ifaces.append(
            WirelessInterface(
                name=parts[0],
                state=parts[1] if len(parts) > 1 else "?",
                bands=parts[2] if len(parts) > 2 else "?",
                bus=parts[3] if len(parts) > 3 else "?",
                driver=parts[4] if len(parts) > 4 else "?",
                chipset=" ".join(parts[5:]) if len(parts) > 5 else "?",
            )
        )
    return ifaces


def parse_status_line(line: str) -> Optional[Dict[str, str]]:
    """`[2026-10-31T12:00:00] TARGET_SELECTED ssid=... bssid=...` biçimi.

    Değerler boşluk içerebilir (SSID'ler, "Handshake Snooper" gibi yol adları),
    bu yüzden alanlar yalnızca `anahtar=` deseninden hemen önce bölünür;
    düz `split()` değerleri ilk boşlukta kırardı.
    """
    match = re.match(r"\[.*?\]\s*(.+)", line)
    if not match:
        return None
    body = match.group(1).strip()
    head, _, rest = body.partition(" ")
    if not head:
        return None
    event: Dict[str, str] = {"type": head}
    for token in re.split(r"\s+(?=[A-Za-z_][A-Za-z0-9_]*=)", rest.strip()):
        if "=" in token:
            key, _, value = token.partition("=")
            event[key] = value
    return event


class CapWifiController:
    """
    Hibrit denetleyici: capwifi.sh'i CLI bayraklarıyla `--auto` modunda
    çalıştırır. Arayüz şu callback'lerle bilgilendirilir:

        on_state_change(AttackState)
        on_log(message, level)          level: info|success|warn|error|raw
        on_candidates([TargetCandidate])
        on_credential(CapturedCredential)
        on_environment([EnvironmentCheck])
        on_dependency_install(bool)
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._state = AttackState.IDLE
        self._candidates: List[TargetCandidate] = []
        self._credentials: List[CapturedCredential] = []
        self._watcher: Optional[threading.Thread] = None
        self._stop_watching = threading.Event()
        self._pending_output: List[str] = []
        self._install_result: Optional[bool] = None
        self._handshake_detected = False
        # Başarıyla biten bir saldırıdan sonra süreç kapanınca durum rozeti
        # "Durduruldu"ya düşmemeli; kullanıcı bir şey durdurmadı.
        self._success_state: Optional[AttackState] = None
        self._last_config: Optional[AttackConfig] = None
        self._status_offset = 0

        self.on_state_change: Callable[[AttackState], None] = lambda s: None
        self.on_log: Callable[[str, str], None] = lambda msg, level: None
        self.on_candidates: Callable[[List[TargetCandidate]], None] = lambda c: None
        self.on_credential: Callable[[CapturedCredential], None] = lambda c: None
        self.on_handshake: Callable[[HandshakeFile], None] = lambda h: None
        self.on_environment: Callable[[List[EnvironmentCheck]], None] = lambda c: None
        self.on_dependency_install: Callable[[bool], None] = lambda ok: None

    # ── durum ───────────────────────────────────────────────────

    @property
    def state(self) -> AttackState:
        return self._state

    @property
    def candidates(self) -> List[TargetCandidate]:
        return list(self._candidates)

    @property
    def credentials(self) -> List[CapturedCredential]:
        return list(self._credentials)

    @property
    def is_busy(self) -> bool:
        return self.state in (
            AttackState.INSTALLING,
            AttackState.SCANNING,
            AttackState.STARTING,
            AttackState.RUNNING,
        )

    @property
    def is_root(self) -> bool:
        return os.name != "nt" and os.geteuid() == 0

    # ── ortam ───────────────────────────────────────────────────

    def check_environment(self, background: bool = True) -> None:
        if background:
            threading.Thread(target=self._check_environment, daemon=True).start()
        else:
            self._check_environment()

    def _check_environment(self) -> None:
        checks: List[EnvironmentCheck] = []

        checks.append(
            EnvironmentCheck(
                name=t("env.root.name"),
                ok=self.is_root,
                detail=t("env.root.ok") if self.is_root else t("env.root.missing"),
                hint=t("env.root.hint"),
            )
        )

        for tool in REQUIRED_TOOLS:
            path = shutil.which(tool)
            checks.append(
                EnvironmentCheck(
                    name=tool,
                    ok=bool(path),
                    detail=t(f"purpose.{tool}") if path else t("env.tool.missing"),
                    hint=f"sudo apt install -y {tool}",
                )
            )

        for tool in OPTIONAL_TOOLS:
            path = shutil.which(tool)
            checks.append(
                EnvironmentCheck(
                    name=t("env.optional.name", tool=tool),
                    ok=bool(path),
                    detail=t(f"purpose.{tool}") if path else t("env.optional.missing"),
                    hint=f"sudo apt install -y {tool}",
                    required=False,
                )
            )

        try:
            ifaces = self.list_interfaces()
        except Exception:
            ifaces = []
        wireless = [i for i in ifaces if i.name]
        checks.append(
            EnvironmentCheck(
                name=t("env.adapter.name"),
                ok=bool(wireless),
                detail=(t("env.adapter.found", names=", ".join(i.name for i in wireless))
                        if wireless else t("env.adapter.none")),
                hint=t("env.adapter.hint"),
            )
        )

        monitor_ok = any("monitor" in i.state.lower() for i in wireless)
        checks.append(
            EnvironmentCheck(
                name=t("env.monitor.name"),
                ok=monitor_ok,
                detail=t("env.monitor.ready") if monitor_ok else t("env.monitor.pending"),
                hint=t("env.monitor.hint"),
            )
        )

        self.on_environment(checks)

    # ── kurulum ─────────────────────────────────────────────────

    def missing_required_tools(self) -> List[str]:
        """PATH'te bulunamayan zorunlu araçlar."""
        return [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]

    def install_dependencies(self, language: str = "") -> None:
        """Eksik paketleri kurar (`--install-deps`), çıktı log paneline akar."""
        if self.is_busy:
            self._log(t("ctrl.install.busy"), "warn")
            return

        if not language:
            language = "tur" if get_language() == "tr" else "en"

        self._install_result = None
        args = [
            "sudo", "-n", str(SCRIPT),
            "--install-deps",
            "--auto",
            "-k",
            "-l", language,
        ]
        self._set_state(AttackState.INSTALLING)
        self._log(t("ctrl.install.start"), "info")
        self._run_async(args, mode="install")

    # ── listeler ────────────────────────────────────────────────

    def list_interfaces(self) -> List[WirelessInterface]:
        try:
            result = subprocess.run(
                ["sudo", "-n", str(SCRIPT), "--list-interfaces"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        if result.returncode != 0:
            return []
        return parse_interface_table(result.stdout.splitlines())

    def list_portals(self) -> List[PortalSite]:
        sites_dir = REPO_DIR / "attacks" / "Captive Portal" / "sites"
        portals: List[PortalSite] = []
        if not sites_dir.is_dir():
            return portals
        for portal_path in sorted(sites_dir.iterdir()):
            if not portal_path.name.endswith(".portal"):
                continue
            stem = portal_path.name[: -len(".portal")]
            parts = stem.rsplit("_", 1)
            name = parts[0] if len(parts) == 2 else stem
            lang = parts[1] if len(parts) == 2 else "en"
            portals.append(
                PortalSite(
                    site_id=stem,
                    name=name,
                    lang=lang,
                    path=str(portal_path),
                    has_submit=(portal_path / "submit.php").exists(),
                )
            )
        return portals

    def list_handshakes(self) -> List[HandshakeFile]:
        folder = REPO_DIR / "attacks" / "Handshake Snooper" / "handshakes"
        res: List[HandshakeFile] = []
        if not folder.is_dir():
            return res
        for p in sorted(folder.glob("*.cap"), key=lambda x: x.stat().st_mtime, reverse=True):
            ssid = ""
            bssid = ""
            stem = p.stem
            if "-" in stem:
                parts = stem.rsplit("-", 1)
                ssid = parts[0]
                bssid = parts[1]
            else:
                ssid = stem
            stat = p.stat()
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
            res.append(HandshakeFile(
                filename=p.name,
                filepath=str(p),
                ssid=ssid,
                bssid=bssid,
                size_bytes=stat.st_size,
                created_at=mtime_str,
            ))
        return res

    def crack_handshake(
        self,
        cap_path: str,
        bssid: str = "",
        wordlist_path: str = "/usr/share/wordlists/rockyou.txt",
        on_done: Callable[[bool, str], None] = None,
    ) -> None:
        """Aircrack-ng ile arka planda wordlist kırma işlemi başlatır."""
        if not os.path.exists(cap_path):
            self._log(t("ctrl.crack.missing_file", path=cap_path), "error")
            return
        if not os.path.exists(wordlist_path):
            self._log(t("ctrl.crack.missing_wordlist", path=wordlist_path), "warn")
            return

        self._log(t("ctrl.crack.started"), "info")
        self._log(t("ctrl.crack.handshake", name=Path(cap_path).name), "info")
        self._log(t("ctrl.crack.wordlist", path=wordlist_path), "info")

        def _worker():
            cmd = ["aircrack-ng"]
            if bssid:
                cmd += ["-b", bssid]
            cmd += ["-w", wordlist_path, cap_path]
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
                )
                found_pw = ""
                for raw in proc.stdout:
                    clean = strip_ansi(raw.strip())
                    if not clean:
                        continue
                    if "KEY FOUND!" in clean:
                        self._log(t("ctrl.crack.found", line=clean), "success")
                        m = re.search(r"KEY FOUND!\s*\[\s*(.*?)\s*\]", clean)
                        if m:
                            found_pw = m.group(1)
                    elif any(w in clean for w in ("Current passphrase:", "keys tested", "Master Key")):
                        pass
                    else:
                        self._log(clean, "raw")
                proc.wait()
                if found_pw:
                    self._log(t("ctrl.crack.solved", password=found_pw), "success")
                    if on_done:
                        on_done(True, found_pw)
                else:
                    self._log(t("ctrl.crack.not_found"), "warn")
                    if on_done:
                        on_done(False, "")
            except Exception as e:
                self._log(t("ctrl.crack.error", error=e), "error")
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    # ── tarama ──────────────────────────────────────────────────

    def start_scan(
        self,
        interface: str,
        scan_time: int = 30,
        channel: str = "",
        band: str = "bg",
    ) -> None:
        if self.is_busy:
            self._log(t("ctrl.scan.busy"), "warn")
            return

        args = [
            "sudo",
            "-n",
            str(SCRIPT),
            "--scan-only",
            "--scan-time",
            str(scan_time),
            "-k",
        ]
        if interface:
            args += ["--interface", interface]
        if channel:
            args += ["-c", channel]
        if band:
            args += ["--band", band]

        self._set_state(AttackState.SCANNING)
        self._log(
            t("ctrl.scan.start", iface=interface or t("log.iface_auto"),
              seconds=scan_time),
            "info",
        )
        self._run_async(args, mode="scan")

    # ── saldırı ─────────────────────────────────────────────────

    def start_attack(self, config: AttackConfig) -> None:
        if self.is_busy:
            self._log(t("ctrl.attack.busy"), "warn")
            return

        attack_flag = (
            "Captive_Portal"
            if config.attack_type is AttackType.CAPTIVE_PORTAL
            else "Handshake_Snooper"
        )
        args = [
            "sudo",
            "-n",
            str(SCRIPT),
            "--auto",
            "-k",
            "-m",
            "-a",
            attack_flag,
            "-l",
            config.language,
            "--band",
            config.band,
        ]
        if config.interface:
            args += ["--interface", config.interface]
        if config.target_bssid:
            args += ["-b", config.target_bssid]
        if config.target_essid:
            args += ["-e", config.target_essid]
        if config.target_channel:
            args += ["-c", config.target_channel]
        if config.jammer_interface:
            args += ["--jammer-interface", config.jammer_interface]
        if config.ap_interface:
            args += ["--ap-interface", config.ap_interface]
        if config.ap_channel:
            args += ["--ap-channel", config.ap_channel]
        if config.ap_service:
            args += ["--ap-service", config.ap_service]
        if config.deauth_method:
            args += ["--deauth-method", config.deauth_method]
        if config.reg_domain:
            args += ["--reg-domain", config.reg_domain]
        if config.attack_type is AttackType.CAPTIVE_PORTAL and config.portal_site:
            args += ["--site", config.portal_site]
        if config.timeout_minutes:
            args += ["--timeout", str(config.timeout_minutes)]

        self._last_config = config
        self._handshake_detected = False
        self._success_state = None
        self._set_state(AttackState.STARTING)
        self._log(
            t("ctrl.attack.start", attack=config.attack_type.value,
              target=(config.target_essid or config.target_bssid
                      or t("ctrl.attack.none"))),
            "info",
        )
        self._run_async(args, mode="attack")

    # ── gömülü konsollar (tmux panelleri) ───────────────────────
    CONSOLE_SESSION = "CAPWIFI"

    def _tmux(self, args: List[str]) -> str:
        """tmux komutunu çalıştır, stdout'u döndür; olmazsa boş dizge.

        Neden iki deneme: GUI normalde root çalışır (gui/root_gate.py) ama
        ``sudo -n`` parolasız sudo izni olmayan kurulumlarda (ya da sudo hiç
        yokken) sessizce başarısız oluyor ve konsol sekmesi sonsuza kadar boş
        kalıyordu. Önce sudo ile (tmux sunucusu root'a aitse), olmazsa doğrudan
        tmux ile deniyoruz.
        """
        commands = []
        if os.name != "nt":
            commands.append(["sudo", "-n", "tmux"] + args)
        commands.append(["tmux"] + args)
        for command in commands:
            try:
                proc = subprocess.run(command, capture_output=True, text=True,
                                      timeout=4)
            except (OSError, subprocess.SubprocessError):
                continue
            if proc.returncode == 0:
                return proc.stdout
        return ""

    def console_windows(self) -> List[tuple]:
        """Saldırının açtığı tmux pencereleri: [(index, name), ...].

        Yalnızca ``CAPWIFI`` oturumuna bakmak yetmiyordu: lib/WindowUtils.sh
        (satır 25-39) eski bir CAPWIFI oturumu duruyorsa yeni oturumu
        ``CAPCAP_$$`` adıyla açıyor ve ardından gelen
        ``tmux rename-session CAPWIFI`` "duplicate session" ile başarısız
        oluyor. O durumda tüm saldırı pencereleri CAPCAP_* içinde kalıyor,
        CAPWIFI'de ise yalnızca eskimiş pencere var; sekme bu yüzden boş
        görünüyordu. Burada iki adı da tarıyoruz.
        """
        raw = self._tmux(["list-windows", "-a", "-F",
                          "#{session_name}\t#{window_index}\t#{window_name}"])
        if not raw:
            return []
        by_session: Dict[str, List[tuple]] = {}
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            session, index, name = (part.strip() for part in parts)
            if session != self.CONSOLE_SESSION and not session.startswith(
                    "CAPCAP_"):
                continue
            by_session.setdefault(session, []).append((index, name))
        if not by_session:
            return []
        # Eski bir CAPWIFI oturumu duruyorsa içinde tek bir eskimiş pencere
        # kalıyor; asıl saldırı ise CAPCAP_* oturumunda. Bu yüzden "CAPWIFI
        # varsa onu kullan" yetmiyor: en çok pencereye sahip oturumu seçiyoruz,
        # eşitlikte CAPWIFI kazanıyor (normal durum).
        session = max(by_session,
                      key=lambda name: (len(by_session[name]),
                                        name == self.CONSOLE_SESSION))
        self._console_session = session
        return by_session[session]

    def capture_console(self, index: str) -> str:
        """Bir pencerenin son ekranını metin olarak döndürür."""
        session = getattr(self, "_console_session", self.CONSOLE_SESSION)
        target = f"{session}:{index}"
        text = self._tmux(["capture-pane", "-p", "-J", "-S", "-160",
                           "-t", target])
        if not text and session != self.CONSOLE_SESSION:
            # Pencere bu arada CAPWIFI'ye taşınmış olabilir.
            text = self._tmux(["capture-pane", "-p", "-J", "-S", "-160",
                               "-t", f"{self.CONSOLE_SESSION}:{index}"])
        return text.rstrip()

    def stop(self) -> None:
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except OSError:
                    pass
            self._log(t("ctrl.stop.done"), "warn")

        self._stop_watching.set()
        # Yakalanan bir handshake/şifre varsa rozet başarı durumunda kalsın.
        self._set_state(self._success_state or AttackState.STOPPED)

    # ── iç işleyiş ──────────────────────────────────────────────

    def _set_state(self, state: AttackState) -> None:
        self._state = state
        self.on_state_change(state)

    def _log(self, msg: str, level: str = "info") -> None:
        self.on_log(msg, level)

    def _run_async(self, args: List[str], mode: str) -> None:
        self._pending_output = []
        threading.Thread(target=self._run, args=(args, mode), daemon=True).start()

    def _run(self, args: List[str], mode: str) -> None:
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["LANG"] = env.get("LANG", "C.UTF-8")

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except FileNotFoundError:
            self._log(t("ctrl.error.script_missing"), "error")
            self._set_state(AttackState.ERROR)
            # Kurulum çalışırken çağrıldıysa ilerleme çubuğu sonsuza kadar
            # dönmesin: sonucu her durumda bildir.
            if mode == "install":
                self.on_dependency_install(False)
            return
        except OSError as exc:
            self._log(t("ctrl.error.spawn", error=exc), "error")
            self._set_state(AttackState.ERROR)
            if mode == "install":
                self.on_dependency_install(False)
            return

        with self._lock:
            self._proc = proc

        # Süreç anında ölmüşse (ör. `sudo -n` parola istiyor ve hemen
        # çıkıyor) döngüye girip sonsuza kadar beklemeyelim: hiç satır
        # gelmezse durum SCANNING'de kilitli kalıyordu.
        early = self._detect_immediate_exit(proc, mode)
        if early:
            return

        # Yapılandırılmış olaylar ve yakalanan girdiler için dosya izleyici.
        self._stop_watching.clear()
        self._watcher = threading.Thread(
            target=self._watch_workspace, args=(mode,), daemon=True
        )
        self._watcher.start()

        failure: Optional[BaseException] = None
        try:
            for raw in proc.stdout:  # type: ignore[union-attr]
                line = clean_log_line(raw.rstrip())
                if not line:
                    continue
                self._pending_output.append(line)
                h_line, h_level = humanize_log(line)
                self._log(h_line, h_level)
                # Tek bir bozuk satır taramanın tamamını düşürmemeli:
                # ayrıştırma hatasını loglayıp sonraki satıra geçiyoruz.
                try:
                    self._handle_status_line(line, mode)
                except Exception as exc:  # noqa: BLE001 - satır bazlı koruma
                    self._log(t("ctrl.error.parse", error=exc), "warn")
        except Exception as exc:  # noqa: BLE001 - süreç okuma hatası
            failure = exc
            self._log(t("ctrl.error.read", error=exc), "error")
        finally:
            proc.wait()
            self._stop_watching.set()
            if self._watcher:
                self._watcher.join(timeout=2)

        # Aşağıdaki bitirme adımları HER durumda çalışmalı. Daha önce bu blok
        # `finally` dışındaydı: döngüde bir istisna olursa durum SCANNING'de
        # kalıyor, düğmeler kilitli kalıyor ve arayüz "Tara hiçbir şey
        # yapmıyor" hâline geliyordu.
        try:
            self._finish(mode, proc, failure)
        except Exception as exc:  # noqa: BLE001 - arayüzü asla kilitleme
            self._log(t("ctrl.error.finalize", error=exc), "error")
            self._set_state(AttackState.ERROR)

    def _finish(self, mode: str, proc, failure: Optional[BaseException]) -> None:
        """Süreç bittikten sonra durumu kesin bir sonuca bağlar.

        Buradaki tek kural: arayüz asla belirsiz durumda bırakılmaz. Döngüde
        bir istisna olduysa (``failure`` doluysa) sonuç hata sayılır, çünkü
        başarı iddiası doğrulanamamıştır.
        """
        if mode == "scan":
            self._finish_scan()
            if failure is not None:
                self._set_state(AttackState.ERROR)
        elif mode == "install":
            self._drain_workspace(mode)
            ok = self._install_result
            if ok is None:
                ok = proc.returncode == 0 and failure is None
            self._install_result = ok
            self._set_state(AttackState.IDLE if ok else AttackState.ERROR)
            self.on_dependency_install(bool(ok))
        else:
            # Süreç bittiğinde dosyada kalan satırları bir kez daha oku.
            self._drain_workspace(mode)
            if self._state in (AttackState.RUNNING, AttackState.STARTING,
                               AttackState.SCANNING):
                # Süreç, başarı durumu işlenmeden önce kapanabilir (yarış);
                # o zaman kullanıcıya "durduruldu" demek yanıltıcı olur.
                if self._success_state is not None:
                    self._set_state(self._success_state)
                elif failure is not None or proc.returncode != 0:
                    self._set_state(AttackState.ERROR)
                else:
                    self._set_state(AttackState.STOPPED)

    def _handle_status_line(self, line: str, mode: str) -> None:
        event = parse_status_line(line)
        if not event:
            return
        kind = event.get("type", "")

        if kind == "SCAN_START":
            self._set_state(AttackState.SCANNING)
        elif kind == "DEP_CHECK":
            self._log(t("ctrl.dep.check"), "info")
        elif kind == "DEP_MISSING":
            tools = event.get("tools", "")
            self._log(t("ctrl.dep.missing", tools=tools), "warn")
        elif kind == "DEP_OK":
            self._install_result = True
            self._log(t("ctrl.dep.ok"), "success")
        elif kind == "DEP_FAILED":
            self._install_result = False
            self._log(t("ctrl.dep.failed"), "error")
        elif kind == "SCAN_COMPLETE":
            count = event.get("candidates", "?")
            self._log(t("ctrl.scan.complete", count=count), "success")
        elif kind == "TARGET_SELECTED":
            self._log(
                t("ctrl.target",
                  ssid=event.get("ssid", "?"),
                  bssid=event.get("bssid", "?"),
                  channel=event.get("channel", "?")),
                "info",
            )
        elif kind == "ATTACK_STARTED":
            self._set_state(AttackState.RUNNING)
            cfg = self._last_config
            if cfg is not None and cfg.attack_type is AttackType.CAPTIVE_PORTAL:
                # Telefon kayıtlı bir WPA2 ağının açık kopyasına kendiliğinden
                # geçmez; kullanıcı SSID'yi elle seçmeli.
                self._log(t("ctrl.portal.join_hint",
                            ssid=cfg.target_essid or "?"), "info")
        elif kind == "AP_CHANNEL_FALLBACK":
            self._log(t("ctrl.ap_channel_fallback",
                        frm=event.get("from", "?"),
                        to=event.get("to", "?")), "warn")
        elif kind == "ATTACK_FAILED":
            reason = event.get("reason", "").strip()
            self._success_state = None
            self._log(t("ctrl.attack.failed", reason=reason or "?"), "error")
            self._set_state(AttackState.ERROR)
        elif kind == "ATTACK_FINISHED":
            reason = event.get("reason", "")
            if reason == "handshake":
                self._success_state = AttackState.HANDSHAKE_CAPTURED
                self._log(t("ctrl.finish.handshake"), "warn")
            elif reason == "credentials":
                self._success_state = AttackState.CREDENTIALS_FOUND
                self._log(t("ctrl.finish.credentials"), "success")
        elif kind == "TIMEOUT":
            self._log(t("ctrl.timeout", minutes=event.get("minutes", "?")), "warn")
        elif kind == "HANDSHAKE_CAPTURED":
            path = event.get("path", "")
            self._handle_handshake_captured(path)
        elif kind == "RESULT":
            self._handle_result(event)

    def _handle_handshake_captured(self, path_str: str) -> None:
        # Aynı yakalama üç kanaldan gelebilir: başarı bayrağı, HANDSHAKE_CAPTURED
        # durum satırı ve RESULT handshake= satırı. Kullanıcıya bir kez göster.
        if self._handshake_detected:
            return
        self._handshake_detected = True

        p = Path(path_str) if path_str else None
        ssid = ""
        bssid = ""
        size = 0
        mtime_str = time.strftime("%H:%M:%S")
        if p and p.exists():
            size = p.stat().st_size
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
            stem = p.stem
            if "-" in stem:
                parts = stem.rsplit("-", 1)
                ssid = parts[0]
                bssid = parts[1]
            else:
                ssid = stem
        elif self._last_config:
            ssid = self._last_config.target_essid
            bssid = self._last_config.target_bssid
            path_str = str(REPO_DIR / "attacks" / "Handshake Snooper" / "handshakes" / f"{ssid}-{bssid}.cap")

        hf = HandshakeFile(
            filename=p.name if p else f"{ssid}.cap",
            filepath=path_str,
            ssid=ssid,
            bssid=bssid,
            size_bytes=size,
            created_at=mtime_str,
        )
        self._success_state = AttackState.HANDSHAKE_CAPTURED
        self._set_state(AttackState.HANDSHAKE_CAPTURED)
        self._log(f"🎉 {t('ctrl.handshake.congrats')}", "success")
        self._log(f"📁 {t('ctrl.handshake.location', path=path_str)}", "info")
        self._log(t("ctrl.handshake.autostop"), "info")
        self._log(f"💡 {t('ctrl.handshake.whatnow')}", "warn")
        self._log(t("ctrl.handshake.option1"), "info")
        self._log(t("ctrl.handshake.option2"), "info")
        self.on_handshake(hf)

    def _handle_result(self, event: Dict[str, str]) -> None:
        password = event.get("password")
        handshake = event.get("handshake")
        if password:
            username = event.get("username", "")
            # The portal already appended this login to
            # instagram_credentials.log, which the watcher reads live; adding
            # the RESULT line too would show every capture twice.
            if not any(c.password == password
                       and (not username or c.username == username)
                       for c in self._credentials):
                cred = CapturedCredential(
                    timestamp=time.strftime("%H:%M:%S"),
                    ssid=event.get("ssid", ""),
                    bssid=event.get("bssid", ""),
                    password=password,
                    username=username,
                )
                self._credentials.append(cred)
                self.on_credential(cred)
            self._success_state = AttackState.CREDENTIALS_FOUND
            self._set_state(AttackState.CREDENTIALS_FOUND)
        elif handshake:
            self._handle_handshake_captured(handshake)

    def _detect_immediate_exit(self, proc, mode: str) -> bool:
        """Süreç daha ilk satır gelmeden ölmüşse True döner ve durumu kapatır.

        En sık nedeni ``sudo -n`` parola istemesidir: komut hemen hata verip
        çıkar, çıktı boştur ve GUI "taranıyor" ekranında kilitli kalır.
        Kullanıcı için bu, "Tara'ya bastım hiçbir şey olmuyor" demektir.
        """
        code = proc.poll()
        if code is None:
            return False
        # Çıktısı olan süreçler normal yoldan işlenir (aşağıdaki döngü
        # boşaltır). Burada yalnızca hiçbir şey yazmayan süreç ele alınır.
        try:
            has_output = bool(proc.stdout and proc.stdout.peek(1))
        except Exception:
            has_output = False
        if has_output:
            return False

        self._stop_watching.set()
        if code == 0:
            self._finish(mode, proc, None)
            return True

        self._log(t("ctrl.error.early_exit", code=code), "error")
        self._log(t("ctrl.error.needs_root"), "warn")
        if mode == "install":
            self._install_result = False
            self._set_state(AttackState.ERROR)
            self.on_dependency_install(False)
        else:
            self._set_state(AttackState.ERROR)
        return True

    def _watch_workspace(self, mode: str) -> None:
        """Süreç çalışırken status ve kimlik dosyalarını izler.

        Bu thread arka planda sessizce çalışır; bir kez istisna atarsa
        yakalanmaz ve süreç boyunca hiçbir olay iletilmez. Bu yüzden her tur
        korunuyor: çalışma alanı root'a aitse (GUI root değilken) okuma
        ``PermissionError`` verebilir, bu da kullanıcıya ancak konsolda
        "Exception in thread" olarak görünürdü.
        """
        # Script her çalışmanın başında capcap.status'u sıfırlar; eski
        # offset'i taşımak yeni satırları yutardı.
        self._status_offset = 0
        cred_offset = self._file_size(CREDENTIAL_LOG)
        warned = False

        while not self._stop_watching.is_set():
            try:
                if self._safe_exists(STATUS_FILE):
                    self._status_offset = self._read_new_lines(
                        STATUS_FILE, self._status_offset,
                        self._handle_status_line, mode)

                if self._safe_exists(CREDENTIAL_LOG):
                    cred_offset = self._read_new_lines(
                        CREDENTIAL_LOG, cred_offset,
                        self._handle_credential_line, mode)

                flag_file = WORKSPACE / "handshake_success.flag"
                if self._safe_exists(flag_file) and not self._handshake_detected:
                    folder = (REPO_DIR / "attacks" / "Handshake Snooper"
                              / "handshakes")
                    caps = (sorted(folder.glob("*.cap"),
                                   key=lambda x: x.stat().st_mtime,
                                   reverse=True)
                            if folder.is_dir() else [])
                    recent_cap = (str(caps[0]) if caps
                                  else str(WORKSPACE / "capture" / "recent.cap"))
                    self._handle_handshake_captured(recent_cap)
            except OSError as exc:
                # İzin/erişim hatası: bir kez uyar, izlemeye devam et.
                # (Döngüyü öldürmek, süreç bitene kadar hiçbir olayın
                # gelmemesi demekti.)
                if not warned:
                    warned = True
                    self._log(t("ctrl.watch.error", error=exc), "warn")
            except Exception as exc:  # noqa: BLE001 - thread asla ölmesin
                self._log(t("ctrl.watch.error", error=exc), "warn")

            self._stop_watching.wait(0.4)

    @staticmethod
    def _safe_exists(path: Path) -> bool:
        """``Path.exists()`` erişim hatasını yutar; izleyiciyi düşürmez."""
        try:
            return path.exists()
        except OSError:
            return False

    def _drain_workspace(self, mode: str) -> None:
        """Süreç bittikten sonra son satırları kaçırmamak için bir kez daha oku."""
        self._status_offset = self._read_new_lines(
            STATUS_FILE, getattr(self, "_status_offset", 0),
            self._handle_status_line, mode,
        )

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _read_new_lines(self, path: Path, offset: int, handler, mode: str) -> int:
        # Dosya küçüldüyse (truncate/rotation) baştan oku; aksi hâlde seek
        # dosya sonunun ötesine gider ve yeni olaylar hiç görünmez.
        if self._file_size(path) < offset:
            offset = 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                for line in handle:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    # Tek bir bozuk satır kalanların okunmasını engellemesin.
                    try:
                        handler(line, mode)
                    except Exception as exc:  # noqa: BLE001
                        self._log(t("ctrl.error.parse", error=exc), "warn")
                return handle.tell()
        except OSError:
            return offset

    def _handle_credential_line(self, line: str, _mode: str) -> None:
        """instagram_credentials.log: zaman · IP · kullanıcı · şifre · UA"""
        parts = line.split("\t")
        if len(parts) < 4:
            return
        cred = CapturedCredential(
            timestamp=parts[0][11:19] if len(parts[0]) > 19 else parts[0],
            ssid="",
            bssid="",
            username=parts[2],
            password=parts[3],
            client_ip=parts[1],
        )
        self._credentials.append(cred)
        self.on_credential(cred)
        self._log(t("ctrl.credential.new", username=cred.username,
                    ip=cred.client_ip), "success")
        self._success_state = AttackState.CREDENTIALS_FOUND
        self._set_state(AttackState.CREDENTIALS_FOUND)

    def _finish_scan(self) -> None:
        candidates = parse_scan_table(self._pending_output)
        if candidates:
            self._candidates = candidates
            self.on_candidates(candidates)
            self._log(t("ctrl.scan.found", count=len(candidates)), "success")
        else:
            # Boş sonuç da bir sonuçtur: arayüze bildirilmezse kullanıcı
            # "Tara'ya bastım, hiçbir şey olmadı" der. Boş liste göndermek
            # tabloyu temizler ve yönlendirme metnini devreye alır.
            self._candidates = []
            self.on_candidates([])
            self._log(t("ctrl.scan.empty"), "warn")
            self._log(t("ctrl.scan.empty_next"), "info")
        self._set_state(AttackState.STOPPED)
