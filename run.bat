@echo off
echo ============================================
echo   SmartSort AI — Native Desktop App
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found on PATH. Please install Python 3.10+.
    pause
    exit /b 1
)

REM Install/verify dependencies
echo Checking dependencies...
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

python -c "import webview" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing pywebview...
    pip install pywebview
)

REM Check if model exists
if not exist "models\classifier.joblib" (
    echo.
    echo Model not found. Training classifier...
    python scripts\train_model.py
    if %ERRORLEVEL% neq 0 (
        echo WARNING: Model training failed. AI classification may be limited.
    )
)

echo.
echo Starting SmartSort AI...
echo.

python main.py

pause
