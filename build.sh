#!/usr/bin/env bash

# 1. Gerekli kütüphaneleri kur
pip install -r requirements.txt

# 2. Veritabanı tablolarını oluştur (Mutlak Python yolu ile zorla çalıştırma)
/usr/bin/env python -c "from app import app, db; with app.app_context(): db.create_all()"