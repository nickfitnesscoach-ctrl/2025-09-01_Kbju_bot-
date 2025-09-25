"""
Калькулятор КБЖУ для Fitness Bot
Формула Миффлина—Сан Жеора + учёт ожирения (ABW) и правил по целям.
"""

from __future__ import annotations
import logging
from app.texts import get_text

logger = logging.getLogger(__name__)


class KBJUCalculator:
    # Активность
    ACTIVITY_COEFFICIENTS: dict[str, float] = {
        "low": 1.2,
        "moderate": 1.375,
        "high": 1.55,
        "very_high": 1.725,
    }

    # Профицит/дефицит
    GOAL_ADJUSTMENTS: dict[str, float] = {
        "weight_loss": -0.15,
        "maintenance": 0.0,
        "weight_gain": +0.15,
    }

    # Полы калорий (только для похудения)
    CAL_FLOOR_MALE = 1600
    CAL_FLOOR_FEMALE = 1300

    @staticmethod
    def calculate_bmr(gender: str, age: int, weight: float, height: int) -> float:
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
        return ibw + 0.4 * (weight - ibw)

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

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

        if gender not in {"male", "female"}:
            raise ValueError("gender_invalid")
        if activity not in cls.ACTIVITY_COEFFICIENTS:
            raise ValueError("activity_invalid")
        if goal not in cls.GOAL_ADJUSTMENTS:
            raise ValueError("goal_invalid")

        # Калории
        bmr = cls.calculate_bmr(gender, age, weight, height)
        tdee = bmr * cls.ACTIVITY_COEFFICIENTS[activity]
        calories_target = tdee * (1 + cls.GOAL_ADJUSTMENTS[goal])
        calories_initial = calories_target
        calories_adjusted_reason: str | None = None

        # Ожирение → ABW
        bmi = cls._bmi(weight, height)
        ibw = cls._ibw_bmi25(height)
        use_abw = bool(bmi >= 30.0 or weight > ibw * 1.2)
        base_wt_loss = cls._abw(weight, ibw) if use_abw else weight  # база для сушки

        # ==== ЦЕЛИ ====
        if goal == "weight_gain":
            proteins = round(weight * 2.0)
            # жиры 1 г/кг с рамками 20–35% и 0.9–1.1 г/кг
            fats_target = weight * 1.0
            fats_lo_gkg = weight * 0.9
            fats_hi_gkg = weight * 1.1
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, max(fats_lo_gkg, fats_lo_pct), min(fats_hi_gkg, fats_hi_pct)))
            # минимум жиров для женщин
            if gender == "female" and fats < 40:
                fats = 40
            # угли ≥ 4 г/кг
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)
            carbs_min = round(weight * 4.0)
            if carbs < carbs_min:
                carbs = carbs_min
                calories_target = proteins * 4 + fats * 9 + carbs * 4
                calories_adjusted_reason = "carbs_min_gain_4gkg"

        elif goal == "weight_loss":
            # белок 2 г/кг от ABW/TBW
            proteins = round(base_wt_loss * 2.0)

            # жиры 0.7–0.8 г/кг (ABW/TBW) с рамками 20–35%
            fats_target = base_wt_loss * 0.75
            fats_lo_gkg = base_wt_loss * 0.6
            fats_hi_gkg = base_wt_loss * 1.0
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, max(fats_lo_gkg, fats_lo_pct), min(fats_hi_gkg, fats_hi_pct)))
            # минимум жиров для женщин
            if gender == "female" and fats < 40:
                fats = 40

            # угли: остаток, но ≥ max(1 г/кг base, 100 г)
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)
            carbs_min = max(round(base_wt_loss * 1.0), 100)
            if carbs < carbs_min:
                carbs = carbs_min
                calories_target = proteins * 4 + fats * 9 + carbs * 4
                calories_adjusted_reason = "carbs_min_loss_1gkg_or_100"

            # пол калорий: 1600 муж / 1300 жен; добираем углями
            cal_floor = cls.CAL_FLOOR_MALE if gender == "male" else cls.CAL_FLOOR_FEMALE
            if calories_target < cal_floor:
                need_carb_g = int((cal_floor - (proteins * 4 + fats * 9) + 3) // 4)  # ceil
                carbs = max(carbs, carbs_min, need_carb_g)
                calories_target = proteins * 4 + fats * 9 + carbs * 4
                calories_adjusted_reason = (calories_adjusted_reason + "|cal_floor") if calories_adjusted_reason else "cal_floor"

        elif goal == "maintenance":
            proteins = round(weight * 1.8)
            fats_target = weight * 0.8
            fats_lo_pct = calories_target * 0.20 / 9.0
            fats_hi_pct = calories_target * 0.35 / 9.0
            fats = round(cls._clamp(fats_target, fats_lo_pct, fats_hi_pct))
            if gender == "female" and fats < 40:
                fats = 40
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)

        else:
            proteins = round(weight * 1.8)
            fats = round(calories_target * 0.25 / 9.0)
            if gender == "female" and fats < 40:
                fats = 40
            carbs = round((calories_target - proteins * 4 - fats * 9) / 4)

        # ==== РЕЗУЛЬТАТ ====
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

    @staticmethod
    def validate_user_data(
        gender: str, age: int, weight: float, height: int
    ) -> tuple[bool, str]:
        if gender not in {"male", "female"}:
            return False, get_text("errors.gender_invalid")
        if not (15 <= age <= 80):
            return False, get_text("errors.age_range")
        if not (30 <= weight <= 250):
            return False, get_text("errors.weight_range")
        if not (140 <= height <= 220):
            return False, get_text("errors.height_range")
        return True, ""


# ---- Текстовые описания (из JSON) ----

def get_activity_description(activity: str) -> str:
    return get_text(f"activity_descriptions.{activity}")


def get_goal_description(goal: str) -> str:
    return get_text(f"goal_descriptions.{goal}")
