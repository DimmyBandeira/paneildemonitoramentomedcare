import random
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "vitals.db"


def seed() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()

        cur.execute("DELETE FROM vitals_history")
        cur.execute("DELETE FROM tokens")
        cur.execute("DELETE FROM users")
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'tokens', 'vitals_history')")

        cur.execute(
            "INSERT INTO users (nome, tipo, email, senha_hash, identificador, idade) VALUES (?, 'medico', ?, ?, ?, ?)",
            ("Dra. Marina Cardoso", "marina@medcare.local", "hash-demo", "CRM/SP123456", 45),
        )
        medico_id = cur.lastrowid

        cur.execute(
            "INSERT INTO users (nome, tipo, doctor_id, email, senha_hash, identificador, idade) VALUES (?, 'paciente', ?, ?, ?, ?, ?)",
            ("João Estável", medico_id, "joao@paciente.local", "hash-demo", "11111111111", 38),
        )
        paciente1_id = cur.lastrowid

        cur.execute(
            "INSERT INTO users (nome, tipo, doctor_id, email, senha_hash, identificador, idade) VALUES (?, 'paciente', ?, ?, ?, ?, ?)",
            ("Carlos Pico", medico_id, "carlos@paciente.local", "hash-demo", "22222222222", 52),
        )
        paciente2_id = cur.lastrowid

        cur.execute("INSERT INTO tokens (user_id, pulsoid_token) VALUES (?, ?)", (paciente1_id, "TOKEN_PULSOID_P1"))
        cur.execute("INSERT INTO tokens (user_id, pulsoid_token) VALUES (?, ?)", (paciente2_id, "TOKEN_PULSOID_P2"))

        now = datetime.utcnow()
        for day in range(7):
            for slot in range(8):
                base_time = now - timedelta(days=day, hours=slot * 3)

                bpm1 = random.randint(70, 75)
                cur.execute(
                    "INSERT INTO vitals_history (paciente_id, bpm, timestamp) VALUES (?, ?, ?)",
                    (paciente1_id, bpm1, base_time.isoformat()),
                )

                if slot in (0, 1) and day % 2 == 0:
                    bpm2 = random.randint(132, 140)
                else:
                    bpm2 = random.randint(80, 92)
                cur.execute(
                    "INSERT INTO vitals_history (paciente_id, bpm, timestamp) VALUES (?, ?, ?)",
                    (paciente2_id, bpm2, base_time.isoformat()),
                )

        conn.commit()


if __name__ == "__main__":
    seed()
    print("Seed concluído com sucesso.")
