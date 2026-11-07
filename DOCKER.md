# Pokretanje

Sistem ima tri dela. **Automobil** je u našem slučaju laptop: na njemu rade kamera (pušta snimke iz dataseta), model koji
na svakom frejmu prepoznaje ometanje i **koordinator** koji od toga računa ocenu pažnje i odlučuje kako kola reaguju.
**Server** je „van kola“: čuva naloge, vožnje i slike i pravi izveštaj posle vožnje. Treći deo su ekrani: **aplikacija
na telefonu** vozača i **dashboard**, web prikaz ekrana u kolima. Svaki deo radi u svom Docker kontejneru, a sve se
pokreće jednom skriptom.

| Deo | Kontejneri | Port na laptopu |
|---|---|---|
| automobil (`docker/car.yml`) | koordinator, model, kamera | 8000 |
| server (`docker/server.yml`) | server, Postgres, RustFS (slike) | 8001 |
| dashboard (`docker/dashboard.yml`) | nginx sa web aplikacijom | 5173 |

Telefon sa kolima razgovara preko koordinatora (WebSocket `/api/v1/ws` za stanje uživo, REST za početak i kraj vožnje),
a sa serverom preko REST-a (`/api/v1/auth`, `/api/v1/trips`, izveštaj). Baza i skladište slika vidljivi su samo unutar
Docker-a.

## Pokretanje sistema

Iz korena repoa, u PowerShell-u:

```powershell
.\start.ps1
```

Skripta instalira i pokrene Docker Desktop ako ga nema, nađe dataset sa klipovima, upiše podešavanja u `docker/.env`,
izgradi i pokrene kontejnere i sačeka da se svi jave. Na samom laptopu zatim otvori dva prozora za ono što ne može u
Docker: **Bluetooth gateway** (veza telefona sa kolima preko Bluetooth-a) i **adb reverse** (telefon na USB kablu). Na
kraju ispiše adrese i otvori dashboard. Prvo pokretanje traje ~10 minuta jer se gradi model od ~3 GB, a svako sledeće
oko minut.

```powershell
.\start.ps1 -Status       # šta radi
.\start.ps1 -Logs         # logovi (-Service model za jedan deo)
.\start.ps1 -Stop         # ugasi sve, podaci ostaju
.\start.ps1 -Reset        # ugasi sve i obriši bazu
.\start.ps1 -Dataset "D:\Hackathon dataset 2026"   # gde su klipovi, ako ih skripta ne nađe sama
```

## Aplikacija na telefonu

Aplikacija se ne pravi u Docker-u, nego se gradi kao Android APK iz `frontend/mobile` (treba Node, JDK 17 i Android SDK).
Za demo je najbolji **release APK**, koji nosi ceo kod u sebi: `npm run android:release` ga izgradi i instalira na
telefon povezan kablom. Ako izgradnja na Windows-u padne zbog predugačkih putanja, recept je u `README.md`
(„Release APK without Android Studio“). Gotov APK se može instalirati i preko `adb install <apk>`.

U aplikaciji se pri prvom otvaranju upisuje **adresa servera** (zupčanik na ekranu za prijavu), pa se pravi nalog:

- preko hotspota ili Wi-Fi-ja: `<IP laptopa>:8001` (IP ispiše `start.ps1`);
- preko USB kabla: `localhost:8001`.

Vezu sa kolima biraš posle prijave, u Settings → Car connection: Bluetooth („Rivian demo car“) ili Wi-Fi na
`<IP laptopa>:8000`. Svaka vožnja pokrenuta sa telefona dobija sledeći klip iz dataseta.

Ako telefon ne stiže do servera, otvori `http://<IP laptopa>:8001/api/v1/health` u browseru telefona. Kad se ni to ne
otvori, problem je u mreži ili firewall-u laptopa, a ne u aplikaciji. Model u Docker-u radi na procesoru; varijanta
bez Docker-a (`demo.ps1`) može da koristi grafičku karticu, ali ne pokreći obe istovremeno jer koriste iste portove.
