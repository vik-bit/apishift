import datetime

from calendar_utils import start_of_2024, weekend_flags


def test_weekend_flags():
    assert weekend_flags(["2024-01-05", "2024-01-06", "2024-01-07"]) == [0, 1, 1]


def test_start():
    assert start_of_2024() == datetime.datetime(2024, 1, 1)
