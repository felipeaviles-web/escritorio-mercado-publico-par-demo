"""Demostración local del flujo de estudio del Escritorio PAR."""
import argparse
import json
import re
import secrets
import unicodedata
import webbrowser
from datetime import date, datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from archivos_par import store_upload, verify_expediente
from multipart_local import read_uploads

API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
PORTAL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion="
CODE = re.compile(r"[0-9]+-[0-9]+-[A-Z0-9]{2,12}")
SAMPLE = {
    "CodigoExterno": "DEMO-PAR-01",
    "Nombre": "Mejoramiento de veredas del Barrio Estación",
    "Estado": "Publicada (ejemplo)",
    "Comprador": {"NombreOrganismo": "Municipalidad de Ejemplo"},
    "Fechas": {"FechaCierre": "2026-12-18T15:00:00"},
    "MontoEstimado": 84_000_000,
    "Moneda": "CLP",
}
SAMPLES = (
    SAMPLE,
    {**SAMPLE, "CodigoExterno": "DEMO-PAR-02", "Nombre": "Mejoramiento de la Plaza Los Aromos",
     "Fechas": {"FechaCierre": "2026-12-22T14:00:00"}, "MontoEstimado": 61_000_000},
    {**SAMPLE, "CodigoExterno": "DEMO-PAR-03", "Nombre": "Reposición de luminarias en Plaza del Río",
     "Fechas": {"FechaCierre": "2027-01-08T16:00:00"}, "MontoEstimado": 39_000_000},
)
DOCUMENTS = {
    "bases-ficticias.txt": (
        "EJEMPLO FICTICIO — DEMO-PAR-01\n"
        "Obra: reposición de veredas y rebajes accesibles.\n"
        "Categoría simulada: B2 cuarta. Anticipo simulado: 15 %.\n"
        "Verificar en estudio si el espesor del pavimento coincide con los planos.\n"
    ),
    "partidas-ficticias.csv": (
        "Partida;Unidad;Cantidad\nDemolición de vereda;m2;580\n"
        "Pavimento de hormigón;m2;580\nRebaje accesible;un;8\n"
    ),
}
STYLE = """
:root{font:16px/1.5 system-ui;color:#19323d;background:#f1f5f4}
*{box-sizing:border-box}body{margin:0}main{max-width:790px;padding:36px 20px;margin:auto}
h1{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.1;margin:8px 0 18px}
h2{font-size:1.16rem;margin:0 0 12px}p{margin:0 0 14px}
nav,section{margin:20px 0}nav{display:flex;flex-wrap:wrap;gap:10px 24px;color:#42585e}
nav strong{color:#075b56}section{background:white;border:1px solid #cddbd8;
border-radius:12px;padding:22px}label{display:block;font-weight:650;margin:10px 0 4px}
input:not([type=file]),textarea{font:inherit;color:inherit;width:100%;padding:8px;
border:1px solid #859892;border-radius:5px}textarea{min-height:90px}
button,.button{font:inherit;font-weight:650;display:inline-block;background:#075b56;
color:white;border:0;border-radius:6px;padding:9px 15px;margin:8px 0;text-decoration:none;
cursor:pointer}a{color:#075b56}dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px}
dd{margin:0;overflow-wrap:anywhere}.notice{padding:10px 13px;background:#fcecd6}
.muted{color:#42585e}li{overflow-wrap:anywhere}
.match{border-top:1px solid #cddbd8;padding:12px 0}.match p{margin:4px 0 0}
.match button{margin-bottom:0}.alternatives{margin-top:20px}
"""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def query_api(ticket, **params):
    if not 1 <= len(ticket) <= 128:
        raise ValueError("Ingresa tu ticket personal de Mercado Público.")
    url = API + "?" + urlencode(dict(params, ticket=ticket))
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with build_opener(NoRedirects()).open(request, timeout=25) as response:
            payload = json.load(response)
    except (URLError, OSError, ValueError):
        raise ValueError("No se pudo consultar Mercado Público. Revisa tu ticket y tu conexión.") from None
    rows = payload.get("Listado") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Mercado Público no devolvió un listado válido. Revisa tu ticket.")
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("Nombre"), str)
            and CODE.fullmatch(str(row.get("CodigoExterno", "")))]


