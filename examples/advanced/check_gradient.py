import autograd.numpy as np
import tensorflow as tf
import torch

import pymanopt
from examples._tools import ExampleRunner
from pymanopt import Problem
from pymanopt.manifolds import Sphere
from pymanopt.tools.diagnostics import check_gradient


SUPPORTED_BACKENDS = ("autograd", "numpy", "pytorch", "tensorflow")


def create_cost_egrad(manifold, matrix, backend):
    egrad = None

    if backend == "autograd":

        @pymanopt.function.autograd(manifold)
        def cost(x):
            return -np.inner(x, matrix @ x)

    elif backend == "numpy":

        @pymanopt.function.numpy(manifold)
        def cost(x):
            return -np.inner(x, matrix @ x)

        @pymanopt.function.numpy(manifold)
        def egrad(x):
            return -2 * matrix @ x

    elif backend == "pytorch":
        matrix_ = torch.from_numpy(matrix)

        @pymanopt.function.pytorch(manifold)
        def cost(x):
            return -x @ matrix_ @ x

    elif backend == "tensorflow":

        @pymanopt.function.tensorflow(manifold)
        def cost(x):
            return -tf.tensordot(x, tf.tensordot(matrix, x, axes=1), axes=1)

    else:
        raise ValueError(f"Unsupported backend '{backend}'")

    return cost, egrad


def run(backend=SUPPORTED_BACKENDS[0], quiet=True):
    n = 128
    manifold = Sphere(n)

    # Generate random problem data.
    matrix = np.random.randn(n, n)
    matrix = 0.5 * (matrix + matrix.T)
    cost, egrad = create_cost_egrad(manifold, matrix, backend)

    # Create the problem structure.
    problem = Problem(manifold=manifold, cost=cost, egrad=egrad)
    if quiet:
        problem.verbosity = 0

    # Numerically check gradient consistency (optional).
    check_gradient(problem)


if __name__ == "__main__":
    runner = ExampleRunner(
        run, "Check gradient for sphere manifold", SUPPORTED_BACKENDS
    )
    runner.run()
