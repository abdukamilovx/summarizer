@echo off
echo ============================================
echo   VoiceScribe Desktop — Build EXE
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Installing PyInstaller...
pip install pyinstaller --quiet

echo [2/3] Building executable...
pyinstaller voicescribe.spec --noconfirm --clean

echo [3/3] Copying .env to dist folder...
if exist ".env" (
    copy ".env" "dist\VoiceScribe\.env" >nul
    echo   .env copied.
) else (
    copy ".env.example" "dist\VoiceScribe\.env" >nul
    echo   .env.example copied as .env — please add your API key!
)

echo.
echo ============================================
echo   BUILD COMPLETE!
echo   Output: dist\VoiceScribe\VoiceScribe.exe
echo ============================================
echo.
echo To run:  dist\VoiceScribe\VoiceScribe.exe
echo Make sure .env has your OPENAI_API_KEY
pause
