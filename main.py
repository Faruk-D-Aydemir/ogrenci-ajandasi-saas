import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)

# --- VERİTABANI VE GÜVENLİK ---
uri = os.getenv('DATABASE_URL')
if uri and uri.startswith("mysql://"):
    uri = uri.replace("mysql://", "mysql+pymysql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///ajanda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'nihai-gizli-anahtar-2026')

db = SQLAlchemy(app)

# --- MODELLER ---
class Kullanici(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(150), unique=True, nullable=False)
    eposta = db.Column(db.String(150), unique=True, nullable=False)
    parola_hash = db.Column(db.String(512))
    def set_password(self, parola): self.parola_hash = generate_password_hash(parola)
    def check_password(self, parola): return check_password_hash(self.parola_hash, parola)

class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)
    konular = db.Column(db.Text, nullable=False)
    video_sonuc = db.Column(db.Text)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

# --- LOGIN SİSTEMİ ---
login_manager = LoginManager(app)
login_manager.login_view = 'giris'
@login_manager.user_loader
def load_user(user_id): return Kullanici.query.get(int(user_id))

# --- YOUTUBE MOTORU ---
def get_youtube_videos(query):
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key: return ""
    try:
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&key={api_key}&type=video&maxResults=3"
        r = requests.get(url, timeout=5).json()
        videos = [f"{i['snippet']['title']}:::https://www.youtube.com/watch?v={i['id']['videoId']}" for i in r.get('items', [])]
        return "|||".join(videos)
    except: return ""

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
        v_list = get_youtube_videos(f"{ders} {konu}")
        yeni = Kayit(ders_adi=ders, konular=konu, tarih=datetime.strptime(tarih_str, '%Y-%m-%d'), video_sonuc=v_list, kullanici_id=current_user.id)
        db.session.add(yeni); db.session.commit()
        return redirect(url_for('index'))
    return render_template('form.html')

@app.route('/sil/<int:id>')
@login_required
def sil(id):
    k = Kayit.query.get_or_404(id)
    if k.kullanici_id == current_user.id:
        db.session.delete(k); db.session.commit()
    return redirect(url_for('index'))

@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if request.method == 'POST':
        u = Kullanici.query.filter_by(eposta=request.form.get('eposta')).first()
        if u and u.check_password(request.form.get('parola')):
            login_user(u); return redirect(url_for('index'))
    return render_template('giris.html')

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if request.method == 'POST':
        y = Kullanici(kullanici_adi=request.form.get('kullanici_adi'), eposta=request.form.get('eposta'))
        y.set_password(request.form.get('parola'))
        db.session.add(y); db.session.commit()
        return redirect(url_for('giris'))
    return render_template('kayitol.html')

@app.route('/ayarlar')
@login_required
def ayarlar(): return render_template('ayarlar.html')

@app.route('/cikis')
def cikis(): logout_user(); return redirect(url_for('giris'))

with app.app_context(): db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)