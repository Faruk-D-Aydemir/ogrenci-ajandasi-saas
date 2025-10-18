from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from dotenv import load_dotenv 
import os 
from googleapiclient.discovery import build
import json

# --- VERİ TABANI YERİNE GEÇİCİ LİSTE KULLANIYORUZ ---
# Not: Bu liste, uygulama her yeniden başlatıldığında (Render'da sık olur) sıfırlanır.
ajanda_kayitlari = []
kayit_id_sayaci = 1

# --- ÇEVRE DEĞİŞKENLERİNİ YÜKLEME (.env) ---
load_dotenv() 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") 

# Flask uygulamasını başlat
app = Flask(__name__)

# --- GEÇİCİ KAYIT SINIFI (SQLAlchemy Yerine) ---
class Kayit:
    def __init__(self, id, ders_adi, tarih, konular, video_sonuc=None):
        self.id = id
        self.ders_adi = ders_adi
        self.tarih = tarih
        self.konular = konular
        self.video_sonuc = video_sonuc
        self.eklenme_tarihi = datetime.utcnow()

# --- YOUTUBE ARAMA FONKSİYONU ---
def youtube_arama(arama_sorgusu):
    if not YOUTUBE_API_KEY:
        return []
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        request = youtube.search().list(
            q=arama_sorgusu,             
            part="snippet",              
            maxResults=3,                
            type="video",                
            videoEmbeddable="true"       
        )
        
        response = request.execute()
        
        video_listesi = []
        for item in response.get("items", []):
            video_listesi.append({
                'title': item['snippet']['title'],
                'video_id': item['id']['videoId']
            })
            
        return video_listesi
    except Exception:
        # API anahtarı geçersizse veya kota dolduysa boş liste döner
        return []


# --- ROTALAR (SAYFA ADRESLERİ) ---

# Ana sayfa (Formun ve kayıtların gösterildiği yer)
@app.route('/')
def index():
    bugun = datetime.now().date() 
    
    # Sıralama: Sınav tarihine göre sırala
    sirali_kayitlar = sorted(ajanda_kayitlari, key=lambda k: k.tarih)
    
    ajanda_verileri = []
    
    for kayit in sirali_kayitlar:
        kalan_gun = (kayit.tarih.date() - bugun).days
        plan_etiketi = ""

        # Basit AI Planlama Mantığı
        if kalan_gun < 0:
            plan_etiketi = "Sınav Günü Geçti 😥"
        elif kalan_gun <= 3:
            plan_etiketi = "🚨 KRİTİK! Hemen Başla!"
        elif kalan_gun <= 7:
            plan_etiketi = "🔥 Yoğun Çalışma Zamanı"
        else:
            plan_etiketi = "✅ Planlı İlerleme"
            
        # JSON verisini Python listesine çevirme
        video_listesi_python = []
        if kayit.video_sonuc:
            try:
                video_listesi_python = json.loads(kayit.video_sonuc)
            except json.JSONDecodeError:
                video_listesi_python = []

        # Verileri listeye ekle
        ajanda_verileri.append({
            'kayit': kayit, 
            'kalan_gun': kalan_gun,
            'plan_etiketi': plan_etiketi,
            'video_listesi': video_listesi_python
        })
    
    return render_template('index.html', ajanda_listesi=ajanda_verileri)

# Form verilerinin işleneceği yer
@app.route('/ajanda-olustur', methods=['POST'])
def ajanda_olustur():
    global kayit_id_sayaci
    if request.method == 'POST':
        
        ders_adi = request.form.get('ders_adi')
        tarih_str = request.form.get('tarih')
        konular = request.form.get('konular')
        
        # YouTube Arama ve Sonuçları Alma
        arama_sorgusu = f"{ders_adi} {konular.split(',')[0].strip()} konu anlatımı"
        video_sonuclari = youtube_arama(arama_sorgusu)

        # Sonuçları Kayıt modeline eklemek için JSON string'e çevir
        video_json = json.dumps(video_sonuclari)
        
        # Geçici Listeye Kayıt İşlemi
        tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d')
        yeni_kayit = Kayit(
            id=kayit_id_sayaci,
            ders_adi=ders_adi, 
            tarih=tarih_obj, 
            konular=konular,
            video_sonuc=video_json
        )
        ajanda_kayitlari.append(yeni_kayit)
        kayit_id_sayaci += 1
        
        return redirect(url_for('index'))
    
    return "Hata: Yanlış istek metodu."


# --- KAYIT SİLME (Listeden Silme) ---
@app.route('/sil/<int:kayit_id>', methods=['POST'])
def kayit_sil(kayit_id):
    global ajanda_kayitlari
    
    # ID'ye göre listeden kaydı bul ve sil
    global ajanda_kayitlari
    ajanda_kayitlari = [kayit for kayit in ajanda_kayitlari if kayit.id != kayit_id]
        
    return redirect(url_for('index'))


# --- UYGULAMAYI ÇALIŞTIRMA ---
# NOT: Render Gunicorn'ı kullandığı için bu blok yerelde çalışır.
if __name__ == '__main__':
    app.run(debug=True)