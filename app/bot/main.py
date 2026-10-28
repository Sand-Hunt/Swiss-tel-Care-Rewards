import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from sqlalchemy import select
from datetime import datetime, UTC
from .handlers import router
from ..config import get_settings
from ..db import init_db
from ..seed import seed_demo_data
from ..db import SessionLocal
from ..services import backfill_review_links
from ..models import Notification, Employee


async def deliver_notifications(bot: Bot) -> None:
    while True:
        try:
            async with SessionLocal() as db:
                pending = (await db.scalars(select(Notification).where(Notification.delivered_at == None).order_by(Notification.id))).all()
                for notification in pending:
                    employee = await db.get(Employee, notification.employee_id)
                    if employee:
                        try:
                            await bot.send_message(employee.telegram_id, notification.text)
                            notification.delivered_at = datetime.now(UTC).replace(tzinfo=None)
                        except Exception:
                            continue
                await db.commit()
        except Exception:
            pass
        await asyncio.sleep(15)


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token or settings.bot_token == 'replace-with-your-token':
        raise RuntimeError(
            'BOT_TOKEN не задан или оставлен placeholder. Создайте файл .env '
            'из .env.example и замените BOT_TOKEN на токен, полученный у @BotFather.'
        )
    await init_db()
    await seed_demo_data()
    async with SessionLocal() as db:
        await backfill_review_links(db)
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command='start', description='Главное меню'),
        BotCommand(command='help', description='Справка'),
        BotCommand(command='register', description='Регистрация сотрудника'),
    ])
    asyncio.create_task(deliver_notifications(bot))
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
