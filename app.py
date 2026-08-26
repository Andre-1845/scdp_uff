import os
import json
import shutil
from datetime import datetime, date

from flask import (Flask, render_template, redirect, url_for, session,
                   request, flash, abort, send_file)
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

import docs_gen

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
EXTENSOES_PERMITIDAS = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "dados.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB por requisição

db = SQLAlchemy(app)

ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "id.uff.br")
DEV_LOGIN = os.getenv("DEV_LOGIN", "1") == "1"

# ---- carrega a "receita" dos formulários ----
def carregar_config():
    with open(os.path.join(BASE_DIR, "forms_config.json"), encoding="utf-8") as f:
        return json.load(f)


def data_br(iso):
    """Converte 'AAAA-MM-DD' para 'DD/MM/AAAA'. Usado nos templates."""
    if not iso:
        return ""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso


app.jinja_env.filters["data_br"] = data_br


def nome_exibicao_arquivo(valor):
    """O arquivo é salvo em disco como 'campo__nomeoriginal.ext'; aqui devolvemos
    só o nome original, para mostrar na tela."""
    if not valor:
        return ""
    return valor.split("__", 1)[-1] if "__" in valor else valor


app.jinja_env.filters["nome_arquivo"] = nome_exibicao_arquivo


def _extensao_permitida(nome_arquivo):
    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    return ext in EXTENSOES_PERMITIDAS


def _pasta_rascunho(docente_id, situacao):
    pasta = os.path.join(UPLOAD_DIR, f"rascunho_{docente_id}_{situacao}")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _pasta_solicitacao(sid):
    return os.path.join(UPLOAD_DIR, f"solicitacao_{sid}")

# ---- OAuth Google (só ativa se houver credenciais) ----
oauth = None
google = None
GOOGLE_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
if GOOGLE_ID and GOOGLE_SECRET:
    from authlib.integrations.flask_client import OAuth
    oauth = OAuth(app)
    google = oauth.register(
        name="google",
        client_id=GOOGLE_ID,
        client_secret=GOOGLE_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "hd": ALLOWED_DOMAIN},
    )


# ---------------- modelos ----------------
class Docente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    nome = db.Column(db.String(200))
    siape = db.Column(db.String(30))
    departamento = db.Column(db.String(120))
    cargo = db.Column(db.String(120))
    telefone = db.Column(db.String(40))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Solicitacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    situacao = db.Column(db.String(50), nullable=False)
    respostas_json = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    docente = db.relationship("Docente", backref="solicitacoes")

    @property
    def respostas(self):
        return json.loads(self.respostas_json)


# ---------------- helpers ----------------
def docente_logado():
    email = session.get("email")
    if not email:
        return None
    return Docente.query.filter_by(email=email).first()


@app.context_processor
def injetar_usuario():
    return {"usuario": docente_logado()}


def exige_login():
    if not session.get("email"):
        return redirect(url_for("login"))
    return None


# ---------------- autenticação ----------------
@app.route("/")
def index():
    if session.get("email"):
        return redirect(url_for("escolher"))
    return redirect(url_for("login"))


@app.route("/login")
def login():
    return render_template("login.html", dev_login=DEV_LOGIN,
                           oauth_ativo=google is not None, dominio=ALLOWED_DOMAIN)


@app.route("/auth/google")
def auth_google():
    if not google:
        flash("Login com Google não configurado. Use o acesso de teste.", "erro")
        return redirect(url_for("login"))
    redirect_uri = url_for("auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/callback")
def auth_callback():
    if not google:
        return redirect(url_for("login"))
    token = google.authorize_access_token()
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if not email.endswith("@" + ALLOWED_DOMAIN):
        flash("Acesso permitido apenas para contas @" + ALLOWED_DOMAIN + ".", "erro")
        return redirect(url_for("login"))
    _entrar(email, info.get("name"))
    return redirect(url_for("perfil"))


