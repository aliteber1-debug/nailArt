#!/usr/bin/env python3
"""
Tırnak Pozisyon Offset Ölçüm Aracı - Düzeltilmiş Versiyon
X/Y ekseni hareket sorunları çözüldü
"""

import os
import sys
import time
import select
from motor_controller import NailScannerController
from shared_config import *
from imaging_pipeline import NailImagingPipeline


class OffsetCalibrationTool:
    def __init__(self):
        print("🎯 TIRNAK POZİSYON OFFSET ÖLÇÜM ARACI")
        print("=" * 50)

        self.controller = NailScannerController(auto_homing=True)
        self.manual_offset_x = 0.0  # mm
        self.manual_offset_y = 0.0  # mm
        self.manual_offset_z = 0.0  # mm
        self.step_size = 0.5  # Her tuş basımında hareket miktarı (mm)
        self.z_step_size = 0.2  # Z ekseni için daha küçük adım
        self.coord_file = None

    def run_imaging_pipeline(self):
        """Görüntü işleme pipeline'ını çalıştır ve koordinat dosyasını döndür"""
        print("\n📸 GÖRÜNTÜ İŞLEME BAŞLIYOR...")
        print("=" * 40)

        try:
            pipeline = NailImagingPipeline()
            result = pipeline.run_full_pipeline(save_coordinates=True)

            if result and os.path.exists(result):
                print(f"✅ Koordinat dosyası oluşturuldu: {os.path.basename(result)}")
                return result
            else:
                print("❌ Koordinat dosyası oluşturulamadı!")
                return None
        except Exception as e:
            print(f"❌ Görüntü işleme hatası: {e}")
            return None

    def get_coordinate_file(self):
        """Koordinat dosyasını seç veya oluştur"""
        print("\n📂 KOORDİNAT DOSYASI SEÇİMİ")
        print("=" * 40)

        # Mevcut dosyaları listele
        coord_files = []
        if os.path.exists(PATHS['OUTPUT_DIR']):
            coord_files = [f for f in os.listdir(PATHS['OUTPUT_DIR'])
                           if f.startswith('all_nails_path_') and f.endswith('.txt')]
            coord_files.sort(reverse=True)  # En yeni en üstte

        print("1. 🆕 Yeni görüntü işle (önerilen)")

        if coord_files:
            print("\nMevcut koordinat dosyaları:")
            for i, file in enumerate(coord_files[:5], 2):  # Son 5 dosyayı göster
                file_path = os.path.join(PATHS['OUTPUT_DIR'], file)
                file_time = os.path.getmtime(file_path)
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_time))
                print(f"{i}. 📄 {file} ({time_str})")

        while True:
            choice = input(f"\nSeçiminiz (1-{min(len(coord_files) + 1, 6)}): ").strip()

            if choice == '1':
                # Yeni görüntü işle
                return self.run_imaging_pipeline()
            elif choice.isdigit() and 2 <= int(choice) <= min(len(coord_files) + 1, 6):
                # Mevcut dosyayı seç
                file_idx = int(choice) - 2
                return os.path.join(PATHS['OUTPUT_DIR'], coord_files[file_idx])
            else:
                print("❌ Geçersiz seçim!")

    def move_motor_relative(self, axis, distance_mm):
        """Motoru göreceli olarak hareket ettir (offset hesaplaması yapmadan)"""
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

    def get_char_non_blocking(self):
        """Non-blocking karakter okuma"""
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            char = sys.stdin.read(1)
            return char
        return None

    def run_calibration(self):
        """Kalibrasyon işlemi"""
        # 1. Koordinat dosyasını al (yeni oluştur veya mevcut seç)
        self.coord_file = self.get_coordinate_file()

        if not self.coord_file:
            print("❌ Koordinat dosyası alınamadı!")
            return

        print(f"\n📂 Kullanılan dosya: {os.path.basename(self.coord_file)}")

        # 2. İlk noktayı yükle ve git
        self.controller.load_coordinates_from_file(self.coord_file)
        if not self.controller.scan_points:
            print("❌ Koordinat yüklenemedi!")
            return

        first_point = self.controller.scan_points[0]
        print(f"\n🎯 İlk nokta: X={first_point.x:.2f}, Y={first_point.y:.2f} mm")
        print("📍 Bu noktaya gidiliyor...")

        self.controller.move_to_position(first_point.x, first_point.y)
        print("✅ Hedefe ulaşıldı!")

        # 3. Manuel kontrol
        print("\n" + "=" * 50)
        print("MANUEL KONTROL MODU")
        print("=" * 50)
        print("Hareket Kontrolleri:")
        print("  W/S: Y ekseni (+/- İleri/Geri)")
        print("  A/D: X ekseni (-/+ Sola/Sağa)")
        print("  R/F: Z ekseni (+/- Yukarı/Aşağı)")
        print("\nAdım Boyutu:")
        print("  +/-: X/Y adım boyutu değiştir")
        print("  P/O: Z adım boyutu değiştir")
        print("\nDiğer:")
        print("  N: Sonraki nokta")
        print("  B: Önceki nokta")
        print("  M: Sonraki tırnağın ilk noktası")
        print("  Q: Çıkış ve sonuçları göster")
        print(f"\nX/Y adım: {self.step_size} mm | Z adım: {self.z_step_size} mm")
        print("\nTırnağın tam üzerine gelene kadar hareket ettirin...")

        # Mevcut nokta indeksi
        current_point_index = 0
        total_points = len(self.controller.scan_points)

        # Terminal raw moduna al
        import termios
        import tty
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setraw(sys.stdin.fileno())

            print("\n🎮 Kontroller aktif! (Q ile çıkış)")

            while True:
                # Karakter oku
                char = sys.stdin.read(1).lower()

                if char == 'q':
                    break

                # X/Y ekseni kontrolleri
                elif char == 'w':  # Y+ (ileri)
                    if self.move_motor_relative('Y', self.step_size):
                        self.manual_offset_y += self.step_size
                        print(f"\n➡️ Y+ hareket: {self.step_size}mm")

                elif char == 's':  # Y- (geri)
                    if self.move_motor_relative('Y', -self.step_size):
                        self.manual_offset_y -= self.step_size
                        print(f"\n⬅️ Y- hareket: {self.step_size}mm")

                elif char == 'a':  # X- (sola)
                    if self.move_motor_relative('X', -self.step_size):
                        self.manual_offset_x -= self.step_size
                        print(f"\n⬅️ X- hareket: {self.step_size}mm")

                elif char == 'd':  # X+ (sağa)
                    if self.move_motor_relative('X', self.step_size):
                        self.manual_offset_x += self.step_size
                        print(f"\n➡️ X+ hareket: {self.step_size}mm")

                # Z ekseni kontrolleri
                elif char == 'r':  # Z+ (yukarı)
                    if self.move_motor_relative('Z', -self.z_step_size):  # Z+ için - direction
                        self.manual_offset_z -= self.z_step_size
                        print(f"\n⬆️ Z+ hareket: {self.z_step_size}mm")

                elif char == 'f':  # Z- (aşağı)
                    if self.move_motor_relative('Z', self.z_step_size):  # Z- için + direction
                        self.manual_offset_z += self.z_step_size
                        print(f"\n⬇️ Z- hareket: {self.z_step_size}mm")

                # Adım boyutu kontrolleri
                elif char == '+' or char == '=':
                    self.step_size = min(5.0, self.step_size + 0.1)
                    print(f"\n📏 XY adım: {self.step_size:.1f}mm")

                elif char == '-':
                    self.step_size = max(0.1, self.step_size - 0.1)
                    print(f"\n📏 XY adım: {self.step_size:.1f}mm")

                elif char == 'p':  # Z adım artır
                    self.z_step_size = min(2.0, self.z_step_size + 0.05)
                    print(f"\n📏 Z adım: {self.z_step_size:.2f}mm")

                elif char == 'o':  # Z adım azalt
                    self.z_step_size = max(0.05, self.z_step_size - 0.05)
                    print(f"\n📏 Z adım: {self.z_step_size:.2f}mm")

                # Nokta navigasyonu
                elif char == 'n':  # Sonraki nokta
                    if current_point_index < total_points - 1:
                        # Z'yi güvenli pozisyona çek
                        if self.controller.current_pos['z'] > 0:
                            self.controller.retract_z_axis(2.0)

                        current_point_index += 1
                        next_point = self.controller.scan_points[current_point_index]

                        print(f"\n🔄 Nokta {current_point_index + 1}/{total_points} - Tırnak {next_point.nail_id}")
                        print(f"📍 Hedef: X={next_point.x:.2f}, Y={next_point.y:.2f} mm")
                        print("🚀 Hareket ediliyor...")

                        # Hedef pozisyona göreceli hareket hesapla
                        target_x = next_point.x + self.controller.motor_offset['x']
                        target_y = next_point.y + self.controller.motor_offset['y']

                        delta_x = target_x - self.controller.current_pos['x']
                        delta_y = target_y - self.controller.current_pos['y']

                        print(f"📏 Delta: X={delta_x:.2f}, Y={delta_y:.2f} mm")

                        # Hareketi gerçekleştir
                        if abs(delta_x) > 0.1:
                            self.move_motor_relative('X', delta_x)
                        if abs(delta_y) > 0.1:
                            self.move_motor_relative('Y', delta_y)

                        # Offset'leri sıfırla (yeni nokta için)
                        self.manual_offset_x = 0.0
                        self.manual_offset_y = 0.0
                        self.manual_offset_z = 0.0

                        print("✅ Hedefe ulaşıldı!")

                elif char == 'b':  # Önceki nokta
                    if current_point_index > 0:
                        # Z'yi güvenli pozisyona çek
                        if self.controller.current_pos['z'] > 0:
                            self.controller.retract_z_axis(2.0)

                        current_point_index -= 1
                        prev_point = self.controller.scan_points[current_point_index]

                        print(f"\n🔄 Nokta {current_point_index + 1}/{total_points} - Tırnak {prev_point.nail_id}")
                        print(f"📍 Hedef: X={prev_point.x:.2f}, Y={prev_point.y:.2f} mm")
                        print("🚀 Hareket ediliyor...")

                        # Hedef pozisyona göreceli hareket hesapla
                        target_x = prev_point.x + self.controller.motor_offset['x']
                        target_y = prev_point.y + self.controller.motor_offset['y']

                        delta_x = target_x - self.controller.current_pos['x']
                        delta_y = target_y - self.controller.current_pos['y']

                        print(f"📏 Delta: X={delta_x:.2f}, Y={delta_y:.2f} mm")

                        # Hareketi gerçekleştir
                        if abs(delta_x) > 0.1:
                            self.move_motor_relative('X', delta_x)
                        if abs(delta_y) > 0.1:
                            self.move_motor_relative('Y', delta_y)

                        # Offset'leri sıfırla (yeni nokta için)
                        self.manual_offset_x = 0.0
                        self.manual_offset_y = 0.0
                        self.manual_offset_z = 0.0

                        print("✅ Hedefe ulaşıldı!")

                elif char == 'm':  # Sonraki tırnağın ilk noktası
                    # Mevcut tırnak ID'sini bul
                    current_nail_id = self.controller.scan_points[current_point_index].nail_id

                    # Sonraki tırnağı bul
                    next_nail_first_point = None
                    next_nail_index = None

                    for i, point in enumerate(self.controller.scan_points):
                        if point.nail_id > current_nail_id:
                            next_nail_first_point = point
                            next_nail_index = i
                            break

                    if next_nail_first_point is not None:
                        # Z'yi güvenli pozisyona çek
                        if self.controller.current_pos['z'] > 0:
                            self.controller.retract_z_axis(2.0)

                        current_point_index = next_nail_index

                        print(f"\n🎯 Tırnak {next_nail_first_point.nail_id} ilk noktası")
                        print(f"📍 Hedef: X={next_nail_first_point.x:.2f}, Y={next_nail_first_point.y:.2f} mm")
                        print("🚀 Hareket ediliyor...")

                        # Hedef pozisyona göreceli hareket hesapla
                        target_x = next_nail_first_point.x + self.controller.motor_offset['x']
                        target_y = next_nail_first_point.y + self.controller.motor_offset['y']

                        delta_x = target_x - self.controller.current_pos['x']
                        delta_y = target_y - self.controller.current_pos['y']

                        print(f"📏 Delta: X={delta_x:.2f}, Y={delta_y:.2f} mm")

                        # Hareketi gerçekleştir
                        if abs(delta_x) > 0.1:
                            self.move_motor_relative('X', delta_x)
                        if abs(delta_y) > 0.1:
                            self.move_motor_relative('Y', delta_y)

                        # Offset'leri sıfırla (yeni tırnak için)
                        self.manual_offset_x = 0.0
                        self.manual_offset_y = 0.0
                        self.manual_offset_z = 0.0

                        print("✅ Sonraki tırnağa ulaşıldı!")
                    else:
                        print(f"\n⚠️ Sonraki tırnak bulunamadı! (Mevcut: Tırnak {current_nail_id})")

                # Durum göster
                print(f"\r📍 {current_point_index + 1}/{total_points} | "
                      f"X: {self.manual_offset_x:+.2f} | Y: {self.manual_offset_y:+.2f} | "
                      f"Z: {self.manual_offset_z:+.2f} | Step: {self.step_size:.1f}mm    ",
                      end="", flush=True)

        except KeyboardInterrupt:
            print("\n\n⚠️ Kullanıcı tarafından iptal edildi")
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

        # Z eksenini güvenli pozisyona çek
        if self.controller.current_pos['z'] > 0:
            print("\n\n⬆️ Z ekseni güvenli pozisyona çekiliyor...")
            self.controller.retract_z_axis(self.controller.current_pos['z'])

        # 4. Sonuçları göster ve kaydet
        self.show_and_save_results()

    def show_and_save_results(self):
        """Kalibrasyon sonuçlarını göster ve kaydet"""
        print("\n\n" + "=" * 50)
        print("📊 KALİBRASYON SONUÇLARI")
        print("=" * 50)
        print(f"X Offset: {self.manual_offset_x:+.3f} mm")
        print(f"Y Offset: {self.manual_offset_y:+.3f} mm")
        print(f"Z Offset: {self.manual_offset_z:+.3f} mm")

        print("\nBu değerleri shared_config.py'de kullanabilirsiniz:")
        print(f"'MOTOR_OFFSET_X': {self.manual_offset_x:.3f},")
        print(f"'MOTOR_OFFSET_Y': {self.manual_offset_y:.3f},")
        print(f"'MOTOR_OFFSET_Z': {self.manual_offset_z:.3f},")

        # Sonuçları dosyaya kaydet
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(PATHS['OUTPUT_DIR'], f"calibration_offset_{timestamp}.txt")

        with open(result_file, 'w') as f:
            f.write("# Tırnak Tarayıcı Kalibrasyon Offset Değerleri\n")
            f.write(f"# Tarih: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Koordinat Dosyası: {os.path.basename(self.coord_file) if self.coord_file else 'N/A'}\n")
            f.write("\n")
            f.write("# shared_config.py'deki MOTOR_CONFIG içine ekleyin:\n")
            f.write(f"'MOTOR_OFFSET_X': {self.manual_offset_x:.3f},\n")
            f.write(f"'MOTOR_OFFSET_Y': {self.manual_offset_y:.3f},\n")
            f.write(f"'MOTOR_OFFSET_Z': {self.manual_offset_z:.3f},\n")
            f.write("\n")
            f.write("# Detaylı Bilgiler:\n")
            f.write(f"# X Offset: {self.manual_offset_x:+.3f} mm\n")
            f.write(f"# Y Offset: {self.manual_offset_y:+.3f} mm\n")
            f.write(f"# Z Offset: {self.manual_offset_z:+.3f} mm\n")

        print(f"\n💾 Sonuçlar kaydedildi: {os.path.basename(result_file)}")


def main():
    """Ana program"""
    print("\n" + "=" * 60)
    print("🚀 TIRNAK POZİSYON OFFSET ÖLÇÜM SİSTEMİ")
    print("=" * 60)
    print("\nBu araç:")
    print("1. Görüntü işleme yaparak tırnak koordinatlarını bulur")
    print("2. İlk noktaya gider")
    print("3. Manuel kontrolle tam pozisyonu ayarlamanızı sağlar")
    print("4. Offset değerlerini hesaplar ve kaydeder")
    print("\nKontroller:")
    print("• W/A/S/D: Y/X ekseni hareket")
    print("• R/F: Z ekseni hareket")
    print("• +/-: Adım boyutu ayar")
    print("• N/B: Nokta değiştir")
    print("• M: Sonraki tırnak")
    print("• Q: Çıkış")
    print("\nDevam etmek için ENTER'a basın...")
    input()

    try:
        tool = OffsetCalibrationTool()
        tool.run_calibration()
    except KeyboardInterrupt:
        print("\n\n⚠️ Kullanıcı tarafından iptal edildi")
    except Exception as e:
        print(f"\n\n❌ Hata: {e}")
    finally:
        print("\n👋 Program sonlandırıldı")


if __name__ == "__main__":
    main()