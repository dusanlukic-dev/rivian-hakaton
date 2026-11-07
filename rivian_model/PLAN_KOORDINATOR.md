# Plan: uklapanje modela u arhitekturu sa koordinatorom

**Status (6. 11. 2026):** u kodu **ništa nije menjano**. Čeka se novi backend (koordinator + server) koji se pravi na drugom laptopu.
Kad stigne: prvo proveriti backend po sekciji 5, pa tek onda raditi korake iz sekcije 6.
Ovaj plan zamenjuje ugovor v1 iz `ARHITEKTURA.md` (vozilo → backend JSON preko `pipeline.py --send`).

---

## 1. Nova arhitektura (dogovor CV kolege i backend kolege)

```
 U AUTU
 kamera ─► KOORDINATOR (backend, deo 1) ── frejmovi ──► MODEL (Docker, bez prozora, radi stalno)
              │  keš poslednjih X s                        │
              │◄────────── vrednosti po frejmu ────────────┘
              │  + spoljni podaci (brzina, ekran telefona, ...)
              ├─► konačni skor (stream) ─► telefon   (kasnije i displej u autu, lampice)
              └─► rizičan segment: jedna slika ili video ─► SERVER (backend, deo 2, VAN auta): baza + API
```

- **Model** samo gleda frejmove i vraća vrednosti po frejmu. Ne računa skor.
- **Koordinator** spaja vrednosti modela sa spoljnim podacima, računa konačni skor i šalje ga telefonu. Sam prepoznaje rizične segmente i šalje sliku ili video serveru.
- **Server** (van auta) čuva slike, video i statistiku i daje ih preko API-ja.

---

## 2. Šta iz postojećeg koda ide gde

| Deo | Fajl sada | Ide u |
|---|---|---|
| Modeli (poza, telefon, lice), ONNX podešavanja, zagrevanje | `pipeline.py` (`Models`, `run_pose`, `run_phone`, `run_face`) | **MODEL kontejner** |
| Pravila po frejmu → verovatnoće `phone`, `look_away`, `drowsy`, `collapse` | `features.py` (`DriverLogic`) | **MODEL kontejner** (CV logika; pamti kalibraciju po vožnji) |
| Skor, događaji, alarmi, „kolaps → skor 0“ | `scoring.py` (`DriverScorer`) | **KOORDINATOR** (čist Python, može se samo uvesti) |
| Najkritičniji frejm, snimak rizičnog segmenta | `pipeline.py` | **KOORDINATOR** (on ima frejmove i keš) |
| Slanje vozilo → backend (`sender.py`, `--send`, ugovor v1) | `pipeline.py`, `sender.py` | ne treba; ostaje samo kao alat za testiranje |
| `replay.py`, `mock_backend.py` | | šablon za test alate novog ugovora |

---

## 3. Predlog ugovora koordinator ↔ model (za dogovor sa backend kolegom)

**Veza:** WebSocket u istom `docker-compose`, npr. `ws://model:8100/stream`. Jedna veza po kameri/vožnji.

**Koordinator → model:**

| Poruka | Sadržaj |
|---|---|
| `stream_start` | `{"stream_id": "<trip_id>", "camera": "08_14", "fps": 10}`. Model pravi novo stanje za vožnju (kalibracija kreće ispočetka). |
| `frame` | JSON zaglavlje `{"stream_id", "frame_id", "t"}` + JPEG (binarno). `t` = **vreme snimanja** u sekundama od početka vožnje, ne vreme obrade. **10 frejmova u sekundi**, ne 30. |
| `stream_end` | `{"stream_id"}`. Model briše stanje vožnje. |

**Model → koordinator** (za svaki obrađen frejm):

```json
{"stream_id": "08_14_62_092916-20261106T180000Z", "frame_id": 594, "t": 19.8,
 "probs": {"phone": 1.0, "look_away": 0.0, "drowsy": 0.0, "collapse": 0.0},
 "calibrated": true,
 "details": {"phone_box": [933, 801, 1100, 981], "head_yaw": 31.6, "head_pitch": 14.4, "eyes_closed": 0.21},
 "latency_ms": 66}
```

