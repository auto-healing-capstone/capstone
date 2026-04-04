import pandas as pd

def transform_to_prophet_df(raw_data):
    df = pd.DataFrame(raw_data, columns=['ds', 'y'])
    
    df['ds'] = pd.to_datetime(df['ds'], unit='s')
    
    df['y'] = pd.to_numeric(df['y'])
    
    df = df.ffill().bfill()
    
    return df