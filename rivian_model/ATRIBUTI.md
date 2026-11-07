# Pažnja vozača — signali, formati i ograničenja

Sistem gleda kameru u kabini (fisheye 180°, 1920×1536, 30 fps), obrađuje svaki 3. frejm (10 fps)
i daje skor pažnje 0–100, događaje sa vremenom, live alarme, najkritičniji frejm i video sa okvirima.

```
klip ─► isečak vozača (rois.json) ─┬─► yolo11n-pose (384 px) ─► 17 tačaka tela ──┐
                                   ├─► yolo11n (640 px), paralelno, 5 fps ─► telefon ├─► DriverLogic (features.py) ─► scoring.py ─► JSON
                                   └─► MediaPipe Face Landmarker (isečak glave) ────┘
```

Fajlovi:
- `pipeline.py`: video → modeli → `DriverLogic` → `scoring.py` → izlazi.
- `features.py`: **sva pravila na jednom mestu**.
- `scoring.py`: nepromenjen.
- `sim_features.py` i `dump_features.py`: brzo podešavanje pravila bez ponovnog puštanja modela.

Pokretanje:
- `python pipeline.py --all-test`: 4 test klipa, sa videom.
- `python pipeline.py 08_14_62_092916`: jedan klip.
- `python pipeline.py --all --no-video --out out_all`: ceo dataset (56 klipova, ~30 min).
- `python pipeline.py 08_14_62_092916 --realtime --send ws://localhost:8000/ingest`: demo, tempom prave kamere uz slanje backendu (ARHITEKTURA.md, sekcije 5 i 6).

Izlaz po klipu: `<out>/<klip>/result.json`, `live.jsonl`, `critical.jpg`, `annotated.mp4` (osim uz `--no-video`).
**Ne pokreći dva prolaza istovremeno**: otimaju se o procesor, pa izmerena brzina nije tačna.

---

## 1. Tabela signala

Sva rastojanja su u **širinama ramena (sw)**, pa ne zavise od toga koliko je vozač blizu kameri.
Prag i trajanje odnose se na `scoring.py`:
- Signal prvo prolazi kroz EMA (α = 0.3). Događaj **počinje** kad EMA pređe **0.6**, a **završava** se kad padne ispod **0.4** (histereza).
- Događaj se računa samo ako traje bar *min. trajanje*. Crveni alarm na dashboardu pali se posle *alarm posle*.
- Kazna u skoru je `6 bodova/s × težina × EMA`. U svakom trenutku se kažnjava **samo najgora** aktivna kategorija (nema duplog kažnjavanja).
- **Izuzetak: kolaps.** Kad se potvrdi (traje ≥ 2 s), skor odmah pada na **0** (crveno), u istom trenutku kad krene hitan alarm.

