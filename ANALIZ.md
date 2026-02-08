# Tirnak Tarayici Sistemi - Detayli Teknik Analiz

## Icindekiler

1. [Sistem Mimarisi](#sistem-mimarisi)
2. [Modul Detaylari](#modul-detaylari)
3. [Koordinat Sistemi](#koordinat-sistemi)
4. [Donanim Entegrasyonu](#donanim-entegrasyonu)
5. [Veri Akisi](#veri-akisi)
6. [Konfigurasyon Sistemi](#konfigurasyon-sistemi)
7. [Calisma Senaryolari](#calisma-senaryolari)
8. [Guvenlik ve Hata Yonetimi](#guvenlik-ve-hata-yonetimi)

---

## Sistem Mimarisi

Proje, moduler bir yapiyla tasarlanmistir. Her modul belirli bir sorumluluk alanina sahiptir:

```
master_controller.py (Orkestrator)
        |
        +---> imaging_pipeline.py (Goruntu + AI)
        |           |
        |           +---> shared_config.py (Ayarlar)
        |           +---> 0824.tflite (AI Model)
        |           +---> camera_calibration_*.json
        |
        +---> motor_controller.py (Motor + Sensor)
                    |
                    +---> shared_config.py (Ayarlar)
```

**Temel Tasarim Kararlari:**
- Imaging pipeline, subprocess olarak calistirilarak bellek izolasyonu saglanir
- Motor controller, dogrudan import edilerek calistirilir
- Tum konfigurasyonlar tek bir merkezi dosyada (`shared_config.py`) tutulur
- Her phase sonrasi `gc.collect()` ile bellek temizligi yapilir

---

## Modul Detaylari

### 1. master_controller.py - Ana Koordinator (333 satir)

**Sinif:** `NailScannerMaster`

Ana orkestrator modulu. Kullaniciya interaktif bir menu sunar ve tum alt sistemleri koordine eder.

**Menu Secenekleri:**
1. Tam Otomatik Tarama (Homing + Imaging + Motor)
2. Sadece Homing
3. Sadece Goruntu Isleme (Phase 1)
4. Sadece Motor Tarama (Phase 2)
5. Koordinat Donusum Testi
6. Sistem Bilgileri
7. Cikis

**Ana Metodlar:**

| Metod | Aciklama |
|-------|----------|
| `run_homing_procedure()` | X ve Y eksenlerini home pozisyonuna goturur |
| `run_imaging_pipeline()` | Goruntu isleme pipeline'ini calistirir, koordinat dosyasi dondurur |
| `run_motor_controller(file)` | Koordinat dosyasindan motor taramasi baslatir |
| `run_full_pipeline()` | Homing + Imaging + Motor sirasyla calistirir |
| `show_available_coordinates()` | Mevcut koordinat dosyalarini listeler |
| `test_coordinate_conversion()` | Piksel -> motor koordinat donusumunu test eder |

**Ozellikler:**
- Phase 1 (Imaging) ve Phase 2 (Motor) koordinasyonu
- Subprocess ile bellek izolasyonu
- Otomatik dosya temizleme (basarili tarama sonrasi)
- Sistem gereksinim kontrolleri (dosya varliklari)

---

### 2. imaging_pipeline.py - Goruntu Isleme Pipeline (894 satir)

**Sinif:** `NailImagingPipeline`

Kamera goruntusu alma, AI tabanli tirnak segmentasyonu, yol planlama ve koordinat donusumu islemlerini yurutur.

**Pipeline Adimlari:**

```
Kamera Kurulumu (Picamera2)
    |
Canli Onizleme + Fotograf Cekme (Q tusu ile)
    |
AI Segmentasyon (TFLite 512x512 patch'ler, 256 stride)
    |
Kontur Filtreleme (50-500 mm2 boyut kontrolu)
    |
Zigzag Raster Yol Planlama (adaptif)
    |
Koordinat Donusumu (piksel -> mm, anizotropik)
    |
Dosya Kaydetme (TXT koordinat + PNG gorsel)
```

**Ana Metodlar:**

| Metod | Aciklama |
|-------|----------|
| `load_calibration()` | Kamera kalibrasyon verilerini JSON'dan yukler |
| `setup_camera()` | Picamera2'yi shared_config ayarlariyla baslatir |
| `capture_image_interactive()` | Canli onizleme gosterir, Q tusuyla fotograf cekilir |
| `run_ai_segmentation()` | TFLite modeli ile patch-wise tirnak segmentasyonu |
| `create_mock_segmentation()` | AI model yoksa test amacli eliptik tirnak olusturur |
| `filter_nail_contours()` | Boyut ve alan filtrelemesi ile gecerli tirnaklari secer |
| `create_raster_scan_path()` | Her tirnak icin zigzag tarama path'i olusturur |
| `convert_to_motor_coordinates()` | Kalibrasyon matrisi ile piksel -> mm donusumu |
| `generate_paths_for_all_nails()` | Tum tirnaklar icin koordinat uretimi |
| `save_coordinates()` | TXT formatinda dosya kaydetme |
| `visualize_results()` | Matplotlib ile 2x2 subplot sonuc grafigi |
| `run_full_pipeline()` | Tum adimlari sirali olarak calistirir |

**Cikti Dosyalari:**
- `all_nails_path_YYYYMMDD_HHMMSS.txt` - Tum tirnaklarin birlesik koordinatlari
- `nail_N_path_YYYYMMDD_HHMMSS.txt` - Bireysel tirnak koordinatlari
- `multi_nail_results_YYYYMMDD_HHMMSS.png` - Gorsellestirme sonucu

---

### 3. motor_controller.py - Motor Kontrol Sistemi (849 satir)

**Siniflar:** `NailScannerController`, `FSRPressureSensor`, `Position`, `ScanPoint`

Step motor kontrolu, FSR basinc sensoru entegrasyonu, homing islemleri ve tarama yurutmesi.

**Veri Yapilari:**

```python
@dataclass
class Position:
    x: float = 0.0    # X pozisyonu (mm)
    y: float = 0.0    # Y pozisyonu (mm)
    z: float = 0.0    # Z pozisyonu (mm)

@dataclass
class ScanPoint:
    x: float           # X koordinati (mm)
    y: float           # Y koordinati (mm)
    nail_id: int = 0   # Tirnak ID'si
    index: int = 0     # Nokta sira numarasi
```

**NailScannerController - Ana Metodlar:**

| Metod | Aciklama |
|-------|----------|
| `setup_gpio()` | 3 eksen + switch pin konfigurasyonu |
| `load_coordinates_from_file()` | TXT dosyasindan koordinat okuma |
| `mm_to_steps()` | mm -> motor adim donusumu |
| `move_motor()` | Tekli motor hareket kontrolu |
| `move_to_position()` | X,Y pozisyonlama |
| `perform_z_touch()` | Z ekseni FSR temasina kadar inme |
| `retract_z_axis()` | Z eksenini guvenli geri cekme (5mm) |
| `run_full_scan()` | Tum koordinatlari sirali tarama |
| `home_x_axis()` | X ekseni home switch'e gitme |
| `home_y_axis()` | Y ekseni home switch'e gitme |
| `home_all_axes()` | Tum eksenleri (0,0,0)'a dondurme |
| `cleanup()` | GPIO temizleme ve guvenli kapatma |

**FSRPressureSensor - Basinc Sensoru:**

| Metod | Aciklama |
|-------|----------|
| `read_raw()` | Ham GPIO okumasini dondurur |
| `read_debounced()` | Gurultu filtrelenimis okuma (50ms debounce) |
| `read_confirmed()` | Coklu ornek ile onaylanmis okuma (3 okuma) |
| `wait_for_contact()` | Basinc algilayana kadar bekler |
| `wait_for_release()` | Basinc kalkaana kadar bekler |

**Tarama Sureci:**
1. **Koordinat Yukleme** -> TXT dosyasindan parse etme
2. **Pozisyon Hareket** -> X,Y hedef koordinatina gitme
3. **Z Ekseni Tarama** -> FSR tetiklenene kadar inme
4. **Veri Toplama** -> 0.1s bekleme (simulasyon)
5. **Guvenli Geri Cekme** -> Z eksenini 5mm yukari cekme
6. **Sonraki Nokta** -> Siradaki koordinata gecme

---

### 4. shared_config.py - Merkezi Konfigurasyon (210 satir)

Tum sistem ayarlarini tek bir dosyada toplayan merkezi konfigurasyon modulu.

**Konfigurasyon Bloklari:**

```python
PATHS          # Dosya yollari (model, kalibrasyon, cikti, gecici)
CAMERA_CONFIG  # Kamera ayarlari (1920x1080, pozlama, parlaklik, vb.)
PATH_CONFIG    # Yol planlama (nokta araligi, serit genisligi, tirnak boyutlari)
COORDINATE_SYSTEM  # Koordinat sistemi tanimlari
MOTOR_CONFIG   # Motor pin ve parametre ayarlari
FSR_CONFIG     # FSR basinc sensoru ayarlari
AI_CONFIG      # Yapay zeka model ayarlari (patch boyutu, stride, esik degeri)
SYSTEM_CONFIG  # Sistem davranis ayarlari (AI, gorsellestirme, debug)
```

**Yardimci Fonksiyonlar:**

| Fonksiyon | Aciklama |
|-----------|----------|
| `create_directories()` | Gerekli klasorleri (scan_outputs, temp_images) olusturur |
| `validate_config()` | Model ve kalibrasyon dosyalarinin varligini kontrol eder |
| `print_system_info()` | Tum sistem parametrelerini ekrana yazdirir |

---

### 5. offset_olcum_v2.py / ofset_olcum.py - Kalibrasyon Araclari

Motor sifir noktasi ile kamera origin'ini hizalamak icin kullanilan interaktif kalibrasyon araclari.

**Tus Kontrolleri:**
- **W/S**: Y ekseni hareket (+/-)
- **A/D**: X ekseni hareket (+/-)
- **R/F**: Z ekseni hareket (yukari/asagi)
- **+/-**: Adim boyutu ayarlama (1-100)
- **H**: Home pozisyonuna gitme (0,0,0)
- **T**: Pozisyon sayacini sifirlama
- **Q**: Cikis

**Gorsel Ozellikler:**
- Kirmizi capraz: Kamera origin noktasi
- Grid cizgileri: 50 piksel aralikli referans
- Pozisyon bilgisi: X,Y,Z motor koordinatlari (real-time)
- Switch durumu: Z limit switch gosterimi

---

## Koordinat Sistemi

### Goruntu Koordinatlari
- **Origin**: Sag kenardan 50px, alt kenardan 50px
- **X+**: Sola dogru (goruntude)
- **Y+**: Yukari dogru (goruntude)

### Motor Koordinatlari
- **Origin**: Home pozisyonu (0, 0)
- **X+**: Saga hareket
- **Y+**: Ileri hareket (operatordan uzaga)
- **Calisma Alani**: X: [0 - 200mm], Y: [-36 - 74mm]

### Donusum Parametreleri
- **Kamera-Motor Ofset**: X=17.50mm, Y=2.50mm, Z=0mm
- **Piksel-mm Donusumu**: ~9.44 px/mm (X ve Y eksenleri icin farkli - anizotropik)
- **X Flip**: Devre disi (duzeltildi)
- **Y Flip**: Devre disi

---

## Donanim Entegrasyonu

### Step Motor Sistemi

| Parametre | X Ekseni | Y Ekseni | Z Ekseni |
|-----------|----------|----------|----------|
| Step Pin | GPIO 17 | GPIO 18 | GPIO 27 |
| Dir Pin | GPIO 22 | GPIO 23 | GPIO 24 |
| Adim/mm | 80 | 80 | 320 |
| Hiz (adim/s) | 800 | 800 | 200 |
| Home Switch | GPIO 19 | GPIO 20 | - |

**Mikrostep Modu:** 1/16 mikro adim

### FSR Basinc Sensoru

| Parametre | Deger |
|-----------|-------|
| GPIO Pin | 16 |
| Aktif Durum | HIGH (temas algilandginda) |
| Debounce | 50ms |
| Onay Okumalari | 3 adet |
| Maks. Temas Suresi | 5 saniye |
| Harici Pull-up | 10K Ohm |
| Komparator | LM339 |

### Kamera

| Parametre | Deger |
|-----------|-------|
| Cozunurluk | 1920x1080 (Full HD) |
| Pozlama Suresi | 66000 |
| Analog Kazanc | 4.0 |
| Parlaklik | 0.1 |
| Kontrast | 1.3 |
| Netlik | 3.0 |
| Otomatik Odak | Surekli (Continuous) |

---

## Veri Akisi

```
Kamera Goruntusu (1920x1080)
    |
AI Segmentasyon (512x512 patch'ler, 256 stride)
    |
Kontur Filtreleme (50-500 mm2 boyut)
    |
Path Planning (zigzag raster scan)
    |
Koordinat Donusumu (piksel -> mm)
    |
Dosya Kaydetme (TXT + PNG)
    |
Motor Yukleme (TXT parse)
    |
3D Tarama (X,Y,Z hareket)
    |
Otomatik Temizlik (dosya silme)
```

### Koordinat Dosya Formati

```
# Tirnak Tarayici Koordinat Dosyasi
# Tarih: 2025-05-22 18:00:00
# Toplam Tirnak: 5
# Toplam Nokta: 1250
# x(mm) y(mm) nail_id
10.50 5.25 1
10.75 5.25 1
11.00 5.25 1
...
```

---

## Konfigurasyon Sistemi

### Gelistirme ve Test Ayarlari

AI modeli olmadan test etmek icin:
```python
SYSTEM_CONFIG['ENABLE_AI_MODEL'] = False      # Mock segmentasyon kullanir
SYSTEM_CONFIG['ENABLE_VISUALIZATION'] = False  # Grafik gosterimini kapatir
PATH_CONFIG['POINT_SPACING'] = 2.0            # Daha seyrek nokta (hizli test)
```

### Produksiyon Ayarlari

```python
SYSTEM_CONFIG['ENABLE_AI_MODEL'] = True        # Gercek AI modeli
SYSTEM_CONFIG['USE_FSR_SENSOR'] = True         # FSR sensoru aktif
SYSTEM_CONFIG['ENABLE_VISUALIZATION'] = True   # Sonuc grafikleri
```

---

## Calisma Senaryolari

### Senaryo 1: Tam Otomatik Tarama

```bash
python3 master_controller.py
# Menuden "1" sec
```

**Akis:**
```
Master Controller
    |
    +-> Homing (X ve Y eksenlerini sifirla)
    |
    +-> Imaging Pipeline (fotograf + AI + yol planlama)
    |       |
    |       +-> Koordinat dosyasi olustur (all_nails_path_*.txt)
    |
    +-> Motor Controller (koordinatlari yukle ve tara)
    |
    +-> Basarili tarama sonrasi dosyalari sil
```

### Senaryo 2: Manuel Iki Asama

```bash
# Phase 1: Goruntu isleme
python3 imaging_pipeline.py --save-coordinates

# Phase 2: Motor tarama
python3 motor_controller.py -f all_nails_path_20250522_180000.txt --auto-scan
```

### Senaryo 3: Kalibrasyon

```bash
python3 offset_olcum_v2.py
# W,A,S,D,R,F tuslariyla manuel hizalama
# Motor origin -> kamera origin hizalama
```

### Senaryo 4: Sorun Giderme

```bash
# Modul kontrolleri
python3 master_controller.py  # Menuden "6. Sistem Bilgileri" sec

# Konfigurasyon testi
python3 shared_config.py

# Manuel motor testi
python3 motor_controller.py   # Menu modu
```

---

## Guvenlik ve Hata Yonetimi

### Guvenlik Ozellikleri

- **Z ekseni limit switch korumasi**: Z ekseni, switch tetiklenene kadar iner
- **FSR basinc sensoru**: Temas algilandiginda hareket durur
- **Hareket sinir kontrolleri**: Motor calisma alani disina cikmaz (X: 0-200mm, Y: -36-74mm)
- **Acil durdurma**: Ctrl+C ile program guvenli sekilde kapanir
- **GPIO temizleme garantisi**: `finally` bloklari ile GPIO her zaman temizlenir
- **Motor surucu durumu kontrolu**: Enable pin yonetimi
- **Maksimum temas suresi**: FSR sensorde 5 saniye siniri

### Bellek Yonetimi

- Imaging pipeline subprocess olarak calisir (bellek izolasyonu)
- Her phase sonrasi `gc.collect()` cagrilir
- Basarisiz islemler sonrasi dosya temizligi yapilir

### Dosya Yonetimi

- Timestamp bazli dosya isimlendirme (cakisma onleme)
- Basarili tarama sonrasi otomatik temizlik
- Hata durumunda dosya korunmasi (debug icin)
- Ilgili dosyalarin grup halinde silinmesi

---

Son Guncelleme: 2026-02-08
Versiyon: 1.1
