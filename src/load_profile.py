import pandas as pd

def load_consumption_profile(profile_name: str, annual_kwh: float) -> pd.Series:
    df = pd.read_csv("data/load_profiles.csv")

    if profile_name not in df.columns:
        raise ValueError(f"Unknown profile: {profile_name}")

    hourly_kwh = df[profile_name] * annual_kwh / 365
    hourly_kwh.index = df["hour"]

    return hourly_kwh
