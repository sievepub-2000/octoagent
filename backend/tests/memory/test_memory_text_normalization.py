from src.agents.memory.text_normalization import repair_mojibake


def test_repair_mojibake_restores_utf8_chinese() -> None:
    assert repair_mojibake("ä½ å¥½ï¼æ£æ¥è®°å¿") == "你好，检查记忆"


def test_repair_mojibake_preserves_valid_text() -> None:
    assert repair_mojibake("用户偏好 concise answers") == "用户偏好 concise answers"
    assert repair_mojibake("café") == "café"
