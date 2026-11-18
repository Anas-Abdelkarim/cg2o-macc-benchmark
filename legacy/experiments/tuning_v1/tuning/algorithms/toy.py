"""Algorithm of the toy experiment (see experiments/toy.py): a minimal example of an algorithm file."""
from ..constraints import Constraint
from ..params import Cat, Float, Int, Log, ParamSpace
from ..registry import register
from ..spec import AlgorithmSpec

register(AlgorithmSpec(
    name="toy",
    description="toy test function (no simulation); template for new algorithms",
    params=ParamSpace([
        Float("toy.x", -5.0, 5.0, default=0.0, doc="optimum at 2"),
        Log("toy.y", 1e-3, 1e2, default=1.0, doc="optimum at 0.1"),
        Int("toy.n", 1, 10, default=5, doc="optimum at 7"),
        Cat("toy.mode", ["slow", "fast"], default="slow", doc="fast is better"),
    ]),
    experiment="toy",
    setup=dict(cases=("a", "b")),
    constraints=(Constraint("violation", "<=", 0.5, "violation"),),
    default_objective="toy_loss"))
