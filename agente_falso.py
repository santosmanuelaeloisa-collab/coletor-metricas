import socket, json, random, sys, time

HOST, PORTA = "127.0.0.1", 5000   # 127.0.0.1 = "este mesmo computador"
token = sys.argv[1] if len(sys.argv) > 1 else "TOKEN_123"   # crachá (dá para trocar nos testes)
modo = sys.argv[2] if len(sys.argv) > 2 else "normal"       # "invalido" manda lixo de propósito

with socket.create_connection((HOST, PORTA), timeout=10) as s:
    respostas = s.makefile("r")   # para ler o que o servidor responde
    while True:
        if modo == "invalido":
            linha = "isso nao e json"
        else:
            dados = {"cpu": round(random.uniform(10, 90), 1),
                     "memoria": round(random.uniform(20, 80), 1),
                     "token": token}
            linha = json.dumps(dados)
        s.sendall((linha + "\n").encode())      # o \n marca o fim da mensagem
        resposta = respostas.readline().strip()
        print("enviei:", linha, "| resposta:", resposta)
        if resposta.startswith("ERRO token"):   # servidor fechou a conexão
            break
        time.sleep(5)                           # espera 5 segundos
