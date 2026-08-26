# Plataforma de solicitação de afastamentos - protótipo

Protótipo em Flask que concentra a solicitação de diárias, passagens e afastamentos antes do lançamento no SCDP. Segue as três situações da IN 058/2023 da UFF, conforme o guia oficial.

Ele organiza a solicitação, não substitui o SCDP. A Secretaria segue lançando no SCDP, ou no futuro um robô lança por ela.

## O que já faz

- Login institucional com Google, restrito ao domínio id.uff.br, sem que o site veja a senha.
- Acesso de teste embutido, para experimentar sem configurar o Google.
- Cadastro dos dados do docente, salvos para reuso.
- Escolha entre as três situações de afastamento.
- Formulários em vários passos, um por página, fiéis aos quatro passos de cada situação do guia.
- Validação da regra de ouro dos 15 dias de antecedência e da duração de cada situação.
- Revisão antes de enviar e histórico das solicitações.
- Geração dos documentos em Word ao final da solicitação, já preenchidos com o que o professor digitou, editáveis antes de assinar.
- Formulários definidos em um arquivo de configuração, para mudar campos sem tocar no código.


## Fidelidade ao regulamento (IN 058/2023)

Os formulários seguem os campos reais dos anexos da Instrução Normativa GAR/RET/UFF 058/2023.
- Situação 1, nacional curto, usa os campos do Anexo II, Requisição de Diárias e Passagens, mais o Termo de Renúncia, Anexo V.
- Situações 2 e 3 acrescentam o número do processo no SEI, e a 3 exige a apólice de seguro viagem, com publicação no DOU.
- Os dados pessoais e bancários não são recoletados na solicitação, pois vêm do SIAPE, conforme a Obs 1 do Anexo II. Isso reduz a exposição de dados e ajuda na conformidade com a LGPD.
- O assistente de enquadramento reproduz a tabela do Anexo VII. Ele pergunta abrangência, atividade, duração e categoria do servidor, e indica a situação correta e se abre processo no SEI.
- Cada passo traz orientações e links diretos para o SCDP e para a página de orientações da UFF.

## Documentos gerados ao final

Ao concluir uma solicitação, o sistema abre a tela de documentos e monta arquivos Word preenchidos com os dados informados, prontos para conferir, editar e assinar. Também dá para gerar os documentos de qualquer solicitação depois, pelo botão Baixar no histórico. São gerados:
- Anexo II, Requisição de Diárias e Passagens, preenchido com o proponente, os dados do proposto, a viagem, os trechos, a missão e o objetivo.
- Anexo V, Termo de Renúncia, quando o professor indica que renuncia a diárias e ou passagens.
- Relatório de viagem, nacional (Anexo III) ou internacional (Anexo IV) conforme a situação, com o cabeçalho preenchido e os campos de relato em branco para a prestação de contas após a viagem.

A geração usa a biblioteca python-docx, já incluída no requirements.txt.

## Como rodar

1. Crie e ative um ambiente virtual.
   - `python -m venv venv`
   - Windows `venv\Scripts\activate`, Linux ou Mac `source venv/bin/activate`
2. Instale as dependências.
   - `pip install -r requirements.txt`
3. Copie o arquivo de exemplo de variáveis.
   - `cp .env.example .env` (no Windows, copie manualmente)
4. Rode.
   - `python app.py`
5. Abra no navegador.
   - `http://localhost:5000`

Na primeira tela use o acesso de teste, informando qualquer e-mail terminado em @id.uff.br. O banco de dados SQLite é criado sozinho no primeiro acesso, no arquivo dados.db.

## Como mudar um formulário sem programar

Abra o arquivo forms_config.json. Cada situação tem uma lista de formulários, e cada formulário tem uma lista de campos. Para acrescentar, remover ou renomear um campo, edite esse arquivo e salve. O site passa a montar o formulário novo sozinho, sem alteração no código.

Cada campo aceita estas propriedades:
- nome, o identificador interno, sem espaços
- label, o texto que aparece na tela
- tipo, um entre text, date, number, select, textarea, checkbox, file
- obrigatorio, true ou false
- opcoes, a lista de valores quando o tipo é select
- ajuda, um texto de orientação abaixo do campo

## Como ativar o login real com Google

1. Acesse o Google Cloud Console em https://console.cloud.google.com
2. Crie um projeto e, em Credenciais, gere um ID do cliente OAuth do tipo aplicativo da Web.
3. Em URIs de redirecionamento autorizados, informe `http://localhost:5000/auth/callback` para testes, e depois a URL real de produção.
4. Copie o ID e a chave secreta para o arquivo .env, nos campos GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.
5. Reinicie o app. O botão Entrar com Google passa a funcionar.

Para produção, defina DEV_LOGIN como 0 no .env para desativar o acesso de teste, e use uma SECRET_KEY longa e aleatória.

## Correções aplicadas (revisão de código)

- **Upload de arquivos**: antes, os arquivos selecionados nos formulários
  (convite, apólice de seguro, comprovantes...) eram descartados
  silenciosamente — a tela dava a entender que o arquivo tinha sido
  anexado, mas nada era salvo. Agora os arquivos são gravados de fato em
  `uploads/`, aparecem na tela de Revisão e ficam disponíveis para baixar
  na tela de Documentos. Extensões aceitas: pdf, jpg, jpeg, png, doc, docx
  (tamanho máximo de 15 MB por envio).
- **Checkbox obrigatório desmarcando sozinho**: quando um formulário
  voltava com erro de validação, os checkboxes marcados apareciam
  desmarcados na nova tela, obrigando o usuário a marcá-los de novo sem
  entender por quê. Corrigido.
- **Documento sem o nome da chefia** nas situações "nacional longo" e
  "internacional": o Anexo II gerado saía com o campo "Proponente /
  Concedente" e a linha de assinatura da chefia em branco, porque esse
  dado só era coletado no fluxo "nacional curto". Agora as três situações
  coletam esse dado.
- **Data em formato errado** na tela "Minhas solicitações" (aparecia
  `2026-09-15` em vez de `15/09/2026`). Corrigido.

## Cuidados para virar oficial

A plataforma lida com dados de servidores, então precisa de conformidade com a LGPD e do aval da área de tecnologia da UFF, a STI, antes de entrar em produção. Este protótipo serve para validar a ideia e demonstrar o conceito.

## Estrutura dos arquivos

- app.py, a aplicação e as rotas
- forms_config.json, a definição dos formulários
- docs_gen.py, a geração dos documentos Word
- templates, as telas em HTML
- static/style.css, o estilo
- requirements.txt, as dependências
- .env.example, o modelo de configuração
- uploads/, os arquivos anexados pelos professores (criada sozinha no
  primeiro uso; não é versionada no git)
