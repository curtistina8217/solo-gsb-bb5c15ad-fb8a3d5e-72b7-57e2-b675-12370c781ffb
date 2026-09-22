"""请求 / 响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DesignIn(BaseModel):
    """一份待审计的机织纹样设计。"""

    name: str | None = Field(default=None, description="设计名称（可选）")
    cyclic: bool = Field(
        default=False,
        description="纹样是否循环；为 true 时合并矩阵首尾跨边界的连续浮长段",
    )
    max_float: int = Field(..., ge=1, description="允许的最大浮长，超过即判违规")
    threading: list[int] = Field(
        ..., description="经纱穿综映射：threading[w] 为第 w 根经纱所穿综框的索引"
    )
    tie_up: list[list[int]] = Field(
        ...,
        description="绑综矩阵：tie_up[t][s] ∈ {0,1}，踏板 t 是否提升综框 s；"
        "行数 = 踏板数，列数 = 综框数",
    )
    treadling: list[int] = Field(
        ..., description="逐纬踏综序列：treadling[h] 为第 h 纬踩下的踏板索引"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "2/2 twill, 8x8 repeat",
                    "cyclic": True,
                    "max_float": 2,
                    "threading": [0, 1, 2, 3, 0, 1, 2, 3],
                    "tie_up": [
                        [1, 1, 0, 0],
                        [0, 1, 1, 0],
                        [0, 0, 1, 1],
                        [1, 0, 0, 1],
                    ],
                    "treadling": [0, 1, 2, 3, 0, 1, 2, 3],
                }
            ]
        }
    }


class Violation(BaseModel):
    direction: Literal["warp", "weft"] = Field(
        ..., description="warp=经向浮长（经纱连续浮于纬上），weft=纬向浮长"
    )
    yarn_index: int = Field(..., description="纱线索引：经纱列号或纬纱行号")
    start: int = Field(
        ..., description="连续段起点；循环合并段取尾部段的起点（跨边界延伸）"
    )
    length: int = Field(..., description="连续浮长")


class AuditOut(BaseModel):
    exceeds: bool = Field(..., description="是否存在超过 max_float 的浮长")
    interlacing: list[list[int]] = Field(
        ..., description="经纬交织矩阵，1=经纱在上，0=纬纱在上"
    )
    violations: list[Violation]


class DesignOut(BaseModel):
    id: int
    name: str | None
    cyclic: bool
    max_float: int
    shafts: int
    treadles: int
    warp_ends: int
    weft_picks: int
    threading: list[int]
    tie_up: list[list[int]]
    treadling: list[int]
    created_at: str
    audit: AuditOut


class DesignSummary(BaseModel):
    id: int
    name: str | None
    cyclic: bool
    max_float: int
    shafts: int
    treadles: int
    warp_ends: int
    weft_picks: int
    exceeds: bool
    created_at: str


class TieUpSuggestionOut(BaseModel):
    """单步绑综修复建议：翻转一个 tie_up 单元后违规总数严格减少的候选。"""

    treadle: int = Field(..., description="踏板索引（tie_up 行号）")
    shaft: int = Field(..., description="综框索引（tie_up 列号）")
    new_value: Literal[0, 1] = Field(..., description="该单元翻转后的新值")
    remaining_violations: int = Field(
        ..., description="翻转后按原 cyclic、max_float 重跑审计的剩余违规总数"
    )
    affected_points: int = Field(
        ..., description="受影响交织点数：翻转前后交织矩阵中取值变化的单元数"
    )


class RepairPlanStepOut(BaseModel):
    """修复方案中的一步绑综翻转。"""

    step: int = Field(..., description="第几步翻转（从 1 开始）")
    treadle: int = Field(..., description="踏板索引（tie_up 行号）")
    shaft: int = Field(..., description="综框索引（tie_up 列号）")
    old_value: Literal[0, 1] = Field(..., description="翻转前该单元的值")
    new_value: Literal[0, 1] = Field(..., description="翻转后该单元的值")
    violations_after: int = Field(
        ..., description="本次翻转后完整审计的违规总数（中间状态允许不下降）"
    )


class RepairPlanOut(BaseModel):
    """多步绑综修复方案：终态违规总数严格少于原设计。"""

    changes: int = Field(..., description="方案翻转次数（1～max_changes）")
    final_violations: int = Field(..., description="最终违规总数")
    changed_points: int = Field(
        ..., description="最终交织矩阵相对原矩阵取值变化的点数"
    )
    steps: list[RepairPlanStepOut] = Field(..., description="逐步翻转序列")
    violations: list[Violation] = Field(..., description="最终违规列表")
    interlacing: list[list[int]] = Field(
        ..., description="最终交织矩阵，1=经纱在上，0=纬纱在上"
    )


class RepeatPeriodOut(BaseModel):
    """交织矩阵的最小循环单元分析。"""

    warp_period: int = Field(
        ..., description="经向最小正周期（一个循环单元的列数/经纱数），整除经纱数"
    )
    weft_period: int = Field(
        ..., description="纬向最小正周期（一个循环单元的行数/纬纱数），整除纬纱数"
    )
    unit: list[list[int]] = Field(
        ...,
        description="最小循环单元矩阵（weft_period 行 × warp_period 列），"
        "1=经纱在上，0=纬纱在上；在经纬两方向重复平铺可无缝还原整幅交织矩阵",
    )
    strict_2d_repeat: bool = Field(
        ...,
        description="是否为严格二维重复：仅当 warp_period、weft_period 均严格小于"
        "整幅对应尺寸（单元在两个方向都至少平铺 2 次）时为 true",
    )


class ErrorOut(BaseModel):
    detail: str


class DesignCompareIn(BaseModel):
    """设计对齐比对请求。"""

    other_design_id: int = Field(
        ..., ge=1, description="参与比对的另一份已入库设计 ID"
    )


class MismatchPointOut(BaseModel):
    """最佳对齐下一个不一致单元的坐标与双方取值。"""

    row: int = Field(..., description="错位单元所在纬纱行号")
    col: int = Field(..., description="错位单元所在经纱列号")
    design_value: int = Field(..., description="第一份设计交织矩阵在该单元的值")
    other_value: int = Field(..., description="第二份设计矩阵对齐后在该单元的值")


class DesignCompareOut(BaseModel):
    """两份设计交织矩阵的最佳循环对齐比对结果。"""

    design_id: int = Field(..., description="第一份（路径指定的）设计 ID")
    other_design_id: int = Field(..., description="第二份（被循环错位比对的）设计 ID")
    warp_ends: int = Field(..., description="两份设计共同的经纱数（矩阵列数）")
    weft_picks: int = Field(..., description="两份设计共同的纬纱数（矩阵行数）")
    weft_offset: int = Field(
        ..., description="第二份矩阵沿纬向（行）的最佳循环错位量"
    )
    warp_offset: int = Field(
        ..., description="第二份矩阵沿经向（列）的最佳循环错位量"
    )
    mismatch_count: int = Field(..., description="最佳对齐下不一致单元数")
    mismatch_ratio: float = Field(
        ..., description="不一致单元占比：mismatch_count / (weft_picks × warp_ends)"
    )
    mismatches: list[MismatchPointOut] = Field(
        ..., description="错位坐标列表，按行、列升序"
    )
    row_mismatches: list[int] = Field(
        ..., description="按行汇总：row_mismatches[h] 为第 h 纬的错位数"
    )
    col_mismatches: list[int] = Field(
        ..., description="按列汇总：col_mismatches[w] 为第 w 根经纱的错位数"
    )
    aligned: list[list[int]] = Field(
        ...,
        description="最佳对齐后的第二份交织矩阵（1=经纱在上，0=纬纱在上）："
        "aligned[h][w] = 原矩阵[(h + weft_offset) % 行数][(w + warp_offset) % 列数]",
    )
