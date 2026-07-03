import logging
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
    gateway_pagamento,
    PACKAGES,
    SUPPORT_USERNAME
)


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "subscriptions.db"),
    )
)

BANNER_PATH = Path(
    os.getenv(
        "BANNER_PATH",
        str(BASE_DIR / "banner.png"),
    )
)

# ============================================================
#SUPPORT_USERNAME importado de settings.py
# ============================================================

# ============================================================
# PACOTES agora sao importados de settings
# ============================================================



# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("telegram-stars-bot")


# ============================================================
# VALIDATE PACKAGES
# ============================================================
def validate_packages() -> None:
    if not PACKAGES:
        raise RuntimeError(
            "Nenhum pacote configurado em settings.py"
        )

    required_fields = {
        "name",
        "stars",
        "days",
        "description",
    }

    for package_id, package in PACKAGES.items():
        missing = required_fields - package.keys()

        if missing:
            raise RuntimeError(
                f"Pacote '{package_id}' incompleto. "
                f"Campos ausentes: {sorted(missing)}"
            )

        if not isinstance(package["stars"], int):
            raise RuntimeError(
                f"Pacote '{package_id}': stars deve ser inteiro"
            )

        if package["stars"] <= 0:
            raise RuntimeError(
                f"Pacote '{package_id}': stars deve ser maior que zero"
            )

        if not isinstance(package["days"], int):
            raise RuntimeError(
                f"Pacote '{package_id}': days deve ser inteiro"
            )

        if package["days"] <= 0:
            raise RuntimeError(
                f"Pacote '{package_id}': days deve ser maior que zero"
            )
# ============================================================
# DATAS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


# ============================================================
# SQLITE
# ============================================================

