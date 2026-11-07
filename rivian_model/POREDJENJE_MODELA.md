# Poređenje modela na pravom koordinatoru (6. 11. 2026, uveče)

Naš model (`rivian_detector.py`, worker `rivian-pose`) i model CV kolege (`model/worker.py`, worker `cv-pipeline`)
su pušteni kroz **isti** koordinator tima, na 4 test klipa, jedan po jedan. Laptop je bio na struji.

## Kako je mereno
- Kod tima je na najnovijem `origin/main` (`5f1656b`), u zasebnom checkout-u `C:\Users\PC\rivian-hakaton-main`. **Nijedna linija njihovog koda nije menjana.**
- Koordinator: `run.py --role coordinator --port 8765`, server namerno nedostupan (koordinator radi i bez njega).
  Brzina auta je fiksna: `SPEED_SCENARIO=cruise` (50–62 km/h), ista za oba modela. Podrazumevani `random` bi dao različite vožnje.
- Kamera: njihov `tools/camera_stream.py --video <klip>` (10 fps, 1280 px, u realnom vremenu), 30 s po klipu.
- Skor i ponašanja: `GET /trips/{id}` 4× u sekundi, rezime: `POST /trips/{id}/end`. Skripta: `run_compare.py` u ovom folderu (uputstvo za pokretanje je na vrhu fajla).
- Rizik, skor i alarme računa **njihov** `RiskEngine` + `scoring.py`, a ne naš `scoring.py`.

## Rezultati

| Klip (šta se stvarno dešava) | Naš model | Model CV kolege |
|---|---|---|
| **092916**: poziv telefonom ~12–24 s | skor **0**, hitan alarm u 27.2 s. Telefon 14.1–26.2 s | skor **0**, hitan alarm u 19.8 s. Telefon 13.3–26.6 s, ruke van volana 17.4–27.7 s, **pogled van puta 1.9–7.1 s** (pre poziva) |
| **084339**: kuca na telefonu nisko ~11–28 s | skor **0**, hitan alarm u 20.3 s. Telefon 14.3–27.6 s (2 dela, 13.0 s), pogled van puta 18.1 s | skor **0**, hitan alarm u 19.9 s. **Telefon samo 2.3 s**, pogled van puta 16.6 s, ruke van volana 4.2 s |
| **085956**: miran klip, ruka sa satom ispred kamere 0–9 s | skor **95** (zeleno). Jedan pogled van puta od 0.5 s | skor **51** (visok rizik). Pogled van puta 0.8–7.9 s (dok ruka zaklanja lice), ruke van volana 16.6–21.0 s |
| **031246**: pada na volan ~9 s i ostaje | skor **89, bez alarma**. Naš `collapse` koordinator **odbacuje** (nije u `risk_config.json`) | skor **0, hitan alarm u 25.2 s** (~16 s posle pada), preko „pogled van puta” od 9.9 s + „ruke van volana” od 16.3 s |

| Brzina (po frejmu, u workeru) | Naš model | Model CV kolege |
|---|---|---|
| vreme obrade | **59–66 ms** | **106–156 ms** (raslo iz klipa u klip) |
| obrađeni frejmovi od ~300 (10 fps × 30 s) | ~292–296 (skoro svi) | ~166–198 (koordinator ostale preskače) |

## Šta iz ovoga sledi
1. **Telefon:** oba modela hvataju poziv (092916). Kucanje nisko kod konzole (084339) naš model hvata 13 s, CV model 2.3 s.
2. **Lažni alarmi:** na mirnom klipu (085956) naš model daje 95, CV model 51, zbog ruke ispred kamere i „ruku van volana”.
3. **Kolaps:** u sistemu kakav je sada, **samo CV model diže alarm** (posredno, ~16 s posle pada). Naš model kolaps vidi, ali ga koordinator ne čita.
   Kada bi se kolaps dodao u njihov sistem, naš alarm bi bio ~13 s (izmereno ranije, van koordinatora, **nije provereno na koordinatoru**).
4. **Brzina:** naš model je ~2× brži i stiže svih 10 fps; CV model stiže ~6 fps.
5. **Njihov skoring je vrlo strog (za oba modela isto):** ~12 s telefona pri 50–62 km/h daje skor 0 i **hitan alarm** sa porukom „javljeno kontaktu za hitne slučajeve”.
   Najviše kažnjava svaki *novi* početak ponašanja (092916: telefon na trenutak nestane i vrati se → skor odjednom −14).
   Na demo-u to znači da poziv telefonom izgleda isto kao kolaps. To treba reći backend i CV kolegi.

## Šta nije provereno (ne obećavati)
- Po jedan prolaz po klipu, samo 4 klipa (ne ceo dataset od 56).
- CV model je pušten u globalnom Python-u 3.13 (MediaPipe 1.2.2), ne u njihovom venv-u (3.12). Brzina i rezultati mogu malo da se razlikuju.
- Zašto se CV model usporavao iz klipa u klip (106 → 156 ms): nije istraženo.
- Vremena su pomerena ~0.5–1.5 s zbog starta kamere i glađenja u koordinatoru.
- Telefon nije bio povezan (nema WS klijenta), a server nije radio, pa sekcije sa slikama nisu proverene.