@app.route("/dev-login", methods=["POST"])
def dev_login():
    if not DEV_LOGIN:
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    if not email.endswith("@" + ALLOWED_DOMAIN):
        flash("Use um e-mail @" + ALLOWED_DOMAIN + " para o teste.", "erro")
        return redirect(url_for("login"))
    _entrar(email, request.form.get("nome") or email.split("@")[0])
    return redirect(url_for("perfil"))


def _entrar(email, nome):
    doc = Docente.query.filter_by(email=email).first()
    if not doc:
        doc = Docente(email=email, nome=nome)
        db.session.add(doc)
        db.session.commit()
    session["email"] = email


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- perfil ----------------
@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    if request.method == "POST":
        doc.nome = request.form.get("nome", doc.nome)
        doc.siape = request.form.get("siape")
        doc.departamento = request.form.get("departamento")
        doc.cargo = request.form.get("cargo")
        doc.telefone = request.form.get("telefone")
        db.session.commit()
        flash("Dados salvos.", "ok")
        return redirect(url_for("escolher"))
    return render_template("perfil.html", doc=doc)


# ---------------- escolha da situação ----------------
@app.route("/escolher")
def escolher():
    r = exige_login()
    if r:
        return r
    cfg = carregar_config()["situacoes"]
    situacoes = sorted(cfg.items(), key=lambda kv: kv[1].get("ordem", 99))
    return render_template("escolher.html", situacoes=situacoes)


# ---------------- assistente de enquadramento (Anexo VII) ----------------
@app.route("/enquadrar", methods=["GET", "POST"])
def enquadrar():
    r = exige_login()
    if r:
        return r
    if request.method == "POST":
        abrangencia = request.form.get("abrangencia")
        atividade = request.form.get("atividade")
        periodo = request.form.get("periodo")
        categoria = request.form.get("categoria")
        situacao, explicacao, abre_sei = _enquadrar(abrangencia, atividade, periodo, categoria)
        cfg = carregar_config()["situacoes"]
        return render_template("enquadrar.html", resultado=True,
                               situacao=situacao, titulo=cfg[situacao]["titulo"],
                               explicacao=explicacao, abre_sei=abre_sei)
    return render_template("enquadrar.html", resultado=False)


def _enquadrar(abrangencia, atividade, periodo, categoria):
    # lógica derivada da tabela do Anexo VII da IN 058/2023
    if abrangencia == "exterior":
        return ("internacional",
                "Viagem ao exterior. Abre processo no SEI, exige seguro viagem e passa pela DACQ da PROGEPE, com publicação no DOU.",
                True)
    # nacional
    desenvolvimento = atividade in ("treinamento", "congresso", "capacitacao")
    if desenvolvimento:
        if periodo == "mais15":
            return ("nacional_longo",
                    "Ação de desenvolvimento acima de 15 dias. Abre processo no SEI e vai à DACQ da PROGEPE.",
                    True)
        if categoria == "tecnico":
            return ("nacional_longo",
                    "Técnico-administrativo em ação de desenvolvimento abre processo no SEI mesmo até 15 dias, conforme a Instrução de Serviço PROGEPE 001/2020.",
                    True)
        return ("nacional_curto",
                "Docente em ação de desenvolvimento de 1 a 15 dias não abre processo no SEI, apenas o Anexo II para cadastro da PCDP.",
                False)
    # viagem a serviço, banca de concurso ou trabalho de campo, nacional
    return ("nacional_curto",
            "Viagem a serviço, banca de concurso ou trabalho de campo no país não abre processo no SEI, apenas o Anexo II para cadastro da PCDP pela unidade. Se durar mais de 15 dias, o fluxo é o mesmo, mas confirme o prazo com a Secretaria.",
            False)


