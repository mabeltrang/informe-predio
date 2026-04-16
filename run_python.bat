@echo off
REM ── Informe de Aprovechamiento — correr en Python nativo ─────────────────────────
set CARTOGRAFIA=C:\Users\MiguelAndresBeltranG\Documents\UNERGY\Cartografia

echo Verificando entorno virtual (venv)...
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
)

echo Activando entorno virtual...
call venv\Scripts\activate.bat

echo Instalando dependencias...
pip install -r requirements.txt

echo.
echo Iniciando aplicacion con Streamlit...
echo Presiona Ctrl+C para detener.
echo.

set CARTOGRAFIA_DIR=%CARTOGRAFIA%
streamlit run app.py
