import sqlite3
import datetime
import random

DB_NAME = "vitals.db"
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print("⏳ Limpando banco de dados antigo...")
cursor.execute("DROP TABLE IF EXISTS vitals_history")
cursor.execute("DROP TABLE IF EXISTS tokens")
cursor.execute("DROP TABLE IF EXISTS users")

print("🏗️ Criando tabelas...")
cursor.execute('''
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    identificador TEXT,
    tipo TEXT,
    doctor_id INTEGER,
    email TEXT,
    senha_hash TEXT,
    idade INTEGER
)
''')

cursor.execute('''
CREATE TABLE tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    pulsoid_token TEXT
)
''')

cursor.execute('''
CREATE TABLE vitals_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER,
    bpm INTEGER,
    timestamp DATETIME
)
''')

print("👨‍⚕️ Inserindo cadastros demo com idades...")
# 1. Médico
cursor.execute(
    "INSERT INTO users (nome, identificador, tipo, idade) VALUES ('Dr. Resolve', 'CRM/SP123456', 'medico', 45)")
medico_id = cursor.lastrowid

# 2. Paciente 1 (Saudável, 35 anos)
cursor.execute(
    f"INSERT INTO users (nome, identificador, tipo, doctor_id, idade) VALUES ('João Silva', '10349150702', 'paciente', {medico_id}, 35)")
paciente1_id = cursor.lastrowid

# 3. Paciente 2 (Com arritmia, 62 anos)
cursor.execute(
    f"INSERT INTO users (nome, identificador, tipo, doctor_id, idade) VALUES ('Maria Oliveira', '22222222222', 'paciente', {medico_id}, 62)")
paciente2_id = cursor.lastrowid

print("🫀 Gerando histórico de batimentos simulados...")
agora = datetime.datetime.now()

# Histórico Paciente 1 (Média 70-75 BPM)
for i in range(50):
    tempo = agora - datetime.timedelta(minutes=i*15)
    bpm = random.randint(70, 75)
    cursor.execute(
        "INSERT INTO vitals_history (paciente_id, bpm, timestamp) VALUES (?, ?, ?)", (paciente1_id, bpm, tempo))

# Histórico Paciente 2 (Média 80-85 BPM, picos de 135)
for i in range(50):
    tempo = agora - datetime.timedelta(minutes=i*15)
    if 10 < i < 15:
        bpm = random.randint(130, 140)
    else:
        bpm = random.randint(80, 85)
    cursor.execute(
        "INSERT INTO vitals_history (paciente_id, bpm, timestamp) VALUES (?, ?, ?)", (paciente2_id, bpm, tempo))

conn.commit()
conn.close()

print("✅ SUCESSO! Banco de dados atualizado. Pronto para a demo!")
