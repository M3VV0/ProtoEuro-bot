import re
from dataclasses import dataclass
from typing import Optional
from aiogram.fsm.state import State, StatesGroup

import aiohttp

from web import parse_youtube_video

class ApplicationForm(StatesGroup):
    singer = State()
    song = State()
    video_start = State()
    video_end = State()
    singer_photo = State()
    video_link = State()

UN_COUNTRIES_RU: dict[str, None] = dict.fromkeys(
    (
        "Австралия",
        "Австрия",
        "Азербайджан",
        "Албания",
        "Алжир",
        "Ангола",
        "Андорра",
        "Антигуа и Барбуда",
        "Аргентина",
        "Армения",
        "Афганистан",
        "Багамы",
        "Бангладеш",
        "Барбадос",
        "Бахрейн",
        "Беларусь",
        "Белиз",
        "Бельгия",
        "Бенин",
        "Болгария",
        "Боливия",
        "Босния и Герцеговина",
        "Ботсвана",
        "Бразилия",
        "Бруней",
        "Буркина-Фасо",
        "Бурунди",
        "Бутан",
        "Вануату",
        "Ватикан",
        "Венгрия",
        "Венесуэла",
        "Вьетнам",
        "Габон",
        "Гаити",
        "Гайана",
        "Гамбия",
        "Гана",
        "Гватемала",
        "Гвинея",
        "Гвинея-Бисау",
        "Германия",
        "Гондурас",
        "Гренада",
        "Греция",
        "Грузия",
        "Дания",
        "Демократическая Республика Конго",
        "Джибути",
        "Доминика",
        "Доминиканская Республика",
        "Египет",
        "Замбия",
        "Зимбабве",
        "Израиль",
        "Индия",
        "Индонезия",
        "Иордания",
        "Ирак",
        "Иран",
        "Ирландия",
        "Исландия",
        "Испания",
        "Италия",
        "Йемен",
        "Кабо-Верде",
        "Казахстан",
        "Камбоджа",
        "Камерун",
        "Канада",
        "Катар",
        "Кения",
        "Кипр",
        "Кирибати",
        "Китай",
        "Колумбия",
        "Коморы",
        "Корейская Народно-Демократическая Республика",
        "Коста-Рика",
        "Кот-Д'ивуар",
        "Куба",
        "Кувейт",
        "Кыргызстан",
        "Лаос",
        "Латвия",
        "Лесото",
        "Либерия",
        "Ливан",
        "Ливия",
        "Литва",
        "Лихтенштейн",
        "Люксембург",
        "Маврикий",
        "Мавритания",
        "Мадагаскар",
        "Малави",
        "Малайзия",
        "Мали",
        "Мальдивы",
        "Мальта",
        "Марокко",
        "Маршалловы Острова",
        "Мексика",
        "Микронезия",
        "Мозамбик",
        "Молдова",
        "Монако",
        "Монголия",
        "Мьянма",
        "Намибия",
        "Науру",
        "Непал",
        "Нигер",
        "Нигерия",
        "Нидерланды",
        "Никарагуа",
        "Новая Зеландия",
        "Норвегия",
        "Объединенные Арабские Эмираты",
        "Оман",
        "Пакистан",
        "Палау",
        "Панама",
        "Палестина",
        "Папуа-Новая Гвинея",
        "Парагвай",
        "Перу",
        "Польша",
        "Португалия",
        "Республика Конго",
        "Республика Корея",
        "Россия",
        "Руанда",
        "Румыния",
        "Сальвадор",
        "Самоа",
        "Сан-Марино",
        "Сан-Томе и Принсипи",
        "Саудовская Аравия",
        "Северная Македония",
        "Сейшелы",
        "Сенегал",
        "Сент-Винсент и Гренадины",
        "Сент-Китс и Невис",
        "Сент-Люсия",
        "Сербия",
        "Сингапур",
        "Сирия",
        "Словакия",
        "Словения",
        "Великобритания",
        "США",
        "Соломоновы Острова",
        "Сомали",
        "Судан",
        "Суринам",
        "Сьерра-Леоне",
        "Таджикистан",
        "Таиланд",
        "Танзания",
        "Тимор-Лешти",
        "Того",
        "Тонга",
        "Тринидад и Тобаго",
        "Тувалу",
        "Тунис",
        "Туркменистан",
        "Турция",
        "Уганда",
        "Узбекистан",
        "Украина",
        "Уругвай",
        "Фиджи",
        "Филиппины",
        "Финляндия",
        "Франция",
        "Хорватия",
        "Центральноафриканская Республика",
        "Чад",
        "Черногория",
        "Чехия",
        "Чили",
        "Швейцария",
        "Швеция",
        "Шри-Ланка",
        "Эквадор",
        "Экваториальная Гвинея",
        "Эритрея",
        "Эсватини",
        "Эстония",
        "Эфиопия",
        "Южно-Африканская Республика",
        "Южный Судан",
        "Ямайка",
        "Япония",
    )
)


