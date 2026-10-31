# CapWifi

A Wi-Fi security auditing toolkit for Kali Linux, with two ways to drive it: a guided
Python desktop application for everyday use, and a non-interactive CLI for scripts,
CI and headless boxes.

CapWifi audits WPA/WPA2 networks by capturing handshakes and by running a captive
portal (evil twin) against networks you own or have written permission to test.

```
sudo ./capwifi.sh        # interactive terminal UI
./run_gui.sh                # desktop application (installs what it needs)
```

---

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Desktop application](#desktop-application)
- [Command line](#command-line)
- [How an attack runs](#how-an-attack-runs)
- [Output and workspace](#output-and-workspace)
- [Troubleshooting](#troubleshooting)
- [Project layout](#project-layout)
- [Development](#development)
- [Intended use](#intended-use)

---

## What it does

| Attack | What happens | Result |
| --- | --- | --- |
| **Handshake Snooper** | Deauthenticates clients of the target AP so they reconnect, then captures the WPA/WPA2 four-way handshake | `.cap` file you can crack offline |
| **Captive Portal** | Clones the target AP, serves a login page from one of 61 bundled templates, and records what visitors submit | Credentials in the workspace log |

Both attacks can run on a single adapter; two adapters (one for the rogue AP, one for
deauthentication) is the more reliable setup.

Portal templates include 7 Instagram variants (English, Turkish, German, Spanish,
French, Italian, Brazilian Portuguese) plus consumer router brands such as ARRIS,
TP-Link, HUAWEI and Netgear. Templates that ship their own `submit.php` record
submissions directly, so they do not require a captured handshake to verify a password.

---

## Requirements

- **Linux** with the tooling below. Kali rolling is the supported target; any
  Debian-derived distribution with the same packages works.
- **Root.** Monitor mode, `hostapd`, `iptables` and the DHCP server all require it.
- **A wireless adapter that supports monitor mode and frame injection.** Most
  built-in laptop cards do not. Atheros AR9271, Ralink RT3070/RT5370 and
  Realtek RTL8812AU chipsets are known to work. Inside a VM the adapter must be
  passed through (USB, not bridged).
- **Python 3.9+** for the desktop application (`python3-tk` is required; the
  launcher installs it if missing).

The runtime dependencies are `aircrack-ng`, `airmon-ng`, `hostapd`, `lighttpd`,
`php-cgi`, `kea-dhcp4`, `dnsspoof`, `mdk4`, `iw`, `iptables`, `macchanger`,
`rfkill`, `nmap`, `openssl`, `7zr`, `unzip` and either `xterm` or `tmux` (with `-m`).
You do not need to install them by hand.

---

## Installation

```bash
git clone https://github.com/sametuca/capwifi.git
cd capwifi
sudo ./capwifi.sh --install-deps
```

`--install-deps` checks every required tool, installs whatever is missing with `apt`,
and exits. The interactive UI and the desktop application do the same check on their
own, so this step is optional — it is just the fastest way to get the machine ready.

---

## Desktop application

The GUI wraps the same attack engine, runs it in the background, and turns its status
output into a guided workflow. Nothing in the application requires memorising a flag.

```bash
./run_gui.sh
```

The launcher handles the environment for you:

1. Verifies `python3` and installs `python3-tk` / `python3-venv` through `apt` if needed.
2. Creates a virtual environment and installs `customtkinter` and `pillow`.
3. Asks for `sudo` once, then re-executes itself as root.
4. Opens the window.

On first launch the **Environment** card lists every requirement with a pass or fail
mark. If something required is missing, installation starts on its own: a progress
bar runs, the `apt` output streams into the live log, and the card refreshes when the
install finishes. The same check can be triggered by hand with the install button in
that card, or from a terminal with:

```bash
sudo ./capwifi.sh --install-deps --auto
```

This mode needs no X display and no tmux: it only installs the missing packages and
exits with `0` on success or `7` on failure.

### Workflow

The step bar at the top tracks where you are: **Adapter → Scan → Select target →
Attack → Result**. The status bar at the bottom always states the single next action.

1. **Adapter.** Pick a primary adapter, and optionally separate adapters for the
   rogue AP and the deauthentication traffic. Leave everything on automatic if you
   have one card.
2. **Scan.** Choose a duration and band, then hit **Scan**. Longer scans see more
   clients, not just more networks.
3. **Select target.** Networks are shown as cards with a channel badge, signal bars,
   dBm, a client count and a handshake marker. Green rows have at least one connected
   client — the only networks where deauthentication can produce a result. Click a
   card; the target fields fill in and a one-line explanation appears underneath.
4. **Attack.** Pick an attack type. Its description, prerequisites and expected
   outcome are shown inline, as is the selected portal's behaviour. Start it.
5. **Result.** Captured credentials appear under the credentials tab (each with a copy
   button). A captured handshake opens a green panel above the tabs with the full path
   of the saved `.cap` file and two buttons: continue with the Captive Portal, or crack
   the file with a wordlist. A system bell, a highlighted log line and the step bar
   jumping to **Result** make the capture hard to miss.

The help tab holds the same walkthrough inside the application, including the
workspace paths. The interface language is switched with the EN / TR control in the
top bar: the window is re-rendered in place, an attack that is already running keeps
going, and the choice is remembered between launches. `CAPCAP_GUI_LANG=en|tr` forces
a language for one run. The CLI language is independent of it and is set with `-l`.

### Conventions in the UI

- Signal strength is drawn as four bars, coloured by quality, with the dBm value kept
  for precision.
- A green client pill means a device is associated with that AP.
- A check mark means a handshake for that network is already saved.
- `DFS` marks radar channels (52–64, 100–144). The rogue AP cannot start there with
  `hostapd`; the engine falls back to `airbase-ng` in auto mode.

---

## Command line

```bash
sudo ./capwifi.sh              # interactive, prompt-driven
sudo ./capwifi.sh --help        # full manual page
```

### Common flags

| Flag | Purpose |
| --- | --- |
| `--auto` | Fully non-interactive; every prompt takes a sensible default, one attack cycle, then exit |
| `-m` | Use `tmux` instead of `xterm`; enables headless operation without X11 |
| `-k` | Kill interfering wireless processes (NetworkManager and friends) first |
| `-l <lang>` | UI language code (`en`, `tur`, …) |
| `-a <attack>` | Attack type, e.g. `"Captive Portal"` or `"Handshake Snooper"` |
| `-b <bssid>` | Target by access point MAC |
| `-e <essid>` | Target by network name |
| `-c <channel>` | Restrict the scan / lock the channel |
| `--band bg\|a\|abg` | 2.4 GHz, 5 GHz, or both |
| `--scan-time <s>` | Scanner duration in seconds (default 30) |
| `--scan-only` | Print nearby networks as a table and exit |
| `--list-interfaces` | Print detected wireless adapters with bands, driver, chipset and state |
| `--install-deps` | Install whatever is missing, then exit |
| `--interface <if>` | Adapter used for scanning |
| `--jammer-interface <if>` | Adapter used for deauthentication |
| `--ap-interface <if>` | Adapter used for the rogue AP |
| `--ap-channel <ch>` | Run the rogue AP on a different channel than the target |
| `--ap-service hostapd\|airbase-ng` | Rogue AP backend |
| `--deauth-method aireplay-ng\|mdk4` | Deauthentication method (default `aireplay-ng`) |
| `--site <template>` | Captive Portal template to serve, e.g. `Instagram_tur` or `ARRIS_en` |
| `--timeout <min>` | Stop the attack after N minutes |
| `--reg-domain <CC>` | Regulatory domain for 5 GHz (default `US`) |
| `--kill-exclude <name,…>` | Processes to spare when killing interference |

### Examples

```bash
# See what the adapter can do
sudo ./capwifi.sh --list-interfaces

# Survey nearby networks for a minute
sudo ./capwifi.sh --scan-only --scan-time 60 --band abg

# Headless handshake capture against a specific AP, 20 minute limit
sudo ./capwifi.sh -m --auto -a "Handshake Snooper" \
     -b AA:BB:CC:DD:EE:FF -c 6 --timeout 20

# Captive portal with the Turkish Instagram template, two adapters
sudo ./capwifi.sh -m --auto -a "Captive Portal" -l tur \
     -b AA:BB:CC:DD:EE:FF --ap-interface wlan1 --jammer-interface wlan0
```

Notes on behaviour that tends to surprise people:

- The deauthentication method is not a question. `aireplay-ng` is used unless
  `--deauth-method mdk4` overrides it. `mdk4` only transmits after it observes traffic
  from a client, so on a quiet network it appears to do nothing.
- In auto mode the tracker that follows channel changes is disabled unless
  `--tracker-interface` is given.
- Everything is restored on exit: interfaces leave monitor mode, `iptables` is
  restored from the backup taken at startup, and system services are restarted.

---

## How an attack runs

```
scan → select target → prepare (monitor mode, services, firewall)
     → run attack → collect result → restore system state
```

`capwifi.sh` orchestrates the attacks under `attacks/`. Each attack owns its
preparation, its windows and its teardown. Progress is written to a status file so a
front-end (the GUI, a script, a CI job) can follow along without parsing terminal art.

Status lines look like this:

```
[2026-10-31T12:04:11] SCAN_START interface=wlan0 duration=30s
[2026-10-31T12:04:44] SCAN_COMPLETE candidates=14
[2026-10-31T12:04:52] TARGET_SELECTED ssid=Example bssid=AA:BB:CC:DD:EE:FF channel=6
[2026-10-31T12:05:01] ATTACK_STARTED attack=Captive Portal
[2026-10-31T12:07:39] RESULT password=… ssid=Example bssid=AA:BB:CC:DD:EE:FF
```

---

## Output and workspace

The workspace defaults to `/tmp/capcapspace` and is created with `0700` permissions.
Override it with the `CAPCAPWorkspacePath` environment variable.

| Path | Contents |
| --- | --- |
| `/tmp/capcapspace/capcap.status` | Timestamped event log (auto mode only) |
| `/tmp/capcapspace/instagram_credentials.log` | Tab-separated submissions: time, client IP, username, password, user agent; rotates at 512 KiB, keeping `.1`–`.3` |
| `attacks/Handshake Snooper/handshakes/` | Captured `.cap` files |

---

## Troubleshooting

**No wireless interfaces / `--list-interfaces` is empty.**
The adapter is not visible to Linux. Check `iw dev`. In a VM, attach the USB adapter
to the guest instead of bridging the host card.

**Monitor mode fails or injection tests fail.**
Not every card supports it. `airmon-ng check kill` (or `-k`) first, then retry. On
macOS hosts the driver is the usual culprit, not CapWifi.

**Portal is up but nothing is captured.**
The target AP must have at least one connected client, otherwise there is no traffic
to deauthenticate. Re-scan with a longer duration and pick a network with a green
client pill.

**Attack starts on a DFS channel.**
Hostapd needs radar detection support. Pass `--ap-channel` to serve the rogue AP on a
non-DFS channel, which normally requires a second adapter.

**`sudo` prompts or `permission denied` in the GUI.**
Start it through `./run_gui.sh`; it escalates once and reuses that session. Running
`python3 gui/app.py` directly will not have the privileges the attacks need.

---

## Project layout

```
capwifi/
├── capwifi.sh            # entry point, orchestration and CLI
├── run_gui.sh               # desktop application launcher (installs, escalates)
├── gui/
│   ├── app.py               # window layout, workflow, guidance
│   ├── controller.py        # runs the engine, parses status, tails the workspace
│   ├── widgets.py           # network cards, signal bars, log, checklist
│   └── models.py            # plain data classes
├── attacks/
│   ├── Captive Portal/      # evil twin attack and 61 portal templates
│   └── Handshake Snooper/   # handshake capture
├── lib/                     # shared shell libraries, installer, window manager
├── language/                # CLI locale strings (en, tur, …)
├── scripts/                 # portal build/verify helpers
└── tests/                   # shell and portal test suites
```

---

## Development

```bash
# syntax and behaviour tests that need no hardware
bash tests/run_safe_suite.sh

# shell lint against the accepted baseline
bash scripts/run_shellcheck.sh

# desktop application imports and syntax
python3 tests/test_gui_imports.py
```

The safe suite covers locale loading, CLI parsing, hash handling, target selection,
channel selection, sandbox utilities, the Instagram portal server and the
`--install-deps` surface. Tests that need `aircrack-ng` or real adapters live outside
it and are expected to fail on non-Linux hosts.

Portal templates are generated from `scripts/instagram_portal/`; edit the source, run
`python3 scripts/build_instagram_portals.py`, and `--check` in CI will catch drift.

---

## Intended use

CapWifi is an auditing tool. Use it on networks you own or have explicit written
permission to test. Running it against third-party networks is illegal in most
jurisdictions and outside the scope of what this project supports.

Maintained by [sametuca](https://github.com/sametuca). Bug reports and feature
requests belong in this repository's issue tracker:
https://github.com/sametuca/capwifi/issues
