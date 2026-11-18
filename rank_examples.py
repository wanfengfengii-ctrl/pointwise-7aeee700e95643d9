"""可直接运行的 V1 对照及秩复查输入样例。"""

from contextlib import closing
from fractions import Fraction

from db import initialize, open_database
from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.batches import submit_batch
from intake.store import load_batch_rows
from retention.purge import expire_batch
from review.reports import get_rank_review, get_review, issue_rank_review, issue_review
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


def _check(label, actual, expected):
    if actual != expected:
        raise AssertionError(f"{label} 预期 {expected}，实测 {actual}")


def run_v1_comparison(db):
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
    return seals


def run_rank_checks(db):
    # 同矩异秩：清理后仅凭封存联合证据签发。
    moment_seals = []
    for key, rows, expected_q, expected_passed in (
        ("rank-moment-a", MOMENT_A, Fraction(1, 10), True),
        ("rank-moment-b", MOMENT_B, Fraction(-1, 10), False),
    ):
        batch_id = submit_fixture(db, key, rows)
        seal = seal_batch(db, batch_id)
        expire_batch(db, batch_id, PERIOD, DUE)
        report = issue_rank_review(db, [seal.seal_id], 0)
        _check(f"{key} 秩报告", (report.n, report.q, report.passed),
               (4, expected_q, expected_passed))
        _check(f"{key} 秩报告读回", get_rank_review(db, report.report_id), report)
        print(f"清理后秩签发 {key}: n={report.n} q={report.q} passed={report.passed}")
        moment_seals.append(seal)

    # 跨批并列：换标后的右批与左批统一坐标，反序选件结果一致。
    left = seal_batch(db, submit_fixture(db, "cross-left", CROSS_LEFT))
    right = seal_batch(db, submit_fixture(
        db, "cross-right", CROSS_RIGHT, bench="b", x_slope=-1, x_offset=2,
    ))
    forward = issue_rank_review(db, [left.seal_id, right.seal_id], "1/2")
    reverse = issue_rank_review(db, [right.seal_id, left.seal_id], "1/2")
    ordered = tuple(sorted((left.seal_id, right.seal_id)))
    _check("跨批选件升序", (forward.seal_ids, reverse.seal_ids), (ordered, ordered))
    for report in (forward, reverse):
        _check("跨批秩统计", (report.n, report.q, report.passed),
               (4, Fraction(1, 2), True))
    _check("跨批报告读回", get_rank_review(db, reverse.report_id), reverse)
    print(f"跨批秩签发: seal_ids={forward.seal_ids} n={forward.n} "
          f"q={forward.q} 等门槛 passed={forward.passed}")

    # 相同配对的重复出现：重数计入，单轴缺测行不入样。
    repeated = seal_batch(db, submit_fixture(db, "repeated", REPEATED))
    repeated_report = issue_rank_review(db, [repeated.seal_id], 0)
    _check("重复配对秩报告", (repeated_report.n, repeated_report.q, repeated_report.passed),
           (4, Fraction(2, 27), True))
    print(f"重复配对秩签发: n={repeated_report.n} q={repeated_report.q} "
          f"passed={repeated_report.passed}")

    # 零对新件：证据完整但不含配对，清理后仍可签发 q=None 的不通过报告。
    zero_batch = submit_fixture(db, "zero-pairs", ZERO_PAIRS)
    zero_seal = seal_batch(db, zero_batch)
    expire_batch(db, zero_batch, PERIOD, DUE)
    _check("零对件证据", zero_seal.rank_evidence.pairs, ())
    zero_report = issue_rank_review(db, [zero_seal.seal_id], 0)
    _check("零对秩报告", (zero_report.n, zero_report.q, zero_report.passed),
           (0, None, False))
    _check("零对报告读回", get_rank_review(db, zero_report.report_id), zero_report)
    print(f"零对新件清理后秩签发: n={zero_report.n} q=None passed=False")
    return moment_seals


def main():
    with closing(open_database(":memory:")) as db:
        initialize(db)
        run_v1_comparison(db)
        run_rank_checks(db)
        print("V1 对照与秩联合核验全部通过。")


if __name__ == "__main__":
    main()
