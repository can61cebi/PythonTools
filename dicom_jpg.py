import os
import sys
from pathlib import Path
import logging
from PIL import Image
import numpy as np
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import multiprocessing

try:
    import pydicom
except ImportError:
    print("Hata: pydicom kütüphanesi bulunamadı!")
    print("Yüklemek için: pip install pydicom")
    sys.exit(1)

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dcm_conversion.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class DCMtoJPGConverter:
    def __init__(self, base_directory=None, output_folder_name="converted_jpg"):
        """
        DICOM to JPG dönüştürücü sınıfı
        
        Args:
            base_directory (str): Taranacak ana dizin. None ise mevcut dizin kullanılır.
            output_folder_name (str): Dönüştürülen JPG dosyalarının toplanacağı klasör adı
        """
        self.base_directory = Path(base_directory) if base_directory else Path.cwd()
        self.output_folder = self.base_directory / output_folder_name
        self.converted_count = 0
        self.error_count = 0
        
        # Thread-safe işlemler için lock'lar
        self.counter_lock = threading.Lock()
        self.file_lock = threading.Lock()
        
        # Çıktı klasörünü oluştur
        self.output_folder.mkdir(exist_ok=True)
        
        # Sistem bilgilerini al
        self.cpu_count = multiprocessing.cpu_count()
        print(f"Sistem bilgisi: {self.cpu_count} CPU çekirdeği tespit edildi")
    
    def _increment_converted(self):
        """Thread-safe şekilde başarılı dönüştürme sayacını artır"""
        with self.counter_lock:
            self.converted_count += 1
    
    def _increment_error(self):
        """Thread-safe şekilde hata sayacını artır"""
        with self.counter_lock:
            self.error_count += 1
    
    def _get_unique_output_path(self, base_name):
        """Thread-safe şekilde benzersiz çıktı yolu oluştur"""
        with self.file_lock:
            output_path = self.output_folder / f"{base_name}.jpg"
            counter = 1
            original_output_path = output_path
            
            while output_path.exists():
                name_without_ext = original_output_path.stem
                output_path = self.output_folder / f"{name_without_ext}_{counter}.jpg"
                counter += 1
                
            return output_path
        
    def find_dcm_files(self):
        """
        Tüm .dcm dosyalarını bulur
        
        Returns:
            list: .dcm dosyalarının yollarını içeren liste
        """
        dcm_files = []
        
        # Rekursif olarak tüm .dcm dosyalarını bul
        for dcm_file in self.base_directory.rglob("*.dcm"):
            dcm_files.append(dcm_file)
            
        # Büyük/küçük harf duyarsız arama için .DCM uzantılı dosyalar da dahil
        for dcm_file in self.base_directory.rglob("*.DCM"):
            dcm_files.append(dcm_file)
            
        return dcm_files
    
    def convert_dcm_to_jpg(self, dcm_path, quality=95):
        """
        Tek bir DICOM dosyasını JPG'ye dönüştürür (Thread-safe)
        
        Args:
            dcm_path (Path): DICOM dosyasının yolu
            quality (int): JPG kalitesi (1-100)
            
        Returns:
            tuple: (bool, Path, str) - Başarı durumu, çıktı yolu, mesaj
        """
        try:
            # DICOM dosyasını oku
            ds = pydicom.dcmread(str(dcm_path))
            
            # Pixel verisini al
            if hasattr(ds, 'pixel_array'):
                pixel_array = ds.pixel_array
            else:
                error_msg = f"Pixel verisi bulunamadı: {dcm_path.name}"
                logging.warning(error_msg)
                return False, None, error_msg
            
            # Benzersiz dosya adı oluştur (orijinal klasör yolu dahil)
            relative_path = dcm_path.relative_to(self.base_directory)
            # Klasör ayırıcılarını alt çizgiyle değiştir ve .dcm uzantısını kaldır
            safe_name = str(relative_path.with_suffix('')).replace(os.sep, '_').replace('/', '_').replace('\\', '_')
            
            # Thread-safe benzersiz dosya yolu al
            output_path = self._get_unique_output_path(safe_name)
            
            # Görüntüyü normalize et
            if pixel_array.dtype != np.uint8:
                # 16-bit veya farklı formatları 8-bit'e dönüştür
                pixel_array = pixel_array.astype(np.float64)
                pixel_min, pixel_max = pixel_array.min(), pixel_array.max()
                if pixel_max > pixel_min:  # Sıfır bölmeyi önle
                    pixel_array = (pixel_array - pixel_min) / (pixel_max - pixel_min)
                    pixel_array = (pixel_array * 255).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)
            
            # Görüntü boyutlarını kontrol et
            if len(pixel_array.shape) == 2:
                # Gri tonlamalı görüntü
                image = Image.fromarray(pixel_array, mode='L')
            elif len(pixel_array.shape) == 3:
                # Renkli görüntü
                if pixel_array.shape[2] == 3:
                    image = Image.fromarray(pixel_array, mode='RGB')
                elif pixel_array.shape[2] == 4:
                    image = Image.fromarray(pixel_array, mode='RGBA')
                else:
                    error_msg = f"Desteklenmeyen görüntü formatı: {dcm_path.name}"
                    logging.warning(error_msg)
                    return False, None, error_msg
            else:
                error_msg = f"Desteklenmeyen görüntü boyutu: {dcm_path.name}"
                logging.warning(error_msg)
                return False, None, error_msg
            
            # JPG olarak kaydet
            image.save(str(output_path), 'JPEG', quality=quality, optimize=True)
            
            success_msg = f"✓ {dcm_path.name} -> {output_path.name}"
            logging.info(f"Dönüştürüldü: {dcm_path} -> {output_path}")
            return True, output_path, success_msg
            
        except Exception as e:
            error_msg = f"✗ {dcm_path.name}: {str(e)}"
            logging.error(f"Dönüştürme hatası {dcm_path}: {str(e)}")
            return False, None, error_msg
    
    def convert_all(self, quality=95, max_workers=None):
        """
        Bulunan tüm DICOM dosyalarını multithread ile dönüştürür
        
        Args:
            quality (int): JPG kalitesi (1-100)
            max_workers (int): Maksimum thread sayısı. None ise otomatik hesaplanır.
        """
        print(f"Dizin taranıyor: {self.base_directory}")
        print(f"JPG dosyaları şuraya kaydedilecek: {self.output_folder}")
        
        # Tüm .dcm dosyalarını bul
        dcm_files = self.find_dcm_files()
        
        if not dcm_files:
            print("Hiç .dcm dosyası bulunamadı!")
            return
        
        print(f"Toplam {len(dcm_files)} adet .dcm dosyası bulundu.")
        
        # Thread sayısını belirle
        if max_workers is None:
            # Ryzen 5 5600H için optimize edilmiş thread sayısı
            # I/O yoğun işlemler için CPU çekirdek sayısı * 1.5 - 2 arasında optimal
            max_workers = min(self.cpu_count * 2, 16)  # Maksimum 16 thread
        
        print(f"🚀 {max_workers} thread ile dönüştürme başlatılıyor...")
        
        # İlerleme takibi için
        completed = 0
        start_time = time.time()
        
        # ThreadPoolExecutor ile paralel işleme
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Tüm dosyaları işleme kuyruğuna ekle
            future_to_file = {
                executor.submit(self.convert_dcm_to_jpg, dcm_file, quality): dcm_file 
                for dcm_file in dcm_files
            }
            
            # Sonuçları topla
            for future in as_completed(future_to_file):
                dcm_file = future_to_file[future]
                completed += 1
                
                try:
                    success, output_path, message = future.result()
                    
                    if success:
                        self._increment_converted()
                        print(f"[{completed}/{len(dcm_files)}] {message}")
                    else:
                        self._increment_error()
                        print(f"[{completed}/{len(dcm_files)}] {message}")
                        
                except Exception as exc:
                    self._increment_error()
                    error_msg = f"✗ {dcm_file.name}: Beklenmeyen hata - {str(exc)}"
                    print(f"[{completed}/{len(dcm_files)}] {error_msg}")
                    logging.error(f"Thread hatası {dcm_file}: {str(exc)}")
                
                # İlerleme yüzdesi göster
                if completed % 10 == 0 or completed == len(dcm_files):
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    percentage = (completed / len(dcm_files)) * 100
                    print(f"📊 İlerleme: %{percentage:.1f} - {rate:.1f} dosya/saniye")
        
        # Özet rapor
        elapsed_total = time.time() - start_time
        print(f"\n{'='*50}")
        print(f"🎉 DÖNÜŞTÜRME TAMAMLANDI")
        print(f"{'='*50}")
        print(f"✅ Başarıyla dönüştürülen: {self.converted_count}")
        print(f"❌ Hata sayısı: {self.error_count}")
        print(f"📁 Toplam işlenen: {len(dcm_files)}")
        print(f"⏱️  Toplam süre: {elapsed_total:.2f} saniye")
        print(f"🚀 Ortalama hız: {len(dcm_files)/elapsed_total:.2f} dosya/saniye")
        print(f"💾 JPG dosyaları: {self.output_folder}")
        
        if self.error_count > 0:
            print("⚠️  Hata detayları için 'dcm_conversion.log' dosyasını kontrol edin.")

