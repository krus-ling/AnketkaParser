from playwright.async_api import Page
from engines.js_snippets import JS_SYNC_MEMORY


class DOMSynchronizer:
    """
    Отвечает за сбор фактически выбранных вариантов на странице
    и сохранение их в локальную базу данных (память).
    """

    @staticmethod
    async def sync_memory(page: Page, brain):
        try:
            data = await page.evaluate(JS_SYNC_MEMORY)

            if not data:
                return

            for item in data:
                q_text = item['q']
                if item['type'] == 'text':
                    brain.memory.save_record(
                        q_text, "open_text", None, item['val'], item['val'],
                        "Синхронизировано со страницей (финальный ответ)"
                    )
                elif item['type'] in ['choices', 'select']:
                    q_type = "multiselect" if len(item['indices']) > 1 else "single"
                    brain.memory.save_record(
                        q_text, q_type, item['opts'], item['indices'], item['texts'],
                        "Синхронизировано со страницей (финальный ответ)"
                    )

        except Exception as e:
            print(f"[!] Ошибка фоновой синхронизации памяти: {e}")