def normalized(text):
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def closes_at(row):
    dates = row.get("Fechas")
    raw = (dates.get("FechaCierre") if isinstance(dates, dict) else None) or row.get("FechaCierre")
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def matching(rows, criteria):
    def patterns(field):
        terms = [normalized(term.strip()) for term in criteria[field].split(",") if term.strip()]
        return [re.compile(r"(?<!\w)" + re.escape(term)) for term in terms]

    include, exclude = patterns("incluir"), patterns("excluir")
    deadline = date.fromisoformat(criteria["hasta"]) if criteria["hasta"] else None
    result = []
    for row in rows:
        title = normalized(row["Nombre"])
        if include and not any(pattern.search(title) for pattern in include):
            continue
        if any(pattern.search(title) for pattern in exclude):
            continue
        closing = closes_at(row)
        if deadline and (closing is None or closing.date() > deadline):
            continue
        result.append(row)
    return result


def sample_documents(row):
    if row["CodigoExterno"] == SAMPLE["CodigoExterno"]:
        return DOCUMENTS
    work = {
        "DEMO-PAR-02": "Retiro de pavimento;m2;220\nInstalación de juego inclusivo;un;1\n",
        "DEMO-PAR-03": "Retiro de luminaria;un;12\nLuminaria LED instalada;un;12\n",
    }
    return {
        "bases-ficticias.txt": (f'EJEMPLO FICTICIO — {row["CodigoExterno"]}\n'
                                f'Obra: {row["Nombre"]}.\n'
                                'Verificar las cantidades y condiciones de ejecución.\n'),
        "partidas-ficticias.csv": "Partida;Unidad;Cantidad\n" + work[row["CodigoExterno"]],
    }


def facts(row):
    buyer = row.get("Comprador")
    buyer_name = buyer.get("NombreOrganismo") if isinstance(buyer, dict) else ""
    closing = closes_at(row)
    amount = row.get("MontoEstimado")
    budget = "No informado"
    try:
        if amount is not None and Decimal(str(amount)).is_finite():
            budget = f'{Decimal(str(amount)):,.0f}'.replace(",", ".") + " " + str(row.get("Moneda") or "CLP")
    except ArithmeticError:
        pass
    return {
        "Código": row["CodigoExterno"],
        "Organismo": buyer_name or "No informado",
        "Estado": row.get("Estado") or "No informado",
        "Cierre": closing.strftime("%d/%m/%Y %H:%M") if closing else "No informado",
        "Monto estimado": budget,
    }


def pdf_bytes(case, report):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output = BytesIO()
    styles = getSampleStyleSheet()
    styles["Heading1"].textColor = HexColor("#075b56")
    story = []

    def add(value, style="BodyText"):
        story.append(Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style]))

    add("Ficha preliminar de licitación", "Heading1")
    source = "Datos ficticios" if case["sample"] else "Fuente: API oficial de Mercado Público"
    if case.get("summary"):
        source += " (datos básicos del listado de activas)"
    add(source)
    add(f"Generada: {datetime.now():%d/%m/%Y %H:%M}")
    add(case["row"]["Nombre"], "Heading2")
    for name, value in facts(case["row"]).items():
        add(f"{name}: {value}")
    add("Antecedentes incorporados", "Heading2")
    for file in report["manifiesto"]:
        add(file["archivo"])
    add("Revisión preliminar", "Heading2")
    add(case["notes"])
    story.append(Spacer(1, 10))
    add("La comprobación local cubre los archivos incorporados. "
        "Completitud del expediente y decisión de ofertar: pendientes de validación.")
    SimpleDocTemplate(output, title="Ficha preliminar de licitación").build(story)
    return output.getvalue()


