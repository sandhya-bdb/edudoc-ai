from src.monitoring import record_token_usage


def test_record_token_usage_none():
    assert record_token_usage(None) == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


class DummyUsage:
    def __init__(self, p, c):
        self.prompt_token_count = p
        self.candidates_token_count = c


def test_record_token_usage_valid():
    usage = DummyUsage(100, 50)
    result = record_token_usage(usage)
    assert result == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