@contextmanager
def db():
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=20,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                telegram_chat_id INTEGER NOT NULL,
                telegram_username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS star_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                telegram_user_id INTEGER NOT NULL,
                package_id TEXT NOT NULL,

                invoice_payload TEXT NOT NULL UNIQUE,

                telegram_payment_charge_id TEXT UNIQUE,
                provider_payment_charge_id TEXT,

                stars_amount INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'pending',

                created_at TEXT NOT NULL,
                paid_at TEXT,

                FOREIGN KEY (telegram_user_id)
                    REFERENCES users(telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                telegram_user_id INTEGER PRIMARY KEY,

                package_id TEXT NOT NULL,

                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'active',

                last_payment_id INTEGER,

                updated_at TEXT NOT NULL,

                FOREIGN KEY (telegram_user_id)
                    REFERENCES users(telegram_user_id),

                FOREIGN KEY (last_payment_id)
                    REFERENCES star_payments(id)
            );

            CREATE INDEX IF NOT EXISTS
                idx_star_payments_status
            ON star_payments (
                status,
                created_at
            );

            CREATE INDEX IF NOT EXISTS
                idx_subscriptions_expiration
            ON subscriptions (
                status,
                expires_at
            );
            """
        )


# ============================================================
# USUÁRIOS
# ============================================================

def save_user(update: Update) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    now = iso(utc_now())

    with db() as conn:
        conn.execute(
            """
            INSERT INTO users (
                telegram_user_id,
                telegram_chat_id,
                telegram_username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(telegram_user_id)
            DO UPDATE SET
                telegram_chat_id =
                    excluded.telegram_chat_id,

                telegram_username =
                    excluded.telegram_username,

                first_name =
                    excluded.first_name,

                updated_at =
                    excluded.updated_at
            """,
            (
                user.id,
                chat.id,
                user.username,
                user.first_name,
                now,
                now,
            ),
        )


# ============================================================
# INTERFACE DE PACOTES
# ============================================================

def package_keyboard() -> InlineKeyboardMarkup:
    buttons = []

    for package_id, package in PACKAGES.items():

        if gateway_pagamento:
            label = (
                f"{package['name']} — "
                f"⭐ {package['stars']}"
            )
        else:
            label = package["name"]

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=(
                        f"package:{package_id}"
                    ),
                )
            ]
        )

    return InlineKeyboardMarkup(buttons)


def package_caption() -> str:
    lines = [
        "Escolha um dos pacotes abaixo:",
        "",
    ]

    for package in PACKAGES.values():

        if gateway_pagamento:
            price_text = (
                f"⭐ {package['stars']} Stars"
            )
        else:
            price_text = "Acesso direto"

        lines.append(
            f"• {package['name']} — "
            f"{price_text} — "
            f"{package['description']}"
        )

    return "\n".join(lines)


async def show_packages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    save_user(update)

    chat = update.effective_chat

    if not chat:
        return

    if BANNER_PATH.exists():
        with BANNER_PATH.open("rb") as banner:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=banner,
                caption=package_caption(),
                reply_markup=package_keyboard(),
            )
    else:
        await context.bot.send_message(
            chat_id=chat.id,
            text=package_caption(),
            reply_markup=package_keyboard(),
        )


# ============================================================
# COMANDOS
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await show_packages(
        update,
        context,
    )


async def paysupport(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.effective_message.reply_text(
        "Suporte para pagamentos:\n\n"
        f"Entre em contato com {SUPPORT_USERNAME}."
    )


async def meu_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user = update.effective_user

    if not user:
        return

    await update.effective_message.reply_text(
        f"Seu Telegram ID é:\n{user.id}"
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    save_user(update)

    user = update.effective_user

    if not user:
        return

    with db() as conn:
        subscription = conn.execute(
            """
            SELECT
                package_id,
                starts_at,
                expires_at,
                status
            FROM subscriptions
            WHERE telegram_user_id = ?
            """,
            (user.id,),
        ).fetchone()

    if not subscription:
        await update.effective_message.reply_text(
            "Você ainda não possui uma assinatura."
        )
        return

    expiration = parse_iso(
        subscription["expires_at"]
    )

    if (
        subscription["status"] == "active"
        and expiration
        and expiration > utc_now()
    ):
        package = PACKAGES.get(
            subscription["package_id"]
        )

        package_name = (
            package["name"]
            if package
            else subscription["package_id"]
        )

        await update.effective_message.reply_text(
            "✅ Assinatura ativa\n\n"
            f"Pacote: {package_name}\n"
            f"Validade: {expiration:%d/%m/%Y %H:%M} UTC"
        )

    else:
        await update.effective_message.reply_text(
            "Sua assinatura está vencida.\n\n"
            "Use /pacotes para renovar."
        )


# ============================================================
# CONVITE DO CANAL
# ============================================================

async def create_invite_link(
    context: ContextTypes.DEFAULT_TYPE,
) -> str | None:
    if not TELEGRAM_CHANNEL_ID:
        return None

    invite = await context.bot.create_chat_invite_link(
        chat_id=TELEGRAM_CHANNEL_ID,

        expire_date=(
            utc_now()
            + timedelta(minutes=30)
        ),

        member_limit=1,

        name=(
            "assinante-"
            f"{utc_now():%Y%m%d%H%M%S}"
        ),
    )

    return invite.invite_link


# ============================================================
# ATIVAÇÃO DA ASSINATURA
# ============================================================

def activate_subscription(
    telegram_user_id: int,
    package_id: str,
    payment_id: int | None,
) -> datetime:

    package = PACKAGES[package_id]
    now = utc_now()

    with db() as conn:
        current = conn.execute(
            """
            SELECT expires_at
            FROM subscriptions
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        ).fetchone()

        old_expiration = None

        if current:
            old_expiration = parse_iso(
                current["expires_at"]
            )

        if (
            old_expiration
            and old_expiration > now
        ):
            base_date = old_expiration
        else:
            base_date = now

        new_expiration = (
            base_date
            + timedelta(
                days=package["days"]
            )
        )

        conn.execute(
            """
            INSERT INTO subscriptions (
                telegram_user_id,
                package_id,
                starts_at,
                expires_at,
                status,
                last_payment_id,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'active', ?, ?)

            ON CONFLICT(telegram_user_id)
            DO UPDATE SET
                package_id =
                    excluded.package_id,

                expires_at =
                    excluded.expires_at,

                status = 'active',

                last_payment_id =
                    excluded.last_payment_id,

                updated_at =
                    excluded.updated_at
            """,
            (
                telegram_user_id,
                package_id,
                iso(now),
                iso(new_expiration),
                payment_id,
                iso(now),
            ),
        )

    return new_expiration


