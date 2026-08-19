import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from apps.devices.models import BasketDevice, CheckoutTerminal


ALLOWED_ROLES = {"Administrateur", "Caissier", "Superviseur"}


@database_sync_to_async
def user_has_cashier_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name__in=ALLOWED_ROLES).exists())
    )


@database_sync_to_async
def user_can_manage_rfid_enrollments(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name="Administrateur").exists())
    )


class DomainConsumer(AsyncWebsocketConsumer):
    group_name = None

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def domain_message(self, event):
        await self.send(text_data=json.dumps(event["payload"], default=str))


class CashierTerminalConsumer(DomainConsumer):
    @database_sync_to_async
    def terminal_exists(self, terminal_code):
        return CheckoutTerminal.objects.filter(terminal_code=terminal_code, enabled=True).exists()

    async def connect(self):
        user = self.scope.get("user")
        if not await user_has_cashier_access(user):
            await self.close(code=4403 if getattr(user, "is_authenticated", False) else 4401)
            return
        terminal_code = self.scope["url_route"]["kwargs"]["terminal_code"]
        if not await self.terminal_exists(terminal_code):
            await self.close(code=4404)
            return
        self.group_name = f"cashier_terminal_{terminal_code}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()


class BasketDisplayConsumer(DomainConsumer):
    @database_sync_to_async
    def basket_exists(self, matrix_id):
        return BasketDevice.objects.filter(matrix_id=matrix_id, enabled=True).exists()

    async def connect(self):
        user = self.scope.get("user")
        if not await user_has_cashier_access(user):
            await self.close(code=4403 if getattr(user, "is_authenticated", False) else 4401)
            return
        matrix_id = int(self.scope["url_route"]["kwargs"]["matrix_id"])
        if not await self.basket_exists(matrix_id):
            await self.close(code=4404)
            return
        self.group_name = f"basket_{matrix_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()


class RfidEnrollmentConsumer(DomainConsumer):
    """Live notification channel for users allowed to register physical cards."""

    async def connect(self):
        user = self.scope.get("user")
        if not await user_can_manage_rfid_enrollments(user):
            await self.close(code=4403 if getattr(user, "is_authenticated", False) else 4401)
            return
        self.group_name = "rfid_enrollment"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
