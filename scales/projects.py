from dataclasses import dataclass


def require_label(value, name):
    if not isinstance(value, str) or not value or value != value.strip() or '\x00' in value:
        raise ValueError(f'{name} must be nonempty text without padding or NUL')
    return value


def _validate_axes(x_axis, x_unit, y_axis, y_unit):
    require_label(x_axis, 'x axis')
    require_label(y_axis, 'y axis')
    require_label(x_unit, 'x unit')
    require_label(y_unit, 'y unit')
    if x_axis == y_axis:
        raise ValueError('axis names must be distinct')


@dataclass(frozen=True)
class ProjectAxes:
    project: str
    x_axis: str
    x_unit: str
    y_axis: str
    y_unit: str

    def __post_init__(self):
        require_label(self.project, 'project')
        _validate_axes(self.x_axis, self.x_unit, self.y_axis, self.y_unit)


@dataclass(frozen=True)
class BenchAxes:
    bench: str
    x_axis: str
    x_unit: str
    y_axis: str
    y_unit: str

    def __post_init__(self):
        require_label(self.bench, 'bench')
        _validate_axes(self.x_axis, self.x_unit, self.y_axis, self.y_unit)


def validate_axis_mapping(project, bench, x_mapping, y_mapping):
    expected_x = (bench.x_axis, bench.x_unit, project.x_axis, project.x_unit)
    expected_y = (bench.y_axis, bench.y_unit, project.y_axis, project.y_unit)
    if x_mapping != expected_x or y_mapping != expected_y:
        raise ValueError('input and output axes or units do not match registration')


INITIAL_AXES = (
    (
        ProjectAxes('repeatability', 'reference_x', 'mm', 'reference_y', 'mm'),
        tuple(BenchAxes(name, 'dial_x', 'tick', 'dial_y', 'tick') for name in ('a', 'b', 'c')),
    ),
)
