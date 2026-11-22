"""Gera dados de teste na tabela metricas (mesmo esquema do coletor).
Uso: python seed.py [qtd_registros] [qtd_hosts] [--limpar]
Precisa de acesso de ESCRITA ao banco (o painel nunca escreve)."""
import os, random, sqlite3, sys
from datetime import datetime, timedelta, timezone

DB = os.getenv("DB", "/dados/dados.db")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
qtd = int(args[0]) if args else 500
nhosts = int(args[1]) if len(args) > 1 else 4
hosts = [f"172.20.0.{10 + i}" for i in range(nhosts)]

os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
con = sqlite3.connect(DB)
con.execute("CREATE TABLE IF NOT EXISTS metricas (origem TEXT, cpu REAL, memoria REAL, "
            "momento TEXT DEFAULT CURRENT_TIMESTAMP)")
con.execute("CREATE INDEX IF NOT EXISTS idx_origem_momento ON metricas (origem, momento)")
if "--limpar" in sys.argv:
    con.execute("DELETE FROM metricas")
agora = datetime.now(timezone.utc)
linhas = []
for i in range(qtd):  # espalha os registros no tempo, mais antigo primeiro
    t = agora - timedelta(seconds=(qtd - i) * 5 / nhosts)
    h = hosts[i % nhosts]
    linhas.append((h, round(random.uniform(5, 95), 1), round(random.uniform(20, 90), 1),
                   t.strftime("%Y-%m-%d %H:%M:%S")))
con.executemany("INSERT INTO metricas (origem, cpu, memoria, momento) VALUES (?,?,?,?)", linhas)
con.commit()
print(f"{qtd} registros inseridos para {nhosts} hosts em {DB}")
con.close()
