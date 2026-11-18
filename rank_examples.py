"""可直接运行的 V1 对照及秩复查输入样例。"""

from contextlib import closing

from db import initialize, open_database
from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.batches import submit_batch
from intake.store import load_batch_rows
from retention.purge import expire_batch
from review.reports import get_review, issue_review
from scales.revisions import set_scale
from tests.support import ACCEPTED, DUE, PERIOD, PROJECT, axis_specs


MOMENT_A = (("r0", 0, 0), ("r1", 1, 4), ("r2", 2, 1), ("r3", 3, 1))
MOMENT_B = (("r0", 0, 1), ("r1", 1, 1), ("r2", 2, 4), ("r3", 3, 0))
CROSS_LEFT = (("r0", 0, 0), ("r1", 1, 1))
CROSS_RIGHT = (("r0", "1", "0/2"), ("r1", 0, 1))
REPEATED = (("r0", 0, 0), ("r1", 0, 0), ("r2", 1, 1), ("r3", 2, 0),
            ("r4", None, 7), ("r5", 8, None))
ZERO_PAIRS = (("r0", 0, None), ("r1", None, 1))


def submit_fixture(db, key, rows, *, bench="a", predecessor_id=None, **scale_options):
    x, y = axis_specs(**scale_options)
    scale_id = set_scale(db, PROJECT, bench, x=x, y=y)
    return submit_batch(db, PROJECT, bench, key, scale_id, rows,
                        accepted_at=ACCEPTED, predecessor_id=predecessor_id)


def main():
    with closing(open_database(":memory:")) as db:
        initialize(db)
        seals = []
        reports = []
        for key, rows in (("moment-a", MOMENT_A), ("moment-b", MOMENT_B)):
            batch_id = submit_fixture(db, key, rows)
            seal = seal_batch(db, batch_id)
            receipt = expire_batch(db, batch_id, PERIOD, DUE)
            if (receipt.removed_rows != len(rows)
                    or receipt.supporting_seal_id != seal.seal_id
                    or load_batch_rows(db, batch_id) is not None
                    or get_seal(db, seal.seal_id) != seal):
                raise AssertionError(f"原始行清理或封存领取有误 {key}")
            report = issue_review(db, [seal.seal_id], 0)
            if (report.n, report.q, report.passed) != (4, 0, True):
                raise AssertionError(f"普通报告与对照不符 {report!r}")
            if get_review(db, report.report_id) != report:
                raise AssertionError(f"普通报告读取有误 {report!r}")
            seals.append(seal)
            reports.append(report)
        if seals[0].moments != seals[1].moments:
            raise AssertionError("两组 V1 封存矩应相同")
        for seal, report in zip(seals, reports):
            print(f"封存 {seal.seal_id} 原始行已清理。普通报告 {report.report_id} "
                  f"n={report.n} q={report.q} passed={report.passed}")


if __name__ == "__main__":
    main()
