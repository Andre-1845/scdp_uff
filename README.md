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

## Painel da Secretaria (novo)

**Atenção, antes de rodar esta versão:** se você já tinha usado uma versão
anterior deste sistema, apague o arquivo `dados.db` antes de rodar de novo.
Esta atualização acrescentou colunas novas nas tabelas do banco
(`is_staff` no professor, `status` na solicitação), e o SQLite não adiciona
colunas sozinho em um banco que já existe — ele só cria tabelas novas do
zero. Como ainda é fase de protótipo/teste, a forma mais simples é apagar
`dados.db` e deixar o sistema recriar o banco na próxima vez que rodar
(`python app.py`). Isso apaga as solicitações de teste que você já tinha
criado, mas não afeta nada de produção, já que isso ainda não está em uso
real.

Agora existe uma visão que reúne as solicitações de **todos** os professores,
não só as de quem está logado — é o que faltava para a Secretaria conseguir
usar o sistema de fato para organizar o que precisa ser lançado no SCDP.

### Como dar acesso a alguém

Não tem tela de cadastro de usuário/permissão. É mais simples: no arquivo
`.env`, defina os e-mails da Secretaria na variável `STAFF_EMAILS`, separados
por vírgula:

```
STAFF_EMAILS=secretaria@id.uff.br,outra.pessoa@id.uff.br
```

Quem logar com um desses e-mails (pelo Google ou pelo acesso de teste)
ganha acesso automático ao Painel da Secretaria — não precisa reiniciar o
banco nem fazer nada manual. Se tirar um e-mail dessa lista, a pessoa perde
o acesso no próximo login dela.

### O que o painel mostra

- Todas as solicitações, com nome, e-mail e departamento do professor.
- Filtro por situação (curta/longa/internacional), por status e por busca
  livre (nome, e-mail ou destino).
- Um status por solicitação — **Pendente**, **Lançado no SCDP** ou
  **Concluído** — que a Secretaria muda direto na lista, sem precisar abrir
  cada uma.
- Acesso aos documentos Word e aos anexos de qualquer solicitação (a
  Secretaria não fica restrita a ver só o que ela mesma preencheu).

## Correções e melhorias (segunda rodada)

**Atenção, antes de rodar esta versão:** ela acrescenta mais uma tabela no
banco (`rascunho`). Se você já vinha usando uma versão anterior e o
`dados.db` já existe, apague-o antes de rodar de novo, pelo mesmo motivo já
explicado na seção do Painel da Secretaria — o SQLite não cria coluna ou
tabela nova sozinho num banco que já existe. Isso é só para a fase de
protótipo, sem dado real em uso.

### Rascunho do formulário agora sobrevive a fechar o navegador

Antes, as respostas dos passos do formulário ficavam só num cookie de
sessão do navegador — se o professor fechasse a aba ou o navegador no meio
do preenchimento, perdia tudo sem aviso. Agora cada resposta é salva no
banco de dados a cada passo, associada ao professor e à situação. Se ele
sair no meio do caminho, ao voltar (mesmo em outro dia, outro computador
com o mesmo login) a tela "Nova solicitação" mostra um aviso "Você tem
solicitação(ões) em andamento", com um link para continuar de onde parou e
outro para descartar o rascunho.

### Documento oficial não sai mais incompleto por falta de dado do SIAPE

O Anexo II depende de SIAPE, departamento e cargo do professor, que vêm da
tela "Meus dados". Antes, esses campos eram opcionais e dava para gerar um
documento oficial com eles em branco. Agora:
- No primeiro login, só é forçada a tela de perfil se algum desses dados
  estiver faltando (antes era sempre forçada, mesmo sem nada a corrigir).
- Antes de enviar a solicitação (na revisão e na gravação), o sistema
  confere de novo se o perfil está completo; se não estiver, manda para a
  tela "Meus dados" com aviso de quais campos faltam.

### Prazo de antecedência agora é o correto por situação

O aviso e a validação de "regra de ouro" usavam sempre 15 dias, mas a
norma pede 60 dias de antecedência para as situações "nacional longo" e
"internacional" (isso já estava certo no resumo de cada card, mas a
validação do formulário e o aviso fixo no rodapé da tela "Nova solicitação"
ainda usavam 15 para todas). Agora o prazo vem do `forms_config.json` (uma
entrada `prazo_dias` por situação) e cada card mostra o prazo certo.

### Segurança, antes de sair do protótipo

- **Proteção CSRF** em todos os formulários (Flask-WTF), o que evita que
  outro site force uma ação no sistema em nome de um usuário já logado.
- **`debug` desligado por padrão**: antes ficava sempre ligado
  (`debug=True`), o que expõe informação interna e o debugger interativo
  do Werkzeug em caso de erro. Agora só liga se `FLASK_DEBUG=1` estiver no
  `.env`, e o padrão de fábrica é desligado.
- A lógica do assistente de enquadramento (`_enquadrar()`) agora lê os
  limites e listas (quais atividades contam como "desenvolvimento", o
  limite de dias, quais categorias sempre abrem SEI) de uma seção nova do
  `forms_config.json` (`enquadramento`), em vez de ter esses números fixos
  no código Python. Ainda não é um "motor de regras" completo — a
  estrutura da lógica continua em Python — mas os números que mais mudam
  com a norma agora ficam editáveis sem mexer em código.
- Segue pendente (recomendação, não implementado ainda): trocar o SQLite
  por um banco com melhor suporte a acesso concorrente antes de qualquer
  uso com volume real de professores simultâneos.

### Outras melhorias de uso do dia a dia

- Confirmação antes de enviar a solicitação final ("Confirma o envio?
  Isso registra a solicitação e gera os documentos oficiais..."), já que
  antes o clique único no botão já gravava tudo.
- Dá para excluir uma solicitação enviada por engano, enquanto ela ainda
  estiver com status "Pendente" (tela "Minhas solicitações"). Depois que a
  Secretaria começa a tratar (muda o status), não dá mais para excluir por
  ali — nesse caso é preciso falar direto com a Secretaria.

## Cuidados para virar oficial

A plataforma lida com dados de servidores, então precisa de conformidade com a LGPD e do aval da área de tecnologia da UFF, a STI, antes de entrar em produção. Este protótipo serve para validar a ideia e demonstrar o conceito. Como avanço desde a versão anterior, já tem proteção CSRF nos formulários e o modo debug fica desligado por padrão — mas o SQLite (bom para protótipo) ainda precisa ser avaliado antes de um uso com volume real.

## Estrutura dos arquivos

- app.py, a aplicação e as rotas
- forms_config.json, a definição dos formulários (inclui o prazo de
  antecedência e as regras do assistente de enquadramento)
- docs_gen.py, a geração dos documentos Word
- templates, as telas em HTML
- static/style.css, o estilo
- requirements.txt, as dependências
- .env.example, o modelo de configuração
- uploads/, os arquivos anexados pelos professores (criada sozinha no
  primeiro uso; não é versionada no git)
