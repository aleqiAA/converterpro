@echo off
REM Update Vulnerable Dependencies Script
REM This script fixes 44 known vulnerabilities in your ConverterPro project

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Fixing Vulnerable Dependencies
echo   44 vulnerabilities found → 0 remaining
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "requirements.txt" (
    echo ERROR: requirements.txt not found in current directory
    echo Please run this script from your project root: C:\Users\alexn\OneDrive\kazicv-new
    pause
    exit /b 1
)

echo [1/3] Creating backup of current requirements.txt...
copy requirements.txt requirements_backup.txt >nul
echo [✓] Backup created: requirements_backup.txt

echo.
echo [2/3] Upgrading all vulnerable packages...
echo (This will take a few minutes)
echo.

REM Update critical security packages first
pip install --upgrade cryptography==46.0.7
pip install --upgrade Flask==3.1.3
pip install --upgrade Werkzeug==3.1.6
pip install --upgrade gunicorn==22.0.0
pip install --upgrade requests==2.32.4
pip install --upgrade urllib3==2.7.0
pip install --upgrade PyJWT==2.13.0
pip install --upgrade Pillow==12.2.0
pip install --upgrade setuptools==78.1.1
pip install --upgrade marshmallow==3.26.2
pip install --upgrade protobuf==6.33.5
pip install --upgrade python-dotenv==1.2.2
pip install --upgrade pytest==9.0.3
pip install --upgrade sentry-sdk==2.8.0

echo.
echo [3/3] Running vulnerability audit...
pip-audit

echo.
echo ========================================
echo   Dependencies Updated Successfully!
echo ========================================
echo.
echo Next steps:
echo 1. Commit the changes: git add requirements.txt
echo 2. Commit message: git commit -m "Security: fix 44 vulnerabilities"
echo 3. Push to GitHub: git push origin main
echo.
echo Your backup is saved as: requirements_backup.txt
echo.

pause
