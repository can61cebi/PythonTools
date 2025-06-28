import os
import time

# Dizin ve çıktı dosyası tanımları
pdf_dir = r"C:\Users\can\Desktop\liderlik_sinav"
output_file = os.path.join(pdf_dir, "liderlik_metinleri.txt")

def extract_text_with_pypdf2(pdf_path):
    """PyPDF2 kullanarak PDF'den metin çıkarır."""
    import PyPDF2
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            # Şifreli PDF kontrolü
            if pdf_reader.is_encrypted:
                return "Bu PDF şifrelidir ve metin çıkartılamadı."
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if not text.strip():
                return "Bu PDF'den metin çıkartılamadı. PDF taranmış görüntüler içeriyor olabilir."
    except Exception as e:
        text = f"PDF okuma hatası: {str(e)}"
    return text

def extract_text_with_pdfminer(pdf_path):
    """pdfminer.six kullanarak PDF'den metin çıkarır."""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(pdf_path)
        if not text.strip():
            return "Bu PDF'den metin çıkartılamadı. PDF taranmış görüntüler içeriyor olabilir."
        return text
    except ImportError:
        return "pdfminer.six kütüphanesi yüklü değil. PyPDF2 kullanmayı deneyin."
    except Exception as e:
        return f"PDF okuma hatası: {str(e)}"

def main():
    # Hangi PDF çıkarma yönteminin kullanılacağını seç
    # Türkçe karakterler için "pdfminer" önerilir
    # pdfminer.six yüklü değilse "pypdf2" kullanın
    extraction_method = "pdfminer"  # veya "pypdf2"
    
    # Dizindeki tüm PDF dosyalarını bul
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    total_files = len(pdf_files)
    
    if total_files == 0:
        print(f"'{pdf_dir}' dizininde PDF dosyası bulunamadı.")
        return
    
    print(f"Toplam {total_files} PDF dosyası bulundu.")
    print(f"PDF metin çıkarma yöntemi: {extraction_method}")
    
    # Her PDF'den metin çıkar ve çıktı dosyasına yaz
    start_time = time.time()
    try:
        with open(output_file, 'w', encoding='utf-8') as out_file:
            for idx, pdf_file in enumerate(pdf_files, 1):
                pdf_path = os.path.join(pdf_dir, pdf_file)
                
                print(f"İşleniyor ({idx}/{total_files}): {pdf_file}")
                
                # Dosya adını başlık olarak yaz
                out_file.write(f"Dosya Adı: {pdf_file}\n")
                out_file.write("="*50 + "\n\n")
                
                # PDF içeriğini çıkar ve yaz
                if extraction_method == "pdfminer":
                    pdf_text = extract_text_with_pdfminer(pdf_path)
                else:  # PyPDF2'yi varsayılan olarak kullan
                    pdf_text = extract_text_with_pypdf2(pdf_path)
                    
                out_file.write(pdf_text)
                
                # Dosyalar arasına ayırıcı ekle
                out_file.write("\n\n" + "="*50 + "\n\n")
    
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print(f"İşlem tamamlandı! Geçen süre: {elapsed_time:.2f} saniye")
        print(f"Tüm PDF dosyalarının metinleri başarıyla '{output_file}' dosyasına kaydedildi.")
    
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")

if __name__ == "__main__":
    main()