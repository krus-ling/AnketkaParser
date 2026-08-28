import asyncio

class BotState:
    def __init__(self):
        self.is_paused = False
        self.is_debug = False
        self.pause_event = None
        self.step_event = None

    def init_events(self):
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Изначально не на паузе
        self.step_event = asyncio.Event()

    async def check_pause(self):
        """Если нажата пауза - бот замирает здесь и ждет снятия."""
        if self.pause_event:
            await self.pause_event.wait()

    async def wait_debug_confirm(self):
        """Если включена отладка - бот ждет ручного клика 'Подтвердить шаг' в GUI."""
        if self.is_debug and self.step_event:
            print("\n[⏳ ОТЛАДКА] Бот заполнил поля. Проверьте ответы в браузере.")
            print("[⏳ ОТЛАДКА] Нажмите кнопку «✅ Подтвердить шаг» в GUI для перехода дальше...")
            self.step_event.clear()
            await self.step_event.wait()
            print("[▶] Шаг подтвержден, переходим на следующую страницу!")

state = BotState()