import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "vitals.db"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

load_dotenv()

app = FastAPI(title="Monitor Cardiago - Monolito Modular MVP")


class VitalPayload(BaseModel):
    bpm: int = Field(..., ge=25, le=240)
    source: str = Field(default="pulsoid_real", max_length=40)


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


def fetch_patients_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.nome, p.identificador, p.idade,
               COALESCE(p.data_source, 'demo') AS data_source,
               COALESCE(p.scenario, 'Paciente de demonstração') AS scenario,
               (SELECT bpm FROM vitals_history vh WHERE vh.paciente_id = p.id ORDER BY timestamp DESC LIMIT 1) AS bpm_atual,
               (SELECT timestamp FROM vitals_history vh WHERE vh.paciente_id = p.id ORDER BY timestamp DESC LIMIT 1) AS ultimo_evento,
               (SELECT ROUND(AVG(vh.bpm), 1) FROM vitals_history vh WHERE vh.paciente_id = p.id) AS media_bpm,
               (SELECT MAX(vh.bpm) FROM vitals_history vh WHERE vh.paciente_id = p.id) AS pico_bpm,
               (SELECT COUNT(1) FROM vitals_history vh WHERE vh.paciente_id = p.id) AS total_historico
        FROM users p
        WHERE p.tipo='paciente'
        ORDER BY CASE WHEN p.data_source='pulsoid_real' THEN 0 ELSE 1 END, p.id
        """
    ).fetchall()

    patients: list[dict[str, Any]] = []
    for row in rows:
        patients.append({
            'id': row['id'],
            'nome': row['nome'],
            'identificador': row['identificador'],
            'idade': row['idade'],
            'data_source': row['data_source'],
            'scenario': row['scenario'],
            'bpm_atual': row['bpm_atual'],
            'ultimo_evento': row['ultimo_evento'],
            'media_bpm': row['media_bpm'],
            'pico_bpm': row['pico_bpm'],
            'total_historico': row['total_historico'] or 0,
        })
    return patients


@app.get("/dashboard/medico")
def dashboard_medico(request: Request):
    with closing(get_conn()) as conn:
        pacientes = fetch_patients_summary(conn)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard_medico.html",
        context={"pacientes": pacientes},
    )


@app.get("/api/patients/summary")
def get_patients_summary() -> dict[str, list[dict[str, Any]]]:
    with closing(get_conn()) as conn:
        patients = fetch_patients_summary(conn)
    return {"patients": patients}


@app.get("/dashboard/paciente")
def dashboard_paciente(request: Request, cpf: str | None = None):
    with closing(get_conn()) as conn:
        if cpf:
            paciente = conn.execute(
                "SELECT id, nome, identificador FROM users WHERE tipo='paciente' AND identificador=? LIMIT 1",
                (cpf,),
            ).fetchone()
        else:
            paciente = conn.execute(
                "SELECT id, nome, identificador FROM users WHERE tipo='paciente' ORDER BY id LIMIT 1").fetchone()

        if not paciente:
            raise HTTPException(
                status_code=404, detail="Paciente não encontrado")

        token_row = conn.execute(
            "SELECT pulsoid_token FROM tokens WHERE user_id=? LIMIT 1", (paciente["id"],)).fetchone()

    pulsoid_token = (token_row["pulsoid_token"] if token_row else None) or os.getenv(
        "PULSOID_TOKEN", "TOKEN_DO_PACIENTE")
    return TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard_paciente.html",
        context={"paciente": paciente, "pulsoid_token": pulsoid_token},
    )


@app.post("/api/vitals/{paciente_id}")
def save_vital(paciente_id: int, payload: VitalPayload) -> dict[str, Any]:
    with closing(get_conn()) as conn:
        paciente = conn.execute(
            "SELECT id FROM users WHERE id=? AND tipo='paciente' LIMIT 1",
            (paciente_id,),
        ).fetchone()
        if not paciente:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")

        timestamp = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO vitals_history (paciente_id, bpm, timestamp)
            VALUES (?, ?, ?)
            """,
            (paciente_id, payload.bpm, timestamp),
        )
        conn.commit()

    return {"ok": True, "paciente_id": paciente_id, "bpm": payload.bpm, "timestamp": timestamp}


