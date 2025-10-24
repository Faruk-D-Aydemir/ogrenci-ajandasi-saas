#!/usr/bin/env bash

# 1. Gerekli kütüphaneleri kur
pip install -r requirements.txt

# 2. Veritabanı tablolarını oluştur (db.create_all() komutunu çalıştır)
python -c "from app import app, db; with app.app_context(): db.create_all()"