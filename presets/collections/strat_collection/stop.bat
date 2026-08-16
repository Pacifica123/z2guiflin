@echo off
echo Останавливаем все процессы winws.exe...

REM Останавливаем все процессы напрямую
taskkill /F /IM winws.exe /T

REM Останавливаем и удаляем службу WinDivert если она существует
sc stop windivert
sc delete windivert

REM Явно выходим с кодом успешного завершения
exit /b 0