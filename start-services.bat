@echo off
:: VoiceMode Services Starter for Windows
:: 使用 faster-whisper (CTranslate2) 取代 whisper.cpp
:: Usage: Double-click this file or run from terminal

echo ============================================
echo   VoiceMode Services Starter
echo   (faster-whisper + CUDA)
echo ============================================
echo.

:: 設定 CUDA DLL 路徑（pip 安裝的 nvidia-cublas-cu12 / nvidia-cudnn-cu12）
set CUDA_BIN=%APPDATA%\Python\Python313\site-packages\nvidia\cublas\bin
set CUDNN_BIN=%APPDATA%\Python\Python313\site-packages\nvidia\cudnn\bin
set PATH=%CUDA_BIN%;%CUDNN_BIN%;%PATH%

:: Kokoro TTS
curl -s http://127.0.0.1:8880/health >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Kokoro TTS already running on port 8880
) else (
    echo [Starting] Kokoro TTS on port 8880...
    start /B "" cmd /c "cd /d %USERPROFILE%\.voicemode\services\kokoro && .venv\Scripts\python.exe -m uvicorn api.src.main:app --host 127.0.0.1 --port 8880"
    echo [Waiting] Kokoro loading model...
    timeout /t 15 /nobreak >nul
    curl -s http://127.0.0.1:8880/health >nul 2>&1
    if %errorlevel%==0 (
        echo [OK] Kokoro TTS started successfully
    ) else (
        echo [INFO] Kokoro may need more time to start, check with: curl http://127.0.0.1:8880/health
    )
)

:: Whisper Proxy (faster-whisper + CUDA，內建推論引擎)
curl -s http://127.0.0.1:2023/health >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Whisper Proxy already running on port 2023
) else (
    echo [Starting] Whisper Proxy on port 2023 (faster-whisper small + CUDA)...
    set HF_ENDPOINT=https://hf-mirror.com
    start /B "" "C:\Python313\python.exe" "%USERPROFILE%\.voicemode\whisper-proxy.py"
    echo [Waiting] Loading faster-whisper model...
    timeout /t 10 /nobreak >nul
    curl -s http://127.0.0.1:2023/health >nul 2>&1
    if %errorlevel%==0 (
        echo [OK] Whisper Proxy started successfully
    ) else (
        echo [FAIL] Whisper Proxy failed to start
    )
)

echo.
echo ============================================
echo   Services Status:
echo ============================================
echo   Whisper Proxy:  http://127.0.0.1:2023 (faster-whisper small + CUDA)
echo   Kokoro TTS:     http://127.0.0.1:8880
echo ============================================
echo.
echo   Ready! Use /voicemode:converse in Claude Code
echo.
echo   Press any key to stop all services...
pause >nul

echo.
echo Stopping services...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":2023.*LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8880.*LISTENING"') do taskkill /f /pid %%a >nul 2>&1
echo Services stopped.
