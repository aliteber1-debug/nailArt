#!/usr/bin/env python3
"""
Tırnak Tarayıcı Ana Koordinatör - Düzeltilmiş Versiyon
Imaging Pipeline ve Motor Controller arasında koordinasyon sağlar
"""

import os
import sys
import time
from shared_config import *


class NailScannerMaster:
    def __init__(self):
        print("🤖 TİRNAK TARAYICI ANA SİSTEM - KOORDİNAT DÜZELTİLDİ")
        print("=" * 50)
        print("✅ X Flip düzeltmesi aktif")
        print("✅ Edge offset kaldırıldı")
        print("✅ Gerçek koordinatlar kullanılıyor")
        print("=" * 50)

        self.imaging_available = os.path.exists('imaging_pipeline.py')
        self.motor_available = os.path.exists('motor_controller.py')

        create_directories()

        print(f"📸 Imaging Pipeline: {'✅' if self.imaging_available else '❌'}")
        print(f"🤖 Motor Controller: {'✅' if self.motor_available else '❌'}")

        # Sistem bilgilerini göster
        print_system_info()

    def run_homing_procedure(self) -> bool:
        """Homing işlemini gerçekleştir"""
        if not self.motor_available:
            print("❌ Motor controller mevcut değil!")
            return False

        print("\n🏠 HOMİNG İŞLEMİ BAŞLIYOR...")
        print("=" * 30)

        try:
            from motor_controller import NailScannerController
            controller = NailScannerController(auto_homing=True)

            # X ve Y eksenlerini home'a götür
            controller.home_x_axis()
            time.sleep(0.5)
            controller.home_y_axis()
            time.sleep(0.5)

            controller.cleanup()

            print("✅ Homing işlemi tamamlandı!")
            return True

        except Exception as e:
            print(f"❌ Homing hatası: {e}")
            return False

    def run_imaging_pipeline(self) -> str:
        """Imaging pipeline çalıştır ve koordinat dosyası döndür"""
        if not self.imaging_available:
            print("❌ Imaging pipeline mevcut değil!")
            return None

        print("\n📸 GÖRÜNTÜ İŞLEME BAŞLIYOR...")

        try:
            from imaging_pipeline import NailImagingPipeline
            pipeline = NailImagingPipeline()
            result = pipeline.run_full_pipeline(save_coordinates=True)

            if result and os.path.exists(result):
                print(f"✅ Koordinat dosyası: {result}")

                # Dosya içeriğini kontrol et
                with open(result, 'r') as f:
                    lines = f.readlines()
                    data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
                    print(f"   • Toplam veri satırı: {len(data_lines)}")

                return result
            else:
                print("❌ Koordinat dosyası oluşturulamadı!")
                return None

        except Exception as e:
            print(f"❌ Imaging hatası: {e}")
            import traceback
            if SYSTEM_CONFIG.get('DEBUG_MODE', False):
                traceback.print_exc()
            return None

    def run_motor_controller(self, coordinates_file: str) -> bool:
        """Motor controller çalıştır"""
        if not self.motor_available:
            print("❌ Motor controller mevcut değil!")
            return False

        if not os.path.exists(coordinates_file):
            print(f"❌ Koordinat dosyası bulunamadı: {coordinates_file}")
            return False

        print(f"\n🤖 MOTOR KONTROL BAŞLIYOR...")
        print(f"📂 Dosya: {os.path.basename(coordinates_file)}")

        try:
            from motor_controller import NailScannerController
            controller = NailScannerController(auto_homing=True)

            if controller.load_coordinates_from_file(coordinates_file):
                print(f"🎯 {len(controller.scan_points)} nokta yüklendi")

                # Çalışma alanı kontrolü
                if controller.scan_points:
                    x_coords = [p.x for p in controller.scan_points]
                    y_coords = [p.y for p in controller.scan_points]

                    print(f"📐 Yüklenen koordinat aralığı:")
                    print(f"   X: [{min(x_coords):.2f}, {max(x_coords):.2f}] mm")
                    print(f"   Y: [{min(y_coords):.2f}, {max(y_coords):.2f}] mm")

                    # Sınır kontrolü
                    if (min(x_coords) < MOTOR_CONFIG['X_AXIS_MIN'] or
                            max(x_coords) > MOTOR_CONFIG['X_AXIS_MAX'] or
                            min(y_coords) < MOTOR_CONFIG['Y_AXIS_MIN'] or
                            max(y_coords) > MOTOR_CONFIG['Y_AXIS_MAX']):
                        print("⚠️ UYARI: Bazı noktalar çalışma alanı dışında!")
                        print(f"   Motor çalışma alanı:")
                        print(f"   X: [{MOTOR_CONFIG['X_AXIS_MIN']:.1f}, {MOTOR_CONFIG['X_AXIS_MAX']:.1f}] mm")
                        print(f"   Y: [{MOTOR_CONFIG['Y_AXIS_MIN']:.1f}, {MOTOR_CONFIG['Y_AXIS_MAX']:.1f}] mm")

                confirmation = input("\nTaramayı başlat? (E/H): ").strip().upper()
                if confirmation == 'E':
                    success = controller.run_full_scan()

                    if success:
                        # Başarılı tarama sonrası dosyayı sil
                        os.remove(coordinates_file)
                        print(f"🗑️ Koordinat dosyası silindi")

                    controller.cleanup()
                    return success
                else:
                    print("❌ Tarama iptal edildi")
                    controller.cleanup()
                    return False
            else:
                print("❌ Koordinat dosyası yüklenemedi")
                controller.cleanup()
                return False

        except Exception as e:
            print(f"❌ Motor hatası: {e}")
            if SYSTEM_CONFIG.get('DEBUG_MODE', False):
                import traceback
                traceback.print_exc()
            return False

    def run_full_pipeline(self) -> bool:
        """Tam otomatik tarama (Homing + Imaging + Motor)"""
        print("\n🚀 TAM OTOMATİK TARAMA")
        print("=" * 30)

        # Phase 1: Homing
        print("\n1️⃣ Homing işlemi...")
        if not self.run_homing_procedure():
            print("❌ Homing başarısız, işlem durduruluyor")
            return False

        # Phase 2: Imaging
        print("\n2️⃣ Görüntü işleme...")
        coordinates_file = self.run_imaging_pipeline()
        if not coordinates_file:
            print("❌ Görüntü işleme başarısız, işlem durduruluyor")
            return False

        # Phase 3: Motor
        print("\n3️⃣ Motor tarama...")
        success = self.run_motor_controller(coordinates_file)

        if success:
            print("\n🎉 TARAMA BAŞARIYLA TAMAMLANDI!")
        else:
            print("\n⚠️ Tarama tamamlanamadı")

        return success

    def show_available_coordinates(self):
        """Mevcut koordinat dosyalarını listele"""
        if not os.path.exists(PATHS['OUTPUT_DIR']):
            print("❌ Çıktı klasörü bulunamadı")
            return []

        coord_files = [f for f in os.listdir(PATHS['OUTPUT_DIR'])
                       if f.startswith('all_nails_path_') and f.endswith('.txt')]

        if coord_files:
            print("📁 Mevcut koordinat dosyaları:")
            for i, file in enumerate(coord_files, 1):
                file_path = os.path.join(PATHS['OUTPUT_DIR'], file)
                file_size = os.path.getsize(file_path)
                print(f"   {i}. {file} ({file_size} bytes)")
            return coord_files
        else:
            print("❌ Hiç koordinat dosyası bulunamadı")
            return []

    def test_coordinate_conversion(self):
        """Koordinat dönüşümünü test et"""
        print("\n🧪 KOORDİNAT DÖNÜŞÜM TESTİ")
        print("=" * 30)

        # Test noktaları (piksel)
        test_points = [
            (100, 100, "Sol üst"),
            (1820, 100, "Sağ üst"),
            (100, 980, "Sol alt"),
            (1820, 980, "Sağ alt"),
            (960, 540, "Merkez")
        ]

        # Kalibrasyon değerleri (örnek)
        px_per_mm_x = 20.0  # örnek
        px_per_mm_y = 25.0  # örnek (anizotropi)

        img_width = 1920
        img_height = 1080
        origin_x = img_width - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT']
        origin_y = img_height - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM']

        print(f"Görüntü boyutu: {img_width}x{img_height} px")
        print(f"Origin: ({origin_x}, {origin_y}) px")
        print(f"Kalibrasyon: X={px_per_mm_x} px/mm, Y={px_per_mm_y} px/mm")
        print(f"Anizotropi oranı: {px_per_mm_x / px_per_mm_y:.3f}")
        print(f"X Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']} (DÜZELTİLDİ)")
        print()

        for px, py, label in test_points:
            # Görüntü koordinatları (origin'e göre)
            rel_px = origin_x - px  # X+ sola
            rel_py = origin_y - py  # Y+ yukarı

            # mm'ye dönüşüm (anizotropik)
            x_mm = rel_px / px_per_mm_x
            y_mm = rel_py / px_per_mm_y

            # Motor koordinatları
            if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']:
                motor_x = -x_mm
            else:
                motor_x = x_mm

            if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']:
                motor_y = -y_mm
            else:
                motor_y = y_mm

            print(f"{label:10} | Piksel: ({px:4}, {py:4}) → Motor: ({motor_x:6.2f}, {motor_y:6.2f}) mm")


