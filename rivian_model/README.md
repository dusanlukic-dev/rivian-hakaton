# rivian_model: naš model (pažnja vozača) za koordinator

**Model sistema** od 7. 11. 2026 (spojen sa grane `nas-demo` u `main`). Model CV tima (`model/worker.py` +
`notebooks/risk_pipeline.py`) je uklonjen; ostaje u git istoriji (`git show 8d05c97:model/worker.py`).

## Šta radi

Javlja se koordinatoru (`WS /api/v1/model/ws`: `hello` → `frame` → `detection`, uz `reset` i `idle`; protokol u
`docs/ARCHITECTURE.md`) i za svaki frejm vraća dokaz 0–1 po kategoriji:

| Naš signal | Kategorija za koordinator | Iz čega |
|---|---|---|
| telefon | `phone_use` | yolo11n (640) + filter „u šaci ili uz glavu“ + poza |
| pogled van puta | `eyes_off_road` | MediaPipe ugao glave, neprekidna kalibracija |
| zatvorene oči | `eyes_closed` | MediaPipe blendshapes, u odnosu na lični nivo |
| **pad vozača** | `collapse` | yolo11n-pose: glava ispod ramena + telo miruje ≥ 1 s |

Rizik, alarm, skor 0–100 i reakciju kola računa koordinator (`RiskEngine` + `scoring.py`). Potvrđen kolaps (2 s) daje
skor 0, crveno, glasan alarm i poruku kontaktu odmah, i kad auto stoji (`backend/tests/test_collapse.py`). Aplikacija i
dashboard tada pišu „The driver is not responding“.

## Pokretanje (Windows, iz korena repoa)

Jednom (modeli i slika za zagrevanje nisu u gitu):
```powershell
py -3.13 -m venv rivian_model\.venv
rivian_model\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
rivian_model\.venv\Scripts\python.exe -m pip install -r rivian_model\requirements.txt
rivian_model\.venv\Scripts\python.exe rivian_model\setup_models.py      # modeli; slika za zagrevanje vise ne treba
```
Ceo auto (skladište, server, koordinator, Bluetooth, model, kamera), svaki deo u svom prozoru: `.\demo.ps1 -PoVoznji`
(README.md u korenu). Pojedinačno:
```powershell
rivian_model\.venv\Scripts\python.exe rivian_model\rivian_detector.py --camera 05_23    # javlja se na ws://127.0.0.1:8000/api/v1/model/ws
backend\.venv\Scripts\python.exe tools\camera_stream.py --video ..\dataset\05_23_62_031246_video_inCabin.mp4
backend\.venv\Scripts\python.exe rivian_model\klip_po_voznji.py     # umesto kamere: svaka vožnja iz aplikacije = sledeći klip
rivian_model\.venv\Scripts\python.exe rivian_model\test_rivian_detector.py 08_14_62_092916   # bez backenda (lažni koordinator)
backend\.venv\Scripts\python.exe rivian_model\run_compare.py --port 8000 --clip <klip>.mp4 --label nas --out <folder>  # kroz pravi koordinator
```

- **GPU:** `--device auto` (podrazumevano) uzima GPU ako ga ONNX Runtime ima: na Windows-u `onnxruntime-directml` (bilo koja
  DX12 kartica, NVIDIA/AMD/Intel), na Linux-u `onnxruntime-gpu` (CUDA); inače CPU, i na CPU pada sam ako GPU zakaže.
  `--device cpu|gpu` ili `$env:MODEL_DEVICE`; `$env:MODEL_GPU_ID` bira DirectML karticu. Na GPU-u telefon-YOLO ide na svaki
  frejm. Koji uređaj radi: prva linija prozora modela i `GET /api/v1/coordinator/status` (`model.device`).
- Zagrevanje: sivi frejm pri pokretanju (~2-3 s), bez slike iz dataseta.
- Dataset: `$env:DATASET_DIR`, inače folder `dataset` pored repoa (`..\dataset`), inače Dušanov put.
- `--camera 05_23` / `08_14`: zona vozača po seriji kamere (`rois.json`). Protokol ne šalje koja je kamera, pa svi klipovi
  jednog pokretanja moraju biti iz iste serije (`klip_po_voznji.py` to proverava).
- Koordinator prima jednu kameru: dok jedna šalje, druga je odbijena (HTTP 403), jer bi model video dva vozača.
- Brojevi (Dušan, CPU i5-1235U, na struji): ~73 ms po frejmu (i u Docker-u), spreman ~4–5 s posle pokretanja, ~490 MB RAM u Docker-u.
  Matijin laptop (Ryzen 5 5600H + GTX 1650): CPU ~43 ms po frejmu, **GPU (DirectML) ~25 ms** sa telefonom na svakom frejmu.
- `test_rivian_detector.py` uzima bilo koji slobodan port (Windows rezerviše opsege portova, npr. 8685–8884 ovde).
- Detalji: `ATRIBUTI.md` (signali, tačnost na 56 klipova, šta ne obećavamo), `POREDJENJE_MODELA.md` (naš model i model CV
  tima kroz isti koordinator), `PLAN_KOORDINATOR.md` (kako je uklopljen).
- Docker: `Dockerfile` (Dušan ga je proverio na svom laptopu); sledeći korak je slika za svaki deo sistema.
