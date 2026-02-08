#!/usr/bin/env python3
"""
Tırnak Tarayıcı Motor Kontrol Modülü
FSR Basınç Sensörü Entegrasyonu ile Güncellenmiş Versiyon

Değişiklikler:
- FSR sensör sınıfı eklendi
- Debounce ve güvenilir okuma mekanizması
- Ayarlanabilir hassasiyet desteği
"""

import RPi.GPIO as GPIO
import time
import os
import sys
from dataclasses import dataclass
from typing import List, Optional
import argparse

# Ortak konfigürasyonu import et
try:
    from shared_config import *
except ImportError as e:
    print(f"❌ shared_config import hatası: {e}")
    sys.exit(1)


@dataclass
class ScanPoint:
    x: float  # mm cinsinden
    y: float  # mm cinsinden
    nail_id: int = 0
    index: int = 0


class FSRPressureSensor:
    """
    FSR Basınç Sensörü Sınıfı
    
    LM339 comparator ile kullanılan FSR sensörü okur.
    Debounce ve güvenilir okuma mekanizması içerir.
    """
    
    def __init__(self, pin: int = None):
        """
        FSR sensörü başlat
        
        Args:
            pin: GPIO pin numarası (None ise config'den alınır)
        """
        self.pin = pin or FSR_CONFIG['SENSOR_PIN']
        self.active_state = GPIO.HIGH if FSR_CONFIG['ACTIVE_STATE'] == 'HIGH' else GPIO.LOW
        self.inactive_state = GPIO.LOW if self.active_state == GPIO.HIGH else GPIO.HIGH
        
        self.debounce_time = FSR_CONFIG['DEBOUNCE_TIME_MS'] / 1000.0  # saniyeye çevir
        self.confirmation_reads = FSR_CONFIG['CONFIRMATION_READS']
        self.read_interval = FSR_CONFIG['READ_INTERVAL_MS'] / 1000.0
        self.max_contact_time = FSR_CONFIG['MAX_CONTACT_TIME_MS'] / 1000.0
        
        self.logging_enabled = FSR_CONFIG.get('ENABLE_LOGGING', False)
        self.last_state = None
        self.last_change_time = time.time()
        
        print(f"🔴 FSR Sensör başlatıldı:")
        print(f"   Pin: GPIO{self.pin}")
        print(f"   Aktif durum: {'HIGH' if self.active_state == GPIO.HIGH else 'LOW'}")
        print(f"   Debounce: {FSR_CONFIG['DEBOUNCE_TIME_MS']}ms")
    
    def setup(self):
        """GPIO pinini yapılandır"""
        # Pull resistor ayarı
        pull = FSR_CONFIG.get('PULL_RESISTOR', 'NONE')
        
        if pull == 'UP':
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        elif pull == 'DOWN':
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        else:
            # Harici pull-up kullanılıyor (LM339 devresinde 10kΩ)
            GPIO.setup(self.pin, GPIO.IN)
        
        if self.logging_enabled:
            print(f"   ✅ GPIO{self.pin} yapılandırıldı")
    
    def read_raw(self) -> bool:
        """
        Ham sensör değerini oku
        
        Returns:
            True: Temas algılandı, False: Temas yok
        """
        return GPIO.input(self.pin) == self.active_state
    
    def read_debounced(self) -> bool:
        """
        Debounce uygulanmış sensör okuma
        
        Returns:
            True: Kararlı temas algılandı, False: Temas yok
        """
        current_state = self.read_raw()
        current_time = time.time()
        
        # Durum değişikliği kontrolü
        if current_state != self.last_state:
            self.last_state = current_state
            self.last_change_time = current_time
            return False  # Debounce süresi dolmadı
        
        # Debounce süresi kontrolü
        if (current_time - self.last_change_time) >= self.debounce_time:
            return current_state
        
        return False
    
    def read_confirmed(self) -> bool:
        """
        Onaylı sensör okuma (birden fazla ardışık okuma)
        
        Returns:
            True: Güvenilir temas algılandı, False: Temas yok
        """
        positive_reads = 0
        
        for _ in range(self.confirmation_reads):
            if self.read_raw():
                positive_reads += 1
            time.sleep(self.read_interval)
        
        # Tüm okumaların çoğunluğu pozitif olmalı
        threshold = self.confirmation_reads // 2 + 1
        result = positive_reads >= threshold
        
        if self.logging_enabled and result:
            print(f"   📊 Sensör onayı: {positive_reads}/{self.confirmation_reads} pozitif")
        
        return result
    
    def wait_for_contact(self, timeout: float = None) -> bool:
        """
        Temas algılanana kadar bekle
        
        Args:
            timeout: Maksimum bekleme süresi (saniye)
        
        Returns:
            True: Temas algılandı, False: Timeout
        """
        timeout = timeout or self.max_contact_time
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            if self.read_confirmed():
                return True
            time.sleep(0.001)  # 1ms bekleme
        
        return False
    
    def wait_for_release(self, timeout: float = None) -> bool:
        """
        Temas bırakılana kadar bekle
        
        Args:
            timeout: Maksimum bekleme süresi (saniye)
        
        Returns:
            True: Bırakıldı, False: Timeout
        """
        timeout = timeout or self.max_contact_time
        min_release = FSR_CONFIG['MIN_RELEASE_TIME_MS'] / 1000.0
        start_time = time.time()
        release_start = None
        
        while (time.time() - start_time) < timeout:
            if not self.read_raw():
                if release_start is None:
                    release_start = time.time()
                elif (time.time() - release_start) >= min_release:
                    return True
            else:
                release_start = None
            time.sleep(0.001)
        
        return False
    
    def get_status(self) -> dict:
        """Sensör durumunu döndür"""
        return {
            'pin': self.pin,
            'raw_value': self.read_raw(),
            'debounced_value': self.read_debounced(),
            'active_state': 'HIGH' if self.active_state == GPIO.HIGH else 'LOW'
        }


