import os
import hashlib
import random
import string
import shutil
from pathlib import Path
import time
import logging
import re

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('PhotoProcessor')

class PhotoProcessor:
    """
    Fotoğraf dosyalarını işlemek için profesyonel bir araç.
    
    Bu sınıf:
    1. Fotoğrafları benzersiz olarak tespit eder (içeriğe göre)
    2. İsteğe bağlı olarak rastgele isimler atar
    3. İsteğe bağlı olarak sıralı isimler atar (kullanıcının seçtiği bir sayıdan başlayarak)
    """
    def __init__(self):
        # Desteklenen resim dosyası uzantıları
        self.image_extensions = [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif'
        ]
        
        # Zaman damgası (tüm program için ortak)
        self.timestamp = int(time.time())
        
        # Geçici klasör adı
        self.temp_dir = f"temp_processing_{self.timestamp}"
        
        # İşlenmiş dosya kayıtları
        self.processed_files = {}
        self.file_hashes = {}
        self.duplicate_files = {}  # Her hash değeri için tüm kopya dosyaları takip eder
        
    def find_image_files(self, include_pattern=None, exclude_pattern=None):
        """
        Mevcut klasördeki resim dosyalarını bulur.
        """
        image_files = []
        
        # Python dosyalarını hariç tut
        python_files = set(Path('.').glob('*.py'))
        
        # Tüm desteklenen uzantılar için klasörü tara
        for ext in self.image_extensions:
            # Hem küçük hem büyük harfli uzantıları kontrol et
            for pattern in [f'*.{ext}', f'*.{ext.upper()}']:
                for file_path in Path('.').glob(pattern):
                    # Python dosyalarını atla
                    if file_path in python_files:
                        continue
                        
                    # Desenlere göre filtreleme
                    if include_pattern and not re.search(include_pattern, file_path.name):
                        continue
                    if exclude_pattern and re.search(exclude_pattern, file_path.name):
                        continue
                    
                    image_files.append(file_path)
        
        return image_files
    
    def get_file_hash(self, file_path, block_size=65536):
        """
        Dosyanın içeriğinin MD5 hash değerini hesaplar.
        """
        if file_path in self.file_hashes:
            return self.file_hashes[file_path]
            
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                buf = f.read(block_size)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(block_size)
            
            result = hasher.hexdigest()
            self.file_hashes[file_path] = result
            return result
        except Exception as e:
            logger.error(f"Hash hesaplanamadı ({file_path}): {e}")
            # Hash hesaplanamazsa benzersiz bir tanımlayıcı oluştur
            unique_id = f"ERROR_HASH_{str(file_path)}_{random.randint(1000, 9999)}"
            self.file_hashes[file_path] = unique_id
            return unique_id
    
    def find_unique_files(self, files):
        """
        Dosya listesinden benzersiz dosyaları bulur (içeriğe göre).
        Aynı zamanda kopya dosyaları da takip eder.
        """
        unique_files = {}  # {hash: dosya_yolu} - her hash için bir dosya
        duplicates = []    # [(kopya_dosya, orijinal_dosya)] - tüm kopyaları listeler
        
        # Her hash için tüm dosyaları tutacak bir sözlük
        hash_to_files = {}  # {hash: [dosya_yolu1, dosya_yolu2, ...]}
        
        logger.info(f"Benzersizlik kontrolü başlatılıyor ({len(files)} dosya)...")
        
        # İlk geçiş: Tüm dosyaların hash değerlerini hesapla ve gruplandır
        for file_path in files:
            file_hash = self.get_file_hash(file_path)
            
            if file_hash not in hash_to_files:
                hash_to_files[file_hash] = []
            
            hash_to_files[file_hash].append(file_path)
        
        # İkinci geçiş: Her hash grubu için bir "birincil" dosya seç, diğerlerini kopya olarak işaretle
        for file_hash, file_list in hash_to_files.items():
            # Her grup için ilk dosyayı birincil olarak seç
            primary_file = file_list[0]
            unique_files[file_hash] = primary_file
            
            # Diğer dosyaları kopya olarak işaretle
            for duplicate_file in file_list[1:]:
                duplicates.append((duplicate_file, primary_file))
            
            # Tüm kopyaları kaydet (gelecekte referans için)
            self.duplicate_files[file_hash] = file_list
        
        # Kopya dosyaları raporla
        if duplicates:
            logger.info(f"{len(duplicates)} adet kopya dosya tespit edildi:")
            for dup, orig in duplicates[:5]:  # İlk 5 kopyayı göster
                logger.info(f"  - {dup.name} = {orig.name}")
            
            if len(duplicates) > 5:
                logger.info(f"  (ve {len(duplicates) - 5} dosya daha)")
        
        logger.info(f"Toplam {len(unique_files)} benzersiz dosya bulundu.")
        
        # Benzersiz dosyaları ve tüm kopyalarını raporla
        print("\nÖNEMLİ: Bazı dosyalar içerik olarak aynı (kopya) olduğundan birleştirilecektir.")
        print(f"Klasörde toplam {len(files)} dosya var, {len(unique_files)} benzersiz içerik tespit edildi.")
        print(f"Bu işlem sonucunda benzersiz {len(unique_files)} dosya elde edilecektir.")
        
        if duplicates:
            print("\nTespit edilen kopyalar (her satır aynı fotoğrafı temsil eder):")
            
            # Her hash grubu için tüm dosyaları göster
            group_count = 0
            for file_hash, file_list in hash_to_files.items():
                if len(file_list) > 1:  # Sadece birden fazla dosya içeren grupları göster
                    group_count += 1
                    if group_count <= 10:  # İlk 10 grubu göster
                        print(f"\nGrup {group_count}:")
                        for i, file_path in enumerate(file_list, 1):
                            print(f"  {i}. {file_path.name}")
            
            if group_count > 10:
                print(f"\n... ve {group_count - 10} grup daha")
            
        return unique_files
    
    def ensure_temp_directory(self):
        """Geçici işlem klasörünü oluşturur."""
        temp_path = Path(self.temp_dir)
        if not temp_path.exists():
            temp_path.mkdir()
            logger.info(f"Geçici klasör oluşturuldu: {self.temp_dir}")
        return temp_path
    
    def randomize_photos(self):
        """
        Orijinal fotoğrafları rastgele isimlerle geçici klasöre kopyalar.
        """
        logger.info("RASTGELE İSİMLENDİRME AŞAMASI BAŞLADI")
        
        # Tüm resim dosyalarını bul (python dosyaları hariç)
        original_files = self.find_image_files()
        
        if not original_files:
            logger.warning("İşlenecek dosya bulunamadı!")
            return 0
        
        logger.info(f"{len(original_files)} dosya bulundu, benzersizlik kontrolü yapılıyor...")
        
        # Benzersiz dosyaları bul
        unique_files = self.find_unique_files(original_files)
        
        # İşlem onayı
        print("\nİşlenecek benzersiz dosyalar:")
        for i, file_path in enumerate(unique_files.values(), 1):
            if i <= 10:  # İlk 10 dosyayı göster
                print(f"  {i}. {file_path.name}")
            
        if len(unique_files) > 10:
            print(f"  ... ve {len(unique_files) - 10} dosya daha")
            
        user_input = input(f"\nToplam {len(unique_files)} benzersiz dosyayı rastgele isimlendirmek istiyor musunuz? (E/H): ")
        if user_input.upper() != 'E':
            logger.info("İşlem kullanıcı tarafından iptal edildi.")
            return 0
        
        # Geçici klasörü oluştur
        temp_dir = self.ensure_temp_directory()
        
        # Benzersiz dosyaları kopyala ve rastgele isimler ata
        processed_count = 0
        for file_hash, file_path in unique_files.items():
            # Rastgele isim oluştur
            random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            file_ext = file_path.suffix.lower()
            random_name = f"RANDOM_{self.timestamp}_{random_str}{file_ext}"
            target_path = temp_dir / random_name
            
            try:
                # Dosyayı kopyala
                shutil.copy2(file_path, target_path)
                # Orijinal dosya ve yeni adı eşleştir (ileri aşamalar için)
                self.processed_files[file_hash] = target_path
                processed_count += 1
                
                if processed_count <= 10 or processed_count % 10 == 0:
                    logger.info(f"Kopyalandı: {file_path.name} -> {random_name}")
            except Exception as e:
                logger.error(f"Kopyalama hatası ({file_path.name}): {e}")
        
        logger.info(f"Rastgele isimlendirme tamamlandı. {processed_count} dosya işlendi.")
        
        # Orijinal dosyaları silme seçeneği
        if processed_count > 0:
            user_input = input("Tüm orijinal dosyaları silmek istiyor musunuz? (E/H): ")
            if user_input.upper() == 'E':
                removed_count = 0
                
                # Set olarak silinen dosyaları takip et - tekrar silmeyi önler
                removed_files = set()
                
                # Klasörde bulunan tüm resim dosyalarını sil (Kopya dosyalar dahil)
                for file_path in original_files:
                    try:
                        # Dosya zaten silinmiş mi kontrol et
                        if file_path in removed_files or not file_path.exists():
                            continue
                            
                        os.remove(file_path)
                        removed_files.add(file_path)
                        removed_count += 1
                        
                        if removed_count <= 5 or removed_count % 20 == 0:
                            logger.info(f"Silindi: {file_path.name}")
                    except Exception as e:
                        # Eğer dosya zaten silinmişse bu hatayı gösterme
                        if "No such file or directory" not in str(e) and "The system cannot find the file specified" not in str(e):
                            logger.error(f"Silme hatası ({file_path.name}): {e}")
                
                logger.info(f"{removed_count} orijinal dosya silindi.")
        
        return processed_count
    
    def sequentially_rename_photos(self):
        """
        Rastgele adlandırılmış fotoğrafları sıralı olarak yeniden adlandırır.
        """
        logger.info("SIRALI İSİMLENDİRME AŞAMASI BAŞLADI")
        
        # Geçici klasör kontrolü
        temp_dir = Path(self.temp_dir)
        if not temp_dir.exists() or not temp_dir.is_dir():
            # Geçici klasör yoksa, mevcut klasördeki RANDOM_ ile başlayan dosyaları kullan
            logger.info("Geçici klasör bulunamadı, mevcut klasör içindeki rastgele adlandırılmış dosyalar kullanılacak.")
            include_pattern = r'^RANDOM_'
            random_files = self.find_image_files(include_pattern=include_pattern)
            source_dir = Path('.')
        else:
            # Geçici klasördeki tüm dosyaları al
            random_files = list(temp_dir.glob('*.*'))
            source_dir = temp_dir
        
        if not random_files:
            logger.warning("İşlenecek rastgele adlandırılmış dosya bulunamadı!")
            return 0
        
        # Dosyaları sırala (isimlendirme sırasına göre)
        sorted_files = sorted(random_files, key=lambda x: x.name)
        
        logger.info(f"{len(sorted_files)} rastgele adlandırılmış dosya bulundu.")
        
        # İşlem onayı
        print("\nSıralı adlandırılacak dosyalar:")
        for i, file_path in enumerate(sorted_files[:5], 1):
            print(f"  {i}. {file_path.name}")
        
        if len(sorted_files) > 5:
            print(f"  ... ve {len(sorted_files) - 5} dosya daha")
        
        user_input = input(f"\nToplam {len(sorted_files)} dosyayı sıralı olarak adlandırmak istiyor musunuz? (E/H): ")
        if user_input.upper() != 'E':
            logger.info("İşlem kullanıcı tarafından iptal edildi.")
            return 0
        
        # Başlangıç numarasını sor
        while True:
            try:
                starting_number = int(input("Yeniden adlandırmaya hangi sayıdan başlamak istiyorsunuz? "))
                break
            except ValueError:
                print("Lütfen geçerli bir sayı girin.")
        
        # Benzersiz dosyaları yeniden adlandır
        processed_count = 0
        
        for i, file_path in enumerate(sorted_files, starting_number):
            # Dosya uzantısını al
            file_ext = file_path.suffix.lower()
            
            # Hedef isim oluştur (001.jpg, 002.jpg, ...)
            target_name = f"{i:03d}{file_ext}"
            target_path = Path('.') / target_name
            
            try:
                # DÜZELTME: Dosya yollarını doğru şekilde birleştir
                if source_dir == Path('.'):
                    # Mevcut klasördeki dosyalar için
                    source_file = file_path
                else:
                    # Geçici klasördeki dosyalar için
                    source_file = source_dir / file_path.name
                
                # Hedef dosya zaten varsa sil
                if target_path.exists():
                    os.remove(target_path)
                
                # Dosyayı kopyala
                shutil.copy2(source_file, target_path)
                processed_count += 1
                
                if processed_count <= 10 or processed_count % 10 == 0:
                    logger.info(f"Kopyalandı: {file_path.name} -> {target_name}")
            except Exception as e:
                logger.error(f"Kopyalama hatası ({file_path.name}): {e}")
        
        logger.info(f"Sıralı adlandırma tamamlandı. {processed_count} dosya işlendi.")
        
        # Rastgele adlandırılmış dosyaları silme seçeneği
        if processed_count > 0:
            user_input = input("Rastgele adlandırılmış dosyaları silmek istiyor musunuz? (E/H): ")
            if user_input.upper() == 'E':
                removed_count = 0
                
                # Geçici klasördeki tüm dosyaları sil
                if temp_dir.exists() and temp_dir.is_dir():
                    try:
                        # Önce klasördeki dosyaları tek tek sil
                        for file_path in temp_dir.glob('*.*'):
                            try:
                                os.remove(file_path)
                                removed_count += 1
                            except Exception as e:
                                logger.error(f"Dosya silme hatası ({file_path.name}): {e}")
                        
                        # Sonra klasörü sil
                        os.rmdir(temp_dir)
                        logger.info(f"Geçici klasör silindi: {self.temp_dir} ({removed_count} dosya)")
                    except Exception as e:
                        logger.error(f"Geçici klasör silme hatası: {e}")
                else:
                    # Klasördeki RANDOM_ ile başlayan dosyaları sil
                    for file_path in sorted_files:
                        if file_path.exists():  # Dosyanın hala mevcut olduğundan emin ol
                            try:
                                os.remove(file_path)
                                removed_count += 1
                                
                                if removed_count <= 5 or removed_count % 20 == 0:
                                    logger.info(f"Silindi: {file_path.name}")
                            except Exception as e:
                                logger.error(f"Silme hatası ({file_path.name}): {e}")
                
                logger.info(f"{removed_count} rastgele adlandırılmış dosya silindi.")
        
        return processed_count
    
    def cleanup_temp_directory(self):
        """Geçici klasörü temizler."""
        temp_dir = Path(self.temp_dir)
        if temp_dir.exists() and temp_dir.is_dir():
            try:
                # Önce klasördeki dosyaları tek tek sil
                for file_path in temp_dir.glob('*.*'):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Geçici dosya silme hatası ({file_path.name}): {e}")
                
                # Sonra klasörü sil
                os.rmdir(temp_dir)
                logger.info(f"Geçici klasör temizlendi: {self.temp_dir}")
                return True
            except Exception as e:
                logger.warning(f"Geçici klasör temizleme hatası: {e}")
                return False
        return True  # Klasör zaten yok
    
    def process_all(self):
        """Tüm işlem adımlarını çalıştırır."""
        print("=" * 50)
        print("FOTOĞRAF İŞLEME PROGRAMI")
        print("=" * 50)
        
        try:
            print("\nBilgi: Bu program, aynı içeriğe sahip kopya dosyaları tespit edecek")
            print("ve sadece benzersiz dosyaları işleyerek gereksiz tekrarları önleyecektir.")
            print("=" * 50)
            
            # 1. Aşama: Rastgele isimlendirme
            randomized_count = self.randomize_photos()
            
            if randomized_count == 0:
                print("\nRastgele isimlendirme aşaması gerçekleştirilemedi veya iptal edildi.")
                # Temizlik yap ve çık
                self.cleanup_temp_directory()
                return
            
            # 2. Aşama: Sıralı isimlendirme
            sequential_count = self.sequentially_rename_photos()
            
            if sequential_count == 0:
                print("\nSıralı isimlendirme aşaması gerçekleştirilemedi veya iptal edildi.")
            
            # İşlem özeti
            print("\n" + "=" * 50)
            print("İŞLEM ÖZETİ")
            print("-" * 50)
            print(f"Başlangıçta bulunan toplam dosya sayısı: {len(self.file_hashes)}")
            print(f"Tespit edilen benzersiz dosya sayısı: {randomized_count}")
            print(f"Sıralı adlandırılan dosya sayısı: {sequential_count}")
            print("=" * 50)
            
            # Geçici klasörü temizle
            self.cleanup_temp_directory()
            
        except KeyboardInterrupt:
            print("\nİşlem kullanıcı tarafından kesildi.")
            # Temizlik yap
            self.cleanup_temp_directory()
        except Exception as e:
            logger.error(f"İşlem sırasında beklenmeyen hata: {e}")
            # Temizlik yap
            self.cleanup_temp_directory()
        finally:
            print("\nProgram sonlandırıldı.")

if __name__ == "__main__":
    processor = PhotoProcessor()
    processor.process_all()