_COUNTRY_CODES = (
    "AU AT AZ AL DZ AO AD AG AR AM AF BS BD BB BH BY BZ BE BJ BG BO BA BW BR BN BF BI BT "
    "VU VA HU VE VN GA HT GY GM GH GT GN GW DE HN GD GR GE DK CD DJ DM DO EG ZM ZW IL IN "
    "ID JO IQ IR IE IS ES IT YE CV KZ KH CM CA QA KE CY KI CN CO KM KP CR CI CU KW KG LA "
    "LV LS LR LB LY LT LI LU MU MR MG MW MY ML MV MT MA MH MX FM MZ MD MC MN MM NA NR NP "
    "NE NG NL NI NZ NO AE OM PK PW PA PS PG PY PE PL PT CG KR RU RW RO SV WS SM ST SA MK SC "
    "SN VC KN LC RS SG SY SK SI GB US SB SO SD SR SL TJ TH TZ TL TG TO TT TV TN TM TR UG UZ "
    "UA UY FJ PH FI FR HR CF TD ME CZ CL CH SE LK EC GQ ER SZ EE ET ZA SS JM JP"
).split()


def _country_flag(country_code: str) -> str:
    """Build a Unicode regional-indicator flag emoji from an ISO country code."""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in country_code)

COUNTRY_FLAGS_RU: dict[str, str] = {
    country_name: _country_flag(country_code)
    for country_name, country_code in zip(UN_COUNTRIES_RU, _COUNTRY_CODES)
}


def _normalize_country_name(name: str) -> str:
    if name.strip().casefold() == "сша":
        return "США"

    normalized_words = []
    for word in name.strip().split():
        if word.lower() == "и":
            normalized_words.append("и")
            continue

        normalized_words.append("-".join(part.capitalize() for part in word.split("-")))

    return " ".join(normalized_words)


def validate_country_name(name: str) -> tuple[bool, Optional[str]]:
    """Return whether *name* is a UN member or observer state and its normalized form."""
    normalized_name = _normalize_country_name(name)

    if normalized_name not in UN_COUNTRIES_RU:
        return False, None

    return True, normalized_name


def get_country_flag(name: str) -> Optional[str]:
    """Return the Telegram-compatible flag emoji for a valid country name."""
    is_valid, normalized_name = validate_country_name(name)
    if not is_valid:
        return None

    return COUNTRY_FLAGS_RU[normalized_name] # type: ignore


def parse_time(value: str) -> Optional[int]:
    """Parse a trimmed ``minutes:seconds`` value into total seconds."""
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdecimal() for part in parts):
        return None

    minutes, seconds = (int(part) for part in parts)
    if seconds > 59:
        return None

    return minutes * 60 + seconds

async def validate_youtube_video_link(
    link: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> tuple[bool, str]:
    """Return whether a YouTube video meets contest age, title, and view limits."""
    video = await parse_youtube_video(link, session)
    if video is None:
        return False, "Не удалось получить видео."

    if video.published_year < 2010:
        return False, "Год выхода песни должен быть не меньше 2010."
    if re.search(r"\bcover\b", video.title, flags=re.IGNORECASE) is not None:
        return False, "Видео должно быть оригинальным клипом на песню."
    if video.view_count > 300_000_000:
        return False, "У клипа не должно быть больше 300 миллионов просмотров."
    return True, ""

@dataclass
class Application:
    user_id: int
    country_name: str
    country_flag: str
    singer_name: str
    song_name: str
    video_link: str
    video_start: int # seconds
    video_end: int # seconds
    singer_photo: str
    
    def __init__(
        self,
        user_id: int,
        country_name: str,
        country_flag: str,
        singer_name: str,
        song_name: str,
        video_link: str,
        video_start: int,
        video_end: int,
        singer_photo: str,
    ) -> None:
        self.user_id = user_id
        self.country_name = country_name
        self.country_flag = country_flag
        self.singer_name = singer_name
        self.song_name = song_name
        self.video_link = video_link
        self.video_start = video_start
        self.video_end = video_end
        self.singer_photo = singer_photo
