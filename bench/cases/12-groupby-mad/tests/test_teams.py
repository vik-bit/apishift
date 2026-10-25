import pandas as pd
from teams import score_spread


def test_per_team_mad():
    df = pd.DataFrame({"team": ["a", "a", "b", "b"], "score": [1.0, 3.0, 5.0, 5.0]})
    assert score_spread(df) == {"a": 1.0, "b": 0.0}
