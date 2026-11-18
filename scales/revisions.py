from db import require_id, transaction
from scales.axes import make_axis_transforms
from scales.projects import require_label
from scales.store import (
    insert_scale_revision,
    load_bench_axes,
    load_project_axes,
    load_scale_revision,
)


def set_scale(db, project, bench, *, x, y):
    require_label(project, 'project')
    require_label(bench, 'bench')
    with transaction(db):
        project_axes = load_project_axes(db, project)
        bench_axes = load_bench_axes(db, project, bench)
        if project_axes is None or bench_axes is None:
            raise ValueError('unknown project or bench')
        x_transform, y_transform = make_axis_transforms(project_axes, bench_axes, x, y)
        return insert_scale_revision(db, project, bench, x_transform, y_transform)


def require_scale_revision(db, scale_id, *, project=None, bench=None):
    require_id(scale_id, 'scale ID')
    revision = load_scale_revision(db, scale_id)
    if revision is None:
        raise ValueError('unknown scale revision')
    if project is not None and revision.project != project:
        raise ValueError('scale revision belongs to another project')
    if bench is not None and revision.bench != bench:
        raise ValueError('scale revision belongs to another bench')
    return revision