# ============================================================
# ACESSO SEM PAGAMENTO
# ============================================================

async def grant_direct_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    package_id: str,
) -> None:

    query = update.callback_query
    user = update.effective_user

    if not query or not user:
        return

    if not TELEGRAM_CHANNEL_ID:
        await query.message.reply_text(
            "O grupo ou canal ainda não foi "
            "configurado em settings.py."
        )
        return

    try:
        expiration = activate_subscription(
            telegram_user_id=user.id,
            package_id=package_id,
            payment_id=None,
        )

        invite_link = await create_invite_link(
            context
        )

    except TelegramError:
        logger.exception(
            "Erro do Telegram ao liberar acesso"
        )

        await query.message.reply_text(
            "Não foi possível criar o convite."
        )
        return

    except Exception:
        logger.exception(
            "Erro inesperado ao liberar acesso"
        )

        await query.message.reply_text(
            "Não foi possível liberar o acesso."
        )
        return

    package = PACKAGES[package_id]

    keyboard = None

    if invite_link:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="Entrar no canal",
                        url=invite_link,
                    )
                ]
            ]
        )

    await query.message.reply_text(
        "✅ Acesso liberado!\n\n"
        f"Pacote: {package['name']}\n"
        f"Validade: {expiration:%d/%m/%Y}",
        reply_markup=keyboard,
    )


# ============================================================
# CRIAÇÃO DA COBRANÇA EM STARS
# ============================================================

