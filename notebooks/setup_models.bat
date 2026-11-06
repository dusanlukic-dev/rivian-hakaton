<<<<<<< HEAD
@echo off
REM Instalacija paketa i modela za risk_pipeline.py (Windows).
REM Pokrenuti iz foldera gde su risk_pipeline.py i risk_config.json:
REM   setup_models.bat               -> samo instalacija
REM   setup_models.bat snimak.mp4    -> instalacija + test na jednom snimku
cd /d "%~dp0"

pip install opencv-python mediapipe numpy ultralytics onnx || goto :err

if not exist models mkdir models
if not exist models\face_landmarker.task curl -L -o models\face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
if not exist models\hand_landmarker.task curl -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
REM yolo11s/640: nano/320 skoro ne vidi telefon na fisheye cabin kameri
if not exist models\yolo11s_640.onnx (
  python -c "from ultralytics import YOLO; YOLO('yolo11s.pt').export(format='onnx', imgsz=640)" || goto :err
  move yolo11s.onnx models\yolo11s_640.onnx
)
dir models

if not "%~1"=="" python risk_pipeline.py --video "%~1" --show
goto :eof

:err
echo Greska tokom instalacije.
exit /b 1
=======
@echo off
REM Preuzimanje modela za risk_pipeline.py (Windows).
REM
REM Pakete prvo instaliraj iz requirements.txt, u venv ili globalno:
REM   python -m pip install -r requirements.txt
REM
REM Zatim pokreni iz foldera gde su risk_pipeline.py i risk_config.json
REM (radi i u cmd i u PowerShell-u; u PowerShell-u je .\ na pocetku obavezan):
REM   .\setup_models.bat               - samo preuzme modele
REM   .\setup_models.bat snimak.mp4    - preuzme modele i pusti test na snimku
REM
REM Tekst je namerno bez dijakritika jer ih cmd ne prikazuje ispravno.

setlocal

REM Putanja do snimka se racuna u odnosu na folder iz kog je skripta pozvana
set "VIDEO="
if not "%~1"=="" set "VIDEO=%~f1"

cd /d "%~dp0"

REM Koristi Python iz aktivnog venv-a, a ako ga nema, sistemski (python, pa py)
set "PY=python"
python --version >nul 2>&1
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo Greska: Python nije pronadjen.
    exit /b 1
)
%PY% -c "import sys; print('Python:', sys.executable)"

REM Provera da su paketi iz requirements.txt instalirani bas za taj Python
%PY% -c "import cv2, mediapipe, numpy, ultralytics, onnx"
if errorlevel 1 (
    echo.
    echo Greska: nisu instalirani svi paketi za ovaj Python.
    echo Instaliraj ih, u venv ili globalno:
    echo   %PY% -m pip install -r requirements.txt
    exit /b 1
)

if not exist models mkdir models
echo Modeli:

call :download "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" "models\face_landmarker.task"
if errorlevel 1 exit /b 1

call :download "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" "models\hand_landmarker.task"
if errorlevel 1 exit /b 1

if exist models\yolo11n_320.onnx (
    echo   [ok] models\yolo11n_320.onnx vec postoji
) else (
    echo   Export YOLO11n u ONNX, imgsz=320 ...
    %PY% -c "from pathlib import Path; from ultralytics import YOLO; Path(YOLO('models/yolo11n.pt').export(format='onnx', imgsz=320)).replace('models/yolo11n_320.onnx')"
    if errorlevel 1 (
        echo Greska: export YOLO modela nije uspeo.
        exit /b 1
    )
)

echo.
echo Instalirani modeli:
for %%F in (models\*) do echo   %%~nxF   %%~zF B

REM Test na snimku ako je prosledjen argument
if "%VIDEO%"=="" goto :kraj
echo.
echo Test na snimku: "%VIDEO%"
%PY% risk_pipeline.py --video "%VIDEO%" --show
if errorlevel 1 exit /b 1

:kraj
echo.
echo Gotovo! Pokretanje:
echo   %PY% risk_pipeline.py --video snimak.mp4 --show
if defined VIRTUAL_ENV echo   U novom terminalu prvo aktiviraj venv: "%VIRTUAL_ENV%\Scripts\activate"
exit /b 0


REM ---------------------------------------------------------------------
REM Preuzima fajl samo ako vec ne postoji. Prvi argument je URL, drugi putanja.
REM Ide preko .part fajla, da prekinuto preuzimanje ne ostavi pokvaren model.
:download
if exist "%~2" (
    echo   [ok] %~2 vec postoji
    exit /b 0
)
echo   Preuzimam %~2 ...
curl.exe -fL --retry 3 -o "%~2.part" "%~1"
if errorlevel 1 (
    if exist "%~2.part" del "%~2.part"
    echo Greska: preuzimanje nije uspelo: %~1
    exit /b 1
)
move /y "%~2.part" "%~2" >nul
exit /b 0
>>>>>>> 0c36827 (requirements i setup skripte finalne)
