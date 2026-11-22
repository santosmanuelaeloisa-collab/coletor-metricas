import socket, threading, json, sqlite3, logging, os
HOST, PORTA = "0.0.0.0", 5000                      # porta combinada 
TOKEN = os.environ.get("TOKEN", "TOKEN_123")       # o "crachá"
DB_PATH = os.environ.get("DB_PATH", "dados.db")    # onde fica o "caderno"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("servidor.log"), logging.StreamHandler()])

def salvar(m, origem):
    # cada thread abre o seu próprio acesso ao caderno
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS metricas
                  (origem TEXT, cpu REAL, memoria REAL,
                   momento TEXT DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("INSERT INTO metricas (origem,cpu,memoria) VALUES (?,?,?)",
               (origem, m["cpu"], m["memoria"]))
    db.commit()
    db.close()

def atender(conn, addr):
    logging.info(f"Conectou: {addr}")
    try:
        conn.settimeout(30)                 # se o cliente sumir, não espera para sempre
        for linha in conn.makefile():       # cada linha = 1 mensagem JSON
            try:
                m = json.loads(linha)
                if m.get("token") != TOKEN:
                    logging.warning(f"Token inválido de {addr}")
                    conn.sendall(b"ERRO token\n")
                    break
                if not all(0 <= m[k] <= 100 for k in ("cpu", "memoria")):
                    raise ValueError("valor fora de 0-100")
                salvar(m, addr[0])          # addr[0] = IP de quem conectou
                logging.info(f"Salvo de {addr[0]}: cpu={m['cpu']} memoria={m['memoria']}")
                conn.sendall(b"OK\n")
            except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as e:
                logging.warning(f"Mensagem inválida de {addr}: {e}")
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
    conn, addr = srv.accept()               # espera alguém ligar
    threading.Thread(target=atender, args=(conn, addr), daemon=True).start()
