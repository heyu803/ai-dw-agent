"""
统计异常检测引擎（对应方案 7.2 统计异常检测引擎 / 图5 StatisticalAnomalyDetector）。

三种方法，对应不同数据形态（面试可讲选型）：
- z_score：假设近似正态，对"突刺"敏感，但易受极端值影响；
- IQR（四分位距）：基于分位数，对极端值更鲁棒（图中注释"对异常值不敏感"）；
- Prophet：适用于有趋势/周期性的时序（如订单量的周/年季节性），预测带置信区间。

代码与文档保持一致；Prophet 为可选依赖，未安装时自动降级提示。
"""
import numpy as np
from ...schemas.models import AnomalyResult


class StatisticalAnomalyDetector:
    """基于统计方法的数据异常检测。"""

    def detect_zscore(self, current: float, history: list[float], threshold: float = 3.0) -> AnomalyResult:
        """Z-Score 异常检测。"""
        mean = float(np.mean(history))
        std = float(np.std(history))
        if std == 0:
            return AnomalyResult(is_anomaly=False, score=0.0, method="z_score",
                                 details="历史无波动(std=0)，跳过")
        z_score = abs(current - mean) / std
        return AnomalyResult(
            is_anomaly=z_score > threshold,
            score=z_score,
            method="z_score",
            details=f"当前值={current}, 均值={mean:.2f}, 标准差={std:.2f}, Z-Score={z_score:.2f}",
        )

    def detect_iqr(self, current: float, history: list[float], factor: float = 1.5) -> AnomalyResult:
        """IQR（四分位距）异常检测 —— 对异常值不敏感。"""
        q1 = float(np.percentile(history, 25))
        q3 = float(np.percentile(history, 75))
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        is_anomaly = current < lower or current > upper
        score = max(abs(current - lower), abs(current - upper)) / iqr if iqr > 0 else 0.0
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            method="iqr",
            details=f"IQR={iqr:.2f}, 正常范围=[{lower:.2f}, {upper:.2f}], 当前值={current}",
            lower_bound=lower, upper_bound=upper,
        )

    def detect_prophet(self, history_df, current_dt: str) -> AnomalyResult:
        """Prophet 趋势预测 —— 适用于周期性数据（可选依赖）。"""
        try:
            from prophet import Prophet
        except ImportError:
            return AnomalyResult(is_anomaly=False, method="prophet",
                                 details="未安装 prophet，已跳过（pip install prophet 启用）")

        df = history_df.rename(columns={"dt": "ds", "value": "y"})
        model = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
        model.fit(df)
        future = model.make_future_dataframe(periods=1)
        forecast = model.predict(future)
        predicted = float(forecast.iloc[-1]["yhat"])
        lower_bound = float(forecast.iloc[-1]["yhat_lower"])
        upper_bound = float(forecast.iloc[-1]["yhat_upper"])
        return AnomalyResult(
            is_anomaly=False,  # 由调用方根据实际值与 bound 判断
            predicted_value=predicted,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            method="prophet",
        )
