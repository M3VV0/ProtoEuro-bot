import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from database import ProtoeuroBotDatabase
from entities.application import (
    Application,
    ApplicationForm,
    _normalize_country_name,
    get_country_flag,
    parse_time,
    validate_country_name,
    validate_youtube_video_link,
)
from entities.herald import HeraldForm
from entities.points_table import PointsTable
from utils import (
    ADMIN_IDS,
    ADMIN_TAG,
    BOT_TOKEN,
    CEO,
    DB_NAME,
    get_message_text,
    get_user_id,
    load_text,
    none_user_id_message,
    send_message,
    send_to_users,
)

applications_stage_router = Router(name="applications_stage")
finalize_applications_router = Router(name="finalize_applications")
voting_stage_router = Router(name="voting_stage")
finalization_stage_router = Router(name="finalization_stage")
admin_router = Router(name="admin")
protoeuro_db = ProtoeuroBotDatabase(DB_NAME)
points_table = None

class ActiveStage(BaseFilter):
    def __init__(self, expected_stage: str) -> None:
        self.expected_stage = expected_stage

    async def __call__(self, message: Message) -> bool:
        active_stage = await protoeuro_db.get_active_stage()
        return active_stage == self.expected_stage

applications_stage_router.message.filter(ActiveStage("applications_stage"))
finalize_applications_router.message.filter(ActiveStage("finalize_applications"))
voting_stage_router.message.filter(ActiveStage("voting_stage"))
finalization_stage_router.message.filter(ActiveStage("finalization_stage"))

dp = Dispatcher()
dp.include_router(admin_router)
dp.include_router(applications_stage_router)
dp.include_router(finalize_applications_router)
dp.include_router(voting_stage_router)
dp.include_router(finalization_stage_router)

@dp.startup()
async def on_startup():
    await protoeuro_db.connect()
    await protoeuro_db.create_tables()


@dp.shutdown()
async def on_shutdown():
    await protoeuro_db.teardown()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await send_message(
        [
            "Привет!",
            "Это бот для проведения PROTOEURO SONG CONTEST.",
            "Если хочешь узнать, что я могу, напиши /help",
        ],
        message,
    )


# applications stage


@applications_stage_router.message(Command("help"))
async def command_applications_help(message: Message) -> None:
    await send_message(
        [
            "Доступные команды:",
            "1️⃣ /contest_rules — правила PROTOEURO SONG CONTEST.",
            "2️⃣ /application_rules — правила подачи заявки.",
            "3️⃣ /choose_country — выбор страны для участия в конкурсе. ВНИМАНИЕ: после выбора страны её не получится изменить.",
            "4️⃣ /booked_countries — просмотр уже выбранных стран. Два участника не могут выбрать одинаковую страну.",
            "5️⃣ /application — подача заявки. Перед подачей заявки необходимо выбрать страну с помощью команды  /choose_country и "  # noqa: ISC004
            "ознакомиться с правилами конкурса /contest_rules и правилами подачи заявки /application_rules.",
            "6️⃣ /check_application — проверка поданной заявки.\n",
            f"Если возникла проблема, пиши автору бота {ADMIN_TAG} :)",
        ],
        message,
    )

@applications_stage_router.message(Command("application_rules"))
async def command_application_rules(message: Message) -> None:
    await message.answer(load_text("APPLICATION_RULES"))

@applications_stage_router.message(Command("contest_rules"))
@voting_stage_router.message(Command("contest_rules"))
async def command_contest_rules(message: Message) -> None:
    await message.answer(load_text("CONTEST_RULES", CEO=CEO))

@applications_stage_router.message(Command("booked_countries"))
async def command_booked_countries(message: Message) -> None:
    countries = await protoeuro_db.booked_countries()
    if len(countries) == 0:
        await message.answer("Все страны свободны!🏳️")
        return
    await message.answer(f"Занятые страны: {', '.join(countries)}")

