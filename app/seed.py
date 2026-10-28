from sqlalchemy import select
from .db import SessionLocal
from .models import Employee, EmployeeRole, Reward, Task


async def seed_demo_data():
    async with SessionLocal() as session:
        existing_employee = await session.scalar(select(Employee).limit(1))
        if not existing_employee:
            session.add_all([
                Employee(telegram_id=100000001, full_name='Анна Иванова', department='Ресторан', points=120),
                Employee(telegram_id=100000002, full_name='Иван Петров', department='Front Office', role=EmployeeRole.MANAGER.value, points=250),
                Employee(telegram_id=100000003, full_name='Мария Сидорова', department='Housekeeping', points=80),
            ])
        existing_task = await session.scalar(select(Task).limit(1))
        if not existing_task:
            session.add_all([
                Task(title='Приветствие гостя', description='Поздоровайтесь с гостем лично и по имени.', points=10),
                Task(title='Замечено улучшение', description='Предложите и внедрите улучшение в своей зоне.', points=25),
                Task(title='Помощь коллегам', description='Поддержите коллегу в смене.', points=15),
            ])
        legacy_reward_costs = {
            'Кофе с коллегами': 120,
            'Дополнительный выходной': 2000,
            'Фирменная кружка': 320,
        }
        for name, cost in legacy_reward_costs.items():
            legacy_reward = await session.scalar(select(Reward).where(Reward.name == name))
            if legacy_reward is not None:
                legacy_reward.cost = cost

        rewards = [
            Reward(name='☕ Кофе с коллегами', description='Напиток в кофейне отеля', cost=120, stock=30),
            Reward(name='🍫 Небольшой подарок', description='Шоколад или сладкий набор', cost=180, stock=25),
            Reward(name='🍱 Обед от шеф-повара', description='Ланч по меню сотрудников отеля', cost=480, stock=12),
            Reward(name='🎟️ Spa-скидка 20%', description='Скидка на услуги wellness-центра', cost=720, stock=15),
            Reward(name='🏨 Номерной сертификат', description='Сертификат на проживание согласно правилам отеля', cost=2800, stock=3),
            Reward(name='🎂 Подарок ко дню рождения', description='Именной подарок и праздничный торт', cost=1000, stock=10),
            Reward(name='🏅 Награда за стаж 1 год', description='Фирменный подарок за год работы', cost=1600, stock=8),
            Reward(name='🌟 Привилегия раннего сменового отбора', description='Приоритетный выбор смены на неделю', cost=1200, stock=5),
            Reward(name='📚 Учебный курс отеля', description='Оплата внутреннего курса повышения квалификации', cost=1400, stock=8),
            Reward(name='🌴 Дополнительный выходной', description='Дополнительный выходной по согласованию с руководителем', cost=2000, stock=2),
            Reward(name='☕ Фирменная кружка Swissôtel', description='Кружка и набор кофе Swissôtel', cost=320, stock=10),
        ]
        for reward in rewards:
            existing_reward = await session.scalar(select(Reward).where(Reward.name == reward.name))
            if existing_reward is None:
                session.add(reward)
            else:
                existing_reward.cost = reward.cost
        await session.commit()
