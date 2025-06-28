import os
import shutil
import json
import time
from PIL import Image, ExifTags
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import hashlib
from datetime import datetime

@dataclass
class ImageInfo:
    """Resim bilgileri için veri sınıfı"""
    filename: str
    width: int
    height: int
    aspect_ratio: float
    file_size: int
    category: str
    hash_value: str
    creation_date: Optional[str] = None

class AdvancedImageSorter:
    def __init__(self, 
                 source_dir=None, 
                 config_file="image_sorter_config.json"):
        self.source_dir = source_dir or os.getcwd()
        self.config_file = config_file
        self.thread_lock = threading.Lock()
        
        # Varsayılan konfigürasyon
        self.default_config = {
            "directories": {
                "landscape": "yatay_resimler",
                "portrait": "dikey_resimler", 
                "square": "kare_resimler",
                "panoramic": "panoramik_resimler",
                "tall": "uzun_resimler"
            },
            "thresholds": {
                "square_tolerance": 0.05,      # %5 tolerans kare için
                "panoramic_ratio": 2.5,        # 2.5:1 oranından büyük = panoramik
                "tall_ratio": 0.4,             # 1:2.5 oranından küçük = uzun dikey
                "almost_square_ratio": 0.1     # %10 tolerans "neredeyse kare" için
            },
            "processing": {
                "max_workers": 12,
                "check_duplicates": True,
                "preserve_metadata": True,
                "create_backup": False,
                "preview_mode": False
            },
            "filters": {
                "min_width": 100,
                "min_height": 100,
                "max_file_size_mb": 100,
                "supported_formats": [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif", ".raw", ".cr2", ".nef"]
            }
        }
        
        self.config = self.load_config()
        
        # İstatistikler
        self.stats = {
            'yatay': 0, 'dikey': 0, 'kare': 0, 'panoramik': 0, 'uzun': 0,
            'dublicate': 0, 'cok_kucuk': 0, 'cok_buyuk': 0, 'hata': 0, 'toplam': 0
        }
        
        self.processed_images: List[ImageInfo] = []
        self.duplicates: Dict[str, List[str]] = {}
        
    def load_config(self) -> dict:
        """Konfigürasyon dosyasını yükle veya oluştur"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"✓ Konfigürasyon yüklendi: {self.config_file}")
                return {**self.default_config, **config}
            except Exception as e:
                print(f"⚠ Konfigürasyon yüklenemedi: {e}")
                
        # Varsayılan konfigürasyonu kaydet
        self.save_config(self.default_config)
        return self.default_config.copy()
    
    def save_config(self, config: dict):
        """Konfigürasyonu dosyaya kaydet"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✓ Konfigürasyon kaydedildi: {self.config_file}")
        except Exception as e:
            print(f"⚠ Konfigürasyon kaydedilemedi: {e}")
    
    def calculate_file_hash(self, filepath: str) -> str:
        """Dosyanın hash değerini hesapla (duplicate detection için)"""
        try:
            with open(filepath, 'rb') as f:
                # İlk 8KB ile hash hesapla (hız için)
                content = f.read(8192)
                return hashlib.md5(content).hexdigest()
        except:
            return ""
    
    def get_image_metadata(self, filepath: str) -> Optional[str]:
        """Resim metadata'sından oluşturulma tarihini al"""
        try:
            with Image.open(filepath) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        tag_name = ExifTags.TAGS.get(tag, tag)
                        if tag_name == "DateTime":
                            return str(value)
        except:
            pass
        
        # EXIF bulunamazsa dosya tarihini kullan
        try:
            timestamp = os.path.getctime(filepath)
            return datetime.fromtimestamp(timestamp).strftime("%Y:%m:%d %H:%M:%S")
        except:
            return None
    
    def categorize_image(self, width: int, height: int) -> str:
        """Gelişmiş resim kategorizasyonu"""
        aspect_ratio = width / height
        thresholds = self.config["thresholds"]
        
        # Kare kontrolü (tolerans ile)
        square_tolerance = thresholds["square_tolerance"]
        if abs(aspect_ratio - 1.0) <= square_tolerance:
            return "kare"
        
        # Neredeyse kare kontrolü
        almost_square_tolerance = thresholds["almost_square_ratio"]
        if abs(aspect_ratio - 1.0) <= almost_square_tolerance:
            print(f"   ⚠ Neredeyse kare resim tespit edildi (oran: {aspect_ratio:.3f})")
            return "kare"  # Neredeyse kare olanları da kare olarak sınıflandır
        
        # Panoramik yatay
        if aspect_ratio >= thresholds["panoramic_ratio"]:
            return "panoramik"
        
        # Uzun dikey
        if aspect_ratio <= thresholds["tall_ratio"]:
            return "uzun"
        
        # Normal yatay/dikey
        if aspect_ratio > 1:
            return "yatay"
        else:
            return "dikey"
    
    def create_directories(self):
        """Tüm hedef klasörleri oluştur"""
        dirs = self.config["directories"]
        created_dirs = []
        
        for category, directory in dirs.items():
            try:
                os.makedirs(directory, exist_ok=True)
                created_dirs.append(directory)
            except Exception as e:
                print(f"⚠ Klasör oluşturulamadı {directory}: {e}")
        
        print(f"✓ {len(created_dirs)} klasör hazırlandı")
        return created_dirs
    
    def is_valid_image(self, filepath: str) -> Tuple[bool, str]:
        """Resmin geçerli olup olmadığını kontrol et"""
        try:
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            filters = self.config["filters"]
            
            # Dosya boyutu kontrolü
            if file_size_mb > filters["max_file_size_mb"]:
                return False, f"çok büyük ({file_size_mb:.1f}MB)"
            
            # Format kontrolü
            ext = Path(filepath).suffix.lower()
            if ext not in filters["supported_formats"]:
                return False, f"desteklenmeyen format ({ext})"
            
            # Resim boyutu kontrolü
            with Image.open(filepath) as img:
                width, height = img.size
                
                if width < filters["min_width"] or height < filters["min_height"]:
                    return False, f"çok küçük ({width}x{height})"
                    
                return True, "geçerli"
                
        except Exception as e:
            return False, f"okunamıyor ({str(e)[:50]})"
    
    def get_image_files(self) -> List[str]:
        """Kaynak dizindeki geçerli resim dosyalarını listele"""
        image_files = []
        invalid_files = []
        
        try:
            all_files = [f for f in os.listdir(self.source_dir) 
                        if os.path.isfile(os.path.join(self.source_dir, f))]
            
            print(f"📁 {len(all_files)} dosya taranıyor...")
            
            for filename in all_files:
                filepath = os.path.join(self.source_dir, filename)
                is_valid, reason = self.is_valid_image(filepath)
                
                if is_valid:
                    image_files.append(filename)
                else:
                    invalid_files.append((filename, reason))
            
            if invalid_files:
                print(f"\n⚠ {len(invalid_files)} geçersiz dosya atlandı:")
                for filename, reason in invalid_files[:5]:  # İlk 5'ini göster
                    print(f"   - {filename}: {reason}")
                if len(invalid_files) > 5:
                    print(f"   ... ve {len(invalid_files) - 5} dosya daha")
            
            print(f"✓ {len(image_files)} geçerli resim dosyası bulundu")
            return image_files
            
        except Exception as e:
            print(f"⚠ Dosya tarama hatası: {e}")
            return []
    
    def process_image(self, filename: str) -> Optional[ImageInfo]:
        """Tek bir resmi analiz et ve işle"""
        source_path = os.path.join(self.source_dir, filename)
        
        try:
            # Resim bilgilerini al
            with Image.open(source_path) as img:
                width, height = img.size
                
            file_size = os.path.getsize(source_path)
            aspect_ratio = width / height
            category = self.categorize_image(width, height)
            
            # Hash hesapla (duplicate detection için)
            hash_value = ""
            if self.config["processing"]["check_duplicates"]:
                hash_value = self.calculate_file_hash(source_path)
            
            # Metadata al
            creation_date = None
            if self.config["processing"]["preserve_metadata"]:
                creation_date = self.get_image_metadata(source_path)
            
            # ImageInfo oluştur
            image_info = ImageInfo(
                filename=filename,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
                file_size=file_size,
                category=category,
                hash_value=hash_value,
                creation_date=creation_date
            )
            
            # Duplicate kontrolü
            if hash_value and self.config["processing"]["check_duplicates"]:
                with self.thread_lock:
                    if hash_value in self.duplicates:
                        self.duplicates[hash_value].append(filename)
                        self.stats['dublicate'] += 1
                        print(f"🔄 {filename} -> DUBLICATE (benzer: {self.duplicates[hash_value][0]})")
                        return image_info
                    else:
                        self.duplicates[hash_value] = [filename]
            
            # Preview modda dosya kopyalama
            if not self.config["processing"]["preview_mode"]:
                target_dir = self.config["directories"].get(
                    {"yatay": "landscape", "dikey": "portrait", "kare": "square", 
                     "panoramik": "panoramic", "uzun": "tall"}.get(category, "landscape")
                )
                
                if not target_dir:
                    target_dir = self.config["directories"]["landscape"]
                
                # Hedef dosya yolu
                target_path = os.path.join(target_dir, filename)
                
                # Aynı isimde dosya varsa yeni isim oluştur
                counter = 1
                original_target_path = target_path
                while os.path.exists(target_path):
                    name, ext = os.path.splitext(original_target_path)
                    target_path = f"{name}_({counter}){ext}"
                    counter += 1
                
                # Dosyayı kopyala
                shutil.copy2(source_path, target_path)
            
            # İstatistikleri güncelle
            with self.thread_lock:
                category_key = {"yatay": "yatay", "dikey": "dikey", "kare": "kare", 
                               "panoramik": "panoramik", "uzun": "uzun"}.get(category, "yatay")
                self.stats[category_key] += 1
                self.stats['toplam'] += 1
            
            # Detaylı çıktı
            status = "PREVIEW" if self.config["processing"]["preview_mode"] else "MOVED"
            print(f"✓ {filename} -> {category.upper()} ({width}x{height}, {aspect_ratio:.3f}) [{status}]")
            
            return image_info
            
        except Exception as e:
            with self.thread_lock:
                self.stats['hata'] += 1
                self.stats['toplam'] += 1
            print(f"✗ {filename} - Hata: {e}")
            return None
    
    def interactive_config(self):
        """Kullanıcı ile etkileşimli konfigürasyon"""
        print(f"\n{'='*60}")
        print("🔧 GELİŞMİŞ KONFİGÜRASYON")
        print(f"{'='*60}")
        
        # Mevcut ayarları göster
        print("\n📋 Mevcut Ayarlar:")
        print(f"   Kare toleransı: %{self.config['thresholds']['square_tolerance']*100:.1f}")
        print(f"   Panoramik oranı: {self.config['thresholds']['panoramic_ratio']:g}:1")
        print(f"   Uzun dikey oranı: 1:{1/self.config['thresholds']['tall_ratio']:g}")
        print(f"   Thread sayısı: {self.config['processing']['max_workers']}")
        print(f"   Dublicate kontrolü: {'Açık' if self.config['processing']['check_duplicates'] else 'Kapalı'}")
        print(f"   Preview modu: {'Açık' if self.config['processing']['preview_mode'] else 'Kapalı'}")
        
        print(f"\n📁 Hedef Klasörler:")
        for category, folder in self.config['directories'].items():
            print(f"   {category}: {folder}")
        
        # Değişiklik yapmak istiyor mu?
        response = input(f"\nAyarları değiştirmek istiyor musunuz? (e/h): ").strip().lower()
        
        if response == 'e':
            # Kare toleransı
            try:
                tolerance = float(input(f"Kare toleransı (0-1, şu an {self.config['thresholds']['square_tolerance']}): ") or self.config['thresholds']['square_tolerance'])
                self.config['thresholds']['square_tolerance'] = max(0, min(1, tolerance))
            except:
                pass
            
            # Preview modu
            preview = input("Preview modu (sadece analiz, kopyalama yok) (e/h): ").strip().lower()
            self.config['processing']['preview_mode'] = (preview == 'e')
            
            # Dublicate kontrolü
            duplicates = input("Dublicate kontrolü (e/h): ").strip().lower()
            self.config['processing']['check_duplicates'] = (duplicates == 'e')
            
            # Konfigürasyonu kaydet
            self.save_config(self.config)
            print("✓ Konfigürasyon güncellendi!")
    
    def sort_images(self):
        """Ana sıralama fonksiyonu"""
        print(f"\n{'='*60}")
        print("🖼️  GELİŞMİŞ RESİM AYIRMA PROGRAMI")
        print(f"{'='*60}")
        print(f"📂 Kaynak: {self.source_dir}")
        print(f"⚙️  Thread: {self.config['processing']['max_workers']}")
        print(f"🔍 Mod: {'PREVIEW (analiz only)' if self.config['processing']['preview_mode'] else 'PRODUCTION (kopyalama)'}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Konfigürasyon menüsü
        self.interactive_config()
        
        # Klasörleri oluştur (preview modda değilse)
        if not self.config['processing']['preview_mode']:
            self.create_directories()
        
        # Resim dosyalarını al
        image_files = self.get_image_files()
        
        if not image_files:
            print("❌ İşlenecek resim dosyası bulunamadı!")
            return
        
        print(f"\n🚀 {len(image_files)} resim dosyası işlenmeye başlanıyor...\n")
        
        # Multithread ile işle
        with ThreadPoolExecutor(max_workers=self.config['processing']['max_workers']) as executor:
            future_to_filename = {
                executor.submit(self.process_image, filename): filename 
                for filename in image_files
            }
            
            for future in as_completed(future_to_filename):
                filename = future_to_filename[future]
                try:
                    image_info = future.result()
                    if image_info:
                        self.processed_images.append(image_info)
                except Exception as e:
                    print(f"✗ {filename} - Thread hatası: {e}")
        
        # İşlem süresi
        elapsed_time = time.time() - start_time
        
        # Sonuçları yazdır
        self.print_detailed_results(elapsed_time)
        
        # Rapor oluştur
        self.generate_report()
    
    def print_detailed_results(self, elapsed_time: float):
        """Detaylı sonuçları yazdır"""
        print(f"\n{'='*60}")
        print("📊 DETAYLI SONUÇLAR")
        print(f"{'='*60}")
        print(f"⏱️  İşlem süresi: {elapsed_time:.2f} saniye")
        print(f"🏃 Hız: {len(self.processed_images)/elapsed_time:.1f} resim/saniye")
        print(f"\n📈 Kategoriler:")
        print(f"   🔳 Kare resimler: {self.stats['kare']}")
        print(f"   ↔️  Yatay resimler: {self.stats['yatay']}")  
        print(f"   ↕️  Dikey resimler: {self.stats['dikey']}")
        print(f"   🌄 Panoramik: {self.stats['panoramik']}")
        print(f"   🏢 Uzun dikey: {self.stats['uzun']}")
        
        if self.config['processing']['check_duplicates']:
            duplicate_count = sum(len(files)-1 for files in self.duplicates.values() if len(files) > 1)
            print(f"   🔄 Dublicateler: {duplicate_count}")
        
        print(f"   ❌ Hatalar: {self.stats['hata']}")
        print(f"\n📊 Toplam: {self.stats['toplam']} dosya")
        
        # En büyük ve en küçük resimler
        if self.processed_images:
            largest = max(self.processed_images, key=lambda x: x.width * x.height)
            smallest = min(self.processed_images, key=lambda x: x.width * x.height)
            print(f"\n🔍 İstatistikler:")
            print(f"   En büyük: {largest.filename} ({largest.width}x{largest.height})")
            print(f"   En küçük: {smallest.filename} ({smallest.width}x{smallest.height})")
        
        print(f"{'='*60}")
    
    def generate_report(self):
        """JSON raporu oluştur"""
        if not self.processed_images:
            return
            
        report = {
            "timestamp": datetime.now().isoformat(),
            "source_directory": self.source_dir,
            "config": self.config,
            "statistics": self.stats,
            "processed_images": [
                {
                    "filename": img.filename,
                    "dimensions": f"{img.width}x{img.height}",
                    "aspect_ratio": round(img.aspect_ratio, 3),
                    "category": img.category,
                    "file_size_mb": round(img.file_size / (1024*1024), 2),
                    "creation_date": img.creation_date
                }
                for img in self.processed_images
            ]
        }
        
        if self.config['processing']['check_duplicates']:
            duplicates_found = {hash_val: files for hash_val, files in self.duplicates.items() if len(files) > 1}
            report["duplicates"] = duplicates_found
        
        report_file = f"image_sort_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"📄 Detaylı rapor: {report_file}")
        except Exception as e:
            print(f"⚠ Rapor kaydedilemedi: {e}")


def main():
    """Ana fonksiyon"""
    print("🎨 GELİŞMİŞ RESİM AYIRMA PROGRAMI v2.0")
    print("=" * 50)
    print("Bu program akıllı algoritma ile resimleri kategorize eder:")
    print("• Kare resimleri tolerans ile tespit eder")
    print("• Panoramik ve uzun dikey resimleri ayırır") 
    print("• Dublicate resimleri bulur")
    print("• Detaylı raporlama yapar")
    print("• Konfigürasyon dosyası ile özelleştirilebilir")
    print("=" * 50)
    
    # Sorter'ı başlat
    sorter = AdvancedImageSorter()
    sorter.sort_images()


if __name__ == "__main__":
    main()