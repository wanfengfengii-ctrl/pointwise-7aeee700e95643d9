import argparse
import json
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from db import initialize, open_database
from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.batches import submit_batch
from intake.store import load_batch_header, load_batch_rows
from retention.policy import RetentionPolicy
from retention.purge import expire_batch
from review.reports import get_rank_review, get_review, issue_rank_review, issue_review
from scales.revisions import set_scale


def _sample_batch(db, project, spec, accepted_at, predecessor_id=None):
    x = dict(input_axis='dial_x', input_unit='tick', output_axis='reference_x',
             output_unit='mm', slope=1, offset=spec['x_shift'])
    y = dict(input_axis='dial_y', input_unit='tick', output_axis='reference_y',
             output_unit='mm', slope=1, offset=0)
    scale = set_scale(db, project, spec['bench'], x=x, y=y)
    return submit_batch(
        db, project, spec['bench'], spec['submission_key'], scale, spec['rows'],
        accepted_at=accepted_at, predecessor_id=predecessor_id,
    )


def _summary(report):
    return {'n': report.n, 'q': None if report.q is None else str(report.q), 'passed': report.passed}


def run_demo():
    sample = json.loads(Path(__file__).with_name('sample.json').read_text(encoding='utf-8'))
    project = sample['project']
    accepted_at = datetime.fromisoformat(sample['accepted_at'])
    cutoff = datetime.fromisoformat(sample['cutoff'])
    policy = RetentionPolicy(timedelta(days=sample['retention_days']))
    expected = {'n': 3, 'q': '0', 'passed': False}
    with TemporaryDirectory(prefix='yuchuan-demo-') as directory:
        path = Path(directory) / 'workshop.sqlite3'
        with closing(open_database(path)) as db:
            initialize(db)
            batches = [_sample_batch(db, project, spec, accepted_at) for spec in sample['batches']]
            seals = [seal_batch(db, batch_id) for batch_id in batches]
            selected = tuple(seal.seal_id for seal in seals)
            report = issue_review(db, selected, sample['threshold'])
            if _summary(report) != expected:
                raise AssertionError(f'POOL_SCALE_MISMATCH: {_summary(report)}')
            receipts = [expire_batch(db, batch_id, policy, cutoff) for batch_id in batches]
            # 原始行清理后，仅凭封存联合证据签发秩一致性报告。
            rank_report = issue_rank_review(db, selected, sample['threshold'])
            if _summary(rank_report) != expected:
                raise AssertionError(f'RANK_SCALE_MISMATCH: {_summary(rank_report)}')
            corrected_id = _sample_batch(db, project, sample['replacement'], cutoff, batches[1])
        with closing(open_database(path)) as db:
            old = get_review(db, report.report_id)
            replayed = issue_review(db, reversed(selected), sample['threshold'])
            corrected = load_batch_header(db, corrected_id)
            if old != report or _summary(replayed) != expected or replayed.seal_ids != selected:
                raise AssertionError(f'POOL_SCALE_MISMATCH: old={old!r}, new={replayed!r}')
            # 关闭重开后按原秩报告号领取清理后签发的结果。
            reopened_rank = get_rank_review(db, rank_report.report_id)
            if reopened_rank != rank_report:
                raise AssertionError(f'RANK_REOPEN_MISMATCH: {reopened_rank!r}')
            # 追加式更正产生新批与新封存，旧绑定与旧秩报告保持不变。
            corrected_seal = seal_batch(db, corrected_id)
            corrected_rank = issue_rank_review(db, [corrected_seal.seal_id], 0)
            if get_rank_review(db, rank_report.report_id) != rank_report:
                raise AssertionError('correction disturbed the original rank report')
            if corrected.predecessor_id != batches[1]:
                raise AssertionError('replacement did not retain the predecessor')
            if corrected.scale_id == seals[1].scale_id:
                raise AssertionError('replacement did not retain the predecessor and new scale')
            for seal, receipt in zip(seals, receipts):
                if load_batch_rows(db, seal.batch_id) is not None or get_seal(db, seal.seal_id) != seal:
                    raise AssertionError('expiry did not preserve exactly the fixed seal')
                if expire_batch(db, seal.batch_id, policy, accepted_at) != receipt:
                    raise AssertionError('expiry retry did not return the original receipt')
            observed = {
                'case_id': 'V8',
                'input': sample,
                'expected': expected,
                'actual': _summary(old),
                'downstream_expected': expected,
                'downstream_actual': _summary(replayed),
                'code_paths': ['freeze/moments.py', 'review/pool.py', 'review/reports.py', 'retention/purge.py'],
                'oracle': 'Project pairs (0,0),(1,1),(2,0) have zero centered cross-product; 0 is below 1/2.',
            }
            print('POINTWISE_SCENARIO ' + json.dumps(observed, ensure_ascii=False, sort_keys=True))
            print(f'清理后秩签发: 报告号 {rank_report.report_id} '
                  f'n={rank_report.n} q={rank_report.q} passed={rank_report.passed}')
            print(f'重开领取: {_summary(reopened_rank)}；'
                  f'更正批新封存 {corrected_seal.seal_id} 秩报告 '
                  f'n={corrected_rank.n} q={corrected_rank.q} passed={corrected_rank.passed}；'
                  f'原秩报告 {rank_report.report_id} 仍可按号领取。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='榆川台架复测质控')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='初始化工作库')
    init.add_argument('database', type=Path)
    commands.add_parser('demo', help='运行班次上报和夜班复查样例')
    args = parser.parse_args(argv)
    if args.command == 'init':
        with closing(open_database(args.database)) as db:
            initialize(db)
    else:
        run_demo()


if __name__ == '__main__':
    main()
