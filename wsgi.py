from app import app, db 

# Uygulama bağlamı içinde veritabanı tablolarını oluşturma işlemini zorla
# Bu, UndefinedTable hatasını çözmek için yapılmıştır.
with app.app_context():
    db.create_all()

# Ana uygulamayı gunicorn'a sunmak için app'i hazırla
if __name__ == '__main__':
    from gunicorn.app.wsgiapp import WSGIApp
    WSGIApp("app:app").run()