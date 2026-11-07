# Video sim: snimak umesto kamere (dizajn)

Datum: 2026-11-07 · Status: dizajn odobren u chatu, čeka pregled ovog speca

## Cilj

Sajt `frontend/video-sim/` na koji dodaš snimljen in-cabin klip (oko 30 s), a on ga pošalje backendu kao da je
kamera. Koristi se za:

- testiranje modela na snimcima,
- demo na pitchu, kad nema prave kamere,
- testiranje telefona i dashboarda sa pravim tokom (kamera → model → score), umesto ručnih labela iz Simulator panela.

**Uspeh:** izabereš klip i klikneš **Send**. Dok klip traje, `GET /api/v1/coordinator/status` pokazuje `camera.fps`
oko 10, `model.frames_sent` raste (kad je model worker povezan), a telefon i dashboard reaguju. Slanje traje koliko
i klip.

## Odluke

| Pitanje | Odluka |
|---|---|
| Mesto | nova zasebna app `frontend/video-sim/`: Vite + React 19 + TypeScript + Tailwind v4, kao dashboard |
| Put do backenda | postojeći `WS /api/v1/camera/ws`. Backend se ne menja |
| Klipovi | jedan fajl odjednom, uvek sa diska. Ništa se ne pamti, nema ugrađenih klipova |
| Vožnja | sajt je pokreće samo ako nijedna nije aktivna |
| Prikaz | ništa sa backenda: sajt ne sluša `/ws` i ne prikazuje score. Samo svoj napredak i greške |
| Kraj klipa | slanje stane i WS se zatvori, a vožnja ostaje (završava je telefon ili dashboard) |
| Tekst u UI-ju | engleski, kao dashboard i telefon (`mobile/src/config/strings.ts`: svi stringovi su na engleskom) |

## Šta backend (`main`) očekuje

Izvori: `backend/app/coordinator/routes/live.py`, `routes/trips.py`, `services/coordinator.py`,
`services/model_link.py`, `services/trips.py`, `core/config.py`.

- Jedna binarna WS poruka je jedan JPEG (počinje sa `FF D8 FF`), najviše 2 000 000 bajtova. Sve ostalo se tiho odbacuje.
- Bez aktivne vožnje frejmovi se tiho odbacuju, a WS ostaje otvoren.
- Koordinator meri vreme po dolasku frejma: sat modela, trajanje ponašanja, sekcije od 2 s. Zato se šalje u realnom
  vremenu, pa 30 s klip traje 30 s.
- Model dobija jedan frejm u letu i najnoviji pobeđuje. Brže slanje ne bi pomoglo, model bi samo preskakao frejmove.
- Video keš čuva najviše 10 frejmova/s (`VIDEO_CACHE_FPS`), pa sajt šalje 10/s.
- `POST /api/v1/trips` završava vožnju koja je u toku. Zato ga sajt zove samo kad `GET /api/v1/coordinator/status`
  vrati `trip_id: null`. Bez prijave traži `driver_id`.
- Score se menja samo dok je povezan model worker. Bez njega frejmovi samo pune video keš (slike opasnih momenata).
- Ispod 5 km/h nema opasnosti, a mock brzina `random` ume da stane baš dok ide klip. Za testove i demo:
  `SPEED_SCENARIO=cruise` u `backend/.env` (50–62 km/h, nikad ne staje).
- Kad klip stane, backend više ne dobija detekcije, pa telefon i dashboard ostaju na poslednjem stanju.

## Arhitektura

```
fajl ──► extractFrames (glavna nit, odmah posle izbora fajla)
           <video> van DOM-a + canvas: seek na i/10 s, JPEG 80 %, najviše 1280 px širine
           → ArrayBuffer[]  (30 s = 300 frejmova, oko 50 MB)
Send ──► ensureTrip: GET /coordinator/status → trip_id null? → POST /trips {driver_id: "video-sim"}
     ──► sender.worker: WS /api/v1/camera/ws, frejm i u trenutku t0 + i × 100 ms
           buđenje zakasni → šalje najnoviji frejm, prethodne preskače
           bufferedAmount > 1 MB → preskače frejm
     ──► pregled: isti klip se pušta bez zvuka, samo da se vidi šta ide
```

