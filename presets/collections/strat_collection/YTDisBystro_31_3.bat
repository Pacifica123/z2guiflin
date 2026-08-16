@echo off

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "YTDisBystro 3.1 v3" /b "winws.exe" --wf-tcp=80,443 --wf-udp=443,50000-50100 ^
--filter-tcp=443 --ipset="russia-youtube-rtmps.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_7.bin" --dup=2 --dup-cutoff=n3 --new ^
--filter-udp=443 --hostlist="russia-youtubeQ.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=4 --dpi-desync-fake-quic="quic_4.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=2 --new ^
--filter-tcp=443 --hostlist-domains=googlevideo.com --hostlist="russia-youtube.txt" --ipcache-hostname --dpi-desync=syndata,fake,multisplit --dpi-desync-split-pos=sld+1 --dpi-desync-fake-syndata="tls_clienthello_7.bin" --dpi-desync-fake-tls=0x0F0F0E0F --dpi-desync-fake-tls="tls_clienthello_9.bin" --dpi-desync-fake-tls-mod=rnd,dupsid --dpi-desync-fooling=md5sig --dpi-desync-autottl --dup=2 --dup-fooling=md5sig --dup-autottl --dup-cutoff=n3 --new ^
--filter-tcp=80 --hostlist="mycdnlist.txt" --hostlist="russia-blacklist.txt" --hostlist="myhostlist.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=sld+1 --dpi-desync-fake-http=0x0F0F0F0F --dpi-desync-fooling=md5sig --dup=2 --dup-fooling=md5sig --dup-cutoff=n3 --new ^
--filter-tcp=443 --hostlist-domains=animego.online,doramy.club,animejoy.ru,getchu.com --dpi-desync=multisplit --dpi-desync-split-seqovl=308 --dpi-desync-split-seqovl-pattern="tls_clienthello_15.bin" --new ^
--filter-tcp=443 --hostlist="russia-blacklist.txt" --hostlist="myhostlist.txt" --hostlist="mycdnlist.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=308 --dpi-desync-split-seqovl-pattern="tls_clienthello_9.bin" --dup=2 --dup-cutoff=n3 --new ^
--filter-tcp=443 --ipset-exclude-ip=1.1.1.1, 1.0.0.1, 212.109.195.93, 83.220.169.155, 141.105.71.21 --ipset="cloudflare-ipset.txt" --dpi-desync=fake,multidisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=sld+1 --dpi-desync-fake-tls=0x0F0F0E0F --dpi-desync-fake-tls="tls_clienthello_9.bin" --dpi-desync-fake-tls-mod=rnd,dupsid --dpi-desync-fooling=md5sig --dpi-desync-autottl --dup=2 --dup-fooling=md5sig --dup-autottl --dup-cutoff=n3 --new ^
--filter-udp=50000-50090 --filter-l7=discord,stun --dpi-desync=fake --dpi-desync-autottl --dup=2 --dup-autottl --dup-cutoff=n3 --new ^
--filter-tcp=80 --hostlist="other.txt" --hostlist-exclude="netrogat.txt" --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=2 --dpi-desync-split-pos=host+1 --dpi-desync-fake-http=0x0F0F0F0F --dpi-desync-fooling=md5sig --new ^
--filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=fake,fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fake-tls="tls_clienthello_9.bin" --dpi-desync-fooling=badseq --dpi-desync-autottl