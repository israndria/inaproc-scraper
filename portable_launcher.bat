@echo off
setlocal
:: Launcher source lokal; dokumen/output tidak berada di repo ini.

cd /d "%~dp0"
echo Posisi Script: %CD%
set "PYTHON=%POKJA_PYTHON_SYS%"
if not defined PYTHON set "PYTHON=C:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe"
echo Membuka aplikasi...
"%PYTHON%" -m streamlit run app.py --server.port 8511 --server.headless true --browser.gatherUsageStats false

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python lokal tidak ditemukan atau Streamlit gagal dijalankan.
    pause
)
