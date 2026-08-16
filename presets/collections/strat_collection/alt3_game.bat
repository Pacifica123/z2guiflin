@echo off

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "zapret: winws custom 5" /b "winws.exe" ^
 --wf-tcp=80,443,444-50000 --wf-udp=443,5000-51000 ^
 --filter-udp=443 --hostlist="discord.txt" --hostlist-domains=riotcdn.net,playvalorant.com,riotgames.com,pvp.net,rgpub.io,rdatasrv.net,riotcdn.com,riotgames.es,RiotClientServices.com,LeagueofLegends.com --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-50100 --ipset="ipset-discord.txt" --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --new ^
 --filter-tcp=80 --dpi-desync=fake,split2 --dpi-desync-autottl=2 --dpi-desync-fooling=md5sig --new ^
 --filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=split --dpi-desync-split-pos=1 --dpi-desync-autottl --dpi-desync-fooling=badseq --dpi-desync-repeats=8 --new ^
 --filter-udp=443-9000 --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-tcp=2000-8400 --dpi-desync=syndata