"""
capcapwifi GUI – Backend Controller
Runs capcapwifi.sh asynchronously with --auto flags, parses status output,
and emits events to the GUI layer via callbacks.
"""
from __future__ import annotations

import os
import re
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
    PortalSite,
    TargetCandidate,
    WirelessInterface,
)

REPO_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────── helpers ───────────────────────────


def _parse_csv_candidates(csv_path: Path) -> List[TargetCandidate]:
    """Parse airodump-ng CSV output into TargetCandidate list."""
    candidates: List[TargetCandidate] = []
    try:
        text = csv_path.read_text(errors="replace")
        lines = text.splitlines()
        # Skip until AP section header
        in_ap = False
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if not in_ap:
                if parts and re.match(r"([A-F0-9]{2}:){5}[A-F0-9]{2}", parts[0]):
                    in_ap = True
                else:
                    continue
            if len(parts) < 14:
                continue
            mac = parts[0]
            if not re.match(r"([A-F0-9]{2}:){5}[A-F0-9]{2}", mac):
                continue
            try:
                power = int(parts[8])
            except ValueError:
                power = -100

            quality = "??"
            if power >= -60:
                quality = "100%"
            elif power <= -90:
                quality = "0%"
            else:
                q = ((power - (-90)) * 100) // (-60 - (-90))
                quality = f"{q}%"

            candidates.append(
                TargetCandidate(
                    bssid=mac,
                    channel=parts[3].strip(),
                    power=power,
                    clients=0,
                    quality=quality,
                    enc=parts[5].strip(),
                    vendor="",
                    essid=parts[13].strip(),
                )
            )
    except Exception:
        pass
    return candidates


def _parse_status_line(line: str) -> Optional[Dict]:
    """Parse [timestamp] KEY key=val key=val lines."""
    m = re.match(r"\[.*?\] (.+)", line)
    if not m:
        return None
    body = m.group(1).strip()
    parts = body.split()
    if not parts:
        return None
    event = {"type": parts[0]}
    for p in parts[1:]:
        if "=" in p:
            k, _, v = p.partition("=")
            event[k] = v
    return event


# ─────────────────────────── controller ────────────────────────


