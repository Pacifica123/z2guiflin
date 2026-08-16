@echo off
REM Стратегия Ultimate Fix ALT
REM VERSION: 1.1
REM Дата обновления: 2024

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoLogo -NoProfile -Command ^
        "Start-Process -FilePath '%~f0' -ArgumentList 'ELEV' -Verb RunAs"
    exit /b
)
if /i "%1"=="ELEV" shift /1

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "---] zapret: http,https,quic,youtube,discord [---" /b "winws.exe" ^
--wf-tcp=80,443 --wf-udp=443,50000-65535 ^
--filter-tcp=443 --ipset="russia-youtube-rtmps.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_4.bin" --dpi-desync-fooling=badseq --new ^
--filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake,ipfrag2 --dpi-desync-fake-quic="quic_3.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=2 --new ^                                   %YTDB_YTQC%
--filter-tcp=443 --hostlist="youtube.txt" --dpi-desync=fake,multisplit --dpi-desync-fooling=badseq --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=2 --dpi-desync-fake-tls="%~dp0fake\tls_clienthello_2n.bin" --dpi-desync-fake-tls-mod=rnd --dpi-desync-autottl --new ^                     %YTDB_YTPot%
--filter-tcp=80,443 --hostlist="mycdnlist.txt" --dpi-desync=fakeddisorder --dpi-desync-split-pos=2,midsld --dpi-desync-fakedsplit-pattern="%~dp0fake\tls_clienthello_1.bin" --dpi-desync-fooling=badseq --new ^
--filter-tcp=443 --hostlist="discord.txt" --dpi-desync=fakedsplit --dpi-desync-split-pos=midsld-1,1 --dpi-desync-fooling=badseq --dpi-desync-fakedsplit-pattern="%~dp0fake\tls_clienthello_4.bin" --dpi-desync-autottl                      %YTDB_DIS1% --new ^
--filter-tcp=80 --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=sld+1 --dpi-desync-fooling=badseq --new ^
--filter-tcp=443 --dpi-desync=fakedsplit --dpi-desync-fooling=badseq --dpi-desync-split-pos=2,midsld-1 --dpi-desync-fakedsplit-pattern="%~dp0fake\tls_clienthello_4.bin" --new ^
--filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake --dpi-desync-repeats=6 --dpi-desync-fake-quic="%~dp0fake\quic_1.bin" --new ^                         %YTDB_DIS2% 
--filter-udp=50000-50090 --filter-l7=discord,stun --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=d3 --dpi-desync-repeats=6 --new ^                     %YTDB_DIS3% 
--filter-tcp=443 --ipset-ip=XXX.XXX.XXX.XXX/XX,XXX.XXX.XXX.XXX/XX --wssize=1:6 --hostlist-domains=googlevideo.com --dpi-desync=multidisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2 --new ^
--filter-tcp=443 --hostlist-domains=googlevideo.com --dpi-desync=fakeddisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=2,midsld-2 --dpi-desync-fakedsplit-pattern="%~dp0fake\tls_clienthello_7.bin" --dpi-desync-fooling=badseq --dpi-desync-autottl --new ^      %YTDB_WinSZ%




rem set YTDB_YTQC=--dpi-desync=fake --dpi-desync-fake-quic="%~dp0fake\quic_2.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=6
rem set YTDB_YTQC=--dpi-desync=fake,udplen --dpi-desync-udplen-increment=8 --dpi-desync-udplen-pattern=0xFEA82025 --dpi-desync-fake-quic="%~dp0fake\quic_3.bin" --dpi-desync-cutoff=n4 --dpi-desync-repeats=2
rem set YTDB_YTQC=--dpi-desync=fake,udplen --dpi-desync-udplen-increment=25 --dpi-desync-fake-quic="%~dp0fake\quic_3.bin" --dpi-desync-repeats=2 --dpi-desync-cutoff=n3
rem set YTDB_YTQC=[Вы можете добавить сюда свою стратегию]

rem set YTDB_YTPot=--dpi-desync=fake,multisplit --dpi-desync-fooling=badseq --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=2 --dpi-desync-fake-tls-mod=dupsid,sni=drive.google.com --dpi-desync-autottl
rem set YTDB_YTPot=--dpi-desync=multisplit --dpi-desync-split-seqovl=652 --dpi-desync-split-pos=2 --dpi-desync-split-seqovl-pattern="%~dp0fake\tls_clienthello_2.bin"
rem set YTDB_YTPot=[Вы можете добавить сюда свою стратегию]

rem set YTDB_WinSZ=43 --hostlist-domains=googlevideo.com --dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10  --dpi-desync-autottl
rem set YTDB_WinSZ=43 --hostlist-domains=googlevideo.com --dpi-desync=multisplit --dpi-desync-split-seqovl=652 --dpi-desync-split-pos=2 --dpi-desync-split-seqovl-pattern="%~dp0fake\tls_clienthello_2.bin"
rem set YTDB_WinSZ=43 [Вы можете добавить сюда свою стратегию]
rem set YTDB_WinSZ=43 --wssize 1:6 --dpi-desync=fakedsplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld-1 --dpi-desync-fooling=badseq --dpi-desync-autottl

rem set YTDB_DIS1=--hostlist="%~dp0lists\russia-discord.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld-1 --dpi-desync-fooling=badseq --dpi-desync-fake-tls-mod=dupsid,sni=river.rutube.ru,padencap --dpi-desync-autottl
rem set YTDB_DIS1=--ipset="%~dp0lists\russia-discord-ipset.txt" --dpi-desync=syndata,fake,multidisorder --dpi-desync-fake-syndata="%~dp0fake\tls_clienthello_1.bin" --hostlist="%~dp0lists\russia-discord.txt" --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=1,midsld-2 --dpi-desync-fake-tls="%~dp0fake\tls_clienthello_4.bin" --dpi-desync-fooling=badseq --dpi-desync-autottl
rem set YTDB_DIS1=--ipset="%~dp0lists\russia-discord-ipset.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="%~dp0fake\tls_clienthello_4.bin" --dpi-desync-autottl
rem set YTDB_DIS1=--hostlist="%~dp0lists\russia-discord.txt" --dpi-desync=fake --dpi-desync-fooling=badseq --dpi-desync-fake-tls="%~dp0fake\tls_clienthello_2n.bin" --dpi-desync-fake-tls-mod=rnd --dpi-desync-repeats=4 --dpi-desync-autottl
rem set YTDB_DIS1=--hostlist="%~dp0lists\russia-discord.txt" --dpi-desync=fake --dpi-desync-fooling=badseq --dpi-desync-fake-tls-mod=dupsid,sni=drive.google.com,padencap --dpi-desync-repeats=4 --dpi-desync-autottl

rem set YTDB_DIS3=--dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-fake-unknown-udp=0xC30000000108 --dpi-desync-cutoff=n2
rem set YTDB_DIS3=[Вы можете добавить сюда свою стратегию (голос)]
:: Конец блока настройки стратегий ::
