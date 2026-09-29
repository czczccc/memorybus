import pytest

from memorybus.secret_filter import find_secrets


@pytest.mark.parametrize(
    "text",
    [
        "my key is sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "password: hunter2!!",
        "我的密码是 abc12345",
        "card 4111 1111 1111 1111",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        "my recovery phrase is apple banana ...",
        "verification code: 482913",
    ],
)
def test_detects_secrets(text):
    assert find_secrets(text)


@pytest.mark.parametrize(
    "text",
    [
        "User uses Windows + WSL for development.",
        "以后我的 Python 项目默认使用 uv。",
        "JobAgent Studio uses Next.js and PostgreSQL.",
        "User's phone number format preference is international",
        "Order 1234 5678 shipped",
    ],
)
def test_allows_normal_memories(text):
    assert find_secrets(text) == []
