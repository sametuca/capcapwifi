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
git clone <repository-url> capcapwifi
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

## Captive Portal

The portal runs locally: the rogue AP hands out a gateway address, `dnsspoof`
resolves every name to it, and `iptables` forwards HTTP/HTTPS to a lighttpd
instance whose document root is the selected portal. No traffic leaves the
machine for the portal page itself.

Portals live in `attacks/Captive Portal/sites/<Name>_<lang>.portal/` and are
plain HTML plus the PHP endpoints. Adding one means dropping in a directory; the
menu picks it up from the glob.

### Instagram portal

`Instagram_tur.portal` and `Instagram_en.portal` mirror Instagram's current
mobile login (dark sheet, gradient glyph) and post to a portal-local
`submit.php` instead of the stock WPA authenticator:

- Every submission is appended to `$FLUXIONWorkspacePath/instagram_credentials.log`
  as tab-separated `time · IP · username · password · user agent`.
- The first attempt is answered with Instagram's "password incorrect" page
  (username prefilled, password cleared); the second redirects to the success
  page so the flow ends instead of looping. `MAX_ATTEMPTS` in `submit.php`
  controls that threshold.
- Attempts are also mirrored into Fluxion's own `hit.txt` / `pwdattempt.txt`
  bookkeeping, so the attack window's counters and pass log stay correct.

```bash
sudo ./capcapwifi.sh
# Captive Portal → target AP → portal list → Instagram
sudo tail -f /tmp/fluxspace/instagram_credentials.log
```

## Tests

```bash
bash tests/run_safe_suite.sh          # unit/regression suite, no hardware
bash scripts/run_shellcheck.sh        # lint gate against the committed baseline
```

The suite is hardware-free by design; end-to-end runs need a monitor-mode
adapter (or `mac80211_hwsim`).

## License and credit

GPL-3.0. Based on Fluxion by the FluxionNetwork contributors; the original
copyright and licence are preserved in `LICENSE`. Internal identifiers and the
`FLUXION*` environment variables keep their upstream names so patches from
upstream still apply.

Use it only on networks you own or have written permission to test.
