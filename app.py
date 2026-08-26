import os
import json
import shutil
from datetime import datetime, date

from flask import (Flask, render_template, redirect, url_for, session,
                   request, flash, abort, send_file)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
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
csrf = CSRFProtect(app)

ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "id.uff.br")
DEV_LOGIN = os.getenv("DEV_LOGIN", "1") == "1"
STAFF_EMAILS = {
    e.strip().lower() for e in os.getenv("STAFF_EMAILS", "").split(",") if e.strip()
}
STATUS_VALIDOS = ["Pendente", "Lançado no SCDP", "Concluído"]
PRAZO_PADRAO_DIAS = 15
# campos do perfil que o Anexo II precisa (vêm do SIAPE, conforme a norma);
# sem eles o documento oficial sai incompleto
PERFIL_CAMPOS_OBRIGATORIOS = [("siape", "SIAPE"), ("departamento", "Departamento"), ("cargo", "Cargo")]

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


# ---- rascunho do formulário, persistido no banco (item 6) ----
def _carregar_rascunho(docente_id, situacao):
    r = Rascunho.query.filter_by(docente_id=docente_id, situacao=situacao).first()
    return r.respostas if r else {}


def _salvar_rascunho(docente_id, situacao, dados):
    r = Rascunho.query.filter_by(docente_id=docente_id, situacao=situacao).first()
    if not r:
        r = Rascunho(docente_id=docente_id, situacao=situacao)
        db.session.add(r)
    r.respostas_json = json.dumps(dados, ensure_ascii=False)
    db.session.commit()


def _excluir_rascunho(docente_id, situacao):
    r = Rascunho.query.filter_by(docente_id=docente_id, situacao=situacao).first()
    if r:
        db.session.delete(r)
        db.session.commit()
    pasta = _pasta_rascunho(docente_id, situacao)
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)


# ---- perfil completo o bastante para gerar documento oficial (item 7) ----
def _perfil_incompleto(doc):
    """Devolve a lista de rótulos dos campos do perfil que ainda faltam."""
    return [rotulo for campo, rotulo in PERFIL_CAMPOS_OBRIGATORIOS if not (getattr(doc, campo) or "").strip()]

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
    is_staff = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Solicitacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    situacao = db.Column(db.String(50), nullable=False)
    respostas_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="Pendente", nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    docente = db.relationship("Docente", backref="solicitacoes")

    @property
    def respostas(self):
        return json.loads(self.respostas_json)


class Rascunho(db.Model):
    """Guarda o formulário em andamento no banco, não só na sessão do
    navegador — se o professor fechar o navegador no meio do preenchimento,
    o rascunho continua ali para ele retomar depois."""
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    situacao = db.Column(db.String(50), nullable=False)
    respostas_json = db.Column(db.Text, nullable=False, default="{}")
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("docente_id", "situacao", name="uq_rascunho_docente_situacao"),)

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


def exige_staff():
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    if not doc or not doc.is_staff:
        abort(403)
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
    return _destino_pos_login(email)


@app.route("/dev-login", methods=["POST"])
def dev_login():
    if not DEV_LOGIN:
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    if not email.endswith("@" + ALLOWED_DOMAIN):
        flash("Use um e-mail @" + ALLOWED_DOMAIN + " para o teste.", "erro")
        return redirect(url_for("login"))
    _entrar(email, request.form.get("nome") or email.split("@")[0])
    return _destino_pos_login(email)


def _entrar(email, nome):
    doc = Docente.query.filter_by(email=email).first()
    if not doc:
        doc = Docente(email=email, nome=nome)
        db.session.add(doc)
    # a lista de e-mails da Secretaria fica no .env (STAFF_EMAILS); ao logar,
    # o sistema confere e ajusta o acesso automaticamente, sem precisar de
    # tela de administração
    deve_ser_staff = email.lower() in STAFF_EMAILS
    if doc.is_staff != deve_ser_staff:
        doc.is_staff = deve_ser_staff
    db.session.commit()
    session["email"] = email


