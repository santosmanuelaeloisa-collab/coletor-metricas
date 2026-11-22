#!/usr/bin/env python3
"""
coletor_falso.py - Coletor simulado para testar o agente (Pessoa 1).

Faz o papel do servidor da Pessoa 2:
  - escuta TCP (porta 5000 por padrao)
  - atende varios agentes ao mesmo tempo (uma thread por conexao)
  - valida o token enviado dentro do JSON
  - responde "OK\n" ou "ERRO: <motivo>\n"
  - imprime e registra tudo no log

Uso:
  python coletor_falso.py                      # porta 5000, token "segredo123"
  python coletor_falso.py --token meutoken --porta 5000
"""
import argparse
import json
import logging
import socket
import threading

CAMPOS_OBRIGATORIOS = ("token",)


def tratar_cliente(conn: socket.socket, addr, token_esperado: str) -> None:
    """Le mensagens JSON de um cliente ate ele fechar a conexao."""
    log = logging.getLogger("coletor")
    log.info("Conexao aberta de %s:%s", *addr)
    conn.settimeout(60)  # evita thread presa para sempre
    decoder = json.JSONDecoder()
    buffer = ""
    try:
        while True:
            dados = conn.recv(4096)
            if not dados:
                break  # cliente fechou
            buffer += dados.decode("utf-8", errors="replace")

            # Extrai todos os JSONs completos do buffer
            # (funciona com ou sem '\n' entre as mensagens)
            while True:
                buffer = buffer.lstrip()
                if not buffer:
                    break
                try:
                    msg, fim = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if len(buffer) > 65536:
                        conn.sendall(b"ERRO: mensagem invalida\n")
                        log.warning("Buffer grande demais de %s, descartando", addr[0])
                        buffer = ""
                    break  # mensagem incompleta, espera mais bytes
                buffer = buffer[fim:]
                resposta = validar(msg, token_esperado, addr)
                conn.sendall(resposta.encode())
    except socket.timeout:
        log.warning("Timeout de %s:%s, fechando", *addr)
    except (ConnectionResetError, BrokenPipeError):
        log.warning("Conexao com %s:%s caiu", *addr)
    except OSError as e:
        log.error("Erro de socket com %s:%s: %s", addr[0], addr[1], e)
    finally:
        conn.close()
        log.info("Conexao encerrada de %s:%s", *addr)


def validar(msg, token_esperado: str, addr) -> str:
    log = logging.getLogger("coletor")
    if not isinstance(msg, dict):
        log.warning("Mensagem nao e objeto JSON de %s", addr[0])
        return "ERRO: formato invalido\n"
    if msg.get("token") != token_esperado:
        log.warning("TOKEN INVALIDO de %s", addr[0])
        return "ERRO: token invalido\n"
    # Mostra a mensagem sem o token
    visivel = {k: v for k, v in msg.items() if k != "token"}
    log.info("Metrica recebida de %s: %s", addr[0], json.dumps(visivel, ensure_ascii=False))
    return "OK\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Coletor falso para testes do agente")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--porta", type=int, default=5000)
    ap.add_argument("--token", default="segredo123")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("coletor_falso.log")],
    )
    log = logging.getLogger("coletor")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.porta))
    srv.listen(20)
    log.info("Coletor falso escutando em %s:%s (token: %s)", args.host, args.porta, args.token)

    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(
                target=tratar_cliente, args=(conn, addr, args.token), daemon=True
            ).start()
    except KeyboardInterrupt:
        log.info("Encerrando coletor")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
