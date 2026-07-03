#!/usr/bin/env python3

import asyncio
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

from settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", BASE_DIR / "subscriptions.db")
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("expire-subscriptions")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@contextmanager
def db():
    connection = sqlite3.connect(DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_expired_subscriptions() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            """
            SELECT
                s.telegram_user_id,
                s.package_id,
                s.expires_at,
                u.telegram_chat_id
            FROM subscriptions AS s
            JOIN users AS u
              ON u.telegram_user_id = s.telegram_user_id
            WHERE s.status = 'active'
              AND s.expires_at <= ?
            ORDER BY s.expires_at
            """,
            (iso(utc_now()),),
        ).fetchall()


def mark_as_expired(telegram_user_id: int) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET status = 'expired',
                updated_at = ?
            WHERE telegram_user_id = ?
              AND status = 'active'
            """,
            (
                iso(utc_now()),
                telegram_user_id,
            ),
        )


async def remove_user_from_channel(
    bot: Bot,
    telegram_user_id: int,
) -> None:
    await bot.ban_chat_member(
        chat_id=TELEGRAM_CHANNEL_ID,
        user_id=telegram_user_id,
        revoke_messages=False,
    )

    # O unban após o ban remove o usuário, mas permite que ele volte
    # futuramente usando um novo convite depois da renovação.
    await bot.unban_chat_member(
        chat_id=TELEGRAM_CHANNEL_ID,
        user_id=telegram_user_id,
        only_if_banned=True,
    )


async def notify_user(
    bot: Bot,
    chat_id: int,
) -> None:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "Sua assinatura venceu e o acesso ao canal foi encerrado.\n\n"
                "Use /pacotes para renovar."
            ),
        )
    except TelegramError:
        logger.exception(
            "Não foi possível avisar o usuário no chat %s",
            chat_id,
        )


async def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não configurado em settings.py")
        return 1

    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID não configurado em settings.py")
        return 1

    if not DATABASE_PATH.exists():
        logger.error("Banco SQLite não encontrado: %s", DATABASE_PATH)
        return 1

    expired = get_expired_subscriptions()

    if not expired:
        logger.info("Nenhuma assinatura vencida encontrada.")
        return 0

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    removed = 0
    failed = 0

    async with bot:
        for subscription in expired:
            telegram_user_id = subscription["telegram_user_id"]

            try:
                await remove_user_from_channel(
                    bot,
                    telegram_user_id,
                )

                mark_as_expired(telegram_user_id)

                await notify_user(
                    bot,
                    subscription["telegram_chat_id"],
                )

                removed += 1
                logger.info(
                    "Usuário %s removido. Vencimento: %s",
                    telegram_user_id,
                    subscription["expires_at"],
                )

            except TelegramError:
                failed += 1
                logger.exception(
                    "Erro do Telegram ao remover usuário %s",
                    telegram_user_id,
                )

            except Exception:
                failed += 1
                logger.exception(
                    "Erro inesperado ao remover usuário %s",
                    telegram_user_id,
                )

    logger.info(
        "Processamento concluído: encontrados=%s removidos=%s falhas=%s",
        len(expired),
        removed,
        failed,
    )

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
