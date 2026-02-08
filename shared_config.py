#!/usr/bin/env python3
"""
Tırnak Tarayıcı Sistemi - Ortak Konfigürasyon
FSR Basınç Sensörü Entegrasyonu ile Güncellenmiş Versiyon
"""
import os

# Dosya Yolları
PATHS = {
    'MODEL_PATH': './0824.tflite',
    'CALIBRATION_FILE': 'camera_calibration_20250522_180213.json',
    'OUTPUT_DIR': 'scan_outputs',
    'TEMP_DIR': 'temp_images'
}

# Kamera Ayarları
CAMERA_CONFIG = {
    'IMAGE_SIZE': (1920, 1080),
    'CAMERA_CONTROLS': {
        "AfMode": "Continuous",
        "AeEnable": True,
        "AwbEnable": True,
        "AnalogueGain": 4.0,
        "ExposureTime": 66000,
        "Brightness": 0.1,
        "Contrast": 1.3,
        "Saturation": 1.2,
        "Sharpness": 3.0,
        "NoiseReductionMode": 3
    }
}

# Path Planning Ayarları
PATH_CONFIG = {
    'POINT_SPACING': 0.5,  # mm - nokta aralığı
    'STRIP_WIDTH': 1.0,  # mm - şerit genişliği
    'MIN_NAIL_AREA_MM2': 50,  # Minimum tırnak alanı (mm²)
    'MAX_NAIL_AREA_MM2': 500,  # Maksimum tırnak alanı (mm²)
    'MIN_NAIL_AREA_PX': 100,  # Minimum tırnak alanı (piksel²)
    'OVERLAP_FACTOR': 0.85,  # Strip overlap faktörü (%15 overlap)
}

# Koordinat Sistemi Tanımları
COORDINATE_SYSTEM = {
    # Görüntü koordinat sistemi
    'IMAGE_ORIGIN_FROM_RIGHT': 50,  # Sağ kenardan origin mesafesi (px)
    'IMAGE_ORIGIN_FROM_BOTTOM': 50,  # Alt kenardan origin mesafesi (px)

    # Motor koordinat sistemi
    # Motor home pozisyonu = fiziksel (0,0) noktası
    # Motor X+ = Sağa hareket
    # Motor Y+ = İleri hareket (operatörden uzağa)

    # Görüntü-Motor dönüşüm parametreleri
    'IMAGE_TO_MOTOR_X_FLIP': False,  # X ekseni ters çevrilmemeli
    'IMAGE_TO_MOTOR_Y_FLIP': False,  # Y ekseni de ters çevrilmemeli
}

# Motor Ayarları
MOTOR_CONFIG = {
    # Pin Tanımlamaları
    'X_STEP_PIN': 17,
    'X_DIR_PIN': 22,
    'Y_STEP_PIN': 18,
    'Y_DIR_PIN': 23,
    'Z_STEP_PIN': 27,
    'Z_DIR_PIN': 24,
    'ENABLE_PIN': None,
    'X_SWITCH_PIN': 19,  # X ekseni home switch
    'Y_SWITCH_PIN': 20,  # Y ekseni home switch

    # Motor Parametreleri
    'SPEED': 800,  # X,Y adım/saniye
    'Z_AXIS_SPEED': 200,  # Z adım/saniye
    'MICROSTEP': 16,  # 1/16 mikro adım modu
    'PAUSE_BETWEEN_POINTS': 0.0,  # Noktalar arası bekleme
    'Z_RETRACT_DISTANCE': 5.0,  # Z geri çekme mesafesi (mm)
    'MAX_TRAVEL': 100.0,  # Maksimum hareket sınırı (mm)

    # Motor Adım Değerleri - 1/16 mikrostep için
    'X_STEPS_PER_MM': 80.0,  # X ekseni: 80 adım/mm
    'Y_STEPS_PER_MM': 80.0,  # Y ekseni: 80 adım/mm
    'Z_STEPS_PER_MM': 320.0,  # Z ekseni: 320 adım/mm

    # Çalışma Alanı (motor koordinatlarında)
    'MOTOR_START_OFFSET_Y': -36.0,  # Y başlangıç offset (mm)
    'X_AXIS_MIN': 0.0,  # X minimum (mm)
    'X_AXIS_MAX': 200.0,  # X maksimum (mm)
    'Y_AXIS_MIN': -36.0,  # Y minimum (mm)
    'Y_AXIS_MAX': 74.0,  # Y maksimum (mm)
    
    # Kamera-Motor Ofset Değerleri
    'OFFSET_X': 17.50,  # X ekseni ofset (mm)
    'OFFSET_Y': 2.50,   # Y ekseni ofset (mm)
    'OFFSET_Z': 0.0,    # Z ekseni ofset (mm)
}

