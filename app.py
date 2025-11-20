from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from dotenv import load_dotenv 
import os 
from googleapiclient.discovery import build
from werkzeug.security import generate_password_hash, check_password_hash
import tempfile 
from flask_session import Session 

load_dotenv() 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") 

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

if not app.config['SQLALCHEMY_DATABASE_URI']:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///proje_ajandasi.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cok_gizli_bir_anahtar') 

app.config['SESSION_TYPE'] = 'filesystem' 
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
Session(app)

db = SQLAlchemy(app)

# --- VERİ TABANI MODELLERİ ---
class Kullanici(UserMixin, db.Model):
    __tablename__ = 'kullanici' 
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(255), unique=True, nullable=False) 
    eposta = db.Column(db.String(255), unique=True, nullable=False) 
    parola_hash = db.Column(db.String(512))
    kayitlar = db.relationship('Kayit', backref='yazar', lazy=True)

    def set_password(self, parola):
        self.parola_hash = generate_password_hash(parola)

    def check_password(self, parola):
        return check_password_hash(self.parola_hash, parola)

class Kayit(db.Model):
    __tablename__ = 'kayit'
    id = db.Column(db.Integer, primary_key=True)
    ders_adi = db.Column(db.String(100), nullable=False)
    tarih = db.Column(db.DateTime, nullable=False)
    konular = db.Column(db.Text, nullable=False)
    etiket = db.Column(db.String(50)) 
    video_sonuc = db.Column(db.Text)
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

def create_tables(uygulama):
    with uygulama.app_context():
        try:
            # 🚨 HATA DÜZELTME İÇİN GEÇİCİ SIFIRLAMA
            # Bu, "etiket" sütununu eklemek için TÜM VERİYİ SİLER.
            db.drop_all() 
            db.create_all()
            print("INFO: Veritabanı tabloları başarıyla SIFIRLANDI ve oluşturuldu.") 
        except Exception as e:
            print(f"HATA: Tablo oluşturulurken bir hata oluştu: {e}")
            pass

create_tables(app)

# --- FLASK-LOGIN YAPILANDIRMASI ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'giris' 
login_manager.login_message = "Bu sayfaya erişmek için lütfen giriş yapın."

@login_manager.user_loader
def load_user(user_id):
    return Kullanici.query.get(int(user_id))

def youtube_arama(arama_sorgusu):
    if not YOUTUBE_API_KEY or not YOUTUBE_API_KEY.strip():
        return ""
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
            video_listesi.append(f"{item['snippet']['title']}:::{'https://www.youtube.com/embed/' + item['id']['videoId']}")
            
        return "|||".join(video_listesi)
    except Exception:
        return ""


# --- ROTALAR ---

@app.route('/')
@app.route('/ajanda')
@login_required 
def index():
    bugun = date.today() 
    try:
        sirali_kayitlar = Kayit.query.filter_by(kullanici_id=current_user.id).order_by(Kayit.tarih).all()
    except Exception as e:
        flash(f'Ajanda verileri çekilirken hata oluştu: {e}', 'danger'); sirali_kayitlar = []

    ajanda_verileri = []
    
    for kayit in sirali_kayitlar:
        tarih_obj = kayit.tarih.date()
        kalan_gun = (tarih_obj - bugun).days
        plan_etiketi = ""; etiket_sinifi = ""

        # AI Destekli Otomatik Etiketleme Mantığı
        if kalan_gun < 0:
            plan_etiketi = "Sınav Günü Geçti 😥"
            etiket_sinifi = "gecmis"
        elif kalan_gun <= 3:
            plan_etiketi = "🚨 KRİTİK! Hemen Başla!"
            etiket_sinifi = "kritik"
        elif kalan_gun <= 7:
            plan_etiketi = "🔥 YOĞUN Çalışma Zamanı"
            etiket_sinifi = "yogun"
        else:
            plan_etiketi = "✅ Planlı İlerleme"
            etiket_sinifi = "planli"
            
        
        ajanda_verileri.append({
            'id': kayit.id,
            'ders_adi': kayit.ders_adi,
            'tarih': kayit.tarih,
            'konular': kayit.konular,
            'video_sonuc': kayit.video_sonuc,
            'kalan_gun': kalan_gun,
            'etiket': plan_etiketi, 
            'etiket_sinifi': etiket_sinifi 
        })
    
    # Artık sadece list.html'i render ediyoruz
    return render_template('list.html', kayitlar=ajanda_verileri)