| Naziv | Šta meri | Iz kog modela | Prag / min. trajanje / alarm posle | Težina u skoru | Kako radi na test klipovima | Poznati problemi |
|---|---|---|---|---|---|---|
| **phone** (konačni) | Vozač koristi telefon (poziv, kucanje) | max(yolo_phone, pose_call, pose_typing). **Poza mora biti potvrđena YOLO-om** (vidi ispod). | 0.6 → / 1.5 s / 3 s | **1.0** | 092916 (poziv ~12–25 s): **12.5–24.2 s** ✔. 084339 (kucanje ~11–28 s): **12.4–29.9 s** u 3 dela ✔. 085956 (bez telefona): 0 ✔. 031246: 0 ✔ | Telefon u krilu u mraku se ne hvata (010741). Kratko gledanje u telefon (< ~2 s) se ne hvata (023609). Telefon na konzoli koji YOLO ne vidi hvata se kasno ili nikako (090604, 090759). |
| ↳ yolo_phone | Kutija „cell phone” u šaci ili uz glavu | yolo11n (COCO klasa 67), 640 px, conf ≥ 0.15, na svaki 2. frejm (5 fps), u paralelnoj niti | conf/0.30, max 1.0. **Filter:** prihvaćen ako je < 0.8 sw od glave. Inače odbačen ako je kutija u visini ramena ili grudi (< 0.3 sw ispod ramena) ili ako je najbliži zglob podignut iznad ramena. Prihvaćen ako je 0.35–1.2 sw od zgloba (u šaci). | (deo phone) | Sirovi pogoci: 092916 82/300, 084339 32/300, 085956 8/300 (**sat na ruci!**), 031246 0/300. Filter uklanja sat u 085956 (→ 0) i telefon odložen u konzolu na kraju 092916 | Nizak conf na fisheye slici (prosek ~0.25) i treperi. **Na 480 px gubi telefon nisko u ruci** (084339: 32 → 0), zato mora 640. Pametni sat liči na telefon. Rezultat kasni 0.2 s jer radi paralelno. U mraku „potvrdi” i šaku na licu (011221). |
| ↳ pose_call | Ručni zglob uz uvo ili nos | yolo11n-pose | zglob–glava ≤ 0.75 sw → 1, ≥ 0.95 sw → 0. **Bez YOLO telefona u poslednje 3 s ograničen na 0.5** (ispod praga 0.6) | (deo phone) | 092916: poziv pokriven, YOLO ga potvrđuje ✔. Ruka podignuta ka kameri (085956) je 1.0–1.15 sw i ne pali se ✔ | **Ruka na licu ili glavi** (češanje, kašalj, trljanje očiju, glavobolja) ima istu pozu. Pre uvođenja YOLO potvrde to je davalo lažni telefon u ~5 klipova (030825, 090313, 091116, 022338, 011221). Sad se to dešava samo kad YOLO pogrešno „potvrdi” (011221). |
| ↳ pose_typing | Glava spuštena + jedna šaka nisko i ka konzoli | yolo11n-pose | glava: nos–linija ramena od −0.40 do −0.22 sw. Šaka: 0.6–1.7 sw ispod ramena, x od −0.2 do −0.5 sw ka konzoli. Uzima se manja vrednost. **Bez YOLO potvrde ograničen na 0.5, osim ako se poza drži ≥ 4 s bez prekida** | (deo phone) | 084339: ✔. 090604 (telefon na konzoli, YOLO ga skoro ne vidi): hvata od 16.2 s, ~8 s kasno | **Vezivanje i odvezivanje pojasa** ima istu pozu (kopča je kod konzole). Pre uvođenja YOLO potvrde to je bio **najveći izvor lažnih uzbuna** (8 klipova; plus ~7 sa posezanjem ka konzoli). Geometrija je podešena za ove dve kamere i levi volan. Kucanje u sredini krila se ne hvata. |
| **look_away** | Glava okrenuta od neutralnog položaja (levo, desno, dole) | MediaPipe Face Landmarker (matrica transformacije → yaw, pitch) | ugao od neutralnog ≥ 15° → 0, 30° → 1 / 2.0 s / 2.5 s | **0.8** | 084339: pali se dok gleda dole u telefon (9.6–26.7 s, u delovima), što je očekivano, a skor se ne kažnjava duplo. 092916: 0, jer tokom poziva gleda na put ✔. 085956: 0. 031246: ugašen tokom kolapsa | **Neutralni položaj se stalno osvežava:** medijana „mirnih” frejmova u poslednjih 60 s (šake dole, bez telefona, mirno ≥ 1 s), prva procena posle 3 s. Ranije je bila samo iz prvih 3 s i u 011549 je uhvatila vozačicu dok gleda u stranu, pa je cela vožnja bila „sa puta” (skor 0). Mana: ako vozač **većinu vremena** gleda u stranu, to postaje „neutralno”. Fisheye krivi uglove na ivicama (nemamo parametre sočiva). |
| **drowsy** | Zatvorene oči duže od 1.5 s | MediaPipe Face Landmarker (blendshape eyeBlink L/R) | (prosek očiju − lični nivo) 0.25 → 0, 0.45 → 1. Isključen kad je glava spuštena > 12° / 1.5 s / 2 s | **0.9** | 0 događaja na sva 4 test klipa (nijedan ne prikazuje pospanost). Ceo dataset: 1 događaj (022338, vozačica sa glavoboljom zatvara oči), verovatno tačno | **Nije potvrđeno da hvata pravu pospanost** (nema takvog klipa). Kad vozač gleda dole, kamera odozgo vidi kapke kao zatvorene, pa je tada isključen. **Naočare za sunce:** signal ne važi (model „izmišlja” oči). |
| **collapse** | Vozač pao napred i **ne pomera se** | yolo11n-pose | nos–linija ramena +0.10 → 0, +0.30 sw → 1, × **mirovanje** (pomeraj ramena u 1 s ≤ 0.15 sw → 1, ≥ 0.30 sw → 0). = 0 ako je telefon potvrđen / 2.0 s / 2.0 s, **hitan alarm** | **skor odmah pada na 0** (crveno) kad se kolaps potvrdi (`zero_score`), uz `emergency: true` | 031246 (pada na volan ~9 s): kolaps 11.0–29.9 s, **alarm u 13.0 s** ✔. Ceo dataset: **2 hitna alarma, oba prava** (031246, 022338) | **Kasni:** u 022338 vozačica pada ~14 s, a alarm je tek u 23.5 s, jer poza ne prepoznaje osobu koja leži na volanu sa kosom preko lica. Ranije su izlazak iz auta i saginjanje nad telefonom davali lažni hitni alarm. Mirovanje i potvrda telefonom su to uklonili. Isti kolaps može dati **2 alarma** ako se signal na trenutak prekine. |
| eating | Jelo i piće | — | (postoji u scoring.py: 0.6 / 3 s / 6 s) | 0.4 | **Nije implementirano** (uvek 0) | — |
| no_belt | Pojas nije vezan | — | (postoji u scoring.py: 0.6 / 5 s / 5 s) | 0.6 | **Nije implementirano** (uvek 0) | U datasetu ima puno scena vezivanja pojasa, pa bi ovo bio prirodan sledeći signal. |

