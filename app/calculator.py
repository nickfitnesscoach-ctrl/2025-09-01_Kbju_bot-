"""
Калькулятор КБЖУ для Fitness Bot
Формула Миффлина—Сан Жеора + учёт ожирения (ABW) и разных целей.
Все человеко-читабельные тексты берём из texts_data.json.
"""

from __future__ import annotations
import logging
from app.texts import get_text

logger = logging.getLogger(__name__)


class KBJUCalculator:
    """
    Полный расчёт калорий и БЖУ.

    ОСНОВНЫЕ ПРАВИЛА
    ----------------
    • Активность: множители для TDEE.
    • Цели:
        - weight_gain:   TDEE * 1.15; белок 2.0 г/кг; жиры 1.0 г/кг (в пределах 20–35% ккал);
                          углеводы ≥ 4.0 г/кг (если не хватает — повышаем калории).
        - weight_loss:   TDEE * 0.85; ожирение считается по ABW; белок 2.0 г/кг от ABW;
                          жиры 0.7–0.8 г/кг от ABW (в пределах 20–35% ккал);
                          углеводы = остаток, но ≥ 1.0 г/кг ABW.
        - maintenance:   TDEE; белок 1.8 г/кг; жиры 0.8 г/кг (20–35% ккал); углеводы = остаток.
    • Ожирение: BMI ≥ 30 (или вес >120% «идеала») → используем ABW.
        - IBW по BMI=25: 25 * (рост_м^2)
        - ABW = IBW + 0.4 * (TBW - IBW)
    """

    # Коэффициенты активности
    ACTIVITY_COEFFICIENTS: dict[str, float] = {
        "low": 1.2,
        "moderate": 1.375,
        "high": 1.55,
        "very_high": 1.725,
    }

    # Корректировки калорий по целям
    GOAL_ADJUSTMENTS: dict[str, float] = {
        "weight_loss": -0.15,
        "maintenance": 0.0,
        "weight_gain": +0.15,
    }

    # -------------------- базовые помощники --------------------

    @staticmethod
    def calculate_bmr(gender: str, age: int, weight: float, height: int) -> float:
        """BMR по Миффлину—Сан Жеору."""
        if gender == "male":
            return 10 * weight + 6.25 * height - 5 * age + 5
        return 10 * weight + 6.25 * height - 5 * age - 161

    @staticmethod
    def _bmi(weight: float, height_cm: int) -> float:
        h = height_cm / 100.0
        return weight / (h * h)

    @staticmethod
    def _ibw_bmi25(height_cm: int) -> float:
        h = height_cm / 100.0
        return 25.0 * (h * h)

    @staticmethod
    def _abw(weight: float, ibw: float) -> float:
        # Adjusted Body Weight для ожирения
        return ibw + 0.4 * (weight - ibw)

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    # -------------------- публичный расчёт --------------------

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
        Возвращает dict:
          - 'calories', 'proteins', 'fats', 'carbs', 'bmr' (ints)
        Дополнительно (по ситуации) добавляет:
          - 'calories_initial' (ккал до автокоррекции)
          - 'calories_adjusted_reason' ('carbs_min_gain_4gkg' | 'carbs_min_loss_1gkg')
          - 'used_weight_basis' ('TBW' | 'ABW')
        """
        # ---- валидации входа ----
        if gender not in {"male", "female"}:
            raise ValueError("gender_invalid")
        if activity not in cls.ACTIVITY_COEFFICIENTS:
            raise ValueError("activity_invalid")
        if goal not in cls.GOAL_ADJUSTMENTS:
            raise ValueError("goal_invalid")

        # ---- калории ----
        bmr = cls.calculate_bmr(gender, age, weight, height)
        tdee = bmr * cls.ACTIVITY_COEFFICIENTS[activity]
        calories_target = tdee * (1 + cls.GOAL_ADJUSTMENTS[goal])
        calories_initial = calories_target
        calories_adjusted_reason: str | None = None

        # ---- ожирение / базовый вес для расчётов ----
        bmi = cls._bmi(weight, height)
        ibw = cls._ibw_bmi25(height)
        use_abw = bool(bmi >= 30.0 or weight > ibw * 1.2)
        base_wt_loss = cls._abw(weight, ibw) if use_abw else weight

        # ---- расчёт макросов по целям ----
        if goal == "weight_gain":
            # Белок: 2.0 г/кг (от фактического веса)
            proteins = round(weight * 2.0)

            # Жиры: таргет 1.0 г/кг, но в пределах 20–35% ккал и 0.9–1.1 г/кг
            fats_target = weight * 1.0
            fats_lo_gkg = weight * 0.9
            fats_hi_gkg = weight * 1.1
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, max(fats_lo_gkg, fats_lo_pct), min(fats_hi_gkg, fats_hi_pct)))

            # Углеводы: остаток, но минимум 4.0 г/кг
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)
            carbs_min = round(weight * 4.0)
            if carbs < carbs_min:
                carbs = carbs_min
                calories_target = proteins * 4 + fats * 9 + carbs * 4
                calories_adjusted_reason = "carbs_min_gain_4gkg"

        elif goal == "weight_loss":
            # Белок: 2.0 г/кг от ABW (или от фактического веса, если нет ожирения)
            proteins = round(base_wt_loss * 2.0)

            # Жиры: 0.7–0.8 г/кг от ABW, в пределах 20–35% ккал
            fats_target = base_wt_loss * 0.75
            fats_lo_gkg = base_wt_loss * 0.6
            fats_hi_gkg = base_wt_loss * 1.0
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, max(fats_lo_gkg, fats_lo_pct), min(fats_hi_gkg, fats_hi_pct)))

            # Углеводы: остаток, но минимум 1.0 г/кг от базового веса (ABW/вес)
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)
            carbs_min = round(base_wt_loss * 1.0)
            if carbs < carbs_min:
                carbs = carbs_min
                calories_target = proteins * 4 + fats * 9 + carbs * 4
                calories_adjusted_reason = "carbs_min_loss_1gkg"

        elif goal == "maintenance":
            proteins = round(weight * 1.8)
            # Жиры: 0.8 г/кг, но в рамках 20–35% ккал
            fats_target = weight * 0.8
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, fats_lo_pct, fats_hi_pct))
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)

        else:  # на всякий случай для совместимости
            proteins = round(weight * 1.8)
            fats = round(calories_target * 0.25 / 9.0)
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)

        # ---- формирование ответа ----
        result: dict[str, int | str] = {
            "calories": int(round(calories_target)),
            "proteins": int(proteins),
            "fats": int(fats),
            "carbs": int(carbs),
            "bmr": int(round(bmr)),
        }

        if calories_adjusted_reason:
            result["calories_adjusted_reason"] = calories_adjusted_reason
            result["calories_initial"] = int(round(calories_initial))
        if goal == "weight_loss":
            result["used_weight_basis"] = "ABW" if use_abw else "TBW"

        return result

    # -------------------- публичные справочники --------------------

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
        if not (30 <= weight <= 250):
            return False, get_text("errors.weight_range")
        if not (140 <= height <= 220):
            return False, get_text("errors.height_range")
        return True, ""


# ---------- Текстовые описания (из JSON) ----------

def get_activity_description(activity: str) -> str:
    """activity_descriptions.<key>"""
    return get_text(f"activity_descriptions.{activity}")


def get_goal_description(goal: str) -> str:
    """goal_descriptions.<key>"""
    return get_text(f"goal_descriptions.{goal}")
