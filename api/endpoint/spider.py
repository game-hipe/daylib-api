import asyncio
import json
from typing import Literal

from fastapi import Body, HTTPException, Query
from fastapi.websockets import WebSocket, WebSocketDisconnect

from core.manager.spider._status import SpiderStatusSnapshotSchema
from core.spider import __all__

from .._alert import AdminAlert
from ..base import BaseAPI

TaskState = Literal[
    "pending",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "idle",
    "all",
]

Spider = Literal[*__all__]  # NOTE: По большей части просто для FastAPI, а не для mypy


class SpiderAPI(BaseAPI):
    def _connect_endpoint(self):
        self.add_api_route("/status", self.get_status, methods=["GET"])
        self.add_api_route("/recover", self.recover_spider, methods=["POST"])
        self.add_api_route("/start", self.start_spider, methods=["POST"])
        self.add_api_route("/stop", self.stop_spider, methods=["POST"])
        self.add_api_route("/start/all", self.start_all_spider, methods=["POST"])
        self.add_api_route("/stop/all", self.stop_all_spider, methods=["POST"])
        self.add_api_websocket_route("/ws", self.status_websocket)

    async def start_spider(
        self,
        *,
        spider: Spider = Query(...),
        start_page: int = Query(1, ge=1),
        pagination_kwargs: dict | None = Body(None),
        update: bool = Query(False),
        force: bool = Query(False),
    ) -> SpiderStatusSnapshotSchema:
        status = await self.content.spider.start_spider(
            spider=spider,
            start_page=start_page,
            pagination_kwargs=pagination_kwargs,
            update=update,
            force=force,
        )
        return SpiderStatusSnapshotSchema.model_validate(status.to_snapshot())

    async def stop_spider(
        self,
        *,
        spider: Spider = Query(...),
    ) -> SpiderStatusSnapshotSchema:
        try:
            status = await self.content.spider.stop_spider(spider)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return SpiderStatusSnapshotSchema.model_validate(status.to_snapshot())

    async def start_all_spider(self) -> list[SpiderStatusSnapshotSchema]:
        return [
            SpiderStatusSnapshotSchema.model_validate(x.to_snapshot())
            for x in await self.content.spider.start_all_spider()
        ]

    async def stop_all_spider(self) -> None:
        await self.content.spider.stop_all_spider()

    async def get_status(self) -> list[SpiderStatusSnapshotSchema]:
        return [
            SpiderStatusSnapshotSchema.model_validate(x.to_snapshot())
            for x in await self.content.spider.get_status()
        ]

    async def status_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()

        alert = AdminAlert(websocket, True)
        await self.content.alert.add_alert(alert)

        async def send_status():
            last_hash: int | None = None
            stop = False

            while True:
                try:
                    snapshots = [
                        x.model_dump(mode="json", exclude=["created_at", "updated_at"])
                        for x in await self.get_status()
                    ]
                    current_hash = hash(json.dumps(snapshots))

                    if current_hash != last_hash:
                        await websocket.send_json(
                            {"signal": "spider", "result": snapshots}
                        )
                        last_hash = current_hash

                    await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    stop = True
                    return

                except WebSocketDisconnect:
                    stop = True
                    return

                finally:
                    if stop:
                        try:
                            await websocket.close()
                        except RuntimeError:
                            pass

        try:
            await send_status()
        except RuntimeError:
            pass
        finally:
            try:
                await self.content.alert.delete_alert(alert)
                await websocket.close()
            except RuntimeError:
                pass
            except ValueError:
                pass

    async def recover_spider(
        self,
        *,
        state: TaskState = Query("idle", description="Состояние задачи"),
    ) -> None:
        await self.content.spider.recover(state)
