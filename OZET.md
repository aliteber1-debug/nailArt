# Tirnak Tarayici Sistemi - Proje Ozeti

## Proje Nedir?

Bu proje, **yapay zeka destekli otomatik tirnak boyama sistemidir**. Raspberry Pi uzerinde calisan sistem, bir kamera ile elin fotografini ceker, yapay zeka modeli kullanarak tirnaklari tespit eder, her tirnak icin zigzag tarama yolu planlar ve 3 eksenli step motor sistemiyle tirnaklari fiziksel olarak boyar.

## Nasil Calisir?

Sistem uc asamali bir boru hatti (pipeline) ile calisir:

```
1. Homing       -> Motorlari baslangic noktasina gotur
2. Goruntu      -> Fotograf cek -> AI segmentasyon -> Yol planlama
3. Motor Tarama -> Koordinatlari yukle -> Tirnaklari tara/boya
```

### Adim Adim Akis

1. **Kamera Goruntusu Alma**: Raspberry Pi kamerasi ile 1920x1080 canli onizleme ve fotograf cekimi
2. **AI Tirnak Tespiti**: TensorFlow Lite modeli (0824.tflite) ile 512x512 patch'ler halinde tirnak segmentasyonu
3. **Kontur Filtreleme**: Tespit edilen alanlardan boyut kontrolu ile gecerli tirnaklarin secilmesi (50-500 mm2)
4. **Yol Planlama**: Her tirnak icin adaptif zigzag raster tarama yolu olusturma (0.5mm nokta araligi, 1.0mm serit genisligi)
5. **Koordinat Donusumu**: Piksel koordinatlarindan motor koordinatlarina donusum (kamera kalibrasyonu + ofset)
6. **Motor Hareketi**: X,Y eksenleri ile hedefe gitme, Z ekseni ile FSR basinc sensorune kadar inis
7. **Otomatik Temizlik**: Basarili tarama sonrasi gecici dosyalarin silinmesi

## Teknoloji Yigini

| Katman | Teknoloji |
|--------|-----------|
| Dil | Python 3 |
| Platform | Raspberry Pi (RPi.GPIO) |
| Yapay Zeka | TensorFlow Lite (tirnak segmentasyonu) |
| Goruntu Isleme | OpenCV, Pillow, NumPy, Picamera2 |
| Donanim | 3 eksenli step motor, FSR basinc sensoru (LM339), home switch'ler |
| Konfigrasyon | JSON (kamera kalibrasyonu), Python modulu (shared_config.py) |

## Dosya Yapisi

```
nailArt/
  master_controller.py          # Ana giris noktasi - orkestrator (333 satir)
  imaging_pipeline.py           # Goruntu isleme + AI pipeline (894 satir)
  motor_controller.py           # Motor + sensor kontrol (849 satir)
  shared_config.py              # Merkezi konfigurasyon (210 satir)
  offset_olcum_v2.py            # Kamera-motor ofset olcum araci (v2)
  ofset_olcum.py                # Kamera-motor ofset olcum araci (v1)
  switchKontrol.py              # GPIO test yardimci araci
  0824.tflite                   # TFLite tirnak segmentasyon modeli
  camera_calibration_*.json     # Kamera kalibrasyon verileri
  ozet.pdf                      # Proje dokumantasyonu (PDF)
  scan_outputs/                 # Cikti dosyalari (otomatik olusturulur)
  temp_images/                  # Gecici goruntuler (otomatik olusturulur)
```

## Hizli Baslangic

```bash
# Tam otomatik tarama
python3 master_controller.py
# Menuден "1" secin

# Sadece goruntu isleme (Phase 1)
python3 imaging_pipeline.py --save-coordinates

# Sadece motor tarama (Phase 2)
python3 motor_controller.py -f all_nails_path_*.txt --auto-scan

# Kalibrasyon
python3 offset_olcum_v2.py
```

## Donanim Gereksinimleri

- Raspberry Pi (GPIO destekli)
- Raspberry Pi Kamera Modulu
- 3 eksenli step motor sistemi (X, Y, Z)
- FSR basinc sensoru + LM339 komparator
- X ve Y eksenleri icin home switch'ler

## Toplam Kod Boyutu

~3.100 satir Python kodu (5 ana modul + 1 yardimci)

---
Son Guncelleme: 2026-02-08
Versiyon: 1.1
