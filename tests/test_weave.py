"""核心织纹逻辑的单元测试（不依赖 FastAPI）。"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weave import (  # noqa: E402
    DesignError,
    analyze_repeat_period,
    audit_floats,
    best_alignment,
    build_interlacing,
    repeat_period_of_matrix,
    search_repair_plans,
    suggest_tie_up_flips,
    validate_design,
    _proper_divisors,
    _runs,
)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def assert_tiles(matrix, period, msg):
    """校验 period.unit 在经纬两方向取模平铺后逐点等于整幅矩阵。"""
    wp, wfp, unit = period.warp_period, period.weft_period, period.unit
    picks, ends = len(matrix), len(matrix[0])
    check(wp >= 1 and wfp >= 1, f"{msg}: periods positive")
    check(ends % wp == 0, f"{msg}: warp_period divides ends")
    check(picks % wfp == 0, f"{msg}: weft_period divides picks")
    check(len(unit) == wfp and all(len(r) == wp for r in unit),
          f"{msg}: unit is weft_period x warp_period")
    tiled = all(
        matrix[h][w] == unit[h % wfp][w % wp]
        for h in range(picks)
        for w in range(ends)
    )
    check(tiled, f"{msg}: unit tiles the full matrix seamlessly (mod wrap)")



def test_interlacing():
    # 平纹：2 综 2 踏
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    m = build_interlacing(threading, tie_up, treadling)
    check(m == [[1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1]], "plain weave interlacing")


def test_warp_and_weft_floats():
    # 第 0 根经纱连续 3 纬浮起；第 0 纬纬纱连续浮过 3 根经纱
    threading = [0, 0, 0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 0, 1]
    # 矩阵:
    # 1 1 1
    # 1 1 1
    # 1 1 1
    # 0 0 0
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    warp = [x for x in v if x.direction == "warp"]
    weft = [x for x in v if x.direction == "weft"]
    check(len(warp) == 3 and all(x.length == 3 and x.start == 0 for x in warp),
          "warp floats of length 3 on all 3 ends")
    check(len(weft) == 1 and weft[0].yarn_index == 3 and weft[0].length == 3,
          "weft float of length 3 on pick 3")
    check(all(x.yarn_index in (0, 1, 2) for x in warp), "warp yarn indices")


def test_cyclic_merge():
    # 列: 1 1 0 0 1 1 -> 非循环两段(0,2),(4,2)；循环合并为 (4,4)
    check(_runs([1, 1, 0, 0, 1, 1], 1, False) == [(0, 2), (4, 2)],
          "non-cyclic runs")
    check(_runs([1, 1, 0, 0, 1, 1], 1, True) == [(4, 4)],
          "cyclic merge across boundary")
    # 全 1 列：只有一段，不自我合并
    check(_runs([1, 1, 1], 1, True) == [(0, 3)],
          "all-float line stays a single run")
    # 首尾不相接时不合并
    check(_runs([1, 0, 0, 1, 0], 1, True) == [(0, 1), (3, 1)],
          "no merge when boundary not both target")


def test_cyclic_audit_end_to_end():
    # 2/2 斜纹 4x4 循环，max_float=2：循环合并后每根经纱浮长恰为 2，不超限
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1] if False else [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(v == [], "2/2 twill cyclic: no float exceeds 2")
    # 非循环时边界处浮长仍 <= 2，也不超限
    _, v2 = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v2 == [], "2/2 twill non-cyclic: no float exceeds 2")
    # max_float=1 时循环与非循环都应报出浮长 2
    _, v3 = audit_floats(threading, tie_up, treadling, max_float=1, cyclic=True)
    check(len(v3) > 0 and all(x.length == 2 for x in v3),
          "2/2 twill with max_float=1 flags length-2 floats")


def test_cyclic_wrap_violation():
    # 构造跨边界合并后才超限的情形：列 1 1 0 1 1，max_float=2
    # 非循环：两段长度 2、2，不超限；循环：合并为长度 4，超限
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    _, v_off = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v_off == [], "wrap-around float not flagged when cyclic=False")
    _, v_on = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(len(v_on) == 1 and v_on[0].direction == "warp"
          and v_on[0].yarn_index == 0 and v_on[0].start == 3 and v_on[0].length == 4,
          "wrap-around float merged to length 4 starting at 3")


def test_repeat_period_plain_weave():
    # 平纹 4x4：交织矩阵 [[1,0,1,0],[0,1,0,1],...]，经纬周期都是 2，
    # 单元 2x2，是严格二维重复
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    period = analyze_repeat_period(threading, tie_up, treadling, 2)
    matrix = build_interlacing(threading, tie_up, treadling)
    check(period.warp_period == 2 and period.weft_period == 2,
          "plain weave: both periods are 2")
    check(period.unit == [[1, 0], [0, 1]], "plain weave: 2x2 unit")
    check(period.strict_2d_repeat is True, "plain weave: strict 2D repeat")
    assert_tiles(matrix, period, "plain weave")


def test_repeat_period_full_size_when_prime():
    # 3x3 满幅随机（尺寸为素数且无重复）：不存在小于整幅的周期，
    # 返回完整尺寸，unit 即整幅矩阵，strict_2d_repeat=False
    matrix = [
        [1, 0, 1],
        [0, 1, 1],
        [1, 1, 0],
    ]
    period = repeat_period_of_matrix(matrix)
    check(period.warp_period == 3 and period.weft_period == 3,
          "prime 3x3 matrix: no period smaller than full size")
    check(period.unit == matrix, "prime 3x3 matrix: unit is the full matrix")
    check(period.strict_2d_repeat is False,
          "prime 3x3 matrix: not strict 2D repeat")


def test_repeat_period_one_axis_only():
    # 仅经向重复、纬向不重复：列 [A B A B]，但两行不同
    # 1 0 1 0
    # 1 1 1 1
    # 经向周期 2（<4），纬向周期 2（=行数），不是严格二维重复
    matrix = [
        [1, 0, 1, 0],
        [1, 1, 1, 1],
    ]
    period = repeat_period_of_matrix(matrix)
    check(period.warp_period == 2, "one-axis: warp period 2")
    check(period.weft_period == 2, "one-axis: weft period full size 2")
    check(period.unit == [[1, 0], [1, 1]], "one-axis: unit is 2x2 (full height)")
    check(period.strict_2d_repeat is False,
          "one-axis: not strict 2D repeat (weft has no smaller period)")
    assert_tiles(matrix, period, "one-axis")


def test_repeat_period_based_on_matrix_not_threading():
    # 关键：周期必须基于交织矩阵，而非分别检查 threading/treadling。
    # 3 踏 3 综，仅踩踏板 0、1；tie_up 的第 0、2 列在这两行上相同
    # （穿综 0 与 2 的经纱交织表现一致），尽管穿综索引本身不同。
    # threading = [0,1,2,1]（作为序列最小周期 4，无 2-周期，因为 0!=2），
    # treadling = [0,1,0,1]（周期 2）。交织矩阵中穿综 0 与 2 的列相同，
    # 因此矩阵经向周期为 2。
    threading = [0, 1, 2, 1]
    tie_up = [[1, 0, 1], [0, 1, 0], [0, 0, 1]]
    treadling = [0, 1, 0, 1]
    period = analyze_repeat_period(threading, tie_up, treadling, 4)
    matrix = build_interlacing(threading, tie_up, treadling)
    # threading 序列本身没有 2-周期（threading[0]=0 != threading[2]=2）
    check(any(threading[w] != threading[w % 2] for w in range(4)),
          "threading sequence alone has no 2-period")
    check(period.warp_period == 2,
          "matrix warp period 2 despite threading sequence period 4")
    check(period.weft_period == 2, "matrix weft period 2")
    check(period.unit == [[1, 0], [0, 1]], "matrix-derived 2x2 unit")
    check(period.strict_2d_repeat is True, "matrix-derived strict 2D repeat")
    assert_tiles(matrix, period, "matrix-based")


def test_repeat_period_cyclic_boundary():
    # 循环设计的边界：单列、treadling [0,0,1] 重复两次（6 纬）。
    # 列为 1 1 0 1 1 0，周期 3 整除 6；取模回绕比较必须正确跨越首尾边界，
    # 不能因为末段(1,1)接首段(1,1)看似相连而误判为更小周期（2 不整除 6）。
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0, 1]
    # 该设计按 cyclic=true 审计
    matrix, _ = audit_floats(threading, tie_up, treadling, 2, cyclic=True)
    period = analyze_repeat_period(threading, tie_up, treadling, 2)
    check(period.warp_period == 1, "single-column: warp period 1")
    check(period.weft_period == 3, "cyclic boundary: weft period 3 (not 2)")
    check(period.unit == [[1], [1], [0]], "cyclic boundary: 3x1 unit")
    check(period.strict_2d_repeat is False,
          "cyclic boundary single column: not strict 2D repeat")
    assert_tiles(matrix, period, "cyclic boundary")

    # 直接对跨边界平铺的矩阵验证回绕：4 列模式在边界处也必须对齐
    wrap_matrix = [
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
    ]
    wp = repeat_period_of_matrix(wrap_matrix)
    check(wp.warp_period == 2 and wp.weft_period == 2,
          "wrap matrix aligned across both boundaries")
    assert_tiles(wrap_matrix, wp, "wrap matrix")


def test_repeat_period_constant_and_single_cell():
    # 全 1 矩阵 6x4：经纬周期都为 1
    all_ones = [[1] * 4 for _ in range(6)]
    period = repeat_period_of_matrix(all_ones)
    check(period.warp_period == 1 and period.weft_period == 1
          and period.unit == [[1]], "constant matrix: 1x1 unit")
    check(period.strict_2d_repeat is True, "constant 6x4: strict 2D repeat")
    assert_tiles(all_ones, period, "constant")

    # 1x1 单元即整幅，不是严格二维重复
    single = [[0]]
    p1 = repeat_period_of_matrix(single)
    check(p1.warp_period == 1 and p1.weft_period == 1 and p1.unit == [[0]],
          "single cell: periods 1")
    check(p1.strict_2d_repeat is False, "single cell: not strict 2D repeat")


def test_repeat_period_properties_random():
    # 随机交织矩阵：周期整除尺寸、单元无缝平铺、且没有更小的整除周期
    # （用朴素因子枚举交叉验证最小性）。
    rng = random.Random(20260921)
    check(_proper_divisors(12) == [1, 2, 3, 4, 6], "proper divisors helper")
    for picks in range(1, 9):
        for ends in range(1, 9):
            matrix = [[rng.randint(0, 1) for _ in range(ends)] for _ in range(picks)]
            period = repeat_period_of_matrix(matrix)
            assert_tiles(matrix, period, f"random {picks}x{ends}")

            for d in _proper_divisors(ends):
                if d >= period.warp_period:
                    break
                has_smaller = all(
                    matrix[h][w] == matrix[h][w % d]
                    for h in range(picks) for w in range(ends)
                )
                check(not has_smaller,
                      f"{picks}x{ends}: no warp divisor {d} smaller than "
                      f"{period.warp_period}")
            for d in _proper_divisors(picks):
                if d >= period.weft_period:
                    break
                has_smaller = all(
                    matrix[h][w] == matrix[h % d][w]
                    for h in range(picks) for w in range(ends)
                )
                check(not has_smaller,
                      f"{picks}x{ends}: no weft divisor {d} smaller than "
                      f"{period.weft_period}")
            expected_strict = period.warp_period < ends and period.weft_period < picks
            check(period.strict_2d_repeat == expected_strict,
                  f"{picks}x{ends}: strict_2d_repeat flag correct")


def test_tie_up_suggestions_basic():
    # 列 1 1 0 1 1 循环合并为长度 4 的经向浮长（max_float=2），共 1 条违规
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, True)
    # 仅 flip tie_up[0][0] -> 0 可消除违规；受影响点 = 踩踏板 0 的 4 纬 × 1 经
    check(len(suggestions) == 1, "exactly one improving flip")
    s = suggestions[0]
    check(s.treadle == 0 and s.shaft == 0 and s.new_value == 0,
          "flip tie_up[0][0] to 0")
    check(s.remaining_violations == 0, "no violations remain after flip")
    check(s.affected_points == 4, "4 interlacing points affected")
    # 原设计不被修改
    check(tie_up == [[1], [0]], "original tie_up unchanged")


def test_tie_up_suggestions_ordering():
    # 3 根经纱各浮 3 纬 + 末纬纬浮 3 经，共 4 条违规；多个单步翻转可改善
    threading = [0, 1, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, False)
    got = [(s.treadle, s.shaft, s.remaining_violations, s.affected_points)
           for s in suggestions]
    # 按 (剩余违规数, 受影响点数, 踏板索引, 综框索引) 升序
    check(got == [(0, 1, 2, 6), (1, 0, 3, 1), (1, 1, 3, 2), (0, 0, 3, 3)],
          "suggestions sorted by remaining, affected, treadle, shaft")
    check(all(s.remaining_violations < 4 for s in suggestions),
          "all candidates strictly reduce violations")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_tie_up_suggestions_no_improvement():
    # 平纹无违规：违规数为 0，不存在严格更少的翻转，返回空列表
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    check(suggest_tie_up_flips(threading, tie_up, treadling, 2, False) == [],
          "empty list when no flip improves")


def test_repair_plans_two_flips_needed():
    # 单列 6 纬全 1，cyclic 下整列一段长度 6，max_float=2：1 条经向违规。
    # 每个踏板各踩 1 纬，单次翻转只产生 1 个 0，仍有 1 条违规（长度 5）；
    # 循环上间隔恰为 3 的两次翻转把 1-段切成三段各长 2，违规清零。
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    _, base_v = audit_floats(threading, tie_up, treadling, 2, True)
    check(len(base_v) == 1, "baseline has exactly one violation")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=1)
    check(plans == [], "no improving plan within 1 flip")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2)
    # 循环 6 点上两个 0 间隔恰为 3 时三段各长 2：恰 3 个方案
    check(len(plans) == 3, f"3 two-flip plans, got {len(plans)}")
    seq0 = [(s.treadle, s.shaft) for s in plans[0].steps]
    check(seq0 == [(0, 0), (3, 0)], "lexicographically smallest sequence first")
    check([(s.treadle, s.shaft) for s in plans[1].steps] == [(1, 0), (4, 0)]
          and [(s.treadle, s.shaft) for s in plans[2].steps] == [(2, 0), (5, 0)],
          "remaining plans in lexicographic order")
    for p in plans:
        check(p.changes == 2 and p.final_violations == 0,
              "every plan uses 2 flips and clears violations")
        check(p.changed_points == 2, "2 interlacing points changed")
        check(len(p.steps) == 2 and p.steps[0].step == 1 and p.steps[1].step == 2,
              "steps are numbered 1..2")
        check(p.steps[0].old_value == 1 and p.steps[0].new_value == 0
              and p.steps[1].old_value == 1 and p.steps[1].new_value == 0,
              "flips 1 -> 0 with correct old/new values")
        check(p.steps[0].violations_after == 1,
              "intermediate state may keep violations unchanged")
        check(p.violations == [], "final violation list empty")
        check(sum(x for row in p.interlacing for x in row) == 4,
              "final matrix has exactly two zeros")
    check(tie_up == [[1], [1], [1], [1], [1], [1]],
          "original tie_up unchanged")


def test_repair_plans_state_dedup():
    # 同一绑综终态可由不同翻转序列到达：按状态去重，只保留字典序最小序列。
    # 2 踏 2 综，单列单纬时仅被踩踏板所提升的综框影响矩阵；构造多步搜索，
    # 验证终态去重（无重复终态）且原设计不被修改。
    threading = [0, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    plans = search_repair_plans(threading, tie_up, treadling, 2, False,
                                max_changes=3, limit=50)
    finals = []
    for p in plans:
        check(p.final_violations < 4, "plan strictly improves over baseline")
        # 同一单元在一条序列内不重复出现
        coords = [(s.treadle, s.shaft) for s in p.steps]
        check(len(coords) == len(set(coords)),
              "no cell flipped twice within one sequence")
        finals.append(tuple(tuple(row) for row in p.interlacing))
    check(len(finals) == len(set(finals)),
          "equivalent final states deduplicated")
    # 排序键：最终违规数、改动数、变化点数、序列字典序
    keys = [
        (p.final_violations, p.changes, p.changed_points,
         tuple((s.treadle, s.shaft) for s in p.steps))
        for p in plans
    ]
    check(keys == sorted(keys), "plans sorted by the declared key")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_repair_plans_limit_and_validation():
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2, limit=2)
    check(len(plans) == 2, "limit caps the number of plans")
    for bad in (0, 4):
        try:
            search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=bad)
            raise AssertionError(f"max_changes={bad} should be rejected")
        except DesignError:
            pass
    try:
        search_repair_plans(threading, tie_up, treadling, 2, True, limit=0)
        raise AssertionError("limit=0 should be rejected")
    except DesignError:
        pass
    print("  ok: repair plan parameter validation")


def test_best_alignment_shift_recovery():
    # b 为 a 沿纬向循环移 2 行、经向循环移 1 列：b[h][w] = a[(h+2)%3][(w+1)%3]
    # 对齐约定 aligned[h][w] = b[(h+ro)%H][(w+co)%W]，故最佳偏移为 (1, 2)
    a = [[1, 0, 1], [0, 1, 1], [1, 0, 0]]
    b = [[a[(h + 2) % 3][(w + 1) % 3] for w in range(3)] for h in range(3)]
    result = best_alignment(a, b)
    check(result.weft_offset == 1 and result.warp_offset == 2,
          "shifted copy: best offset recovers the cyclic shift")
    check(result.mismatch_count == 0 and result.mismatch_ratio == 0.0,
          "shifted copy: zero mismatches")
    check(result.aligned == a, "shifted copy: aligned matrix equals first matrix")
    check(result.mismatches == [], "shifted copy: no mismatch points")
    check(result.row_mismatches == [0, 0, 0]
          and result.col_mismatches == [0, 0, 0],
          "shifted copy: zero row/col summaries")
    check(a == [[1, 0, 1], [0, 1, 1], [1, 0, 0]]
          and b == [[0, 0, 1], [0, 1, 1], [1, 1, 0]],
          "input matrices unchanged")


def test_best_alignment_mismatch_details():
    # 仅 (2, 2) 单元不同：最佳对齐为零偏移，恰 1 处错位
    a = [[1, 0, 1], [0, 1, 1], [1, 1, 0]]
    c = [[1, 0, 1], [0, 1, 1], [1, 1, 1]]
    result = best_alignment(a, c)
    check(result.weft_offset == 0 and result.warp_offset == 0,
          "single-cell diff: zero offset")
    check(result.mismatch_count == 1, "single-cell diff: one mismatch")
    check(abs(result.mismatch_ratio - 1 / 9) < 1e-12,
          "single-cell diff: ratio 1/9")
    check(len(result.mismatches) == 1, "single-cell diff: one mismatch point")
    m = result.mismatches[0]
    check((m.row, m.col, m.design_value, m.other_value) == (2, 2, 0, 1),
          "single-cell diff: mismatch coordinate and values")
    check(result.row_mismatches == [0, 0, 1]
          and result.col_mismatches == [0, 0, 1],
          "single-cell diff: row/col summaries")
    check(result.aligned == c, "single-cell diff: aligned is unshifted second matrix")


def test_best_alignment_tie_break():
    # 行全同：偏移 (0,1) 与 (1,1) 同为 0 错位，按行偏移升序取 (0,1)
    a = [[1, 0], [1, 0]]
    b = [[0, 1], [0, 1]]
    result = best_alignment(a, b)
    check((result.weft_offset, result.warp_offset) == (0, 1),
          "row tie broken by smaller weft offset")
    check(result.mismatch_count == 0, "row tie: zero mismatches")
    # 单行：偏移 1 与 3 同为 0 错位，按列偏移升序取 1
    a1 = [[1, 0, 1, 0]]
    b1 = [[0, 1, 0, 1]]
    r1 = best_alignment(a1, b1)
    check((r1.weft_offset, r1.warp_offset) == (0, 1),
          "column tie broken by smaller warp offset")
    # 全同常量矩阵：所有偏移平局，取 (0, 0)
    r2 = best_alignment([[1, 1], [1, 1]], [[1, 1], [1, 1]])
    check((r2.weft_offset, r2.warp_offset) == (0, 0)
          and r2.mismatch_count == 0,
          "constant matrices: offset (0, 0)")


def test_best_alignment_dimension_mismatch():
    for a, b in (
        ([[1, 0], [0, 1]], [[1, 0, 1], [0, 1, 0]]),   # 列数不同
        ([[1, 0], [0, 1]], [[1, 0]]),                 # 行数不同
        ([[1]], []),                                  # 空矩阵
    ):
        try:
            best_alignment(a, b)
            raise AssertionError(f"{a} vs {b} should be rejected")
        except DesignError:
            pass
    print("  ok: dimension mismatch raises DesignError")


def test_validation():
    ok_cases = []
    # 维度不一致：绑综矩阵不是矩形
    try:
        validate_design([0], [[1, 0], [1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 穿综索引越界
    try:
        validate_design([0, 2], [[1, 0], [0, 1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 踏综索引越界
    try:
        validate_design([0], [[1], [0]], [2], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 绑综取值非 0/1
    try:
        validate_design([0], [[2]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 空输入
    try:
        validate_design([], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 负索引
    try:
        validate_design([-1], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    check(all(ok_cases), "invalid designs are rejected")


if __name__ == "__main__":
    test_interlacing()
    test_warp_and_weft_floats()
    test_cyclic_merge()
    test_cyclic_audit_end_to_end()
    test_cyclic_wrap_violation()
    test_repeat_period_plain_weave()
    test_repeat_period_full_size_when_prime()
    test_repeat_period_one_axis_only()
    test_repeat_period_based_on_matrix_not_threading()
    test_repeat_period_cyclic_boundary()
    test_repeat_period_constant_and_single_cell()
    test_repeat_period_properties_random()
    test_tie_up_suggestions_basic()
    test_tie_up_suggestions_ordering()
    test_tie_up_suggestions_no_improvement()
    test_repair_plans_two_flips_needed()
    test_repair_plans_state_dedup()
    test_repair_plans_limit_and_validation()
    test_best_alignment_shift_recovery()
    test_best_alignment_mismatch_details()
    test_best_alignment_tie_break()
    test_best_alignment_dimension_mismatch()
    test_validation()
    print("all tests passed")
