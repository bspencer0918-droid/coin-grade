@echo off
echo Starting Chrome with remote debugging on port 9222...
echo.
echo After Chrome opens:
echo   1. Log in to ha.com if not already logged in
echo   2. Keep this Chrome window open
echo   3. Run the scraper normally
echo.

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% (
    echo Chrome not found at default location.
    echo Edit this file and set the CHROME variable to your chrome.exe path.
    pause
    exit /b 1
)

%CHROME% --remote-debugging-port=9222 --user-data-dir="%APPDATA%\ChromeDebug"
