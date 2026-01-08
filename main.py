import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)

# --- KONFİGÜRASYON ---
uri = os.getenv('DATABASE_URL')
if uri and uri.startswith("mysql://"):
    uri = uri.replace("mysql://", "mysql+pymysql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///ajanda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cok-gizli-anahtar-99')

db = SQLAlchemy(app)

# --- MODELLER ---
class Kullanici(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(150), unique=True, nullable=False)
    eposta = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(512))
    kayitlar = db.relationship('Kayit', backref='sahibi', lazy=True)

    def set_password(self, parola):
        self.parola_hash = generate_password_hash(parola)
    def check_password(self, parola):
        return check_password_hash(self.parola_hash, parola)

class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)
    konular = db.Column(db.Text, nullable=False)
    video_sonuc = db.Column(db.Text) # "Başlık:::Link|||Başlık:::Link" formatında saklar
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

# --- LOGIN AYARLARI ---
login_manager = LoginManager(app)
login_manager.login_view = 'giris'
login_manager.login_message = "Lütfen önce giriş yapın."

@login_manager.user_loader
def load_user(user_id):
    return Kullanici.query.get(int(user_id))

# --- YOUTUBE API FONKSİYONU (ZIRHLI) ---
def get_youtube_videos(query):
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        return ""
    try:
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&key={api_key}&type=video&maxResults=3"
        response = requests.get(url, timeout=5)
        data = response.json()
        videos = []
        for item in data.get('items', []):
            title = item['snippet']['title']
            video_id = item['id']['videoId']
            videos.append(f"{title}:::https://www.youtube.com/watch?v={video_id}")
        return "|||".join(videos)
    except Exception as e:
        print(f"YouTube Hatası: {e}")
        return ""

# --- ROTALAR ---
@app.route('/')
@login_required
def index():
    kayitlar = Kayit.query.filter_by(kullanici_id=current_user.id).order_by(Kayit.tarih.desc()).all()
    return render_template('list.html', kayitlar=kayitlar)

@app.route('/ekle', methods=['GET', 'POST'])
@login_required
def ekle():
    if request.method == 'POST':
        ders = request.form.get('ders_adi')
        konu = request.form.get('konular')
        tarih_str = request.form.get('tarih')
        
        # Videoları çek
        videolar = get_youtube_videos(f"{ders} {konu}")
        
        yeni_kayit = Kayit(
            ders_adi=ders,
            konular=konu,
            tarih=datetime.strptime(tarih_str, '%Y-%m-%d'),
            video_sonuc=videolar,
            kullanici_id=current_user.id
        )
        db.session.add(yeni_kayit)
        db.session.commit()
        flash('Ders başarıyla eklendi ve videolar getirildi!', 'success')
        return redirect(url_for('index'))
    return render_template('form.html')

@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    if request.method == 'POST':
        current_user.kullanici_adi = request.form.get('kullanici_adi')
        db.session.commit()
        flash('Profil güncellendi!', 'info')
    return render_template('ayarlar.html')

@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if request.method == 'POST':
        user = Kullanici.query.filter_by(eposta=request.form.get('eposta')).first()
        if user and user.check_password(request.form.get('parola')):
            login_user(user)
            return redirect(url_for('index'))
        flash('E-posta veya şifre hatalı!', 'danger')
    return render_template('giris.html')

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if request.method == 'POST':
        if Kullanici.query.filter_by(eposta=request.form.get('eposta')).first():
            flash('Bu e-posta zaten kullanımda!', 'warning')
        else:
            yeni = Kullanici(kullanici_adi=request.form.get('kullanici_adi'), eposta=request.form.get('eposta'))
            yeni.set_password(request.form.get('parola'))
            db.session.add(yeni); db.session.commit()
            flash('Hesap oluşturuldu, giriş yapabilirsiniz.', 'success')
            return redirect(url_for('giris'))
    return render_template('kayitol.html')

@app.route('/cikis')
@login_required
def cikis():
    logout_user()
    return redirect(url_for('giris'))

# --- VERİTABANI OLUŞTURMA ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)