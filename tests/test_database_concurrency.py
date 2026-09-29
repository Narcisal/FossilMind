import json
import multiprocessing

import config
import database

WORKERS = 8
WRITES_PER_WORKER = 25


def _worker(db_file, legacy_file, worker_id, start_event):
    # 模擬 gunicorn 的多個 worker：各自是獨立的行程，同時啟動、同時初始化、同時寫入
    config.DB_FILE = db_file
    config.LEGACY_JSON_FILE = legacy_file
    start_event.wait()
    database.init_db()
    for i in range(WRITES_PER_WORKER):
        chat_id = f"w{worker_id}"
        database.open_chat(chat_id, "並發測試")
        database.save_exchange(chat_id, f"q{i}", f"a{i}", "IDENTIFY")


def test_concurrent_workers_init_and_write_without_losing_data(tmp_path):
    db_file = str(tmp_path / "shared.db")
    legacy_file = tmp_path / "chats.json"
    legacy_file.write_text(json.dumps({"old": {"title": "t", "timestamp": 1.0, "messages": [
        {"role": "user", "content": "舊訊息"}]}}, ensure_ascii=False), encoding="utf-8")

    ctx = multiprocessing.get_context("spawn")
    start = ctx.Event()
    procs = [ctx.Process(target=_worker, args=(db_file, str(legacy_file), n, start)) for n in range(WORKERS)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(timeout=60)

    assert all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs]

    config.DB_FILE = db_file
    for n in range(WORKERS):
        assert len(database.get_messages(f"w{n}")) == WRITES_PER_WORKER * 2
    # 舊紀錄只能被匯入一次
    assert len(database.get_messages("old")) == 1
