# Kako rade model i računanje ocene

Put jednog frejma je kratak: kamera snimi kabinu, model kaže šta vidi, a koordinator od toga izračuna rizik, ocenu
pažnje i reakciju kola. Model samo prepoznaje; ocenu i odluke donosi koordinator.

```
kamera ──JPEG, 10 fps──► koordinator ──frejm──► model ──dokaz po kategoriji (JSON)──► koordinator
                                                          RiskEngine → ocena 0–100 → svetlo, vibracija, zvuk
                                                          na svake 2 s → sekcija (+ slika) → server → izveštaj
```

## Video

Kamera u kabini je fisheye od 180° (1920×1536, 30 fps); u demou je zamenjuju snimci iz dataseta. Program za kameru
(`tools/camera_stream.py`) dekodira video pomoću **ffmpeg-a** (paket `imageio-ffmpeg`), uzima svaki treći frejm, smanji ga
na 1280 px širine i šalje koordinatoru kao JPEG preko WebSocket-a, deset puta u sekundi. Koordinator čuva poslednjih pet
minuta frejmova (`diskcache`), da bi za opasan trenutak kasnije izvukao sliku, i svaki frejm prosleđuje modelu. Ako model
kasni, stariji frejm se preskače i uvek se analizira najnoviji.

## Analiza frejma

Model (`rivian_model/`) prvo iseče deo slike gde sedi vozač (zona zavisi od serije kamere), pa na tom isečku pušta tri
unapred obučena modela. Sva tri rade preko **ONNX Runtime-a**, a slike se obrađuju pomoću **OpenCV-a** i **NumPy-a**.

| Model | Biblioteka | Šta daje |
|---|---|---|
| YOLO11n-pose (384 px) | Ultralytics | 17 tačaka tela: glava, ramena, laktovi, šake |
| YOLO11n (640 px), na svaki drugi frejm | Ultralytics | kutiju „mobilni telefon“ (COCO klasa 67) |
| Face Landmarker | MediaPipe | uglove glave (levo-desno, gore-dole) i koliko su oči zatvorene |

Pravila u `features.py` od toga prave četiri verovatnoće od 0 do 1. Rastojanja se mere u širinama ramena, pa ne zavise
od toga koliko je vozač blizu kameri.

- `phone_use`: telefon u šaci ili uz uvo, ili poza poziva i kucanja koju potvrđuje YOLO kutija telefona;
- `eyes_off_road`: glava okrenuta 15–30° od vozačevog uobičajenog položaja, koji se stalno osvežava iz mirnih trenutaka;
- `eyes_closed`: oči zatvorenije od vozačevog ličnog nivoa;
- `collapse`: glava pala ispod linije ramena, a telo se ne pomera.

Rezultat za svaki frejm model vraća koordinatoru kao JSON:

```json
{ "type": "detection", "t": 12.4, "ms": 61.0,
  "evidence": { "phone_use": 0.82, "eyes_off_road": 0.10, "eyes_closed": 0.00, "collapse": 0.00 } }
```

Na laptopu bez grafičke kartice obrada jednog frejma traje ~60–80 ms, pa model stiže svih deset frejmova u sekundi.

## Od dokaza do ocene

Koordinator dokaz prvo provlači kroz **RiskEngine** (`risk_engine.py`, pragovi u `notebooks/risk_config.json`). On
izglađuje svaku verovatnoću eksponencijalnim prosekom (EMA, τ 0.3 s), uključuje i isključuje kategoriju sa histerezom
da ne bi treperila, i pojačava doprinos što ponašanje duže traje. Kategorije spaja u jedan rizik od 0 do 1: unutar grupe
se uzima najveća, a između grupa se kombinuju kao nezavisni događaji. Tvrda pravila postavljaju donju granicu rizika,
na primer mikrospavanje duže od 1.5 s, telefon duži od 2 s ili kolaps duži od 2 s. Iz rizika sledi i alarm modela:
zeleno, žuto (od 0.4) ili crveno (od 0.7).

Ocenu 0–100 računa `scoring.py`, takođe u koordinatoru. Ponašanje se računa tek kad traje dovoljno dugo (telefon 1 s,
pogled sa puta 2 s), a kratke rupe u detekciji ga ne prekidaju, pa jedan poziv daje jedan glatki pad ocene. Trenutna
opasnost je najgore aktivno ponašanje uz 30 % ostalih (ili rizik iz RiskEngine-a, ako je veći), a množi se
faktorom brzine: 0 dok kola stoje, 1.0 na 50 km/h,
1.6 na 130 km/h, i još ×1.25 noću. Ocena je `100 × (1 − opasnost × brzina)`; brzo pada, a za nekoliko sekundi se vraća
na 100 kad ponašanje prestane. Bez kolapsa ne pada ispod 10. Potvrđen kolaps je odmah 0 i hitan slučaj.

Na svake dve sekunde koordinator zatvori **sekciju**: šta je viđeno, ocenu i stepen opasnosti. Za opasnu sekciju uz nju
ide i slika najrizičnijeg frejma iz keša. Sekcije idu telefonu uživo i serveru, koji ih čuva u Postgres-u (slike u S3
skladištu RustFS). Iz njih server posle vožnje pravi izveštaj: prosečnu ocenu dok su se kola kretala, grafik i opasne
trenutke sa slikama.
