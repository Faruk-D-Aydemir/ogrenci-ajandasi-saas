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
import random

load_dotenv() 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") 

app = Flask(__name__)

# --- UYGULAMA YAPILANDIRMASI (VERİ TABANI VE GİZLİ ANAHTAR) ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

# PostgreSQL uyumluluğu için düzeltme
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

if not app.config['SQLALCHEMY_DATABASE_URI']:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///proje_ajandasi.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cok_gizli_bir_anahtar') 

# SESSION AYARLARI
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
    calisma_saatleri_json = db.Column(db.Text, default='{}') 
    okul_saatleri = db.Column(db.String(50), default='08:00-17:00') 

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

class ProgramGorev(db.Model):
    __tablename__ = 'program_gorev'
    id = db.Column(db.Integer, primary_key=True)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    kayit_id = db.Column(db.Integer, db.ForeignKey('kayit.id'))
    gorev_tarihi = db.Column(db.Date, nullable=False)
    baslangic_saati = db.Column(db.Time, nullable=False)
    bitis_saati = db.Column(db.Time, nullable=False)
    gorev_adi = db.Column(db.String(200), nullable=False)
    tamamlandi = db.Column(db.Boolean, default=False)
    gorev_sirasi = db.Column(db.Integer, default=0)
    
# --- TABLOLARI OLUŞTURMA İŞLEVİ ---
def create_tables(uygulama):
    with uygulama.app_context():
        try:
            db.create_all()
            print("INFO: Veritabanı tabloları başarıyla oluşturuldu/güncellendi.") 
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

# --- PROGRAM OLUŞTURMA ALGORİTMASI (DÜZELTİLMİŞ) ---
def program_olustur_algo(kullanici_id):
    kullanici = Kullanici.query.get(kullanici_id)
    if not kullanici: return False

    bugun = date.today()
    bitis_tarihi = bugun + timedelta(days=7) 
    yaklasan_kayitlar = Kayit.query.filter(
        Kayit.kullanici_id == kullanici_id,
        Kayit.tarih.cast(db.Date) > bugun,
        Kayit.tarih.cast(db.Date) <= bitis_tarihi 
    ).order_by(Kayit.tarih).all()
    
    if not yaklasan_kayitlar: return False 

    ProgramGorev.query.filter_by(kullanici_id=kullanici_id).delete()
    db.session.commit()

    try:
        bos_saatler = json.loads(kullanici.calisma_saatleri_json)
    except:
        bos_saatler = {}
    
    try:
        okul_bas_str, okul_bit_str = kullanici.okul_saatleri.split('-')
        okul_bas = time.fromisoformat(okul_bas_str)
        okul_bit = time.fromisoformat(okul_bit_str)
    except:
        okul_bas = time(8, 0)
        okul_bit = time(17, 0)

    gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
    gorev_sirasi = 0
    
    gorev_havuzu = []
    
    for kayit in yaklasan_kayitlar:
        kalan_gun = (kayit.tarih.date() - bugun).days
        
        if kalan_gun <= 2:
            suresi = 3 * 60 
            zorluk = "KRİTİK"
        elif kalan_gun <= 4:
            suresi = 2 * 60 
            zorluk = "YOĞUN"
        else:
            suresi = 1 * 60 
            zorluk = "PLANLI"

        konu_suresi = int(suresi * 0.6)
        soru_suresi = int(suresi * 0.4)
        
        gorev_havuzu.append({'kayit_id': kayit.id, 'kayit': kayit, 'suresi': konu_suresi, 'tip': 'Konu Anlatımı/Video İzle', 'zorluk': zorluk})
        gorev_havuzu.append({'kayit_id': kayit.id, 'kayit': kayit, 'suresi': soru_suresi, 'tip': 'Soru Çözme/Tekrar', 'zorluk': zorluk})
    
    gorev_havuzu.sort(key=lambda x: x['zorluk'], reverse=True)

    for i in range(7):
        suanki_tarih = bugun + timedelta(days=i)
        gun_adi = gunler[suanki_tarih.weekday()]

        if gun_adi in bos_saatler:
            try:
                bos_bas_str, bos_bit_str = bos_saatler[gun_adi].split('-')
                
                calisma_baslangici = datetime.combine(suanki_tarih, time.fromisoformat(bos_bas_str))
                calisma_bitisi = datetime.combine(suanki_tarih, time.fromisoformat(bos_bit_str))
                
                # Okul/Sınırlı saatleri kontrol et
                okul_baslangic_dt = datetime.combine(suanki_tarih, okul_bas)
                okul_bitis_dt = datetime.combine(suanki_tarih, okul_bit)
                
                # --- 🛠️ DÜZELTİLMİŞ OKUL SAATLERİ ATLATMA MANTIĞI ---
                
                # Eğer boş zaman okul saatleriyle çakışıyorsa (Okul sonrası çalışmaya başla veya atla)
                if calisma_baslangici < okul_bitis_dt and calisma_bitisi > okul_baslangic_dt:
                    
                    if calisma_baslangici >= okul_bitis_dt:
                        # Eğer boş zaman okul bittikten sonra başlıyorsa sorun yok
                        pass 
                    elif calisma_baslangici < okul_bitis_dt and calisma_bitisi > okul_bitis_dt:
                        # Boş zaman okul saatleri içinde başlıyor, başlangıcı okul bitişine taşı
                        calisma_baslangici = okul_bitis_dt
                    elif calisma_baslangici < okul_baslangic_dt and calisma_bitisi > okul_bitis_dt:
                        # Boş zaman okul öncesi ve sonrası kapsıyorsa, başlangıcı okul bitişine taşı (Okul sonrası çalış)
                        calisma_baslangici = okul_bitis_dt 
                    elif calisma_baslangici >= okul_baslangic_dt and calisma_bitisi <= okul_bitis_dt:
                        # Boş zaman tamamen okul içinde, bu günü ATLA
                        continue 
                
                # ----------------------------------------------------

                suanki_zaman = calisma_baslangici
                
                while suanki_zaman < calisma_bitisi and gorev_havuzu:
                    
                    gorev = gorev_havuzu.pop(0)
                    gorev_suresi_td = timedelta(minutes=gorev['suresi'])
                    gorev_bitis_zamani = suanki_zaman + gorev_suresi_td
                    
                    if gorev_bitis_zamani <= calisma_bitisi:
                        gorev_sirasi += 1
                        yeni_gorev = ProgramGorev(
                            kullanici_id=kullanici_id,
                            kayit_id=gorev['kayit_id'],
                            gorev_tarihi=suanki_tarih.date(),
                            baslangic_saati=suanki_zaman.time(),
                            bitis_saati=gorev_bitis_zamani.time(),
                            gorev_adi=f"[{gorev['zorluk']}] {gorev['kayit'].ders_adi}: {gorev['tip']}",
                            gorev_sirasi=gorev_sirasi
                        )
                        db.session.add(yeni_gorev)
                        suanki_zaman = gorev_bitis_zamani + timedelta(minutes=15)
                    else:
                        gorev_havuzu.insert(0, gorev)
                        break

            except Exception:
                continue 
    
    db.session.commit()
    return True


