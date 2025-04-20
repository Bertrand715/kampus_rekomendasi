from flask import Flask, render_template, request, jsonify, redirect, url_for
import mysql.connector
import pandas as pd
from datetime import datetime
import mysql.connector.errors
import difflib
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # Ganti dengan nama pengguna MySQL Anda
    'password': '',  # Ganti dengan kata sandi MySQL Anda
    'database': 'universitas_db'  # Nama database yang valid
}

def create_database():
    try:
        temp_config = db_config.copy()
        temp_config.pop('database')
        conn = mysql.connector.connect(**temp_config)
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_config['database']}")
        app.logger.debug(f"Database '{db_config['database']}' created or already exists.")
        
        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error(f"Error creating database: {err}")
        raise
    except Exception as e:
        app.logger.error(f"Unexpected error creating database: {e}")
        raise

def get_db_connection():
    try:
        return mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        app.logger.error(f"Error connecting to database: {err}")
        raise

def populate_universities():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS universities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                univ_name VARCHAR(255) NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sekolah_id INT,
                nama VARCHAR(255),
                lokasi VARCHAR(50),
                akreditasi CHAR(1),
                biaya INT,
                fasilitas INT,
                jarak INT,
                skor FLOAT,
                search_time DATETIME,
                FOREIGN KEY (sekolah_id) REFERENCES universities(id)
            )
        ''')
        
        cursor.execute('SELECT COUNT(*) FROM universities')
        count = cursor.fetchone()[0]
        
        if count == 0:
            try:
                df = pd.read_csv('data/univ_indonesia.csv', usecols=['univ_name'], 
                               skipinitialspace=True, on_bad_lines='warn', encoding='utf-8')
                df = df.dropna(subset=['univ_name'])
                df['univ_name'] = df['univ_name'].str.strip()
                df = df.drop_duplicates(subset=['univ_name'])
                
                for univ_name in df['univ_name']:
                    if univ_name:
                        cursor.execute('INSERT INTO universities (univ_name) VALUES (%s)', (univ_name,))
                conn.commit()
                app.logger.debug(f"Successfully populated universities table with {len(df)} entries.")
            except FileNotFoundError:
                app.logger.error("Error: 'univ_indonesia.csv' not found in 'data' directory.")
            except pd.errors.ParserError as e:
                app.logger.error(f"Error parsing CSV: {e}")
            except Exception as e:
                app.logger.error(f"Error populating universities: {e}")
        
        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in populate_universities: {err}")
    except Exception as e:
        app.logger.error(f"Unexpected error in populate_universities: {e}")

@app.route('/')
def home():
    app.logger.debug("Rendering home page")
    return render_template('home.html')

@app.route('/how-to-use')
def how_to_use():
    app.logger.debug("Rendering how_to_use page")
    return render_template('how_to_use.html')

@app.route('/calculator')
def calculator():
    app.logger.debug("Rendering calculator page")
    return render_template('calculator.html')

@app.route('/history')
def history():
    app.logger.debug("Rendering history page")
    page = request.args.get('page', 1, type=int)
    items_per_page = 5
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('SELECT COUNT(*) AS total FROM history')
        total_items = cursor.fetchone()['total']
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        offset = (page - 1) * items_per_page
        cursor.execute('''
            SELECT * FROM history 
            ORDER BY search_time DESC 
            LIMIT %s OFFSET %s
        ''', (items_per_page, offset))
        history = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('history.html', 
                             history=history, 
                             current_page=page, 
                             total_pages=total_pages)
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in history: {err}")
        return render_template('history.html', error=f"Database error: {err}")
    except Exception as e:
        app.logger.error(f"Unexpected error in history: {e}")
        return render_template('history.html', error=f"Unexpected error: {e}")
@app.route('/about')
def about():
    app.logger.debug("Rendering about page")
    return render_template('about.html')

@app.route('/search')
def index():
    app.logger.debug("Rendering search page")
    return render_template('index.html')

@app.route('/cari-sekolah')
def cari_sekolah():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, univ_name FROM universities WHERE univ_name LIKE %s LIMIT 20', ('%' + query + '%',))
        results = [{'id': row[0], 'text': row[1]} for row in cursor.fetchall()]
        
        filtered_results = []
        seen_names = set()
        for result in results:
            name = result['text'].lower()
            is_similar = any(difflib.SequenceMatcher(None, name, seen).ratio() > 0.9 for seen in seen_names)
            if not is_similar:
                filtered_results.append(result)
                seen_names.add(name)
        
        cursor.close()
        conn.close()
        
        return jsonify(filtered_results[:10])
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in cari_sekolah: {err}")
        return jsonify({'error': f"Database error: {err}"})
    except Exception as e:
        app.logger.error(f"Unexpected error in cari_sekolah: {e}")
        return jsonify({'error': f"Unexpected error: {e}"})

@app.route('/rekomendasi', methods=['POST'])
def rekomendasi():
    app.logger.debug("Processing rekomendasi request")
    nama = request.form.get('nama')
    sekolah_id = request.form.get('sekolah_id')
    lokasi = request.form.get('lokasi')
    akreditasi = request.form.get('akreditasi')
    biaya = int(request.form.get('biaya'))
    fasilitas = int(request.form.get('fasilitas'))
    jarak = int(request.form.get('jarak'))
    
    if not all([nama, sekolah_id, lokasi, akreditasi]) or \
       biaya < 1 or biaya > 5 or fasilitas < 1 or fasilitas > 5 or jarak < 1 or jarak > 5:
        app.logger.warning("Invalid input in rekomendasi")
        return render_template('index.html', error='Input tidak valid. Pastikan semua field terisi dan nilai antara 1-5.')
    
    bobot_akreditasi = 0.3
    bobot_biaya = 0.25
    bobot_fasilitas = 0.2
    bobot_lokasi = 0.15
    bobot_jarak = 0.1
    
    skor_akreditasi = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}.get(akreditasi, 0)
    skor_biaya = 5 - biaya
    skor_fasilitas = fasilitas
    skor_lokasi = {'Pusat Kota': 5, 'Kecamatan': 4, 'Pedesaan': 3}.get(lokasi, 0)
    skor_jarak = 5 - jarak
    
    total_skor = (skor_akreditasi * bobot_akreditasi +
                  skor_biaya * bobot_biaya +
                  skor_fasilitas * bobot_fasilitas +
                  skor_lokasi * bobot_lokasi +
                  skor_jarak * bobot_jarak)
    
    detail_perhitungan = {
        'akreditasi': {'nilai': akreditasi, 'skor': skor_akreditasi, 'bobot': '30%', 'kontribusi': round(skor_akreditasi * bobot_akreditasi, 2)},
        'biaya': {'nilai': biaya, 'skor': skor_biaya, 'bobot': '25%', 'kontribusi': round(skor_biaya * bobot_biaya, 2)},
        'fasilitas': {'nilai': fasilitas, 'skor': skor_fasilitas, 'bobot': '20%', 'kontribusi': round(skor_fasilitas * bobot_fasilitas, 2)},
        'lokasi': {'nilai': lokasi, 'skor': skor_lokasi, 'bobot': '15%', 'kontribusi': round(skor_lokasi * bobot_lokasi, 2)},
        'jarak': {'nilai': jarak, 'skor': skor_jarak, 'bobot': '10%', 'kontribusi': round(skor_jarak * bobot_jarak, 2)}
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO history (sekolah_id, nama, lokasi, akreditasi, biaya, fasilitas, jarak, skor, search_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (sekolah_id, nama, lokasi, akreditasi, biaya, fasilitas, jarak, round(total_skor, 2), datetime.now()))
        
        conn.commit()
        
        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in rekomendasi: {err}")
        return render_template('index.html', error=f"Database error: {err}")
    except Exception as e:
        app.logger.error(f"Unexpected error in rekomendasi: {e}")
        return render_template('index.html', error=f"Unexpected error: {e}")
    
    return render_template('result.html', result={
        'nama': nama,
        'skor': round(total_skor, 2),
        'detail': {
            'Lokasi': lokasi,
            'Akreditasi': akreditasi,
            'Biaya': biaya,
            'Fasilitas': fasilitas,
            'Jarak': jarak
        },
        'detail_perhitungan': detail_perhitungan
    })

if __name__ == '__main__':
    try:
        create_database()
        populate_universities()
        app.run(debug=True)
    except Exception as e:
        app.logger.error(f"Failed to start application: {e}")