import pandas as pd


def transform_to_prophet_df(raw_data):
    df = pd.DataFrame(raw_data, columns=["ds", "y"])

    df["ds"] = pd.to_datetime(df["ds"], unit="s")

    df["y"] = pd.to_numeric(df["y"])

    df = df.ffill().bfill()

    return df

def adjust_model_for_recovery(df, recovery_events):
    """
    복구 액션 이력을 바탕으로 시계열 데이터의 충격을 보정합니다.
    """
    # recovery_events: [{'time': '13:10', 'action': 'RESTART'}]
    # 복구 액션 시점 이후의 데이터에 가중치를 두거나 
    # 이전의 급등 패턴이 현재에 영향을 덜 주도록 파라미터 조정
    pass
