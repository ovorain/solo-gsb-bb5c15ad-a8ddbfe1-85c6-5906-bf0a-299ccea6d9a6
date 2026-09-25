"""最低代价全局单调对齐（Needleman-Wunsch 变体）。

代价模型：
- 两条文本匹配：归一化字符编辑距离 = Levenshtein(a, b) / max(len(a), len(b)) ∈ [0, 1]
- 跳过任一侧一条（缺项）：固定 GAP_COST（默认 0.45）

每条最多匹配一次，允许缺项；由于对齐全局单调，重复短句会依整段顺序配对。

最优性说明：任何含「代价 > 2*GAP_COST 的匹配」的对齐，都可通过把该匹配
替换为两次跳过得到更小的总代价，因此最优解中不存在此类匹配。据此对
编辑距离做下界剪枝（长度差下界超过 2*GAP_COST 时不必精确计算），
不改变最优对齐结果。
"""
from __future__ import annotations

try:  # 优先使用 C 实现（python-Levenshtein）
    from Levenshtein import distance as _c_distance
except Exception:  # pragma: no cover - 无该依赖时回退
    _c_distance = None

GAP_COST = 0.45

# 对齐操作
OP_MATCH = 0
OP_SCRIPT_ONLY = 1  # 剧本有条目，字幕缺项
OP_SRT_ONLY = 2     # 字幕有条目，剧本缺项


def _py_distance(a: str, b: str) -> int:
    """纯 Python Levenshtein（双行滚动数组）。"""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[lb]


def lev_distance(a: str, b: str) -> int:
    if _c_distance is not None:
        return _c_distance(a, b)
    return _py_distance(a, b)


def match_cost(a: str, b: str) -> float:
    """归一化字符编辑距离，两串皆空时为 0。"""
    mx = max(len(a), len(b))
    if mx == 0:
        return 0.0
    return lev_distance(a, b) / mx


def align(a_items: list[str], b_items: list[str], gap: float = GAP_COST):
    """求最低代价全局单调对齐。

    参数为两侧归一化后的文本列表。返回 (ops, total_cost)：
    ops 为按顺序的 (op, a_index, b_index) 列表，未匹配侧索引为 -1。
    """
    n, m = len(a_items), len(b_items)
    prune = 2.0 * gap          # 匹配代价超过该值时，最优解必然改用两次跳过
    placeholder = prune + 1.0  # 剪枝占位代价（保证不会被最优解选中）

    b_lens = [len(b) for b in b_items]

    # prev 为上一行动态规划代价；trace 记录回溯方向（0 对角 / 1 上 / 2 左）
    prev = [j * gap for j in range(m + 1)]
    trace = [bytearray(m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        trace[i][0] = 1

    for i in range(1, n + 1):
        a = a_items[i - 1]
        la = len(a)
        cur = [i * gap] + [0.0] * m
        ti = trace[i]
        for j in range(1, m + 1):
            lb = b_lens[j - 1]
            mx = la if la > lb else lb
            if mx == 0:
                cost = 0.0
            else:
                diff = la - lb if la > lb else lb - la
                if diff > prune * mx:
                    cost = placeholder  # 长度差下界已超 2*gap，无需精确计算
                else:
                    cost = lev_distance(a, b_items[j - 1]) / mx
            d = prev[j - 1] + cost
            u = prev[j] + gap
            lft = cur[j - 1] + gap
            if d <= u and d <= lft:  # 平局优先匹配
                cur[j] = d
                ti[j] = 0
            elif u <= lft:
                cur[j] = u
                ti[j] = 1
            else:
                cur[j] = lft
                ti[j] = 2
        prev = cur

    total = prev[m]

    # 回溯
    ops: list[tuple[int, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and trace[i][j] == 0:
            ops.append((OP_MATCH, i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or trace[i][j] == 1):
            ops.append((OP_SCRIPT_ONLY, i - 1, -1))
            i -= 1
        else:
            ops.append((OP_SRT_ONLY, -1, j - 1))
            j -= 1
    ops.reverse()
    return ops, total
