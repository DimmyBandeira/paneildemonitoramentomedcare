import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "vitals.db"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

load_dotenv()

app = FastAPI(title="Monitor Cardiago - Monolito Modular MVP")


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
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('medico', 'paciente')),
                doctor_id INTEGER,
                email TEXT,
                senha_hash TEXT,
                identificador TEXT UNIQUE,
                idade INTEGER DEFAULT 40,
                FOREIGN KEY (doctor_id) REFERENCES users(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pulsoid_token TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vitals_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER NOT NULL,
                bpm INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (paciente_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/")
def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={})


@app.post("/auth")
async def auth_route(request: Request):
    payload = await request.json()
    credential = str(payload.get("credential", "")).strip().upper()

    if re.fullmatch(r"CRM\/[A-Z]{2}\d{6}", credential):
        return {"redirect_url": "/dashboard/medico"}
    if re.fullmatch(r"\d{11}", credential):
        return {"redirect_url": f"/dashboard/paciente?cpf={credential}"}

    return JSONResponse(status_code=400, content={"error": "Formato inválido. Use CRM/SP123456 ou CPF com 11 dígitos."})


@app.get("/dashboard/medico")
def dashboard_medico(request: Request):
    with closing(get_conn()) as conn:
        pacientes = conn.execute(
            """
            SELECT p.id, p.nome, p.identificador, p.idade,
                   (SELECT bpm FROM vitals_history vh WHERE vh.paciente_id = p.id ORDER BY timestamp DESC LIMIT 1) AS bpm_atual,
                   (SELECT pulsoid_token FROM tokens tk WHERE tk.user_id = p.id LIMIT 1) AS pulsoid_token
            FROM users p
            WHERE p.tipo='paciente'
            ORDER BY p.id
            """
        ).fetchall()

    return TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard_medico.html",
        context={"pacientes": pacientes},
    )


@app.get("/dashboard/paciente")
def dashboard_paciente(request: Request, cpf: str | None = None):
    with closing(get_conn()) as conn:
        if cpf:
            paciente = conn.execute(
                "SELECT id, nome, identificador FROM users WHERE tipo='paciente' AND identificador=? LIMIT 1",
                (cpf,),
            ).fetchone()
        else:
            paciente = conn.execute("SELECT id, nome, identificador FROM users WHERE tipo='paciente' ORDER BY id LIMIT 1").fetchone()

        if not paciente:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")

        token_row = conn.execute("SELECT pulsoid_token FROM tokens WHERE user_id=? LIMIT 1", (paciente["id"],)).fetchone()

    pulsoid_token = (token_row["pulsoid_token"] if token_row else None) or os.getenv("PULSOID_TOKEN", "TOKEN_DO_PACIENTE")
    return TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard_paciente.html",
        context={"paciente": paciente, "pulsoid_token": pulsoid_token},
    )


@app.post("/api/gemini/analyze/{paciente_id}")
def gemini_analyze(paciente_id: int):
    with closing(get_conn()) as conn:
        paciente = conn.execute(
            "SELECT id, nome, idade FROM users WHERE id=? AND tipo='paciente'",
            (paciente_id,),
        ).fetchone()
        if not paciente:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")

        start = (datetime.utcnow() - timedelta(days=7)).isoformat()
        stats = conn.execute(
            """
            SELECT ROUND(AVG(bpm), 1) AS media_bpm, MAX(bpm) AS pico_bpm
            FROM vitals_history
            WHERE paciente_id=? AND timestamp >= ?
            """,
            (paciente_id, start),
        ).fetchone()

    media_bpm = stats["media_bpm"] if stats and stats["media_bpm"] is not None else 0
    pico_bpm = stats["pico_bpm"] if stats and stats["pico_bpm"] is not None else 0

    prompt = (
        f"Você é um assistente cardiológico. O paciente {paciente['nome']} tem {paciente['idade']} anos. "
        f"Nos últimos 7 dias, sua frequência cardíaca de repouso (RHR) média foi de {media_bpm} BPM, "
        f"com picos de {pico_bpm} BPM. Forneça: 1) Projeção sobre o nível de estresse e qualidade do sono; "
        "2) Três insights acionáveis sobre mudança de estilo de vida; 3) Possíveis sinais de alerta clínicos "
        "para investigação. Responda em formato de relatório médico conciso."
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"insight": "GEMINI_API_KEY não configurada no .env.", "media_bpm": media_bpm, "pico_bpm": pico_bpm}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)

    return {"insight": (response.text or "").strip(), "media_bpm": media_bpm, "pico_bpm": pico_bpm}
