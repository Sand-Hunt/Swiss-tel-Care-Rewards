from io import BytesIO

import qrcode
from aiogram import F, Router
from aiogram.types import BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import select
from ..config import get_settings
from ..db import SessionLocal
from ..models import AdaptationSurvey, Employee, EmployeeIssue, EmployeeRole, IssueStatus, Reward, Task, TaskCompletion, Redemption, CleaningMark, Notification, GuestReview
from ..services import complete_task, redeem_reward, register_employee
from ..locations import normalize_location

router = Router()


class Registration(StatesGroup):
    full_name = State()
    department = State()


class IssueForm(StatesGroup):
    category = State()
    text = State()


class Survey(StatesGroup):
    comfort = State()
    support = State()
    comment = State()


class CleaningForm(StatesGroup):
    location = State()
    note = State()


def main_menu(role: str = EmployeeRole.EMPLOYEE.value) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text='👤 Мой профиль'), KeyboardButton(text='🎯 Задания')],
            [KeyboardButton(text='🎁 Награды'), KeyboardButton(text='🎟️ Мои награды')],
            [KeyboardButton(text='🧭 Адаптация'), KeyboardButton(text='🆘 Сообщить о проблеме')],
            [KeyboardButton(text='🧹 Отметить уборку'), KeyboardButton(text='💬 Мои отзывы')],
            [KeyboardButton(text='📱 Мой QR')]]
    if role in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        rows.append([KeyboardButton(text='📋 Проблемы команды'), KeyboardButton(text='📱 QR персонала')])
        rows.append([KeyboardButton(text='💬 Отзывы гостей')])
        rows.append([KeyboardButton(text='🎟️ Выдать награды')])
    if role == EmployeeRole.ADMIN.value:
        rows.append([KeyboardButton(text='⚙️ Администрирование')])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def employee_for(user_id: int) -> Employee | None:
    async with SessionLocal() as db:
        return await db.scalar(select(Employee).where(Employee.telegram_id == user_id))


@router.message(CommandStart())
async def start(message: Message):
    employee = await employee_for(message.from_user.id)
    role = employee.role if employee else EmployeeRole.EMPLOYEE.value
    if employee:
        await message.answer(f'Добро пожаловать, {employee.full_name}! Выберите раздел:', reply_markup=main_menu(role))
    else:
        await message.answer('Добро пожаловать в Swissôtel Care & Rewards!\nСначала зарегистрируйтесь командой /register.', reply_markup=main_menu())


@router.message(Command('help'))
async def help_command(message: Message):
    await message.answer('Команды:\n/register — регистрация\n/start — главное меню\n\nВ разделах меню доступны задания, баллы, адаптация и обращение о проблеме.')


@router.message(Command('register'))
async def register(message: Message, state: FSMContext):
    if await employee_for(message.from_user.id):
        await message.answer('Вы уже зарегистрированы. Используйте главное меню.')
        return
    await state.set_state(Registration.full_name)
    await message.answer('Введите ваше ФИО полностью:')