class DemoHandler(BaseHTTPRequestHandler):
    timeout = 15

    def log_message(self, *args):
        # El ticket viaja solo en el cuerpo del formulario y hacia la API oficial.
        pass

    def send_content(self, content, content_type, status=200, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        return self.headers.get("Host") == self.server.host

    def do_GET(self):
        if not self.valid_host():
            self.send_error(403)
        else:
            with self.server.lock:
                if self.path == "/":
                    self.page()
                elif self.path == "/ficha.pdf" and self.server.case and self.server.case["pdf"]:
                    self.send_content(self.server.case["pdf"], "application/pdf", filename="ficha-par.pdf")
                else:
                    self.send_error(404)

    def do_POST(self):
        if (not self.valid_host() or self.headers.get("Origin", self.server.url) != self.server.url
                or not self.path.startswith(f"/{self.server.token}/")):
            self.send_error(403)
            return
        with self.server.lock:
            try:
                self.perform(self.path.rsplit("/", 1)[-1])
            except (ValueError, RuntimeError) as exc:
                self.page(str(exc), 400)
                return
            except OSError:
                self.page("No se pudo acceder a los archivos temporales de la demo.", 500)
                return
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def fields(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 32_768:
            raise ValueError("El formulario supera el tamaño permitido.")
        return parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)

    def new_case(self, row, sample=False, summary=False):
        folder = self.server.root / secrets.token_hex(12)
        folder.mkdir()
        self.server.case = {"row": row, "sample": sample, "summary": summary,
                            "folder": folder, "notes": "", "pdf": b""}

    def search(self, fields):
        criteria = {key: fields.get(key, [""])[0].strip() for key in ("incluir", "excluir", "hasta")}
        if any(len(criteria[key]) > 200 for key in ("incluir", "excluir")):
            raise ValueError("Usa hasta 200 caracteres por campo de palabras.")
        if criteria["hasta"]:
            try:
                date.fromisoformat(criteria["hasta"])
            except ValueError:
                raise ValueError("Ingresa una fecha de cierre válida.") from None
        mode = fields.get("modo", [""])[0]
        if mode not in ("ejemplos", "activas"):
            raise ValueError("Elige ejemplos o licitaciones activas.")
        if mode == "activas":
            ticket = fields.get("ticket", [""])[0].strip()
            if ticket or self.server.live_rows is None:
                self.server.live_rows = query_api(ticket, estado="activas")
            rows = self.server.live_rows
        else:
            rows = SAMPLES
        self.server.criteria = criteria
        self.server.search_mode = mode
        self.server.results = matching(rows, criteria)

    def perform(self, action):
        if action == "inicio":
            self.server.case = None
            return
        if action == "ejemplo":
            self.new_case(SAMPLE, sample=True)
            return
        if action == "buscar":
            self.search(self.fields())
            return
        if action == "resultado":
            code = self.fields().get("codigo", [""])[0]
            row = next((row for row in self.server.results if row["CodigoExterno"] == code), None)
            if row is None:
                raise ValueError("Elige una licitación del listado de resultados.")
            sample = self.server.search_mode == "ejemplos"
            self.new_case(row, sample=sample, summary=not sample)
            return
        if action == "consulta":
            fields = self.fields()
            code = fields.get("codigo", [""])[0].strip().upper()
            ticket = fields.get("ticket", [""])[0].strip()
            if not CODE.fullmatch(code):
                raise ValueError("Ingresa un código de licitación válido.")
            rows = query_api(ticket, codigo=code)
            row = next((row for row in rows if isinstance(row, dict)
                        and row.get("CodigoExterno") == code and isinstance(row.get("Nombre"), str)
                        and row["Nombre"].strip()), None)
            if row is None:
                raise ValueError("La API no devolvió una ficha para ese código.")
            self.new_case(row)
            return

        case = self.server.case
        if not case:
            raise ValueError("Abre primero una licitación.")
        folder = case["folder"]
        if action == "antecedentes" and case["sample"]:
            for name, content in sample_documents(case["row"]).items():
                store_upload(BytesIO(content.encode("utf-8")), name, folder)
            case["pdf"] = b""
        elif action == "archivos" and not case["sample"]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 25 * 1024 * 1024:
                raise ValueError("El total de archivos por carga debe ser inferior a 25 MB.")
            uploads = read_uploads(self.rfile, self.headers.get("Content-Type"), length, folder)
            if not uploads:
                raise ValueError("Selecciona al menos un archivo.")
            case["pdf"] = b""
            try:
                for name, path in uploads:
                    with path.open("rb") as source:
                        store_upload(source, name, folder)
            finally:
                for _, path in uploads:
                    path.unlink(missing_ok=True)
        elif action == "generar":
            notes = self.fields().get("notas", [""])[0].strip()
            report = verify_expediente(folder)
            if not report["comprobacion_local_ok"] or not 1 <= len(notes) <= 1200:
                raise ValueError("Incorpora antecedentes válidos y escribe una nota de hasta 1.200 caracteres.")
            case["notes"] = notes
            case["pdf"] = pdf_bytes(case, report)
        else:
            raise ValueError("Esta acción no está disponible para la licitación actual.")

    def form(self, action, body, extra=""):
        return f'<form method="post" action="/{self.server.token}/{action}" {extra}>{body}</form>'

    def search_page(self):
        criteria = self.server.criteria
        fields = (
            '<label for="incluir">Incluir alguna palabra o frase</label>'
            f'<input id="incluir" name="incluir" maxlength="200" value="{escape(criteria["incluir"])}" '
            'placeholder="veredas, plaza">'
            '<label for="excluir">Excluir palabras o frases</label>'
            f'<input id="excluir" name="excluir" maxlength="200" value="{escape(criteria["excluir"])}" '
            'placeholder="luminarias">'
            '<p class="muted">Separa los términos con comas. La búsqueda coincide desde el inicio de una palabra del título.</p>'
            '<label for="hasta">Fecha límite de cierre (opcional)</label>'
            f'<input id="hasta" name="hasta" type="date" value="{escape(criteria["hasta"])}">'
            '<button name="modo" value="ejemplos">Buscar en ejemplos</button>'
            '<details class="alternatives"><summary>Buscar licitaciones activas con mi ticket</summary>'
            '<label for="ticket-busqueda">Ticket personal de Mercado Público</label>'
            '<input id="ticket-busqueda" name="ticket" type="password" autocomplete="off" maxlength="128">'
            '<p class="muted">Después de la primera consulta puedes volver a filtrar el listado durante esta sesión.</p>'
            '<button name="modo" value="activas">Buscar licitaciones activas</button></details>'
        )
        body = '<section><h2>Define tus criterios de búsqueda</h2>' + self.form("buscar", fields) + "</section>"
        if self.server.search_mode:
            results = self.server.results
            source = "Ejemplos" if self.server.search_mode == "ejemplos" else "Licitaciones activas de Mercado Público"
            body += f'<section><h2>{source}</h2><p role="status">Coincidencias: {len(results)}.</p>'
            if len(results) > 50:
                body += '<p>Se muestran las primeras 50. Acota tus criterios para ver otras coincidencias.</p>'
            for row in results[:50]:
                code = escape(row["CodigoExterno"])
                name = escape(row["Nombre"])
                closing = facts(row)["Cierre"]
                body += f'<article class="match"><strong>{name}</strong><p>{code} · Cierre: {closing}</p>'
                body += self.form("resultado", f'<button name="codigo" value="{code}" '
                                  f'aria-label="Abrir {name}">Abrir licitación</button>') + "</article>"
            body += "</section>"
        body += '<section><details><summary>Otras formas de abrir una licitación</summary>'
        body += self.form("ejemplo", "<button>Abrir ejemplo de veredas</button>")
        body += self.form("consulta", '<label for="codigo">Consultar por código</label>'
                          '<input id="codigo" name="codigo" required maxlength="32" placeholder="1234-56-LQ26">'
                          '<label for="ticket">Ticket personal de Mercado Público</label>'
                          '<input id="ticket" name="ticket" type="password" autocomplete="off" required maxlength="128">'
                          '<button>Consultar licitación</button>') + "</details></section>"
        return body

    def page(self, error="", status=200):
        case = self.server.case
        report = verify_expediente(case["folder"]) if case else None
        active = 3 if report and report["comprobacion_local_ok"] else 2 if case else 1
        steps = ["Abrir licitación", "Incorporar antecedentes", "Generar ficha"]
        progress = "".join(f'<strong aria-current="step">{i}. {step}</strong>' if i == active
                           else f'<span>{i}. {step}</span>' for i, step in enumerate(steps, 1))
        body = f'<h1>Escritorio Mercado Público PAR</h1><nav aria-label="Flujo">{progress}</nav>'
        if error:
            body += f'<p class="notice" role="alert">{escape(error)}</p>'
        if not case:
            body += self.search_page()
        else:
            row = case["row"]
            label = "Datos ficticios" if case["sample"] else "API oficial de Mercado Público"
            details = "".join(f"<dt>{name}</dt><dd>{escape(str(value))}</dd>"
                              for name, value in facts(row).items())
            body += f'<section><p class="muted">{label}</p><h2>{escape(row["Nombre"])}</h2><dl>{details}</dl>'
            if not case["sample"]:
                if case["summary"]:
                    body += '<p>Datos básicos del listado. Para obtener el detalle de la API, consulta por código.</p>'
                body += (f'<a href="{PORTAL}{quote(row["CodigoExterno"])}" target="_blank" rel="noreferrer">'
                         'Ver licitación oficial</a>')
            body += "</section><section><h2>Antecedentes</h2>"
            if case["sample"] and not report["archivos"]:
                body += self.form("antecedentes", "<button>Incorporar bases e itemizado ficticios</button>")
            if not case["sample"]:
                body += '<p>Descarga los antecedentes desde el portal y agrégalos aquí para revisarlos.</p>'
                body += self.form("archivos", '<label for="archivos">Archivos del expediente</label>'
                                  '<input id="archivos" name="archivos" type="file" required multiple> '
                                  '<button>Incorporar archivos</button>', 'enctype="multipart/form-data"')
            if report["archivos"]:
                body += "<ul>" + "".join(f'<li>{escape(file["archivo"])}</li>'
                                         for file in report["manifiesto"]) + "</ul>"
            for message in report["errores"]:
                body += f'<p class="notice">{escape(message)}</p>'
            body += "</section>"
            if report["comprobacion_local_ok"]:
                notes = case["notes"]
                if case["sample"] and not notes:
                    notes = ("Categoría de ejemplo: B2 cuarta. Anticipo de ejemplo: 15 %. "
                             "Pendiente para el estudio: cotejar el espesor del pavimento con los planos."
                             if row["CodigoExterno"] == SAMPLE["CodigoExterno"]
                             else "Pendiente para el estudio: verificar cantidades y condiciones de ejecución.")
                body += '<section><h2>Ficha preliminar</h2>'
                body += self.form("generar", '<label for="notas">Hallazgos y pendientes</label>'
                                  f'<textarea id="notas" name="notas" maxlength="1200" required>{escape(notes)}</textarea>'
                                  '<button>Generar ficha PDF</button>')
                if case["pdf"]:
                    body += ('<p role="status">Ficha generada.</p>'
                             '<a class="button" href="/ficha.pdf" download="ficha-par.pdf">Descargar ficha PDF</a>')
                body += "</section>"
            body += self.form("inicio", "<button>Volver a la búsqueda</button>")
        html = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>Demo del Escritorio PAR</title><style>{STYLE}</style></head><body>'
                f'<main><p class="muted">Demo local</p>{body}</main></body></html>')
        self.send_content(html.encode("utf-8"), "text/html; charset=utf-8", status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8767)
    parser.add_argument("--sin-navegador", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="escritorio-par-demo-") as directory:
        with ThreadingHTTPServer(("127.0.0.1", args.puerto), DemoHandler) as server:
            server.host = f"127.0.0.1:{server.server_port}"
            server.url = f"http://{server.host}"
            server.root = Path(directory)
            server.token = secrets.token_urlsafe(24)
            server.case = None
            server.criteria = {"incluir": "", "excluir": "", "hasta": ""}
            server.search_mode = None
            server.results = []
            server.live_rows = None
            server.lock = Lock()
            print(f"Demo local en {server.url}/. Para terminar, presiona Ctrl+C.", flush=True)
            if not args.sin_navegador:
                webbrowser.open(server.url + "/", new=2)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