class CapCapWifiController:
    """
    Hybrid controller: drives capcapwifi.sh with --auto + CLI flags.
    All network/process work runs in background threads; the GUI
    subscribes via on_state_change / on_log / on_candidates / on_credential.
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._state = AttackState.IDLE
        self._candidates: List[TargetCandidate] = []
        self._credentials: List[CapturedCredential] = []

        self.on_state_change: Callable[[AttackState], None] = lambda s: None
        self.on_log: Callable[[str, str], None] = lambda msg, level: None  # msg, level
        self.on_candidates: Callable[[List[TargetCandidate]], None] = lambda c: None
        self.on_credential: Callable[[CapturedCredential], None] = lambda c: None

    # ── public ──────────────────────────────────────────────────

    @property
    def state(self) -> AttackState:
        return self._state

    @property
    def candidates(self) -> List[TargetCandidate]:
        return list(self._candidates)

    @property
    def credentials(self) -> List[CapturedCredential]:
        return list(self._credentials)

    def list_interfaces(self) -> List[WirelessInterface]:
        """
        On Linux: run --list-interfaces and parse output.
        On macOS: use system_profiler / airport for demo/dev purposes.
        """
        import platform
        if platform.system() == "Darwin":
            return self._mac_interfaces()
        return self._linux_interfaces()

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
            has_submit = (portal_path / "submit.php").exists()
            portals.append(
                PortalSite(
                    site_id=stem,
                    name=name,
                    lang=lang,
                    path=str(portal_path),
                    has_submit=has_submit,
                )
            )
        return portals

    def start_scan(
        self,
        interface: str,
        scan_time: int = 30,
        channel: str = "",
        band: str = "bg",
    ) -> None:
        """Scan for nearby WPA networks (scan-only mode)."""
        args = [
            "sudo", str(REPO_DIR / "capcapwifi.sh"),
            "--scan-only",
            "--scan-time", str(scan_time),
            "-k",
        ]
        if interface:
            args += ["--interface", interface]
        if channel:
            args += ["-c", channel]
        if band:
            args += ["--band", band]

        self._set_state(AttackState.SCANNING)
        self._log(f"Tarama başlatılıyor – arayüz: {interface or 'otomatik'}", "info")
        self._run_async(args, mode="scan")

    def start_attack(self, config: AttackConfig) -> None:
        """Launch a full attack in --auto mode."""
        if self._state not in (AttackState.IDLE, AttackState.STOPPED, AttackState.ERROR):
            return

        args = [
            "sudo", str(REPO_DIR / "capcapwifi.sh"),
            "--auto", "-k", "-m",
            "-a", config.attack_type.value,
            "-l", config.language,
            "--band", config.band,
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
        self._log("Saldırı başlatılıyor...", "info")
        self._run_async(args, mode="attack")

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
        self._set_state(AttackState.STOPPED)
        self._log("İşlem durduruldu.", "warn")

    # ── private ─────────────────────────────────────────────────

    def _set_state(self, s: AttackState) -> None:
        self._state = s
        self.on_state_change(s)

    def _log(self, msg: str, level: str = "info") -> None:
        self.on_log(msg, level)

    def _run_async(self, args: list, mode: str) -> None:
        t = threading.Thread(target=self._run, args=(args, mode), daemon=True)
        t.start()

    def _run(self, args: list, mode: str) -> None:
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._proc = proc

            for raw_line in proc.stdout:  # type: ignore[union-attr]
                line = raw_line.rstrip()
                # Strip ANSI codes for status parsing
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                self._log(line, "raw")
                self._handle_status_line(clean, mode)

            proc.wait()
            if mode == "scan":
                self._finish_scan()
            else:
                self._set_state(
                    AttackState.STOPPED if proc.returncode == 0 else AttackState.ERROR
                )
        except FileNotFoundError:
            self._log(
                "capcapwifi.sh bulunamadı veya sudo izni yok. "
                "Lütfen Linux/Kali üzerinde root olarak çalıştırın.",
                "error",
            )
            self._set_state(AttackState.ERROR)
        except Exception as exc:
            self._log(f"Hata: {exc}", "error")
            self._set_state(AttackState.ERROR)

    def _handle_status_line(self, line: str, mode: str) -> None:
        ev = _parse_status_line(line)
        if ev is None:
            return
        t = ev.get("type", "")
        if t == "SCAN_START":
            self._set_state(AttackState.SCANNING)
        elif t == "SCAN_COMPLETE":
            n = ev.get("candidates", "?")
            self._log(f"Tarama tamamlandı – {n} ağ bulundu.", "success")
        elif t == "TARGET_SELECTED":
            ssid = ev.get("ssid", "")
            bssid = ev.get("bssid", "")
            ch = ev.get("channel", "")
            self._log(f"Hedef seçildi: {ssid} ({bssid}) CH{ch}", "info")
        elif t == "ATTACK_STARTED":
            self._set_state(AttackState.RUNNING)
        elif t == "RESULT":
            pw = ev.get("password")
            hs = ev.get("handshake")
            if pw:
                cred = CapturedCredential(
                    timestamp=time.strftime("%H:%M:%S"),
                    ssid=ev.get("ssid", ""),
                    bssid=ev.get("bssid", ""),
                    password=pw,
                )
                self._credentials.append(cred)
                self.on_credential(cred)
                self._set_state(AttackState.CREDENTIALS_FOUND)
            elif hs:
                self._set_state(AttackState.HANDSHAKE_CAPTURED)
                self._log(f"Handshake yakalandı: {hs}", "success")

    def _finish_scan(self) -> None:
        """Try to parse the CSV dump after scan-only mode finishes."""
        workspace = os.environ.get("FLUXIONWorkspacePath", "/tmp/fluxspace")
        csv_path = Path(workspace) / "dump-01.csv"
        if csv_path.exists():
            cands = _parse_csv_candidates(csv_path)
            self._candidates = cands
            self.on_candidates(cands)
            self._log(f"{len(cands)} ağ parse edildi.", "success")
        self._set_state(AttackState.STOPPED)

    def _linux_interfaces(self) -> List[WirelessInterface]:
        ifaces: List[WirelessInterface] = []
        try:
            result = subprocess.run(
                ["sudo", str(REPO_DIR / "capcapwifi.sh"), "--list-interfaces"],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.splitlines()
            # Skip header rows (first 2)
            for line in lines[2:]:
                parts = line.split()
                if len(parts) >= 2:
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
        except Exception:
            pass
        return ifaces

    def _mac_interfaces(self) -> List[WirelessInterface]:
        """macOS fallback – reads networksetup for Wi-Fi interfaces."""
        ifaces: List[WirelessInterface] = []
        try:
            result = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.splitlines()
            current_name = ""
            for line in lines:
                if line.startswith("Hardware Port:"):
                    current_name = line.split(":", 1)[1].strip()
                elif line.startswith("Device:") and "Wi-Fi" in current_name or "Wireless" in current_name:
                    dev = line.split(":", 1)[1].strip()
                    ifaces.append(WirelessInterface(name=dev, chipset=current_name, state="UP"))
        except Exception:
            pass
        if not ifaces:
            ifaces = [WirelessInterface(name="en0", chipset="Built-in Wi-Fi", state="UP", bands="2.4/5 GHz")]
        return ifaces