@router.message(Registration.full_name)
async def reg_name(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer('Введите корректное ФИО.')
        return
    await state.update_data(full_name=message.text.strip())
    await state.set_state(Registration.department)
    await message.answer('Введите отдел (например: Housekeeping, Front Office, Ресторан):')


@router.message(Registration.department)
async def reg_department(message: Message, state: FSMContext):
    name = (await state.get_data()).get('full_name')
    department = message.text.strip() if message.text else 'Общий'
    async with SessionLocal() as db:
        role = EmployeeRole.ADMIN.value if message.from_user.id in get_settings().admin_ids else EmployeeRole.EMPLOYEE.value
        employee = await register_employee(db, message.from_user.id, name, department)
        if employee:
            employee.role = role
            await db.commit()
    await state.clear()
    await message.answer('Регистрация завершена! Добро пожаловать в систему.', reply_markup=main_menu(role))


@router.message(F.text == '👤 Мой профиль')
async def profile(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.')
        return
    await message.answer(f'👤 {employee.full_name}\nОтдел: {employee.department}\nРоль: {employee.role}\n⭐ Баллы: {employee.points}')


@router.message(F.text == '🎯 Задания')
async def tasks(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.')
        return
    async with SessionLocal() as db:
        active_tasks = (await db.scalars(select(Task).where(Task.active == True).order_by(Task.id))).all()
        completed_ids = set((await db.scalars(select(TaskCompletion.task_id).where(TaskCompletion.employee_id == employee.id))).all())
    pending = [task for task in active_tasks if task.id not in completed_ids]
    buttons = [[InlineKeyboardButton(text=f'✅ {task.title} — {task.points} б.', callback_data=f'task:{task.id}')] for task in pending]
    if pending:
        buttons.append([InlineKeyboardButton(text='🏁 Отметить всё выполненным', callback_data='tasks:all')])
    if active_tasks:
        await message.answer(
            f'Задания: выполнено {len(active_tasks) - len(pending)} из {len(active_tasks)}.\n'
            'Нажмите «Отметить выполненным», чтобы получить баллы.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
        )
    else:
        await message.answer('Активных заданий пока нет.')


@router.callback_query(F.data.startswith('task:'))
async def complete(callback: CallbackQuery):
    employee = await employee_for(callback.from_user.id)
    if not employee:
        await callback.answer('Сначала зарегистрируйтесь', show_alert=True)
        return
    task_id = int(callback.data.split(':')[1])
    async with SessionLocal() as db:
        ok, text = await complete_task(db, employee.id, task_id)
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data == 'tasks:all')
async def complete_all(callback: CallbackQuery):
    employee = await employee_for(callback.from_user.id)
    if not employee:
        await callback.answer('Сначала зарегистрируйтесь', show_alert=True)
        return
    awarded = 0
    async with SessionLocal() as db:
        pending_tasks = (await db.scalars(select(Task).where(Task.active == True))).all()
        for task in pending_tasks:
            ok, text = await complete_task(db, employee.id, task.id)
            if ok and 'Начислено' in text:
                awarded += task.points
    await callback.answer(f'Все доступные задания обработаны. Начислено: {awarded} баллов.', show_alert=True)


@router.message(F.text == '🎁 Награды')
async def rewards(message: Message):
    async with SessionLocal() as db:
        rewards = (await db.scalars(select(Reward).where(Reward.active == True).order_by(Reward.id))).all()
    employee = await employee_for(message.from_user.id)
    buttons = [[InlineKeyboardButton(text=f'{r.name} — {r.cost} б.', callback_data=f'reward:{r.id}') ] for r in rewards if r.stock > 0]
    balance = employee.points if employee else 0
    await message.answer(f'Баланс: {balance}\nВыберите награду:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None)


@router.callback_query(F.data.startswith('reward:'))
async def redeem(callback: CallbackQuery):
    employee = await employee_for(callback.from_user.id)
    if not employee:
        await callback.answer('Сначала зарегистрируйтесь', show_alert=True)
        return
    reward_id = int(callback.data.split(':')[1])
    async with SessionLocal() as db:
        ok, text = await redeem_reward(db, employee.id, reward_id, f'telegram:{callback.from_user.id}:{callback.message.message_id}:{reward_id}')
    await callback.answer(text, show_alert=True)


def employee_qr_payload(employee: Employee) -> str:
    username = get_settings().bot_username.strip().lstrip('@')
    if username:
        return f'https://t.me/{username}?start=staff_{employee.id}'
    return f'swissotel://employee/{employee.id}'


def make_qr_image(payload: str) -> BufferedInputFile:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color='#1c1c1c', back_color='white').get_image()
    output = BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    return BufferedInputFile(output.read(), filename='swissotel-personnel-qr.png')


@router.message(F.text == '📱 Мой QR')
async def own_qr(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.')
        return
    await message.answer_photo(make_qr_image(employee_qr_payload(employee)), caption=f'QR сотрудника: {employee.full_name}\nТабельный ID: {employee.id}')


@router.message(F.text == '📱 QR персонала')
async def personnel_qr(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee or employee.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await message.answer('Недостаточно прав.')
        return
    async with SessionLocal() as db:
        staff = (await db.scalars(select(Employee).where(Employee.active == True).order_by(Employee.full_name))).all()
    buttons = [[InlineKeyboardButton(text=f'{person.full_name} (ID {person.id})', callback_data=f'staffqr:{person.id}')] for person in staff]
    await message.answer('Выберите сотрудника для создания QR-кода:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith('staffqr:'))
async def personnel_qr_generate(callback: CallbackQuery):
    manager = await employee_for(callback.from_user.id)
    if not manager or manager.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await callback.answer('Недостаточно прав.', show_alert=True)
        return
    employee_id = int(callback.data.split(':')[1])
    async with SessionLocal() as db:
        employee = await db.get(Employee, employee_id)
    if not employee:
        await callback.answer('Сотрудник не найден.', show_alert=True)
        return
    await callback.message.answer_photo(make_qr_image(employee_qr_payload(employee)), caption=f'QR сотрудника: {employee.full_name}\nТабельный ID: {employee.id}')
    await callback.answer('QR-код создан')


@router.message(F.text == '🧹 Отметить уборку')
async def cleaning_start(message: Message, state: FSMContext):
    if not await employee_for(message.from_user.id):
        await message.answer('Сначала выполните /register.')
        return
    await state.set_state(CleaningForm.location)
    await message.answer('Где выполнена уборка? Например: «Номер 12», «Сауна», «Коридор 3 этажа».')


@router.message(CleaningForm.location)
async def cleaning_location(message: Message, state: FSMContext):
    location = (message.text or '').strip()
    if len(location) < 2:
        await message.answer('Укажите место уборки текстом, например: «Номер 12».')
        return
    await state.update_data(location=normalize_location(location)[:100])
    await state.set_state(CleaningForm.note)
    await message.answer('Комментарий к уборке? Можно написать кратко, или отправьте «-».')


@router.message(CleaningForm.note)
async def cleaning_save(message: Message, state: FSMContext):
    employee = await employee_for(message.from_user.id)
    data = await state.get_data()
    note = (message.text or '').strip()
    if note == '-':
        note = ''
    async with SessionLocal() as db:
        db.add(CleaningMark(employee_id=employee.id, location=data['location'], note=note[:500], points=0))
        await db.commit()
    await state.clear()
    await message.answer(f'✅ Уборка отмечена: {data["location"]}. Отзывы гостей будут привязаны к вам до следующей уборки в этом месте.')


@router.message(F.text == '💬 Мои отзывы')
async def my_reviews(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.')
        return
    async with SessionLocal() as db:
        reviews = (await db.scalars(select(GuestReview).where(GuestReview.employee_id == employee.id).order_by(GuestReview.created_at.desc()).limit(20))).all()
    if not reviews:
        await message.answer('Отзывов, привязанных к вашей уборке, пока нет.')
        return
    lines = []
    for review in reviews:
        text = review.comment.replace('\n', ' ')[:180]
        lines.append(f'📅 {review.created_at.strftime("%d.%m.%Y %H:%M")}\n📍 {review.room_number}\n⭐ {review.rating}/5 — {text}')
    await message.answer('\n\n'.join(lines))


@router.message(F.text == '🆘 Сообщить о проблеме')
async def issue_start(message: Message, state: FSMContext):
    await state.set_state(IssueForm.category)
    await message.answer('Категория проблемы? Например: оборудование, обслуживание, коллектив, безопасность.')


@router.message(IssueForm.category)
async def issue_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text[:50] if message.text else 'Другое')
    await state.set_state(IssueForm.text)
    await message.answer('Опишите проблему подробно:')


@router.message(IssueForm.text)
async def issue_text(message: Message, state: FSMContext):
    employee = await employee_for(message.from_user.id)
    data = await state.get_data()
    if not employee:
        await message.answer('Сначала выполните /register.')
        await state.clear(); return
    async with SessionLocal() as db:
        db.add(EmployeeIssue(employee_id=employee.id, category=data['category'], text=message.text[:3000] if message.text else ''))
        await db.commit()
    await state.clear()
    await message.answer('Обращение принято. Мы свяжемся с вами при необходимости.')


@router.message(F.text == '🎟️ Мои награды')
async def my_rewards(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.')
        return
    async with SessionLocal() as db:
        redemptions = (await db.scalars(
            select(Redemption).where(Redemption.employee_id == employee.id).order_by(Redemption.created_at.desc())
        )).all()
        lines_pending = []
        lines_received = []
        for redemption in redemptions:
            reward = await db.get(Reward, redemption.reward_id)
            if not reward:
                continue
            line = f'• {reward.name} — списано {reward.cost} б. ({redemption.created_at.strftime("%d.%m.%Y")})'
            if redemption.status == 'received':
                lines_received.append(line)
            else:
                lines_pending.append(line)
    text = '⏳ Ожидают получения:\n' + ('\n'.join(lines_pending) if lines_pending else 'Нет наград в ожидании.')
    text += '\n\n✅ Получены:\n' + ('\n'.join(lines_received) if lines_received else 'Полученных наград пока нет.')
    await message.answer(text)


@router.message(F.text == '🎟️ Выдать награды')
async def issue_rewards(message: Message):
    manager = await employee_for(message.from_user.id)
    if not manager or manager.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await message.answer('Недостаточно прав.')
        return
    async with SessionLocal() as db:
        pending = (await db.scalars(
            select(Redemption).where(Redemption.status == 'pending').order_by(Redemption.created_at)
        )).all()
        buttons = []
        for redemption in pending:
            employee = await db.get(Employee, redemption.employee_id)
            reward = await db.get(Reward, redemption.reward_id)
            if employee and reward:
                buttons.append([InlineKeyboardButton(
                    text=f'{employee.full_name}: {reward.name}',
                    callback_data=f'rewardissued:{redemption.id}',
                )])
    if not buttons:
        await message.answer('Нет наград, ожидающих выдачи.')
        return
    await message.answer(
        'Выберите награду, которую уже выдали сотруднику:',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith('rewardissued:'))
async def mark_reward_received(callback: CallbackQuery):
    manager = await employee_for(callback.from_user.id)
    if not manager or manager.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await callback.answer('Недостаточно прав.', show_alert=True)
        return
    redemption_id = int(callback.data.split(':')[1])
    async with SessionLocal() as db:
        redemption = await db.get(Redemption, redemption_id)
        if not redemption or redemption.status == 'received':
            await callback.answer('Эта награда уже выдана или заявка не найдена.', show_alert=True)
            return
        redemption.status = 'received'
        await db.commit()
    await callback.answer('Награда отмечена как полученная.', show_alert=True)
    await callback.message.edit_text('✅ Награда выдана и отмечена как полученная.')


@router.message(F.text == '🧭 Адаптация')
async def survey_start(message: Message, state: FSMContext):
    employee = await employee_for(message.from_user.id)
    if not employee:
        await message.answer('Сначала выполните /register.'); return
    await state.set_state(Survey.comfort)
    await message.answer('Опрос адаптации, вопрос 1 из 3:\nНасколько удобно вам работать? Введите оценку от 1 до 5.')


@router.message(Survey.comfort)
async def survey_comfort(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or not 1 <= int(message.text) <= 5:
        await message.answer('Введите число от 1 до 5.'); return
    await state.update_data(comfort=int(message.text))
    await state.set_state(Survey.support)
    await message.answer('Вопрос 2 из 3:\nНасколько хорошо вы понимаете процессы? Введите оценку от 1 до 5.')


@router.message(Survey.support)
async def survey_support(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or not 1 <= int(message.text) <= 5:
        await message.answer('Введите число от 1 до 5.'); return
    await state.update_data(support=int(message.text))
    await state.set_state(Survey.comment)
    await message.answer('Вопрос 3 из 3:\nНужна ли вам дополнительная поддержка? Напишите ответ.')


@router.message(Survey.comment)
async def survey_comment(message: Message, state: FSMContext):
    employee = await employee_for(message.from_user.id)
    data = await state.get_data()
    answers = {'comfort': data['comfort'], 'support': data['support'], 'support_needed': message.text or ''}
    async with SessionLocal() as db:
        db.add(AdaptationSurvey(employee_id=employee.id, answers=str(answers), score=data['comfort'] + data['support']))
        await db.commit()
    await state.clear()
    await message.answer('Спасибо! Опрос адаптации сохранён.')


@router.message(F.text == '💬 Отзывы гостей')
async def guest_reviews_manager(message: Message):
    manager = await employee_for(message.from_user.id)
    if not manager or manager.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await message.answer('Недостаточно прав.')
        return
    async with SessionLocal() as db:
        reviews = (await db.scalars(select(GuestReview).order_by(GuestReview.created_at.desc()).limit(30))).all()
    if not reviews:
        await message.answer('Отзывы гостей пока не поступали.')
        return
    await message.answer('\n\n'.join(
        f'📅 {review.created_at.strftime("%d.%m.%Y %H:%M")}\n'
        f'📍 {normalize_location(review.room_number)}\n⭐ {review.rating}/5\n'
        f'Комментарий: {review.comment}'
        for review in reviews
    ))


@router.message(F.text == '📋 Проблемы команды')
async def issues(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee or employee.role not in (EmployeeRole.MANAGER.value, EmployeeRole.ADMIN.value):
        await message.answer('Недостаточно прав.'); return
    async with SessionLocal() as db:
        issues = (await db.scalars(select(EmployeeIssue).order_by(EmployeeIssue.id.desc()).limit(20))).all()
    text = '\n\n'.join(f'#{i.id} [{i.status}] {i.category}: {i.text}' for i in issues)
    await message.answer(text or 'Новых обращений нет.')


@router.message(F.text == '⚙️ Администрирование')
async def admin(message: Message):
    employee = await employee_for(message.from_user.id)
    if not employee or employee.role != EmployeeRole.ADMIN.value:
        await message.answer('Недостаточно прав.')
        return
    async with SessionLocal() as db:
        staff = (await db.scalars(select(Employee).order_by(Employee.full_name))).all()
    buttons = [[InlineKeyboardButton(text=f'{person.full_name} — {person.role}', callback_data=f'roleuser:{person.id}')] for person in staff]
    await message.answer(
        f'Администрирование. Пользователей: {len(staff)}. Выберите сотрудника для изменения роли:',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
    )


@router.callback_query(F.data.startswith('roleuser:'))
async def admin_choose_role(callback: CallbackQuery):
    admin = await employee_for(callback.from_user.id)
    if not admin or admin.role != EmployeeRole.ADMIN.value:
        await callback.answer('Недостаточно прав.', show_alert=True)
        return
    user_id = int(callback.data.split(':')[1])
    async with SessionLocal() as db:
        user = await db.get(Employee, user_id)
    if not user:
        await callback.answer('Пользователь не найден.', show_alert=True)
        return
    buttons = [[
        InlineKeyboardButton(text='Персонал', callback_data=f'roleset:{user.id}:employee'),
        InlineKeyboardButton(text='Руководитель', callback_data=f'roleset:{user.id}:manager'),
        InlineKeyboardButton(text='Администратор', callback_data=f'roleset:{user.id}:admin'),
    ]]
    await callback.message.edit_text(f'{user.full_name}\nТекущая роль: {user.role}\nВыберите новую роль:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith('roleset:'))
async def admin_set_role(callback: CallbackQuery):
    admin = await employee_for(callback.from_user.id)
    if not admin or admin.role != EmployeeRole.ADMIN.value:
        await callback.answer('Недостаточно прав.', show_alert=True)
        return
    _, user_id, role = callback.data.split(':')
    if role not in ('employee', 'manager', 'admin'):
        await callback.answer('Недопустимая роль.', show_alert=True)
        return
    async with SessionLocal() as db:
        user = await db.get(Employee, int(user_id))
        if not user:
            await callback.answer('Пользователь не найден.', show_alert=True)
            return
        user.role = role
        await db.commit()
    await callback.answer('Роль обновлена.', show_alert=True)
    await callback.message.edit_text(f'✅ Роль пользователя обновлена: {role}')
