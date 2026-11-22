"""The hashed session store, on its own."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Session
from apps.accounts.session_backend import SessionStore, hash_session_key

pytestmark = pytest.mark.django_db


def test_round_trip():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    assert SessionStore(store.session_key)["answer"] == 42
    assert store.exists(store.session_key)


def test_only_the_hash_is_stored():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    row = Session.objects.get()
    assert row.session_key == hash_session_key(store.session_key)
    assert row.session_key != store.session_key
    assert not store.exists(row.session_key), "the stored value must not work as a key"


def test_delete_and_flush():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    key = store.session_key
    store.delete()
    assert not Session.objects.exists()
    assert "answer" not in SessionStore(key)


def test_cycling_the_key_keeps_the_data_and_drops_the_old_row():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    old = store.session_key
    store.cycle_key()
    assert store.session_key != old
    assert list(Session.objects.values_list("session_key", flat=True)) == [
        hash_session_key(store.session_key)
    ]
    assert SessionStore(store.session_key)["answer"] == 42


def test_an_expired_session_is_empty_and_gets_cleared():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
    assert "answer" not in SessionStore(store.session_key)
    SessionStore.clear_expired()
    assert not Session.objects.exists()


def test_the_model_decodes_through_the_same_store():
    store = SessionStore()
    store["answer"] = 42
    store.save()
    assert Session.objects.get().get_decoded() == {"answer": 42}
