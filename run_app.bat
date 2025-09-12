@echo off
echo =====================================
echo   Type Beat Video Generator v2.0
echo =====================================
echo.
echo 1. Generador de Videos (main.py)
echo 2. Editor de Thumbnails (thumbnail_editor.py)
echo.
set /p choice="Selecciona una opcion (1-2): "

REM Verificar si existe el entorno virtual
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: No se encontro el entorno virtual .venv
    echo.
    echo Ejecute primero:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install PyQt6 qdarkstyle qtawesome Pillow
    echo.
    pause
    exit /b 1
)

echo Iniciando aplicacion con entorno virtual...
echo.

REM Ejecutar segun la seleccion
if "%choice%"=="1" (
    echo Iniciando Generador de Videos...
    .venv\Scripts\python.exe main.py
) else if "%choice%"=="2" (
    echo Iniciando Editor de Thumbnails...
    .venv\Scripts\python.exe thumbnail_editor.py
) else (
    echo Opcion invalida, iniciando Generador de Videos por defecto...
    .venv\Scripts\python.exe main.py
)

REM Si hay error, mostrar mensaje
if errorlevel 1 (
    echo.
    echo ERROR: La aplicacion termino con errores.
    echo.
    echo Verifica que las dependencias esten instaladas:
    echo   .venv\Scripts\pip install PyQt6 qdarkstyle qtawesome Pillow
    echo.
    pause
)