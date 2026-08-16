@echo off
REM Стратегия Ростелеком и Мегафон
REM VERSION: 1.4
REM Дата обновления: 2024

whoami /groups | find "S-1-5-32-544" >nul 2>&1 && goto :ADMIN
powershell -nop -c "Start-Process '%~f0' -arg @('ELEV','%*') -Verb RunAs"
exit /b
:ADMIN
if /i "%1"=="ELEV" shift

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "zapret: winws Rostelecom_Megafon" /b "winws.exe" ^
 --wf-tcp=80,443 --wf-udp=443,50000-59000 ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-repeats=4 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=split --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-autottl=2 --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-59000 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fake,split --dpi-desync-autottl=2 --dpi-desync-repeats=6 --dpi-desync-fooling=badseq --dpi-desync-fake-tls="tls_clienthello_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist-exclude-domains=lmarena.ai,ixbt.com,gitflic.ru,searchengines.guru,habr.com,cdn.ampproject.org,st.top100.ru,rootsplants.co.uk,podviliepitomnik.ru,cvetovod.by,veresk.by,use.fontawesome.com,xn--p1ai --dpi-desync=fake,split2 --hostlist-exclude-domains=lmarena.ai,gitflic.ru,searchengines.guru,habr.com,cdn.ampproject.org,st.top100.ru,rootsplants.co.uk,kaspersky.com,podviliepitomnik.ru,cvetovod.by,veresk.by,use.fontawesome.com,xn--p1ai --dpi-desync=fake,split2 --dpi-desync-split-seqovl=1 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_3.bin" --dpi-desync-ttl=2