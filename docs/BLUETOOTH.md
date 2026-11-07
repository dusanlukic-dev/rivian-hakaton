# Bluetooth veza telefon ↔ kola (BLE)

Telefon sa kolima (koordinatorom) priča preko **Bluetooth Low Energy**, a sa serverom preko HTTP(S). Hotspot
telefona više nije potreban za vožnju: služi samo da telefon (i laptop) stignu do servera dok server radi na
laptopu. Rezerva je stari put, WebSocket preko Wi-Fi-ja (Podešavanja → Car connection → Wi-Fi).

```
 telefon ──BLE (stanje, sekcije, uzbuna; start/kraj vožnje)──► car link gateway ──localhost──► koordinator :8000
    │                                                           (laptop, zaseban proces)
    └──HTTP(S): nalozi, istorija, izveštaj, slike─────────────────────────────────────────────► server :8001
```

- **Gateway** (`backend/coordinator/car_link/gateway.py`) je zaseban proces u kolima: koordinatorov WebSocket
  (`/api/v1/ws`) prosleđuje telefonu kao BLE notifikacije, a zahteve telefona pretvara u lokalne REST pozive
  koordinatoru. **Koordinator se ne menja** i ne zna za Bluetooth. Pad Bluetooth-a ne ruši score.
- **Ugovor ostaje [API.md](API.md):** iste JSON poruke (§6) i iste rute [K] (§5). Menja se samo prenos.
- Laptop mora da ima uključen Bluetooth i adapter koji podržava *peripheral* ulogu (ovaj laptop: MediaTek, da).

## GATT

| | UUID | Svojstva | Smer |
|---|---|---|---|
| servis | `5afe0000-7a1e-4c55-8d2b-9c1e0f3a6b01` | oglašava se (discoverable, connectable) | |
| `rx` | `5afe0001-7a1e-4c55-8d2b-9c1e0f3a6b01` | indicate (telefon potvrđuje svaki okvir) | kola → telefon |
| `tx` | `5afe0002-7a1e-4c55-8d2b-9c1e0f3a6b01` | write, write without response | telefon → kola |

Telefon traži kola po UUID-u servisa (ne po adresi, jer Windows može da menja BLE adresu), traži MTU 517,
visok prioritet veze, pa se pretplati na `rx` i pošalje `hello`.

## Okviri (framing)

Jedna poruka = jedan JSON objekat (UTF-8). Notifikacija ili upis nosi najviše `MTU − 3` bajta, pa se poruka
seče na okvire:

```
bajt 0-1  msg_id  uint16 BE   broj poruke pošiljaoca (raste, posle 65535 ide 0)
bajt 2-3  index   uint16 BE   0 .. count-1
bajt 4-5  count   uint16 BE   ≥ 1
bajt 6..  deo JSON-a
```

Primalac skuplja okvire jedne poruke redom. `index == 0` počinje novu poruku; okvir sa drugim `msg_id` ili
neočekivanim `index` odbacuje započetu (izgubljen okvir košta jednu poruku, ne ceo tok). Kad stigne
`index == count − 1`, JSON se parsira.

**Okvir je najviše 244 bajta** u oba smera (jedan radio paket: LE data length 251), iako telefon i laptop
dogovore MTU 517. Provereno na ovom laptopu (MediaTek, Windows 11) i A54: okviri od 514 B (pun MTU, traže L2CAP
segmentaciju) **nikad nisu stigli** do telefona, iako ih je Windows prijavio kao poslate, a okviri ≤ 244 B stižu
svi. Poruka `state` (~0.9–1.2 KB) je tako 4–5 okvira, dva puta u sekundi: ~3 KB/s, daleko ispod kapaciteta.
Gateway: `--max-frame`; telefon: `MAX_FRAME` u `CarLinkModule.kt`.

**Indikacije, ne notifikacije.** Sa notifikacijama su se gubile poruke dok telefon piše zahtev (odgovor na
"End trip" i `trip_ended` nikad nisu stigli). Indikaciju telefon potvrđuje, pa Windows javlja uspeh tek kad okvir
stigne. Cena je brzina (jedan okvir po potvrdi, Windows drži interval veze ~30 ms), pa gateway **spaja stanja**:
noviji `state` (i `ping`) zamenjuje onaj koji još čeka u redu, a odgovori, sekcije i događaji (`trip_started`,
`emergency`, `trip_ended`, `hello`) uvek idu, redom. Red zato nikad ne raste i telefon uvek ima najsvežije stanje.

## Da li je veza živa