def _destino_pos_login(email):
    """Só força a tela 'Meus dados' se faltar algo que o Anexo II precisa.
    Quem já tem o perfil completo vai direto para a tela de solicitação."""
    doc = Docente.query.filter_by(email=email).first()
    if _perfil_incompleto(doc):
        flash("Complete seus dados antes de começar uma solicitação.", "ok")
        return redirect(url_for("perfil"))
    return redirect(url_for("escolher"))


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
    doc = docente_logado()
    cfg = carregar_config()["situacoes"]
    situacoes = sorted(cfg.items(), key=lambda kv: kv[1].get("ordem", 99))
    rascunhos = Rascunho.query.filter_by(docente_id=doc.id).all()
    rascunhos_pendentes = [
        {"situacao": r.situacao, "titulo": cfg[r.situacao]["titulo"], "atualizado_em": r.atualizado_em}
        for r in rascunhos if r.situacao in cfg
    ]
    return render_template("escolher.html", situacoes=situacoes, rascunhos_pendentes=rascunhos_pendentes)


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
    # lógica derivada da tabela do Anexo VII da IN 058/2023. Os limites e
    # listas usadas aqui (quais atividades contam como "desenvolvimento",
    # o limite de dias, quais categorias sempre abrem SEI) ficam no
    # forms_config.json, em "enquadramento" — se a norma mudar um número
    # ou uma lista, dá para editar o JSON sem mexer neste código.
    regras = carregar_config().get("enquadramento", {})
    atividades_dev = regras.get("atividades_desenvolvimento", ["treinamento", "congresso", "capacitacao"])
    dias_limite = regras.get("dias_limite_sem_sei", 15)
    categorias_sei = regras.get("categorias_sempre_abrem_sei", ["tecnico"])

    if abrangencia == "exterior":
        return ("internacional",
                "Viagem ao exterior. Abre processo no SEI, exige seguro viagem e passa pela DACQ da PROGEPE, com publicação no DOU.",
                True)
    # nacional
    desenvolvimento = atividade in atividades_dev
    if desenvolvimento:
        if periodo == "mais15":
            return ("nacional_longo",
                    f"Ação de desenvolvimento acima de {dias_limite} dias. Abre processo no SEI e vai à DACQ da PROGEPE.",
                    True)
        if categoria in categorias_sei:
            return ("nacional_longo",
                    "Técnico-administrativo em ação de desenvolvimento abre processo no SEI mesmo até "
                    f"{dias_limite} dias, conforme a Instrução de Serviço PROGEPE 001/2020.",
                    True)
        return ("nacional_curto",
                f"Docente em ação de desenvolvimento de 1 a {dias_limite} dias não abre processo no SEI, apenas o Anexo II para cadastro da PCDP.",
                False)
    # viagem a serviço, banca de concurso ou trabalho de campo, nacional
    return ("nacional_curto",
            f"Viagem a serviço, banca de concurso ou trabalho de campo no país não abre processo no SEI, apenas o Anexo II para cadastro da PCDP pela unidade. Se durar mais de {dias_limite} dias, o fluxo é o mesmo, mas confirme o prazo com a Secretaria.",
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

    # respostas parciais ficam no banco (Rascunho), não só na sessão do
    # navegador — assim sobrevivem a fechar o navegador no meio do caminho
    rascunho = _carregar_rascunho(doc.id, situacao)

    if request.method == "POST":
        prazo_dias = cfg[situacao].get("prazo_dias", PRAZO_PADRAO_DIAS)
        erros = _validar(formulario, request.form, situacao, prazo_dias)

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
        _salvar_rascunho(doc.id, situacao, rascunho)
        if passo < total:
            return redirect(url_for("solicitar", situacao=situacao, passo=passo + 1))
        return redirect(url_for("revisao", situacao=situacao))

    valores = {c["nome"]: rascunho.get(c["nome"], "") for c in formulario["campos"]}
    return render_template("formulario.html", situacao=situacao,
                           titulo_situacao=cfg[situacao]["titulo"],
                           formulario=formulario, passo=passo, total=total, valores=valores)


def _validar(formulario, form, situacao=None, prazo_dias=PRAZO_PADRAO_DIAS):
    erros = []
    for c in formulario["campos"]:
        val = form.get(c["nome"])
        if c.get("obrigatorio"):
            if c["tipo"] == "checkbox" and not val:
                erros.append("Marque o campo obrigatório: " + c["label"])
            elif c["tipo"] != "checkbox" and not (val or "").strip():
                erros.append("Preencha o campo obrigatório: " + c["label"])
    # regra de ouro da antecedência mínima — o prazo varia por situação
    # (15 dias para nacional curto, 60 para nacional longo e internacional,
    # conforme forms_config.json), então não dá pra usar um número fixo aqui
    di = form.get("data_inicio")
    df = form.get("data_fim")
    d_ini = None
    if di:
        try:
            d_ini = datetime.strptime(di, "%Y-%m-%d").date()
            if (d_ini - date.today()).days < prazo_dias:
                erros.append(f"Atenção, a data de início está a menos de {prazo_dias} dias. A norma pede no mínimo {prazo_dias} dias de antecedência para esta situação.")
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


@app.route("/rascunho/<situacao>/descartar", methods=["POST"])
def descartar_rascunho(situacao):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    _excluir_rascunho(doc.id, situacao)
    flash("Rascunho descartado.", "ok")
    return redirect(url_for("escolher"))


# ---------------- revisão e gravação ----------------
@app.route("/revisao/<situacao>")
def revisao(situacao):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    cfg = carregar_config()["situacoes"]
    if situacao not in cfg:
        abort(404)
    faltando = _perfil_incompleto(doc)
    if faltando:
        flash("Antes de enviar, complete no seu perfil: " + ", ".join(faltando) +
             ". Esses dados são obrigatórios no Anexo II.", "erro")
        return redirect(url_for("perfil"))
    rascunho = _carregar_rascunho(doc.id, situacao)
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
    faltando = _perfil_incompleto(doc)
    if faltando:
        flash("Antes de enviar, complete no seu perfil: " + ", ".join(faltando) +
             ". Esses dados são obrigatórios no Anexo II.", "erro")
        return redirect(url_for("perfil"))
    rascunho = _carregar_rascunho(doc.id, situacao)
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

    r_rascunho = Rascunho.query.filter_by(docente_id=doc.id, situacao=situacao).first()
    if r_rascunho:
        db.session.delete(r_rascunho)
        db.session.commit()
    flash("Solicitação registrada. Agora baixe os documentos preenchidos.", "ok")
    return redirect(url_for("documentos", sid=s.id))


@app.route("/solicitacao/<int:sid>/documentos")
def documentos(sid):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    if doc.is_staff:
        s = Solicitacao.query.filter_by(id=sid).first_or_404()
    else:
        s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    lista = docs_gen.documentos_da_situacao(s.situacao, _perfil_dict(s.docente), s.respostas)
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
    if doc.is_staff:
        s = Solicitacao.query.filter_by(id=sid).first_or_404()
    else:
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
    if doc.is_staff:
        s = Solicitacao.query.filter_by(id=sid).first_or_404()
    else:
        s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    buf, nome = docs_gen.gerar(tipo, _perfil_dict(s.docente), s.respostas)
    if not buf:
        abort(404)
    return send_file(buf, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _perfil_dict(doc):
    return {"nome": doc.nome, "siape": doc.siape, "departamento": doc.departamento,
            "cargo": doc.cargo, "telefone": doc.telefone, "email": doc.email}


@app.route("/solicitacao/<int:sid>/excluir", methods=["POST"])
def excluir_solicitacao(sid):
    r = exige_login()
    if r:
        return r
    doc = docente_logado()
    s = Solicitacao.query.filter_by(id=sid, docente_id=doc.id).first_or_404()
    # só deixa excluir enquanto ainda está pendente — depois que a Secretaria
    # começa a tratar (mudou o status), cancelar por conta própria pode
    # deixar a Secretaria sem saber que sumiu
    if s.status != "Pendente":
        flash("Esta solicitação já está sendo tratada pela Secretaria e não pode mais ser excluída por aqui. Fale direto com a Secretaria.", "erro")
        return redirect(url_for("minhas_solicitacoes"))
    pasta = _pasta_solicitacao(sid)
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
    db.session.delete(s)
    db.session.commit()
    flash("Solicitação excluída.", "ok")
    return redirect(url_for("minhas_solicitacoes"))


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


# ---------------- painel da secretaria ----------------
@app.route("/secretaria")
def secretaria():
    r = exige_staff()
    if r:
        return r
    cfg = carregar_config()["situacoes"]

    situacao_f = request.args.get("situacao", "")
    status_f = request.args.get("status", "")
    busca = (request.args.get("busca") or "").strip().lower()

    query = Solicitacao.query.join(Docente)
    if situacao_f:
        query = query.filter(Solicitacao.situacao == situacao_f)
    if status_f:
        query = query.filter(Solicitacao.status == status_f)
    itens = query.order_by(Solicitacao.criado_em.desc()).all()

    if busca:
        def bate(s):
            alvo = " ".join([
                s.docente.nome or "", s.docente.email or "",
                s.respostas.get("destino") or "", s.respostas.get("cidade_destino") or "",
            ]).lower()
            return busca in alvo
        itens = [s for s in itens if bate(s)]

    return render_template("secretaria.html", itens=itens, cfg=cfg,
                           situacoes=cfg.items(), status_validos=STATUS_VALIDOS,
                           situacao_f=situacao_f, status_f=status_f, busca=busca)


@app.route("/secretaria/solicitacao/<int:sid>/status", methods=["POST"])
def atualizar_status(sid):
    r = exige_staff()
    if r:
        return r
    s = Solicitacao.query.get_or_404(sid)
    novo = request.form.get("status")
    if novo not in STATUS_VALIDOS:
        abort(400)
    s.status = novo
    db.session.commit()
    flash("Status atualizado.", "ok")
    # mantém os filtros que estavam ativos na tela (vieram como campos ocultos)
    filtros = {
        "situacao": request.form.get("situacao_f", ""),
        "status": request.form.get("status_f", ""),
        "busca": request.form.get("busca_f", ""),
    }
    filtros = {k: v for k, v in filtros.items() if v}
    return redirect(url_for("secretaria", **filtros))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    # debug=True vaza stack trace e habilita o debugger interativo do
    # Werkzeug (risco de execução remota de código se alguém achar o PIN) —
    # nunca deixe ligado em um ambiente exposto. Controlado pelo .env.
    modo_debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=modo_debug, port=5000)
