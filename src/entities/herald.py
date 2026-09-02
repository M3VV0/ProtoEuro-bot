from dataclasses import dataclass
from aiogram.fsm.state import State, StatesGroup

class HeraldForm(StatesGroup):
    herald_photo = State()
    herald_text = State()

@dataclass
class Herald:
    herald_photo: str
    herald_text: str