**Zašto frejmovi unapred i Web Worker:** kad tab nije vidljiv (npr. na bini prebaciš na dashboard), browser na glavnoj
niti uspori tajmere na 1/s i prestane da crta video. Tajmeri i WebSocket u workeru rade normalno. Izvlačenje frejmova
ide dok je tab vidljiv, odmah posle izbora fajla, pa Send kreće bez čekanja.

### Delovi

| Fajl | Šta radi | Zavisi od |
|---|---|---|
| `src/config.ts` | konstante: `FPS = 10`, `MAX_WIDTH = 1280`, `JPEG_QUALITY = 0.8`, `FALLBACK_QUALITY = 0.5`, `MAX_DURATION_S = 120`, `MAX_FRAME_BYTES = 2_000_000`, `MAX_BUFFERED_BYTES = 1_000_000`, `DRIVER_ID = 'video-sim'` | – |
| `src/lib/frames.ts` | čiste `frameTimes(duration, fps)` i `fitSize(w, h, maxWidth)`, plus `extractFrames(file, onProgress, signal)`. Frejm veći od 2 MB se ponovo kodira sa `FALLBACK_QUALITY` | DOM (`<video>`, canvas) |
| `src/lib/backend.ts` | `apiBase()`, `cameraSocketUrl()`, `getStatus()`, `startTrip()`, `ensureTrip(api)` | `fetch` |
| `src/lib/schedule.ts` | `startSchedule({ count, fps, onFrame, onDone, clock })` vraća `stop()`. Realno vreme, preskače zakasnele frejmove | sat (ubrizgan) |
| `src/lib/senderCore.ts` | WS + raspored + preskakanje po `bufferedAmount`. Javlja `progress`, `done`, `error` | `WebSocket` (ubrizgan), `schedule.ts` |
| `src/lib/sender.worker.ts` | tanak omotač: poruke `start` i `stop` prosleđuje `senderCore` | `senderCore.ts` |
| `src/useVideoSim.ts` | stanje stranice i tok: fajl → priprema → spremno → slanje | `lib/*` |
| `src/App.tsx` | jedna stranica, samo prikaz | `useVideoSim.ts` |

Poruke između glavne niti i workera:

- ka workeru: `{ type: 'start', url, frames, fps }`, `{ type: 'stop' }`
- od workera: `{ type: 'progress', index, sent, skipped }` (najviše oko 4/s), `{ type: 'done', sent, skipped }`,
  `{ type: 'error', message }`

**Adresa backenda, kao u dashboardu:** u `npm run dev` sve ide na isti origin (`/api` i WS kroz Vite proxy sa
`ws: true` na `VITE_API_URL`, podrazumevano `http://localhost:8000`). Build ide direktno na `VITE_API_URL` (backend ima
CORS `*`). Port 5174, jer je dashboard na 5173.

## Stranica

Stanja: `empty → preparing → ready → starting → sending → ready`, uz red za grešku.

- **empty:** polje „Drop a video here or click to choose“ (`accept="video/*"`).
- **preparing:** ime fajla i „Preparing frames 120 / 300“.
- **ready:** pregled prvog frejma, „300 frames · 30.0 s · 1280×720“, dugmad **Send** i **Choose another**.
- **starting:** „Checking trip…“ dok traje `ensureTrip`.
- **sending:** pregled se pušta, traka „12.3 / 30.0 s“, dugme **Stop** i red „Started trip video-sim“ ili
  „Sending into the active trip“.
- Posle kraja ili Stop: nazad na **ready** sa redom „Sent 300 frames, 0 skipped“. **Send** šalje isti klip ispočetka.
- Novi fajl usred slanja prvo zaustavi slanje.
- Izgled: font IBM Plex Sans i boje iz `frontend/dashboard/src/index.css`, tamna tema po sistemu
  (`prefers-color-scheme`).

## Greške

| Slučaj | Šta korisnik vidi | Stanje posle |
|---|---|---|
| fajl nije video | „That file is not a video.“ | empty |
| browser ne ume da dekodira (npr. HEVC `.mov` sa iPhona) | „This browser can't decode the video. Export it as MP4 (H.264).“ | empty |
| klip duži od 2 min | „The clip is longer than 2 minutes. Trim it first.“ | empty |
| frejm i sa `FALLBACK_QUALITY` veći od 2 MB | „A frame is still larger than 2 MB. Use a smaller video.“ | empty |
| `GET /coordinator/status` ne uspe | „Backend not reachable at <adresa>. Start it with `python run.py`.“ | ready |
| `POST /trips` ne uspe | „Couldn't start a trip: <detail>“ | ready |
| WS se ne otvori ili se zatvori pre kraja | „Lost the connection to the backend after 12.3 s.“ | ready |

