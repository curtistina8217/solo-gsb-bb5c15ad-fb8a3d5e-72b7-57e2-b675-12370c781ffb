"""GET /designs/{id}/threshold-profile 的接口集成测试。

使用临时 SQLite 文件与 FastAPI TestClient，不依赖运行中的服务，也不触碰
仓库默认的 data/weave.db。直接执行：python3 tests/test_api_threshold_profile.py
（也可被 pytest 收集）。
"""

import os
import sys
import tempfile

_TMP_DB = tempfile.NamedTemporaryFile(prefix="weave-test-", suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_PATH"] = _TMP_DB.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def test_threshold_profile_endpoint():
    with TestClient(app) as client:
        # 不存在的设计 -> 404
        resp = client.get("/designs/99999/threshold-profile")
        check(resp.status_code == 404, "missing design returns 404")
        check(resp.json()["detail"] == "design 99999 not found", "404 detail message")

        # 循环单列 [1,1,0,1,1]：跨边界合并为一段长度 4 的经向浮长
        cyclic_col = {
            "name": "cyclic column",
            "cyclic": True,
            "max_float": 2,
            "threading": [0],
            "tie_up": [[1], [0]],
            "treadling": [0, 0, 1, 0, 0],
        }
        cid = client.post("/designs", json=cyclic_col).json()["id"]

        # 默认上限 = 原设计 max_float（2）
        resp = client.get(f"/designs/{cid}/threshold-profile")
        check(resp.status_code == 200, "cyclic column endpoint 200")
        data = resp.json()
        check(data["design_id"] == cid, "design_id echoed")
        check(data["cyclic"] is True, "cyclic flag echoed")
        check(data["max_float_limit"] == 2, "default limit is design max_float")
        check(len(data["entries"]) == 2, "one entry per threshold 1..limit")
        check([e["threshold"] for e in data["entries"]] == [1, 2],
              "thresholds ascend from 1")
        # 合并段长 4：阈值 1、2 下各 1 条经向违规，无纬向违规
        for entry in data["entries"]:
            check(entry["warp_violations"] == 1
                  and entry["weft_violations"] == 0
                  and entry["total_violations"] == 1,
                  f"cyclic merged run violates at threshold {entry['threshold']}")
        check(data["min_zero_violation_threshold"] is None,
              "no zero-violation threshold within 1..2")

        # 显式上限 4：合并段长 4 在阈值 4 处归零
        data = client.get(
            f"/designs/{cid}/threshold-profile?max_float_limit=4"
        ).json()
        check(data["max_float_limit"] == 4, "explicit limit echoed")
        check([e["total_violations"] for e in data["entries"]] == [1, 1, 1, 0],
              "cyclic merged run of 4 clears at threshold 4")
        check(data["min_zero_violation_threshold"] == 4,
              "min zero-violation threshold is 4 (cyclic merge preserved)")

        # 同一矩阵非循环：两段长度 2，阈值 1 下 2 条违规，阈值 2 起归零
        non_cyclic = {**cyclic_col, "name": "non-cyclic column", "cyclic": False}
        nid = client.post("/designs", json=non_cyclic).json()["id"]
        data = client.get(
            f"/designs/{nid}/threshold-profile?max_float_limit=4"
        ).json()
        entries = data["entries"]
        check(entries[0]["warp_violations"] == 2
              and entries[0]["total_violations"] == 2,
              "non-cyclic: two separate runs of 2 at threshold 1")
        check([e["total_violations"] for e in entries] == [2, 0, 0, 0],
              "non-cyclic: runs of 2 clear from threshold 2")
        check(data["min_zero_violation_threshold"] == 2,
              "non-cyclic min zero-violation threshold is 2")

        # 纬向违规：整行连续 0 浮长 3，逐档统计到阈值 3 归零
        weft_row = {
            "name": "weft row",
            "max_float": 1,
            "threading": [0, 0, 0],
            "tie_up": [[0], [1]],
            "treadling": [0, 1],
        }
        wid = client.post("/designs", json=weft_row).json()["id"]
        data = client.get(
            f"/designs/{wid}/threshold-profile?max_float_limit=3"
        ).json()
        check([e["weft_violations"] for e in data["entries"]] == [1, 1, 0],
              "weft run of 3 violates below threshold 3")
        check([e["warp_violations"] for e in data["entries"]] == [0, 0, 0],
              "no warp violations in weft-row design")
        check(data["min_zero_violation_threshold"] == 3,
              "weft run of 3 clears at threshold 3")

        # 平纹 4x4：任何阈值下都无违规，最小零违规阈值为 1
        plain = {
            "name": "plain",
            "max_float": 2,
            "threading": [0, 1, 0, 1],
            "tie_up": [[1, 0], [0, 1]],
            "treadling": [0, 1, 0, 1],
        }
        pid = client.post("/designs", json=plain).json()["id"]
        data = client.get(f"/designs/{pid}/threshold-profile").json()
        check(all(e["total_violations"] == 0 for e in data["entries"]),
              "plain weave: zero violations at every threshold")
        check(data["min_zero_violation_threshold"] == 1,
              "plain weave: zero violations already at threshold 1")

        # 上限越界 -> 422
        resp = client.get(f"/designs/{pid}/threshold-profile?max_float_limit=0")
        check(resp.status_code == 422, "max_float_limit=0 rejected (422)")
        resp = client.get(f"/designs/{pid}/threshold-profile?max_float_limit=65")
        check(resp.status_code == 422, "max_float_limit=65 rejected (422)")

        # 原设计 max_float 超过 64 时，默认上限按 64 截断
        big = {
            "name": "big max_float",
            "max_float": 100,
            "threading": [0, 1],
            "tie_up": [[1, 0], [0, 1]],
            "treadling": [0, 1],
        }
        bid = client.post("/designs", json=big).json()["id"]
        data = client.get(f"/designs/{bid}/threshold-profile").json()
        check(data["max_float_limit"] == 64 and len(data["entries"]) == 64,
              "default limit clamps to 64 when design max_float exceeds it")
        check(data["min_zero_violation_threshold"] == 1,
              "plain 2x2: zero violations already at threshold 1")

        # 接口只读，不改变设计与其审计结果
        again = client.get(f"/designs/{cid}").json()
        check(again["max_float"] == 2 and again["cyclic"] is True,
              "threshold-profile does not modify the stored design")
        check(again["audit"]["violations"] == [
            {"direction": "warp", "yarn_index": 0, "start": 3, "length": 4}
        ], "stored audit unchanged after threshold-profile")


if __name__ == "__main__":
    test_threshold_profile_endpoint()
    try:
        os.unlink(_TMP_DB.name)
    except OSError:
        pass
    print("all API tests passed")
