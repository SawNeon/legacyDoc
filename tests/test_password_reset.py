"""Password reset: what the email carries, who can use it, and what it ends."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from legacydoc_core import email as email_module
from legacydoc_core.models import ApiKey, PasswordResetToken, User
from legacydoc_core.security import RESET_COOLDOWN_SECONDS, RESET_TOKEN_TTL_MINUTES
from sqlalchemy import select

PASSWORD = "senha-bem-longa-123"
NEW_PASSWORD = "nova-senha-forte-9"
REQUEST = "/v1/auth/password-reset/request"
CONFIRM = "/v1/auth/password-reset/confirm"


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def token(self, index: int = -1) -> str:
        match = re.search(r"token=([A-Za-z0-9_\-]+)", self.sent[index][2])
        assert match, self.sent[index][2]

        return match.group(1)


class BrokenSender:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        raise ConnectionRefusedError("smtp fora do ar")


@pytest.fixture
def mailbox(monkeypatch) -> RecordingSender:
    sender = RecordingSender()
    monkeypatch.setattr("legacydoc_api.routers.auth.get_email_sender", lambda settings: sender)

    return sender


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"r-{uuid.uuid4().hex[:10]}@exemplo.com"
    response = await client.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/v1/auth/login", json={"email": email, "password": password})


async def _user(session, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def _confirm(client: AsyncClient, token: str, password: str = NEW_PASSWORD):
    return await client.post(CONFIRM, json={"token": token, "new_password": password})


async def _skip_cooldown(session, email: str) -> None:
    user = await _user(session, email)
    tokens = (
        (
            await session.execute(
                select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    for token in tokens:
        token.expires_at = token.expires_at - timedelta(seconds=RESET_COOLDOWN_SECONDS + 5)
    await session.commit()


class TestTheEmail:
    async def test_the_link_carries_the_token_in_the_fragment(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)

        await client.post(REQUEST, json={"email": email})

        body = mailbox.sent[0][2]
        assert "/nova-senha#token=" in body
        assert "?token=" not in body

    async def test_the_email_goes_to_the_account_address(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)

        await client.post(REQUEST, json={"email": f"  {email.upper()}  "})

        assert [item[0] for item in mailbox.sent] == [email]

    async def test_the_email_states_the_validity(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)

        await client.post(REQUEST, json={"email": email})

        assert f"{RESET_TOKEN_TTL_MINUTES} minutos" in mailbox.sent[0][2]

    async def test_an_unknown_address_gets_no_email(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        response = await client.post(REQUEST, json={"email": "ninguem@exemplo.com"})

        assert response.status_code == 202
        assert mailbox.sent == []

    async def test_a_disabled_account_gets_no_email_and_the_same_answer(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        (await _user(session, email)).is_active = False
        await session.commit()

        response = await client.post(REQUEST, json={"email": email})
        other = await client.post(REQUEST, json={"email": "ninguem@exemplo.com"})

        assert mailbox.sent == []
        assert response.status_code == other.status_code == 202
        assert response.json() == other.json()

    async def test_the_console_backend_prints_the_link_for_development(
        self, client: AsyncClient, caplog
    ):
        _, email = await _register(client)

        with caplog.at_level(logging.WARNING, logger="legacydoc_core.email"):
            await client.post(REQUEST, json={"email": email})

        assert "nova-senha#token=" in caplog.text


class TestDeliveryFailure:
    async def test_a_broken_mail_server_does_not_change_the_answer(
        self, client: AsyncClient, monkeypatch
    ):
        _, email = await _register(client)
        healthy = await client.post(REQUEST, json={"email": "ninguem@exemplo.com"})

        monkeypatch.setattr(
            "legacydoc_api.routers.auth.get_email_sender", lambda settings: BrokenSender()
        )
        broken = await client.post(REQUEST, json={"email": email})

        assert broken.status_code == 202
        assert broken.json() == healthy.json()

    async def test_the_failure_is_logged_without_the_token(
        self, client: AsyncClient, monkeypatch, caplog
    ):
        _, email = await _register(client)
        monkeypatch.setattr(
            "legacydoc_api.routers.auth.get_email_sender", lambda settings: BrokenSender()
        )

        with caplog.at_level(logging.ERROR):
            await client.post(REQUEST, json={"email": email})

        assert "Falha ao enviar" in caplog.text
        assert "token=" not in caplog.text

    async def test_the_token_is_stored_even_if_the_delivery_fails(
        self, client: AsyncClient, session, monkeypatch
    ):
        _, email = await _register(client)
        monkeypatch.setattr(
            "legacydoc_api.routers.auth.get_email_sender", lambda settings: BrokenSender()
        )

        await client.post(REQUEST, json={"email": email})

        rows = (await session.execute(select(PasswordResetToken))).scalars().all()
        assert len(rows) == 1

    async def test_the_token_is_stored_before_the_email_leaves(
        self, client: AsyncClient, session, monkeypatch
    ):
        _, email = await _register(client)
        seen: list[int] = []

        class Probe:
            async def send(self, *, to: str, subject: str, body: str) -> None:
                token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)
                seen.append((await _confirm_probe(client, token)).status_code)

        async def _confirm_probe(http: AsyncClient, token: str):
            return await _confirm(http, token, NEW_PASSWORD)

        monkeypatch.setattr("legacydoc_api.routers.auth.get_email_sender", lambda s: Probe())

        await client.post(REQUEST, json={"email": email})

        assert seen == [200], "the link must already work when the email is delivered"


class TestCooldown:
    async def test_a_second_request_within_the_window_sends_nothing(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)

        first = await client.post(REQUEST, json={"email": email})
        second = await client.post(REQUEST, json={"email": email})

        assert len(mailbox.sent) == 1
        assert first.json() == second.json()
        assert second.status_code == 202

    async def test_the_first_link_keeps_working_after_a_throttled_request(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await client.post(REQUEST, json={"email": email})

        assert (await _confirm(client, mailbox.token())).status_code == 200

    async def test_after_the_window_a_new_request_sends_again(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await _skip_cooldown(session, email)

        await client.post(REQUEST, json={"email": email})

        assert len(mailbox.sent) == 2

    async def test_a_new_link_cancels_the_previous_one(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await _skip_cooldown(session, email)
        await client.post(REQUEST, json={"email": email})

        assert (await _confirm(client, mailbox.token(0))).status_code == 401
        assert (await _confirm(client, mailbox.token(1))).status_code == 200

    async def test_the_cooldown_is_per_account(self, client: AsyncClient, mailbox: RecordingSender):
        _, first = await _register(client)
        _, second = await _register(client)

        await client.post(REQUEST, json={"email": first})
        await client.post(REQUEST, json={"email": second})

        assert sorted(item[0] for item in mailbox.sent) == sorted([first, second])


class TestConfirming:
    async def test_the_new_password_replaces_the_old_one(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        response = await _confirm(client, mailbox.token())

        assert response.status_code == 200
        assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
        assert (await _login(client, email, PASSWORD)).status_code == 401

    async def test_the_session_returned_works(self, client: AsyncClient, mailbox: RecordingSender):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        token = (await _confirm(client, mailbox.token())).json()["access_token"]
        me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert me.status_code == 200
        assert me.json()["email"] == email

    async def test_a_weak_password_does_not_burn_the_link(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        weak = await _confirm(client, mailbox.token(), "123")
        retry = await _confirm(client, mailbox.token(), NEW_PASSWORD)

        assert weak.status_code == 422
        assert retry.status_code == 200

    async def test_an_all_numeric_password_is_refused(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        assert (await _confirm(client, mailbox.token(), "1234567890123")).status_code == 422

    async def test_the_link_works_only_once(self, client: AsyncClient, mailbox: RecordingSender):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        first = await _confirm(client, mailbox.token())
        second = await _confirm(client, mailbox.token(), "outra-senha-forte-7")

        assert (first.status_code, second.status_code) == (200, 401)
        assert (await _login(client, email, NEW_PASSWORD)).status_code == 200

    async def test_two_simultaneous_confirmations_let_only_one_through(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        token = mailbox.token()

        results = await asyncio.gather(
            _confirm(client, token, "senha-da-aba-um-11"),
            _confirm(client, token, "senha-da-aba-dois-22"),
        )

        assert sorted(response.status_code for response in results) == [200, 401]

    async def test_an_expired_link_is_refused_with_a_clear_message(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        row = (await session.execute(select(PasswordResetToken))).scalars().one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        response = await _confirm(client, mailbox.token())

        assert response.status_code == 401
        assert "expirado" in response.json()["message"].lower()

    async def test_an_expired_link_does_not_change_the_password(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        row = (await session.execute(select(PasswordResetToken))).scalars().one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

        await _confirm(client, mailbox.token())

        assert (await _login(client, email, PASSWORD)).status_code == 200

    async def test_a_link_for_a_disabled_account_is_refused(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        (await _user(session, email)).is_active = False
        await session.commit()

        assert (await _confirm(client, mailbox.token())).status_code == 401

    @pytest.mark.parametrize("token", ["curto", "x" * 15, "token-falso-que-nao-existe-mesmo"])
    async def test_made_up_tokens_are_refused(self, client: AsyncClient, token: str):
        response = await _confirm(client, token)

        assert response.status_code in (401, 422)

    async def test_the_token_is_not_stored_in_clear(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        row = (await session.execute(select(PasswordResetToken))).scalars().one()

        assert mailbox.token() not in row.token_hash
        assert row.token_hash != mailbox.token()

    async def test_the_link_of_one_account_never_resets_another(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, victim = await _register(client)
        _, attacker = await _register(client)
        await client.post(REQUEST, json={"email": attacker})

        await _confirm(client, mailbox.token())

        assert (await _login(client, victim, PASSWORD)).status_code == 200
        assert (await _login(client, victim, NEW_PASSWORD)).status_code == 401

    async def test_proving_email_access_clears_a_lock(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        from legacydoc_core.security import MAX_FAILED_LOGINS

        _, email = await _register(client)

        for _ in range(MAX_FAILED_LOGINS):
            await _login(client, email, "senha-errada-123")

        assert (await _login(client, email, PASSWORD)).status_code == 401

        await client.post(REQUEST, json={"email": email})
        await _confirm(client, mailbox.token())

        assert (await _login(client, email, NEW_PASSWORD)).status_code == 200


class TestWhatTheResetEnds:
    async def test_a_session_from_before_the_reset_stops_working(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        headers, email = await _register(client)
        assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

        (await _user(session, email)).password_changed_at = datetime.now(UTC) + timedelta(seconds=5)
        await session.commit()

        assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401

    async def test_the_real_reset_ends_the_old_session(
        self, client: AsyncClient, session, mailbox: RecordingSender, monkeypatch
    ):
        headers, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await asyncio.sleep(1.1)

        await _confirm(client, mailbox.token())

        assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401

    async def test_the_session_issued_by_the_reset_is_not_ended_by_it(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})

        token = (await _confirm(client, mailbox.token())).json()["access_token"]

        for _ in range(3):
            ok = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert ok.status_code == 200

    async def test_a_session_taken_after_the_reset_works(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await _confirm(client, mailbox.token())

        token = (await _login(client, email, NEW_PASSWORD)).json()["access_token"]

        me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200

    async def test_api_keys_made_before_the_reset_are_revoked(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        headers, email = await _register(client)
        key = (
            await client.post("/v1/auth/api-keys", json={"name": "vscode"}, headers=headers)
        ).json()["api_key"]
        await client.post(REQUEST, json={"email": email})

        await _confirm(client, mailbox.token())

        me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
        assert me.status_code == 401
        revoked = (await session.execute(select(ApiKey))).scalars().all()
        assert all(item.revoked_at is not None for item in revoked)

    async def test_a_key_created_after_the_reset_works(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        token = (await _confirm(client, mailbox.token())).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        key = (
            await client.post("/v1/auth/api-keys", json={"name": "novo"}, headers=headers)
        ).json()["api_key"]

        me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
        assert me.status_code == 200

    async def test_other_pending_links_of_the_account_die_with_the_reset(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        first = mailbox.token()
        session.add(
            PasswordResetToken(
                user_id=(await _user(session, email)).id,
                token_hash="b" * 64,
                expires_at=datetime.now(UTC) + timedelta(minutes=20),
            )
        )
        await session.commit()

        await _confirm(client, first)

        pending = (
            (
                await session.execute(
                    select(PasswordResetToken).where(PasswordResetToken.used_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        assert pending == []

    async def test_the_moment_of_the_change_is_recorded(
        self, client: AsyncClient, session, mailbox: RecordingSender
    ):
        _, email = await _register(client)
        assert (await _user(session, email)).password_changed_at is None
        await client.post(REQUEST, json={"email": email})

        await _confirm(client, mailbox.token())

        session.expire_all()
        changed = (await _user(session, email)).password_changed_at
        assert changed is not None

    async def test_another_account_is_untouched_by_the_reset(
        self, client: AsyncClient, mailbox: RecordingSender
    ):
        other_headers, _ = await _register(client)
        _, email = await _register(client)
        await client.post(REQUEST, json={"email": email})
        await asyncio.sleep(1.1)

        await _confirm(client, mailbox.token())

        assert (await client.get("/v1/auth/me", headers=other_headers)).status_code == 200


class TestPlumbing:
    def test_the_cooldown_is_shorter_than_the_link_lifetime(self):
        assert 0 < RESET_COOLDOWN_SECONDS < RESET_TOKEN_TTL_MINUTES * 60

    def test_the_console_sender_is_the_default_without_smtp(self, settings):
        assert isinstance(email_module.get_email_sender(settings), email_module.ConsoleEmailSender)
