# Personal Safety Reviewer: Rivian hakaton

Tim komunicira na srpskom (latinica). Kod, identifikatori, API i labele su na engleskom.

## Ideja

Kamera u kabini prati vozača. Backend računa **koeficijent pažnje 0–100** (100 = potpuno usredsređen,
0 = opasnost po život), a kola reaguju: svetlo na dashboardu, vibracija sedišta, zvučni signal, poruka
kontaktu za hitne slučajeve. Na kraju vožnje vozač dobija statistiku i savete. Kompanija vidi samo
koeficijente i vrste grešaka, **nikad slike** (privatnost).

## Delovi repoa

| Putanja | Šta je |
|---|---|
| `backend/` | FastAPI: računa score, šalje događaje aplikaciji. Detalji u `backend/CLAUDE.md` |
| `notebooks/` | CV modeli (YOLO, OpenCV, MediaPipe), rade drugi članovi tima |
| `notebooks/safety_client.py` | most modeli → backend, plus simulator cele vožnje |
| `frontend/mobile/` | Expo (SDK 58) Android aplikacija za vozača, dev build. Pravila: `.claude/rules/mobile.md` |
| `frontend/dashboard/` | web mock ekrana u kolima (Vite + React). Pravila: `.claude/rules/dashboard.md` |
| `docs/API.md` | **ugovor backend ↔ aplikacija, izvor istine.** Pročitaj ga pre bilo kakvog rada na frontendu |
| `PROGRESS.md` | stanje projekta, bagovi, sledeći koraci. Pročitaj na početku, ažuriraj na kraju |
| `.claude/` | pravila, skillovi i knowledge za agente (frontend, alati, mreža, Android). Indeks: `.claude/CLAUDE.md` |

## Arhitektura i mreža

```
laptop: notebooks (modeli) ──POST 127.0.0.1:8000/api/v1/telemetry (~2/s, frejm modela ili labele)──► backend
telefon (hotspot): React Native app ◄──WS /api/v1/ws (uživo)── backend
                                    ──REST /trips (start, kraj, istorija)──►
```

- Za demo **nema servera ni DNS-a**. Laptop pokreće backend i modele, telefon pravi hotspot, a laptop
  je povezan na njega. Aplikacija gađa IP laptopa, koji `python backend/run.py` ispiše pri
  pokretanju. IP se menja pri svakom ponovnom povezivanju.
- **Jedan auto = jedna aktivna vožnja.** Telemetrija ide u aktivnu vožnju, a nova vožnja završava
  prethodnu.
- Model šalje svoj zapis frejma (isti kao red u `frames.jsonl`) preko `SafetyClient.send_frame`,
  bez `perception` i bez slika. Backend preslikava aktivne kategorije modela na labele
  (`CATEGORY_TO_BEHAVIOR` u `backend/app/services/camera.py`), a rizik i kategorije modela
  prosleđuje aplikaciji u polju `camera`.

## Pravila domena (sažetak)

- Labele: `looking_at_phone`, `looking_behind`, `turning_around`, `hands_off_wheel`, `drowsy`,
  `eyes_off_road`.
- Penal = težina × sekunde, plus jednokratni udar kad ponašanje počne. Penal se množi sa:
  - brzinom (< 5 km/h nema penala, autoput 1.7×)
  - noći (22–06h, 1.5×)
  - "krhkošću" (što je score niži, lakše pada)
- Oporavak: posle 30 s čiste vožnje, +3 poena/min.
- Nivoi: `safe` 90–100, `caution` 75–90, `warning` 55–75, `high_risk` 35–55, `critical` 10–35,
  `emergency` < 10. Reakcija kola po nivou je opisana u `docs/API.md`, sekcija 7.
- Alarm modela: kad model javi crveno (`alert.level == "red"`), kola u pokretu odmah vibriraju i
  glasno pište, na bilo kom nivou.

## Odluke (tumačenje prvog nacrta ideje)

- U nacrtu je pisalo 75–80 → uzeto 75–90. Pisalo je 35–75 → uzeto 35–55, sa žutim svetlom i
  pragom reakcije od 2 s.
- "Velika pripravnost" (10–35) = crveno svetlo, a vibracija i zvuk kreću odmah.
- Dok kola stoje nema penala ni upozorenja, i to se ne računa u statistiku.
- Jelo, cigareta, konverzacija i ometanje od suvozača su izbačeni, jer ih modeli ne prepoznaju.
- (2026-11-06) Model ima svoj trenutni rizik (0..1, tri boje). **Naš score 0–100 ostaje glavni** za
  svetlo, nivoe i statistiku, a crveni alarm modela samo forsira vibraciju i zvuk. Razlog: kod
  score-a 100 nivo `safe` nikad ne reaguje, pa bi prvo mikrospavanje prošlo bez upozorenja.
- (2026-11-06) `eyes_off_road` je vraćen kao labela sa malom težinom (1.0), jer ga model sada daje.
  Kad ide zajedno sa `phone_use`, penali se sabiraju.
- `perception` (uglovi glave, oči, šake) ne ide na backend, jer aplikaciji ne treba.

## Otvorena pitanja (ažuriraj kad se dogovori)

1. **Brzina:** kamera je ne zna. Sada je šalje strana sa modelima (za demo zakucana). Predlog je
   GPS telefona preko WebSocket-a.
2. **Imena kategorija modela:** viđeni su samo `phone_use` i `eyes_off_road`. Za ostale je
   pretpostavka `turned_around`, `hands_off`, `drowsiness`, `microsleep` (`CATEGORY_TO_BEHAVIOR`).
   Treba potvrditi sa CV timom. Nepoznatu kategoriju backend loguje i ne boduje. Takođe: da li
   postoji poseban izlaz za `looking_behind` ili samo `turned_around`?
3. `hands_off_wheel`: obe ruke ili bar jedna? Ako je jedna, težinu treba spustiti na 0.3–0.5.
4. **Poruka kontaktu:** backend sada samo loguje. Predlog je da aplikacija pošalje SMS na
   događaj `emergency`.

## Pravila za izmene koje prelaze iz jednog dela u drugi

- Promena ruta, šema ili enuma u backendu → **ažuriraj `docs/API.md` u istoj izmeni**.
- Promena labela → `Behavior` enum, težina u `scoring.py`, savet u `TIPS`, `BEHAVIORS` u
  `notebooks/safety_client.py`, `CATEGORY_TO_BEHAVIOR` u `services/camera.py` (ako se ime
  kategorije modela razlikuje) i `docs/API.md`.
- Frontend ne izmišlja endpointe ni polja. Ako nešto fali, to je izmena backenda.
