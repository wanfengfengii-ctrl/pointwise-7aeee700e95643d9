from dataclasses import dataclass

from scales.axes import AxisTransform
from scales.projects import BenchAxes, ProjectAxes
from scales.rationals import decode_rational, encode_rational


@dataclass(frozen=True)
class ScaleRevision:
    scale_id: int
    project: str
    bench: str
    x: AxisTransform
    y: AxisTransform


def init_scale_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS project_axes (
            project TEXT PRIMARY KEY NOT NULL,
            x_axis TEXT NOT NULL, x_unit TEXT NOT NULL,
            y_axis TEXT NOT NULL, y_unit TEXT NOT NULL,
            CHECK (x_axis <> y_axis)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS bench_axes (
            project TEXT NOT NULL REFERENCES project_axes(project),
            bench TEXT NOT NULL,
            x_axis TEXT NOT NULL, x_unit TEXT NOT NULL,
            y_axis TEXT NOT NULL, y_unit TEXT NOT NULL,
            PRIMARY KEY (project, bench),
            CHECK (x_axis <> y_axis)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS scale_revisions (
            scale_id INTEGER PRIMARY KEY,
            project TEXT NOT NULL, bench TEXT NOT NULL,
            x_slope TEXT NOT NULL, x_offset TEXT NOT NULL,
            y_slope TEXT NOT NULL, y_offset TEXT NOT NULL,
            FOREIGN KEY (project, bench) REFERENCES bench_axes(project, bench)
        )
    ''')


def register_initial_axes(db, project, benches):
    db.execute('''
        INSERT INTO project_axes (project, x_axis, x_unit, y_axis, y_unit)
        VALUES (?, ?, ?, ?, ?) ON CONFLICT (project) DO NOTHING
    ''', (project.project, project.x_axis, project.x_unit, project.y_axis, project.y_unit))
    db.executemany('''
        INSERT INTO bench_axes (project, bench, x_axis, x_unit, y_axis, y_unit)
        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (project, bench) DO NOTHING
    ''', (
        (project.project, bench.bench, bench.x_axis, bench.x_unit, bench.y_axis, bench.y_unit)
        for bench in benches
    ))


def load_project_axes(db, project):
    row = db.execute('''
        SELECT project, x_axis, x_unit, y_axis, y_unit FROM project_axes WHERE project = ?
    ''', (project,)).fetchone()
    return ProjectAxes(*row) if row is not None else None


def load_bench_axes(db, project, bench):
    row = db.execute('''
        SELECT bench, x_axis, x_unit, y_axis, y_unit FROM bench_axes
        WHERE project = ? AND bench = ?
    ''', (project, bench)).fetchone()
    return BenchAxes(*row) if row is not None else None


def insert_scale_revision(db, project, bench, x, y):
    cursor = db.execute('''
        INSERT INTO scale_revisions (project, bench, x_slope, x_offset, y_slope, y_offset)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        project, bench, encode_rational(x.slope), encode_rational(x.offset),
        encode_rational(y.slope), encode_rational(y.offset),
    ))
    return cursor.lastrowid


def load_scale_revision(db, scale_id):
    row = db.execute('''
        SELECT scale_id, project, bench, x_slope, x_offset, y_slope, y_offset
        FROM scale_revisions WHERE scale_id = ?
    ''', (scale_id,)).fetchone()
    if row is None:
        return None
    return ScaleRevision(
        row['scale_id'], row['project'], row['bench'],
        AxisTransform(decode_rational(row['x_slope']), decode_rational(row['x_offset'])),
        AxisTransform(decode_rational(row['y_slope']), decode_rational(row['y_offset'])),
    )