@applications_stage_router.message(Command("choose_country"))
async def command_choose_country(
    message: Message,
    command: CommandObject,
) -> None:
    country_input = command.args
    if not country_input:
        await message.answer("Небходимо ввести страну после команды, например: /choose_country Россия")
        return

    is_valid, country = validate_country_name(country_input)
    if not is_valid or country is None:
        await message.answer("Имя страны не удалось распознать.")
        return

    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return

    if (country_flag := get_country_flag(country)) is None:
        await message.answer("Не удалось определить флаг страны.")
        return

    if await protoeuro_db.is_booked(country):
        await message.answer("Эта страна уже занята.")
        return

    if not await protoeuro_db.book_country(
        user_id,
        country,
        country_flag,
    ):
        await message.answer(
            "Вы уже выбрали другую страну."
        )
        return

    await message.answer(f"Ваша страна — {country}{country_flag}!")

@applications_stage_router.message(Command("application"))
async def start_application(message: Message, state: FSMContext) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    
    if (await protoeuro_db.get_selected_country(user_id)) is None:
        await message.answer(
            "Сначала выберите страну, например так: /choose_country Россия"
        )
        return
  
    if await protoeuro_db.has_application(user_id):
        await message.answer("У вас уже есть активная заявка. Если вы продолжите, она перезапишется.")
    
    await state.set_state(ApplicationForm.singer)
    await message.answer("Напишите название выбранной группы/исполнителя")