- `probs` su iste vrednosti koje danas ulaze u `scoring.py`, pa koordinator može odmah da ih koristi sa `DriverScorer`.
- `calibrated: false` prvih ~3 s vožnje: `look_away` i `drowsy` tada još ne važe. Frontend ne treba da crta tu nulu kao „sve u redu“.
- `details` je opciono (za objašnjenje alarma ili okvir na slici). Koordinator može da ga ignoriše.
- Ako model ne stigne, **preskače zastarele frejmove** i uzima najnoviji. Tako `--realtime` već radi. Odgovor uvek nosi `t` frejma, pa koordinator zna na šta se odnosi.

---

## 4. Zamerke i pitanja (pushback), po važnosti

1. **Koordinator mora biti u autu, ne na serveru.** Inače alarm zavisi od mreže (u tunelu nema alarma, ni hitnog za kolaps), a video izlazi iz auta (privatnost, ~10 Mbit/s po autu). Iz opisa deluje da je u autu (keš, displej, lampice). **Potvrditi.**
2. **Model nije bez stanja.** Vrednosti po frejmu zavise od kratke istorije iste vožnje:
   - kalibracija pogleda (prve ~3 s, osvežava se do 60 s unazad);
   - „telefon viđen u poslednje 3 s“ (potvrda poze);
   - poza kucanja ≥ 4 s;
   - pokreti u poslednjoj sekundi (kolaps).

   Zato koordinator mora da šalje `stream_id` i `stream_start` / `stream_end`, a model drži jedno stanje po vožnji.
3. **Vreme i broj frejmova.** Koordinator šalje vreme snimanja frejma, jer pravila rade po vremenu, ne po broju frejmova. Model obrađuje 10 u sekundi (svaki 3. frejm), pa nema svrhe slati 30. Model ne sme da gomila red frejmova: zakasneo alarm ne vredi.
4. **Prenos frejmova košta vreme.** Pun frejm 1920×1536 kao JPEG ima **285 KB**, a kodiranje + dekodiranje traju **~22 ms**. Uz ~65–80 ms modela to je ~90–100 ms, na samoj granici. Predlog: koordinator šalje **samo isečak vozača** (zona iz `rois.json`, ~37% piksela) ili koristi deljenu memoriju umesto JPEG-a.
5. **Keš i snimak rizičnog segmenta.** Koordinator za rizik saznaje tek ~2–3 s posle početka (EMA + minimalno trajanje 1.5–2 s). Keš mora da drži bar **~10 s unazad**, da snimak obuhvati i početak. Najbolja slika je vrh događaja (`peak_t` iz `scoring.py`), a on se zna tek kad se događaj završi. Za kolaps poslati sliku odmah, ne čekati kraj.
6. **Spoljni podaci (brzina, ekran telefona) ne postoje u datasetu.** U demou će biti simulirani, i na pitchu to treba reći. Dogovoriti kako ulaze u skor, npr. brzina 0 → nema kazne, ili ekran upaljen + glava dole → jači dokaz za telefon.
7. **Skor sada pravi koordinator.** Sva pravila skora iz `scoring.py` treba preneti ili uvesti: EMA, histereza, minimalno trajanje, kazna samo za najgoru kategoriju, i **kolaps → skor 0 odmah**.
8. **Docker modela.** Bez prozora radi već danas (`pipeline.py` nema GUI). Ali Ultralytics učitava ceo PyTorch: veliki image i ~170 MB RAM samo za učitavanje.
   - Prva verzija može tako.
   - Kasnije zameniti čistim ONNX Runtime-om (manji image, manje RAM-a, bolje za kriterijum „embedded”).
   - Brzinu treba **ponovo izmeriti u Docker-u** (WSL2), na struji.
9. **Zone vozača po kameri** (`rois.json`) model drži u svojoj konfiguraciji. Koordinator samo šalje `camera` (`08_14` / `05_23`).

