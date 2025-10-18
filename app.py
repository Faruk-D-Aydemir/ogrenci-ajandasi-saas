from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy 
from datetime import datetime
from dotenv import load_dotenv 
import os 
from googleapiclient.discovery import build
import json

# --- ÇEVRE DEĞİŞKENLERİNİ YÜKLEME (.env) ---
load_dotenv() 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") 

# Flask uygulamasını başlat
app = Flask(__name__)

# --- VERİ TABANI YAPILANDIRMASI ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///proje_ajandasi.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- VERİ MODELİ (DATABASE TABLOSU) ---
class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, nullable=False)
    konular = db.Column(db.Text, nullable=False)
    video_sonuc = db.Column(db.Text, nullable=True) 
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"Kayit('{self.ders_adi}', '{self.tarih}')"


# --- YOUTUBE ARAMA FONKSİYONU ---
def youtube_arama(arama_sorgusu):
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


# --- ROTALAR (SAYFA ADRESLERİ) ---

# Ana sayfa (Formun ve kayıtların gösterildiği yer)
@app.route('/')
def index():
    # Sınav tarihine ve eklenme tarihine göre sırala (en yeni kayıt en üstte)
    hepsi_kayit = Kayit.query.order_by(Kayit.tarih, Kayit.eklenme_tarihi.desc()).all() 

    ajanda_verileri = []
    bugun = datetime.now().date() 
    
    for kayit in hepsi_kayit:
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
            
        # JSON verisini Python listesine çevirme (Hata Düzeltmesi)
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
    if request.method == 'POST':
        # 1. Form Verilerini Alma
        ders_adi = request.form.get('ders_adi')
        tarih_str = request.form.get('tarih')
        konular = request.form.get('konular')
        
        # 2. YouTube Arama ve Sonuçları Alma
        arama_sorgusu = f"{ders_adi} {konular.split(',')[0].strip()} konu anlatımı"
        video_sonuclari = youtube_arama(arama_sorgusu)

        # Sonuçları Kayıt modeline eklemek için JSON string'e çevir
        video_json = json.dumps(video_sonuclari)
        
        # 3. Veri Tabanına Kayıt İşlemi
        tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d')
        yeni_kayit = Kayit(
            ders_adi=ders_adi, 
            tarih=tarih_obj, 
            konular=konular,
            video_sonuc=video_json
        )

        try:
            db.session.add(yeni_kayit)
            db.session.commit()
            
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Veri kaydı sırasında hata oluştu: {e}")
            return "Kayıt Başarısız Oldu!" 
    
    return "Hata: Yanlış istek metodu."


# --- YENİ ROTA: KAYIT SİLME ---
@app.route('/sil/<int:kayit_id>', methods=['POST'])
def kayit_sil(kayit_id):
    # Silinecek kaydı ID ile veri tabanında bul
    silinecek_kayit = Kayit.query.get_or_404(kayit_id)
    
    try:
        # Kaydı silme işlemi
        db.session.delete(silinecek_kayit)
        db.session.commit()
        
        # Başarılı silme sonrası ana sayfaya yönlendir
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Silme işlemi sırasında hata oluştu: {e}")
        return "Silme Başarısız Oldu!"


# --- UYGULAMAYI ÇALIŞTIRMA ---
if __name__ == '__main__':
    app.run(debug=True)