# ---------------- wizard de formulários ----------------
@app.route("/solicitar/<situacao>/<int:passo>", methods=["GET", "POST"])
def solicitar(situacao, passo):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    cfg = carregar_config()["situacoes"]
    if situacao not in cfg:
        abort(404)
    forms = cfg[situacao]["formularios"]
    total = len(forms)
    if passo < 1 or passo > total:
        abort(404)
    formulario = forms[passo - 1]

    # respostas parciais ficam na sessão, por situação
    chave = "rascunho_" + situacao
    rascunho = session.get(chave, {})

    if request.method == "POST":
        erros = _validar(formulario, request.form, situacao)

        # valida extensão dos arquivos antes de gravar qualquer coisa em disco
        for c in formulario["campos"]:
            if c["tipo"] == "file":
                arq = request.files.get(c["nome"])
                if arq and arq.filename and not _extensao_permitida(arq.filename):
                    erros.append(
                        f"Arquivo inválido em \"{c['label']}\". "
                        f"Tipos aceitos: {', '.join(sorted(EXTENSOES_PERMITIDAS))}."
                    )

        if erros:
            for e in erros:
                flash(e, "erro")
            dados_atuais = {}
            for c in formulario["campos"]:
                if c["tipo"] == "checkbox":
                    dados_atuais[c["nome"]] = "Sim" if request.form.get(c["nome"]) else "Não"
                elif c["tipo"] == "file":
                    # mantém o nome do arquivo já salvo antes, se houver (o campo
                    # de arquivo do navegador não pode ser "pré-preenchido")
                    dados_atuais[c["nome"]] = rascunho.get(c["nome"], "")
                else:
                    dados_atuais[c["nome"]] = request.form.get(c["nome"], "")
            return render_template("formulario.html", situacao=situacao,
                                   titulo_situacao=cfg[situacao]["titulo"],
                                   formulario=formulario, passo=passo, total=total,
                                   valores=dados_atuais)

        for c in formulario["campos"]:
            if c["tipo"] == "checkbox":
                rascunho[c["nome"]] = "Sim" if request.form.get(c["nome"]) else "Não"
            elif c["tipo"] == "file":
                arq = request.files.get(c["nome"])
                if arq and arq.filename:
                    pasta = _pasta_rascunho(doc.id, situacao)
                    nome_salvo = c["nome"] + "__" + secure_filename(arq.filename)
                    arq.save(os.path.join(pasta, nome_salvo))
                    rascunho[c["nome"]] = nome_salvo
                # se nenhum arquivo novo foi escolhido, mantém o que já estava
                # em rascunho.get(c["nome"]) sem sobrescrever com vazio
            else:
                rascunho[c["nome"]] = request.form.get(c["nome"], "")
        session[chave] = rascunho
        if passo < total:
            return redirect(url_for("solicitar", situacao=situacao, passo=passo + 1))
        return redirect(url_for("revisao", situacao=situacao))

    valores = {c["nome"]: rascunho.get(c["nome"], "") for c in formulario["campos"]}
    return render_template("formulario.html", situacao=situacao,
                           titulo_situacao=cfg[situacao]["titulo"],
                           formulario=formulario, passo=passo, total=total, valores=valores)


def _validar(formulario, form, situacao=None):
    erros = []
    for c in formulario["campos"]:
        val = form.get(c["nome"])
        if c.get("obrigatorio"):
            if c["tipo"] == "checkbox" and not val:
                erros.append("Marque o campo obrigatório: " + c["label"])
            elif c["tipo"] != "checkbox" and not (val or "").strip():
                erros.append("Preencha o campo obrigatório: " + c["label"])
    # regra de ouro dos 15 dias de antecedência
    di = form.get("data_inicio")
    df = form.get("data_fim")
    d_ini = None
    if di:
        try:
            d_ini = datetime.strptime(di, "%Y-%m-%d").date()
            if (d_ini - date.today()).days < 15:
                erros.append("Atenção, a data de início está a menos de 15 dias. A norma pede no mínimo 15 dias de antecedência.")
        except ValueError:
            pass
    # regra da duração conforme a situação (guia IN 058/2023)
    if d_ini and df:
        try:
            d_fim = datetime.strptime(df, "%Y-%m-%d").date()
            dur = (d_fim - d_ini).days + 1
            if d_fim < d_ini:
                erros.append("A data de término não pode ser anterior à data de início.")
            elif situacao == "nacional_curto" and dur > 15:
                erros.append("Esta viagem dura mais de 15 dias, então o caso é de afastamento nacional longo. Volte e escolha a situação correta.")
            elif situacao == "nacional_longo" and dur <= 15:
                erros.append("Esta viagem dura 15 dias ou menos, então o caso é de afastamento nacional curto. Volte e escolha a situação correta.")
        except ValueError:
            pass
    return erros


