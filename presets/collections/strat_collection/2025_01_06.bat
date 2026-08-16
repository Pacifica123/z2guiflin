@echo off

start "zapret: winws custom" /b "winws.exe" ^
--wf-l3=ipv4,ipv6 --wf-tcp=80,443 --wf-udp=443,50000-50099 ^
--filter-tcp=443 --ipset="russia-youtube-rtmps.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_4.bin" --dpi-desync-autottl --new ^
--filter-tcp=443 --hostlist="youtube_v2.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld+1 --new ^
--filter-tcp=443 --hostlist="youtubeGV.txt" --dpi-desync=multisplit --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld-1 --new ^
--filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=4 --dpi-desync-fake-quic="quic_3.bin" --dpi-desync-cutoff=n3 --dpi-desync-repeats=2 --new ^
--filter-tcp=443 --ipset="ipset-discord.txt" --dpi-desync=syndata --dpi-desync-fake-syndata="tls_clienthello_3.bin" --dpi-desync-autottl --new ^
--filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake,udplen --dpi-desync-udplen-increment=5 --dpi-desync-udplen-pattern=0xDEADBEEF --dpi-desync-fake-quic="quic_2.bin" --dpi-desync-repeats=7 --dpi-desync-cutoff=n2 --new ^
--filter-udp=50000-50090 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-cutoff=n3 --new ^
--filter-tcp=443 --hostlist-domains=googlevideo.com --dpi-desync=multidisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2 --new
--filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq --dpi-desync-repeats=10 --dpi-desync-autottl --new ^