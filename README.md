# capcapwifi

A wireless auditing and captive-portal research toolkit for Linux. It is a
maintained fork of [Fluxion](https://github.com/FluxionNetwork/fluxion) v6.38:
the attack engine is the same, with a hardened workspace, a ShellCheck gate, a
mobile-accurate Instagram captive portal, and local credential capture that does
not depend on the target's WPA handshake.

Two attack modules ship with it:

| Module | Purpose |
|---|---|
| **Handshake Snooper** | Deauthenticates clients and captures the WPA/WPA2 4-way handshake for offline analysis |
| **Captive Portal** | Evil-twin AP with DHCP, DNS spoofing and a local web server; serves a portal page and records what visitors submit |

## Requirements

- Kali Linux (rolling) or another Linux with the same tooling; root is required.
- A wireless adapter that supports monitor mode and frame injection.
- `hostapd`, `lighttpd`, `php-cgi`, `kea-dhcp4`, `dnsspoof`, `aircrack-ng`,
  `iptables`, `xterm` (or `tmux` with `-m`). The dependency check offers to
  install whatever is missing.

## Running

```bash
git clone https://github.com/sametuca/capcapwifi.git capcapwifi
cd capcapwifi
sudo ./capcapwifi.sh
```

Check or install dependencies without starting an attack:

```bash
sudo ./capcapwifi.sh -i
```

Useful flags: `--auto`, `--bssid`, `--channel`, `--attack`, `--deauth-method`,
`--band`, `--scan-time`, `--list-interfaces`, `--scan-only`, `-m`/`--multiplexer`
(headless tmux, no X11). See `docs/man/capcapwifi.1` or `--help`.

## Running from a terminal, step by step

The first run is interactive: the tool asks one question at a time and every
screen keeps a `[q]` option to go back. Nothing needs to be configured by hand.

**1. Open a terminal on the Linux machine and get the code.**

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/sametuca/capcapwifi.git
cd capcapwifi
```

**2. Check that the adapter is usable.** It must support monitor mode and frame
injection, and if this is a VM it must already be attached to the VM (USB
passthrough), not to the host.

```bash
sudo iw dev            # the adapter should be listed here
sudo rfkill unblock all
```

**3. Install the missing tools.** This prints what is missing and asks before
installing:

```bash
sudo ./capcapwifi.sh -i
```

**4. Start it.** Root is required; without it the wireless interfaces cannot be
switched to monitor mode.

```bash
sudo ./capcapwifi.sh
```

The banner appears, then the first prompt:

| Prompt | What to answer |
|---|---|
| **Wireless interface** | The adapter in monitor mode, usually `wlan0`. `--list-interfaces` shows the names. |
| **Attack** | `Handshake Snooper` to capture a WPA handshake, `Captive Portal` to serve a login page. |
| **Target AP** | A scan list appears. Green rows have at least one device connected — those are the useful ones. Type the number and press Enter. |
| **Captive Portal: portal site** | The language/design pair, e.g. `Instagram_tur`. |

The deauthentication method is not a question any more: `aireplay-ng` is used,
because it behaves the same on every adapter. If your setup works better with
`mdk4`, start with `--deauth-method mdk4` and the tool uses that instead.

Portals that carry their own `submit.php` — the `Instagram_*` ones — also skip
the password-verification step and its "path to a handshake" prompt. They record
what the visitor types directly, so asking for a `.cap` file first would only
add two prompts and change nothing. Stock portals still ask, because they verify
submitted passwords against a handshake.

**5. Watch the result.** Both modules write into `/tmp/fluxspace`, which is
wiped on exit:

```bash
sudo tail -f /tmp/fluxspace/instagram_credentials.log   # captive portal captures
ls /tmp/fluxspace/*.cap                                  # handshake files
```

**6. No X server?** On a VM you reach over SSH, or a machine without a desktop,
run it inside tmux instead of spawning `xterm` windows:

```bash
sudo ./capcapwifi.sh -m
```

Detach with `Ctrl-b d`, reattach with `tmux attach -t CAPCAPWIFI`.

If something does not work, `sudo bash scripts/diagnostics.sh wlan0` reports the
driver, regulatory domain, channel support and tool versions.

## Captive Portal

The portal runs locally: the rogue AP hands out a gateway address, `dnsspoof`
resolves every name to it, and `iptables` forwards HTTP/HTTPS to a lighttpd
instance whose document root is the selected portal. No traffic leaves the
machine for the portal page itself.

Portals live in `attacks/Captive Portal/sites/<Name>_<lang>.portal/` and are
plain HTML plus the PHP endpoints. Adding one means dropping in a directory; the
menu picks it up from the glob.

### Instagram portal

The portal ships in seven languages — `tur`, `en`, `de`, `es`, `fr`, `it` and
`pt-br` — all generated from one set of templates. Each mirrors Instagram's
current mobile login (dark sheet, gradient glyph) and posts to a portal-local
`submit.php` instead of the stock WPA authenticator:

- Every submission is appended to `$FLUXIONWorkspacePath/instagram_credentials.log`
  as tab-separated `time · IP · username · password · user agent`.
- The first attempt is answered with Instagram's "password incorrect" page
  (username prefilled, password cleared); the second redirects to the success
  page so the flow ends instead of looping. `MAX_ATTEMPTS` in `submit.php`
  controls that threshold.
- Attempts are also mirrored into Fluxion's own `hit.txt` / `pwdattempt.txt`
  bookkeeping, so the attack window's counters and pass log stay correct.
- The log rotates in place at 512 KiB, keeping three previous files
  (`instagram_credentials.log.1` … `.3`), so a long run cannot fill the tmpfs
  the workspace usually lives on.
- A resubmitted identical pair within a minute (double-clicked button, page
  refresh) counts once, and a field with tabs, newlines or control characters
  is flattened so one submission is always one log line.

```bash
sudo ./capcapwifi.sh
# Captive Portal → target AP → portal list → Instagram
sudo tail -f /tmp/fluxspace/instagram_credentials.log
```

`submit.php` and the markup live in `scripts/instagram_portal/`; the committed
`Instagram_*.portal` directories are build output. To change the design or add a
language, edit the templates (or `languages.json`) and regenerate:

```bash
python3 scripts/build_instagram_portals.py           # write the portals
python3 scripts/build_instagram_portals.py --check   # fail if they are stale
```

## Tests

```bash
bash tests/run_safe_suite.sh          # unit/regression suite, no hardware
bash scripts/run_shellcheck.sh        # lint gate against the committed baseline
python3 scripts/build_instagram_portals.py --check
```

The suite is hardware-free by design; end-to-end runs need a monitor-mode
adapter (or `mac80211_hwsim`). The portal tests start a throwaway `php -S` and
skip themselves when PHP is not installed.

## License and credit

GPL-3.0. Based on Fluxion by the FluxionNetwork contributors; the original
copyright and licence are preserved in `LICENSE`. Internal identifiers and the
`FLUXION*` environment variables keep their upstream names so patches from
upstream still apply.

Use it only on networks you own or have written permission to test.
