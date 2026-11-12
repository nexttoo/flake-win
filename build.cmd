@echo off
rem Сборка Flake для Windows в один exe.
setlocal
cd /d "%~dp0"

echo [1/4] Проверка Python...
python -c "import sys; assert sys.version_info >= (3,10), 'Need Python 3.10+'; print('Python', sys.version.split()[0])"
if errorlevel 1 goto :fail

echo [2/4] Установка зависимостей...
python -m pip install --quiet --disable-pip-version-check --upgrade "PySide6-Essentials>=6.6" numpy pyinstaller pillow
if errorlevel 1 goto :fail

echo [3/4] Иконка приложения...
python make_icon.py
if errorlevel 1 goto :fail

echo [4/4] Сборка FlakeWin.exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name FlakeWin --icon flake.ico ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data ^
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtOpenGL ^
  --exclude-module PySide6.QtDBus --exclude-module PySide6.QtSql ^
  --exclude-module PySide6.QtTest --exclude-module PySide6.QtPrintSupport ^
  --exclude-module PySide6.QtSvg ^
  run_flake.py
if errorlevel 1 goto :fail

echo.
echo Готово: dist\FlakeWin.exe
echo Запуск: dist\FlakeWin.exe
goto :eof

:fail
echo.
echo Сборка не удалась. Смотрите сообщения выше.
exit /b 1
