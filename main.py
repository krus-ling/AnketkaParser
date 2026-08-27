import asyncio
from brain import SurveyBrain
from engines import SurveyRouter

async def main():
    survey_url = input("Вставь ссылку на опрос: ").strip()
    if not survey_url:
        print("Ссылка не указана.")
        return

    # Настройки подтягиваются автоматически из config.py
    brain = SurveyBrain()
    router = SurveyRouter(brain=brain)
    await router.run(survey_url)

if __name__ == "__main__":
    asyncio.run(main())