import aiohttp
import asyncio
import logging
from typing import Dict, Any

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_ENDPOINT

logger = logging.getLogger(__name__)


async def generate_ai_recommendations(user_data: Dict[str, Any]) -> str:
    """
    Генерирует персонализированные рекомендации через OpenRouter GPT-4 mini

    Args:
        user_data: Словарь с данными пользователя:
            - gender: "male" / "female"
            - age: int
            - weight: float
            - height: int
            - target_weight: float
            - current_body_type: str
            - target_body_type: str
            - timezone: str
            - activity: str
            - goal: str
            - calories: int
            - proteins: int
            - fats: int
            - carbs: int

    Returns:
        Текст рекомендаций в формате HTML

    Raises:
        ValueError: Если API ключ не настроен
        Exception: Если запрос к API не удался
    """

    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not configured")
        raise ValueError("OpenRouter API key not configured")

    # Формируем промпт
    prompt = _build_prompt(user_data)

    # Отправляем запрос
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ты профессиональный фитнес-тренер и нутрициолог. Говори на 'ты'."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1200,
        "temperature": 0.7,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                    raise Exception(f"OpenRouter API returned {resp.status}")

                data = await resp.json()

                if 'choices' not in data or not data['choices']:
                    logger.error(f"Invalid OpenRouter response: {data}")
                    raise Exception("Invalid response from OpenRouter")

                result = data['choices'][0]['message']['content']
                logger.info(f"AI recommendations generated (length: {len(result)})")
                return result

    except asyncio.TimeoutError:
        logger.error("OpenRouter API timeout")
        raise Exception("AI service timeout")
    except Exception as e:
        logger.exception(f"Failed to generate AI recommendations: {e}")
        raise


def _build_prompt(user_data: Dict[str, Any]) -> str:
    """Создать промпт для AI на основе данных пользователя"""

    gender_ru = "мужской" if user_data.get('gender') == 'male' else "женский"

    goal_map = {
        'weight_loss': 'Похудение',
        'weight_gain': 'Набор массы',
        'maintenance': 'Поддержание веса'
    }
    goal_ru = goal_map.get(user_data.get('goal', ''), user_data.get('goal', ''))

    activity_map = {
        'low': 'Низкая (сидячая работа)',
        'moderate': 'Средняя (легкие тренировки 1-3 раза в неделю)',
        'high': 'Высокая (интенсивные тренировки 4-5 раз в неделю)',
        'very_high': 'Очень высокая (ежедневные тренировки)'
    }
    activity_ru = activity_map.get(user_data.get('activity', ''), user_data.get('activity', ''))

    weight_diff = user_data.get('weight', 0) - user_data.get('target_weight', 0)

    prompt = f"""
Проанализируй данные клиента и дай персонализированный ответ.

📋 Данные клиента:
• Пол: {gender_ru}
• Возраст: {user_data.get('age')} лет
• Рост: {user_data.get('height')} см
• Текущий вес: {user_data.get('weight')} кг
• Желаемый вес: {user_data.get('target_weight')} кг
• Разница: {abs(weight_diff):.1f} кг {'(сбросить)' if weight_diff > 0 else '(набрать)'}
• Уровень активности: {activity_ru}
• Цель: {goal_ru}
• Текущий тип фигуры: тип {user_data.get('current_body_type')}
• Желаемый тип фигуры: тип {user_data.get('target_body_type')}
• Часовой пояс: {user_data.get('timezone')}

📊 Рассчитанные КБЖУ:
• Калории: {user_data.get('calories')} ккал/день
• Белки: {user_data.get('proteins')} г
• Жиры: {user_data.get('fats')} г
• Углеводы: {user_data.get('carbs')} г

---

Дай ответ СТРОГО в следующем формате (используй эмодзи и структуру):

📊 <b>Анализ текущего состояния</b>
[2-3 предложения: BMI, оценка веса, примерный процент жира, тип фигуры]

🎯 <b>Безопасные цели</b>
[Реалистичный срок достижения цели, темп снижения/набора веса в неделю с учетом безопасности]

🎨 <b>Ожидаемые изменения</b>
• [конкретное изменение 1]
• [конкретное изменение 2]
• [конкретное изменение 3]

🏋️ <b>Целевые тренировки</b>
• [частота тренировок в неделю]
• [тип нагрузок: силовые/кардио/интервалы/баланс]

🍽 <b>Рамки по питанию</b>
[Краткие принципы питания: дефицит/профицит калорий, распределение БЖУ, примеры продуктов.
Упомяни, что точные цифры индивидуальны и тренер должен погрузиться в ситуацию клиента]

---

⚠️ Важно:
- Будь кратким (до 800 символов)
- Используй ТОЛЬКО указанные секции с эмодзи
- Не добавляй дополнительные разделы
- Говори на "ты", по-русски
- Используй HTML-теги <b> для жирного текста
- НЕ используй markdown (**text**), только HTML
"""

    return prompt
