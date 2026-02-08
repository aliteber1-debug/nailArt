#!/usr/bin/env python3
"""
Tırnak Tarayıcı - Basitleştirilmiş Offset Ölçüm Aracı v2

Amaç: Kamera ile motor arasındaki X/Y offset değerlerini bulmak.

Kullanım:
1. Referans noktası belirle (kağıt üzerinde artı işareti vb.)
2. Kamera bu noktayı görüntüler
3. Motor hesaplanan koordinata gider
4. Manuel olarak motorun TAM referans noktasına gelmesini sağla
5. Bulunan fark = Offset değeri
6. Bu değeri shared_config.py'ye yaz
"""

import os
import sys
import time
import termios
import tty

from shared_config import *
from motor_controller import NailScannerController


class SimpleOffsetCalibration:
    def __init__(self):
        print("\n" + "=" * 50)
        print("🎯 BASİT OFFSET ÖLÇÜM ARACI v2")
        print("=" * 50)
        
        # Mevcut offset değerlerini göster
        print(f"\n📐 Mevcut Offset (shared_config.py):")
        print(f"   OFFSET_X: {MOTOR_CONFIG.get('OFFSET_X', 0):.2f} mm")
        print(f"   OFFSET_Y: {MOTOR_CONFIG.get('OFFSET_Y', 0):.2f} mm")
        
        # Motor başlat
        print("\n🤖 Motor sistemi başlatılıyor...")
        self.controller = NailScannerController(auto_homing=True)
        
        # Ölçüm değişkenleri
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_z = 0.0
        self.step_size = 0.5  # mm
        self.z_step_size = 0.2  # mm

    def move_relative(self, axis: str, distance_mm: float) -> bool:
        """Motoru göreceli hareket ettir"""
        axis = axis.upper()
        
        if axis == 'X':
            steps = int(abs(distance_mm) * MOTOR_CONFIG['X_STEPS_PER_MM'])
        elif axis == 'Y':
            steps = int(abs(distance_mm) * MOTOR_CONFIG['Y_STEPS_PER_MM'])
        elif axis == 'Z':
            steps = int(abs(distance_mm) * MOTOR_CONFIG['Z_STEPS_PER_MM'])
        else:
            return False
        
        direction = 1 if distance_mm > 0 else -1
        return self.controller.move_motor_steps(axis, steps, direction)

    def run_calibration_from_file(self):
        """Koordinat dosyasından kalibrasyon"""
        
        # Dosyaları listele
        if not os.path.exists(PATHS['OUTPUT_DIR']):
            print("❌ Çıktı klasörü bulunamadı!")
            return
        
        coord_files = [f for f in os.listdir(PATHS['OUTPUT_DIR'])
                       if f.startswith('all_nails_path_') and f.endswith('.txt')]
        coord_files.sort(reverse=True)
        
        if not coord_files:
            print("❌ Koordinat dosyası bulunamadı!")
            print("   Önce imaging_pipeline çalıştırın.")
            return
        
        print("\n📂 Mevcut koordinat dosyaları:")
        for i, f in enumerate(coord_files[:5], 1):
            file_path = os.path.join(PATHS['OUTPUT_DIR'], f)
            mod_time = time.strftime("%Y-%m-%d %H:%M", 
                                     time.localtime(os.path.getmtime(file_path)))
            print(f"   {i}. {f} ({mod_time})")
        
        # Dosya seç
        try:
            choice = int(input("\nDosya numarası seçin: ").strip())
            selected_file = os.path.join(PATHS['OUTPUT_DIR'], coord_files[choice - 1])
        except (ValueError, IndexError):
            print("❌ Geçersiz seçim!")
            return
        
        # İlk noktayı oku
        first_point = None
        with open(selected_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 4:
                    x_mm = float(parts[2])
                    y_mm = float(parts[3])
                    first_point = (x_mm, y_mm)
                    break
        
        if not first_point:
            print("❌ Koordinat okunamadı!")
            return
        
        print(f"\n📍 İlk nokta koordinatları: X={first_point[0]:.2f}, Y={first_point[1]:.2f} mm")
        
        # Pozisyona git
        input("\n⚠️ Motor hareket edecek! Devam için ENTER...")
        
        print("🚀 Pozisyona gidiliyor...")
        self.controller.move_to_position(first_point[0], first_point[1])
        print("✅ Hedefe ulaşıldı!")
        
        # Manuel ayarlama
        self._manual_adjustment()
        
        # Sonuçları göster
        self._show_results()

    def run_calibration_manual_coords(self):
        """Manuel koordinat girişi ile kalibrasyon"""
        
        print("\n📍 MANUEL KOORDİNAT GİRİŞİ")
        print("=" * 40)
        print("Motor koordinatlarını mm cinsinden girin.")
        print(f"Çalışma alanı: X[{MOTOR_CONFIG['X_AXIS_MIN']}, {MOTOR_CONFIG['X_AXIS_MAX']}] "
              f"Y[{MOTOR_CONFIG['Y_AXIS_MIN']}, {MOTOR_CONFIG['Y_AXIS_MAX']}]")
        
        try:
            x_mm = float(input("\nX koordinatı (mm): ").strip())
            y_mm = float(input("Y koordinatı (mm): ").strip())
        except ValueError:
            print("❌ Geçersiz giriş!")
            return
        
        # Sınır kontrolü
        if not (MOTOR_CONFIG['X_AXIS_MIN'] <= x_mm <= MOTOR_CONFIG['X_AXIS_MAX']):
            print(f"❌ X değeri sınır dışında!")
            return
        if not (MOTOR_CONFIG['Y_AXIS_MIN'] <= y_mm <= MOTOR_CONFIG['Y_AXIS_MAX']):
            print(f"❌ Y değeri sınır dışında!")
            return
        
        # Pozisyona git
        input("\n⚠️ Motor hareket edecek! Devam için ENTER...")
        
        print(f"🚀 Pozisyona gidiliyor: ({x_mm:.2f}, {y_mm:.2f}) mm")
        self.controller.move_to_position(x_mm, y_mm)
        print("✅ Hedefe ulaşıldı!")
        
        # Manuel ayarlama
        self._manual_adjustment()
        
        # Sonuçları göster
        self._show_results()

    def run_calibration_center(self):
        """Çalışma alanı merkezinde kalibrasyon"""
        
        # Merkez hesapla
        center_x = (MOTOR_CONFIG['X_AXIS_MIN'] + MOTOR_CONFIG['X_AXIS_MAX']) / 2
        center_y = (MOTOR_CONFIG['Y_AXIS_MIN'] + MOTOR_CONFIG['Y_AXIS_MAX']) / 2
        
        print(f"\n📍 Çalışma alanı merkezi: X={center_x:.2f}, Y={center_y:.2f} mm")
        
        input("\n⚠️ Motor merkeze gidecek! Devam için ENTER...")
        
        print("🚀 Merkeze gidiliyor...")
        self.controller.move_to_position(center_x, center_y)
        print("✅ Merkeze ulaşıldı!")
        
        # Manuel ayarlama
        self._manual_adjustment()
        
        # Sonuçları göster
        self._show_results()

    def _manual_adjustment(self):
        """Manuel ayarlama modu"""
        
        # Değerleri sıfırla
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_z = 0.0
        
        print("\n" + "=" * 50)
        print("🎮 MANUEL AYARLAMA MODU")
        print("=" * 50)
        print("Kontroller:")
        print("  W/S : Y ekseni (İleri/Geri)")
        print("  A/D : X ekseni (Sol/Sağ)")
        print("  R/F : Z ekseni (Yukarı/Aşağı)")
        print("  +/- : Adım boyutu değiştir")
        print("  Q   : Kaydet ve çık")
        print("  ESC : İptal")
        print(f"\nAdım boyutu: {self.step_size} mm")
        print("\n🎯 Motorun tam referans noktasına gelmesini sağlayın...")
        
        # Terminal raw mod
        old_settings = termios.tcgetattr(sys.stdin)
        
        try:
            tty.setraw(sys.stdin.fileno())
            
            while True:
                char = sys.stdin.read(1).lower()
                
                if char == 'q':
                    print("\n\n✅ Ayarlama tamamlandı!")
                    break
                    
                elif char == '\x1b':  # ESC
                    print("\n\n❌ İptal edildi!")
                    self.offset_x = 0.0
                    self.offset_y = 0.0
                    self.offset_z = 0.0
                    break
                
                # Y ekseni
                elif char == 'w':
                    if self.move_relative('Y', self.step_size):
                        self.offset_y += self.step_size
                        
                elif char == 's':
                    if self.move_relative('Y', -self.step_size):
                        self.offset_y -= self.step_size
                
                # X ekseni
                elif char == 'a':
                    if self.move_relative('X', -self.step_size):
                        self.offset_x -= self.step_size
                        
                elif char == 'd':
                    if self.move_relative('X', self.step_size):
                        self.offset_x += self.step_size
                
                # Z ekseni
                elif char == 'r':
                    if self.move_relative('Z', -self.z_step_size):
                        self.offset_z -= self.z_step_size
                        
                elif char == 'f':
                    if self.move_relative('Z', self.z_step_size):
                        self.offset_z += self.z_step_size
                
                # Adım boyutu
                elif char == '+' or char == '=':
                    self.step_size = min(5.0, self.step_size + 0.1)
                    
                elif char == '-':
                    self.step_size = max(0.1, self.step_size - 0.1)
                
                # Durum göster
                sys.stdout.write(f"\r📍 X:{self.offset_x:+.2f} Y:{self.offset_y:+.2f} "
                               f"Z:{self.offset_z:+.2f} mm | Adım:{self.step_size:.1f}    ")
                sys.stdout.flush()
        
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def _show_results(self):
        """Sonuçları göster"""
        
        # Mevcut değerler
        current_x = MOTOR_CONFIG.get('OFFSET_X', 0)
        current_y = MOTOR_CONFIG.get('OFFSET_Y', 0)
        
        # Yeni değerler
        new_x = current_x + self.offset_x
        new_y = current_y + self.offset_y
        
        print("\n" + "=" * 50)
        print("📊 KALİBRASYON SONUÇLARI")
        print("=" * 50)
        
        print(f"\n🔹 Mevcut offset (shared_config.py):")
        print(f"   OFFSET_X: {current_x:.3f} mm")
        print(f"   OFFSET_Y: {current_y:.3f} mm")
        
        print(f"\n🔹 Yapılan düzeltme:")
        print(f"   X: {self.offset_x:+.3f} mm")
        print(f"   Y: {self.offset_y:+.3f} mm")
        print(f"   Z: {self.offset_z:+.3f} mm")
        
        print(f"\n🔹 YENİ OFFSET DEĞERLERİ:")
        print(f"   OFFSET_X: {new_x:.3f} mm")
        print(f"   OFFSET_Y: {new_y:.3f} mm")
        
        print("\n" + "=" * 50)
        print("📝 shared_config.py'de MOTOR_CONFIG içine yazın:")
        print("=" * 50)
        print(f"    'OFFSET_X': {new_x:.2f},")
        print(f"    'OFFSET_Y': {new_y:.2f},")
        
        # Dosyaya kaydet
        self._save_to_file(current_x, current_y, new_x, new_y)

    def _save_to_file(self, old_x, old_y, new_x, new_y):
        """Sonuçları dosyaya kaydet"""
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"offset_result_{timestamp}.txt"
        filepath = os.path.join(PATHS['OUTPUT_DIR'], filename)
        
        with open(filepath, 'w') as f:
            f.write("# Offset Kalibrasyon Sonuçları\n")
            f.write(f"# Tarih: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n")
            f.write(f"# Eski değerler:\n")
            f.write(f"# OFFSET_X: {old_x:.3f}\n")
            f.write(f"# OFFSET_Y: {old_y:.3f}\n")
            f.write("\n")
            f.write(f"# Yapılan düzeltme:\n")
            f.write(f"# X: {self.offset_x:+.3f}\n")
            f.write(f"# Y: {self.offset_y:+.3f}\n")
            f.write(f"# Z: {self.offset_z:+.3f}\n")
            f.write("\n")
            f.write(f"# YENİ DEĞERLER (shared_config.py'ye yazın):\n")
            f.write(f"'OFFSET_X': {new_x:.2f},\n")
            f.write(f"'OFFSET_Y': {new_y:.2f},\n")
        
        print(f"\n💾 Kaydedildi: {filename}")

    def cleanup(self):
        """Temizlik"""
        if hasattr(self, 'controller') and self.controller:
            # Z yukarı çek
            if self.controller.current_pos.get('z', 0) > 0:
                print("\n⬆️ Z ekseni yukarı çekiliyor...")
                self.controller.retract_z_axis()
            self.controller.cleanup()


def main():
    tool = None
    
    try:
        tool = SimpleOffsetCalibration()
        
        while True:
            print("\n" + "=" * 40)
            print("📋 MENÜ")
            print("=" * 40)
            print("1. 📂 Koordinat dosyasından kalibrasyon")
            print("2. 📍 Manuel koordinat girişi")
            print("3. 🎯 Merkez noktada kalibrasyon")
            print("4. 🏠 Home pozisyonuna git")
            print("5. ℹ️  Mevcut offset değerleri")
            print("6. 🚪 Çıkış")
            
            choice = input("\nSeçim: ").strip()
            
            if choice == '1':
                tool.run_calibration_from_file()
                
            elif choice == '2':
                tool.run_calibration_manual_coords()
                
            elif choice == '3':
                tool.run_calibration_center()
                
            elif choice == '4':
                print("\n🏠 Home pozisyonuna gidiliyor...")
                tool.controller.home_all_axes()
                print("✅ Home pozisyonunda!")
                
            elif choice == '5':
                print(f"\n📐 Mevcut Offset Değerleri:")
                print(f"   OFFSET_X: {MOTOR_CONFIG.get('OFFSET_X', 0):.3f} mm")
                print(f"   OFFSET_Y: {MOTOR_CONFIG.get('OFFSET_Y', 0):.3f} mm")
                print(f"   OFFSET_Z: {MOTOR_CONFIG.get('OFFSET_Z', 0):.3f} mm")
                
            elif choice == '6':
                break
                
            else:
                print("❌ Geçersiz seçim!")
    
    except KeyboardInterrupt:
        print("\n\n⚠️ İptal edildi")
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if tool:
            tool.cleanup()
        print("\n👋 Program sonlandırıldı")


if __name__ == "__main__":
    main()
