import pandas as pd

MIN_VALID_POINTS = 10
_MAX_GAP_FILL_MIN = 10  # 연속 결측이 이 값 이하인 구간만 보간


def validate_dataframe(df: pd.DataFrame) -> bool:
    if len(df) < MIN_VALID_POINTS:
        return False
    if df["y"].std() == 0:
        return False
    return True


def _clip_outliers(df: pd.DataFrame) -> pd.DataFrame:
    Q1 = df["y"].quantile(0.25)
    Q3 = df["y"].quantile(0.75)
    IQR = Q3 - Q1
    if IQR > 0:
        lower = max(0.0, Q1 - 3 * IQR)
        upper = Q3 + 3 * IQR
        df = df.copy()
        df["y"] = df["y"].clip(lower=lower, upper=upper)
    return df


def _fill_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """§3 데이터 희소성 대응: 1분 단위로 리샘플 후 짧은 결측 구간 선형 보간.

    _MAX_GAP_FILL_MIN(10분) 초과 연속 결측은 보간하지 않아 비정상 예측선을 방지한다.
    """
    df = df.set_index("ds")
    df = df.resample("1min").mean()
    df["y"] = df["y"].interpolate(method="linear", limit=_MAX_GAP_FILL_MIN)
    return df.dropna().reset_index()


def transform_to_prophet_df(raw_data) -> pd.DataFrame:
    df = pd.DataFrame(raw_data, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"], unit="s")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna()
    df = df.sort_values("ds").reset_index(drop=True)
    df = _fill_gaps(df)  # §3 gap 보간 (리샘플 포함)
    df = _clip_outliers(df)
    return df
