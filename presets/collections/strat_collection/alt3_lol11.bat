@echo off

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "zapret: general (ALT3)" /b "winws.exe" --wf-tcp=80,443,2099,8393-8400,5222,5223 --wf-udp=443,5000-5500,50000-50100 ^
--filter-udp=443 --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
--filter-udp=50000-50100 --ipset="ipset-discord.txt" --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --new ^
--filter-tcp=80 --dpi-desync=fake,split2 --dpi-desync-autottl=2 --dpi-desync-fooling=md5sig --new ^
--filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=split --dpi-desync-split-pos=1 --dpi-desync-autottl --dpi-desync-fooling=badseq --dpi-desync-repeats=8 --new ^
--filter-tcp=2099,5222,5223,8393-8400 --ipset="ipset-cloudflare.txt" --dpi-desync=syndata --new ^
--filter-udp=2099,5222,5223,8393-8400 --ipset="ipset-cloudflare.txt" --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="%BIN%quic_initial_www_google_com.bin" --new ^
--filter-udp=5000-5500 --ipset="ipset-lol-ru.txt" --dpi-desync=fake --dpi-desync-repeats=6 --new ^
--filter-tcp=2099 --ipset="ipset-lol-ru.txt" --dpi-desync=syndata --new ^
--filter-tcp=5222,5223 --ipset="ipset-lol-euw.txt" --dpi-desync=syndata --new ^
--filter-udp=5000-5500 --ipset="ipset-lol-euw.txt" --dpi-desync=fake --dpi-desync-repeats=6 --new