def _build_local_insight(nome: str, idade: int, media_bpm: float, pico_bpm: int, total: int) -> str:
    if total <= 0:
        tendencia = "Dados insuficientes na última semana para tendência robusta."
        insights = (
            "- Priorizar coleta contínua por pelo menos 7 dias para maior confiabilidade.\n"
            "- Registrar horários de sono, cafeína e estresse para correlacionar com o BPM.\n"
            "- Revisar aderência ao sensor para reduzir lacunas de telemetria."
        )
    else:
        if media_bpm >= 100 or pico_bpm >= 130:
            tendencia = "Tendência de frequência elevada com picos relevantes."
        elif media_bpm <= 50:
            tendencia = "Tendência de frequência reduzida, exigindo contexto clínico."
        else:
            tendencia = "Tendência estável na maior parte das amostras disponíveis."
        insights = (
            "- Manter rotina regular de sono e hidratação para reduzir variabilidade.\n"
            "- Monitorar gatilhos (estresse, exercício, cafeína) próximos aos picos.\n"
            "- Se picos/sintomas persistirem, considerar avaliação médica direcionada."
        )

    return (
        f"Paciente: {nome} ({idade} anos).\n"
        f"Amostras (7 dias): {total}. Média: {media_bpm} BPM. Pico: {pico_bpm} BPM.\n\n"
        f"1) Tendência objetiva\n{tendencia}\n\n"
        f"2) Insights acionáveis\n{insights}\n\n"
        "3) Sinais de alerta para investigação\n"
        "- Dor torácica, dispneia, síncope, palpitações persistentes ou piora funcional.\n"
        "- Picos repetidos em repouso ou taquicardia associada a sintomas.\n\n"
        "4) Este relatório é de apoio e não substitui avaliação médica presencial."
    )


@app.post("/api/gemini/analyze/{paciente_id}")
def gemini_analyze(paciente_id: int) -> dict[str, Any]:
    with closing(get_conn()) as conn:
        paciente = conn.execute(
            "SELECT id, nome, idade, data_source FROM users WHERE id=? AND tipo='paciente'",
            (paciente_id,),
        ).fetchone()
        if not paciente:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")

        start = (datetime.utcnow() - timedelta(days=7)).isoformat()
        stats = conn.execute(
            """
            SELECT ROUND(AVG(bpm), 1) AS media_bpm,
                   MAX(bpm) AS pico_bpm,
                   COUNT(*) AS total
            FROM vitals_history
            WHERE paciente_id=? AND timestamp >= ?
            """,
            (paciente_id, start),
        ).fetchone()

        rows = conn.execute(
            """
            SELECT bpm, timestamp, source
            FROM vitals_history
            WHERE paciente_id=? AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 30
            """,
            (paciente_id, start),
        ).fetchall()

    media_bpm = float(stats["media_bpm"] if stats and stats["media_bpm"] is not None else 0)
    pico_bpm = int(stats["pico_bpm"] if stats and stats["pico_bpm"] is not None else 0)
    total = int(stats["total"] if stats else 0)

    history_text = ", ".join(
        f"{row['bpm']} BPM em {row['timestamp']} ({row['source']})"
        for row in rows
    )

    fallback = _build_local_insight(
        str(paciente["nome"]),
        int(paciente["idade"]),
        media_bpm,
        pico_bpm,
        total,
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "insight": fallback,
            "media_bpm": media_bpm,
            "pico_bpm": pico_bpm,
            "source": "fallback_no_api_key",
        }

    prompt = (
        "Você é um assistente cardiológico de apoio, sem emitir diagnóstico definitivo. "
        f"Paciente: {paciente['nome']}. "
        f"Idade: {paciente['idade']} anos. "
        f"Fonte do paciente: {paciente['data_source']}. "
        f"Nos últimos 7 dias, média de frequência cardíaca: {media_bpm} BPM, "
        f"pico: {pico_bpm} BPM, amostras: {total}. "
        f"Histórico recente: {history_text or 'sem amostras'}. "
        "Forneça em português: "
        "1) leitura objetiva de tendência; "
        "2) três insights acionáveis; "
        "3) sinais de alerta que justificam investigação; "
        "4) ressalva de que não substitui avaliação médica. "
        "Se os dados forem insuficientes, diga isso claramente."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
        )

        return {
            "insight": (response.text or fallback).strip(),
            "media_bpm": media_bpm,
            "pico_bpm": pico_bpm,
            "source": "gemini",
        }

    except genai_errors.ClientError as exc:
        return {
            "insight": (
                "A IA externa não respondeu agora. "
                "O sistema manteve a análise local abaixo.\n\n"
                f"Motivo técnico: {exc}\n\n"
                f"{fallback}"
            ),
            "media_bpm": media_bpm,
            "pico_bpm": pico_bpm,
            "source": "fallback_gemini_client_error",
        }

    except Exception as exc:
        return {
            "insight": (
                "Falha inesperada ao consultar a IA externa. "
                "O sistema manteve a análise local abaixo.\n\n"
                f"Motivo técnico: {exc}\n\n"
                f"{fallback}"
            ),
            "media_bpm": media_bpm,
            "pico_bpm": pico_bpm,
            "source": "fallback_unexpected_error",
        }
