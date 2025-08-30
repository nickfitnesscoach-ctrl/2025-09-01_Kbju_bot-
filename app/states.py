from aiogram.fsm.state import State, StatesGroup


# Существующий пример (оставляем для совместимости)
class RegExample(StatesGroup):
    name = State()
    number = State()
    location = State()


# FSM состояния для КБЖУ калькулятора
class KBJUStates(StatesGroup):
    waiting_age = State()
    waiting_weight = State()  
    waiting_height = State()


# FSM состояния для воронки лидов
class FunnelStates(StatesGroup):
    waiting_contact = State()
    

# FSM состояния для администратора
class AdminStates(StatesGroup):
    broadcast = State()
    statistics = State()
