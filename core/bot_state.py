import asyncio


class BotState:
    def __init__(self):
        self.is_paused = False
        self.is_debug = False
        self.pause_event = None
        self.step_event = None

        # Ссылки на активный сеанс браузера
        self.active_page = None
        self.active_engine = None

        # Флаги для кнопки «Ответить иначе»
        self.force_alternative = False
        self.step_decision = "CONFIRM"

    def init_events(self):
        self.pause_event = asyncio.Event()
        self.pause_event.set()
        self.step_event = asyncio.Event()
        self.step_decision = "CONFIRM"

    async def check_pause(self):
        """Если нажата пауза — бот замирает здесь и ждет снятия."""
        if self.pause_event:
            await self.pause_event.wait()

    async def wait_debug_confirm(self) -> str:
        """Ждет нажатия 'Подтвердить шаг' (CONFIRM) или 'Ответить иначе' (RETRY)."""
        if not self.is_debug:
            return "CONFIRM"

        self.step_decision = "CONFIRM"
        if self.step_event:
            self.step_event.clear()
            print("\n[⏳ ОТЛАДКА] Бот заполнил поля. Проверьте ответы в браузере.")
            print("[⏳ ОТЛАДКА] Нажмите «✅ Подтвердить шаг» или «🔄 Ответить иначе» в панели GUI...")
            await self.step_event.wait()

        decision = getattr(self, "step_decision", "CONFIRM")
        if decision == "CONFIRM":
            print("[▶] Шаг подтвержден, переходим на следующую страницу!")
        return decision


state = BotState()