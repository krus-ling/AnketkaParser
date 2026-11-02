import os
import sys
from datetime import datetime
from core import config

class SessionLogger:
    """Записывает все логи сессии бота в отдельный файл в data/session_logs/."""
    _instance = None

    def __init__(self):
        self.log_dir = os.path.join(config.BASE_DIR, "data", "session_logs")
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(self.log_dir, f"session_{timestamp}.log")
        self._fp = None
        self._stdout_orig = sys.stdout
        self._stderr_orig = sys.stderr

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SessionLogger()
        return cls._instance

    def start(self):
        try:
            self._fp = open(self.log_file, "a", encoding="utf-8", buffering=1)
            sys.stdout = _TeeStream(self._stdout_orig, self._fp)
            sys.stderr = _TeeStream(self._stderr_orig, self._fp)
            print(f"[📝] [ЛОГ СЕССИИ] Запись логов активирована: {self.log_file}")
        except Exception as e:
            print(f"[!] Не удалось активировать лог сессии: {e}")

    def stop(self):
        try:
            if self._fp:
                sys.stdout = self._stdout_orig
                sys.stderr = self._stderr_orig
                self._fp.close()
                self._fp = None
        except Exception:
            pass

class _TeeStream:
    def __init__(self, original_stream, file_stream):
        self.original_stream = original_stream
        self.file_stream = file_stream

    def write(self, data):
        try:
            self.original_stream.write(data)
        except Exception:
            pass
        try:
            if self.file_stream:
                self.file_stream.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass
        try:
            if self.file_stream:
                self.file_stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self.original_stream, name)

session_logger = SessionLogger.get_instance()