def main():
    """Ana fonksiyon"""
    print("DICOM to JPG Dönüştürücü")
    print("=" * 40)
    
    # Kullanıcıdan ayarları al
    try:
        # Başlangıç dizini
        directory = input("Taranacak dizin (boş bırakırsanız mevcut dizin kullanılır): ").strip()
        if not directory:
            directory = None
        elif not os.path.exists(directory):
            print(f"Hata: '{directory}' dizini bulunamadı!")
            return
        
        # Çıktı klasörü adı
        output_folder = input("JPG dosyalarının toplanacağı klasör adı (varsayılan 'converted_jpg'): ").strip()
        if not output_folder:
            output_folder = "converted_jpg"
        
        # JPG kalitesi
        quality_input = input("JPG kalitesi (1-100, varsayılan 95): ").strip()
        quality = 95
        if quality_input:
            quality = max(1, min(100, int(quality_input)))
        
        print("\nDönüştürme başlatılıyor...")
        
        # Dönüştürücüyü oluştur ve çalıştır
        converter = DCMtoJPGConverter(directory, output_folder)
        converter.convert_all(quality=quality)
        
    except KeyboardInterrupt:
        print("\n\nİşlem kullanıcı tarafından iptal edildi.")
    except ValueError as e:
        print(f"Hata: Geçersiz değer girildi - {e}")
    except Exception as e:
        print(f"Beklenmeyen hata: {e}")

if __name__ == "__main__":
    main()