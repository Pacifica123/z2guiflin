@echo off
REM Стратегия Ульта конфиг v2
REM VERSION: 1.3
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

start "zapret: winws Ultimate_Config_v2" /b "winws.exe" ^
 --wf-tcp=80,443 --wf-udp=443,50000-50090 ^
 --filter-tcp=443 --ipset="russia-youtube-rtmps.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_4.bin" --dpi-desync-autottl --new ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=2 --dpi-desync-fake-quic="quic_3.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=2 --new ^
 --filter-tcp=443 --ipset="ipset-discord.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_3.bin" --dpi-desync-autottl --new ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld+1 --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=5 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_2.bin" --dpi-desync-repeats=7 --dpi-desync-cutoff=n2 --new ^
 --filter-udp=50000-50090 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=n3 --new ^
 --filter-tcp=443 --hostlist="youtubeGV.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld-1 --new ^
 --filter-tcp=443 --hostlist="other.txt" --hostlist="faceinsta.txt" --ipset="ipset-cloudflare.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld-1 --dpi-desync-fooling=md5sig,badseq --dpi-desync-fake-tls="tls_clienthello_4.bin" --dpi-desync-ttl=2