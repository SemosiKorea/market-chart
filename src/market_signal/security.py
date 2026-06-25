from pydantic import SecretStr


def mask_secret(value: SecretStr | str | None, *, visible: int = 4) -> str:
    if value is None:
        return "<unset>"

    raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
    if raw_value == "":
        return "<empty>"

    if len(raw_value) <= visible:
        return "*" * len(raw_value)

    return f"{'*' * (len(raw_value) - visible)}{raw_value[-visible:]}"
