# Model worker

Svoj proces i svoje okruženje (kasnije svoj Docker kontejner). Prima frejmove od **koordinatora**, detektuje
i vraća **dokaz** po kategoriji (`phone_use`, `eyes_off_road`, `hands_off_wheel`, `eating_drinking`,
`drowsiness`, `eyes_closed`). Sve posle toga (glađenje, trajanje, rizik, alarm, score 0–100, reakcija kola)
računa koordinator. Arhitektura i protokol: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

```
koordinator ──frejm (JPEG + id, t)──► worker: detektori CV tima ──► dokaz p po kategoriji
koordinator ◄──detekcija (JSON)──────┘
```

Kod CV tima se koristi **bez izmena**: `FacePerception`, `HandPerception`, `ObjectPerception` i
`FeatureExtractor` iz `notebooks/risk_pipeline.py`, pragovi iz `notebooks/risk_config.json`, modeli iz
`notebooks/models/`. Njihov `RiskEngine` se ovde ne koristi: izdvojen je u koordinator
(`backend/app/coordinator/services/risk_engine.py`).

## Pokretanje

Prvo backend (`backend/`: `python run.py`) i kamera (`python tools/camera_stream.py`). Worker se sam javlja
koordinatoru na `ws://127.0.0.1:8000/api/v1/model/ws` i ponovo se povezuje ako backend restartuje.

**Bez CV paketa** (test celog toka, demo bez kamere): skriptovane detekcije u krugu od 60 s (telefon 14–20 s,
pogled van puta 28–31 s, mikrospavanje 38–41 s, ruke van volana 48–52 s). Radi i u backend venv-u:
```powershell
backend\.venv\Scripts\python.exe model\worker.py --fake
```

**Pravi model CV tima** (svoje okruženje):
```powershell
py -3.12 -m venv model\.venv                 # ili 3.13, ako postoji mediapipe wheel za tu verziju
model\.venv\Scripts\python.exe -m pip install -r model\requirements.txt
notebooks\setup_models.bat                   # modeli u notebooks\models (vidi ispod)
model\.venv\Scripts\python.exe model\worker.py
```
- `setup_models.bat` (Linux: `bash notebooks/setup_models.sh`) skine `face_landmarker.task` i
  `hand_landmarker.task` (treba samo curl) i jednom izveze `yolo11s_640.onnx`. Za izvoz treba Python sa
  `ultralytics` i `onnx` (CV okruženje: `python -m pip install -r notebooks\requirements.txt`), a ne venv
  workera: worker YOLO pokreće preko `cv2.dnn` i ne treba mu ultralytics.
- Bez YOLO modela (`notebooks/models/yolo11s_640.onnx`) worker radi, ali telefon vidi samo preko pogleda u krilo.
- Druga mašina (npr. laptop sa GPU-om): `--coordinator ws://<IP koordinatora>:8000/api/v1/model/ws`
  (port 8000 je već otvoren na firewall-u, nov port ne treba).
- Docker (planirano, još nije testirano): `model/Dockerfile`, build iz korena repoa.

Koordinator pokazuje stanje workera na `GET /api/v1/coordinator/status` (`model`: povezan, frejmova u
sekundi, kašnjenje, izgubljeni frejmovi). Worker na 10 s ispiše koliko frejmova obrađuje i za koliko ms.