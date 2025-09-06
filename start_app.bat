@echo off
echo Instalando dependencias...
pip install -r requirements.txt
echo.
echo Iniciando Type Beat Video Generator...
python main.py
pause
