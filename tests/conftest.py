import os

# 測試環境不需要真的金鑰 —— config.py 只是要求「有值」，實際呼叫 LLM 的地方
# 在測試裡全部被 mock 掉，不會真的發送任何請求。這行必須在任何 import config
# （或間接 import 到 config 的模組，如 backend / app）之前執行。
os.environ.setdefault("FOSSILMIND_API_KEY", "test-dummy-key-not-a-real-secret")
