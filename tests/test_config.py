from lantern_core.config import Settings, settings, sim_hour_to_iso
from tests.conftest import REPO_ROOT


def _env_example_keys() -> list[str]:
    keys = []
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.split("=", 1)[0].strip())
    return keys


def test_every_env_example_key_is_a_settings_field():
    fields = set(Settings.model_fields)
    missing = [k for k in _env_example_keys() if k not in fields]
    assert not missing, f".env.example keys without a Settings field: {missing}"


def test_account_id_expansion():
    s = Settings(_env_file=None, ACCOUNT_ID="123456789012")
    assert s.DATA_BUCKET == "lantern-dev-data-123456789012"
    assert s.WEB_BUCKET == "lantern-dev-web-123456789012"
    assert s.SNS_TOPIC_ARN == "arn:aws:sns:us-east-1:123456789012:lantern-dev-alerts"


def test_csv_lists_parse(monkeypatch):
    monkeypatch.setenv("QUANTILES", "0.1, 0.5,0.9")
    monkeypatch.setenv("DATA_LOSS_LEVELS", "0,40")
    monkeypatch.setenv("CORS_ORIGINS", "http://a,http://b")
    s = Settings(_env_file=None)
    assert s.QUANTILES == [0.1, 0.5, 0.9]
    assert s.DATA_LOSS_LEVELS == [0, 40]
    assert s.CORS_ORIGINS == ["http://a", "http://b"]


def test_defaults_match_contract():
    s = Settings(_env_file=None)
    assert s.LANTERN_MODE == "local"
    assert s.BEDROCK_ENABLED is False and s.NOTIFY_ENABLED is False
    assert s.STALE_QTY_FRAC == 0.04 and s.STALE_SIGMA_FRAC == 0.35
    assert s.SUPPLIES["insulin"]["usage_per_person_per_day"] == 0.01
    assert s.TRANSFER_CAP == {"water": 300, "food": 600, "insulin": 6}
    assert s.MIN_TRANSFER_QTY == {"water": 25, "food": 50, "insulin": 2}
    assert s.DATA_LOSS_LEVELS == [0, 10, 20, 30, 40, 50, 60, 70]


def test_sim_hour_to_iso():
    assert sim_hour_to_iso(0) == settings.SIM_START_TS
    assert sim_hour_to_iso(9, "2026-11-07T08:00:00Z") == "2026-11-07T17:00:00Z"
