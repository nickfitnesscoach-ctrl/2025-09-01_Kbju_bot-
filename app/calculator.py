"""
Калькулятор КБЖУ для Fitness Bot
Формула Миффлина—Сан Жеора. Все человеко-читабельные тексты берём из texts_data.json.
"""

from __future__ import annotations

import logging

from app.texts import get_text


logger = logging.getLogger(__name__)


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
        "weight_gain": 0.12,
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
    ) -> dict[str, int | str]:
        """
        Полный расчёт КБЖУ с учётом активности и цели.
        Возвращает dict: {'calories','proteins','fats','carbs','bmr'} (всё ints).
        Дополнительно может вернуть служебные ключи 'calories_adjusted_reason',
        'calories_initial'.
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
        calories_adjusted_reason: str | None = None
        calories_initial = calories_target

        def _clamp(x: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, x))

        if goal == "weight_gain":
            # 1) Белок 2.0 г/кг
            proteins_out: int = round(weight * 2.0)

            # 2) Жиры таргет 1 г/кг, но в разумных пределах и с учётом % калорий
            fats_by_kg_target = weight * 1.0
            fats_min_by_kg = weight * 0.9
            fats_max_by_kg = weight * 1.1
            fats_min_by_pct = calories_target * 0.20 / 9.0  # >=20% калорий
            fats_max_by_pct = calories_target * 0.35 / 9.0  # <=35% калорий

            fats_lo = max(fats_min_by_kg, fats_min_by_pct)
            fats_hi = min(fats_max_by_kg, fats_max_by_pct)
            fats_out = round(_clamp(fats_by_kg_target, fats_lo, fats_hi))

            # 3) Углеводы = остаток калорий
            carbs_out: int = round((calories_target - proteins_out * 4 - fats_out * 9) / 4)

            # 4) Гарантируем минимум углей для набора (не менее 2.0 г/кг)
            min_carbs = round(weight * 2.0)
            if carbs_out < min_carbs:
                carbs_out = min_carbs
                adjusted_calories = proteins_out * 4 + fats_out * 9 + carbs_out * 4
                if adjusted_calories > calories_target:
                    calories_target = adjusted_calories
                    calories_adjusted_reason = "carbs_min"
                    logger.info(
                        "Calories target increased for weight gain: original=%s adjusted=%s (carbs_min=%s)",
                        round(calories_initial),
                        round(calories_target),
                        carbs_out,
                    )
        else:
            proteins_out = round(weight * 1.8)  # 1.8 г/кг
            fats_out = round(calories_target * 0.25 / 9)  # 25% калорий
            carbs_out = round((calories_target - proteins_out * 4 - fats_out * 9) / 4)

        result: dict[str, int | str] = {
            "calories": round(calories_target),
            "proteins": proteins_out,
            "fats": fats_out,
            "carbs": carbs_out,
            "bmr": round(bmr),
        }

        if calories_adjusted_reason == "carbs_min":
            result["calories_adjusted_reason"] = calories_adjusted_reason
            result["calories_initial"] = round(calories_initial)

        return result

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
