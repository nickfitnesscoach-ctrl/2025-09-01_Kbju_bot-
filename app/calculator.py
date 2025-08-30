"""
Калькулятор КБЖУ для Fitness Bot
Использует формулу Миффлина-Сан Жеора для расчета базового метаболизма
"""


class KBJUCalculator:
    
    # Коэффициенты активности
    ACTIVITY_COEFFICIENTS = {
        'low': 1.2,        # Минимальная активность (офис)
        'moderate': 1.375,  # Легкая активность 1-3 раза в неделю
        'high': 1.55,      # Умеренная активность 3-5 раз в неделю
        'very_high': 1.725  # Высокая активность 6-7 раз в неделю
    }
    
    # Корректировки калорий по целям
    GOAL_ADJUSTMENTS = {
        'weight_loss': -0.15,    # -15% от нормы
        'maintenance': 0,        # норма
        'weight_gain': +0.10     # +10% от нормы
    }
    
    @staticmethod
    def calculate_bmr(gender: str, age: int, weight: float, height: int) -> float:
        """
        Расчет базового метаболизма по формуле Миффлина-Сан Жеора
        
        Args:
            gender: 'male' или 'female'
            age: возраст в годах
            weight: вес в кг
            height: рост в см
            
        Returns:
            float: базовый метаболизм в ккал/день
        """
        if gender == 'male':
            return 10 * weight + 6.25 * height - 5 * age + 5
        else:
            return 10 * weight + 6.25 * height - 5 * age - 161
    
    @classmethod
    def calculate_kbju(cls, gender: str, age: int, weight: float, height: int, 
                       activity: str, goal: str) -> dict:
        """
        Полный расчет КБЖУ с учетом активности и цели
        
        Args:
            gender: 'male' или 'female'
            age: возраст в годах
            weight: вес в кг
            height: рост в см
            activity: 'low', 'moderate', 'high', 'very_high'
            goal: 'weight_loss', 'maintenance', 'weight_gain'
            
        Returns:
            dict: словарь с расчитанными КБЖУ
        """
        
        # Валидация входных параметров
        if gender not in ['male', 'female']:
            raise ValueError("Gender must be 'male' or 'female'")
        
        if activity not in cls.ACTIVITY_COEFFICIENTS:
            raise ValueError(f"Activity must be one of {list(cls.ACTIVITY_COEFFICIENTS.keys())}")
            
        if goal not in cls.GOAL_ADJUSTMENTS:
            raise ValueError(f"Goal must be one of {list(cls.GOAL_ADJUSTMENTS.keys())}")
        
        # Базовый метаболизм
        bmr = cls.calculate_bmr(gender, age, weight, height)
        
        # С учетом активности
        calories_maintenance = bmr * cls.ACTIVITY_COEFFICIENTS[activity]
        
        # С учетом цели
        calories_target = calories_maintenance * (1 + cls.GOAL_ADJUSTMENTS[goal])
        
        # Расчет БЖУ (классические пропорции)
        proteins = round(weight * 2.2)  # 2.2г на кг веса
        fats = round(calories_target * 0.25 / 9)  # 25% от калорий
        carbs = round((calories_target - proteins*4 - fats*9) / 4)  # остальное
        
        return {
            'calories': round(calories_target),
            'proteins': proteins,
            'fats': fats,
            'carbs': carbs,
            'bmr': round(bmr)  # для отладки
        }
    
    @staticmethod
    def validate_user_data(gender: str, age: int, weight: float, height: int) -> tuple[bool, str]:
        """
        Валидация пользовательских данных
        
        Returns:
            tuple: (is_valid, error_message)
        """
        
        if gender not in ['male', 'female']:
            return False, "Некорректный пол"
        
        if not (15 <= age <= 80):
            return False, "Возраст должен быть от 15 до 80 лет"
            
        if not (30 <= weight <= 200):
            return False, "Вес должен быть от 30 до 200 кг"
            
        if not (140 <= height <= 220):
            return False, "Рост должен быть от 140 до 220 см"
        
        return True, ""


# Вспомогательные функции для текстового представления

def get_activity_description(activity: str) -> str:
    """Получить описание уровня активности"""
    descriptions = {
        'low': '🛋️ Низкая (офисная работа)',
        'moderate': '🚶 Умеренная (1-3 тренировки в неделю)',
        'high': '🏃 Высокая (3-5 тренировок в неделю)',
        'very_high': '💪 Очень высокая (6-7 тренировок в неделю)'
    }
    return descriptions.get(activity, activity)


def get_goal_description(goal: str) -> str:
    """Получить описание цели"""
    descriptions = {
        'weight_loss': '📉 Похудение',
        'maintenance': '⚖️ Поддержание веса',
        'weight_gain': '📈 Набор массы'
    }
    return descriptions.get(goal, goal)