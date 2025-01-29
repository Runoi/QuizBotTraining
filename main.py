import aiosqlite
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram import F
import qfile

# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)

# Замените "YOUR_BOT_TOKEN" на токен, который вы получили от BotFather
API_TOKEN = '7789668630:AAGSlEkV_y1k9j7SsOP5_tXXLMZNGCivyCE'

# Объект бота
bot = Bot(token=API_TOKEN)
# Диспетчер
dp = Dispatcher()

# Зададим имя базы данных
DB_NAME = 'quiz_bot.db'


# Структура квиза
quiz_data = qfile.question_file('question.json')

def generate_options_keyboard(answer_options, right_answer):
    builder = InlineKeyboardBuilder()

    for option in answer_options:
        builder.add(types.InlineKeyboardButton(
            text=option,
            callback_data="right_answer" if option == right_answer else "wrong_answer")
        )
        

    builder.adjust(1)
    return builder.as_markup()


@dp.callback_query(F.data.in_({"right_answer", "wrong_answer"}))
async def handle_answer(callback: types.CallbackQuery):
    # Получаем текст нажатой кнопки
    user_answer = None
    for row in callback.message.reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback.data:
                user_answer = button.text
                break
        if user_answer:
            break

    # Убираем клавиатуру после выбора ответа
    await callback.bot.edit_message_reply_markup(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        reply_markup=None
    )

    # Получаем текущий вопрос и правильный ответ
    current_question_index = await get_quiz_index(callback.from_user.id)
    correct_option = quiz_data[current_question_index]['correct_option']
    correct_answer = quiz_data[current_question_index]['options'][correct_option]

    # Выводим ответ пользователя
    if callback.data == "right_answer":
        await callback.message.answer(f"Вы выбрали: {user_answer}\nВерно!")
    else:
        await callback.message.answer(f"Вы выбрали: {user_answer}\nНеправильно. Правильный ответ: {correct_answer}")

    # Обновляем индекс вопроса
    current_question_index += 1
    await update_quiz_index(callback.from_user.id, current_question_index)

    # Переход к следующему вопросу или завершение квиза
    if current_question_index < len(quiz_data):
        await get_question(callback.message, callback.from_user.id)
    else:
        # Квиз завершен, обновляем результаты пользователя
        username = callback.from_user.username or callback.from_user.first_name
        score = current_question_index  # Количество правильных ответов
        await update_leaderboard(callback.from_user.id, username, score)

        # Выводим таблицу лидеров
        await show_leaderboard(callback.message)
        await callback.message.answer("Это был последний вопрос. Квиз завершен!")

# Хэндлер на команду /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Начать игру"))
    await message.answer("Добро пожаловать в квиз!", reply_markup=builder.as_markup(resize_keyboard=True))


async def get_question(message, user_id):

    # Получение текущего вопроса из словаря состояний пользователя
    current_question_index = await get_quiz_index(user_id)
    correct_index = quiz_data[current_question_index]['correct_option']
    opts = quiz_data[current_question_index]['options']
    kb = generate_options_keyboard(opts, opts[correct_index])
    await message.answer(f"{quiz_data[current_question_index]['question']}", reply_markup=kb)


async def new_quiz(message):
    user_id = message.from_user.id
    current_question_index = 0
    await update_quiz_index(user_id, current_question_index)
    await get_question(message, user_id)


async def get_quiz_index(user_id):
     # Подключаемся к базе данных
     async with aiosqlite.connect(DB_NAME) as db:
        # Получаем запись для заданного пользователя
        async with db.execute('SELECT question_index FROM quiz_state WHERE user_id = (?)', (user_id, )) as cursor:
            # Возвращаем результат
            results = await cursor.fetchone()
            if results is not None:
                return results[0]
            else:
                return 0


async def update_quiz_index(user_id, index):
    # Создаем соединение с базой данных (если она не существует, она будет создана)
    async with aiosqlite.connect(DB_NAME) as db:
        # Вставляем новую запись или заменяем ее, если с данным user_id уже существует
        await db.execute('INSERT OR REPLACE INTO quiz_state (user_id, question_index) VALUES (?, ?)', (user_id, index))
        # Сохраняем изменения
        await db.commit()


# Хэндлер на команду /quiz
@dp.message(F.text=="Начать игру")
@dp.message(Command("quiz"))
async def cmd_quiz(message: types.Message):

    await message.answer(f"Давайте начнем квиз!")
    await new_quiz(message)

@dp.message(Command("leaderboard"))
async def cmd_leaderboard(message: types.Message):
    # Выводим таблицу лидеров
    await show_leaderboard(message)

async def create_table():
    # Создаем соединение с базой данных (если она не существует, она будет создана)
    async with aiosqlite.connect(DB_NAME) as db:
        # Создаем таблицу
        await db.execute('''CREATE TABLE IF NOT EXISTS quiz_state (user_id INTEGER PRIMARY KEY, question_index INTEGER)''')
        # Создаем таблицу для лидеров
        await db.execute('''CREATE TABLE IF NOT EXISTS leaderboard (user_id INTEGER PRIMARY KEY, username TEXT, score INTEGER)''')
        # Сохраняем изменения
        await db.commit()

async def update_leaderboard(user_id: int, username: str, score: int):
    async with aiosqlite.connect(DB_NAME) as db:
        # Вставляем или обновляем запись в таблице лидеров
        await db.execute('''INSERT OR REPLACE INTO leaderboard (user_id, username, score)
                            VALUES (?, ?, ?)''', (user_id, username, score))
        await db.commit()

async def show_leaderboard(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        # Получаем топ-10 пользователей
        async with db.execute('''SELECT username, score FROM leaderboard
                                 ORDER BY score DESC LIMIT 10''') as cursor:
            leaders = await cursor.fetchall()

    # Формируем сообщение с таблицей лидеров
    leaderboard_message = "🏆 Таблица лидеров:\n"
    for i, (username, score) in enumerate(leaders, start=1):
        leaderboard_message += f"{i}. {username}: {score} очков\n"

    # Отправляем сообщение
    await message.answer(leaderboard_message)



# Запуск процесса поллинга новых апдейтов
async def main():

    # Запускаем создание таблицы базы данных
    await create_table()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())