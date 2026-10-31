#!/usr/bin/env bash
# capcapwifi GUI başlatıcı
# Kullanım: ./run_gui.sh
# Gereksinim: Python 3.9+ ve venv (kurulum otomatik yapılır)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv"
GUI="$SCRIPT_DIR/gui/app.py"

# Renkler
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
echo -e "${GREEN}║   CapCapWifi GUI  Başlatıcı       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════╝${NC}"

# Python kontrolü
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}[!] python3 bulunamadı. Lütfen Python 3.9+ kurun.${NC}"; exit 1
fi

# Sanal ortam oluşturma/kontrol
if [ ! -d "$VENV" ]; then
  echo -e "${YELLOW}[*] Sanal ortam oluşturuluyor...${NC}"
  python3 -m venv "$VENV"
fi

# Bağımlılık kontrolü
if ! "$VENV/bin/python3" -c "import customtkinter" &>/dev/null; then
  echo -e "${YELLOW}[*] Bağımlılıklar yükleniyor (customtkinter, pillow)...${NC}"
  "$VENV/bin/pip" install --quiet customtkinter pillow
fi

echo -e "${GREEN}[+] GUI başlatılıyor...${NC}"
echo -e "${YELLOW}[!] NOT: Gerçek saldırı modları için Kali Linux ve root yetkisi gerekir.${NC}"
echo

exec "$VENV/bin/python3" "$GUI" "$@"
