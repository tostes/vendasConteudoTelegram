# Bot simples de pacotes e Pix

Fluxo:

1. usuário envia `/start`;
2. o bot envia uma imagem;
3. o bot apresenta os pacotes;
4. o usuário escolhe um pacote;
5. o bot gera QR Code e Pix copia e cola;
6. o usuário pode clicar em **Já paguei**;
7. o bot também verifica pagamentos pendentes automaticamente;
8. depois da confirmação, a assinatura é gravada no SQLite;
9. se `TELEGRAM_CHANNEL_ID` estiver configurado, o bot envia um convite individual.

## Instalação

```bash
unzip telegram_pix_bot_simples.zip
cd telegram_pix_bot_simples

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
cp settings.example.py settings.py

nano .env
nano settings.py
```

## Executar

```bash
source .venv/bin/activate
python bot.py
```

Não é necessário Flask, webhook ou Cloudflare Tunnel.

O bot utiliza polling para receber mensagens do Telegram e consulta o Asaas
periodicamente para verificar os pagamentos.

## Personalizar os pacotes

Edite o dicionário `PACKAGES` no início de `bot.py`:

```python
PACKAGES = {
    "mensal": {
        "name": "Pacote Mensal",
        "price": 39.90,
        "days": 30,
        "description": "Acesso por 30 dias",
    }
}
```

## Personalizar a imagem

Substitua:

```text
banner.png
```

por outra imagem com o mesmo nome, ou altere `BANNER_PATH` no `.env`.

## Comandos

```text
/start
/pacotes
/status
```

## Sandbox do Asaas

Use inicialmente:

```env
ASAAS_BASE_URL=https://api-sandbox.asaas.com/v3
```

Depois, no painel Sandbox, simule a confirmação da cobrança.

## Configurações do Telegram

As informações do bot e do canal ficam em `settings.py`:

```python
TELEGRAM_BOT_TOKEN = "123456789:SEU_TOKEN"
TELEGRAM_CHANNEL_ID = "-1001234567890"
```

`settings.py` está no `.gitignore`. Use `settings.example.py` como modelo.

## Canal privado

O canal é opcional durante os primeiros testes.

Para liberar acesso automaticamente:

1. crie um canal privado;
2. adicione o bot como administrador;
3. permita criar links e remover membros;
4. configure `TELEGRAM_CHANNEL_ID`.


## Ativar ou desativar o gateway de pagamento

No arquivo `settings.py`, use:

```python
gateway_pagamento = True
```

Com `True`, o usuário escolhe um pacote e o bot gera a cobrança Pix.

Para liberar o usuário diretamente no grupo ou canal, sem cobrança:

```python
gateway_pagamento = False
```

Nesse modo, ao escolher um pacote, o bot:

1. registra a assinatura no SQLite;
2. cria um link individual com uma única utilização;
3. envia o botão **Entrar no grupo**.

O bot precisa ser administrador do grupo/canal e ter permissão para criar links de convite.


## Remoção de assinaturas vencidas com cron

O arquivo `expire_subscriptions.py` roda separadamente do bot.

Teste manualmente:

```bash
cd /home/diego/telegram_pix_mvp/telegram_pix_bot_simples_settings/telegram_pix_bot_simples
source .venv/bin/activate
python expire_subscriptions.py
```

Para executar a cada 5 minutos:

```bash
crontab -e
```

Adicione uma única linha:

```cron
*/5 * * * * cd /home/diego/telegram_pix_mvp/telegram_pix_bot_simples_settings/telegram_pix_bot_simples && /home/diego/telegram_pix_mvp/telegram_pix_bot_simples_settings/telegram_pix_bot_simples/.venv/bin/python expire_subscriptions.py >> expire_subscriptions.log 2>&1
```

O script:

1. procura assinaturas com `status = 'active'`;
2. compara `expires_at` com o horário UTC atual;
3. bane o usuário do canal;
4. remove o ban para permitir uma renovação futura;
5. altera o status para `expired`;
6. envia uma mensagem informando o vencimento.

O bot precisa ser administrador do canal e ter permissão para banir usuários.


## Pagamento com Telegram Stars

Com `gateway_pagamento = True`, o bot cobra usando Stars.

Os valores ficam no dicionário `PACKAGES`:

```python
"mensal": {
    "name": "Pacote Mensal",
    "price": 39.90,
    "stars": 250,
    "days": 30,
    "description": "Acesso por 30 dias",
}
```

O fluxo é:

1. usuário escolhe o pacote;
2. Telegram abre uma invoice em Stars;
3. o bot valida a pré-compra;
4. Telegram confirma com `successful_payment`;
5. o pagamento é salvo em `star_payments`;
6. a assinatura é ativada em `subscriptions`;
7. o convite individual é enviado.

Não é necessário token de provedor. Para Stars, a invoice usa `currency="XTR"`
e `provider_token=""`.
