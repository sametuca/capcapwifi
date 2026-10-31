#!/usr/bin/env bash
# CapWifi GUI başlatıcı
# Kullanım: ./run_gui.sh
#
# Gereksinim: Python 3.9+ ve venv. Eksik sistem paketleri (python3-tk,
# python3-venv) otomatik kurulur, ilerleme ekranda görünür.
# Monitor mode, hostapd ve portallar root ister; script kendini sonunda
# sudo ile yeniden başlatır.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv"
GUI="$SCRIPT_DIR/gui/app.py"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[x]${NC} $*" >&2; }
step()  { echo -e "${CYAN}[*]${NC} $*"; }

echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
echo -e "${GREEN}║   CapWifi GUI  Başlatıcı       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════╝${NC}"

# ── 1. Python ───────────────────────────────────────────────────────
step "Python kontrol ediliyor…"
if ! command -v python3 &>/dev/null; then
  fail "python3 bulunamadı."
  echo "    Kurulum: sudo apt install -y python3 python3-venv python3-tk"
  exit 1
fi
info "$(python3 --version 2>&1) bulundu."

# ── 2. sudo yetkisi (parola bir kez sorulur) ────────────────────────
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if ! command -v sudo &>/dev/null; then
    fail "Root değilsiniz ve sudo yok. 'su -' ile root olup tekrar deneyin."
    exit 1
  fi
  step "sudo yetkisi doğrulanıyor (parola istenebilir)…"
  sudo -v || { fail "sudo yetkisi alınamadı."; exit 1; }
  SUDO="sudo"
fi

# ── 3. tkinter (GUI'nin olmazsa olmazı) ──────────────────────────────
step "Tk arayüz kütüphanesi kontrol ediliyor…"
if ! python3 -c "import tkinter" &>/dev/null; then
  warn "python3-tk eksik, kuruluyor…"
  if command -v apt-get &>/dev/null; then
    $SUDO apt-get update -qq || true
    if ! $SUDO apt-get install -y python3-tk; then
      fail "python3-tk kurulamadı. Elle deneyin: sudo apt install -y python3-tk"
      exit 1
    fi
  else
    fail "python3-tk yok ve apt bulunamadı. Paket yöneticinizden tkinter kurun."
    exit 1
  fi
fi
info "Tk hazır."

# ── 4. Sanal ortam ve Python paketleri ──────────────────────────────
if [ ! -x "$VENV/bin/python3" ]; then
  step "Sanal ortam oluşturuluyor: $VENV"
  if ! python3 -m venv "$VENV"; then
    warn "venv oluşturulamadı, python3-venv kuruluyor…"
    if command -v apt-get &>/dev/null; then
      $SUDO apt-get install -y python3-venv || {
        fail "python3-venv kurulamadı."
        exit 1
      }
      python3 -m venv "$VENV" || { fail "Sanal ortam oluşturulamadı."; exit 1; }
    else
      fail "Sanal ortam oluşturulamadı (python3-venv gerekli)."
      exit 1
    fi
  fi
  info "Sanal ortam hazır."
fi

if ! "$VENV/bin/python3" -c "import customtkinter" &>/dev/null; then
  step "Arayüz paketleri indiriliyor (customtkinter, pillow)…"
  "$VENV/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
  if ! "$VENV/bin/pip" install --upgrade customtkinter pillow; then
    fail "Python paketleri kurulamadı. İnternet bağlantısını kontrol edin."
    exit 1
  fi
  info "Paketler kuruldu."
else
  info "Python paketleri hazır."
fi

# ── 5. Grafik ortam ─────────────────────────────────────────────────
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  fail "Grafik ortam bulunamadı (DISPLAY boş)."
  echo
  echo "  Masaüstü oturumundan çalıştırın; SSH kullanıyorsanız:"
  echo "    ssh -X kullanici@makine"
  echo
  exit 1
fi

# ── 6. Root olarak GUI ──────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  warn "Monitör modu ve hostapd root ister; GUI root olarak başlatılıyor."
  exec sudo --preserve-env=DISPLAY,XAUTHORITY,WAYLAND_DISPLAY,XDG_RUNTIME_DIR \
    "$0" "$@"
fi

echo
info "GUI başlatılıyor…"
warn "Eksik paketler ilk açılışta arayüz içinden otomatik kurulur (log panelinde görünür)."
warn "Süren bir saldırıyı kapatmadan önce '⏹ Durdur' kullanın."

exec "$VENV/bin/python3" "$GUI" "$@"
