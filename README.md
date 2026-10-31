# capcapwifi

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

