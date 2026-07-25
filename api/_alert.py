from fastapi.websockets import WebSocket, WebSocketState

from core.abstract.alert import BaseAlert, LEVEL


class AdminAlert(BaseAlert):
    def __init__(self, wb: WebSocket, delete=False):
        super().__init__(delete)
        self._wb = wb

    async def alert(self, message: str, level: LEVEL) -> bool:
        try:
            if self.is_closed():
                return False

            await self._wb.send_json(
                {"signal": "alert", "result": {"message": message, "level": level}}
            )
            return True

        except Exception:
            return False

    def is_closed(self):
        return self._wb.client_state == WebSocketState.DISCONNECTED