### Rezime po test klipu

| Klip | Šta se dešava (ručno, iz frejmova) | Skor | Događaji |
|---|---|---|---|
| 08_14_62_092916 | uzima telefon ~8–12 s, poziv ~12–24 s, odloži telefon u konzolu | **39 crveno** | phone 12.5–24.2 |
| 08_14_62_084339 | kuca na telefonu nisko kod konzole ~11–28 s, glava dole | **29 crveno** | phone 12.4–29.9 (3 dela), look_away 9.6–26.7 (3 dela) |
| 08_14_62_085956 | ruka sa satom ispred kamere 0–9 s, vožnja, gleda dole ~25–30 s | **100 zeleno** | — |
| 05_23_62_031246 | naočare za sunce, pada na volan ~9 s i ostaje | **0 crveno + EMERGENCY** | collapse 11.0–29.9 (hitan alarm i skor 0 u 13.0 s) |

---

## 2. Performanse (kriterijum „Real-Time Performance”)

Hardver: **Intel Core i5-1235U (laptop, 12 logičkih jezgara), 16 GB RAM, bez GPU**, Windows 11, Python 3.13.
Merenje obuhvata ceo put po obrađenom frejmu: dekodovanje 3 frejma, sva 3 modela, pravila i skor.
Upis anotiranog videa nije uključen (to je samo za demo) i dodaje ~8 ms.

**Ceo dataset, 56 klipova (16.800 frejmova), čist prolaz bez ičeg drugog na mašini:**

| | medijana | p95 | p99 |
|---|---|---|---|
| tipičan klip (medijana preko 56 klipova) | **78 ms** | **91 ms** | 124 ms |
| najbolji / najgori klip | 66.5 / 91.0 ms | max 166 ms | max 331 ms |

- Medijana < 100 ms u **56/56 klipova**, p95 < 100 ms u **46/56 klipova**.
- RAM: ~750 MB prosek, peak ≤ 779 MB.
- **Cilj < 100 ms je ispunjen za medijanu, a p95 skoro uvek.** Rep (p99) je iznad 100 ms zbog povremenih skokova (Windows u pozadini, dekodovanje, paralelna nit za telefon).
- Brojevi zavise od stanja laptopa: isti klipovi su na „hladnoj” mašini imali medijanu 65–76 ms, a posle 30 minuta rada 72–86 ms.
- **Sva merenja su na struji.** Na bateriji (Windows „Balanced”) isti klip ima medijanu **~120–190 ms**, jer Windows obara snagu procesora.
  **Na demou laptop mora biti uključen u struju.**
- **Pokretanje:** ~3.0 s učitavanje biblioteka i modela + ~2.1 s **zagrevanje** = **spreman ~5.2 s posle pokretanja** (`perf` → `startup_s`).
  Zagrevanje: prvi poziv svakog modela je spor (~2 s, pravi se ONNX sesija, MediaPipe priprema CPU ubrzivač, rezerviše se memorija),
  pa se jedan pravi frejm provuče kroz sve modele **pre vožnje**. Vožnja zato kreće bez rupe: test 300/300 frejmova, 0 preskočenih (ranije ~16).
- Statistika brzine od tada uključuje **sve** frejmove vožnje (ranije su prva 3 izbacivana zbog zagrevanja).
  Tabele iznad su iz ranijih merenja. Nova merenja za 092916 daju isto: medijana 62–65 ms, p95 71–76 ms, p99 77–82 ms.

