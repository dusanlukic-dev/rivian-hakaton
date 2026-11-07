# rivian_model: naš model (pažnja vozača) za koordinator

Ovo je **drugi model**, pored modela CV tima (`notebooks/risk_pipeline.py` + `model/worker.py`). U ovoj kopiji
(`rivian-demo`, grana `nas-demo`) je **podrazumevani model za demo**. CV model i dalje radi istim backendom (`demo.ps1 -Model cv`).

## Šta radi

Prima frejmove od koordinatora (isti protokol kao `model/worker.py`: `hello` → `frame` → `detection`, uz `reset` i `idle`)
i za svaki frejm vraća dokaz 0–1 po kategoriji:

| Naš signal | Kategorija za koordinator | Iz čega |
|---|---|---|
| telefon | `phone_use` | yolo11n (640) + filter „u šaci ili uz glavu“ + poza |
| pogled van puta | `eyes_off_road` | MediaPipe ugao glave, neprekidna kalibracija |
| zatvorene oči | `eyes_closed` | MediaPipe blendshapes, u odnosu na lični nivo |
| **pad vozača** | `collapse` | yolo11n-pose: glava ispod ramena + telo miruje ≥ 1 s |

**Kolaps radi do kraja** u ovoj kopiji: kategorija `collapse` u `notebooks/risk_config.json` (crveni alarm modela),
`Behavior.COLLAPSE` u backendu, a potvrđen kolaps (2 s) daje skor 0, crveno, glasan alarm i poruku kontaktu odmah,
i kad auto stoji (`backend/app/coordinator/services/scoring.py`, `tests/test_collapse.py`). Aplikacija i dashboard
prikazuju „Driver not responding“.

## Pokretanje

```powershell
cd rivian_model
python setup_models.py                      # jednom: modeli (nisu u gitu)
python rivian_detector.py --camera 08_14    # javlja se koordinatoru na ws://127.0.0.1:8000/api/v1/model/ws
python test_rivian_detector.py 08_14_62_092916   # test bez backenda (lažni koordinator, isti protokol)
docker build -t rivian-model .              # kontejner; podrazumevano pokreće rivian_detector.py
```

- `--camera 05_23` za drugu seriju kamera. Protokol ne šalje koja je kamera, pa se zona vozača bira ovde.
- Brojevi (CPU i5-1235U, na struji): ~73 ms po frejmu (i u Docker-u), spreman ~4–5 s posle pokretanja, ~490 MB RAM u Docker-u.
- Test: 092916 → skor 40 (telefon 12.6–24.2 s), 031246 → kolaps od 11.0 s.
- Detalji: `ATRIBUTI.md` (signali, tačnost na 56 klipova, šta ne obećavamo) i `PLAN_KOORDINATOR.md` (nalazi o backendu, sekcije 8–8.2).
