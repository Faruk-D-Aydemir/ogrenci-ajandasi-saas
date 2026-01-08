from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta, time
from dotenv import load_dotenv 
import os 
import json
import tempfile
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

# --- VERİ TABANI ---
uri = os.getenv('DATABASE_URL')
if uri and uri.startswith("mysql://"):
    uri = uri.replace("mysql://", "mysql+pymysql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///proje_ajandasi.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'gizli_anahtar_123')

# Session Ayarı
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

db = SQLAlchemy(app)

# --- MODELLER ---
class Kullanici(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(150), unique=True, nullable=False)
    eposta = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(512))

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
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

# --- LOGIN ---
login_manager = LoginManager(app)
login_manager.login_view = 'giris'

@login_manager.user_loader
def load_user(user_id):
    return Kullanici.query.get(int(user_id))

# --- ROTALAR ---
@app.route('/')
@login_required
def index():
    kayitlar = Kayit.query.filter_by(kullanici_id=current_user.id).all()
    return render_template('list.html', kayitlar=kayitlar)

@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if request.method == 'POST':
        user = Kullanici.query.filter_by(eposta=request.form.get('eposta')).first()
        if user and user.check_password(request.form.get('parola')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Hatalı giriş!', 'danger')
    return render_template('giris.html')

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if request.method == 'POST':
        if Kullanici.query.filter_by(eposta=request.form.get('eposta')).first():
            flash('Bu e-posta kayıtlı!', 'warning')
        else:
            yeni = Kullanici(kullanici_adi=request.form.get('kullanici_adi'), eposta=request.form.get('eposta'))
            yeni.set_password(request.form.get('parola'))
            db.session.add(yeni); db.session.commit()
            return redirect(url_for('giris'))
    return render_template('kayitol.html')

@app.route('/ekle', methods=['GET', 'POST'])
@login_required
def ekle():
    if request.method == 'POST':
        tarih_str = request.form.get('tarih')
        yeni = Kayit(
            ders_adi=request.form.get('ders_adi'),
            tarih=datetime.strptime(tarih_str, '%Y-%m-%d'),
            konular=request.form.get('konular'),
            kullanici_id=current_user.id
        )
        db.session.add(yeni); db.session.commit()
        return redirect(url_for('index'))
    return render_template('form.html')

@app.route('/ayarlar')
@login_required
def ayarlar():
    return "Ayarlar sayfası yakında eklenecek. <a href='/'>Geri Dön</a>"

@app.route('/cikis')
def cikis():
    logout_user()
    return redirect(url_for('giris'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)