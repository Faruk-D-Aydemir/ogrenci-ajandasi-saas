from flask import Flask, render_template, request, redirect, url_for, flash
# Flask-Login modülleri
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
# SQLAlchemy ve Veritabanı için gerekli modüller (psycopg2'yi kullanacağız)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv 
import os 
from googleapiclient.discovery import build
import json
from werkzeug.security import generate_password_hash, check_password_hash

# --- ÇEVRE DEĞİŞKENLERİNİ YÜKLEME (.env) ---
load_dotenv() 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") 

app = Flask(__name__)

# --- UYGULAMA YAPILANDIRMASI (VERİ TABANI VE GİZLİ ANAHTAR) ---

# Bu tek satır, hem yerelde SQLite'ı hem de Render'da DATABASE_URL'ı (PostgreSQL) kullanır.
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///proje_ajandasi.db') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cok_gizli_bir_anahtar') 

db = SQLAlchemy(app)

# --- TABLOLARI OLUŞTURMA (RENDER İÇİN KRİTİK) ---
# Bu blok, uygulamanın Gunicorn tarafından her başlatılmasında tabloların varlığını kontrol eder ve eksikse oluşturur.
# Bu, UndefinedTable ve Status 2 hatalarını çözen en güvenilir yöntemdir.
with app.app_context():
    db.create_all()

# --- FLASK-LOGIN YAPILANDIRMASI ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'giris' 
login_manager.login_message = "Bu sayfaya erişmek için lütfen giriş yapın."


# Kullanıcı oturumunu yöneten fonksiyon
@login_manager.user_loader
def load_user(user_id):
    return Kullanici.query.get(int(user_id))


# --- VERİ TABANI MODELLERİ (SQLAlchemy) ---

# Kullanıcı Modeli (Flask-Login için UserMixin'den miras alır)
class Kullanici(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(80), unique=True, nullable=False)
    eposta = db.Column(db.String(120), unique=True, nullable=False)
    parola_hash = db.Column(db.String(128))
    kayitlar = db.relationship('Kayit', backref='yazar', lazy=True)

    def set_password(self, parola):
        self.parola_hash = generate_password_hash(parola)

    def check_password(self, parola):
        return check_password_hash(self.parola_hash, parola)

# Ajanda Kayıt Modeli
class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, nullable=False)
    konular = db.Column(db.Text, nullable=False)
    video_sonuc = db.Column(db.Text)
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

# --- YOUTUBE ARAMA FONKSİYONU ---
def youtube_arama(arama_sorgusu):
    if not YOUTUBE_API_KEY:
        return []
    try:
        if not YOUTUBE_API_KEY.strip():
             return []
             
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
        return []

# --- ROTALAR (SAYFA ADRESLERİ) ---

# Giriş Sayfası
@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        eposta = request.form.get('eposta')
        parola = request.form.get('parola')
        
        kullanici = Kullanici.query.filter_by(eposta=eposta).first()
        
        if kullanici and kullanici.check_password(parola):
            login_user(kullanici)
            flash('Başarıyla giriş yaptınız!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Giriş başarısız. Lütfen e-posta ve şifrenizi kontrol edin.', 'danger')
            
    return render_template('giris.html') 

# Kayıt Ol Sayfası
@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        kullanici_adi = request.form.get('kullanici_adi')
        eposta = request.form.get('eposta')
        parola = request.form.get('parola')
        
        if Kullanici.query.filter_by(eposta=eposta).first():
            flash('Bu e-posta adresi zaten kayıtlı.', 'warning')
            return redirect(url_for('kayitol'))
            
        yeni_kullanici = Kullanici(kullanici_adi=kullanici_adi, eposta=eposta)
        yeni_kullanici.set_password(parola)
        
        db.session.add(yeni_kullanici)
        db.session.commit()
        
        flash('Hesabınız başarıyla oluşturuldu! Lütfen giriş yapın.', 'success')
        return redirect(url_for('giris'))
        
    return render_template('kayitol.html') 

# Çıkış Rotası
@app.route('/cikis')
@login_required 
def cikis():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'info')
    return redirect(url_for('giris'))

# Ana Sayfa (Sadece Giriş Yapmış Kullanıcılar Erişebilir)
@app.route('/')
@login_required 
def index():
    bugun = datetime.now().date() 
    
    sirali_kayitlar = Kayit.query.filter_by(kullanici_id=current_user.id).order_by(Kayit.tarih).all()
    
    ajanda_verileri = []
    
    for kayit in sirali_kayitlar:
        tarih_obj = kayit.tarih.date()
        kalan_gun = (tarih_obj - bugun).days
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
            
        video_listesi_python = []
        if kayit.video_sonuc:
            try:
                video_listesi_python = json.loads(kayit.video_sonuc)
            except json.JSONDecodeError:
                video_listesi_python = []

        ajanda_verileri.append({
            'kayit': kayit, 
            'kalan_gun': kalan_gun,
            'plan_etiketi': plan_etiketi,
            'video_listesi': video_listesi_python
        })
    
    return render_template('index.html', ajanda_listesi=ajanda_verileri)


# Form verilerinin işleneceği yer (Kullanıcı ID'si eklendi)
@app.route('/ajanda-olustur', methods=['POST'])
@login_required 
def ajanda_olustur():
    if request.method == 'POST':
        
        ders_adi = request.form.get('ders_adi')
        tarih_str = request.form.get('tarih')
        konular = request.form.get('konular')
        
        arama_sorgusu = f"{ders_adi} {konular.split(',')[0].strip()} konu anlatımı"
        video_sonuclari = youtube_arama(arama_sorgusu)

        video_json = json.dumps(video_sonuclari)
        
        tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d')
        
        yeni_kayit = Kayit(
            ders_adi=ders_adi, 
            tarih=tarih_obj, 
            konular=konular,
            video_sonuc=video_json,
            kullanici_id=current_user.id 
        )
        
        db.session.add(yeni_kayit)
        db.session.commit()
        
        flash('Yeni ajanda kaydı başarıyla oluşturuldu!', 'success')
        return redirect(url_for('index'))
    
    return "Hata: Yanlış istek metodu."


# --- KAYIT SİLME (Veri Tabanından Silme) ---
@app.route('/sil/<int:kayit_id>', methods=['POST'])
@login_required 
def kayit_sil(kayit_id):
    kayit = Kayit.query.filter_by(id=kayit_id, kullanici_id=current_user.id).first_or_404()
    
    db.session.delete(kayit)
    db.session.commit()
    
    flash('Ajanda kaydı başarıyla silindi.', 'info')
    return redirect(url_for('index'))


# --- UYGULAMAYI ÇALIŞTIRMA ---
if __name__ == '__main__':
    app.run(debug=True)