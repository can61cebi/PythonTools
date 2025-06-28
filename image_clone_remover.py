import os
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import time
from collections import defaultdict
import shutil

class DuplicateImageDetector:
    def __init__(self, max_threads=12):
        self.max_threads = max_threads
        self.image_hashes = {}
        self.duplicates = defaultdict(list)
        self.lock = threading.Lock()
        self.processed_count = 0
        self.total_files = 0
        
    def calculate_image_hash(self, image_path):
        """Resmin içeriğine dayalı hash değeri hesaplar"""
        try:
            with Image.open(image_path) as img:
                # Resmi standart boyuta getir ve gri tonlamaya çevir
                img = img.convert('RGB')
                img = img.resize((8, 8), Image.Resampling.LANCZOS)
                img = img.convert('L')  # Gri tonlama
                
                # Piksel verilerini al
                pixels = list(img.getdata())
                
                # Hash hesapla
                pixel_string = ''.join(str(p) for p in pixels)
                hash_value = hashlib.md5(pixel_string.encode()).hexdigest()
                
                return hash_value
                
        except Exception as e:
            print(f"Hata - {image_path}: {str(e)}")
            return None
    
    def process_image(self, image_path):
        """Tek bir resmi işler"""
        hash_value = self.calculate_image_hash(image_path)
        
        if hash_value:
            with self.lock:
                if hash_value in self.image_hashes:
                    # Mükerrer resim bulundu
                    if hash_value not in self.duplicates:
                        self.duplicates[hash_value].append(self.image_hashes[hash_value])
                    self.duplicates[hash_value].append(image_path)
                else:
                    self.image_hashes[hash_value] = image_path
                
                self.processed_count += 1
                if self.processed_count % 10 == 0:
                    print(f"İşlenen dosya sayısı: {self.processed_count}/{self.total_files}")
    
    def find_image_files(self, directory):
        """Belirtilen dizindeki jpg ve png dosyalarını bulur"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
        image_files = []
        
        print(f"Dizin taranıyor: {directory}")
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if any(file.endswith(ext) for ext in image_extensions):
                    image_files.append(os.path.join(root, file))
        
        return image_files
    
    def detect_duplicates(self, directory):
        """Ana fonksiyon - mükerrer resimleri tespit eder"""
        print("Mükerrer Resim Tespit Programı")
        print("=" * 40)
        
        # Resim dosyalarını bul
        image_files = self.find_image_files(directory)
        self.total_files = len(image_files)
        
        if self.total_files == 0:
            print("Hiç resim dosyası bulunamadı!")
            return
        
        print(f"Toplam {self.total_files} resim dosyası bulundu.")
        print(f"{self.max_threads} thread ile işleme başlıyor...\n")
        
        start_time = time.time()
        
        # ThreadPoolExecutor ile paralel işleme
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            # Tüm dosyaları thread havuzuna gönder
            futures = [executor.submit(self.process_image, image_path) 
                      for image_path in image_files]
            
            # Tüm thread'lerin tamamlanmasını bekle
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Thread hatası: {str(e)}")
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Sonuçları göster
        self.display_results(processing_time)
    
    def display_results(self, processing_time):
        """Sonuçları ekrana yazdırır"""
        print("\n" + "=" * 50)
        print("SONUÇLAR")
        print("=" * 50)
        
        if not self.duplicates:
            print("Hiç mükerrer resim bulunamadı!")
        else:
            print(f"Toplam {len(self.duplicates)} grup mükerrer resim bulundu:\n")
            
            for i, (hash_value, file_list) in enumerate(self.duplicates.items(), 1):
                print(f"Grup {i} ({len(file_list)} dosya):")
                for file_path in file_list:
                    print(f"  - {file_path}")
                print()
        
        print(f"İşlem süresi: {processing_time:.2f} saniye")
        print(f"İşlenen dosya sayısı: {self.processed_count}")
        print(f"Saniyede işlenen dosya: {self.processed_count/processing_time:.1f}")
    
    def save_results_to_file(self, output_file="duplicate_images.txt"):
        """Sonuçları dosyaya kaydeder"""
        if not self.duplicates:
            print("Kaydedilecek mükerrer resim bulunamadı.")
            return
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("MÜKERRER RESİMLER RAPORU\n")
                f.write("=" * 40 + "\n\n")
                
                for i, (hash_value, file_list) in enumerate(self.duplicates.items(), 1):
                    f.write(f"Grup {i} ({len(file_list)} dosya):\n")
                    for file_path in file_list:
                        f.write(f"  - {file_path}\n")
                    f.write(f"Hash: {hash_value}\n\n")
            
            print(f"Sonuçlar '{output_file}' dosyasına kaydedildi.")
            
        except Exception as e:
            print(f"Dosya kaydetme hatası: {str(e)}")
    
    def get_file_info(self, file_path):
        """Dosya bilgilerini döndürür (boyut, değiştirilme tarihi)"""
        try:
            stat = os.stat(file_path)
            return {
                'path': file_path,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'name': os.path.basename(file_path)
            }
        except Exception as e:
            print(f"Dosya bilgisi alınamadı {file_path}: {str(e)}")
            return None
    
    def choose_files_to_keep(self, strategy='newest'):
        """Her mükerrer grup için hangi dosyanın korunacağını belirler"""
        files_to_delete = []
        files_to_keep = []
        
        for hash_value, file_list in self.duplicates.items():
            if len(file_list) <= 1:
                continue
            
            # Dosya bilgilerini topla
            file_infos = []
            for file_path in file_list:
                info = self.get_file_info(file_path)
                if info:
                    file_infos.append(info)
            
            if not file_infos:
                continue
            
            # Strateji'ye göre korunacak dosyayı seç
            if strategy == 'newest':
                keep_file = max(file_infos, key=lambda x: x['mtime'])
            elif strategy == 'oldest':
                keep_file = min(file_infos, key=lambda x: x['mtime'])
            elif strategy == 'largest':
                keep_file = max(file_infos, key=lambda x: x['size'])
            elif strategy == 'smallest':
                keep_file = min(file_infos, key=lambda x: x['size'])
            else:
                # Manuel seçim
                keep_file = self.manual_file_selection(file_infos)
            
            files_to_keep.append(keep_file['path'])
            
            # Diğer dosyaları silme listesine ekle
            for info in file_infos:
                if info['path'] != keep_file['path']:
                    files_to_delete.append(info['path'])
        
        return files_to_keep, files_to_delete
    
    def manual_file_selection(self, file_infos):
        """Kullanıcının manuel olarak dosya seçmesini sağlar"""
        print("\nMükerrer dosyalar:")
        for i, info in enumerate(file_infos, 1):
            size_mb = info['size'] / (1024 * 1024)
            mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['mtime']))
            print(f"{i}. {info['name']} (Boyut: {size_mb:.2f} MB, Tarih: {mod_time})")
            print(f"   Yol: {info['path']}")
        
        while True:
            try:
                choice = int(input("Hangi dosyayı korumak istiyorsunuz? (numara girin): "))
                if 1 <= choice <= len(file_infos):
                    return file_infos[choice - 1]
                else:
                    print("Geçersiz numara! Tekrar deneyin.")
            except ValueError:
                print("Lütfen geçerli bir numara girin!")
    
    def preview_deletion(self, files_to_delete, files_to_keep):
        """Silinecek dosyaları önizler"""
        print("\n" + "=" * 60)
        print("SİLME ÖNİZLEMESİ")
        print("=" * 60)
        
        total_size = 0
        delete_count = len(files_to_delete)
        keep_count = len(files_to_keep)
        
        print(f"Korunacak dosya sayısı: {keep_count}")
        print(f"Silinecek dosya sayısı: {delete_count}")
        
        print("\nSilinecek dosyalar:")
        for file_path in files_to_delete:
            try:
                size = os.path.getsize(file_path)
                total_size += size
                size_mb = size / (1024 * 1024)
                print(f"  - {file_path} ({size_mb:.2f} MB)")
            except:
                print(f"  - {file_path} (boyut alınamadı)")
        
        print(f"\nToplam boşaltılacak alan: {total_size / (1024 * 1024):.2f} MB")
        return total_size
    
    def delete_duplicate_files(self, files_to_delete, backup_dir=None):
        """Mükerrer dosyaları siler"""
        deleted_files = []
        failed_deletions = []
        
        # Backup dizini varsa oluştur
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            print(f"\nSilinen dosyalar şuraya yedeklenecek: {backup_dir}")
        
        print(f"\n{len(files_to_delete)} dosya siliniyor...")
        
        for i, file_path in enumerate(files_to_delete, 1):
            try:
                # Backup oluştur
                if backup_dir:
                    backup_path = os.path.join(backup_dir, os.path.basename(file_path))
                    # Aynı isimli dosya varsa numara ekle
                    counter = 1
                    base_backup_path = backup_path
                    while os.path.exists(backup_path):
                        name, ext = os.path.splitext(base_backup_path)
                        backup_path = f"{name}_{counter}{ext}"
                        counter += 1
                    
                    shutil.copy2(file_path, backup_path)
                
                # Dosyayı sil
                os.remove(file_path)
                deleted_files.append(file_path)
                
                if i % 10 == 0 or i == len(files_to_delete):
                    print(f"İlerleme: {i}/{len(files_to_delete)} dosya silindi")
                    
            except Exception as e:
                failed_deletions.append((file_path, str(e)))
                print(f"Silme hatası {file_path}: {str(e)}")
        
        return deleted_files, failed_deletions
    
    def manage_duplicates(self):
        """Mükerrer dosya yönetimi ana fonksiyonu"""
        if not self.duplicates:
            print("Mükerrer dosya bulunamadı, silme işlemi yapılamaz.")
            return
        
        print("\n" + "=" * 50)
        print("MÜKERRER DOSYA YÖNETİMİ")
        print("=" * 50)
        
        # Silme stratejisi seç
        print("Silme stratejisi seçin:")
        print("1. En yeni dosyayı koru, eskilerini sil")
        print("2. En eski dosyayı koru, yenilerini sil")
        print("3. En büyük dosyayı koru, küçüklerini sil")
        print("4. En küçük dosyayı koru, büyüklerini sil")
        print("5. Manuel olarak seç")
        print("6. İptal")
        
        while True:
            try:
                choice = int(input("Seçiminiz (1-6): "))
                if 1 <= choice <= 6:
                    break
                else:
                    print("1-6 arası bir sayı girin!")
            except ValueError:
                print("Geçerli bir sayı girin!")
        
        if choice == 6:
            print("Silme işlemi iptal edildi.")
            return
        
        strategies = {
            1: 'newest',
            2: 'oldest', 
            3: 'largest',
            4: 'smallest',
            5: 'manual'
        }
        
        strategy = strategies[choice]
        
        # Dosyaları seç
        print(f"\nSeçilen strateji ile dosyalar analiz ediliyor...")
        files_to_keep, files_to_delete = self.choose_files_to_keep(strategy)
        
        if not files_to_delete:
            print("Silinecek dosya bulunamadı.")
            return
        
        # Önizleme göster
        total_size = self.preview_deletion(files_to_delete, files_to_keep)
        
        # Onay al
        print("\n⚠️  DİKKAT: Bu işlem geri alınamaz!")
        backup_choice = input("Silmeden önce dosyaları yedeklemek istiyor musunuz? (e/h): ").lower()
        
        backup_dir = None
        if backup_choice == 'e':
            backup_dir = input("Yedek dizini (varsayılan: ./backup_duplicates): ").strip()
            if not backup_dir:
                backup_dir = "./backup_duplicates"
        
        final_confirm = input(f"\n{len(files_to_delete)} dosyayı silmeyi onaylıyor musunuz? (EVET yazın): ")
        
        if final_confirm == "EVET":
            deleted_files, failed_deletions = self.delete_duplicate_files(files_to_delete, backup_dir)
            
            # Sonuçları göster
            print("\n" + "=" * 50)
            print("SİLME İŞLEMİ TAMAMLANDI")
            print("=" * 50)
            print(f"Başarıyla silinen dosya sayısı: {len(deleted_files)}")
            print(f"Silinemyen dosya sayısı: {len(failed_deletions)}")
            
            if failed_deletions:
                print("\nSilinemyen dosyalar:")
                for file_path, error in failed_deletions:
                    print(f"  - {file_path}: {error}")
            
            saved_space = sum(os.path.getsize(f) for f in deleted_files if os.path.exists(f))
            print(f"Boşaltılan disk alanı: {total_size / (1024 * 1024):.2f} MB")
            
        else:
            print("Silme işlemi iptal edildi.")

def main():
    # Kullanım örneği
    detector = DuplicateImageDetector(max_threads=12)
    
    # Taranacak dizini belirtin
    directory = input("Taranacak dizin yolunu girin (boş bırakırsanız mevcut dizin kullanılır): ").strip()
    
    if not directory:
        directory = "."
    
    if not os.path.exists(directory):
        print(f"Hata: '{directory}' dizini bulunamadı!")
        return
    
    # Mükerrer resim tespitini başlat
    detector.detect_duplicates(directory)
    
    # Mükerrer dosyalar bulunduysa yönetim seçenekleri sun
    if detector.duplicates:
        print("\n" + "=" * 50)
        print("SONRAKI İŞLEMLER")
        print("=" * 50)
        print("1. Sonuçları dosyaya kaydet")
        print("2. Mükerrer dosyaları sil")
        print("3. Her ikisini de yap")
        print("4. Hiçbirini yapma")
        
        while True:
            try:
                choice = int(input("Seçiminiz (1-4): "))
                if 1 <= choice <= 4:
                    break
                else:
                    print("1-4 arası bir sayı girin!")
            except ValueError:
                print("Geçerli bir sayı girin!")
        
        if choice in [1, 3]:
            # Sonuçları dosyaya kaydet
            output_file = input("Rapor dosya adı (varsayılan: duplicate_images.txt): ").strip()
            if not output_file:
                output_file = "duplicate_images.txt"
            detector.save_results_to_file(output_file)
        
        if choice in [2, 3]:
            # Mükerrer dosyaları yönet
            detector.manage_duplicates()
        
        if choice == 4:
            print("İşlem tamamlandı.")
    
    else:
        print("\nHiç mükerrer resim bulunamadığı için başka işlem yapılacak bir şey yok.")

if __name__ == "__main__":
    main()