# ============================================================
# FSR BASINÇ SENSÖRÜ AYARLARI (YENİ)
# ============================================================
FSR_CONFIG = {
    # Pin Tanımlaması
    # LM339 comparator çıkışı bu pine bağlanacak
    'SENSOR_PIN': 16,  # GPIO16 - Mevcut SWITCH_PIN ile aynı
    
    # Alternatif olarak farklı pin kullanmak isterseniz:
    # 'SENSOR_PIN': 17,  # GPIO17 (PDF'deki örnek)
    
    # Sensör Davranışı
    'ACTIVE_STATE': 'HIGH',  # Temas algılandığında HIGH sinyali
    'PULL_RESISTOR': 'NONE',  # Harici pull-up direnci kullanıldığı için
    
    # Debounce Ayarları (gürültü filtreleme)
    'DEBOUNCE_TIME_MS': 50,  # Milisaniye cinsinden debounce süresi
    'CONFIRMATION_READS': 3,  # Temas onayı için ardışık okuma sayısı
    'READ_INTERVAL_MS': 5,    # Okumalar arası bekleme (ms)
    
    # Güvenlik Ayarları
    'MAX_CONTACT_TIME_MS': 5000,  # Maksimum temas süresi (5 saniye)
    'MIN_RELEASE_TIME_MS': 100,   # Minimum bırakma süresi
    
    # Debug
    'ENABLE_LOGGING': True,  # Sensör okumalarını logla
}

# Eski SWITCH_PIN referansı için geriye uyumluluk
# (Mevcut kodun bozulmaması için)
MOTOR_CONFIG['SWITCH_PIN'] = FSR_CONFIG['SENSOR_PIN']

# AI Model Ayarları
AI_CONFIG = {
    'PATCH_SIZE': (512, 512),
    'STRIDE': (256, 256),
    'CONFIDENCE_THRESHOLD': 0.5,
}

# Sistem Ayarları
SYSTEM_CONFIG = {
    'ENABLE_AI_MODEL': True,  # False = Mock segmentation
    'ENABLE_VISUALIZATION': True,  # Sonuç grafiklerini göster
    'DEBUG_MODE': False,  # Debug mesajları
    'USE_FSR_SENSOR': True,  # FSR sensör kullanımı aktif
}


# Yardımcı Fonksiyonlar
def create_directories():
    """Gerekli klasörleri oluştur"""
    for path in [PATHS['OUTPUT_DIR'], PATHS['TEMP_DIR']]:
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"📁 Klasör oluşturuldu: {path}")


def validate_config():
    """Konfigürasyon dosyalarını kontrol et"""
    errors = []

    if SYSTEM_CONFIG['ENABLE_AI_MODEL'] and not os.path.exists(PATHS['MODEL_PATH']):
        errors.append(f"Model dosyası bulunamadı: {PATHS['MODEL_PATH']}")

    if not os.path.exists(PATHS['CALIBRATION_FILE']):
        errors.append(f"Kalibrasyon dosyası bulunamadı: {PATHS['CALIBRATION_FILE']}")

    return errors


def print_system_info():
    """Sistem bilgilerini yazdır"""
    print("🤖 TIRNAK TARAYICI SİSTEM BİLGİLERİ")
    print("=" * 50)
    print(f"📐 Motor Adım Değerleri (1/16 mikrostep):")
    print(f"   X Ekseni: {MOTOR_CONFIG['X_STEPS_PER_MM']} adım/mm")
    print(f"   Y Ekseni: {MOTOR_CONFIG['Y_STEPS_PER_MM']} adım/mm")
    print(f"   Z Ekseni: {MOTOR_CONFIG['Z_STEPS_PER_MM']} adım/mm")
    print(f"⚡ Motor Hızları:")
    print(f"   X,Y: {MOTOR_CONFIG['SPEED']} adım/s")
    print(f"   Z: {MOTOR_CONFIG['Z_AXIS_SPEED']} adım/s")
    print(f"📐 Çalışma Alanı (Motor Koordinatları):")
    print(f"   X: {MOTOR_CONFIG['X_AXIS_MIN']} - {MOTOR_CONFIG['X_AXIS_MAX']} mm")
    print(f"   Y: {MOTOR_CONFIG['Y_AXIS_MIN']} - {MOTOR_CONFIG['Y_AXIS_MAX']} mm")
    print(f"🎯 Koordinat Sistemi:")
    print(f"   Görüntü Origin: Sağdan {COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT']}px, Alttan {COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM']}px")
    print(f"   X Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']}")
    print(f"   Y Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']}")
    print(f"🔧 Kamera-Motor Ofset Değerleri:")
    print(f"   X Ofset: {MOTOR_CONFIG['OFFSET_X']:+.2f} mm")
    print(f"   Y Ofset: {MOTOR_CONFIG['OFFSET_Y']:+.2f} mm")
    
    # FSR Sensör Bilgileri
    print(f"\n🔴 FSR BASINÇ SENSÖRÜ:")
    print(f"   Durum: {'✅ Aktif' if SYSTEM_CONFIG['USE_FSR_SENSOR'] else '❌ Devre Dışı'}")
    print(f"   GPIO Pin: {FSR_CONFIG['SENSOR_PIN']}")
    print(f"   Aktif Durum: {FSR_CONFIG['ACTIVE_STATE']}")
    print(f"   Debounce: {FSR_CONFIG['DEBOUNCE_TIME_MS']} ms")
    print(f"   Onay Okuma: {FSR_CONFIG['CONFIRMATION_READS']} adet")


if __name__ == "__main__":
    create_directories()
    errors = validate_config()

    if errors:
        print("⚠️ Konfigürasyon hataları:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ Konfigürasyon geçerli")

    print_system_info()
