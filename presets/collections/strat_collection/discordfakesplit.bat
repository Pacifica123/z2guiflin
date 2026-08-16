@echo off
REM Стратегия Discord Fake Split
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

start "zapret: winws Discord_fake_and_split" /b "winws.exe" ^
 --wf-tcp=80,443 --wf-udp=443,50000-50100 ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-50010 --ipset="ipset-discord.txt" --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --new ^
 --filter-tcp=80 --hostlist="discord.txt" --dpi-desync=fake,split2 --dpi-desync-autottl=2 --dpi-desync-fooling=md5sig --new ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fake,split --dpi-desync-repeats=6 --dpi-desync-fooling=badseq --dpi-desync-fake-tls="tls_clienthello_www_google_com.bin" --new ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake --dpi-desync-repeats=2 --dpi-desync-cutoff=n2 --dpi-desync-fake-quic="quic_test_00.bin" --new ^
 --filter-tcp=443 --hostlist="youtubeGV.txt" --dpi-desync=split --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-cutoff=d2 --dpi-desync-ttl=4 --new ^
 --filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=fake,split2 --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=3 --new ^
 --filter-tcp=443 --dpi-desync=fake,split2 --dpi-desync-split-seqovl=1 --dpi-desync-split-tls=sniext --dpi-desync-fake-tls="tls_clienthello_3.bin" --dpi-desync-ttl=2