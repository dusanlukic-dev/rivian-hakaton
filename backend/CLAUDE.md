# Backend (FastAPI)

Python 3.13, FastAPI, Pydantic v2. Zavisnosti su u `requirements.txt`, a virtuelno okruženje u `.venv/`.

## Komande (iz `backend/`, Windows)

```powershell
.venv\Scripts\activate                      # prvi put: python -m venv .venv; pip install -r requirements.txt
python run.py                               # 0.0.0.0:8000 + ispis IP-a za telefon (auto-reload)
fastapi dev app/main.py                     # samo lokalno, http://127.0.0.1:8000/docs
pytest                                      # testovi
python ..\notebooks\safety_client.py --interval 0.3   # simulirana vožnja (server mora da radi)
python ..\notebooks\safety_client.py --replay frames.jsonl --speedup 2   # snimljen izlaz modela
```

## Slojevi

- `app/api/routes/`: tanke rute. Samo HTTP (status kodovi, 404/409), poziv servisa i slanje
  događaja preko `hub.broadcast`. `live.py` sadrži `POST /telemetry` i `WS /ws`.
- `app/schemas/`: Pydantic modeli, odnosno ugovor sa frontom. Svaku promenu prenesi u `../docs/API.md`.
- `app/domain/`: enumi (`Behavior`, `SafetyLevel`, `LiveEvent`...) i `Trip` dataclass (interno stanje).
- `app/services/`: sva logika, bez FastAPI-ja (osim `live.py`, koji drži WebSocket konekcije).
- `app/repositories/trips.py`: in-memory skladište. Za bazu zameniti klasu, a zadržati
  `add/get/active/list`.

## Gde šta

| Hoćeš da... | Fajl |
|---|---|
| podesiš penale, brzinu, noć, oporavak | `ScoringConfig` u `app/services/scoring.py` |
| promeniš opsege ili reakciju kola | `LEVEL_BANDS` / `POLICIES` u `app/services/alerts.py` |
| dodaš ponašanje | `Behavior` u `app/domain/enums.py`, `_default_weights` u `scoring.py`, `TIPS` u `app/services/trips.py`, `BEHAVIORS` u `notebooks/safety_client.py`, `docs/API.md` |
| preslikaš kategoriju modela na labelu | `CATEGORY_TO_BEHAVIOR` u `app/services/camera.py` |
| promeniš šta od frejma modela ide aplikaciji | `CameraView` u `app/domain/trip.py`, `to_view` u `app/services/camera.py`, ulaz u `app/schemas/camera.py`, `docs/API.md` |
| promeniš alarm modela | `evaluate_response` i `CAMERA_ALARM_MESSAGE` u `app/services/alerts.py` |
| dodaš WebSocket događaj | `LiveEvent` u `enums.py`, `hub.broadcast` u ruti, `LiveMessage` u `docs/API.md` |
| pravi SMS ili push | `app/services/notifications.py` (sada stub) |
| pravu bazu | `app/repositories/trips.py` |
| novo podešavanje | `Settings` u `app/core/config.py` i `.env` |

## Zamke

- Rute koje menjaju stanje (`POST /trips`, `/telemetry`, `/trips/{id}/end`) su `async def`, pa se
  izvršavaju redom na event loop-u i nema trka nad deljenim in-memory stanjem. **Ne prebacuj ih
  u `def`**, jer bi tada radile paralelno u threadpool-u.
- Svaki `Behavior` mora imati težinu i `TIPS` savet. Test `test_every_behavior_has_a_weight_and_a_tip`
  to proverava.
- `timestamp` u ticku je lokalno vreme sa offsetom. Sat iz njega određuje noćne penale. Razmak između
  tickova je ograničen na 5 s.
- Ispod 5 km/h: nema penala, nema oporavka, nema upozorenja i ne ulazi u statistiku.
- Skladište je u memoriji, pa restart briše sve vožnje.
- Tick može imati `behaviors` (labele), `frame` (zapis modela) ili oba, a labele se spajaju.
  `ModelFrame` deklariše samo polja koja koristimo, a ostala (`perception`, `p_hat`, `D_s`...)
  Pydantic ignoriše. NaN/inf iz modela postaju `null`, jer bi inače pokvarili `JSON.parse` u aplikaciji.
- `trip.camera` se postavlja na svaki tick. Tick bez `frame` ga briše, da crveni alarm modela ne
  ostane zaglavljen.
- Kategorija modela koja nije u `CATEGORY_TO_BEHAVIOR` ide aplikaciji, ali se ne boduje, i jednom
  se loguje warning u konzoli servera.
- WebSocket se ne vidi u OpenAPI-ju ni na `/docs`, pa se dokumentuje ručno u `docs/API.md`.
- Testovi: fixture u `tests/test_api.py` menja `get_trip_repository` i `get_live_hub` svežim instancama.
  Koristi `with TestClient(app)`, da HTTP i WebSocket dele isti event loop.
- Windows Firewall blokira konekcije sa hotspota ako Python nije dozvoljen i na **Public** mrežama.
  Komanda za to je u `README.md`.
