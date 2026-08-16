@echo off
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

start "zapret: winws Ultimate_Config_ZL" /b "winws.exe" ^
 --wf-tcp=80,443 --wf-udp=443,50000-50099 ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-fake-quic="quic_1.bin" --dpi-desync-repeats=4 --new ^
 --filter-tcp=443 --hostlist="youtubeGV.txt" --dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-ttl=4 --new ^
 --filter-tcp=443 --hostlist="youtube.txt" --hostlist="other.txt" --hostlist="faceinsta.txt" --ipset="ipset-cloudflare.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=3 --dpi-desync-fake-tls="tls_clienthello_2.bin" --dpi-desync-ttl=3 --new ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-autottl --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-udplen-increment=10 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_2.bin" --dpi-desync-repeats=8 --dpi-desync-cutoff=n2 --new ^
 --filter-udp=50000-50099 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d2 --dpi-desync-fake-quic="quic_1.bin"