from aiogram.fsm.state import State, StatesGroup


# Существующий пример (оставляем для совместимости)
class RegExample(StatesGroup):
    name = State()
    number = State()
    location = State()


# FSM состояния для КБЖУ калькулятора
class KBJUStates(StatesGroup):
    # Существующие состояния
    waiting_age = State()
    waiting_weight = State()
    waiting_height = State()

    # Новые состояния для расширенного опроса (после height, до activity)
    waiting_target_weight = State()
    waiting_current_body_type = State()
    waiting_target_body_type = State()
    waiting_timezone = State()

    # Новое состояние для проверки подписки (перед AI)
    checking_subscription = State()


# FSM состояния для воронки лидов
class FunnelStates(StatesGroup):
    waiting_contact = State()
    

# FSM состояния для администратора
class AdminStates(StatesGroup):
    broadcast = State()
    statistics = State()
    viewing_leads = State()  # для пагинации лидов
    lead_reply = State()
