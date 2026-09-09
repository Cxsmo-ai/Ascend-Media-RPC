from src.core.instance_lock import SingleInstanceLock


def test_single_instance_lock_rejects_second_owner(tmp_path):
    first = SingleInstanceLock(str(tmp_path))
    second = SingleInstanceLock(str(tmp_path))
    assert first.acquire() is True
    try:
        assert second.acquire() is False
        assert second.owner and second.owner.get("pid")
    finally:
        first.release()
    assert second.acquire() is True
    second.release()
