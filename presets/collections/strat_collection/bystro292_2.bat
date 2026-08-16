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

start "---] zapret: http,https,quic,youtube,discord [---" /b "winws.exe" ^
--wf-tcp=80,443 --wf-udp=443,50000-65535 ^
--filter-tcp=443 --ipset="russia-youtube-rtmps.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_4.bin" --dpi-desync-fooling=badseq --new ^
--filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=4 --dpi-desync-fake-quic="quic_4.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=2 --new ^
--filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld+1 --dpi-desync-split-seqovl-pattern="tls_clienthello_7.bin" --new ^
--filter-tcp=80,443 --hostlist="mycdnlist.txt" --dpi-desync=fakeddisorder --dpi-desync-split-pos=2,midsld --dpi-desync-fakedsplit-pattern="tls_clienthello_1.bin" --dpi-desync-fooling=badseq --new ^
--filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-fooling=badseq --dpi-desync-fake-tls="tls_clienthello_7.bin" --dpi-desync-fake-tls-mod=rnd --new ^
--filter-tcp=80 --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=sld+1 --dpi-desync-fooling=badseq --new ^
--filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=fakeddisorder --dpi-desync-split-pos=2,midsld+1 --dpi-desync-fakedsplit-pattern="tls_clienthello_4.bin" --dpi-desync-fooling=badseq --new ^
--filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=5 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_2.bin" --dpi-desync-repeats=7 --dpi-desync-cutoff=n2 --new ^
--filter-udp=50000-50090 --filter-l7=discord,stun --dpi-desync=fake --new ^
--filter-tcp=443 --ipset-ip=XXX.XXX.XXX.XXX/XX,XXX.XXX.XXX.XXX/XX --wssize=1:6 --hostlist-domains=googlevideo.com --dpi-desync=multidisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2 --new ^
--filter-tcp=443 --hostlist-domains=googlevideo.com --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=2,midsld-2 --dpi-desync-split-seqovl-pattern="tls_clienthello_7.bin"