# --- ROTALAR ---

@app.route('/')
def ana_sayfa_yonlendirme():
    # 404 HATASI DÜZELTME ROTASI
    if not current_user.is_authenticated:
        return redirect(url_for('giris'))
    return redirect(url_for('index'))


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
            flash('Hatalı e-posta veya parola.', 'danger')
    return render_template('giris.html')

@app.route('/kayitol', methods=['GET', 'POST'])
def kayitol():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        kullanici_adi = request.form.get('kullanici_adi')
        eposta = request.form.get('eposta')
        parola = request.form.get('parola')

        if Kullanici.query.filter_by(eposta=eposta).first():
            flash('Bu e-posta adresi zaten kayıtlı.', 'danger')
            return redirect(url_for('kayitol'))
        
        if Kullanici.query.filter_by(kullanici_adi=kullanici_adi).first():
            flash('Bu kullanıcı adı zaten alınmış.', 'danger')
            return redirect(url_for('kayitol'))

        yeni_kullanici = Kullanici(kullanici_adi=kullanici_adi, eposta=eposta)
        yeni_kullanici.set_password(parola)
        
        try:
            db.session.add(yeni_kullanici)
            db.session.commit()
            flash('Kayıt başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.', 'success')
            return redirect(url_for('giris'))
        except Exception as e:
            db.session.rollback()
            flash(f'Kayıt sırasında bir hata oluştu: {e}', 'danger')

    return render_template('kayitol.html')