---

## 5. Kad stigne novi backend: provera PRE povezivanja modela

- [ ] **Šta šalje modelu:** format frejma (JPEG / sirovo / ceo frejm / isečak), fps, da li šalje **vreme snimanja**, `stream_id`, kameru, kojim kanalom i na koji port.
- [ ] **Šta očekuje nazad:** imena polja i kategorija, opseg 0–1, koliko često, i **šta radi kad odgovor ne stigne ili kasni**. Ne sme da zamrzne skor ka telefonu niti da beskonačno gomila red.
- [ ] **Skor ka telefonu:** format i učestalost. Da li hitan alarm (kolaps) ide odmah i obara skor na 0. Da li postoji histereza (nema treperenja alarma).
- [ ] **Keš:** koliko sekundi drži i da li snimak hvata početak segmenta. Šta i kada šalje serveru (slika ili video). Ne sme da puni memoriju bez ograničenja.
- [ ] **Tipični bagovi:**
  - poziv modela koji blokira glavnu petlju;
  - nema ponovnog povezivanja kad model padne ili se restartuje;
  - vreme po satu računara umesto vremena snimanja;
  - pogrešni portovi ili imena servisa u `docker-compose`;
  - CORS ka frontendu;
  - isti `trip_id` za dve vožnje.
- [ ] Pre pravog modela pustiti lažni model (vraća snimljene `probs` iz `out_pipeline/*/live.jsonl`) i proveriti da skor ispadne isti kao kod nas: **092916 → 39, 084339 → 29, 085956 → 100, 031246 → 0 + hitan alarm**.

---

## 6. Šta radimo posle (redosled)

1. **`model_service.py`:** servis bez prozora koji prima frejmove po dogovorenom ugovoru. Koristi postojeće `Models` + `DriverLogic` (jedno stanje po `stream_id`), zagreva se pri pokretanju, preskače zastarele frejmove, vraća `probs` + `calibrated` + `details`. Ima i `/health` za Docker.
2. **`Dockerfile` + `requirements`:** Python 3.12-slim, `opencv-python-headless`, `onnxruntime`, `mediapipe`, `ultralytics`, plus modeli (`*.onnx`, `face_landmarker.task`) i `rois.json`. Izmeriti brzinu u kontejneru.
3. **Lažni koordinator za test:** šalje klip iz dataseta kao frejmove (10 fps, vreme snimanja), prima `probs`, računa skor sa `scoring.py`. Tako proveravamo ceo put pre pravog backenda.
4. **Povezivanje sa pravim koordinatorom** i test na 4 klipa: skorovi moraju biti isti kao gore.
5. **Dokumentacija:** ažurirati `ARHITEKTURA.md` (ugovor v1 je zastareo) i `ATRIBUTI.md`.

Procena: koraci 1–3 su par sati; korak 4 zavisi od stanja novog backenda.

---

## 7. Šta važi od dosadašnjeg rada

- Ostaje: `features.py`, `scoring.py` (sa ispravkom za kolaps), modeli, ONNX podešavanja, zagrevanje, brzina ~65–80 ms po frejmu na struji.
- Ostaje za testove: `replay.py`, `mock_backend.py`, `primer_poruka.jsonl` (format v1).
- Zamenjeno ovim planom: ugovor v1 iz `ARHITEKTURA.md` (vozilo šalje skor, alarme i događaje backendu).

---

## 8. Nalazi provere novog backenda (6. 11. 2026, `rivian-hakaton` origin/main, commit 7c19601)

Repo: `C:\Users\PC\rivian-hakaton` (github.com/dusanlukic-dev/rivian-hakaton).
- Urađen je samo `git fetch`; lokalni folder **nije** ažuriran, a kod je čitan direktno iz `origin/main`.
- Fetch zbog AVG antivirusa radi samo ovako: `git -c http.sslBackend=schannel fetch`.