class NailScannerController:
    def __init__(self, auto_homing=True):
        print("🤖 Tırnak Tarayıcı Motor Kontrol Sistemi")
        print("🔴 FSR Basınç Sensörü Entegreli Versiyon")
        print("=" * 50)

        # Motor pozisyonu (mm cinsinden)
        self.current_pos = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self.scan_points: List[ScanPoint] = []
        self.is_scanning = False
        self.z_is_down = False
        
        # FSR Sensör
        self.fsr_sensor = None
        if SYSTEM_CONFIG.get('USE_FSR_SENSOR', True):
            self.fsr_sensor = FSRPressureSensor()

        # GPIO setup
        self.setup_gpio()

        print(f"\n📐 Motor ayarları:")
        print(f"   X: {MOTOR_CONFIG['X_STEPS_PER_MM']} adım/mm")
        print(f"   Y: {MOTOR_CONFIG['Y_STEPS_PER_MM']} adım/mm")
        print(f"   Z: {MOTOR_CONFIG['Z_STEPS_PER_MM']} adım/mm")
        print(f"📐 Çalışma alanı:")
        print(f"   X: {MOTOR_CONFIG['X_AXIS_MIN']:.1f} - {MOTOR_CONFIG['X_AXIS_MAX']:.1f} mm")
        print(f"   Y: {MOTOR_CONFIG['Y_AXIS_MIN']:.1f} - {MOTOR_CONFIG['Y_AXIS_MAX']:.1f} mm")

        # Otomatik homing
        if auto_homing:
            print("\n🚀 Otomatik homing başlıyor...")
            self.initial_homing()

    def setup_gpio(self):
        """GPIO pinlerini yapılandır"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Output pinleri (motor step ve direction)
        output_pins = [
            MOTOR_CONFIG['X_STEP_PIN'], MOTOR_CONFIG['X_DIR_PIN'],
            MOTOR_CONFIG['Y_STEP_PIN'], MOTOR_CONFIG['Y_DIR_PIN'],
            MOTOR_CONFIG['Z_STEP_PIN'], MOTOR_CONFIG['Z_DIR_PIN']
        ]

        if MOTOR_CONFIG['ENABLE_PIN'] is not None:
            output_pins.append(MOTOR_CONFIG['ENABLE_PIN'])

        for pin in output_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # X ve Y home switch'ler (aktif LOW - normalde HIGH)
        for pin in [MOTOR_CONFIG['X_SWITCH_PIN'], MOTOR_CONFIG['Y_SWITCH_PIN']]:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # FSR Sensör kurulumu
        if self.fsr_sensor:
            self.fsr_sensor.setup()
            print("✅ FSR basınç sensörü aktif")
        else:
            # Eski switch modu (geriye uyumluluk)
            GPIO.setup(MOTOR_CONFIG['SWITCH_PIN'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            print("⚠️ Klasik switch modu aktif")

        # Motor sürücüyü etkinleştir
        if MOTOR_CONFIG['ENABLE_PIN'] is not None:
            GPIO.output(MOTOR_CONFIG['ENABLE_PIN'], GPIO.LOW)

    def initial_homing(self):
        """Sistem başlangıcında X ve Y eksenlerini home pozisyonuna götür"""
        print("🏠 Başlangıç homing işlemi - X ve Y eksenleri")

        self.home_x_axis()
        time.sleep(0.5)

        self.home_y_axis()
        time.sleep(0.5)

        print("✅ Başlangıç homing tamamlandı!")

    def move_motor_steps(self, axis, steps, direction):
        """Motor adım adım hareket ettir"""
        axis = axis.upper()

        if axis == 'X':
            step_pin, dir_pin = MOTOR_CONFIG['X_STEP_PIN'], MOTOR_CONFIG['X_DIR_PIN']
            speed = MOTOR_CONFIG['SPEED']
            steps_per_mm = MOTOR_CONFIG['X_STEPS_PER_MM']
        elif axis == 'Y':
            step_pin, dir_pin = MOTOR_CONFIG['Y_STEP_PIN'], MOTOR_CONFIG['Y_DIR_PIN']
            speed = MOTOR_CONFIG['SPEED']
            steps_per_mm = MOTOR_CONFIG['Y_STEPS_PER_MM']
        elif axis == 'Z':
            step_pin, dir_pin = MOTOR_CONFIG['Z_STEP_PIN'], MOTOR_CONFIG['Z_DIR_PIN']
            speed = MOTOR_CONFIG['Z_AXIS_SPEED']
            steps_per_mm = MOTOR_CONFIG['Z_STEPS_PER_MM']
        else:
            return False

        # Yön ayarla
        if axis == 'Z':
            GPIO.output(dir_pin, GPIO.HIGH if direction > 0 else GPIO.LOW)
        else:
            GPIO.output(dir_pin, GPIO.LOW if direction > 0 else GPIO.HIGH)

        # Hareket
        step_delay = 1 / (speed * 2)
        steps_completed = 0

        for i in range(steps):
            # Z aşağı hareket ederken sensör kontrolü
            if axis == 'Z' and direction > 0:
                if self._check_touch_sensor():
                    break

            GPIO.output(step_pin, GPIO.HIGH)
            time.sleep(step_delay)
            GPIO.output(step_pin, GPIO.LOW)
            time.sleep(step_delay)
            steps_completed += 1

        # Pozisyonu güncelle (mm cinsinden)
        distance_mm = (steps_completed / steps_per_mm) * direction
        self.current_pos[axis.lower()] += distance_mm

        return steps_completed > 0

    def _check_touch_sensor(self) -> bool:
        """
        Temas sensörünü kontrol et
        
        FSR sensör aktifse onu, değilse eski switch'i kullanır.
        
        Returns:
            True: Temas algılandı
        """
        if self.fsr_sensor:
            return self.fsr_sensor.read_raw()
        else:
            # Eski switch modu
            return GPIO.input(MOTOR_CONFIG['SWITCH_PIN']) == GPIO.HIGH

    def home_x_axis(self):
        """X eksenini home pozisyonuna götür"""
        print("🏠 X ekseni home pozisyonuna gidiyor...")

        step_pin = MOTOR_CONFIG['X_STEP_PIN']
        dir_pin = MOTOR_CONFIG['X_DIR_PIN']
        switch_pin = MOTOR_CONFIG['X_SWITCH_PIN']
        speed = MOTOR_CONFIG['SPEED']

        # Negatif yön (home'a doğru)
        GPIO.output(dir_pin, GPIO.HIGH)

        step_delay = 1 / (speed * 2)
        steps_taken = 0

        # Switch sinyali gelene kadar hareket et
        while GPIO.input(switch_pin) == GPIO.HIGH:
            GPIO.output(step_pin, GPIO.HIGH)
            time.sleep(step_delay)
            GPIO.output(step_pin, GPIO.LOW)
            time.sleep(step_delay)
            steps_taken += 1

        # X pozisyonunu sıfırla
        self.current_pos['x'] = 0.0
        print(f"✅ X ekseni home'da ({steps_taken} adım)")

    def home_y_axis(self):
        """Y eksenini home pozisyonuna götür"""
        print("🏠 Y ekseni home pozisyonuna gidiyor...")

        step_pin = MOTOR_CONFIG['Y_STEP_PIN']
        dir_pin = MOTOR_CONFIG['Y_DIR_PIN']
        switch_pin = MOTOR_CONFIG['Y_SWITCH_PIN']
        speed = MOTOR_CONFIG['SPEED']

        # Negatif yön (home'a doğru)
        GPIO.output(dir_pin, GPIO.HIGH)

        step_delay = 1 / (speed * 2)
        steps_taken = 0

        # Switch sinyali gelene kadar hareket et
        while GPIO.input(switch_pin) == GPIO.HIGH:
            GPIO.output(step_pin, GPIO.HIGH)
            time.sleep(step_delay)
            GPIO.output(step_pin, GPIO.LOW)
            time.sleep(step_delay)
            steps_taken += 1

        # Y pozisyonunu sıfırla (home = Y minimum)
        self.current_pos['y'] = MOTOR_CONFIG['Y_AXIS_MIN']
        print(f"✅ Y ekseni home'da ({steps_taken} adım, Y={self.current_pos['y']:.1f} mm)")

    def move_to_position(self, target_x: float, target_y: float) -> bool:
        """X ve Y eksenlerini hedef pozisyona hareket ettir (mm cinsinden)"""
        # Çalışma alanı kontrolü
        if not (MOTOR_CONFIG['X_AXIS_MIN'] <= target_x <= MOTOR_CONFIG['X_AXIS_MAX']):
            if SYSTEM_CONFIG['DEBUG_MODE']:
                print(f"   ⚠️ X hedefi sınır dışı: {target_x:.2f} mm")
            return False

        if not (MOTOR_CONFIG['Y_AXIS_MIN'] <= target_y <= MOTOR_CONFIG['Y_AXIS_MAX']):
            if SYSTEM_CONFIG['DEBUG_MODE']:
                print(f"   ⚠️ Y hedefi sınır dışı: {target_y:.2f} mm")
            return False

        dx = target_x - self.current_pos['x']
        dy = target_y - self.current_pos['y']

        # X ekseni hareketi
        if abs(dx) > 0.01:  # 0.01mm hassasiyet
            x_steps = int(abs(dx) * MOTOR_CONFIG['X_STEPS_PER_MM'])
            direction = 1 if dx > 0 else -1
            if not self.move_motor_steps('X', x_steps, direction):
                return False

        # Y ekseni hareketi
        if abs(dy) > 0.01:  # 0.01mm hassasiyet
            y_steps = int(abs(dy) * MOTOR_CONFIG['Y_STEPS_PER_MM'])
            direction = 1 if dy > 0 else -1
            if not self.move_motor_steps('Y', y_steps, direction):
                return False

        return True

    def move_to_position_safe(self, target_x: float, target_y: float) -> bool:
        """Tırnak geçişi için güvenli hareket: önce Y, sonra X (parmağa çarpmayı önle)"""
        # Çalışma alanı kontrolü
        if not (MOTOR_CONFIG['X_AXIS_MIN'] <= target_x <= MOTOR_CONFIG['X_AXIS_MAX']):
            if SYSTEM_CONFIG['DEBUG_MODE']:
                print(f"   ⚠️ X hedefi sınır dışı: {target_x:.2f} mm")
            return False

        if not (MOTOR_CONFIG['Y_AXIS_MIN'] <= target_y <= MOTOR_CONFIG['Y_AXIS_MAX']):
            if SYSTEM_CONFIG['DEBUG_MODE']:
                print(f"   ⚠️ Y hedefi sınır dışı: {target_y:.2f} mm")
            return False

        dy = target_y - self.current_pos['y']
        dx = target_x - self.current_pos['x']

        # Önce Y ekseni hareketi (parmaklar arası boşlukta ilerle)
        if abs(dy) > 0.01:
            y_steps = int(abs(dy) * MOTOR_CONFIG['Y_STEPS_PER_MM'])
            direction = 1 if dy > 0 else -1
            if not self.move_motor_steps('Y', y_steps, direction):
                return False

        # Sonra X ekseni hareketi (yeni tırnağa geç)
        if abs(dx) > 0.01:
            x_steps = int(abs(dx) * MOTOR_CONFIG['X_STEPS_PER_MM'])
            direction = 1 if dx > 0 else -1
            if not self.move_motor_steps('X', x_steps, direction):
                return False

        return True

    def perform_z_touch(self) -> bool:
        """
        Z ekseni dokunuş - FSR sensör ile geliştirilmiş versiyon
        
        Returns:
            True: Temas başarılı, False: Temas algılanamadı
        """
        max_steps = int(MOTOR_CONFIG['MAX_TRAVEL'] * MOTOR_CONFIG['Z_STEPS_PER_MM'])
        step_delay = 1.0 / (MOTOR_CONFIG['Z_AXIS_SPEED'] * 2)

        # Aşağıya hareket
        GPIO.output(MOTOR_CONFIG['Z_DIR_PIN'], GPIO.HIGH)

        steps_taken = 0
        touch_detected = False

        if SYSTEM_CONFIG['DEBUG_MODE']:
            print(f"   🔽 Z aşağı hareketi başlıyor (max {max_steps} adım)")

        for step in range(max_steps):
            # FSR sensör kontrolü
            if self.fsr_sensor:
                # Gelişmiş FSR okuma
                if self.fsr_sensor.read_raw():
                    # Onaylı okuma yap
                    if self.fsr_sensor.read_confirmed():
                        touch_detected = True
                        steps_taken = step
                        if SYSTEM_CONFIG['DEBUG_MODE']:
                            print(f"   ✅ FSR temas algılandı: {steps_taken} adım")
                        break
            else:
                # Eski switch modu
                if GPIO.input(MOTOR_CONFIG['SWITCH_PIN']) == GPIO.HIGH:
                    touch_detected = True
                    steps_taken = step
                    break

            GPIO.output(MOTOR_CONFIG['Z_STEP_PIN'], GPIO.HIGH)
            time.sleep(step_delay)
            GPIO.output(MOTOR_CONFIG['Z_STEP_PIN'], GPIO.LOW)
            time.sleep(step_delay)
            steps_taken = step + 1

        # Z pozisyonunu güncelle
        z_distance = steps_taken / MOTOR_CONFIG['Z_STEPS_PER_MM']
        self.current_pos['z'] += z_distance

        if touch_detected:
            self.z_is_down = True
            time.sleep(0.05)  # Kısa stabilizasyon
            
            if SYSTEM_CONFIG['DEBUG_MODE']:
                print(f"   📍 Z pozisyonu: {self.current_pos['z']:.2f} mm")
            
            return True

        if SYSTEM_CONFIG['DEBUG_MODE']:
            print(f"   ❌ Temas algılanamadı ({steps_taken} adım sonra)")
        
        return False

    def retract_z_axis(self, distance: float = None):
        """Z eksenini geri çek"""
        if distance is None:
            distance = MOTOR_CONFIG.get('Z_RETRACT_DISTANCE', 5.0)

        if self.current_pos['z'] > 0.1:
            retract_distance = min(distance, self.current_pos['z'])
            z_steps = int(retract_distance * MOTOR_CONFIG['Z_STEPS_PER_MM'])
            self.move_motor_steps('Z', z_steps, -1)
            self.z_is_down = False

    def run_full_scan(self) -> bool:
        """Tüm koordinatları sırayla tarar"""
        if not self.scan_points:
            print("❌ Hiç tarama noktası yüklenmemiş!")
            return False

        print(f"\n🚀 TARAMA BAŞLIYOR")
        print(f"📊 Toplam nokta: {len(self.scan_points)}")
        print(f"🔴 Sensör: {'FSR Basınç' if self.fsr_sensor else 'Klasik Switch'}")
        print(f"📐 Çalışma alanı: X[{MOTOR_CONFIG['X_AXIS_MIN']:.1f}, {MOTOR_CONFIG['X_AXIS_MAX']:.1f}] Y[{MOTOR_CONFIG['Y_AXIS_MIN']:.1f}, {MOTOR_CONFIG['Y_AXIS_MAX']:.1f}]")

        self.is_scanning = True
        self.z_is_down = False
        start_time = time.time()
        successful_scans = 0
        current_nail_id = None
        nail_touch_counts = {}

        try:
            for i, point in enumerate(self.scan_points):
                if not self.is_scanning:
                    break

                # Tırnak değişimi kontrolü
                is_nail_transition = current_nail_id != point.nail_id
                if is_nail_transition:
                    if self.z_is_down:
                        print(f"   ⬆️ Z ekseni yukarı çekiliyor (tırnak değişimi)")
                        self.retract_z_axis()
                        time.sleep(0.2)

                    current_nail_id = point.nail_id
                    nail_touch_counts[current_nail_id] = 0
                    print(f"\n🔄 Tırnak {current_nail_id} başlıyor...")

                # İlerleme göstergesi
                print(f"📍 {i + 1}/{len(self.scan_points)} - T{point.nail_id} P{point.index} ({point.x:.2f},{point.y:.2f}mm)", end=" ")

                # X,Y hareketi (mm cinsinden)
                # Tırnak geçişi: Z yukarı → Y → X (parmağa çarpmayı önle)
                # Aynı tırnak: X → Y (normal hareket)
                if is_nail_transition:
                    moved = self.move_to_position_safe(point.x, point.y)
                else:
                    moved = self.move_to_position(point.x, point.y)

                if moved:
                    # Z kontrolü
                    if not self.z_is_down:
                        print("⬇️", end=" ")
                        if self.perform_z_touch():
                            successful_scans += 1
                            nail_touch_counts[current_nail_id] += 1
                            print("✅")
                        else:
                            print("❌ Dokunma algılanamadı")
                    else:
                        successful_scans += 1
                        print("✓")
                else:
                    print("❌ Pozisyon erişilemez")

                if MOTOR_CONFIG.get('PAUSE_BETWEEN_POINTS', 0) > 0:
                    time.sleep(MOTOR_CONFIG['PAUSE_BETWEEN_POINTS'])

        except KeyboardInterrupt:
            print("\n⏹️ Kullanıcı tarafından durduruldu")
            self.is_scanning = False
        except Exception as e:
            print(f"\n❌ Tarama hatası: {e}")
            self.is_scanning = False
        finally:
            # Z'yi yukarı çek
            if self.z_is_down:
                print("\n⬆️ Z ekseni güvenli pozisyona çekiliyor...")
                self.retract_z_axis()
                time.sleep(0.3)
            self.is_scanning = False

        # Tarama özeti
        total_time = time.time() - start_time
        success_rate = (successful_scans / len(self.scan_points)) * 100 if self.scan_points else 0
        avg_time_per_point = total_time / len(self.scan_points) if self.scan_points else 0

        print(f"\n🏁 TARAMA TAMAMLANDI!")
        print(f"✅ Başarılı: {successful_scans}/{len(self.scan_points)} ({success_rate:.1f}%)")
        print(f"⏱️ Toplam süre: {total_time:.1f}s")
        print(f"⚡ Ortalama: {avg_time_per_point:.3f}s/nokta")

        print(f"\n📊 Tırnak Özeti:")
        for nail_id, touch_count in nail_touch_counts.items():
            print(f"   Tırnak {nail_id}: {touch_count} Z dokunuşu")

        # Home pozisyonuna dön
        print("\n🏠 Home pozisyonuna dönülüyor...")
        time.sleep(0.5)

        print("   🏠 X ekseni home pozisyonuna gidiyor...")
        self.home_x_axis()
        time.sleep(0.3)

        print("   🏠 Y ekseni home pozisyonuna gidiyor...")
        self.home_y_axis()
        time.sleep(0.3)

        print("✅ Sistem home pozisyonunda!")

        return success_rate > 80

    def load_coordinates_from_file(self, file_path: str) -> bool:
        """Koordinat dosyasından tarama noktalarını yükle (mm cinsinden)"""
        if not os.path.exists(file_path):
            print(f"❌ Dosya bulunamadı: {file_path}")
            return False

        print(f"📂 Koordinat dosyası yükleniyor: {file_path}")

        self.scan_points.clear()
        current_nail_id = 1

        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()

                # Yorum satırlarını kontrol et
                if line.startswith('#'):
                    if "Tırnak" in line and "başlangıç" in line:
                        try:
                            current_nail_id = int(line.split()[2])
                        except:
                            pass
                    continue

                if not line:
                    continue

                try:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        if len(parts) >= 4:
                            # Birleşik dosya: nail_id, index, x(mm), y(mm)
                            nail_id = int(parts[0].strip())
                            index = int(parts[1].strip())
                            x_mm = float(parts[2].strip())
                            y_mm = float(parts[3].strip())
                        else:
                            # Bireysel dosya: index, x(mm), y(mm)
                            index = int(parts[0].strip())
                            x_mm = float(parts[1].strip())
                            y_mm = float(parts[2].strip())
                            nail_id = current_nail_id

                        # Çalışma alanı kontrolü
                        if (MOTOR_CONFIG['X_AXIS_MIN'] <= x_mm <= MOTOR_CONFIG['X_AXIS_MAX'] and
                                MOTOR_CONFIG['Y_AXIS_MIN'] <= y_mm <= MOTOR_CONFIG['Y_AXIS_MAX']):
                            point = ScanPoint(x=x_mm, y=y_mm, nail_id=nail_id, index=index)
                            self.scan_points.append(point)
                        elif SYSTEM_CONFIG['DEBUG_MODE']:
                            print(f"   ⚠️ Nokta çalışma alanı dışında: ({x_mm:.2f}, {y_mm:.2f})")

                except ValueError as e:
                    if SYSTEM_CONFIG['DEBUG_MODE']:
                        print(f"   ⚠️ Satır işlenemedi: {line}")
                    continue

        if self.scan_points:
            nail_counts = {}
            for point in self.scan_points:
                nail_counts[point.nail_id] = nail_counts.get(point.nail_id, 0) + 1

            print(f"✅ {len(self.scan_points)} koordinat yüklendi")
            for nail_id, count in sorted(nail_counts.items()):
                print(f"   📌 Tırnak {nail_id}: {count} nokta")

            # Min/Max değerleri göster
            x_coords = [p.x for p in self.scan_points]
            y_coords = [p.y for p in self.scan_points]
            print(f"📐 Yüklenen koordinat aralığı:")
            print(f"   X: [{min(x_coords):.2f}, {max(x_coords):.2f}] mm")
            print(f"   Y: [{min(y_coords):.2f}, {max(y_coords):.2f}] mm")

            return True
        else:
            print("❌ Hiç geçerli koordinat bulunamadı")
            return False

    def home_all_axes(self):
        """Manuel homing - Tüm eksenleri home pozisyonuna götür"""
        print("\n🏠 Manuel homing işlemi başlıyor...")

        # Z eksenini yukarı çek
        if self.current_pos['z'] > 0.1:
            print("⬆️ Z ekseni güvenli pozisyona çekiliyor...")
            z_steps = int(abs(self.current_pos['z']) * MOTOR_CONFIG['Z_STEPS_PER_MM'])
            self.move_motor_steps('Z', z_steps, -1)
            self.z_is_down = False

        # X ve Y eksenlerini home'a götür
        self.home_x_axis()
        time.sleep(0.5)
        self.home_y_axis()
        time.sleep(0.5)

        print(f"✅ Manuel homing tamamlandı")

    def test_fsr_sensor(self):
        """FSR sensörü test et"""
        if not self.fsr_sensor:
            print("❌ FSR sensör aktif değil!")
            return
        
        print("\n🧪 FSR SENSÖR TEST MODU")
        print("=" * 40)
        print("Sensöre basın ve bırakın...")
        print("Çıkmak için Ctrl+C\n")
        
        try:
            last_state = None
            while True:
                raw = self.fsr_sensor.read_raw()
                debounced = self.fsr_sensor.read_debounced()
                
                if raw != last_state:
                    last_state = raw
                    status = "🔴 TEMAS ALGILANDI!" if raw else "⚪ Temas yok"
                    print(f"{status} (Raw: {raw}, Debounced: {debounced})")
                
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("\n✅ Test sonlandırıldı")

    def get_status(self):
        """Sistem durumunu göster"""
        print(f"\n📊 MOTOR DURUM:")
        print(f"📍 Pozisyon: ({self.current_pos['x']:.2f}, {self.current_pos['y']:.2f}, {self.current_pos['z']:.2f}) mm")
        print(f"📐 Çalışma alanı:")
        print(f"   X: [{MOTOR_CONFIG['X_AXIS_MIN']:.1f}, {MOTOR_CONFIG['X_AXIS_MAX']:.1f}] mm")
        print(f"   Y: [{MOTOR_CONFIG['Y_AXIS_MIN']:.1f}, {MOTOR_CONFIG['Y_AXIS_MAX']:.1f}] mm")
        print(f"📝 Yüklü nokta: {len(self.scan_points)}")
        print(f"🔄 Tarama: {'Aktif' if self.is_scanning else 'Pasif'}")
        print(f"⬇️ Z durumu: {'Aşağıda' if self.z_is_down else 'Yukarıda'}")
        
        # FSR sensör durumu
        if self.fsr_sensor:
            status = self.fsr_sensor.get_status()
            print(f"\n🔴 FSR SENSÖR:")
            print(f"   Pin: GPIO{status['pin']}")
            print(f"   Ham değer: {'TEMAS' if status['raw_value'] else 'YOK'}")
            print(f"   Debounced: {'TEMAS' if status['debounced_value'] else 'YOK'}")

    def cleanup(self):
        """Sistemi güvenli şekilde kapat"""
        print("\n🧹 Motor sistemi kapatılıyor...")
        self.is_scanning = False

        # Z eksenini güvenli pozisyona çek
        if self.current_pos['z'] > 0:
            self.retract_z_axis(self.current_pos['z'])

        # Motor sürücüyü devre dışı bırak
        if MOTOR_CONFIG['ENABLE_PIN'] is not None:
            GPIO.output(MOTOR_CONFIG['ENABLE_PIN'], GPIO.HIGH)
            time.sleep(0.1)

        GPIO.cleanup()
        print("✅ Motor sistemi kapatıldı")


def main():
    """Ana program döngüsü"""
    parser = argparse.ArgumentParser(description='Tırnak Tarayıcı Motor Kontrolü - FSR Sensör Entegreli')
    parser.add_argument('--coordinates-file', '-f', type=str, help='Koordinat dosyası yolu')
    parser.add_argument('--auto-scan', action='store_true', help='Otomatik tarama başlat')
    parser.add_argument('--test-sensor', action='store_true', help='FSR sensör test modu')
    parser.add_argument('--debug', action='store_true', help='Debug modu')
    args = parser.parse_args()

    if args.debug:
        SYSTEM_CONFIG['DEBUG_MODE'] = True

    controller = NailScannerController(auto_homing=not args.test_sensor)

    try:
        # FSR sensör test modu
        if args.test_sensor:
            controller.test_fsr_sensor()
            return
        
        # Komut satırı parametreleri
        if args.coordinates_file:
            if controller.load_coordinates_from_file(args.coordinates_file):
                if args.auto_scan:
                    controller.run_full_scan()
                    return

        # İnteraktif menü
        while True:
            print(f"\n🤖 MOTOR KONTROL MENÜSÜ (FSR Sensör)")
            print("=" * 40)
            print("1. 📂 Koordinat dosyası yükle")
            print("2. 🚀 Tarama başlat")
            print("3. 🏠 Manuel homing (tüm eksenler)")
            print("4. 🏠 Sadece X home")
            print("5. 🏠 Sadece Y home")
            print("6. 📊 Sistem durumu")
            print("7. 🧪 FSR Sensör Testi")
            print("8. 🚪 Çıkış")

            choice = input("\nSeçiminizi yapın (1-8): ").strip()

            if choice == '1':
                file_path = input("Koordinat dosyası yolu: ").strip()
                controller.load_coordinates_from_file(file_path)

            elif choice == '2':
                if not controller.scan_points:
                    print("❌ Önce koordinat dosyası yükleyin!")
                    continue

                total_points = len(controller.scan_points)
                print(f"\n🎯 {total_points} nokta taranacak")
                confirmation = input("Taramayı başlatmak istiyor musunuz? (E/H): ").strip().upper()

                if confirmation == 'E':
                    controller.run_full_scan()
                else:
                    print("Tarama iptal edildi")

            elif choice == '3':
                controller.home_all_axes()

            elif choice == '4':
                controller.home_x_axis()

            elif choice == '5':
                controller.home_y_axis()

            elif choice == '6':
                controller.get_status()

            elif choice == '7':
                controller.test_fsr_sensor()

            elif choice == '8':
                break

            else:
                print("❌ Geçersiz seçim!")

    except KeyboardInterrupt:
        print("\n⏹️ Program sonlandırıldı")
    except Exception as e:
        print(f"\n❌ Hata: {e}")
    finally:
        controller.cleanup()


if __name__ == "__main__":
    main()
