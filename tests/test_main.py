import pytest
from unittest.mock import patch


def test_main_help(capsys):
    """--help exits cleanly with usage text."""
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["main", "--help"]):
            from src.main import main
            main()
    assert exc_info.value.code == 0


def test_setup_logging():
    """setup_logging sets the root logger level."""
    import logging
    from src.main import setup_logging
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    setup_logging("INFO")  # restore