**Šta koordinator šalje modelu** (`WS /api/v1/model/ws`; model se sam javlja koordinatoru):
- model → koordinator: `hello {worker, version, categories}`;
- koordinator → model: binarno, `uint32 LE dužina zaglavlja` + JSON `{"type": "frame", "id", "t", "trip_id"}` + JPEG. Kamera (`tools/camera_stream.py`) šalje 1280 px širine, 10 fps;
- koordinator → model: `reset {trip_id}` (nova vožnja) i `idle` (kraj vožnje).

**Šta očekuje nazad:**
- `detection {id, t, trip_id, evidence: {kategorija: p 0–1}, perception, ms}`, ili `error {id, message}`;
- jedan frejm u letu, najnoviji pobeđuje, 5 s do odustajanja.

**Šta koordinator radi sa tim:** `RiskEngine` CV tima (EMA, histereza, trajanje, grupe, pravila, alarm) → njihov `scoring.py` 0–100 (težina × sekunde × brzina × noć) → reakcija kola. Na svake 2 s pravi sekciju sa slikom i šalje je serveru.

**Naše zamerke iz sekcije 4:**

| # | Zamerka | Stanje |
|---|---|---|
| 1 | koordinator u autu | ✔ |
| 2 | stanje po vožnji | ✔ (`reset`, `idle`) |
| 3 | vreme i broj frejmova | ✔ (`t`, najnoviji frejm pobeđuje); ali `t` je vreme **dolaska** frejma, ne snimanja |
| 4 | veličina frejma | ✔ (1280 px JPEG) |
| 5 | keš | ✔ (5 min) |
| 6 | spoljni podaci | ✔ (brzina je mock) |
| 7 | kolaps | ✘ **ne postoji** |
| 8 | Docker | delimično: `model/Dockerfile` postoji, ali nije testiran |
| 9 | zone vozača | kod njih su u razlomcima okvira |

**Bagovi i rizici pre povezivanja modela:**
1. **`collapse` ne postoji nigde** (`risk_config.json`, enum `Behavior`, `CATEGORY_TO_BEHAVIOR`). Koordinator koristi samo kategorije iz `risk_config.json`, ostale tiho ignoriše. Pad vozača (031246, 022338) zato ne bi dao hitan alarm.
2. `notebooks/setup_models.bat` ima **nerazrešene merge konflikte**, pa pravi model CV tima ne može da se podesi na Windows-u. Verzija `.sh` je ispravna.
3. `model/requirements.txt` ima i `opencv-python-headless` i `mediapipe`, a `mediapipe` vuče `opencv-contrib-python`. Dve OpenCV distribucije u istom okruženju mogu da pokvare `import cv2`.
4. `model/Dockerfile` nije testiran i traži `notebooks/models/`, koji je u `.gitignore`. U čistom klonu build pada dok se modeli ne skinu.
5. `t` je vreme dolaska frejma u koordinator. Za demo je to u redu, ali neravnomerni frejmovi kvare trajanja.
6. Kamera šalje 1280 px širine, a naše zone (`rois.json`) su u pikselima 1920×1536. Naš detektor mora da ih skalira.
7. Aktivan je samo jedan worker u isto vreme, pa se dva modela mogu porediti samo jedan za drugim.

**Kako se naš model uklapa (bez promene protokola):** kao treća klasa detektora u `model/worker.py`, pored `CvDetector` i `FakeDetector`, sa `reset()` i `detect(jpeg, t) → evidence`.

Mapiranje kategorija:

| Naše | Njihovo |
|---|---|
| `phone` | `phone_use` |
| `look_away` | `eyes_off_road` |
| `drowsy` | `eyes_closed` |
| `collapse` | nova kategorija `collapse` |

Za `collapse` treba dodati unos u `risk_config.json`, mapiranje u `CATEGORY_TO_BEHAVIOR` (i enum) i hitan alarm.

**Odluka tima:**
- koji model ide u demo: naš, model CV kolege, ili kombinacija po kategoriji;
- da li se dodaje `collapse`.

