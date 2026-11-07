# Personal Safety Reviewer

Većina saobraćajnih nesreća ne počinje greškom u upravljanju, nego trenutkom nepažnje: pogled u telefon, mikrospavanje,
okretanje ka zadnjem sedištu. Vozač to često ne primeti, a kada primeti, obično je kasno. **Personal Safety Reviewer**
je sistem koji takve trenutke prepoznaje dok se dešavaju i upozori vozača dok još ima vremena da reaguje.

Kamera u kabini prati vozača, a softver u kolima stalno računa **ocenu pažnje od 0 do 100**: 100 znači da je vozač
potpuno usredsređen na put, a što je ocena niža, to je situacija opasnija. Kola na tu ocenu reaguju postepeno, slično
saobraćajnom semaforu.

| Ocena | Šta to znači | Kako kola reaguju |
|---|---|---|
| 90–100 | vozač je pažljiv | zeleno svetlo |
| 75–90 | kratko ometanje | zeleno-žuto svetlo, poruka na ekranu |
| 35–75 | rizično ponašanje | žuto svetlo, vibracija sedišta i zvučni signal |
| 10–35 | ozbiljna opasnost (npr. duži pogled u telefon u brzini) | crveno svetlo, vibracija i glasan alarm |
| 0 | vozač ne reaguje (onesvestio se, pao na volan) | glasan alarm, telefon sam pošalje SMS kontaktu za hitne slučajeve i nudi poziv |

Sistem je pravedan prema vozaču. Ocena se kvari samo dok se rizično ponašanje zaista dešava, a vraća se na 100 čim
prestane, pa jedan pogled u retrovizor ne ostavlja trag. Dok kola stoje, nema ni upozorenja ni kazne. Brzina pojačava
opasnost: isti pogled u telefon na autoputu teži je nego u gradskoj gužvi.

Posle svake vožnje vozač na telefonu dobija **izveštaj**: grafik cele vožnje sa označenim opasnim delovima, slike
najopasnijih trenutaka, šta je najčešće radio i konkretne savete. Na početnom ekranu aplikacije vidi i trend kroz
poslednje vožnje: da li vozi sve bezbednije i koje mu navike prave najveći rizik.

## Šta sistem prepoznaje

- korišćenje telefona (razgovor, kucanje);
- pogled skrenut sa puta duže od par sekundi;
- zatvorene oči i mikrospavanje;
- kolaps: vozač je pao napred i ne pomera se. To je **hitan slučaj**: uzbuna kreće čak i kad kola stoje, a telefon
  odmah, bez ičije potvrde, pošalje SMS kontaktu za hitne slučajeve i nudi poziv.

Privatnost je ugrađena od početka. Slike iz kabine vidi samo vozač, u svom izveštaju. Kompanija ili osiguravač vide
samo brojeve: ocene, vrste grešaka i koliko su trajale, nikada lice vozača.

## Značaj za osiguravajuće kuće

Osiguravači danas cenu polise uglavnom određuju po godinama, mestu stanovanja i istoriji šteta, dakle po tome ko je
vozač, a ne kako vozi. Ovaj sistem daje ono što nedostaje: **objektivnu meru ponašanja za volanom**, vožnju po vožnju.

- **Pravednija cena polise.** Vozač koji stalno ima visoku ocenu može dobiti popust, kao u postojećim programima „plati
  koliko i kako voziš“, ali sa merom koja vidi uzrok rizika, a ne samo naglo kočenje.
- **Manje šteta.** Upozorenje u trenutku ometanja sprečava nesreću pre nego što se dogodi, što je za osiguravača
  vrednije od bilo kakve naknadne procene.
- **Brža pomoć i jasnija slika posle nesreće.** Kolaps vozača odmah podiže uzbunu i nudi poziv u pomoć, a zapis
  vožnje pokazuje šta se dešavalo u trenucima pre događaja.
- **Podsticaj za bolju vožnju.** Izveštaji i trendovi motivišu vozača da menja navike, pa se rizik smanjuje vremenom.

Uz to, sistem ne zahteva novu infrastrukturu na putu: dovoljna je kamera u kabini i računar koji kola već imaju.

## Šta je sve deo projekta

Projekat obuhvata softver u kolima (prepoznavanje sa kamere i računanje ocene), server koji čuva vožnje i pravi
izveštaje, Android aplikaciju za vozača (upozorenja uživo, istorija, izveštaji, trendovi) i prikaz ekrana u kolima.
Kako se sve pokreće opisano je u [DOCKER.md](DOCKER.md), a kako model i računanje ocene rade u
[KAKO_RADI_MODEL.md](KAKO_RADI_MODEL.md).
