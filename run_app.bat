@echo off
title Type Beat Video Generator v2.0
echo =====================================
echo   Type Beat Video Generator v2.0
echo =====================================
echo.
echo Iniciando aplicacion...
echo.

REM Verificar si existe el entorno virtual
if not exist ".venv\Scripts\python.exe" (
    echo ❌ ERROR: No se encontro el entorno virtual .venv
    echo.
    echo Para crear el entorno virtual ejecute:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Verificar si existe el archivo main.py
if not exist "main.py" (
    echo ❌ ERROR: No se encontro main.py
    echo Asegurese de estar en el directorio correcto del proyecto.
    echo.
    pause
    exit /b 1
)

REM Verificar si FFmpeg existe
if not exist "bin\ffmpeg.exe" (
    echo ⚠️  ADVERTENCIA: No se encontro FFmpeg en bin\ffmpeg.exe
    echo Los videos no se podran generar sin FFmpeg.
    echo Continuando de todas formas...
    echo.
)

echo ✅ Iniciando Type Beat Video Generator v2.0...
echo.

REM Activar entorno virtual y ejecutar la aplicacion
call .venv\Scripts\activate.bat
.venv\Scripts\python.exe main.py

REM Verificar si hubo errores
if errorlevel 1 (
    echo.
    echo ❌ ERROR: La aplicacion termino con errores.
    echo.
    echo Posibles soluciones:
    echo 1. Verificar que las dependencias esten instaladas:
    echo    .venv\Scripts\pip install -r requirements.txt
    echo 2. Verificar que Python este instalado correctamente
    echo 3. Revisar los mensajes de error anteriores
    echo.
) else (
    echo.
    echo ✅ Aplicacion cerrada correctamente.
    echo.
)

echo Presiona cualquier tecla para salir...
pause >nul