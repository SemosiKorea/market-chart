from pydantic import SecretStr

from market_signal.security import mask_secret


def test_mask_secret_handles_missing_and_empty_values() -> None:
    assert mask_secret(None) == "<unset>"
    assert mask_secret("") == "<empty>"


def test_mask_secret_hides_short_and_long_values() -> None:
    assert mask_secret("abc") == "***"
    assert mask_secret("abcdefghi") == "*****fghi"
    assert mask_secret(SecretStr("secret-token")) == "********oken"
