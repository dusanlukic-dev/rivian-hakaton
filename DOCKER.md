# Pokretanje u Docker-u

Ceo sistem se pokreće **jednom skriptom**, iz korena repoa (PowerShell):

```powershell
.\start.ps1
```

Skripta sama radi sve redom:
1. instalira Docker Desktop ako ga nema (winget), pa ga pokrene i sačeka;
2. ugasi ostatke `demo.ps1` i proveri portove 8000, 8001 i 5173;
3. nađe dataset sa klipovima (`*_video_inCabin.mp4`) i upiše podešavanja u `docker/.env` (IP laptopa, klipovi, zona vozača);
4. izgradi i pokrene kontejnere i sačeka da se svi jave;
5. na samom laptopu pokrene ono što ne može u Docker: **Bluetooth gateway** (svoj venv, Python instalira ako ga nema) i
   **adb reverse** za telefon preko USB-a;
6. ispiše adrese i otvori dashboard.

Prvo pokretanje traje ~10 minuta (model ima ~3 GB, težine se prave pri izgradnji). Posle toga oko minut.

## Šta radi gde

| Compose | Kontejneri | Port na laptopu |
|---|---|---|
| `docker/car.yml` (auto) | `coordinator`, `model` (CPU), `camera` (klipovi iz dataseta) | 8000 |
| `docker/server.yml` (server) | `server`, `postgres`, `rustfs` (baza i slike samo unutar Docker-a) | 8001 |
| `docker/dashboard.yml` (ekran u kolima) | `dashboard` (nginx: build + proxy ka `/api`) | 5173 |
| `docker-compose.yml` (sve) | uključuje sva tri | |

Bluetooth gateway i adb reverse rade na laptopu, svaki u svom prozoru `rivian: ...`.

## Telefon

- **Bluetooth** (podrazumevano u aplikaciji): Settings → Car connection → "Rivian demo car".
- **Server** u aplikaciji: `http://<IP laptopa>:8001/api/v1` preko hotspota, ili `localhost:8001` preko USB-a.
- **Wi-Fi veza sa autom** (umesto Bluetooth-a): `<IP laptopa>:8000`.
- Svaka nova vožnja iz aplikacije dobija sledeći klip (podrazumevano kolaps, pa telefon, pa telefon u krilu; klipovi
  kojih nema u datasetu se zamene drugim iz iste serije).

## Česte komande

```powershell
.\start.ps1 -Status                     # šta radi (kontejneri, kamera, model, server)
.\start.ps1 -Logs                       # logovi svih (Ctrl+C izlaz); jedan deo: -Logs -Service model
.\start.ps1 -Stop                       # ugasi sve, podaci ostaju
.\start.ps1 -Reset                      # ugasi sve i obriši bazu i slike (posle promene tabela)
.\start.ps1 -Dataset "D:\Hackathon dataset 2026"                         # gde su klipovi (zapamti se)
.\start.ps1 -Clips 05_23_62_031246 05_23_62_022338                       # svoji klipovi po vožnji
.\start.ps1 -CameraMode loop -Video 05_23_62_031246_video_inCabin.mp4    # jedan klip u petlji
.\start.ps1 -CameraMode test            # bez dataseta: test slika
.\start.ps1 -Speed city -NoBle -NoAdb   # brzina; bez Bluetooth-a; bez USB-a
```

Posle izmene koda samo ponovo `.\start.ps1`: izgradi se samo ono što se promenilo.

## Dobro je znati

- Model u Docker-u radi na **CPU-u** (~10 fps, stiže svaki frejm). DirectML (GPU) postoji samo nativno: `demo.ps1`.
- Web kamera ne radi u Docker-u na Windows-u: kamera pušta klipove iz dataseta.
- Baza: `docker compose exec postgres psql -U safety` (iz korena repoa).
- Jedan deo sam: `docker compose -f docker/server.yml up -d` (podešavanja za takav rad su u `docker/.env.example`).
- `demo.ps1` (sve nativno, bez Docker-a) i dalje radi; ne pokreći ga zajedno sa `start.ps1` (isti portovi).
