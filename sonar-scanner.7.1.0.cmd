@echo off
call "./sonar-scanner-7.1.0/bin/sonar-scanner.bat"
pause
rmdir /S/Q .scannerwork
