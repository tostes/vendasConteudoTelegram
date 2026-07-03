# Venda de Conteúdo no Telegram com Telegram Stars

Aplicação simples em Python para vender acesso temporário a um canal privado do Telegram usando **Telegram Stars**.

O bot funciona por polling, registra usuários, pagamentos e assinaturas em SQLite e pode remover automaticamente assinantes vencidos.

## Fluxo da aplicação

1. o usuário envia `/start`;
2. o bot envia uma imagem de apresentação;
3. o bot exibe os pacotes configurados;
4. o usuário escolhe um pacote;
5. o Telegram abre uma cobrança em Stars;
6. o bot valida a pré-compra;
7. o Telegram confirma o pagamento;
8. o pagamento é registrado no SQLite;
9. a assinatura é criada ou renovada;
10. o bot envia um convite individual para o canal privado;
11. ao vencer, o usuário pode ser removido automaticamente pelo script de expiração.

Também existe um modo sem cobrança, útil para testes ou liberação manual de acesso.

---

## Estrutura do projeto

```text
.
├── bot.py
├── expire_subscriptions.py
├── settings_example.py
├── banner.png
├── requirements.txt
├── .gitignore
└── README.md
```

Os arquivos abaixo são locais e não devem ser enviados ao GitHub:

```text
settings.py
subscriptions.db
.venv/
*.log
```

---

## Clonar o repositório

```bash
git clone https://github.com/tostes/vendasConteudoTelegram.git
cd vendasConteudoTelegram
```

---

## Criar o ambiente virtual

No Ubuntu ou Debian:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Atualize o `pip`:

```bash
python -m pip install --upgrade pip
```

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

Sempre que abrir um novo terminal, ative o ambiente novamente:

```bash
source .venv/bin/activate
```

---

## Criar o arquivo de configuração

Copie o arquivo de exemplo:

```bash
cp settings_example.py settings.py
```

Edite:

```bash
nano settings.py
```

Exemplo:

```python
TELEGRAM_BOT_TOKEN = "123456789:SEU_TOKEN"

TELEGRAM_CHANNEL_ID = "-1001234567890"

SUPPORT_USERNAME = "@seu_usuario"

gateway_pagamento = True

PACKAGES = {
    "basico": {
        "name": "Pacote Básico",
        "stars": 100,
        "days": 7,
        "description": "Acesso por 7 dias",
    },

    "mensal": {
        "name": "Pacote Mensal",
        "stars": 250,
        "days": 30,
        "description": "Acesso por 30 dias",
    },

    "trimestral": {
        "name": "Pacote Trimestral",
        "stars": 600,
        "days": 90,
        "description": "Acesso por 90 dias",
    },
}
```

O arquivo `settings.py` está no `.gitignore` e não deve ser versionado.

---

## Criar o bot no Telegram

Abra o `@BotFather` e execute:

```text
/newbot
```

Escolha:

- o nome do bot;
- um username terminado em `bot`.

Depois copie o token fornecido e coloque em:

```python
TELEGRAM_BOT_TOKEN = "SEU_TOKEN"
```

Nunca publique esse token.

Caso ele seja exposto, use no `@BotFather`:

```text
/revoke
```

---

## Configurar o canal privado

1. crie um canal privado no Telegram;
2. adicione o bot como administrador;
3. permita que ele crie links de convite;
4. permita que ele remova ou bana usuários;
5. descubra o ID do canal;
6. configure `TELEGRAM_CHANNEL_ID` em `settings.py`.

Exemplo:

```python
TELEGRAM_CHANNEL_ID = "-1001234567890"
```

O canal é opcional durante os primeiros testes, mas necessário para o envio automático dos convites.

---

## Configurar os pacotes

Os pacotes ficam em `settings.py`.

Cada pacote precisa ter:

```python
{
    "name": "Nome exibido",
    "stars": 100,
    "days": 30,
    "description": "Descrição do pacote",
}
```

Exemplo:

```python
PACKAGES = {
    "mensal": {
        "name": "Pacote Mensal",
        "stars": 250,
        "days": 30,
        "description": "Acesso ao canal por 30 dias",
    }
}
```

O identificador do pacote, como `mensal`, deve ser único.

---

## Personalizar a imagem

Substitua o arquivo:

```text
banner.png
```

por outra imagem com o mesmo nome.

Também é possível definir outro caminho usando a variável de ambiente:

```bash
export BANNER_PATH="/caminho/para/outra-imagem.png"
```

---

## Executar o bot

Ative o ambiente virtual:

```bash
source .venv/bin/activate
```

Inicie:

```bash
python bot.py
```

A saída esperada é semelhante a:

```text
Bot iniciado em modo polling
```

Não é necessário configurar Flask, webhook, servidor web ou Cloudflare Tunnel.

---

## Comandos disponíveis

```text
/start
/pacotes
/status
/paysupport
/meuid
```

### `/start`

Exibe a imagem e os pacotes.

### `/pacotes`

Exibe novamente os pacotes disponíveis.

### `/status`

Mostra o pacote atual e a data de vencimento.

### `/paysupport`

Exibe o usuário configurado para suporte.

### `/meuid`

Mostra o ID Telegram do usuário.

---

## Ativar ou desativar pagamentos

No `settings.py`:

```python
gateway_pagamento = True
```