Kako smo došli do ovoga (sa ~170–670 ms):
1. **ONNX Runtime umesto PyTorch-a.** Ključno je bilo isključiti „spin-wait” niti (`session.intra_op.allow_spinning=0`) i ograničiti ih na 4. Bez toga su se dve ONNX sesije i MediaPipe otimale o jezgra i svaki model je trajao ~300 ms umesto ~35 ms.
2. **Poza na 384 px**: 90–100% slaganja sa 640 px, ~35 ms.
3. **Telefon-YOLO na 640 px, ali na svaki 2. frejm i u paralelnoj niti**: ne čeka se, a rezultat kasni 0.2 s.
4. **Lice samo na isečku glave** (iz poze): ~12–17 ms.
5. **Zagrevanje pre vožnje**: spori prvi poziv modela (~2 s) dešava se pri pokretanju, a ne u prvim sekundama vožnje.

Spremnost za ugrađeni uređaj (ne prenosimo, ali vodimo računa):
- Modeli ukupno **26 MB** (fp32): yolo11n 10.7 MB, yolo11n-pose 11.7 MB, face_landmarker 3.8 MB. INT8 kvantizacija bi ih smanjila ~4× (nije urađeno ni testirano).
- Od ~750 MB RAM-a, ~250 MB je sam Python sa bibliotekama (PyTorch 173 MB, a koristi ga samo Ultralytics za pre/post-obradu). Dve ONNX sesije su 66 MB. U C++ verziji (ONNX Runtime C++ + MediaPipe C++, kako preporučuje organizator) PyTorch i Python otpadaju.
- Radi samo na CPU, 10 fps, 4 niti za ONNX. Sama pravila (`DriverLogic`) su nekoliko mikrosekundi po frejmu.

---

## 3. JSON format za backend i frontend

### 3.1 Live poruka (svaki obrađeni frejm, 10/s) — `live.jsonl`, jedna linija po frejmu

Linija postoji za svaki **obrađeni** frejm (svaki 3. frejm videa → 10 u sekundi → 300 linija za 30 s),
ne za svih 900 frejmova. Za preskočene frejmove važi poslednja linija pre njih.
Pravi primer sa 08_14_62_092916 (poziv, 19.8 s):

```json
{"trip_id": "08_14_62_092916", "t": 19.8, "alert": true, "reason": "phone", "live_score": 65,
 "probs": {"phone": 1.0, "look_away": 0.0, "drowsy": 0.0, "collapse": 0.0}}
```

| Polje | Tip | Značenje |
|---|---|---|
| `trip_id` | string | ID vožnje (u fajlu: ime klipa; uz `--send`: `<klip>-<vreme početka>`) |
| `t` | float, s | vreme od početka vožnje |
| `alert` | bool | da li dashboard treba da bude crven sada |
| `reason` | string \| null | kategorija koja je izazvala alarm (`phone`, `look_away`, `drowsy`, `collapse`) |
| `live_score` | int 0–100 | skor do ovog trenutka |
| `probs` | obj 0–1 | verovatnoće po kategoriji u ovom frejmu (pre EMA); korisno za grafikon |

Veličina: ~170 B po liniji, ~50 KB za 30 s (~1.7 KB/s).
Uz `--send` iste podatke dobija backend kao poruku tipa `live` (ARHITEKTURA.md, sekcija 5).

### 3.2 Događaj (u `events` na kraju vožnje)

```json
{"trip_id": "08_14_62_092916", "event_id": 0, "type": "phone",
 "start": 12.5, "end": 24.2, "severity": 0.985, "peak_t": 22.2, "emergency": false}
```

| Polje | Značenje |
|---|---|
| `type` | `phone` \| `look_away` \| `drowsy` \| `collapse` |
| `start`, `end` | sekunde od početka vožnje |
| `severity` | težina kategorije × prosečna EMA tokom događaja (0–1) |
| `peak_t` | trenutak najjače vrednosti, za „najkritičniju sliku” |
| `emergency` | `true` samo za `collapse`: hitan alarm; potvrđen kolaps obara skor na 0 |

### 3.3 Kraj vožnje — `result.json` (pravi izlaz sa klipa 08_14_62_092916)