@app.route('/cikis')
@login_required
def cikis():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'info')
    return redirect(url_for('giris'))

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

        if kalan_gun < 0:
            plan_etiketi = "Sınav Günü Geçti 😥"; etiket_sinifi = "gecmis"
        elif kalan_gun <= 3:
            plan_etiketi = "🚨 KRİTİK! Hemen Başla!"; etiket_sinifi = "kritik"
        elif kalan_gun <= 7:
            plan_etiketi = "🔥 YOĞUN Çalışma Zamanı"; etiket_sinifi = "yogun"
        else:
            plan_etiketi = "✅ Planlı İlerleme"; etiket_sinifi = "planli"
            
        ajanda_verileri.append({
            'id': kayit.id, 'ders_adi': kayit.ders_adi, 'tarih': kayit.tarih, 'konular': kayit.konular,
            'video_sonuc': kayit.video_sonuc, 'kalan_gun': kalan_gun, 'etiket': plan_etiketi, 'etiket_sinifi': etiket_sinifi 
        })
    
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
                ders_adi=ders_adi, tarih=tarih_obj, konular=konular,
                video_sonuc=video_sonuclari_string, kullanici_id=current_user.id, etiket="Planlı"
            )
            db.session.add(yeni_kayit); db.session.commit()
            flash('Yeni ajanda kaydı başarıyla oluşturuldu! Programınızı şimdi oluşturabilirsiniz.', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Kayıt oluşturulurken bir hata oluştu: {e}', 'danger')
            
        return redirect(url_for('index'))
    
    return render_template('form.html')

@app.route('/kayit_sil/<int:kayit_id>', methods=['POST'])
@login_required
def kayit_sil(kayit_id):
    kayit = Kayit.query.filter_by(id=kayit_id, kullanici_id=current_user.id).first()
    
    if kayit:
        try:
            ProgramGorev.query.filter_by(kayit_id=kayit_id).delete()
            db.session.delete(kayit)
            db.session.commit()
            flash(f"'{kayit.ders_adi}' kaydı başarıyla silindi.", 'info')
        except Exception as e:
            db.session.rollback()
            flash(f"Kayıt silinirken bir hata oluştu: {e}", 'danger')
    else:
        flash("Silinecek kayıt bulunamadı.", 'warning')

    return redirect(url_for('index'))

@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    kullanici = current_user
    
    if request.method == 'POST':
        if 'kullanici_adi' in request.form:
            yeni_ad = request.form.get('kullanici_adi')
            if yeni_ad:
                try:
                    if Kullanici.query.filter(Kullanici.kullanici_adi == yeni_ad, Kullanici.id != kullanici.id).first():
                        flash('Bu kullanıcı adı zaten alınmış.', 'danger')
                    else:
                        kullanici.kullanici_adi = yeni_ad
                        db.session.commit()
                        flash('Kullanıcı adınız başarıyla güncellendi.', 'success')
                except Exception as e:
                    db.session.rollback(); flash(f'Adınız güncellenirken bir hata oluştu: {e}', 'danger')
        
        elif 'okul_saatleri' in request.form:
            okul_saatleri = request.form.get('okul_saatleri')
            gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
            bos_saatleri_dict = {}

            for gun in gunler:
                bos_saat = request.form.get(gun)
                if bos_saat:
                    bos_saatleri_dict[gun] = bos_saat
            
            try:
                kullanici.okul_saatleri = okul_saatleri
                kullanici.calisma_saatleri_json = json.dumps(bos_saatleri_dict)
                db.session.commit()
                flash('Programlama ayarlarınız başarıyla kaydedildi!', 'success')
            except Exception as e:
                db.session.rollback(); flash(f'Ayarlar kaydedilirken bir hata oluştu: {e}', 'danger')
        
        return redirect(url_for('ayarlar'))

    mevcut_bos_saatler = json.loads(kullanici.calisma_saatleri_json or '{}')
    
    return render_template(
        'ayarlar.html', 
        mevcut_okul_saatleri=kullanici.okul_saatleri,
        mevcut_bos_saatler=mevcut_bos_saatler
    )

@app.route('/program', methods=['GET'])
@login_required
def program():
    gorevler = ProgramGorev.query.filter_by(kullanici_id=current_user.id).order_by(ProgramGorev.gorev_tarihi, ProgramGorev.baslangic_saati).all()
    
    program_verisi = {}
    for gorev in gorevler:
        if isinstance(gorev.gorev_tarihi, date):
            tarih_str = gorev.gorev_tarihi.strftime('%Y-%m-%d')
        else:
            tarih_str = date.today().strftime('%Y-%m-%d')
            
        if tarih_str not in program_verisi:
            program_verisi[tarih_str] = []
        program_verisi[tarih_str].append({
            'id': gorev.id,
            'baslangic': gorev.baslangic_saati.strftime('%H:%M'),
            'bitis': gorev.bitis_saati.strftime('%H:%M'),
            'gorev': gorev.gorev_adi,
            'tamamlandi': gorev.tamamlandi
        })
    
    return render_template('program.html', program_verisi=program_verisi)

@app.route('/program/olustur', methods=['POST'])
@login_required
def program_olustur():
    if program_olustur_algo(current_user.id):
        flash('Çalışma programınız başarıyla oluşturuldu! Aşağıdan kontrol edebilirsiniz.', 'success')
    else:
        flash('Program oluşturulamadı. Ya boş zamanlarınız tanımlı değil ya da yakın zamanda (7 gün içinde) bir sınav kaydı bulunmamaktadır.', 'info')
    
    return redirect(url_for('program'))

@app.route('/program/guncelle/<int:gorev_id>', methods=['POST'])
@login_required
def program_guncelle(gorev_id):
    gorev = ProgramGorev.query.filter_by(id=gorev_id, kullanici_id=current_user.id).first()
    if gorev:
        tamamlandi = request.form.get('tamamlandi') == 'on' 
        gorev.tamamlandi = tamamlandi
        try:
            db.session.commit()
        except:
            db.session.rollback()
            flash('Görev durumu güncellenirken bir hata oluştu.', 'danger')
    
    return redirect(url_for('program'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)