Com `True`, o bot gera uma invoice em Telegram Stars.

Para liberar o acesso diretamente, sem cobrança:

```python
gateway_pagamento = False
```

Nesse modo, ao escolher um pacote, o bot:

1. registra ou renova a assinatura;
2. cria um convite individual;
3. envia o botão para entrada no canal.

Esse modo é útil para testes ou concessões manuais.

---

## Pagamento com Telegram Stars

Com `gateway_pagamento = True`, o bot utiliza a moeda:

```text
XTR
```

O fluxo é:

1. o usuário escolhe o pacote;
2. o bot cria uma invoice;
3. o Telegram envia `pre_checkout_query`;
4. o bot valida usuário, moeda e valor;
5. o Telegram envia `successful_payment`;
6. o pagamento é salvo em `star_payments`;
7. a assinatura é criada ou renovada em `subscriptions`;
8. o convite individual é enviado.

Para Telegram Stars, não é necessário conectar um gateway externo.

A chamada utiliza:

```python
currency="XTR"
```

O parâmetro `provider_token` é omitido.

---

## Banco de dados SQLite

O banco é criado automaticamente ao iniciar o bot:

```text
subscriptions.db
```

As principais tabelas são:

```text
users
star_payments
subscriptions
```

O banco não é enviado ao GitHub.

Para inspecionar:

```bash
sqlite3 subscriptions.db
```

Exemplos:

```sql
SELECT * FROM users;

SELECT * FROM star_payments
ORDER BY id DESC;

SELECT * FROM subscriptions;
```

Para sair:

```sql
.quit
```

---

## Remover assinaturas vencidas

O arquivo:

```text
expire_subscriptions.py
```

roda separadamente do bot.

Teste manualmente:

```bash
source .venv/bin/activate
python expire_subscriptions.py
```

O script:

1. procura assinaturas ativas vencidas;
2. compara `expires_at` com o horário UTC atual;
3. bane o usuário do canal;
4. remove o ban para permitir uma futura renovação;
5. altera o status da assinatura para `expired`;
6. envia uma mensagem informando o vencimento.

O bot precisa ter permissão para remover usuários.

---

## Executar a expiração com cron

Descubra o caminho completo do projeto:

```bash
pwd
```

Edite o cron:

```bash
crontab -e
```

Exemplo a cada cinco minutos:

```cron
*/5 * * * * cd /CAMINHO/vendasConteudoTelegram && /CAMINHO/vendasConteudoTelegram/.venv/bin/python expire_subscriptions.py >> expire_subscriptions.log 2>&1
```

Exemplo com um caminho real:

```cron
*/5 * * * * cd /home/usuario/vendasConteudoTelegram && /home/usuario/vendasConteudoTelegram/.venv/bin/python expire_subscriptions.py >> expire_subscriptions.log 2>&1
```

Verifique o log:

```bash
tail -f expire_subscriptions.log
```

---

## Executar o bot em segundo plano

Para testes simples:

```bash
nohup .venv/bin/python bot.py > bot.log 2>&1 &
```

Acompanhe:

```bash
tail -f bot.log
```

Veja o processo:

```bash
ps aux | grep bot.py
```

Pare o processo:

```bash
pkill -f "python bot.py"
```

Para produção, recomenda-se criar um serviço `systemd`.

---

## Atualizar a aplicação

Dentro do diretório do projeto:

```bash
git pull
```

Ative o ambiente:

```bash
source .venv/bin/activate
```

Atualize as dependências:

```bash
python -m pip install -r requirements.txt
```

Reinicie o bot.

---

## Verificações de segurança

Antes de fazer qualquer commit:

```bash
git check-ignore -v settings.py
git check-ignore -v subscriptions.db
```

Confira os arquivos que serão enviados:

```bash
git status --short
```

Procure tokens expostos:

```bash
grep -RInE \
  --exclude='settings.py' \
  --exclude='subscriptions.db' \
  --exclude-dir='.git' \
  --exclude-dir='.venv' \
  '[0-9]{8,}:[A-Za-z0-9_-]{20,}' .
```

Esse comando não deve retornar nenhum token.

---

## Problemas comuns

### `TELEGRAM_BOT_TOKEN não configurado`

Crie o arquivo:

```bash
cp settings_example.py settings.py
```

Depois edite o token.

### O convite não é criado

Confirme que:

- o ID do canal está correto;
- o bot é administrador;
- o bot pode criar links de convite.

### O usuário vencido não é removido

Confirme que:

- o bot pode banir usuários;
- o cron está ativo;
- o caminho do Python no cron está correto;
- o usuário não é o proprietário do canal.

### `FOREIGN KEY constraint failed`

Confirme se a tabela `subscriptions` referencia:

```text
star_payments
```

Execute:

```bash
sqlite3 subscriptions.db
```

Depois:

```sql
PRAGMA foreign_key_list(subscriptions);
```

### O pagamento não abre

Confirme:

- que o pacote possui `stars` maior que zero;
- que a moeda usada é `XTR`;
- que `provider_token` não está sendo enviado;
- que a conta Google Play ou App Store pode comprar Stars;
- que o bot foi criado corretamente no `@BotFather`.

---

## Licença

Este projeto pode ser adaptado conforme a necessidade do proprietário do repositório.
