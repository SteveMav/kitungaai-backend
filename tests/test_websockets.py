from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase

from apps.devices.models import CheckoutTerminal
from core.asgi import application


class WebSocketAuthorizationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.terminal = CheckoutTerminal(terminal_code="CAISSE-WS")
        self.terminal.set_secret("terminal-websocket-test-secret-123")
        self.terminal.save()

    async def _anonymous_connect(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/v1/cashier/terminals/{self.terminal.terminal_code}/",
        )
        return await communicator.connect()

    def test_anonymous_connection_is_rejected(self):
        connected, close_code = async_to_sync(self._anonymous_connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def _authenticated_connect(self, cookie):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/v1/cashier/terminals/{self.terminal.terminal_code}/",
            headers=[(b"cookie", cookie.encode("ascii"))],
        )
        connected, detail = await communicator.connect()
        if connected:
            await communicator.disconnect()
        return connected, detail

    def test_cashier_session_can_connect_to_enabled_terminal(self):
        user = get_user_model().objects.create_user(
            username="cashier-ws",
            password="strong-test-password",
        )
        user.groups.add(Group.objects.get(name="Caissier"))
        self.client.force_login(user)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        connected, _detail = async_to_sync(self._authenticated_connect)(
            f"{settings.SESSION_COOKIE_NAME}={session_cookie}"
        )
        self.assertTrue(connected)

    async def _rfid_enrollment_connect(self, cookie=None):
        headers = [(b"cookie", cookie.encode("ascii"))] if cookie else None
        communicator = WebsocketCommunicator(
            application,
            "/ws/v1/rfid-enrollments/",
            headers=headers,
        )
        connected, detail = await communicator.connect()
        if connected:
            await communicator.disconnect()
        return connected, detail

    def test_only_administrators_can_connect_to_rfid_enrollment_notifications(self):
        connected, close_code = async_to_sync(self._rfid_enrollment_connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

        cashier = get_user_model().objects.create_user(
            username="cashier-rfid-ws",
            password="strong-test-password",
        )
        cashier.groups.add(Group.objects.get(name="Caissier"))
        self.client.force_login(cashier)
        cashier_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        connected, close_code = async_to_sync(self._rfid_enrollment_connect)(
            f"{settings.SESSION_COOKIE_NAME}={cashier_cookie}"
        )
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

        administrator = get_user_model().objects.create_superuser(
            username="administrator-rfid-ws",
            password="strong-test-password",
        )
        self.client.force_login(administrator)
        administrator_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        connected, _detail = async_to_sync(self._rfid_enrollment_connect)(
            f"{settings.SESSION_COOKIE_NAME}={administrator_cookie}"
        )
        self.assertTrue(connected)