def create_star_invoice_record(
    telegram_user_id: int,
    package_id: str,
) -> str:

    payload = (
        f"stars:{telegram_user_id}:"
        f"{package_id}:"
        f"{secrets.token_hex(8)}"
    )

    package = PACKAGES[package_id]

    with db() as conn:
        conn.execute(
            """
            INSERT INTO star_payments (
                telegram_user_id,
                package_id,
                invoice_payload,
                stars_amount,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (
                telegram_user_id,
                package_id,
                payload,
                package["stars"],
                iso(utc_now()),
            ),
        )

    return payload


async def send_stars_invoice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    package_id: str,
) -> None:

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    package = PACKAGES[package_id]

    payload = create_star_invoice_record(
        telegram_user_id=user.id,
        package_id=package_id,
    )

    await context.bot.send_invoice(
        chat_id=chat.id,

        title=package["name"],

        description=package["description"],

        payload=payload,

        currency="XTR",

        prices=[
            LabeledPrice(
                label=package["name"],
                amount=package["stars"],
            )
        ],

        # Para Stars, provider_token é omitido.
    )


# ============================================================
# ESCOLHA DO PACOTE
# ============================================================

async def handle_package_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    if not query:
        return

    package_id = query.data.split(
        ":",
        1,
    )[1]

    if package_id not in PACKAGES:
        await query.answer(
            text="Pacote inválido.",
            show_alert=True,
        )
        return

    save_user(update)

    if not gateway_pagamento:
        await query.answer(
            text="Liberando acesso..."
        )

        await grant_direct_access(
            update,
            context,
            package_id,
        )

        return

    await query.answer(
        text="Abrindo pagamento em Stars..."
    )

    try:
        await send_stars_invoice(
            update,
            context,
            package_id,
        )

    except Exception:
        logger.exception(
            "Erro ao gerar cobrança em Stars"
        )

        await query.message.reply_text(
            "Não foi possível abrir o pagamento "
            "em Stars agora."
        )


# ============================================================
# PRÉ-CHECKOUT
# ============================================================

async def pre_checkout(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.pre_checkout_query

    if not query:
        return

    with db() as conn:
        payment = conn.execute(
            """
            SELECT *
            FROM star_payments
            WHERE invoice_payload = ?
            """,
            (query.invoice_payload,),
        ).fetchone()

    if not payment:
        await query.answer(
            ok=False,
            error_message=(
                "Cobrança não encontrada."
            ),
        )
        return

    if payment["status"] != "pending":
        await query.answer(
            ok=False,
            error_message=(
                "Esta cobrança já foi processada."
            ),
        )
        return

    if query.currency != "XTR":
        await query.answer(
            ok=False,
            error_message="Moeda inválida.",
        )
        return

    if (
        query.total_amount
        != payment["stars_amount"]
    ):
        await query.answer(
            ok=False,
            error_message="Valor inválido.",
        )
        return

    if (
        query.from_user.id
        != payment["telegram_user_id"]
    ):
        await query.answer(
            ok=False,
            error_message=(
                "Esta cobrança pertence "
                "a outro usuário."
            ),
        )
        return

    await query.answer(ok=True)


# ============================================================
# PAGAMENTO CONFIRMADO
# ============================================================

async def successful_stars_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    successful_payment = (
        message.successful_payment
    )

    if not successful_payment:
        return

    with db() as conn:
        payment = conn.execute(
            """
            SELECT *
            FROM star_payments
            WHERE invoice_payload = ?
            """,
            (
                successful_payment.invoice_payload,
            ),
        ).fetchone()

        if not payment:
            logger.error(
                "Pagamento sem cobrança local: %s",
                successful_payment.invoice_payload,
            )
            return

        if payment["status"] == "paid":
            logger.info(
                "Pagamento já processado: %s",
                successful_payment.invoice_payload,
            )
            return

        if (
            payment["telegram_user_id"]
            != user.id
        ):
            logger.error(
                "Usuário divergente no pagamento"
            )
            return

        if (
            successful_payment.currency
            != "XTR"
        ):
            logger.error(
                "Moeda divergente no pagamento"
            )
            return

        if (
            successful_payment.total_amount
            != payment["stars_amount"]
        ):
            logger.error(
                "Valor divergente no pagamento"
            )
            return

        cursor = conn.execute(
            """
            UPDATE star_payments
            SET
                status = 'paid',

                telegram_payment_charge_id = ?,

                provider_payment_charge_id = ?,

                paid_at = ?

            WHERE id = ?
              AND status = 'pending'
            """,
            (
                successful_payment
                .telegram_payment_charge_id,

                successful_payment
                .provider_payment_charge_id,

                iso(utc_now()),

                payment["id"],
            ),
        )

        if cursor.rowcount != 1:
            logger.warning(
                "Pagamento não atualizado; "
                "provavelmente já processado."
            )
            return

    package = PACKAGES[
        payment["package_id"]
    ]

    expiration = activate_subscription(
        telegram_user_id=user.id,
        package_id=payment["package_id"],
        payment_id=payment["id"],
    )

    try:
        invite_link = await create_invite_link(
            context
        )

    except TelegramError:
        logger.exception(
            "Pagamento confirmado, mas o convite "
            "não pôde ser criado."
        )

        invite_link = None

    keyboard = None

    if invite_link:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="Entrar no canal",
                        url=invite_link,
                    )
                ]
            ]
        )

    await message.reply_text(
        "✅ Pagamento em Stars confirmado!\n\n"
        f"Pacote: {package['name']}\n"
        f"Valor: ⭐ {payment['stars_amount']} Stars\n"
        f"Acesso válido até "
        f"{expiration:%d/%m/%Y}.",
        reply_markup=keyboard,
    )


# ============================================================
# VOLTAR AOS PACOTES
# ============================================================

async def show_packages_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    if not query:
        return

    await query.answer()

    await query.message.reply_text(
        package_caption(),
        reply_markup=package_keyboard(),
    )


# ============================================================
# ERROS
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    logger.exception(
        "Erro não tratado durante atualização",
        exc_info=context.error,
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não configurado "
            "em settings.py"
        )
    validate_packages()
    init_db()

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "pacotes",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status,
        )
    )

    application.add_handler(
        CommandHandler(
            "paysupport",
            paysupport,
        )
    )

    application.add_handler(
        CommandHandler(
            "meuid",
            meu_id,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            handle_package_choice,
            pattern=r"^package:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            show_packages_callback,
            pattern=r"^packages$",
        )
    )

    application.add_handler(
        PreCheckoutQueryHandler(
            pre_checkout
        )
    )

    application.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_stars_payment,
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Bot iniciado em modo polling"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
