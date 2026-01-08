from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta, time
from dotenv import load_dotenv 
import os 
from googleapiclient.discovery import build
from werkzeug.security import generate_password_hash, check_password_hash
import tempfile 
from flask_session import Session 
import json

# .env dosyasını yükle (Yerel çalışma için)
load_dotenv() 

app = Flask(__name__)

# --- VERİ TABANI YAPILANDIRMASI (MYSQL & POSTGRES UYUMLU) ---
# Railway veya Render'dan gelen DATABASE_URL'i al
uri = os.getenv('DATABASE_URL')

if uri:
    # MySQL Uyumluluğu: Railway 'mysql://' verir ama Flask 'mysql+pymysql://' ister
    if uri.startswith("mysql://"):
        uri = uri.replace("mysql://", "mysql+pymysql://", 1)
    # PostgreSQL Uyumluluğu: Render 'postgres://' verir ama SQLAlchemy 'postgresql://' ister
    elif uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
else:
    # Eğer sunucuda değilsek yerel SQLite kullan
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///proje_ajandasi.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_12345')

# YouTube API Anahtarı
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# SESSION AYARLARI
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
Session(app)

db = SQLAlchemy(app)

# --- VERİ TABANI MODELLERİ ---
class Kullanici(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(150), unique=True, nullable=False)
    eposta = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(512))
    calisma_saatleri_json = db.Column(db.Text, default='{}') 
    okul_saatleri = db.Column(db.String(50), default='08:00-17:00')

    def set_password(self, parola):
        self.parola_hash = generate_password_hash(parola)
    def check_password(self, parola):
        return check_password_hash(self.parola_hash, parola)

class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, nullable=False)
    konular = db.Column(db.Text, nullable=False)
    video_sonuc = db.Column(db.Text)
    alinan_not = db.Column(db.Integer, nullable=True)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

class ProgramGorev(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    kayit_id = db.Column(db.Integer, db.ForeignKey('kayit.id'))
    gorev_tarihi = db.Column(db.Date, nullable=False)
    baslangic_saati = db.Column(db.Time, nullable=False)
    bitis_saati = db.Column(db.Time, nullable=False)
    gorev_adi = db.Column(db.String(200), nullable=False)
    tamamlandi = db.Column(db.Boolean, default=False)

# --- YARDIMCI FONKSİYONLAR ---
def youtube_arama(arama_sorgusu):
    if not YOUTUBE_API_KEY: return ""
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        request = youtube.search().list(q=arama_sorgusu, part="snippet", maxResults=3, type="video")
        response = request.execute()
        vids = [f"{i['snippet']['title']}:::{'https://www.youtube.com/embed/'+i['id']['videoId']}" for i in response.get("items", [])]
        return "|||".join(vids)
    except: return ""

def program_olustur_algo(kullanici_id):
    kullanici = Kullanici.query.get(kullanici_id)
    if not kullanici: return False
    bugun = date.today()
    limit = bugun + timedelta(days=7)
    kayitlar = Kayit.query.filter(Kayit.kullanici_id==kullanici_id, Kayit.tarih >= datetime.combine(bugun, time.min)).all()
    if not kayitlar: return False
    
    ProgramGorev.query.filter_by(kullanici_id=kullanici_id).delete()
    
    bos_saatler = json.loads(kullanici.calisma_saatleri_json or '{}')
    gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
    
    for i in range(7):
        su_an = bugun + timedelta(days=i)
        gun_adi = gunler[su_an.weekday()]
        if gun_adi in bos_saatler:
            try:
                bas, bit = bos_saatler[gun_adi].split('-')
                # Basit bir görev ekleme mantığı
                yeni = ProgramGorev(
                    kullanici_id=kullanici_id, gorev_tarihi=su_an,
                    baslangic_saati=time.fromisoformat(bas), bitis_saati=time.fromisoformat(bit),
                    gorev_adi="Ders Çalışma Seansı", tamamlandi=False
                )
                db.session.add(yeni)
            except: continue
    db.session.commit()
    return True

# --- FLASK LOGIN ---
login_manager = LoginManager(app)
login_manager.login_view = 'giris'

@login_manager.user_loader
def load_user(user_id):
    return Kullanici.query.get(int(user_id))

# --- ROTALAR ---
@app.route('/')
def index():
    if not current_user.is_authenticated: return redirect(url_for('giris'))
    kayitlar = Kayit.query.filter_by(kullanici_id=current_user.id).order_by(Kayit.tarih).all()
    return render_template('list.html', kayitlar=kayitlar)

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if request.method == 'POST':
        k_adi = request.form.get('kullanici_adi')
        email = request.form.get('eposta')
        sifre = request.form.get('parola')
        if Kullanici.query.filter_by(eposta=email).first():
            flash('Bu e-posta kayıtlı!', 'danger')
        else:
            yeni = Kullanici(kullanici_adi=k_adi, eposta=email)
            yeni.set_password(sifre)
            db.session.add(yeni); db.session.commit()
            flash('Kayıt başarılı, giriş yap.', 'success')
            return redirect(url_for('giris'))
    return render_template('kayitol.html')

@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if request.method == 'POST':
        user = Kullanici.query.filter_by(eposta=request.form.get('eposta')).first()
        if user and user.check_password(request.form.get('parola')):
            login_user(user); return redirect(url_for('index'))
        flash('Hatalı bilgiler!', 'danger')
    return render_template('giris.html')

@app.route('/ekle', methods=['GET', 'POST'])
@login_required
def ekle():
    if request.method == 'POST':
        ders = request.form.get('ders_adi')
        tarih = datetime.strptime(request.form.get('tarih'), '%Y-%m-%d')
        konu = request.form.get('konular')
        vids = youtube_arama(f"{ders} {konu}")
        yeni = Kayit(ders_adi=ders, tarih=tarih, konular=konu, video_sonuc=vids, kullanici_id=current_user.id)
        db.session.add(yeni); db.session.commit()
        return redirect(url_for('index'))
    return render_template('form.html')

@app.route('/cikis')
def cikis():
    logout_user(); return redirect(url_for('giris'))

# --- VERITABANI BASLATMA ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)