### 8.1 Naš detektor za njihov protokol: `rivian_detector.py` (urađeno 6. 11., njihov repo nije diran)

- Klasa `RivianDetector` ima isti oblik kao `CvDetector` u njihovom `model/worker.py`: `reset()` i `detect(jpeg, t)`, koji vraća dokaze `phone_use`, `eyes_off_road`, `eyes_closed`, `collapse`.
- Uz klasu ide i veza sa koordinatorom (isti protokol kao njihov worker), pa radi samostalno:
  `python rivian_detector.py --camera 08_14|05_23 --coordinator ws://<IP>:8000/api/v1/model/ws`
- Zone vozača se skaliraju na 1280 px. Zagrevanje ide na `warmup_frame.jpg`.
- Test bez njihovog backenda (lažni koordinator po njihovom protokolu): `python test_rivian_detector.py <klip>`.

| Klip | Kroz detektor | Naš `pipeline.py` |
|---|---|---|
| 092916 | 40 crveno, telefon 12.6–24.2 | 39 crveno |
| 031246 | 0 crveno + hitan alarm, kolaps od 11.0 s | isto |

Na oba klipa je 300/300 frejmova i 0 grešaka. Detektor obradi frejm za ~73 ms (p95 89–95 ms), a ceo krug sa slanjem traje ~85–91 ms.
Za uključenje u njihov repo, klasa ide u `model/worker.py` uz izbor detektora, a `collapse` u `risk_config.json` i u mapiranje kategorija.

### 8.2 Naš model u Docker-u (provereno 6. 11., `Dockerfile` u ovom folderu)

`docker build -t rivian-model .` traje ~5 min prvi put, a posle promena ~10–20 s (PyTorch ostaje u kešu).
Kontejner podrazumevano pokreće `rivian_detector.py` (javlja se koordinatoru preko `COORDINATOR_URL`).

| | Laptop (Windows) | Docker (Linux, WSL2) |
|---|---|---|
| Detektor, 1280 px JPEG preko mreže (pravi put u sistemu) | ~73 ms po frejmu | **~73 ms** (p95 84–87 ms), ceo krug ~90 ms |
| `pipeline.py` na klipu, puna rezolucija | ~62–65 ms | ~75 ms (p95 84, p99 90) |
| Spreman posle pokretanja | ~5.2 s | **~3.4–3.9 s** |
| RAM | ~750 MB | **~480–500 MB** (kontejner sa detektorom) |
| Skor 092916 | 39 / detektor 40 | 39 / detektor 40 (isto) |

- Kontejner se povezuje sa koordinatorom na laptopu preko `host.docker.internal` i sam se ponovo povezuje kad koordinator nije dostupan.
- **Dva problema su nađena i popravljena u našem `Dockerfile`:**
  1. MediaPipe na Linux-u traži `libEGL` čak i bez GPU-a, pa je padao pri pokretanju (`OSError: libEGL.so.1`). Rešenje: `libegl1` + `libgles2`.
  2. Ultralytics je pri učitavanju ONNX modela **sam skidao paket `onnx` sa interneta u toku rada**. U autu bez interneta to bi pokvarilo pokretanje. Rešenje: `onnx` je u image-u, a uključeno je `YOLO_AUTOINSTALL=false` i `YOLO_OFFLINE=true`.
- **Važno za CV i backend kolegu:** njihov `model/Dockerfile` instalira samo `libgl1 libglib2.0-0`, a koristi MediaPipe (lice i ruke). Imaće isti `libEGL` pad: treba dodati `libegl1 libgles2`.
- **Image je 3.07 GB, a naš model i kod su samo 26 MB.** Ostatak su biblioteke koje naš ONNX model zapravo ne koristi:
  - PyTorch ~0.9 GB (traži ga Ultralytics);
  - Polars 170 MB;
  - dve verzije OpenCV-a.

  Kad se Ultralytics zameni čistim ONNX Runtime-om, image bi pao na ~1 GB, a RAM bi bio još manji. To nije urađeno.
