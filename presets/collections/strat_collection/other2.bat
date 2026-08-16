@echo off
REM Стратегия Другие провайдеры 2
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

start "zapret: winws Other_Providers_v2" /b "winws.exe" ^
 --wf-l3=ipv4,ipv6 --wf-tcp=443 --wf-udp=443,50000-65535 ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-repeats=11 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=fake,split2 --dpi-desync-split-seqovl=1 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_www_google_com.bin" --dpi-desync-ttl=4 --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-udplen-increment=10 --dpi-desync-repeats=6 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-59000 --dpi-desync=fake,tamper --dpi-desync-any-protocol --dpi-desync-cutoff=n5 --dpi-desync-repeats=10 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fake,split2 --dpi-desync-split-seqovl=1 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_www_google_com.bin" --dpi-desync-ttl=2 --new ^
 --filter-tcp=443 --hostlist="other.txt" --hostlist="faceinsta.txt" --ipset="ipset-cloudflare.txt" --dpi-desync=fake,split2 --dpi-desync-split-seqovl=1 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_3.bin" --dpi-desync-ttl=2