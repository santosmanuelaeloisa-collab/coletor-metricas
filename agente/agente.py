#!/usr/bin/env python3
"""
agente.py - Agente coletor de metricas (Pessoa 1).

Le CPU, memoria, disco e rede da maquina com psutil e envia, a cada
INTERVALO segundos, um JSON via TCP para o coletor (servidor).

Protocolo (uma mensagem JSON por linha, terminada em '\n'):
  {"token": "...", "host": "agente1", "timestamp": "2026-11-22T01:20:00",
   "cpu": 12.5, "mem": 43.1, "disco": 57.0, "rede_enviado": 1234, "rede_recebido": 5678}
Resposta do coletor: "OK\n" ou "ERRO: <motivo>\n".

Robustez (requisito 5.8):
  - timeout em conexao, envio e resposta
  - tratamento de conexao recusada / queda de rede
  - reconexao automatica com espera crescente (backoff)
  - logs em arquivo e no terminal

Configuracao por variaveis de ambiente:
  COLETOR_HOST (padrao: localhost)   COLETOR_PORT (padrao: 5000)
  TOKEN        (padrao: segredo123)  INTERVALO    (padrao: 5 segundos)
  HOST_ID      (padrao: nome da maquina)
  TIMEOUT      (padrao: 5 segundos)
"""
import json
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime

import psutil

COLETOR_HOST = os.environ.get("COLETOR_HOST", "localhost")
COLETOR_PORT = int(os.environ.get("COLETOR_PORT", "5000"))
TOKEN = os.environ.get("TOKEN", "segredo123")
INTERVALO = float(os.environ.get("INTERVALO", "5"))
TIMEOUT = float(os.environ.get("TIMEOUT", "5"))
HOST_ID = os.environ.get("HOST_ID", socket.gethostname())

ESPERA_MIN = 2    # primeira espera para reconectar (s)
ESPERA_MAX = 30   # limite da espera (s)

rodando = True
log = logging.getLogger("agente")


def configurar_log() -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler("agente.log"))
    except OSError:
        pass  # sem permissao de escrita: segue so com o terminal
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def encerrar(signum, frame) -> None:
    """Trata Ctrl+C e 'docker stop' para sair de forma limpa."""
    global rodando
    log.info("Sinal %s recebido, encerrando...", signum)
    rodando = False


def coletar() -> dict:
    """Le as metricas do sistema com psutil."""
    rede = psutil.net_io_counters()
    return {
        "token": TOKEN,
        "host": HOST_ID,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cpu": psutil.cpu_percent(interval=1),
        "mem": psutil.virtual_memory().percent,
        "disco": psutil.disk_usage("/").percent,
        "rede_enviado": rede.bytes_sent,
        "rede_recebido": rede.bytes_recv,
    }


def conectar() -> socket.socket:
    s = socket.create_connection((COLETOR_HOST, COLETOR_PORT), timeout=TIMEOUT)
    s.settimeout(TIMEOUT)  # vale para send e recv
    return s


def ler_resposta(s: socket.socket) -> str:
    """Le ate '\n' (resposta do coletor)."""
    dados = b""
    while not dados.endswith(b"\n"):
        parte = s.recv(1024)
        if not parte:
            raise ConnectionError("coletor fechou a conexao")
        dados += parte
        if len(dados) > 4096:
            break
    return dados.decode("utf-8", errors="replace").strip()


def enviar(s: socket.socket, metricas: dict) -> str:
    s.sendall((json.dumps(metricas) + "\n").encode("utf-8"))
    return ler_resposta(s)


def main() -> None:
    configurar_log()
    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    log.info("Agente '%s' iniciado. Destino: %s:%s, intervalo: %ss",
             HOST_ID, COLETOR_HOST, COLETOR_PORT, INTERVALO)

    sock = None
    espera = ESPERA_MIN

    while rodando:
        # 1) garante conexao
        if sock is None:
            try:
                sock = conectar()
                log.info("Conectado ao coletor %s:%s", COLETOR_HOST, COLETOR_PORT)
                espera = ESPERA_MIN
            except ConnectionRefusedError:
                log.error("Conexao recusada (coletor fora do ar?). Nova tentativa em %ss", espera)
            except socket.timeout:
                log.error("Timeout ao conectar. Nova tentativa em %ss", espera)
            except socket.gaierror:
                log.error("Nome '%s' nao resolvido (DNS). Nova tentativa em %ss", COLETOR_HOST, espera)
            except OSError as e:
                log.error("Erro de rede ao conectar: %s. Nova tentativa em %ss", e, espera)

            if sock is None:
                # espera em passos de 1s para reagir rapido ao Ctrl+C
                for _ in range(int(espera)):
                    if not rodando:
                        break
                    time.sleep(1)
                espera = min(espera * 2, ESPERA_MAX)
                continue

        # 2) coleta e envia
        try:
            metricas = coletar()
            resposta = enviar(sock, metricas)
            if resposta.startswith("OK"):
                log.info("Enviado: cpu=%s%% mem=%s%% disco=%s%% -> %s",
                         metricas["cpu"], metricas["mem"], metricas["disco"], resposta)
            else:
                log.warning("Coletor rejeitou a mensagem: %s", resposta)
        except socket.timeout:
            log.error("Timeout esperando resposta do coletor. Reconectando...")
            sock.close()
            sock = None
            continue
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            log.error("Conexao perdida: %s. Reconectando...", e)
            sock.close()
            sock = None
            continue
        except OSError as e:
            log.error("Erro de socket: %s. Reconectando...", e)
            sock.close()
            sock = None
            continue

        # 3) aguarda o proximo ciclo (a coleta de CPU ja gastou 1s)
        restante = max(INTERVALO - 1, 0)
        fim = time.time() + restante
        while rodando and time.time() < fim:
            time.sleep(0.2)

    if sock is not None:
        sock.close()
    log.info("Agente finalizado.")


if __name__ == "__main__":
    main()
