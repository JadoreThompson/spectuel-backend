from .engine_logger import EngineLogger, Hook


class ShadowEngineLogger(EngineLogger):
    def __init__(
        self,
        name,
        on_log_event=None,
        on_log_command_event=None,
        *,
        on_log_event_request: Hook
    ):
        super().__init__(name, on_log_event, on_log_command_event)
        self.on_log_event_request = on_log_event_request

    def log_event(self, event, kafka_kwargs=None):
        self.on_log_event_request(self._serialise_event(event))
