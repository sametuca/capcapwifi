#!/usr/bin/env bash
# identifier: Handshake Snooper
# description: WPA/WPA2 encryption hash değerlerini alır.

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
HandshakeSnooperJammerInterfaceQuery="Monitör & Jamming(parazit oluşturma) için bir arabirim seçin."
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
HandshakeSnooperMethodQuery="Handshake elde etme yöntemini seçin"
HandshakeSnooperMonitorMethodOption="İzle (${CYel}pasif$CClr)"
HandshakeSnooperAireplayMethodOption="aireplay-ng kimlik doğrulamadan çıkarma (${CRed}saldırgan$CClr)"
HandshakeSnooperMdk4MethodOption="mdk4 kimlik doğrulamadan çıkarma (${CRed}saldırgan$CClr)"
HandshakeSnooperMethodExplanation="${CCyn}İzle$CClr: hiçbir şeyi kesmez, cihaz kendi kendine bağlanana kadar bekler — sessiz ama uzun sürebilir.
${CCyn}aireplay-ng$CClr: cihazları tek tek düşürür, handshake daha hızlı gelir, öngörülebilir.
${CCyn}mdk4$CClr: bağlı tüm cihazları aynı anda düşürür, en hızlısı, ama bazı cihazlar hiç geri bağlanmayabilir."
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
HandshakeSnooperVerifierIntervalQuery="Doğrulacı ne kadar aralıklarla hash kontrolü yapsın?"
HandshakeSnooperVerifierInterval30SOption="Her 30 saniyede (${CGrn}önerilen${CClr})."
HandshakeSnooperVerifierInterval60SOption="Her 60 saniyede."
HandshakeSnooperVerifierInterval90SOption="Her 90 saniyede."
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
HandshakeSnooperVerifierSynchronicityQuery="Doğrulama işlemi nasıl yapılsın?"
HandshakeSnooperVerifierSynchronicityAsynchronousOption="Asenkron (${CYel}hızlı sistemler için${CClr})."
HandshakeSnooperVerifierSynchronicitySynchronousOption="Senkron (${CGrn}önerilen${CClr})."
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
HandshakeSnooperStartingArbiterNotice="${CCyn}Handshake Snooper$CClr daemon'ı çalışıyor."
HandshakeSnooperSnoopingForNSecondsNotice="\$HandshakeSnooperVerifierInterval saniye boyunca izleniyor..."
HandshakeSnooperStoppingForVerifierNotice="İzleme durduruluyor & hash kontrolü yapılıyor"
HandshakeSnooperSearchingForHashesNotice="Capture dosyasında hash aranıyor..."
HandshakeSnooperArbiterAbortedWarning="${CYel}Durduruldu${CClr}: Bu işlem durduruldu, geçerli bir hash bulunamadı."
HandshakeSnooperArbiterSuccededNotice="${CGrn}Başarı${CClr}: Geçerli bir WPA/WPA2 handshake'i yakalandı."
HandshakeSnooperSavedFileNotice="Kayıt dosyası: %s"
HandshakeSnooperArbiterCompletedTip="${CBCyn}Handshake Snooper$CBYel saldırısı tamamlandı.$CClr Kayıtlı handshake'i Captive Portal ile kullanabilir (şifreyi otomatik doğrular) ya da aircrack-ng ile çevrimdışı kırabilirsiniz."
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# FLUXSCRIPT END