## Testiranje

- **Vitest** (Node, bez browsera):
  - `frameTimes`, `fitSize`;
  - `ensureTrip` sa lažnim `fetch`: vožnja postoji → nema POST-a; nema je → POST sa `driver_id: "video-sim"`;
    mreža pada → poruka o nedostupnom backendu;
  - `startSchedule` sa lažnim satom: 10 fps → frejmovi u 0, 100, 200… ms i kraj u `count × 100` ms; zakašnjenje →
    skok na najnoviji frejm; `stop()` prekida;
  - `senderCore` sa lažnim WebSocket-om: šalje `ArrayBuffer` binarno; visok `bufferedAmount` → preskok;
    zatvaranje pre kraja → `error`.
- `npm run build` i `npm run lint`.
- Ručno, na laptopu sa backendom: `python run.py`, `python ..\model\worker.py --fake`, `npm run dev` u
  `frontend/video-sim`, pošalji klip. `curl http://127.0.0.1:8000/api/v1/coordinator/status` treba da pokaže
  `camera.fps` oko 10 i da `model.frames_sent` raste, a dashboard i telefon reaguju.
- `extractFrames` traži pravi browser, pa se proverava ručno: klip od 30 s daje 300 frejmova.

## Dokumentacija

- `frontend/video-sim/README.md`: pokretanje, kako radi i provera pred demo (backend, model worker,
  `SPEED_SCENARIO=cruise`, vožnju prvo pokreni sa telefona, pa pošalji klip).
- `frontend/video-sim/CLAUDE.md`: kratko, kao u ostalim app-ovima (komande, mapa fajlova, zamke).
- Root `docs/ARCHITECTURE.md` i `CLAUDE.md` nisu povezani sa ovom sesijom. Tamo treba dodati jedan red o novom
  klijentu kamere.

## Van obima

Izmene backenda, upload fajla na server, više klipova ili red, pamćenje klipova, prikaz score-a ili poruka sa `/ws`,
podešavanje fps-a i kvaliteta iz UI-ja, automatski kraj vožnje, puštanje ukrug.

## Izmena 2026-11-07 (posle): jedan klip = jedna vožnja

Zahtev korisnika: kad krene nova vožnja, odnosno novi klip, score mora da krene od 100. Koordinator već pravi svaku
vožnju od nule (score, `RiskEngine`, `reset` modelu), ali je sajt slao drugi klip u istu vožnju, pa je score nastavljao
od poslednjeg stanja (npr. 16.4 posle klipa sa telefonom). Ovim se menjaju odluke "Vožnja" i "Prikaz" iz tabele iznad:

| Pitanje | Nova odluka |
|---|---|
| Vožnja | klip ide samo u vožnju koja još nije dobila frejmove. Send: neiskorišćena vožnja u toku, inače `POST /trips` (`video-sim`) |
| Vožnja sa telefona | sajt sluša `WS /api/v1/ws` samo za `trip_started` / `trip_ended` / `state` sa `speed_source`. Nova vožnja sa telefona odmah dobija učitani klip od početka, pa ostaje na nalogu (History, izveštaj) |
| Kraj vožnje | `trip_ended` vožnje u koju se šalje zaustavlja slanje |
| Iskorišćena vožnja | ona u koju je sajt slao, ili za koju je video `state` sa `speed_source` (null pre prvog ticka, API.md §4): tako se prepozna i vožnja koju je hranila druga kamera ili stranica pre osvežavanja |
| Kamera zauzeta | koordinator prima jednu kameru; soket odbijen pre otvaranja se ponavlja (6 × 400 ms), jer stara kamera ume još da se računa odmah posle zaustavljanja |

Provereno na Xiaomiju (2026-11-07): Send u već bodovanu vožnju je napravio novu (100 → 27.9 `critical` na klipu sa
telefonom), a Start trip na telefonu je sam pokrenuo klip u vožnji naloga (100 → 18.2 `critical`, "Looking at phone").
