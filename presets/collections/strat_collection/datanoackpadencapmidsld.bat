@echo off
REM Стратегия datanoack padencap midsld (20.03.2025)
REM VERSION: 1.2
REM Дата обновления: 2025-03-20

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

start "zapret: winws datanoack_padencap_midsld" /b "winws.exe" ^
 --wf-tcp=443 --wf-udp=443,50000-65535 ^
 --filter-tcp=443 --hostlist="other.txt" --hostlist="faceinsta.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=1 --dpi-desync-fake-tls="tls_clienthello_vk_com.bin" --dpi-desync-ttl=5 --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-udplen-increment=10 --dpi-desync-repeats=6 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-59000 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="youtubeGV.txt" --dpi-desync=split --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-cutoff=d2 --dpi-desync-ttl=4 --new ^
 --filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=fake,split2 --dpi-desync-split-seqovl=625 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_vk_com.bin" --dpi-desync-ttl=2 --new ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-repeats=11 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="discord.txt" --ipset="ipset-cloudflare.txt" --dpi-desync=fake,fakeddisorder --dpi-desync-fooling=datanoack --dpi-desync-split-pos=midsld --dpi-desync-fake-tls-mod=rnd,rndsni,padencap