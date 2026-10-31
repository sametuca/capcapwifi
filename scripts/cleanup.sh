#!/usr/bin/env bash
# capwifi cleanup script — kills any lingering state from a forced termination.
# Run as root from anywhere: sudo bash /path/to/capwifi/scripts/cleanup.sh

if [ "$(id -u)" -ne 0 ]; then
	echo "cleanup.sh must be run as root." >&2
	exit 1
fi

echo "[*] Killing capwifi processes..."
pkill -SIGINT -f "capwifi.sh" 2>/dev/null
sleep 2
pkill -9 -f "capwifi.sh" 2>/dev/null

echo "[*] Killing attack service processes..."
for proc in hostapd dnsmasq lighttpd kea-dhcp4 php-cgi airodump-ng aireplay-ng mdk4 airbase-ng; do
	pkill -9 "$proc" 2>/dev/null && echo "    killed $proc"
done

echo "[*] Killing CAPWIFI tmux sessions..."
for session in $(tmux ls 2>/dev/null | grep -oE '^CAPCAP[^:]*'); do
	tmux kill-session -t "$session" 2>/dev/null && echo "    killed tmux session $session"
done

echo "[*] Restoring regulatory domain..."
_iw=$(command -v iw 2>/dev/null || echo /usr/sbin/iw)
if [ -x "$_iw" ]; then
	_reg=$("$_iw" reg get 2>/dev/null | grep -m1 "^country" | sed 's/country \([A-Z0-9]*\).*/\1/')
	if [ "$_reg" = "BO" ]; then
		"$_iw" reg set 00 2>/dev/null && echo "    regulatory domain reset from BO to 00"
	else
		echo "    regulatory domain is $_reg, no change needed"
	fi
fi

echo "[*] Restoring wireless interfaces..."
for iface in $(ip link show | grep -oE 'capwl[^ :@]+'); do
	# Derive original name from MAC: wlx + mac without colons
	mac=$(ip link show "$iface" 2>/dev/null | awk '/link\//{print $2}')
	original="wlx${mac//:/}"

	ip link set "$iface" down 2>/dev/null
	iw dev "$iface" set type managed 2>/dev/null
	ip link set "$iface" name "$original" 2>/dev/null \
		&& echo "    $iface -> $original (managed)" \
		|| echo "    $iface -> rename failed, left as-is"
	ip link set "$original" up 2>/dev/null
done

echo "[*] Restoring ip_forward..."
if [ -f /tmp/capcapspace/ip_forward ]; then
	sysctl -w net.ipv4.ip_forward=$(cat /tmp/capcapspace/ip_forward) 2>/dev/null \
		&& echo "    ip_forward restored from saved value"
else
	sysctl -w net.ipv4.ip_forward=0 2>/dev/null \
		&& echo "    ip_forward reset to 0 (no saved value)"
fi

echo "[*] Cleaning up workspace..."
rm -rf /tmp/capcapspace/ 2>/dev/null && echo "    /tmp/capcapspace/ removed"

echo "[*] Restoring iptables..."
# capwifi saves iptables backup at <capcap_dir>/iptables-rules
_script_dir="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
_iptables_bak="$_script_dir/iptables-rules"
if [ -f "$_iptables_bak" ]; then
	iptables-restore < "$_iptables_bak" \
		&& echo "    iptables restored from backup" \
		&& rm -f "$_iptables_bak"
else
	echo "    no iptables backup found, flushing rules"
	iptables -F
	iptables -X
	iptables -t nat -F
	iptables -t nat -X
fi

echo "[+] Done."

# CAPWIFI END