@applications_stage_router.message(ApplicationForm.singer, F.text)
async def receive_singer(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return

    singer_name = message.text.strip()
    if not singer_name or len(singer_name) > 100:
        await message.answer("Название группы/исполнителя должно содержать от 1 до 100 символов.")
        return

    await state.update_data(singer_name=singer_name)
    await state.set_state(ApplicationForm.song)
    await message.answer("Напишите название выбранной песни")

@applications_stage_router.message(ApplicationForm.song, F.text)
async def receive_song(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return

    song_name = message.text.strip()
    if not song_name or len(song_name) > 100:
        await message.answer("Название песни должно содержать от 1 до 100 символов.")
        return

    await state.update_data(song_name=song_name)
    await state.set_state(ApplicationForm.video_start)
    await message.answer("Отправьте таймкод старта отрезка клипа для рекапа в формате <i>минуты</i>:<i>секунды</i>")

@applications_stage_router.message(ApplicationForm.video_start, F.text)
async def receive_video_start(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return
    
    if (time := parse_time(message.text)) is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return
    
    await state.update_data(video_start=time)
    await state.set_state(ApplicationForm.video_end)
    await message.answer("Отправьте таймкод конца отрезка клипа для рекапа в формате минуты:секунды")

@applications_stage_router.message(ApplicationForm.video_end, F.text)
async def receive_video_end(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return
    if (time := parse_time(message.text)) is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return

    data = await state.get_data()
    video_start = data.get("video_start")
    if not isinstance(video_start, int):
        await message.answer("Таймкод старта не найден. Начните подачу заявки заново.")
        return
    if not 10 <= time - video_start <= 25:
        await message.answer("Отрезок для рекапа должен длиться от 10 до 25 секунд. Попробуйте снова.")
        return

    await state.update_data(video_end=time)
    await state.set_state(ApplicationForm.singer_photo)
    await message.answer("Отправьте фотографию исполнителя")

@applications_stage_router.message(ApplicationForm.singer_photo, F.photo)
async def receive_singer_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer("Не удалось распознать фотографию. Попробуйте снова.")
        return

    await state.update_data(singer_photo=message.photo[-1].file_id)
    await state.set_state(ApplicationForm.video_link)
    await message.answer("Отправьте ссылку на музыкальный клип")

@applications_stage_router.message(ApplicationForm.video_link, F.text)
async def receive_video_link(message: Message, state: FSMContext) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return
    
    result, msg = await validate_youtube_video_link(message.text)
    if not result:
        await message.answer(f"{msg} Попробуйте снова.")
        return

    if (country := await protoeuro_db.get_selected_country(user_id)) is None:
        await message.answer("Выбранная вами страна не найдена. Попробуйте снова.")
        return
    country_name, country_flag = country

    data = await state.get_data()
    data["video_link"] = message.text.strip()

    application = Application(
        user_id=user_id,
        country_name=country_name,
        country_flag=country_flag,
        singer_name=data["singer_name"],
        song_name=data["song_name"],
        video_link=data["video_link"],
        video_start=data["video_start"],
        video_end=data["video_end"],
        singer_photo=data["singer_photo"],
    )
    
    result: bool = await protoeuro_db.save_application(application)
    if not result:
        await message.answer("При сохранении заявки что-то пошло не так. Попробуйте снова.")
        return

    await state.clear()
    await message.answer("Ваша заявка принята!🥳 Вы можете изменить её до окончания приёма заявок.")

@applications_stage_router.message(Command("check_application"))
async def check_application(message: Message) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    if (application := await protoeuro_db.get_application(user_id)) is None:
        await message.answer("У вас пока нет поданной заявки.")
        return
    
    caption = [
        f"<b>Страна:</b> {application.country_name}{application.country_flag}",
        f"<b>Исполнитель:</b> {application.singer_name}",
        f"<b>Песня:</b> {application.song_name}",
        f"<b>Таймкод начала:</b> {application.video_start // 60}:{0 if application.video_start % 60 < 10 else ''}{application.video_start % 60}",
        f"<b>Таймкод конца:</b> {application.video_end // 60}:{0 if application.video_end % 60 < 10 else ''}{application.video_end % 60}",
        f"<b>Ссылка на клип:</b> {application.video_link}"
    ]
    
    await message.answer_photo(photo=application.singer_photo, caption='\n'.join(caption))

# voting stage

@voting_stage_router.message(Command("help"))
async def command_voting_help(message: Message) -> None:
    await send_message(
        [
            "Доступные команды:",
            "1️⃣ /contest_rules — правила PROTOEURO SONG CONTEST.",
            "2️⃣ /voting_rules — правила голосования.",
            "3️⃣ /vote — отправить свои баллы. Перед отправкой необходимо ознакомиться с правилами голосования /voting_rules.",
            "4️⃣ /check_vote — проверить свои баллы.",
            "5️⃣ /herald — выбрать глашатая. Выбор глашатая это обязательная часть голосования, без него голоса не будут приняты.",
            "6️⃣ /check_herald — проверить своего глашатая.\n",
            f"Если возникла проблема, пиши автору бота {ADMIN_TAG} :)",
        ],
        message,
    )

@voting_stage_router.message(Command("voting_rules"))
async def command_voting_rules(message: Message) -> None:
    await message.answer(load_text("VOTING_RULES", CEO=CEO))

# @voting_stage_router.message(Command("applications"))
# async def command_applications(message: Message) -> None:
#     applications: list[Application] = await protoeuro_db.get_applications()
#     if not applications:
#         await message.answer("Пока нет поданных заявок.")
#         return

#     msg = []
#     for application in applications:
#         msg.append(f"{application.country_name}{application.country_flag}: {application.video_link}")
#     await send_message(text_list=msg, message=message)


@voting_stage_router.message(Command("vote"))
async def command_vote(message: Message, command: CommandObject) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    
    if not await protoeuro_db.has_application(user_id):
        await message.answer("Чтобы голосовать, необходимо иметь заявку.")
        return

    if not command.args:
        await message.answer(
            "После команды /vote необходимо написать 10 стран через запятую: от 12 баллов до 1 балла."
        )
        return

    votes = [country.strip() for country in command.args.split(",")]
    if len(votes) != 10:
        await message.answer("После команды /vote необходимо написать 10 стран через запятую: от 12 баллов до 1 балла. Попробуйте снова.")
        return

    normalized_votes = []
    for country_name in votes:
        is_valid, country = validate_country_name(country_name)
        if not is_valid or country is None:
            await message.answer(f"Не удалось распознать страну: {country_name}. Попробуйте снова.")
            return
        normalized_votes.append(country)

    result = await protoeuro_db.add_vote(user_id, normalized_votes)
    if not result:
        await message.answer("При сохранении баллов возникла ошибка. Попробуйте снова.")
        return
    await message.answer("Ваши баллы приняты!🥳 Вы можете изменить их до окончания голосования.")

@voting_stage_router.message(Command("check_vote"))
async def check_vote(message: Message) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return

    if (vote := await protoeuro_db.get_vote(user_id)) is None:
        await message.answer("Вы пока не отправили свои баллы.")
        return

    msg = [
        f"12 баллов: {vote.p_12}",
        f"10 баллов: {vote.p_10}",
        f"8 баллов: {vote.p_8}",
        f"7 баллов: {vote.p_7}",
        f"6 баллов: {vote.p_6}",
        f"5 баллов: {vote.p_5}",
        f"4 балла: {vote.p_4}",
        f"3 балла: {vote.p_3}",
        f"2 балла: {vote.p_2}",
        f"1 балл: {vote.p_1}",
    ]
    await send_message(msg, message)

@voting_stage_router.message(Command("herald"))
async def start_herald(message: Message, state: FSMContext) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    
    if not await protoeuro_db.has_application(user_id):
        await message.answer("Чтобы голосовать, необходимо иметь заявку.")
        return
    
    await state.set_state(HeraldForm.herald_photo)
    await message.answer("Отправьте фотографию вашего глашатая")

@voting_stage_router.message(HeraldForm.herald_photo, F.photo)
async def receive_herald_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer("Не удалось распознать фотографию. Попробуйте снова.")
        return

    await state.update_data(herald_photo=message.photo[-1].file_id)
    await state.set_state(HeraldForm.herald_text)
    await message.answer("Напишите текст с которым выступит ваш глашатай")

@voting_stage_router.message(HeraldForm.herald_text, F.text)
async def receive_herald_text(message: Message, state: FSMContext) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return
    if message.text is None:
        await message.answer("Не удалось распознать текст сообщения. Попробуйте снова.")
        return

    txt = message.text.strip()
    if not txt or len(txt) > 1000:
        await message.answer("Ваш текст слишком длинный или отсутствует! Попробуйте снова.")
        return

    data = await state.get_data()
    data["herald_text"] = txt
    
    result = await protoeuro_db.add_herald(
        user_id,
        data["herald_photo"],
        data["herald_text"],
    )
    if not result:
        await message.answer("Возникла ошибка при сохранении вашего глашатая. Попробуйте снова.")
        return
    
    await state.clear()
    await message.answer("Ваш глашатай принят! Вы можете изменить его до окончания приёма голосов.")

@voting_stage_router.message(Command("check_herald"))
async def check_herald(message: Message) -> None:
    if (user_id := get_user_id(message)) is None:
        await message.answer(none_user_id_message)
        return

    if (herald := await protoeuro_db.get_herald(user_id)) is None:
        await message.answer("Вы пока не выбрали глашатая.")
        return

    await message.answer_photo(
        photo=herald.herald_photo,
        caption=herald.herald_text,
    )


# finalization stage

@finalize_applications_router.message()
async def finalize_applications_query(message: Message) -> None:
    await message.answer("Прием заявок завершен!\nОжидайте церемонию оглашения заявок и последующее голосование!")

@finalization_stage_router.message()
async def finalization_query(message: Message) -> None:
    await message.answer("Голосование завершено!\nОжидайте церемонию оглашения результатов!")

# admin

@admin_router.message(Command("admin_help"))
async def admin_help(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        if message.from_user is not None:
            print(f"{message.from_user.id} пытался узнать админские команды!")
        else:
            print("Кто-то пытался узнать админские команды!")
        return
    
    await send_message(
        [
            "Доступные команды:",
            "<b>1.</b> /finalize_applications — завершение приема заявок. НЕЛЬЗЯ ОТМЕНИТЬ",
            "<b>2.</b> /transition_to_voting — запуск голосования после завершения приема заявок. НЕЛЬЗЯ ОТМЕНИТЬ",
            "<b>3.</b> /finalize_voting — завершение отправки голосов. НЕЛЬЗЯ ОТМЕНИТЬ",
            "<b>4.</b> /drop_applications —- получить список текущих заявок",
            "<b>5.</b> /drop_votes — получить список текущих голосов",
            "<b>6.</b> /deanonymize — получить соответствие стран-участниц тегам участников в телеграме",
            "<b>7.</b> /init_points_table — создать таблицу для подсчета баллов стран",
            "<b>8.</b> /add_points_table — необходимо указать название страны, баллы которой надо добавить к текущей таблице баллов",
            "<b>9.</b> /send_reminder — необходимо указать сообщение, которое отправится всем, от кого ожидается голос/заявка, но еще не поступили",
            "<b>10.</b> /send_everyone — необходимо написать сообщение, которое отправится всем текущим участникам\n",
            f"Если возникла проблема, пиши автору бота {ADMIN_TAG} :)",
        ],
        message,
    )

@admin_router.message(Command("transition_to_voting"))
async def transition_to_voting(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return

    changed = await protoeuro_db.transition_to_voting()
    if changed:
        await message.answer("Стадия голосования запущена.")
        return

    active_stage = await protoeuro_db.get_active_stage()
    if active_stage == "applications_stage":
        await message.answer("Сначала завершите прием заявок командой /finalize_applications.")
        return
    if active_stage == "finalization_stage":
        await message.answer("Голосование уже завершено.")
        return

    await message.answer("Стадия голосования уже идет.")


@admin_router.message(Command("finalize_applications"))
async def finalize_applications(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS: # type: ignore
        await message.answer("Доступ запрещен.")
        return

    changed = await protoeuro_db.transition_to_applications_finalization()
    if changed:
        await message.answer("Прием заявок завершен. Теперь можно запустить голосование.")
        return

    active_stage = await protoeuro_db.get_active_stage()
    if active_stage == "finalize_applications":
        await message.answer("Прием заявок уже завершен.")
        return
    if active_stage == "voting_stage":
        await message.answer("Голосование уже запущено.")
        return

    await message.answer("Голосование уже завершено.")


@admin_router.message(Command("finalize_voting"))
async def finalize_voting(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS: # type: ignore
        await message.answer("Доступ запрещен.")
        return

    changed = await protoeuro_db.transition_to_finalization()
    await message.answer(
        "Голосование завершено. Можно подводить итоги."
        if changed
        else "Финализация недоступна: голосование еще не начато или уже завершено."
    )


@admin_router.message(Command("deanonymize"))
async def deanonymize(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return

    selections = await protoeuro_db.get_country_selections()
    if not selections:
        await message.answer("Пока никто не выбрал страну.")
        return

    country_usernames = []
    for country_name, user_id in selections:
        try:
            chat = await message.bot.get_chat(user_id) # type: ignore
        except TelegramAPIError:
            country_usernames.append(f"{country_name}: username недоступен")
            continue

        if chat.username is None:
            nickname = " ".join(
                name
                for name in (chat.first_name, chat.last_name)
                if name is not None
            )
            country_usernames.append(f"{country_name}: {nickname}")
            continue

        country_usernames.append(f"{country_name}: @{chat.username}")
    await send_message(country_usernames, message)


@admin_router.message(Command("send_reminder"))
async def command_send_reminder(message: Message, command: CommandObject) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return

    text = get_message_text(command)
    if text is None:
        await message.answer("После команды /send_reminder напишите текст до 4096 символов.")
        return

    active_stage = await protoeuro_db.get_active_stage()
    if active_stage == "applications_stage":
        user_ids = await protoeuro_db.get_users_without_application()
    elif active_stage == "voting_stage":
        user_ids = await protoeuro_db.get_users_without_vote_or_herald()
    else:
        await message.answer("На текущей стадии напоминания не отправляются.")
        return

    if not user_ids:
        await message.answer("Нет участников, которым нужно отправить напоминание.")
        return

    sent_count, failed_count = await send_to_users(user_ids, text, message)
    await message.answer(
        f"Напоминание отправлено: {sent_count}. Не удалось доставить: {failed_count}."
    )


@admin_router.message(Command("send_everyone"))
async def command_send_everyone(message: Message, command: CommandObject) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return

    text = get_message_text(command)
    if text is None:
        await message.answer("После команды /send_everyone напишите текст до 4096 символов.")
        return

    user_ids = await protoeuro_db.get_participant_user_ids()
    if not user_ids:
        await message.answer("Пока нет участников для рассылки.")
        return

    sent_count, failed_count = await send_to_users(user_ids, text, message)
    await message.answer(
        f"Сообщение отправлено: {sent_count}. Не удалось доставить: {failed_count}."
    )
    
@admin_router.message(Command("drop_applications"))
async def drop_applications(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return
    
    applications = await protoeuro_db.get_applications()
    if not applications:
        await message.answer("Ошибка базы данных или заявок пока нет. Попробуйте снова.")
    
    for i in range(1, len(applications) + 1):
        application = applications[i - 1]
        msg = [
            f"Заявка номер {i}.",
            f"Таймкод начала {application.video_start // 60}:{0 if application.video_start % 60 < 10 else ''}{application.video_start % 60}",
            f"Таймкод конца {application.video_end // 60}:{0 if application.video_end % 60 < 10 else ''}{application.video_end % 60}",
            f"<b>{application.country_name}</b> {application.country_flag}",
            f"<i>{application.singer_name}</i>",
            f"<i>{application.song_name}</i>",
            "\n",
            f"<u>{application.video_link}</u>"
        ]
        await message.answer_photo(photo=application.singer_photo, caption='\n'.join(msg))

@admin_router.message(Command("drop_votes"))
async def drop_votes(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return
    
    votes = await protoeuro_db.get_votes()
    if not votes:
        await message.answer("Пока нет голосов с глашатаями.")
        return

    for i, vote in enumerate(votes, start=1):
        herald = await protoeuro_db.get_herald(vote.user_id)
        if herald is None:
            continue

        await message.answer_photo(
            photo=herald.herald_photo,
            caption=herald.herald_text,
        )
        msg = [
            f"Голосование номер {i} от страны: <b>{vote.country_name}</b>",
            f"12 баллов: {vote.p_12}",
            f"10 баллов: {vote.p_10}",
            f"8 баллов: {vote.p_8}",
            f"7 баллов: {vote.p_7}",
            f"6 баллов: {vote.p_6}",
            f"5 баллов: {vote.p_5}",
            f"4 балла: {vote.p_4}",
            f"3 балла: {vote.p_3}",
            f"2 балла: {vote.p_2}",
            f"1 балл: {vote.p_1}",
        ]
        await send_message(msg, message)

@admin_router.message(Command("init_points_table"))
async def init_points_table(message: Message) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return
    
    global points_table
    points_table = PointsTable(await protoeuro_db.get_applications())
    if points_table is not None:
        await send_message(points_table.show_table(), message)

@admin_router.message(Command("add_points_table"))
async def add_points_table(message: Message, command: CommandObject) -> None:
    if message.from_user is None or message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен.")
        return
    
    if not command.args:
        await message.answer(
            "После команды /add_points_table необходимо написать страну, баллы которой будут добавлены."
        )
        return
    country = _normalize_country_name(command.args.strip())
    
    vote = await protoeuro_db.get_vote_by_country_name(country)
    if vote is None:
        await message.answer(
            "Не удалось найти баллы этой страны. Попробуйте снова."
        )
        return
    
    if points_table is None:
        await message.answer(
            "Таблица баллов не инициализирована. /init_points_table"
        )
        return
    table = points_table.update_table(vote)
    await send_message(table, message)
    
    

# common query

@applications_stage_router.message()
@voting_stage_router.message()
async def common_query(message: Message) -> None:
    await send_message(["Введите /help, чтобы увидеть список доступных команд."], message)

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
