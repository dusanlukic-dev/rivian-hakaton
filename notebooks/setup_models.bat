@echo off
REM Preuzimanje modela za risk_pipeline.py i model/worker.py (Windows).
REM
REM Modeli idu u notebooks\models\ (nije u gitu):
REM   face_landmarker.task, hand_landmarker.task  - samo se preuzmu (curl, Python ne treba)
REM   yolo11s_640.onnx                            - export iz ultralytics (treba ultralytics + onnx)
REM yolo11s/640 jer nano/320 skoro ne vidi telefon na fisheye cabin kameri (risk_config.json: yolo_onnx).
REM
REM Pakete prvo instaliraj iz requirements.txt, u venv ili globalno:
REM   python -m pip install -r requirements.txt
REM
REM Zatim pokreni iz bilo kog foldera (radi i u cmd i u PowerShell-u; u PowerShell-u je .\ na pocetku obavezan):
REM   .\setup_models.bat               - samo preuzme modele
REM   .\setup_models.bat snimak.mp4    - preuzme modele i pusti test na snimku
REM
REM Tekst je namerno bez dijakritika jer ih cmd ne prikazuje ispravno.

setlocal

REM Putanja do snimka se racuna u odnosu na folder iz kog je skripta pozvana
set "VIDEO="
if not "%~1"=="" set "VIDEO=%~f1"

cd /d "%~dp0"

if not exist models mkdir models
echo Modeli:

call :download "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" "models\face_landmarker.task"
if errorlevel 1 exit /b 1

call :download "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" "models\hand_landmarker.task"
if errorlevel 1 exit /b 1

if exist models\yolo11s_640.onnx (
    echo   [ok] models\yolo11s_640.onnx vec postoji
    goto :yolo_done
)
call :find_python
if errorlevel 1 exit /b 1
call :need_packages "ultralytics, onnx"
if errorlevel 1 exit /b 1
echo   Export YOLO11s u ONNX, imgsz=640 ...
%PY% -c "from pathlib import Path; from ultralytics import YOLO; Path(YOLO('models/yolo11s.pt').export(format='onnx', imgsz=640)).replace('models/yolo11s_640.onnx')"
if errorlevel 1 (
    echo Greska: export YOLO modela nije uspeo.
    exit /b 1
)
:yolo_done

echo.
echo Instalirani modeli:
for %%F in (models\*) do echo   %%~nxF   %%~zF B

REM Test na snimku ako je prosledjen argument
if "%VIDEO%"=="" goto :kraj
call :find_python
if errorlevel 1 exit /b 1
call :need_packages "cv2, mediapipe, numpy"
if errorlevel 1 exit /b 1
echo.
echo Test na snimku: "%VIDEO%"
%PY% risk_pipeline.py --video "%VIDEO%" --show
if errorlevel 1 exit /b 1

:kraj
echo.
echo Gotovo! Pokretanje:
echo   python risk_pipeline.py --video snimak.mp4 --show
if defined VIRTUAL_ENV echo   U novom terminalu prvo aktiviraj venv: "%VIRTUAL_ENV%\Scripts\activate"
exit /b 0


REM ---------------------------------------------------------------------
REM Python iz aktivnog venv-a, a ako ga nema, sistemski (python, pa py). Postavlja PY.
:find_python
if defined PY exit /b 0
set "PY=python"
python --version >nul 2>&1
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
    set "PY="
    echo Greska: Python nije pronadjen.
    exit /b 1
)
%PY% -c "import sys; print('Python:', sys.executable)"
exit /b 0

REM Provera da su paketi iz requirements.txt instalirani bas za taj Python. Argument: moduli za import.
:need_packages
%PY% -c "import %~1"
if errorlevel 1 (
    echo.
    echo Greska: nisu instalirani svi paketi za ovaj Python ^(treba: %~1^).
    echo Instaliraj ih, u venv ili globalno:
    echo   %PY% -m pip install -r requirements.txt
    exit /b 1
)
exit /b 0

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
