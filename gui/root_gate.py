"""Root yetkisi kapısı – uygulama rootsuz açılmaz.

Neden gerekli: monitör modu, hostapd ve sahte portal root ister. Rootsuz
açılan pencere tamamen kuruluyor, düğmeler çalışmıyor ve kullanıcı yalnızca
log panelinde anlaşılmaz bir satır görüyordu. Bu modül o durumu baştan
kesiyor: kısa ve net bir uyarı penceresi gösterip uygulamayı sıfırdan farklı
bir çıkış koduyla kapatıyor.

Neden ayrı modül: karar (root mıyız?) ile sunum (uyarı penceresi) app.py'nin
__init__'i içinde gömülü kalırsa test edilemez. Burada ikisi de pencere
açmadan sorgulanabiliyor; asıl pencere yalnızca :func:`show_warning` çağrılınca
kurulur.
"""
from __future__ import annotations

import os
import sys
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from effects import make_button
from i18n import t
from theme import (
    ACCENT2,
    ACCENT2_ON,
    BORDER,
    CARD_BG,
    DANGER,
    DANGER_ON,
    DARK_BG,
    FONT_MONO_S,
    FONT_UI_S,
    FONT_TITLE,
    MUTED,
    PANEL_BG,
    TEXT_PRI,
    TEXT_SEC,
    WARN,
)

#: Kullanıcıya her yerde gösterilen tek çözüm. Metinlerde birebir geçmeli;
#: testler bu dizgeyi arıyor.
ROOT_COMMAND = "sudo ./run_gui.sh"

#: Uyarı onaylandıktan sonra kullanılan çıkış kodu (sysexits EX_NOPERM).
#: 0 olmaması bilinçli: kabuk betikleri ve CI "başarısız" görsün.
EXIT_CODE = 77

#: Test/teşhis kaçış kapısı: root olmayan bir ortamda arayüzü açmaya izin
#: verir. Normal kullanıcı akışını DEĞİŞTİRMEZ – yalnızca testler ve paket
#: üretimi gibi root verilemeyen durumlar içindir.
ALLOW_NONROOT_ENV = "CAPCAP_ALLOW_NONROOT"

#: Otomasyon için: uyarı penceresi bu kadar milisaniye sonra kendini onaylar
#: (ekran görüntüsü / duman testi). Verilmezse kullanıcı düğmeye basana kadar
#: bekler. Üretimde asla ayarlanmaz.
AUTO_ACK_ENV = "CAPCAP_ROOT_GATE_AUTO_ACK"


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _real_uid() -> str:
    """Uyarı penceresindeki uid rozeti için; bilinmeyen platformda '?'."""
    getuid = getattr(os, "getuid", None)
    try:
        return str(getuid()) if getuid is not None else "?"
    except OSError:
        return "?"


def override_enabled() -> bool:
    """Test/teşhis kaçış kapısı açık mı?"""
    return _truthy(os.environ.get(ALLOW_NONROOT_ENV))


def is_root() -> bool:
    """Root mıyız? Kavramın olmadığı platformlarda "uygulanamaz" sayılır.

    Windows'ta ``geteuid`` yok; orada kapı hiç devreye girmemeli, yoksa
    uygulama hiç açılmazdı. Aynı şekilde ``geteuid`` bulunmayan egzotik
    POSIX'lerde de kapıyı kapatıyoruz: bilinmeyen bir platformda uygulamayı
    kilitlemek, açmaktan daha kötü.
    """
    if os.name == "nt":
        return True
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return True
    try:
        return geteuid() == 0
    except OSError:
        # Yetki sorgusu bile başarısızsa kullanıcıyı suçlamayalım.
        return True


def root_required() -> bool:
    """Kapı kapanmalı mı? (root değiliz ve kaçış kapısı da kapalı)"""
    return not is_root() and not override_enabled()


def terminal_message() -> str:
    """Terminalden başlatan kullanıcının göreceği tek satır (stderr)."""
    return t("root.required.terminal")


def announce(stream=None) -> None:
    """Aynı talimatı stderr'e yaz; CI ve kabuk logları nedeni yakalasın."""
    stream = stream if stream is not None else sys.stderr
    try:
        print(terminal_message(), file=stream, flush=True)
    except (OSError, ValueError):
        pass