```json
{
  "trip_id": "08_14_62_092916",
  "duration": 29.9,
  "score": 39,
  "color": "red",
  "critical_event_id": 0,
  "critical_frame_t": 22.2,
  "emergency": false,
  "events": [
    {"trip_id": "08_14_62_092916", "event_id": 0, "type": "phone", "start": 12.5, "end": 24.2,
     "severity": 0.985, "peak_t": 22.2, "emergency": false}
  ],
  "alerts": [
    {"t": 15.5, "type": "phone", "emergency": false}
  ],
  "critical_frame_file": "critical.jpg",
  "perf": {
    "frames_processed": 300, "analysis_fps": 10.0,
    "ms_per_frame_analysis_mean": 67.8, "ms_per_frame_analysis_median": 68.6,
    "ms_per_frame_analysis_p95": 78.2, "ms_per_frame_analysis_p99": 82.5, "ms_per_frame_analysis_max": 94.9,
    "ms_per_frame_with_video_mean": 75.3,
    "ram_mb_avg": 746, "ram_mb_peak": 772,
    "model_files_mb": {"yolo11n_640.onnx": 10.7, "yolo11n-pose_384.onnx": 11.7, "face_landmarker.task": 3.8},
    "models_total_mb": 26.2,
    "hardware": "12th Gen Intel(R) Core(TM) i5-1235U, 12 logičkih jezgara, 16 GB RAM, bez GPU",
    "backend": "onnx det=640 pose=384 phone_every=2"
  },
  "face_calibration": {"source": "auto, neprekidno (poslednja: 92 mirnih frejmova u 29.0s)",
                       "neutral_yaw_pitch_eyes": [31.58, 14.39, 0.37]}
}
```

- `score`, `color`: `green` ≥ 80, `yellow` ≥ 50, `red` < 50.
- `critical_event_id`, `critical_frame_t`: najkritičniji događaj. Hitan (kolaps) ima prednost; inače onaj sa najvećim `severity × trajanje`. `critical.jpg` je vrh tog događaja, sa okvirima.
- `alerts`: trenuci kad je neki događaj prvi put prešao „alarm posle” (za notifikacije).
- **Važno za frontend:**
  - Kad se kolaps potvrdi, skor u istom trenutku pada na **0** (031246: skor 100 do 13.0 s, pa 0 uz hitan alarm). Hitan alarm i dalje prikazati preko celog ekrana, ne samo kao crven skor.
  - Isti kolaps može dati **više hitnih alarma** (031246: 13.0 s i 18.1 s) ako se signal na trenutak prekine. Frontend treba da ih spoji (npr. ignoriše novi `collapse` alarm u roku od 10 s od prethodnog).
- `perf`, `face_calibration` i `critical_frame_file` dodaje `pipeline.py`. Ostalo je nepromenjeni izlaz `scoring.finish()`.
- Novije verzije u `perf` imaju i `startup_s`: `{"load": 2.98, "warmup": 2.06, "ready_after": 5.16}` (sekunde od pokretanja programa).

---

## 4. Šta NE obećavamo na pitchu (nije uspelo ili nije pouzdano)

1. **Nema zvanične tačnosti u procentima.** Dataset nema oznake; „istinu” smo određivali ručno iz frejmova (35 od 56 klipova). Pravila su podešavana na 16 od tih klipova, pa su brojevi optimistični.
2. **Pospanost (drowsy) nije potvrđena.** U datasetu nema jasnog klipa sa zatvorenim očima (1 događaj u 56 klipova, verovatno tačan). Sa naočarima za sunce signal ne radi.
3. **Gledanje sa puta nije sistematski provereno.** Na pregledanim primerima deluje tačno (gleda pojas, suvozača, konzolu, telefon), ali nije brojano.
4. **Telefon:** pouzdanost dolazi iz kombinacije poze i YOLO-a, ne iz samog detektora (conf ~0.25 na fisheye slici). Propušta:
   - telefon u krilu u mraku (010741);
   - kratko gledanje u telefon (023609);
   - telefon na konzoli koji YOLO ne vidi: kasni (090604, ~8 s) ili ga uopšte ne hvata (090759).
5. **Ruka na licu** može i dalje da izgleda kao poziv, kad YOLO pogrešno „vidi” telefon (011221, u mraku).
6. **Kolaps kasni**, posebno kad poza ne vidi osobu koja leži na volanu (022338: alarm ~9.5 s posle pada). Definicija je „pao napred i miruje ≥ 2 s”, ne medicinska dijagnoza.
7. **Pravila su vezana za ove dve kamere i levi volan** (zone u `rois.json`, „konzola je levo od vozača na slici”). Na drugom autu treba ponovo nacrtati zone i proveriti pragove.
8. **Jelo i pojas nisu implementirani**, iako postoje kao kategorije u `scoring.py`.
9. **Nema ispravke fisheye distorzije** (specifikacija daje samo FOV, ne i parametre sočiva).
10. **Latencija:** medijana < 100 ms na svim klipovima, ali p95 je iznad 100 ms na 10/56 klipova, a p99 je obično ~124 ms. Signal telefona kasni 0.2 s.

