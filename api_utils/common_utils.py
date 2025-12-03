import random


def random_id(length: int = 24) -> str:
    charset = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(charset) for _ in range(length))