def main():
    """Ana menü"""
    master = NailScannerMaster()

    while True:
        print(f"\n🤖 ANA MENÜ")
        print("=" * 20)
        print("1. 🚀 Tam Otomatik Tarama")
        print("2. 🏠 Sadece Homing")
        print("3. 📸 Sadece Görüntü İşleme")
        print("4. 🤖 Sadece Motor Tarama")
        print("5. 🧪 Koordinat Dönüşüm Testi")
        print("6. ℹ️ Sistem Bilgileri")
        print("7. 🚪 Çıkış")

        choice = input("\nSeçim (1-7): ").strip()

        if choice == '1':
            if master.imaging_available and master.motor_available:
                master.run_full_pipeline()
            else:
                print("❌ Tam sistem mevcut değil!")

        elif choice == '2':
            if master.motor_available:
                master.run_homing_procedure()
            else:
                print("❌ Motor controller mevcut değil!")

        elif choice == '3':
            if master.imaging_available:
                master.run_imaging_pipeline()
            else:
                print("❌ Imaging pipeline mevcut değil!")

        elif choice == '4':
            if master.motor_available:
                coord_files = master.show_available_coordinates()
                if coord_files:
                    try:
                        idx = int(input("Dosya numarası: ")) - 1
                        if 0 <= idx < len(coord_files):
                            file_path = os.path.join(PATHS['OUTPUT_DIR'], coord_files[idx])
                            master.run_motor_controller(file_path)
                        else:
                            print("❌ Geçersiz numara!")
                    except ValueError:
                        print("❌ Geçersiz giriş!")
            else:
                print("❌ Motor controller mevcut değil!")

        elif choice == '5':
            master.test_coordinate_conversion()

        elif choice == '6':
            print_system_info()

        elif choice == '7':
            print("👋 Sistem kapatılıyor...")
            break

        else:
            print("❌ Geçersiz seçim!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Program sonlandırıldı")
    except Exception as e:
        print(f"\n❌ Hata: {e}")