@app.route('/ekle', methods=['GET', 'POST'])
@login_required
def ekle():
    if request.method == 'POST':
        
        ders_adi = request.form.get('ders_adi'); tarih_str = request.form.get('tarih'); konular = request.form.get('konular')
        
        arama_sorgusu = f"{ders_adi} {konular.split(',')[0].strip()} konu anlatımı"
        video_sonuclari_string = youtube_arama(arama_sorgusu)
        
        try:
            tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d')
            
            yeni_kayit = Kayit(
                ders_adi=ders_adi, 
                tarih=tarih_obj, 
                konular=konular,
                video_sonuc=video_sonuclari_string,
                kullanici_id=current_user.id,
                etiket="Planlı"
            )
            
            db.session.add(yeni_kayit); db.session.commit()
            flash('Yeni ajanda kaydı başarıyla oluşturuldu!', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Kayıt oluşturulurken bir hata oluştu: {e}', 'danger')
            
        return redirect(url_for('index')) # Kayıt sonrası ana listeye dön
    
    # GET isteği gelirse sadece formu gösteriyoruz
    return render_template('form.html')


@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    if request.method == 'POST':
        yeni_ad = request.form.get('kullanici_adi')
        
        if yeni_ad:
            try:
                # Kullanıcı adının benzersizliğini kontrol et
                if Kullanici.query.filter(Kullanici.kullanici_adi == yeni_ad, Kullanici.id != current_user.id).first():
                    flash('Bu kullanıcı adı zaten alınmış.', 'danger')
                else:
                    current_user.kullanici_adi = yeni_ad
                    db.session.commit()
                    flash('Kullanıcı adınız başarıyla güncellendi.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Adınız güncellenirken bir hata oluştu: {e}', 'danger')
        
        return redirect(url_for('ayarlar'))

    # Kullanıcı e-postası ve mevcut adı ayarlar sayfasına gönderilir
    return render_template('ayarlar.html')


# ... (Diğer rotalar: giris, kayitol, cikis, kayit_sil aynı kalır) ...
@app.route('/giris', methods=['GET', 'POST'])
def giris():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        eposta = request.form.get('eposta'); parola = request.form.get('parola')
        try: kullanici = Kullanici.query.filter_by(eposta=eposta).first()
        except Exception as e: flash(f'Veritabanı hatası: {e}', 'danger'); return render_template('giris.html') 
        if kullanici and kullanici.check_password(parola):
            login_user(kullanici); flash('Başarıyla giriş yaptınız!', 'success'); return redirect(url_for('index'))
        else:
            flash('Giriş başarısız. Lütfen e-posta ve şifrenizi kontrol edin.', 'danger')
    return render_template('giris.html') 

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        kullanici_adi = request.form.get('kullanici_adi'); eposta = request.form.get('eposta'); parola = request.form.get('parola')
        if not kullanici_adi or not eposta or not parola:
             flash('Tüm alanları doldurmanız gerekmektedir.', 'danger'); return redirect(url_for('kayitol'))
        try:
            if Kullanici.query.filter_by(eposta=eposta).first():
                flash('Bu e-posta adresi zaten kayıtlı.', 'warning'); return redirect(url_for('kayitol'))
            yeni_kullanici = Kullanici(kullanici_adi=kullanici_adi, eposta=eposta)
            yeni_kullanici.set_password(parola)
            db.session.add(yeni_kullanici); db.session.commit()
        except Exception as e:
            db.session.rollback(); flash(f'Kayıt işlemi sırasında veritabanı hatası oluştu: {e}', 'danger'); return redirect(url_for('kayitol'))
        flash('Hesabınız başarıyla oluşturuldu! Lütfen giriş yapın.', 'success'); return redirect(url_for('giris'))
    return render_template('kayitol.html') 

@app.route('/cikis')
@login_required 
def cikis():
    logout_user(); flash('Başarıyla çıkış yaptınız.', 'info'); return redirect(url_for('giris'))

@app.route('/sil/<int:kayit_id>', methods=['POST'])
@login_required 
def kayit_sil(kayit_id):
    try:
        kayit = Kayit.query.filter_by(id=kayit_id, kullanici_id=current_user.id).first_or_404()
        db.session.delete(kayit); db.session.commit()
        flash('Ajanda kaydı başarıyla silindi.', 'info')
    except Exception as e:
        db.session.rollback(); flash(f'Silme işlemi sırasında hata oluştu: {e}', 'danger')
    return redirect(url_for('index'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)