@echo off
REM Стратегия multisplit 1,md5sig padencap wssize (discord)
REM VERSION: 1.2
REM Дата обновления: 2025-03-25

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

start "zapret: winws multisplit_md5sig_padencap_wssize_discord" /b "winws.exe" ^
 --wf-tcp=443 --wf-udp=443,50000-65535 ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-udplen-increment=10 --dpi-desync-repeats=6 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-59000 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-repeats=11 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --dpi-desync=fake,multisplit --dpi-desync-ttl=1 --dpi-desync-split-pos=1,midsld --dpi-desync-fake-tls-mod=rnd,rndsni,padencap --wssize 1:6