# Personal Safety Reviewer – backend (FastAPI)

Računa koeficijent bezbednosti vozača (0–100) iz rezultata modela za kameru i uživo javlja mobilnoj
aplikaciji kako kola treba da reaguju (svetlo na dashboardu, vibracija sedišta, zvuk, poruka kontaktu).

## Arhitektura

```
 laptop                                                         telefon (hotspot)
┌─────────────────────────────────────────────────────────┐    ┌──────────────────┐
│ notebooks/  YOLO · MediaPipe · OpenCV                   │    │ React Native app │
│     │  safety_client.send(behaviors, speed_kmh)         │    │                  │
│     ▼  POST 127.0.0.1:8000/api/v1/telemetry  (~1/s)     │    │                  │
│ backend/  FastAPI ── računa score ── WS /api/v1/ws ─────┼───►│ live dashboard   │
│                     ◄── POST /trips, /trips/{id}/end ───┼────│ start / kraj     │
└─────────────────────────────────────────────────────────┘    └──────────────────┘
```

- Modeli i backend rade na **istom laptopu**, pa modeli gađaju `127.0.0.1`.
- Modeli šalju samo **labele** ponašanja (nikad slike). Mapiranje detekcija u labele
  (npr. MediaPipe glava oborena + YOLO "cell phone" → `looking_at_phone`) radi se na strani modela.
- U jednom trenutku je aktivna **jedna vožnja** (jedan auto). Aplikacija je pokreće i završava,
  a telemetrija modela automatski ide u aktivnu vožnju.

## Pokretanje

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python run.py        # za demo preko hotspota, ispisuje adresu za aplikaciju
fastapi dev app/main.py   # samo lokalno, http://127.0.0.1:8000/docs
```

Testovi: `pytest`

### Povezivanje telefona preko hotspota (nema DNS-a)
1. Uključi hotspot na telefonu i poveži laptop na njega.
2. Na laptopu pokreni `python run.py`. Ispisaće nešto ovako:
   ```
   REST       http://192.168.43.57:8000/api/v1
   WebSocket  ws://192.168.43.57:8000/api/v1/ws
   ```
3. Tu IP adresu unesi u aplikaciju. **IP se menja svaki put kad se laptop ponovo poveže na hotspot**,
   pa je ne hardkodujte, nego napravite polje u podešavanjima aplikacije.
4. **Windows Firewall:** pri prvom pokretanju Windows pita da li da pusti Python. Čekiraj i
   **Public** mreže, jer Windows hotspot često vodi kao javnu mrežu. Ako je prozor propušten,
   pokreni PowerShell kao admin:
   ```powershell
   New-NetFirewallRule -DisplayName "Safety API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```
5. Provera sa telefona: otvori `http://<IP>:8000/api/v1/health` u browseru.
6. U Expo Go / dev buildu `http://` i `ws://` rade odmah. Za samostalni Android build treba uključiti
   cleartext saobraćaj (`usesCleartextTraffic` preko `expo-build-properties`).

## Za tim sa modelima ([notebooks/safety_client.py](../notebooks/safety_client.py))

```python
from safety_client import SafetyClient

client = SafetyClient()  # http://127.0.0.1:8000/api/v1
while True:
    frame = ...
    behaviors = set()            # popuni iz YOLO / MediaPipe rezultata
    client.send(behaviors, speed_kmh=60)  # sme svaki frejm, sam se ograniči na ~2/s
```

- `send` ne ruši petlju za kameru ako backend nije podignut ili vožnja još nije počela (vraća `None`).
- Za nepoznatu labelu odmah baca `ValueError`, da se greška u kucanju vidi odmah.
- Simulacija cele vožnje bez modela, korisno za front: `python notebooks/safety_client.py`
  (sa `--interval 0.3` ide brže od realnog vremena).

Labele (moraju se poklapati sa `Behavior` u [app/domain/enums.py](app/domain/enums.py)):

| Labela | Značenje | Težina (poena/s) |
|---|---|---|
| `drowsy` | pospan | 2.5 |
| `looking_at_phone` | gleda u telefon | 2.0 |
| `looking_behind` | gleda iza sebe | 2.0 |
| `turning_around` | okreće se telom (obično ide zajedno sa `looking_behind`, pa se sabiraju) | 1.0 |
| `hands_off_wheel` | ruke van volana | 1.0 |

Više labela u istom ticku je u redu i penali se sabiraju. Novo ponašanje se dodaje na tri mesta:
`Behavior` u `enums.py`, težina u `scoring.py` i savet u `TIPS` u `services/trips.py`.
Test će pasti ako nešto od toga fali.

## Za mobilnu aplikaciju

Ceo ugovor (rute, WebSocket poruke, TypeScript tipovi, primeri, pravila prikaza) je u
**[docs/API.md](../docs/API.md)**. To je jedini izvor istine, pa ga ažuriraj kad menjaš rute ili šeme.

## Kako radi koeficijent

Sve se podešava na jednom mestu:
- [app/services/scoring.py](app/services/scoring.py) (`ScoringConfig`): težine ponašanja, množioci za brzinu i noć, oporavak
- [app/services/alerts.py](app/services/alerts.py) (`LEVEL_BANDS`, `POLICIES`): opsezi i reakcija kola po nivou

Po ticku:
- svako vidljivo ponašanje skida `težina × sekunde` poena, plus jednokratni udar kad počne (pada brzo na početku)
- penal se množi sa: **brzinom** (< 5 km/h = 0, grad 1.0, vangradski 1.3, autoput 1.7), **noć** (22–06h) ×1.5,
  i **krhkošću** `1 + (100 − score)/100` (što je niži, lakše pada)
- posle 30 s čiste vožnje score raste 3 poena u minutu

`timestamp` mora biti u **lokalnom vremenu sa offsetom** (`safety_client` to radi sam), jer sat iz
njega određuje noćne penale.

| Score | Nivo | Svetlo | Reakcija na rizično ponašanje (samo u pokretu) |
|---|---|---|---|
| 90–100 | safe | zeleno | – |
| 75–90 | caution | zeleno-žuto | vibracija ako traje ≥ 5 s |
| 55–75 | warning | žuto | vibracija + tihi zvuk, ≥ 5 s |
| 35–55 | high_risk | žuto | vibracija + glasan zvuk, ≥ 2 s |
| 10–35 | critical | crveno | vibracija + glasan zvuk odmah |
| < 10 | emergency | crveno | + `emergency` događaj i poruka kontaktu (jednom po vožnji) |

Slanje poruke kontaktu je za sada stub koji samo loguje: [app/services/notifications.py](app/services/notifications.py).

## Struktura

```
backend/
  run.py               pokretanje za hotspot (0.0.0.0 + ispis IP adrese)
  app/
    main.py            FastAPI app, CORS, router
    core/config.py     podešavanja iz .env
    api/routes/        HTTP i WebSocket rute (live.py = telemetrija + /ws)
    schemas/           Pydantic modeli (ugovor sa frontom)
    domain/            enumi i stanje vožnje
    services/          scoring, alerts, trips, live (WebSocket), analytics, notifications
    repositories/      in-memory skladište (gubi se na restart)
  tests/
notebooks/
  safety_client.py     most između modela i backenda, plus simulacija vožnje
```
