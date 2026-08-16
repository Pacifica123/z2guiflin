@echo off

start "zapret: winws Ankdev v10" /b "winws.exe" ^
 --wf-l3=ipv4,ipv6 --wf-tcp=443 --wf-udp=443,50000-65535 ^
 --filter-tcp=443 --hostlist="discord.txt" --dpi-desync=syndata,disorder2 --dpi-desync-split-pos=3 --dpi-desync-repeats=11 --dpi-desync-fooling=badseq --dpi-desync-fake-tls="tls_clienthello_www_google_com.bin" --new ^
 --filter-udp=443 --hostlist="discord.txt" --dpi-desync=fake,split2 --dpi-desync-repeats=11 --dpi-desync-udplen-increment=15 --dpi-desync-fake-quic="quic_initial_www_google_com.bin" --new ^
 --filter-udp=50000-50099 --ipset="ipset-discord.txt" --dpi-desync=fake,tamper --dpi-desync-any-protocol --dpi-desync-cutoff=d5 --dpi-desync-repeats=11 --new ^
 --filter-tcp=443 --hostlist-exclude="netrogat.txt" --dpi-desync=syndata,multidisorder --dpi-desync-split-pos=4 --dpi-desync-repeats=10 --dpi-desync-fooling=md5sig --dpi-desync-fake-tls="tls_clienthello_vk_com_kyber.bin" --new ^
 --filter-udp=443 --hostlist="youtubeQ.txt" --dpi-desync=fake,split2 --dpi-desync-repeats=10 --dpi-desync-udplen-increment=25 --dpi-desync-fake-quic="quic_initial_www_google_com.bin"