- Gateway šalje `{"type": "ping"}` na svake **2 s** kad nema drugog saobraćaja.
- Telefon posle **7 s** tišine sam prekida vezu i ponovo traži kola. Zašto: Windows drži radio vezu i kad se
  proces gateway-a ugasi ili restartuje (telefon i dalje misli da je povezan na servis koji više ne postoji), a
  Android ne javi aplikaciji prekid kad se Bluetooth na telefonu isključi i uključi.
- Telefon prati i Android-ov broadcast za uključenje/isključenje Bluetooth-a: isključen = veza se odmah zatvara,
  uključen = odmah novi pokušaj.

## Poruke

**Telefon → kola**

| `type` | Polja | Šta kola rade |
|---|---|---|
| `hello` | `app`, `version` | odgovore porukom `hello`, a ako vožnja traje, odmah pošalju i poslednji `state` |
| `request` | `id` (string), `method`, `path` (bez `/api/v1`), `token` (Bearer ili `null`), `body` (JSON ili `null`) | pozovu koordinatora `http://127.0.0.1:8000/api/v1{path}` sa `Authorization: Bearer <token>` i vrate `response` |

Dozvoljene rute (samo [K] koje telefon koristi): `GET /health`, `POST /trips`, `POST /trips/{id}/end`,
`GET /trips/{id}`, `GET /speed`, `POST /speed`, `GET /coordinator/status`. Ostalo dobija `404`.

**Kola → telefon**

| `type` | `data` / polja | Kada |
|---|---|---|
| `hello` | `{"protocol": 1, "car": "<ime>", "coordinator": true, "server_url": "http://<ip>:8001/api/v1"}` | odgovor na `hello` i svaki put kad gateway izgubi ili vrati vezu sa koordinatorom |
| `ping` | (nema) | na 2 s kad nema drugih poruka (vidi "Da li je veza živa") |
| `response` | `id`, `status` (HTTP status koordinatora; `0` = koordinator ne odgovara), `body` | odgovor na `request` |
| `state`, `trip_started`, `emergency`, `section`, `trip_ended` | kao u API.md §6 | prosleđeno sa koordinatorovog WebSocket-a, bez izmene |

- `coordinator: false` znači da Bluetooth radi, ali koordinator ne odgovara (aplikacija prikazuje "kola offline").
- `server_url` je adresa servera kako je vidi telefon (gateway zamenjuje `127.0.0.1` IP adresom laptopa);
  aplikacija je nudi u ekranu Server kao predlog, nikad je ne menja sama.

## Pokretanje

```powershell
cd backend; .\start.ps1 -Mock -Ble        # server, koordinator (+ mock kamera i model) i gateway, svako u svom prozoru
# ili sam gateway (koordinator već radi na :8000):
backend\coordinator\.venv\Scripts\python.exe backend\coordinator\car_link\gateway.py
```

Gateway u logu piše kad počne oglašavanje, kad se telefon pretplati (i koliki mu je okvir), svaki zahtev i na
10 s koliko je poruka poslato (`-v`: svaka poruka, veličina, broj okvira, ms). Testovi bez Bluetooth-a:
`pytest backend/coordinator/car_link` (okviri + protokol gateway-a sa lažnim GATT-om i koordinatorom).

**Provereno na uređaju (2026-11-07):** laptop (MediaTek, Windows 11) ↔ A54 (Android 16): pronalaženje po UUID-u,
MTU 517, dozvola "Nearby devices" iz aplikacije, start vožnje preko BLE (`POST /trips` 201, ~0.3 s), živo stanje
i sekcije 2/s (180 poruka, 0 izgubljenih, red prazan), kraj vožnje preko BLE (`200`) pa rezime i izveštaj sa
servera na :8001, ponovno povezivanje posle restarta gateway-a (~10 s) i posle gašenja i paljenja Bluetooth-a na
telefonu (~4 s). Windows oglašava sa nasumičnih adresa koje se menjaju (A3:5D, EB:7A, 6E:9E za par minuta), pa
telefon uvek prvo skenira, a poslednju adresu samo preferira.

## Ograničenja i planirano

- **Bez šifrovanja** (demo): ko je u dometu (~10–30 m) može da čita stanje i zove [K] rute, isto kao bilo ko na
  hotspotu ranije. Planirano: `tx` sa `EncryptionRequired` (LE Secure Connections, adapter ih podržava) i
  uparivanje, ili kod sa ekrana kola.
- Ime u oglasu je ime laptopa (Windows ne da GATT serveru da ga menja); aplikacija prikazuje ime iz `hello`.
- Android pamti GATT tabelu uređaja: posle promene servisa ili karakteristika telefon osveži keš sam
  (`BluetoothGatt.refresh`), a ako i dalje ne vidi karakteristike, isključi i uključi Bluetooth.
- Android dozvoljava 5 pokretanja skeniranja u 30 s po aplikaciji, pa aplikacija skenira dugo i retko.
