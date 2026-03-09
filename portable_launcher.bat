@echo off
:: Script Launcher Portable (Bisa di Google Drive / USB)
:: Menggunakan relative path (%~dp0) agar tidak error jika pindah folder

cd /d "%~dp0"
echo Posisi Script: %CD%
:: Coba jalankan dengan 'python' (asumsi sudah ada di PATH atau Run environment WinPython)
echo Membuka aplikasi...
python -m streamlit run app.py

:: Jika gagal, mungkin user belum setting path. 
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python tidak ditemukan atau Streamlit gagal dijalankan.
    echo Pastikan Anda menjalankan file ini dari lingkungan WinPython 
    echo atau folder Python sudah terdaftar di System PATH.
    pause
)
