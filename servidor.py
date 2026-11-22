import socket, threading, json, sqlite3, logging, os

HOST = "0.0.0.0"
PORTA = int(os.environ.get("PORTA", "5000"))        # porta combinada
TOKEN = os.environ.get("TOKEN", "segredo123")       # o "cracha" (mesmo padrao do agente)
DB_PATH = os.environ.get("DB_PATH", "dados.db")     # onde fica o "caderno"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("servidor.log"), logging.StreamHandler()])

CAMPOS_PERCENTUAL = ("cpu", "mem", "disco")
CAMPOS_REDE = ("rede_enviado", "rede_recebido")


def salvar(m, origem):
    # cada thread abre o seu proprio acesso ao caderno
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS metricas
                  (origem TEXT, host TEXT, timestamp TEXT,
                   cpu REAL, mem REAL, disco REAL,
                   rede_enviado INTEGER, rede_recebido INTEGER,
                   momento TEXT DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""INSERT INTO metricas
                  (origem, host, timestamp, cpu, mem, disco, rede_enviado, rede_recebido)
                  VALUES (?,?,?,?,?,?,?,?)""",
               (origem, m["host"], m["timestamp"], m["cpu"], m["mem"], m["disco"],
                m["rede_enviado"], m["rede_recebido"]))
    db.commit()
    db.close()


def validar(m):
    if not all(0 <= m[k] <= 100 for k in CAMPOS_PERCENTUAL):
        raise ValueError("valor fora de 0-100")
    if not all(m[k] >= 0 for k in CAMPOS_REDE):
        raise ValueError("valor de rede negativo")
    if not isinstance(m["host"], str) or not isinstance(m["timestamp"], str):
        raise ValueError("host/timestamp invalidos")


def atender(conn, addr):
    logging.info(f"Conectou: {addr}")
    try:
        conn.settimeout(30)                 # se o cliente sumir, nao espera para sempre
        for linha in conn.makefile():       # cada linha = 1 mensagem JSON
            try:
                m = json.loads(linha)
                if m.get("token") != TOKEN:
                    logging.warning(f"Token invalido de {addr}")
                    conn.sendall(b"ERRO token\n")
                    break
                validar(m)
                salvar(m, addr[0])          # addr[0] = IP de quem conectou
                logging.info(f"Salvo de {m['host']} ({addr[0]}): cpu={m['cpu']} "
                             f"mem={m['mem']} disco={m['disco']}")
                conn.sendall(b"OK\n")
            except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as e:
                logging.warning(f"Mensagem invalida de {addr}: {e}")
                conn.sendall(b"ERRO mensagem\n")
    except (socket.timeout, ConnectionError):
        logging.info(f"Cliente saiu ou deu timeout: {addr}")
    finally:
        conn.close()


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((HOST, PORTA))
srv.listen()
logging.info(f"Servidor ouvindo na porta {PORTA}")
print(f"Servidor ouvindo na porta {PORTA}...")
while True:
    conn, addr = srv.accept()               # espera alguem ligar
    threading.Thread(target=atender, args=(conn, addr), daemon=True).start()
