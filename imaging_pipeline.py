#!/usr/bin/env python3
"""
Tırnak Tarayıcı Görüntü İşleme Pipeline - X Flip ve Edge Offset Düzeltilmiş
"""

import os
import sys
import numpy as np
import cv2
import time
import json
import matplotlib.pyplot as plt
from picamera2 import Picamera2
from libcamera import controls
from PIL import Image
import argparse

# Ortak konfigürasyonu import et
from shared_config import *

# AI modeli için
try:
    from tflite_runtime.interpreter import Interpreter

    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False


class NailImagingPipeline:
    def __init__(self):
        self.calib_data = None
        self.picam2 = None
        self.output_files = []

        print("=" * 60)
        print("📸 TIRNAK GÖRÜNTÜ İŞLEME SİSTEMİ - KOORDİNAT DÜZELTİLDİ")
        print("=" * 60)
        print("✅ X Flip düzeltildi (False)")
        print("✅ X path yönü düzeltildi (SOLDAN SAĞA)")
        print("✅ Edge offset kaldırıldı")
        print("✅ Gerçek koordinatlar kullanılıyor")
        print(f"✅ Ofset uygulanıyor: X={MOTOR_CONFIG['OFFSET_X']:+.2f}, Y={MOTOR_CONFIG['OFFSET_Y']:+.2f} mm")
        print("=" * 60)

        self.load_calibration()
        create_directories()

    def load_calibration(self):
        """Kamera kalibrasyon verilerini yükle"""
        calib_file = PATHS['CALIBRATION_FILE']
        if not os.path.exists(calib_file):
            raise FileNotFoundError(f"❌ Kalibrasyon dosyası bulunamadı: {calib_file}")

        with open(calib_file, 'r') as f:
            self.calib_data = json.load(f)

        # Görüntü boyutlarını ekle
        self.calib_data['image_width'] = CAMERA_CONFIG['IMAGE_SIZE'][0]
        self.calib_data['image_height'] = CAMERA_CONFIG['IMAGE_SIZE'][1]

        # Anizotropi kontrolü
        px_per_mm_x = self.calib_data['pixels_per_mm_x']
        px_per_mm_y = self.calib_data['pixels_per_mm_y']
        anisotropy_ratio = px_per_mm_x / px_per_mm_y

        print(f"✅ Kalibrasyon yüklendi:")
        print(f"   • X: {px_per_mm_x:.1f} px/mm")
        print(f"   • Y: {px_per_mm_y:.1f} px/mm")
        print(f"   • Anizotropi oranı: {anisotropy_ratio:.3f}")

        if abs(anisotropy_ratio - 1.0) > 0.05:
            print(f"   ⚠️ Anizotropi tespit edildi! X ve Y ölçekleri farklı.")

    def setup_camera(self):
        """Kamera başlatma"""
        print("\n📷 Kamera başlatılıyor...")

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": CAMERA_CONFIG['IMAGE_SIZE']},
            display="main"
        )
        self.picam2.configure(config)
        self.picam2.start()

        # Kamera ayarları
        control_settings = {}
        for key, value in CAMERA_CONFIG['CAMERA_CONTROLS'].items():
            if key == "AfMode":
                control_settings[key] = getattr(controls.AfModeEnum, value)
            else:
                control_settings[key] = value

        self.picam2.set_controls(control_settings)
        time.sleep(2)
        print("✅ Kamera hazır")

    def capture_image_interactive(self):
        """Canlı önizleme ile görüntü yakalama"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_path = os.path.join(PATHS['TEMP_DIR'], f"nail_capture_{timestamp}.jpg")

        cv2.namedWindow("Tırnak Görüntüleme", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tırnak Görüntüleme", 800, 600)

        print("\n📸 Görüntü yakalama modu:")
        print("   • 'q': Fotoğraf çek")
        print("   • 'ESC': İptal")

        captured_image_path = None

        try:
            while True:
                frame = self.picam2.capture_array()
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Görüntü üzerine bilgi ekle
                display_frame = frame_rgb.copy()
                h, w = display_frame.shape[:2]

                # Üst bilgi
                cv2.putText(display_frame, "'q': Foto Cek | 'ESC': Iptal",
                            (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Merkez işareti
                cv2.line(display_frame, (w // 2 - 20, h // 2), (w // 2 + 20, h // 2), (0, 255, 255), 2)
                cv2.line(display_frame, (w // 2, h // 2 - 20), (w // 2, h // 2 + 20), (0, 255, 255), 2)

                # Origin noktası (sağ alt)
                origin_x = w - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT']
                origin_y = h - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM']
                cv2.circle(display_frame, (origin_x, origin_y), 10, (255, 0, 0), -1)
                cv2.putText(display_frame, "ORIGIN", (origin_x - 30, origin_y - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

                # X ve Y eksen yönleri
                cv2.arrowedLine(display_frame, (origin_x, origin_y), (origin_x - 50, origin_y),
                                (0, 255, 0), 2, tipLength=0.3)
                cv2.putText(display_frame, "X+", (origin_x - 60, origin_y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                cv2.arrowedLine(display_frame, (origin_x, origin_y), (origin_x, origin_y - 50),
                                (0, 0, 255), 2, tipLength=0.3)
                cv2.putText(display_frame, "Y+", (origin_x + 10, origin_y - 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                cv2.imshow("Tırnak Görüntüleme", display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    cv2.imwrite(image_path, frame_rgb)
                    captured_image_path = image_path
                    print(f"✅ Görüntü kaydedildi: {os.path.basename(image_path)}")
                    break
                elif key == 27:  # ESC
                    print("❌ İptal edildi")
                    break

        finally:
            cv2.destroyAllWindows()

        return captured_image_path

    def run_ai_segmentation(self, image_path):
        """AI ile tırnak segmentasyonu"""
        if not AI_AVAILABLE or not SYSTEM_CONFIG['ENABLE_AI_MODEL']:
            print("🎭 Mock segmentasyon kullanılıyor...")
            return self.create_mock_segmentation(image_path)

        try:
            print("\n🤖 AI segmentasyonu başlıyor...")
            interpreter = Interpreter(model_path=PATHS['MODEL_PATH'])
            interpreter.allocate_tensors()

            input_details = interpreter.get_input_details()
            output_details = interpreter.get_output_details()

            image = cv2.imread(image_path)
            original_height, original_width = image.shape[:2]

            # Padding için 512'nin katına yuvarla
            padded_height = ((original_height + 511) // 512) * 512
            padded_width = ((original_width + 511) // 512) * 512
            pad_bottom = padded_height - original_height
            pad_right = padded_width - original_width

            image = cv2.copyMakeBorder(image, 0, pad_bottom, 0, pad_right,
                                       cv2.BORDER_CONSTANT, value=[0, 0, 0])
            height, width = image.shape[:2]

            # Patch bazlı işleme
            patch_size = AI_CONFIG['PATCH_SIZE']
            stride = AI_CONFIG['STRIDE']
            full_mask = np.zeros((height, width), dtype=np.float32)
            overlap_count = np.zeros((height, width), dtype=np.float32)

            patch_count = 0
            for y in range(0, height - patch_size[1] + 1, stride[1]):
                for x in range(0, width - patch_size[0] + 1, stride[0]):
                    patch = image[y:y + patch_size[1], x:x + patch_size[0]]

                    if patch.shape[:2] != patch_size:
                        patch = cv2.resize(patch, patch_size)

                    patch_pil = Image.fromarray(cv2.cvtColor(patch, cv2.COLOR_BGR2RGB))
                    input_data = np.array(patch_pil).astype(np.float32)
                    input_data = np.expand_dims(input_data, axis=0) / 255.0

                    interpreter.set_tensor(input_details[0]['index'], input_data)
                    interpreter.invoke()

                    output_data = interpreter.get_tensor(output_details[0]['index'])
                    mask_patch = output_data[0, :, :, 0]

                    if mask_patch.shape != patch_size:
                        mask_patch = cv2.resize(mask_patch, patch_size)

                    patch_height, patch_width = patch.shape[:2]
                    full_mask[y:y + patch_height, x:x + patch_width] += mask_patch[:patch_height, :patch_width]
                    overlap_count[y:y + patch_height, x:x + patch_width] += 1
                    patch_count += 1

            # Normalize et ve padding'i kaldır
            full_mask = np.divide(full_mask, overlap_count, where=overlap_count > 0)
            full_mask = full_mask[:original_height, :original_width]
            binary_mask = (full_mask > AI_CONFIG['CONFIDENCE_THRESHOLD']).astype(np.uint8) * 255

            print(f"✅ AI segmentasyonu tamamlandı ({patch_count} patch)")
            original_image = cv2.imread(image_path)
            return original_image, binary_mask

        except Exception as e:
            print(f"❌ AI segmentasyon hatası: {e}")
            print("🎭 Mock segmentasyon kullanılıyor...")
            return self.create_mock_segmentation(image_path)

    def create_mock_segmentation(self, image_path):
        """Test için basit segmentasyon"""
        image = cv2.imread(image_path)
        height, width = image.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)

        # Basit elips şekli
        center_x, center_y = width // 2, height // 2
        cv2.ellipse(mask, (center_x, center_y), (200, 150), 0, 0, 360, 255, -1)

        return image, mask

    def filter_nail_contours(self, contours):
        """Tırnak konturlarını filtrele ve sırala"""
        if not contours:
            raise ValueError("❌ Hiç kontur bulunamadı!")

        # ANİZOTROPİ DÜZELTMESİ
        px_per_mm_x = self.calib_data['pixels_per_mm_x']
        px_per_mm_y = self.calib_data['pixels_per_mm_y']
        avg_px_per_mm2 = px_per_mm_x * px_per_mm_y  # Geometrik ortalama değil, çarpım

        min_area_px = PATH_CONFIG['MIN_NAIL_AREA_MM2'] * avg_px_per_mm2
        max_area_px = PATH_CONFIG['MAX_NAIL_AREA_MM2'] * avg_px_per_mm2
        min_area_px = max(min_area_px, PATH_CONFIG['MIN_NAIL_AREA_PX'])

        filtered_nails = []
        for contour in contours:
            area_px = cv2.contourArea(contour)
            area_mm2 = area_px / avg_px_per_mm2

            if min_area_px <= area_px <= max_area_px:
                # Centroid (ağırlık merkezi) hesapla - boundingRect'ten daha güvenilir
                M = cv2.moments(contour)
                if M['m00'] > 0:
                    centroid_x = M['m10'] / M['m00']
                else:
                    centroid_x = cv2.boundingRect(contour)[0]

                filtered_nails.append({
                    'contour': contour,
                    'area_px': area_px,
                    'area_mm2': area_mm2,
                    'centroid_x': centroid_x,
                    'id': 0  # Sıralama sonrası atanacak
                })

        if not filtered_nails:
            raise ValueError(f"❌ Uygun boyutta tırnak bulunamadı!")

        # Centroid X koordinatına göre sırala (soldan sağa sıralı tarama)
        filtered_nails.sort(key=lambda x: x['centroid_x'])

        # Sıralama sonrası ID'leri sıralı olarak yeniden ata
        for i, nail in enumerate(filtered_nails):
            nail['id'] = i + 1

        print(f"\n🎯 Tırnak analizi (soldan sağa sıralı):")
        for nail in filtered_nails:
            print(f"   • Tırnak {nail['id']}: {nail['area_mm2']:.1f} mm² (X merkez: {nail['centroid_x']:.0f} px)")

        return filtered_nails

    def create_adaptive_zigzag_path(self, nail_contour):
        """
        Kontur-Adaptif Zigzag Tarama Algoritması - EDGE OFFSET KALDIRILDI
        """
        print(f"   📍 Zigzag path oluşturuluyor (edge offset YOK)...")

        # ANİZOTROPİ İÇİN AYRI ÖLÇEKLER
        px_per_mm_x = self.calib_data['pixels_per_mm_x']
        px_per_mm_y = self.calib_data['pixels_per_mm_y']

        # 1. KONTUR ANALİZİ
        M = cv2.moments(nail_contour)
        if M['m00'] == 0:
            raise ValueError("Geçersiz kontur - alan sıfır!")

        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])

        # Kontur düzeltme
        epsilon = 0.01 * cv2.arcLength(nail_contour, True)
        smooth_contour = cv2.approxPolyDP(nail_contour, epsilon, True)

        # 2. DİREKT KONTUR KULLAN - EDGE OFFSET YOK
        working_contour = nail_contour  # Gerçek sınırları kullan
        print(f"      • Edge offset YOK - gerçek tırnak sınırları kullanılıyor")

        # 3. TARAMA PARAMETRELERİ - ANİZOTROPİK
        strip_width_mm = PATH_CONFIG['STRIP_WIDTH']
        point_spacing_mm = PATH_CONFIG['POINT_SPACING']

        strip_width_px = strip_width_mm * px_per_mm_x  # X ekseni için
        point_spacing_y_px = point_spacing_mm * px_per_mm_y  # Y ekseni için

        # Overlap için strip genişliğini azalt
        overlap_factor = PATH_CONFIG['OVERLAP_FACTOR']
        effective_strip_width = strip_width_px * overlap_factor

        # 4. BOUNDING BOX VE X POZİSYONLARI
        x_min, y_min, width, height = cv2.boundingRect(working_contour)
        x_max = x_min + width
        y_max = y_min + height

        # X pozisyonlarını hesapla (SOLDAN SAĞA - Motor yönüne uyumlu)
        x_positions = []
        current_x = x_min  # Sol kenardan başla

        while current_x <= x_max:
            x_positions.append(current_x)
            current_x += effective_strip_width

        # En sağ noktayı da ekle
        if len(x_positions) == 0 or (x_max - x_positions[-1]) > effective_strip_width * 0.5:
            x_positions.append(x_max)

        if SYSTEM_CONFIG['DEBUG_MODE']:
            print(f"      • Şerit sayısı: {len(x_positions)}")
            print(f"      • X yönü: SOLDAN SAĞA (motor uyumlu)")
            print(f"      • X ölçek: {px_per_mm_x:.1f} px/mm")
            print(f"      • Y ölçek: {px_per_mm_y:.1f} px/mm")

        # 5. ZİGZAG PATH OLUŞTURMA
        path = []
        going_up = True

        for strip_idx, x_pos in enumerate(x_positions):
            # Bu X konumundaki Y sınırlarını bul
            y_bounds = []

            for y in range(y_min - 5, y_max + 5):
                if cv2.pointPolygonTest(working_contour, (int(x_pos), y), False) >= 0:
                    y_bounds.append(y)

            if not y_bounds:
                continue

            min_y = min(y_bounds)
            max_y = max(y_bounds)

            # Y noktalarını oluştur (Y ölçeği ile)
            if going_up:
                y_points = np.arange(max_y, min_y - point_spacing_y_px / 2, -point_spacing_y_px)
            else:
                y_points = np.arange(min_y, max_y + point_spacing_y_px / 2, point_spacing_y_px)

            # Noktaları path'e ekle
            strip_points = []
            for y in y_points:
                point = (int(x_pos), int(y))
                if cv2.pointPolygonTest(working_contour, point, False) >= 0:
                    strip_points.append(point)

            # Şerit geçişinde yumuşak bağlantı
            if strip_idx > 0 and len(path) > 0 and len(strip_points) > 0:
                last_point = path[-1]
                next_point = strip_points[0]

                dx = next_point[0] - last_point[0]
                dy = next_point[1] - last_point[1]

                # Anizotropik mesafe hesabı
                dist_mm = np.sqrt((dx / px_per_mm_x) ** 2 + (dy / px_per_mm_y) ** 2)

                if dist_mm > point_spacing_mm * 2:
                    # Ara nokta ekle
                    mid_x = (last_point[0] + next_point[0]) / 2
                    mid_y = (last_point[1] + next_point[1]) / 2
                    mid_point = (int(mid_x), int(mid_y))

                    if cv2.pointPolygonTest(working_contour, mid_point, False) >= 0:
                        path.append(mid_point)

            path.extend(strip_points)
            going_up = not going_up

        # 6. PATH OPTİMİZASYONU - ANİZOTROPİK
        if len(path) > 1:
            optimized_path = [path[0]]
            min_dist_mm = point_spacing_mm * 0.3

            for point in path[1:]:
                last = optimized_path[-1]
                dx = point[0] - last[0]
                dy = point[1] - last[1]

                # Anizotropik mesafe
                dist_mm = np.sqrt((dx / px_per_mm_x) ** 2 + (dy / px_per_mm_y) ** 2)

                if dist_mm >= min_dist_mm:
                    optimized_path.append(point)

            path = optimized_path

        # 7. VALİDASYON
        if len(path) < 10:
            raise ValueError(f"❌ Yetersiz tarama noktası! Üretilen: {len(path)}")

        print(f"      ✅ Path oluşturuldu: {len(path)} nokta")
        return path

    def pixel_to_motor_coordinates(self, pixel_path, image_shape):
        """
        Piksel koordinatlarını motor koordinatlarına dönüştür - MASKELEME YOK
        Direkt mm cinsinden çıktı verir, sadece raporlama yapar
        """
        motor_path = []
        out_of_bounds_count = 0

        # Kalibrasyon değerleri
        px_per_mm_x = self.calib_data['pixels_per_mm_x']
        px_per_mm_y = self.calib_data['pixels_per_mm_y']

        # Origin noktası
        img_height, img_width = image_shape[:2]
        origin_x_px = img_width - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT']
        origin_y_px = img_height - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM']

        print(f"      📐 Koordinat dönüşümü:")
        print(f"         Origin: ({origin_x_px}, {origin_y_px}) px")
        print(f"         X Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']}")
        print(f"         Y Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']}")
        print(f"         X Ofset: {MOTOR_CONFIG['OFFSET_X']:+.2f} mm")
        print(f"         Y Ofset: {MOTOR_CONFIG['OFFSET_Y']:+.2f} mm")

        for px, py in pixel_path:
            # Origin'e göre relatif pozisyon (piksel)
            rel_px = origin_x_px - px  # X+ sola doğru (görüntüde)
            rel_py = origin_y_px - py  # Y+ yukarı doğru (görüntüde)

            # mm'ye çevir (anizotropik)
            x_mm = rel_px / px_per_mm_x
            y_mm = rel_py / px_per_mm_y

            # Motor koordinat sistemine dönüştür
            if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']:
                motor_x_mm = -x_mm
            else:
                motor_x_mm = x_mm

            if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']:
                motor_y_mm = -y_mm
            else:
                motor_y_mm = y_mm

            # Kamera-Motor ofset değerlerini uygula
            motor_x_mm += MOTOR_CONFIG['OFFSET_X']
            motor_y_mm += MOTOR_CONFIG['OFFSET_Y']

            # Çalışma alanı kontrolü - maskeleme yerine raporlama
            if (MOTOR_CONFIG['X_AXIS_MIN'] <= motor_x_mm <= MOTOR_CONFIG['X_AXIS_MAX'] and
                    MOTOR_CONFIG['Y_AXIS_MIN'] <= motor_y_mm <= MOTOR_CONFIG['Y_AXIS_MAX']):
                motor_path.append((motor_x_mm, motor_y_mm))
            else:
                out_of_bounds_count += 1
                if out_of_bounds_count <= 5:  # İlk 5 tanesini göster
                    print(f"         ⚠️ Sınır dışı: Piksel({px},{py}) → Motor({motor_x_mm:.2f},{motor_y_mm:.2f})")

        # Sınır dışı nokta özeti
        if out_of_bounds_count > 0:
            print(f"      ⚠️ Toplam {out_of_bounds_count}/{len(pixel_path)} nokta çalışma alanı dışında")

        # Eğer hiç nokta kalmadıysa detaylı analiz
        if len(motor_path) == 0:
            print(f"      ❌ HİÇBİR nokta çalışma alanında değil!")
            print(
                f"      📐 Motor çalışma alanı: X[{MOTOR_CONFIG['X_AXIS_MIN']},{MOTOR_CONFIG['X_AXIS_MAX']}] Y[{MOTOR_CONFIG['Y_AXIS_MIN']},{MOTOR_CONFIG['Y_AXIS_MAX']}]")

            if len(pixel_path) > 0:
                # Tüm koordinatların aralığını göster
                all_motor_x = []
                all_motor_y = []

                for px, py in pixel_path:
                    rel_px = origin_x_px - px
                    rel_py = origin_y_px - py
                    x_mm = rel_px / px_per_mm_x
                    y_mm = rel_py / px_per_mm_y

                    if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']:
                        motor_x_mm = -x_mm
                    else:
                        motor_x_mm = x_mm

                    if COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']:
                        motor_y_mm = -y_mm
                    else:
                        motor_y_mm = y_mm

                    # Ofsetleri uygula
                    motor_x_mm += MOTOR_CONFIG['OFFSET_X']
                    motor_y_mm += MOTOR_CONFIG['OFFSET_Y']

                    all_motor_x.append(motor_x_mm)
                    all_motor_y.append(motor_y_mm)

                print(f"      📊 Dönüştürülen koordinat aralığı:")
                print(f"         X: [{min(all_motor_x):.2f}, {max(all_motor_x):.2f}] mm")
                print(f"         Y: [{min(all_motor_y):.2f}, {max(all_motor_y):.2f}] mm")

                # İlk birkaç örnek dönüşüm
                print(f"      📍 Örnek dönüşümler (ilk 3):")
                for i in range(min(3, len(pixel_path))):
                    print(f"         Piksel{pixel_path[i]} → Motor({all_motor_x[i]:.2f},{all_motor_y[i]:.2f})")

        else:
            print(f"      ✅ {len(motor_path)}/{len(pixel_path)} nokta çalışma alanında")

        return motor_path

    def generate_all_nail_paths(self, binary_mask):
        """Tüm tırnaklar için path oluştur"""
        print("\n🗺️ PATH PLANNING BAŞLIYOR...")

        # Konturları bul
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filtreleme
        filtered_nails = self.filter_nail_contours(contours)

        # Her tırnak için path oluştur
        all_results = []
        total_points = 0
        failed_nails = []

        for nail_data in filtered_nails:
            nail_id = nail_data['id']
            nail_contour = nail_data['contour']
            nail_area = nail_data['area_mm2']

            print(f"\n📍 Tırnak {nail_id} işleniyor ({nail_area:.1f} mm²)...")

            try:
                # Piksel path oluştur
                pixel_path = self.create_adaptive_zigzag_path(nail_contour)

                # Motor koordinatlarına çevir
                motor_path = self.pixel_to_motor_coordinates(pixel_path, binary_mask.shape)

                if len(motor_path) < 10:
                    raise ValueError(f"Çalışma alanı içinde yeterli nokta yok: {len(motor_path)}")

                # Sonucu kaydet
                result = {
                    'id': nail_id,
                    'contour': nail_contour,
                    'pixel_path': pixel_path,
                    'motor_path': motor_path,
                    'area_mm2': nail_area,
                    'point_count': len(motor_path),
                    'origin_info': {
                        'origin_x_px': binary_mask.shape[1] - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT'],
                        'origin_y_px': binary_mask.shape[0] - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM'],
                        'image_width': binary_mask.shape[1],
                        'image_height': binary_mask.shape[0]
                    }
                }

                all_results.append(result)
                total_points += len(motor_path)
                print(f"   ✅ Başarılı: {len(motor_path)} nokta")

            except Exception as e:
                print(f"   ❌ HATA: {e}")
                failed_nails.append(nail_id)
                continue

        # Özet
        print("\n" + "=" * 40)
        print("📊 PATH PLANNING ÖZET:")
        print(f"   • Başarılı: {len(all_results)}/{len(filtered_nails)} tırnak")
        print(f"   • Toplam nokta: {total_points}")

        if failed_nails:
            print(f"   • Başarısız tırnaklar: {failed_nails}")

        if not all_results:
            raise ValueError("❌ HİÇBİR tırnak için path oluşturulamadı!")

        return all_results

    def save_coordinate_files(self, all_nail_results, timestamp):
        """Koordinatları dosyalara kaydet - SADELEŞTİRİLMİŞ"""
        print("\n💾 Koordinatlar kaydediliyor (mm cinsinden)...")

        # Eski dosyaları temizle
        self.cleanup_old_files()

        saved_files = []

        # Origin bilgisi
        if all_nail_results:
            origin_info = all_nail_results[0]['origin_info']

        # Her tırnak için ayrı dosya
        for nail in all_nail_results:
            nail_id = nail['id']
            motor_path = nail['motor_path']

            filename = os.path.join(PATHS['OUTPUT_DIR'], f"nail_{nail_id}_path_{timestamp}.txt")

            with open(filename, 'w') as f:
                f.write(f"# Tırnak {nail_id} - Zigzag Tarama Koordinatları\n")
                f.write(f"# Alan: {nail['area_mm2']:.1f} mm²\n")
                f.write(f"# Nokta sayısı: {len(motor_path)}\n")
                f.write(f"# Strip width: {PATH_CONFIG['STRIP_WIDTH']} mm\n")
                f.write(f"# Point spacing: {PATH_CONFIG['POINT_SPACING']} mm\n")
                f.write(f"# Edge offset: KALDIRILDI - gerçek sınırlar kullanılıyor\n")
                f.write(f"#\n")
                f.write(f"# KOORDİNAT SİSTEMİ:\n")
                f.write(f"# Birim: mm (milimetre)\n")
                f.write(f"# Motor X+: Sağa, Y+: İleri\n")
                f.write(f"# Motor home pozisyonu: (0, 0)\n")
                f.write(f"# X Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']} (DÜZELTİLDİ)\n")
                f.write(f"# Y Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_Y_FLIP']}\n")
                f.write(f"#\n")
                f.write("# Index, X(mm), Y(mm)\n")

                for i, (x, y) in enumerate(motor_path):
                    f.write(f"{i:4d}, {x:8.3f}, {y:8.3f}\n")

            saved_files.append(filename)
            print(f"   • Tırnak {nail_id}: {os.path.basename(filename)}")

        # Birleşik dosya
        combined_file = os.path.join(PATHS['OUTPUT_DIR'], f"all_nails_path_{timestamp}.txt")

        with open(combined_file, 'w') as f:
            f.write("# TÜM TIRNAKLAR - Zigzag Tarama Koordinatları\n")
            f.write(f"# Toplam tırnak: {len(all_nail_results)}\n")
            f.write(f"# Tarih: {timestamp}\n")
            f.write(f"# Edge offset: KALDIRILDI\n")
            f.write(f"# X Flip: {COORDINATE_SYSTEM['IMAGE_TO_MOTOR_X_FLIP']} (DÜZELTİLDİ)\n")
            f.write(f"#\n")
            f.write(f"# KOORDİNAT SİSTEMİ:\n")
            f.write(f"# Birim: mm (milimetre)\n")
            f.write(f"# Motor X+: Sağa, Y+: İleri\n")
            f.write(f"# Motor home pozisyonu: (0, 0)\n")
            f.write(f"#\n")
            f.write("# Nail_ID, Index, X(mm), Y(mm)\n")

            for nail in all_nail_results:
                nail_id = nail['id']
                motor_path = nail['motor_path']

                f.write(f"\n# === Tırnak {nail_id} başlangıç ===\n")
                for i, (x, y) in enumerate(motor_path):
                    f.write(f"{nail_id:2d}, {i:4d}, {x:8.3f}, {y:8.3f}\n")

        saved_files.append(combined_file)
        print(f"   • Birleşik dosya: {os.path.basename(combined_file)}")

        return saved_files

    def visualize_results(self, original_image, binary_mask, all_nail_results, timestamp):
        """Sonuçları görselleştir - Sıralama ve renkler doğru eşleştirilmiş"""
        if not SYSTEM_CONFIG['ENABLE_VISUALIZATION']:
            return None

        print("\n📊 Görselleştirme oluşturuluyor...")

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'Tırnak Tarama Analizi - {timestamp}\n(Tarama sırası: 1 → {len(all_nail_results)})',
                     fontsize=14, fontweight='bold')

        # BGR renk paleti (OpenCV subplot'ları için)
        colors_bgr = [(255, 0, 0), (0, 180, 0), (0, 0, 255), (255, 200, 0), (255, 0, 255)]
        # RGB normalize renk paleti (matplotlib subplot'ları için - BGR'den dönüştürülmüş)
        colors_rgb = [(b / 255.0, g / 255.0, r / 255.0) for (r, g, b) in colors_bgr]

        # 1. Orijinal görüntü + Origin
        axes[0, 0].imshow(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))
        h, w = original_image.shape[:2]
        origin_x = w - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_RIGHT']
        origin_y = h - COORDINATE_SYSTEM['IMAGE_ORIGIN_FROM_BOTTOM']
        axes[0, 0].scatter([origin_x], [origin_y], c='red', s=200, marker='x', linewidth=3)
        axes[0, 0].annotate('ORIGIN', (origin_x, origin_y), xytext=(origin_x - 50, origin_y - 30),
                            color='red', fontsize=10, fontweight='bold')
        axes[0, 0].set_title('Orijinal Görüntü')
        axes[0, 0].axis('off')

        # 2. Segmentasyon maskesi + tırnak numaraları
        mask_color = cv2.cvtColor(binary_mask, cv2.COLOR_GRAY2BGR)
        for i, nail in enumerate(all_nail_results):
            color = colors_bgr[i % len(colors_bgr)]
            cv2.drawContours(mask_color, [nail['contour']], -1, color, 3)
            M = cv2.moments(nail['contour'])
            if M['m00'] > 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                cv2.putText(mask_color, str(nail['id']), (cx - 10, cy + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
        axes[0, 1].imshow(cv2.cvtColor(mask_color, cv2.COLOR_BGR2RGB))
        axes[0, 1].set_title(f'AI Segmentasyonu ({len(all_nail_results)} tirnak)')
        axes[0, 1].axis('off')

        # 3. Tarama path'leri (piksel uzayında) + tırnak numaraları
        path_image = original_image.copy()

        for i, nail in enumerate(all_nail_results):
            color = colors_bgr[i % len(colors_bgr)]
            nail_id = nail['id']

            # Kontur çiz
            cv2.drawContours(path_image, [nail['contour']], -1, color, 3)

            # Path çizgileri
            pixel_path = nail['pixel_path']
            if len(pixel_path) > 1:
                # Başlangıç noktası - tırnak renginde daire + beyaz kenarlık
                cv2.circle(path_image, pixel_path[0], 10, (255, 255, 255), -1)
                cv2.circle(path_image, pixel_path[0], 8, color, -1)

                # Bitiş noktası - tırnak renginde kare + beyaz kenarlık
                ex, ey = pixel_path[-1]
                cv2.rectangle(path_image, (ex - 8, ey - 8), (ex + 8, ey + 8), (255, 255, 255), -1)
                cv2.rectangle(path_image, (ex - 6, ey - 6), (ex + 6, ey + 6), color, -1)

                # Path çizgisi
                for j in range(1, len(pixel_path)):
                    cv2.line(path_image, pixel_path[j - 1], pixel_path[j], color, 1)

                # Her 10. nokta
                for j in range(0, len(pixel_path), 10):
                    cv2.circle(path_image, pixel_path[j], 2, color, -1)

            # Tırnak ID etiketi - kontur merkezine yaz
            M = cv2.moments(nail['contour'])
            if M['m00'] > 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                # Beyaz arka plan + renkli metin
                label = str(nail_id)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
                cv2.rectangle(path_image, (cx - tw // 2 - 4, cy - th - 8),
                              (cx + tw // 2 + 4, cy + 4), (255, 255, 255), -1)
                cv2.putText(path_image, label, (cx - tw // 2, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        axes[1, 0].imshow(cv2.cvtColor(path_image, cv2.COLOR_BGR2RGB))
        axes[1, 0].set_title('Zigzag Tarama Rotaları (Piksel)')
        axes[1, 0].axis('off')

        # 4. Motor koordinat grafiği (mm) + tırnak numaraları
        for i, nail in enumerate(all_nail_results):
            motor_path = nail['motor_path']
            if motor_path:
                x_coords = [x for x, y in motor_path]
                y_coords = [y for x, y in motor_path]
                color = colors_rgb[i % len(colors_rgb)]

                axes[1, 1].plot(x_coords, y_coords, '-',
                                color=color, linewidth=1, alpha=0.7,
                                label=f"{nail['id']}. Tirnak ({len(motor_path)} nokta)")

                # Başlangıç - tırnak renginde daire
                axes[1, 1].scatter(x_coords[0], y_coords[0], c=[color],
                                   s=60, marker='o', edgecolors='white', linewidths=1, zorder=5)
                # Bitiş - tırnak renginde kare
                axes[1, 1].scatter(x_coords[-1], y_coords[-1], c=[color],
                                   s=60, marker='s', edgecolors='white', linewidths=1, zorder=5)

                # Tırnak ID etiketi - motor path merkezine yaz
                mid_x = np.mean(x_coords)
                mid_y = np.mean(y_coords)
                axes[1, 1].annotate(str(nail['id']),
                                    (mid_x, mid_y),
                                    fontsize=14, fontweight='bold', color=color,
                                    ha='center', va='center',
                                    bbox=dict(boxstyle='round,pad=0.3',
                                              facecolor='white', edgecolor=color, alpha=0.9),
                                    zorder=10)

        # Motor home pozisyonu
        axes[1, 1].scatter([0], [0], c='red', s=100, marker='x', linewidth=2, label='Motor Home')

        # Çalışma alanı sınırları
        axes[1, 1].axhline(y=MOTOR_CONFIG['Y_AXIS_MIN'], color='gray', linestyle='--', alpha=0.5)
        axes[1, 1].axhline(y=MOTOR_CONFIG['Y_AXIS_MAX'], color='gray', linestyle='--', alpha=0.5)
        axes[1, 1].axvline(x=MOTOR_CONFIG['X_AXIS_MIN'], color='gray', linestyle='--', alpha=0.5)
        axes[1, 1].axvline(x=MOTOR_CONFIG['X_AXIS_MAX'], color='gray', linestyle='--', alpha=0.5)

        axes[1, 1].set_xlabel('X (mm) - Motor Koordinatları')
        axes[1, 1].set_ylabel('Y (mm) - Motor Koordinatları')
        axes[1, 1].set_title('Motor Koordinatları (mm) - Tarama Sırası')
        axes[1, 1].grid(True, alpha=0.3)
        axes[1, 1].legend(loc='best', fontsize=8)
        axes[1, 1].axis('equal')

        plt.tight_layout()

        # Kaydet
        save_path = os.path.join(PATHS['OUTPUT_DIR'], f"analysis_{timestamp}.png")
        plt.savefig(save_path, dpi=120, bbox_inches='tight')

        if SYSTEM_CONFIG['ENABLE_VISUALIZATION']:
            plt.show()
        else:
            plt.close()

        print(f"   ✅ Görselleştirme kaydedildi: {os.path.basename(save_path)}")
        return save_path

    def cleanup_old_files(self):
        """Eski koordinat dosyalarını temizle"""
        try:
            if os.path.exists(PATHS['OUTPUT_DIR']):
                old_files = [f for f in os.listdir(PATHS['OUTPUT_DIR']) if f.endswith('.txt')]
                for f in old_files:
                    os.remove(os.path.join(PATHS['OUTPUT_DIR'], f))
                if old_files:
                    print(f"   🗑️ {len(old_files)} eski dosya silindi")
        except Exception as e:
            print(f"   ⚠️ Temizleme hatası: {e}")

    def run_full_pipeline(self, save_coordinates=True):
        """Ana pipeline işlemi"""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            print("\n" + "=" * 60)
            print("🚀 PIPELINE BAŞLIYOR")
            print("=" * 60)

            # 1. Kamera başlat
            self.setup_camera()

            # 2. Görüntü yakala
            image_path = self.capture_image_interactive()
            if not image_path:
                print("❌ Görüntü yakalanamadı!")
                return None

            # 3. AI segmentasyonu
            original_image, binary_mask = self.run_ai_segmentation(image_path)

            # 4. Path planning
            try:
                all_nail_results = self.generate_all_nail_paths(binary_mask)
            except Exception as e:
                print(f"\n❌ PATH PLANNING HATASI:")
                print(str(e))
                return None

            # 5. Koordinatları kaydet
            if save_coordinates:
                saved_files = self.save_coordinate_files(all_nail_results, timestamp)
                self.output_files.extend(saved_files)

            # 6. Görselleştir
            viz_path = self.visualize_results(original_image, binary_mask,
                                              all_nail_results, timestamp)
            if viz_path:
                self.output_files.append(viz_path)

            # Başarı
            print("\n" + "=" * 60)
            print("✅ PIPELINE BAŞARIYLA TAMAMLANDI!")
            print("✅ X Flip düzeltmesi uygulandı")
            print("✅ X path yönü düzeltildi (SOLDAN SAĞA)")
            print("✅ Edge offset kaldırıldı")
            print("=" * 60)

            if save_coordinates and self.output_files:
                main_file = next((f for f in self.output_files if 'all_nails_path_' in f), None)
                return main_file

            return True

        except Exception as e:
            print(f"\n❌ PIPELINE HATASI: {e}")
            import traceback
            print("\n📋 Detaylı hata:")
            print(traceback.format_exc())
            return None

        finally:
            if self.picam2:
                self.picam2.stop()
                print("📷 Kamera kapatıldı")


def main():
    """Ana program"""
    parser = argparse.ArgumentParser(description='Tırnak Görüntü İşleme Pipeline')
    parser.add_argument('--save-coordinates', action='store_true',
                        default=True, help='Koordinatları kaydet')
    parser.add_argument('--debug', action='store_true',
                        help='Debug modunu aktifleştir')
    args = parser.parse_args()

    if args.debug:
        SYSTEM_CONFIG['DEBUG_MODE'] = True

    try:
        pipeline = NailImagingPipeline()
        result = pipeline.run_full_pipeline(save_coordinates=args.save_coordinates)

        if result:
            print("\n🎉 İşlem başarılı!")
            sys.exit(0)
        else:
            print("\n❌ İşlem başarısız!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⏹️ Kullanıcı tarafından durduruldu")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Program hatası: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()