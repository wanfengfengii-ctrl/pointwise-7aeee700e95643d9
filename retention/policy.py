from dataclasses import dataclass
from datetime import timedelta

from db import utc_time


@dataclass(frozen=True)
class RetentionPolicy:
    period: timedelta

    def __post_init__(self):
        if not isinstance(self.period, timedelta) or self.period < timedelta(0):
            raise ValueError('retention period must be a nonnegative timedelta')

    def deadline(self, accepted_at):
        return utc_time(accepted_at) + self.period

    def allows_expiry(self, accepted_at, cutoff):
        return utc_time(cutoff) - utc_time(accepted_at) >= self.period