# ---------------- revisão e gravação ----------------
@app.route("/revisao/<situacao>")
def revisao(situacao):
    r = exige_login()
    if r:
        return r
    cfg = carregar_config()["situacoes"]
    if situacao not in cfg:
        abort(404)
    rascunho = session.get("rascunho_" + situacao, {})
    return render_template("revisao.html", situacao=situacao,
                           titulo_situacao=cfg[situacao]["titulo"],
                           forms=cfg[situacao]["formularios"], respostas=rascunho)


@app.route("/salvar/<situacao>", methods=["POST"])
def salvar(situacao):
    r = exige_login()
    if r:
        return r
    cfg = carregar_config()["situacoes"]
    if situacao not in cfg:
        abort(404)
    doc = docente_logado()
    rascunho = session.get("rascunho_" + situacao, {})
    s = Solicitacao(docente_id=doc.id, situacao=situacao,
                    respostas_json=json.dumps(rascunho, ensure_ascii=False))
    db.session.add(s)
    db.session.commit()

    # promove a pasta de rascunho (com os anexos) para uma pasta definitiva,
    # ligada ao id da solicitação que acabou de ser criada
    pasta_rascunho = _pasta_rascunho(doc.id, situacao)
    if os.path.isdir(pasta_rascunho) and os.listdir(pasta_rascunho):
        pasta_final = _pasta_solicitacao(s.id)
        if os.path.isdir(pasta_final):
            shutil.rmtree(pasta_final)
        shutil.move(pasta_rascunho, pasta_final)
    elif os.path.isdir(pasta_rascunho):
        shutil.rmtree(pasta_rascunho)

    session.pop("rascunho_" + situacao, None)
    flash("Solicitação registrada. Agora baixe os documentos preenchidos.", "ok")
    return redirect(url_for("documentos", sid=s.id))


@app.route("/solicitacao/<int:sid>/documentos")
def documentos(sid):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    lista = docs_gen.documentos_da_situacao(s.situacao, _perfil_dict(doc), s.respostas)
    cfg = carregar_config()["situacoes"]

    # anexos de fato enviados pelo professor (convites, apólice, comprovantes...)
    anexos = []
    for formulario in cfg.get(s.situacao, {}).get("formularios", []):
        for c in formulario["campos"]:
            if c["tipo"] == "file" and s.respostas.get(c["nome"]):
                anexos.append((c["label"], c["nome"]))

    return render_template("documentos.html", s=s, lista=lista, anexos=anexos,
                           titulo_situacao=cfg.get(s.situacao, {}).get("titulo", s.situacao))


@app.route("/solicitacao/<int:sid>/anexo/<nome_campo>")
def baixar_anexo(sid, nome_campo):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    nome_salvo = s.respostas.get(nome_campo)
    if not nome_salvo:
        abort(404)
    caminho = os.path.join(_pasta_solicitacao(sid), nome_salvo)
    if not os.path.isfile(caminho):
        abort(404)
    return send_file(caminho, as_attachment=True,
                     download_name=nome_exibicao_arquivo(nome_salvo))


@app.route("/solicitacao/<int:sid>/documento/<tipo>")
def baixar_documento(sid, tipo):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    buf, nome = docs_gen.gerar(tipo, _perfil_dict(doc), s.respostas)
    if not buf:
        abort(404)
    return send_file(buf, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _perfil_dict(doc):
    return {"nome": doc.nome, "siape": doc.siape, "departamento": doc.departamento,
            "cargo": doc.cargo, "telefone": doc.telefone, "email": doc.email}


@app.route("/minhas-solicitacoes")
def minhas_solicitacoes():
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    itens = (Solicitacao.query.filter_by(docente_id=doc.id)
             .order_by(Solicitacao.criado_em.desc()).all())
    cfg = carregar_config()["situacoes"]
    return render_template("minhas_solicitacoes.html", itens=itens, cfg=cfg)


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