class RootWarningDialog(ctk.CTkToplevel):
    """Bloklayan, kapatılamaz uyarı: neden açılmadı + tam komut.

    Sade bir ``messagebox`` yerine uygulamanın kendi dili kullanılıyor: aynı
    kart yüzeyi, aynı tipografi ve aynı düğme bileşeni. Beyaz metin hiçbir
    yerde yok; dolgulu düğmeler kendi ``*_ON`` renklerini kullanıyor.
    """

    def __init__(self, master, auto_ack_ms: int = 0):
        super().__init__(master, fg_color=DARK_BG)
        self._master = master
        self._closed = False
        self.title(t("root.required.title"))
        self.configure(fg_color=DARK_BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        width, height = 620, 340
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 30)
        self.geometry(f"{width}x{height}+{x}+{y}")

        card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=14,
                            border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(head, text="⛔", font=("Inter", 20),
                     text_color=DANGER_ON, fg_color=DANGER, corner_radius=9,
                     width=36, height=36).pack(side="left")
        ctk.CTkLabel(head, text=t("root.required.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(card, text=t("root.required.body"), font=FONT_UI_S,
                     text_color=TEXT_SEC, anchor="w", justify="left",
                     wraplength=540).pack(fill="x", padx=18, pady=(12, 8))

        # Komut kutusu: kullanıcı kopyalayabilsin diye ayrı, mono ve seçilebilir.
        box = ctk.CTkFrame(card, fg_color=PANEL_BG, corner_radius=10,
                           border_width=1, border_color=BORDER)
        box.pack(fill="x", padx=18, pady=(0, 10))
        self._command_label = ctk.CTkLabel(
            box, text=f"$  {ROOT_COMMAND}", font=FONT_MONO_S,
            text_color=ACCENT2, anchor="w")
        self._command_label.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(card, text=t("root.required.hint"), font=FONT_UI_S,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=540).pack(fill="x", padx=18)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(14, 16))
        # Teşhis satırı: "neden açılmadı" sorusunun makine tarafı. Rapor
        # ederken kullanıcı bu sayıyı kopyalayabiliyor.
        self._badge = ctk.CTkLabel(footer, text=f"uid={_real_uid()} (root: 0)",
                                   font=FONT_MONO_S, text_color=WARN)
        self._badge.pack(side="left")
        self._exit_button = make_button(
            footer, t("root.required.exit"), "danger",
            command=self.close, height=34)
        self._exit_button.pack(side="right")

        self._keys_armed = False
        self._exit_button.bind("<Return>", lambda _e: self._on_confirm_key())
        self.bind("<Escape>", lambda _e: self._on_confirm_key())
        self.after(50, self._focus)
        if auto_ack_ms > 0:
            self.after(auto_ack_ms, self.close)

    def _focus(self) -> None:
        try:
            self.lift()
            self.grab_set()
            self.focus_force()
            self._exit_button.focus_set()
        except Exception:
            pass
        # Kısayolları pencere göründükten 400 ms sonra açıyoruz. Kullanıcı
        # uygulamayı Enter'a basılı tutarak başlatırsa, tuşun otomatik
        # tekrarı uyarıyı okunmadan kapatırdı; bu gecikme onu engelliyor.
        self.after(400, self._arm_keys)

    def _arm_keys(self) -> None:
        self._keys_armed = True

    def _on_confirm_key(self) -> None:
        if not self._keys_armed:
            return
        self.close()

    def close(self) -> None:
        """Tek çıkış yolu; iki kez çağrılsa da zararsız."""
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def wait(self) -> None:
        """Kullanıcı onaylayana kadar bloğa gir (testler bunu ezer).

        ``wait_window`` yerine kendi döngümüz: pencere hiç görünür olmazsa
        (bozuk görüntü sunucusu) uygulama sonsuza kadar beklemesin. 1,5 sn
        içinde eşlenmeyen pencere kendini kapatır; çıkış kararı yine verilir.
        """
        try:
            self.after(1500, self._close_if_unmapped)
        except Exception:
            return
        self.wait_window()

    def _close_if_unmapped(self) -> None:
        try:
            if self._closed or self.winfo_ismapped():
                return
        except Exception:
            pass
        self.close()


def _auto_ack_ms() -> int:
    raw = os.environ.get(AUTO_ACK_ENV, "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def fallback_dialog(master) -> None:
    """Son çare: Tk'nin klasik mesaj kutusu (stilsiz ama bloklayan).

    Yalnızca özel pencerenin kurulamadığı durumlarda devreye girer; metinler
    aynı i18n anahtarlarından geliyor, bu yüzden iki dilde de aynı.
    """
    try:
        messagebox.showerror(
            t("root.required.title"),
            f"{t('root.required.body')}\n\n{t('root.required.hint')}",
            parent=master,
        )
    except Exception:
        pass


def show_warning(master) -> None:
    """Uyarıyı göster ve onaylanana kadar bekle.

    Pencere kurulamazsa (görüntü sunucusu yok, Tk hatası) sessizce dönüyoruz:
    asıl çıkış kararı :func:`enforce_root` içinde, ona hiçbir şey engel
    olmamalı.
    """
    # Ana pencere henüz boş (arayüz kurulmadı). Görünür kalırsa uyarının
    # arkasında bomboş siyah bir çerçeve durur; kullanıcı yanlışlıkla "bozuk
    # uygulama" sanır. Uyarı tek başına görünsün.
    try:
        master.withdraw()
    except Exception:
        pass
    try:
        dialog = RootWarningDialog(master, auto_ack_ms=_auto_ack_ms())
    except Exception:
        # Süslenmiş pencere kurulamadıysa son çare klasik kutu: kullanıcı
        # hiçbir şey görmeden kapanan bir uygulama yaşamasın.
        fallback_dialog(master)
        return
    try:
        dialog.wait()
    finally:
        try:
            dialog.close()
        except Exception:
            pass


def enforce_root(master) -> None:
    """Root değilsek uyarıyı göster ve uygulamayı sonlandır.

    Buradan normal dönüş YOK: ya root/uygulanamaz durumdayız ve fonksiyon
    sessizce döner, ya da ``SystemExit`` ile süreç sonlanır. Ara durum yok;
    yarım kurulmuş bir arayüz bırakmıyoruz.
    """
    if not root_required():
        return

    announce()
    show_warning(master)

    # Ana pencereyi kapatmak SystemExit'i engellememeli (Tk bazen kendi
    # hata ayıklayıcısına düşer); bu yüzden ayrı korunuyor.
    try:
        master.destroy()
    except Exception:
        pass
    raise SystemExit(EXIT_CODE)
