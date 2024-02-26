import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext, filters
from aiogram.dispatcher.filters.state import State, StatesGroup
import sqlite3

from config import config


bot = Bot(token=config)
dp = Dispatcher(bot)

# Подключение к базе данных SQLite
conn = sqlite3.connect('bank_bot.db')
cursor = conn.cursor()


cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 1000, 
        number_balanse INTEGER
        
    )
''')
conn.commit()

storage = MemoryStorage()
dp.storage = storage
start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('/balance')).add(KeyboardButton('/transfer'))

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        cursor.execute('INSERT INTO users (user_id, username, number_balanse) VALUES (?, ?, ?)', (user_id, message.from_user.username, message.from_user.id))
        conn.commit()

   
    user_info = f"Ваш номер счет: {message.from_user.id}\n"
    user_info += f"Никнейм: {message.from_user.username}"

    # Отправка чека о пользователе
    await message.answer(f"Информация о вас .\n\n{user_info}", reply_markup=start_keyboard)


    await message.answer("Привет! Этот бот Оптима банк \n/balanse вы можете посмотреть балланс \n/depozit вы можете паполнить баланс \n/transfer вы можете перевести на другой счет ", reply_markup=start_keyboard)


@dp.message_handler(commands=['balance'])
async def cmd_balance(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    balance = cursor.fetchone()
    
    if balance:
        await message.answer(f"Твой текущий баланс: {balance[0]}")
    else:
        await message.answer("У тебя нет счета. Для создания счета используй команду /start")
        
class AmountTrasfer(StatesGroup):
    amount = State()
    money = State()

@dp.message_handler(state=AmountTrasfer.amount)
async def deposit_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    balance = cursor.fetchone()[0]

    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной.")
        
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        
        await message.answer(f"Баланс успешно пополнен на {amount}")

    except ValueError as e:
        await message.answer(f"Ошибка: {e}")
        await state.finish()


class TransferState(StatesGroup):
    amount = State()
    recipient_balance = State()


@dp.message_handler(commands=['transfer'])
async def transfer_command(message: types.Message):
    await message.answer('Введите сумму перевода:')
    await TransferState.amount.set()

@dp.message_handler(state=TransferState.amount)
async def transfer_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной.")

        # Сохраняем сумму в состояние
        await state.update_data(amount=amount)

        # Запрашиваем номер счета получателя
        await message.answer('Введите номер счета получателя:')
        await TransferState.recipient_balance.set()

    except ValueError as e:
        await message.answer(f"Ошибка: {e}")
        await state.finish()

@dp.message_handler(state=TransferState.recipient_balance)
async def transfer_recipient(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Получаем номер счета получателя из сообщения
    recipient_account_number = message.text

    # Проверяем, существует ли пользователь с таким номером счета
    cursor.execute('SELECT user_id, balance FROM users WHERE number_balanse = ?', (recipient_account_number,))
    recipient_data = cursor.fetchone()

    if not recipient_data:
        await message.answer("Пользователь с таким номером счета не найден.")
        await state.finish()
        return

    recipient_id, recipient_balance = recipient_data

    # Получаем сумму из состояния
    data = await state.get_data()
    amount = data.get('amount', 0)

    # Проверяем, достаточно ли у пользователя средств
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    sender_balance = cursor.fetchone()[0]

    if sender_balance < amount:
        await message.answer("Недостаточно средств для перевода.")
        await state.finish()
        return

    # Обновляем балансы отправителя и получателя
    cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, recipient_id))
    conn.commit()

    await message.answer(f"Перевод успешно выполнен. Остаток на счете: {sender_balance - amount}")
    await state.finish()


executor.start_polling(dp)       