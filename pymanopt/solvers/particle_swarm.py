import time

import numpy as np
import numpy.random as rnd

from pymanopt.solvers.solver import Solver
from pymanopt.tools import printer


class ParticleSwarm(Solver):
    """Particle swarm optimization (PSO) method.

    Perform optimization using the derivative-free particle swarm optimization
    algorithm.

    Args:
        maxcostevals: Maximum number of allowed cost evaluations.
        maxiter: Maximum number of allowed iterations.
        populationsize: Size of the considered swarm population.
        nostalgia: Quantifies performance relative to past performances.
        social: Quantifies performance relative to neighbors.
    """

    def __init__(
        self,
        maxcostevals=None,
        maxiter=None,
        populationsize=None,
        nostalgia=1.4,
        social=1.4,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._maxcostevals = maxcostevals
        self._maxiter = maxiter
        self._populationsize = populationsize
        self._nostalgia = nostalgia
        self._social = social

    def solve(self, problem, x=None):
        """Run PSO algorithm.

        Args:
            problem: Pymanopt problem class instance exposing the cost function
                and the manifold to optimize over.
            x: Initial point on the manifold.
                If no value is provided then a starting point will be randomly
                generated.

        Returns:
            Local minimum of the cost function, or the most recent iterate if
            algorithm terminated before convergence.
        """
        man = problem.manifold
        verbosity = problem.verbosity
        objective = problem.cost

        # Choose proper default algorithm parameters. We need to know about the
        # dimension of the manifold to limit the parameter range, so we have to
        # defer proper initialization until this point.
        dim = man.dim
        if self._maxcostevals is None:
            self._maxcostevals = max(5000, 2 * dim)
        if self._maxiter is None:
            self._maxiter = max(500, 4 * dim)
        if self._populationsize is None:
            self._populationsize = min(40, 10 * dim)

        # If no initial population x is given by the user, generate one at
        # random.
        if x is None:
            x = [man.rand() for i in range(int(self._populationsize))]
        elif not hasattr(x, "__iter__"):
            raise ValueError("The initial population x must be iterable")
        else:
            if len(x) != self._populationsize:
                print(
                    "The population size was forced to the size of "
                    "the given initial population"
                )
                self._populationsize = len(x)

        # Initialize personal best positions to the initial population.
        y = list(x)

        # Save a copy of the swarm at the previous iteration.
        xprev = list(x)

        # Initialize velocities for each particle.
        v = [man.randvec(xi) for xi in x]

        # Compute cost for each particle xi.
        costs = np.array([objective(xi) for xi in x])
        fy = list(costs)
        costevals = self._populationsize

        # Identify the best particle and store its cost/position.
        imin = costs.argmin()
        fbest = costs[imin]
        xbest = x[imin]

        if verbosity >= 2:
            iter_format_length = int(np.log10(self._maxiter)) + 1
            column_printer = printer.ColumnPrinter(
                columns=[
                    ("Iteration", f"{iter_format_length}d"),
                    ("Cost evaluations", "7d"),
                    ("Best cost", "+.8e"),
                ]
            )
        else:
            column_printer = printer.VoidPrinter()

        column_printer.print_header()

        self._start_optlog()

        # Iteration counter (at any point, iter is the number of fully executed
        # iterations so far).
        iter = 0
        time0 = time.time()

        while True:
            iter += 1

            column_printer.print_row([iter, costevals, fbest])

            # Stop if any particle triggers a stopping criterion.
            for i, xi in enumerate(x):
                stop_reason = self._check_stopping_criterion(
                    time0, iter=iter, costevals=costevals
                )
                if stop_reason is not None:
                    break
            if stop_reason:
                if verbosity >= 1:
                    print(stop_reason)
                    print("")
                break

            # Compute the inertia factor which we linearly decrease from 0.9 to
            # 0.4 from iter = 0 to iter = maxiter.
            w = 0.4 + 0.5 * (1 - iter / self._maxiter)

            # Compute the velocities.
            for i, xi in enumerate(x):
                # Get the position and past best position of particle i.
                yi = y[i]

                # Get the previous position and velocity of particle i.
                xiprev = xprev[i]
                vi = v[i]

                # Compute the new velocity of particle i, composed of three
                # contributions.
                inertia = w * man.transp(xiprev, xi, vi)
                nostalgia = rnd.rand() * self._nostalgia * man.log(xi, yi)
                social = rnd.rand() * self._social * man.log(xi, xbest)

                v[i] = inertia + nostalgia + social

            # Backup the current swarm positions.
            xprev = list(x)

            # Update positions, personal bests and global best.
            for i, xi in enumerate(x):
                # Compute new position of particle i.
                x[i] = man.retr(xi, v[i])
                # Compute new cost of particle i.
                fxi = objective(xi)

                # Update costs of the swarm.
                costs[i] = fxi
                # Update self-best if necessary.
                if fxi < fy[i]:
                    fy[i] = fxi
                    y[i] = xi
                    # Update global best if necessary.
                    if fy[i] < fbest:
                        fbest = fy[i]
                        xbest = xi
            costevals += self._populationsize

        if self._logverbosity <= 0:
            return xbest
        else:
            self._stop_optlog(
                xbest,
                fbest,
                stop_reason,
                time0,
                costevals=costevals,
                iter=iter,
            )
            return xbest, self._optlog
