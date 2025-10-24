from app import app
from gunicorn.app.wsgiapp import WSGIApp

# Sadece uygulamayı başlatır, tablo oluşturma Build Command'a taşındı.
if __name__ == '__main__':
    WSGIApp("app:app").run()