---

## 5. Ceo dataset (56 klipova) — provera lažnih uzbuna

Postupak:
1. Pipeline je pušten na svih 56 klipova (`--all --no-video`).
2. Za sumnjive klipove smo napravili listove frejmova u trenucima događaja i ručno proverili šta se dešava (35 klipova ukupno).
3. Našli smo tri vrste lažnih uzbuna i popravili pravila (vidi ispod).
4. Pustili smo ceo dataset ponovo.

### 5.1 Pre i posle popravki (isti 56 klipova)

| | Prvi prolaz | Posle popravki |
|---|---|---|
| Klipova sa događajem `phone` | 30 | **8** |
| Klipova sa `look_away` | 35 | 23 |
| Klipova sa `drowsy` | 2 | 1 |
| Hitnih alarma (kolaps) | 5 klipova | **2 klipa** |
| Klipova bez ijednog događaja | 15 | 27 |
| Zeleno / žuto / crveno | 42 / 7 / 7 | 48 / 2 / 6 (oba kolapsa sada 0, crveno) |

### 5.2 Šta je ručni pregled pokazao

| Signal | Prvi prolaz | Posle popravki |
|---|---|---|
| **Kolaps (hitan alarm)** | 5 alarma: **2 prava** (031246, 022338), **3 lažna** (izlazak iz auta 032409 i 032617, saginjanje nad telefonom u krilu 005853) | **2 alarma, oba prava**. Lažni uklonjeni jer se sada traži mirovanje i odsustvo telefona. |
| **Telefon** | 30 klipova: ~8 pravih, **~19 lažnih**: vezivanje pojasa (010514, 015313, 015556, 031407, 084110, 032409, 032617, 025555), ruka na licu ili glavi (030825, 090313, 091116, 022338), posezanje i nameštanje (010650, 012138, 022115, 022537, 024522, 030020, 032135) | 8 klipova: **6 pravih** (092916, 084339, 090604, 021254, 005853, 010741), **2 sumnjiva** (011221 trljanje očiju u mraku, 094103 okrenut ka suvozaču) |
| **Propušten telefon** | — | 023609 (telefon u krilu ~1.6 s), 090759 (verovatno telefon na konzoli; i dalje dobija `look_away`). Delimično: 010741 (14–26 s, mrak), 090604 (8–16 s) |
| **look_away** | 011549 i 015313: „sa puta” skoro ceo klip zbog loše kalibracije (011549 skor 0) | Uklonjeno (neprekidna kalibracija). Preostali događaji na pregledanim primerima odgovaraju gledanju u pojas, suvozača ili konzolu. |

Za pitch, poštena formulacija:
- „Na 56 klipova sistem je dao 2 hitna alarma i oba su prava padanja vozača na volan.”
- „Lažne uzbune za telefon smanjili smo sa ~19 klipova na ~2, uz cenu od 2 propuštena klipa.”
- Uz napomenu da je „istina” ručna procena iz frejmova, ne zvanične oznake.

### 5.3 Tri popravke posle pregleda (sve u `features.py`, klasa `DriverLogic`)

1. **Poza mora biti potvrđena YOLO-om.** Signali poza-poziv i poza-kucanje mogu dostići pun nivo samo ako je YOLO video telefon (prošao filter) u poslednje 3 s, inače su ograničeni na 0.5. Izuzetak: poza kucanja koja se drži ≥ 4 s. Poza kaže *kako* se telefon koristi, a YOLO *da telefon postoji*.
2. **Neprekidna kalibracija pogleda:** neutralni položaj glave je medijana mirnih frejmova u poslednjih 60 s, a ne samo prve 3 s.
3. **Kolaps traži mirovanje** (izlazak iz auta je pokret, a pad je pa-miruje) i **nema potvrđenog telefona**. Prag za glavu je spušten na 0.10–0.30 sw, jer na 384 px pali vozač ima nos na +0.25 do +0.36.

Probali smo i da pozu pustimo sa nižim pragom (0.10), da nađe vozačicu koja leži na volanu (022338). Model tada daje besmislene tačke, pa smo to vratili.
