@echo off
REM ── Informe de Aprovechamiento — correr en localhost ─────────────────────────
set CARTOGRAFIA=C:\Users\MiguelAndresBeltranG\Documents\UNERGY\Cartografia

echo Construyendo imagen (primera vez tarda varios minutos)...
docker build -t informe-predio .

if %ERRORLEVEL% neq 0 (
    echo ERROR en el build. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo Abriendo en http://localhost:8501 ...
echo Presiona Ctrl+C para detener.
echo.

docker run --rm -p 8501:8501 ^
  -v "%CARTOGRAFIA%:/cartografia" ^
  -e CARTOGRAFIA_DIR=/cartografia ^
  informe-predio
