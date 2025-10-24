from app import app, db 

# Uygulama bağlamı içinde veritabanı tablolarını oluştur
with app.app_context():
    db.create_all()

# Ana uygulamayı gunicorn'a sunmak için app'i hazırla
if __name__ == '__main__':
    from gunicorn.app.wsgiapp import WSGIApp
    WSGIApp("app:app").run()