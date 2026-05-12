import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from google import genai

DB_PATH = Path("vitals.db")
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Monitor Cardiago - MedCare MVP")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('doctor', 'patient')),
                doctor_id INTEGER,
                FOREIGN KEY (doctor_id) REFERENCES users (id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vitals_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bpm INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.commit()


def seed_db() -> None:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM vitals_history")
        cur.execute("DELETE FROM users")
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'vitals_history')")

        cur.execute("INSERT INTO users (username, role) VALUES (?, ?)", ("CRM/SP123456", "doctor"))
        doctor_id = cur.lastrowid

        cur.execute("INSERT INTO users (username, role, doctor_id) VALUES (?, ?, ?)", ("11111111111", "patient", doctor_id))
        patient_1_id = cur.lastrowid
        cur.execute("INSERT INTO users (username, role, doctor_id) VALUES (?, ?, ?)", ("22222222222", "patient", doctor_id))
        patient_2_id = cur.lastrowid

        now = datetime.utcnow()
        patient_1_bpm = [72, 74, 71, 73, 75, 72, 76, 74, 73, 72]
        patient_2_bpm = [88, 92, 95, 102, 110, 120, 128, 135, 118, 90]

        for idx, bpm in enumerate(patient_1_bpm):
            ts = (now - timedelta(days=idx % 7, hours=idx)).isoformat()
            cur.execute("INSERT INTO vitals_history (user_id, bpm, timestamp) VALUES (?, ?, ?)", (patient_1_id, bpm, ts))

        for idx, bpm in enumerate(patient_2_bpm):
            ts = (now - timedelta(days=idx % 7, hours=idx + 1)).isoformat()
            cur.execute("INSERT INTO vitals_history (user_id, bpm, timestamp) VALUES (?, ?, ?)", (patient_2_id, bpm, ts))

        conn.commit()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_db()


@app.get("/")
def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={})


@app.post("/auth")
async def auth(request: Request):
    payload = await request.json()
    username = str(payload.get("username", "")).strip().upper()
    if "CRM" in username and re.fullmatch(r"CRM\/[A-Z]{2}\d{6}", username):
        return {"redirect_url": "/dashboard/medico"}
    if re.fullmatch(r"\d{11}", username):
        return {"redirect_url": f"/dashboard/paciente?cpf={username}"}
    return JSONResponse(status_code=400, content={"error": "Formato inválido"})


@app.get("/dashboard/medico")
def doctor_dashboard(request: Request):
    with closing(get_conn()) as conn:
        patients = conn.execute(
            """
            SELECT u.id, u.username,
                   (SELECT bpm FROM vitals_history vh WHERE vh.user_id = u.id ORDER BY timestamp DESC LIMIT 1) AS latest_bpm
            FROM users u
            WHERE u.role = 'patient'
            ORDER BY u.id
            """
        ).fetchall()
    pulsoid_token = os.getenv("PULSOID_ACCESS_TOKEN", "TOKEN_DO_PACIENTE")
    return TEMPLATES.TemplateResponse(request=request, name="dashboard_medico.html", context={"patients": patients, "pulsoid_token": pulsoid_token})


@app.get("/dashboard/paciente")
def patient_dashboard(request: Request, cpf: str | None = None):
    with closing(get_conn()) as conn:
        if cpf:
            patient = conn.execute("SELECT id, username FROM users WHERE role='patient' AND username=? LIMIT 1", (cpf,)).fetchone()
        else:
            patient = conn.execute("SELECT id, username FROM users WHERE role='patient' ORDER BY id LIMIT 1").fetchone()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    pulsoid_token = os.getenv("PULSOID_ACCESS_TOKEN", "TOKEN_DO_PACIENTE")
    return TEMPLATES.TemplateResponse(request=request, name="dashboard_paciente.html", context={"patient": patient, "pulsoid_token": pulsoid_token})


@app.post("/api/gemini/analyze/{paciente_id}")
def analyze_patient(paciente_id: int):
    with closing(get_conn()) as conn:
        patient = conn.execute("SELECT id, username FROM users WHERE id=? AND role='patient'", (paciente_id,)).fetchone()
        if not patient:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")

        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        stats = conn.execute(
            """
            SELECT ROUND(AVG(bpm), 1) as avg_bpm, MAX(bpm) as max_bpm
            FROM vitals_history
            WHERE user_id=? AND timestamp >= ?
            """,
            (paciente_id, seven_days_ago),
        ).fetchone()

    avg_bpm = stats["avg_bpm"] if stats and stats["avg_bpm"] is not None else 0
    max_bpm = stats["max_bpm"] if stats and stats["max_bpm"] is not None else 0

    prompt = (
        "Você é um assistente cardiológico experiente. O paciente [NOME_PACIENTE] apresentou nos últimos "
        "7 dias uma frequência cardíaca de repouso (RHR) média de [MEDIA_BPM] BPM, com picos de [MAX_BPM] BPM. "
        f"O paciente teve média de {avg_bpm} BPM e pico de {max_bpm} BPM nos últimos 7 dias. "
        "Com base nestes dados de monitoramento contínuo: 1) Projete o nível de estresse e qualidade do sono; "
        "2) Dê 3 insights curtos e acionáveis sobre estilo de vida; 3) Aponte possíveis sinais de alerta "
        "(ex: suspeita de arritmia) para o médico. Responda em formato de relatório médico conciso, "
        "profissional e em português."
    )
    prompt = prompt.replace("[NOME_PACIENTE]", patient["username"]).replace("[MEDIA_BPM]", str(avg_bpm)).replace("[MAX_BPM]", str(max_bpm))

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return JSONResponse({"insight": "GEMINI_API_KEY não configurada. Relatório indisponível no ambiente atual."})

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return {"insight": (response.text or "").strip()}
