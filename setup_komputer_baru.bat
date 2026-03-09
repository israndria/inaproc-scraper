@echo off
:: Script Setup untuk Komputer Baru (Misal: Kantor)
:: Pastikan Python sudah terinstall sebelum menjalankan ini!

cd /d "%~dp0"
echo Sedang menginstall library...
python -m pip install -r requirements.txt

echo.
echo Sedang menginstall browser Chromium untuk robot...
playwright install chromium

echo.
echo SELESAI! Sekarang Anda bisa jalankan 'portable_launcher.bat'
pause
