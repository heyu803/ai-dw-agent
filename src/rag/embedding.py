"""
轻量 Embedding（demo 专用，零依赖、可复现）。

生产环境用 BGE-M3（方案 2.1：多语言、1024 维、中英表现均优），通过
sentence-transformers / FlagEmbedding 加载。这里为了让项目开箱即用，
用"字符 n-gram + 哈希到固定维度"的方式生成稠密向量：
- 不依赖任何模型权重，离线可跑；
- 对中文/英文都能用（按字切 n-gram）；
- 足以演示向量召回的相对排序效果。

切换到 BGE-M3 只需替换 embed() 实现，向量库/检索逻辑无需改动。
"""
import math
import hashlib

DIM = 256


def embed(text: str) -> list[float]:
    """把文本编码为 DIM 维稠密向量（字符 bi/tri-gram 哈希 + L2 归一化）。"""
    text = text.lower().strip()
    vec = [0.0] * DIM
    grams: list[str] = []
    for n in (2, 3):
        for i in range(len(text) - n + 1):
            grams.append(text[i:i + n])
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
        idx = h % DIM
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    # L2 归一化
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # 已归一化，点积即余弦
