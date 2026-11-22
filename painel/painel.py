"""Painel: web Flask que le /dados/dados.db SOMENTE LEITURA e mostra graficos e hosts."""
import os, sqlite3, time, logging
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, g, jsonify, render_template_string, request, abort

DB = os.getenv("DB", "/dados/dados.db")
PORTA = int(os.getenv("PORTA", "8080"))
ONLINE_S = 30  # host sem enviar ha mais que isso = offline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("painel")
app = Flask(__name__)


def consultar(sql, args=()):
    """Abre o banco com mode=ro (nunca escreve). Banco ausente/vazio -> lista vazia."""
    uri = Path(DB).resolve().as_uri() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()
    except sqlite3.Error as e:   # arquivo ainda nao existe, tabela ausente, banco bloqueado
        log.warning("consulta falhou: %s", e)
        return []


def segundos_desde(momento):
    t = datetime.strptime(momento, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds()


@app.before_request
def inicio():
    g.t0 = time.perf_counter()


@app.after_request
def fim(resp):  # tempo de resposta no cabecalho: serve de evidencia nos testes
    ms = (time.perf_counter() - g.t0) * 1000
    resp.headers["X-Tempo-ms"] = f"{ms:.1f}"
    log.info("%s %s %s %.1f ms", request.method, request.path, resp.status_code, ms)
    return resp


def hosts():
    base = consultar("SELECT origem, COUNT(*) total, ROUND(AVG(cpu),1) cpu_media, "
                     "ROUND(AVG(memoria),1) mem_media, MAX(momento) ultimo "
                     "FROM metricas GROUP BY origem ORDER BY origem")
    ult = {r["origem"]: r for r in consultar(
        "SELECT m.origem, m.cpu, m.memoria FROM metricas m JOIN "
        "(SELECT origem, MAX(rowid) r FROM metricas GROUP BY origem) x ON m.rowid = x.r")}
    for h in base:
        h["cpu"], h["memoria"] = ult[h["origem"]]["cpu"], ult[h["origem"]]["memoria"]
        h["online"] = segundos_desde(h["ultimo"]) <= ONLINE_S
    return base


@app.route("/api/series")
def series():
    host = request.args.get("host")
    try:
        limite = max(1, min(int(request.args.get("limite", 60)), 1000))
    except ValueError:
        abort(400)
    if host:
        rows = consultar("SELECT origem, cpu, memoria, momento FROM metricas WHERE origem=? "
                         "ORDER BY momento DESC LIMIT ?", (host, limite))[::-1]
    else:
        rows = consultar("SELECT origem, cpu, memoria, momento FROM (SELECT *, row_number() "
                         "OVER (PARTITION BY origem ORDER BY momento DESC) rn FROM metricas) "
                         "WHERE rn <= ? ORDER BY momento", (limite,))
    out = {}
    for r in rows:
        ms = int(datetime.strptime(r["momento"], "%Y-%m-%d %H:%M:%S")
                 .replace(tzinfo=timezone.utc).timestamp() * 1000)
        out.setdefault(r["origem"], []).append({"x": ms, "cpu": r["cpu"], "mem": r["memoria"]})
    return jsonify(out)


@app.route("/api/hosts")
def api_hosts():
    return jsonify(hosts())


@app.route("/saude")
def saude():
    return {"status": "ok"}


CSS = """<style>
body{font-family:system-ui,sans-serif;margin:0;background:#f4f5f7;color:#222}
nav{background:#1f2a44;padding:12px 24px}nav a{color:#fff;margin-right:20px;text-decoration:none}
main{padding:24px;max-width:1000px;margin:auto}
.cards{display:flex;gap:16px;margin-bottom:20px}.card{background:#fff;border-radius:8px;padding:16px;flex:1;box-shadow:0 1px 3px #0002}
.card b{font-size:26px;display:block}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px}
th,td{padding:10px;text-align:left;border-bottom:1px solid #eee}
.on{color:#0a7d2c;font-weight:600}.off{color:#c0392b;font-weight:600}
canvas{background:#fff;border-radius:8px;padding:12px}
</style>"""
NAV = '<nav><a href="/">Painel</a><a href="/hosts">Hosts</a></nav>'

PAG_INICIO = CSS + NAV + """<main><h2>Visao geral</h2>
<div class="cards">
<div class="card">Hosts<b>{{ hs|length }}</b></div>
<div class="card">Registros<b>{{ hs|sum(attribute='total') }}</b></div>
<div class="card">Online agora<b>{{ hs|selectattr('online')|list|length }}</b></div></div>
{% if not hs %}<p>Ainda sem dados. Aguardando o coletor...</p>{% endif %}
<h3>CPU (%)</h3><canvas id="c1"></canvas><h3>Memoria (%)</h3><canvas id="c2"></canvas></main>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>""" + """
const HOST = {{ host|tojson }};
function opts(){return {animation:false,parsing:false,scales:{x:{type:'linear',ticks:{callback:v=>new Date(v).toLocaleTimeString()}},y:{min:0,max:100}}}}
const g1=new Chart(c1,{type:'line',data:{datasets:[]},options:opts()});
const g2=new Chart(c2,{type:'line',data:{datasets:[]},options:opts()});
async function atualizar(){
  const r=await fetch('/api/series'+(HOST?'?host='+encodeURIComponent(HOST)+'&limite=200':''));
  const d=await r.json();
  const mk=k=>Object.entries(d).map(([h,p])=>({label:h,data:p.map(q=>({x:q.x,y:q[k]})),pointRadius:0,borderWidth:2,tension:.2}));
  g1.data.datasets=mk('cpu');g1.update();g2.data.datasets=mk('mem');g2.update();
}
atualizar();setInterval(atualizar,5000);
</script>"""

PAG_HOSTS = CSS + NAV + """<meta http-equiv="refresh" content="5"><main><h2>Hosts</h2>
<table><tr><th>Host</th><th>Status</th><th>CPU atual</th><th>Mem atual</th><th>CPU media</th><th>Mem media</th><th>Registros</th><th>Ultimo envio (UTC)</th></tr>
{% for h in hs %}<tr><td><a href="/host/{{ h.origem }}">{{ h.origem }}</a></td>
<td class="{{ 'on' if h.online else 'off' }}">{{ 'online' if h.online else 'offline' }}</td>
<td>{{ h.cpu }}%</td><td>{{ h.memoria }}%</td><td>{{ h.cpu_media }}%</td><td>{{ h.mem_media }}%</td>
<td>{{ h.total }}</td><td>{{ h.ultimo }}</td></tr>
{% else %}<tr><td colspan="8">Nenhum host registrado ainda.</td></tr>{% endfor %}</table></main>"""


@app.route("/")
def inicio_pag():
    return render_template_string(PAG_INICIO, hs=hosts(), host=None)


@app.route("/hosts")
def hosts_pag():
    return render_template_string(PAG_HOSTS, hs=hosts())


@app.route("/host/<path:ip>")
def host_pag(ip):
    hs = [h for h in hosts() if h["origem"] == ip]
    if not hs:
        abort(404)
    return render_template_string(PAG_INICIO, hs=hs, host=ip)


if __name__ == "__main__":
    log.info("painel em http://0.0.0.0:%s lendo %s (somente leitura)", PORTA, DB)
    app.run(host="0.0.0.0", port=PORTA, threaded=True)
