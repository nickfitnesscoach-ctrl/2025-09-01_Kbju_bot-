"""
Калькулятор КБЖУ для Fitness Bot
Формула Миффлина—Сан Жеора. Все человеко-читабельные тексты берём из texts_data.json.
"""

from __future__ import annotations

from app.texts import get_text


class KBJUCalculator:
    """Расчёт калорий и БЖУ."""

    # Коэффициенты активности (чистая математика — ок держать в коде)
    ACTIVITY_COEFFICIENTS: dict[str, float] = {
        "low": 1.2,
        "moderate": 1.375,
        "high": 1.55,
        "very_high": 1.725,
    }

    # Корректировки калорий по целям (тоже математика)
    GOAL_ADJUSTMENTS: dict[str, float] = {
        "weight_loss": -0.15,
        "maintenance": 0.0,
        "weight_gain": 0.10,
    }

    @staticmethod
    def calculate_bmr(gender: str, age: int, weight: float, height: int) -> float:
        """Базовый метаболизм (BMR) по Миффлину—Сан Жеору."""
        if gender == "male":
            return 10 * weight + 6.25 * height - 5 * age + 5
        return 10 * weight + 6.25 * height - 5 * age - 161

    @classmethod
    def calculate_kbju(
        cls,
        gender: str,
        age: int,
        weight: float,
        height: int,
        activity: str,
        goal: str,
    ) -> dict[str, int]:
        """
        Полный расчёт КБЖУ с учётом активности и цели.
        Возвращает dict: {'calories','proteins','fats','carbs','bmr'} (всё ints).
        """
        if gender not in {"male", "female"}:
            raise ValueError("gender_invalid")

        if activity not in cls.ACTIVITY_COEFFICIENTS:
            raise ValueError("activity_invalid")

        if goal not in cls.GOAL_ADJUSTMENTS:
            raise ValueError("goal_invalid")

        bmr = cls.calculate_bmr(gender, age, weight, height)
        calories_maintenance = bmr * cls.ACTIVITY_COEFFICIENTS[activity]
        calories_target = calories_maintenance * (1 + cls.GOAL_ADJUSTMENTS[goal])

        if goal == "weight_gain":
            proteins = round(weight * 2.0)                      # 2 г/кг
            fats = round(weight * 1.1)                          # 1.1 г/кг
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)
        else:
            proteins = round(weight * 1.8)                      # 1.8 г/кг
            fats = round(calories_target * 0.25 / 9)            # 25% калорий
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)

        return {
            "calories": round(calories_target),
            "proteins": proteins,
            "fats": fats,
            "carbs": carbs,
            "bmr": round(bmr),
        }

    @staticmethod
    def validate_user_data(
        gender: str, age: int, weight: float, height: int
    ) -> tuple[bool, str]:
        """
        Валидация пользовательских данных.
        Возвращает (is_valid, message). message — уже из JSON (errors.*).
        """
        if gender not in {"male", "female"}:
            return False, get_text("errors.gender_invalid")

        if not (15 <= age <= 80):
            return False, get_text("errors.age_range")

        if not (30 <= weight <= 200):
            return False, get_text("errors.weight_range")

        if not (140 <= height <= 220):
            return False, get_text("errors.height_range")

        return True, ""


# ---------- Текстовые описания (из JSON) ----------

def get_activity_description(activity: str) -> str:
    """
    Человеко-читабельное описание активности.
    Берётся из texts_data.json → activity_descriptions.<key>
    """
    # если ключа нет — вернётся "[Текст не найден: ...]" что заметно в тесте
    return get_text(f"activity_descriptions.{activity}")


def get_goal_description(goal: str) -> str:
    """
    Человеко-читабельное описание цели.
    Берётся из texts_data.json → goal_descriptions.<key>
    """
    return get_text(f"goal_descriptions.{goal}")
