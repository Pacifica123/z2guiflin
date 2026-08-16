@echo off

taskkill /f /im winws.exe >nul 2>&1
sc stop windivert >nul 2>&1
sc delete windivert >nul 2>&1
sc delete windivert >nul 2>&1
cd /d "%~dp0"

start "WARP v1" /b "winws.exe" --wf-tcp=80,443 --wf-udp=443,8886 ^
--filter-tcp=80 --hostlist-domains=cloudflareportal.com,cloudflareok.com,cloudflareclient.com,cloudflarecp.com --dpi-desync=fake,multisplit --dpi-desync-split-pos=sld+1 --dpi-desync-fooling=md5sig --dpi-desync-autottl --new ^
--filter-tcp=443 --hostlist-domains=cloudflareok.com,cloudflareclient.com,cloudflareportal.com,cloudflarecp.com --dpi-desync=fake,multisplit --dpi-desync-split-seqovl=1 --dpi-desync-fooling=md5sig,badseq --dpi-desync-fake-tls="tls_clienthello_7.bin" --dpi-desync-fake-tls-mod=rnd,padencap --dpi-desync-autottl --new ^
--filter-udp=8886 --ipset-ip=188.114.96.0/22 --dpi-desync=fake --dpi-desync-any-protocol --dpi-desync-fake-unknown-udp="quic_4.bin" --dpi-desync-cutoff=d2 --dpi-desync-autottl --new ^
--filter-tcp=443 --dpi-desync=fake,multidisorder --dpi-desync-split-seqovl=1 --dpi-desync-split-pos=midsld+1 --dpi-desync-fooling=md5sig,badseq --dpi-desync-fake-tls="tls_clienthello_5.bin" --dpi-desync-fake-tls-mod=rnd --dpi-desync-autottl