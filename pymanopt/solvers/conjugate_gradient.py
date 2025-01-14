import time
from copy import deepcopy

import numpy as np

from pymanopt import tools
from pymanopt.solvers.linesearch import LineSearchAdaptive
from pymanopt.solvers.solver import Solver
from pymanopt.tools import printer


# TODO: Use Python's enum module.
BetaTypes = tools.make_enum(
    "BetaTypes",
    "FletcherReeves PolakRibiere HestenesStiefel HagerZhang".split(),
)


class ConjugateGradient(Solver):
    """Riemannian conjugate gradient method.

    Perform optimization using nonlinear conjugate gradient method with
    linesearch.
    This method first computes the gradient of the cost function, and then
    optimizes by moving in a direction that is conjugate to all previous search
    directions.

    Args:
        beta_type: Conjugate gradient beta rule used to construct the new
            search direction.
        orth_value: Parameter for Powell's restart strategy.
            An infinite value disables this strategy.
            See in code formula for the specific criterion used.
        linesearch: The line search method.
    """

    def __init__(
        self,
        beta_type=BetaTypes.HestenesStiefel,
        orth_value=np.inf,
        linesearch=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._beta_type = beta_type
        self._orth_value = orth_value

        if linesearch is None:
            self._linesearch = LineSearchAdaptive()
        else:
            self._linesearch = linesearch
        self.linesearch = None

    def solve(self, problem, x=None, reuselinesearch=False):
        """Run CG method.

        Args:
            problem: Pymanopt problem class instance exposing the cost function
                and the manifold to optimize over.
                The class must either
            x: Initial point on the manifold.
                If no value is provided then a starting point will be randomly
                generated.
            reuselinesearch: Whether to reuse the previous linesearch object.
                Allows to use information from a previous call to
                :meth:`solve`.

        Returns:
            Local minimum of the cost function, or the most recent iterate if
            algorithm terminated before convergence.
        """
        man = problem.manifold
        verbosity = problem.verbosity
        objective = problem.cost
        gradient = problem.grad

        if not reuselinesearch or self.linesearch is None:
            self.linesearch = deepcopy(self._linesearch)
        linesearch = self.linesearch

        # If no starting point is specified, generate one at random.
        if x is None:
            x = man.rand()

        if verbosity >= 1:
            print("Optimizing...")
        if verbosity >= 2:
            iter_format_length = int(np.log10(self._maxiter)) + 1
            column_printer = printer.ColumnPrinter(
                columns=[
                    ("Iteration", f"{iter_format_length}d"),
                    ("Cost", "+.16e"),
                    ("Gradient norm", ".8e"),
                ]
            )
        else:
            column_printer = printer.VoidPrinter()

        column_printer.print_header()

        # Calculate initial cost-related quantities
        cost = objective(x)
        grad = gradient(x)
        gradnorm = man.norm(x, grad)
        Pgrad = problem.precon(x, grad)
        gradPgrad = man.inner(x, grad, Pgrad)

        # Initial descent direction is the negative gradient
        desc_dir = -Pgrad

        self._start_optlog(
            extraiterfields=["gradnorm"],
            solverparams={
                "beta_type": self._beta_type,
                "orth_value": self._orth_value,
                "linesearcher": linesearch,
            },
        )

        # Initialize iteration counter and timer
        iter = 0
        stepsize = np.nan
        time0 = time.time()

        while True:
            column_printer.print_row([iter, cost, gradnorm])

            if self._logverbosity >= 2:
                self._append_optlog(iter, x, cost, gradnorm=gradnorm)

            stop_reason = self._check_stopping_criterion(
                time0, gradnorm=gradnorm, iter=iter + 1, stepsize=stepsize
            )

            if stop_reason:
                if verbosity >= 1:
                    print(stop_reason)
                    print("")
                break

            # The line search algorithms require the directional derivative of
            # the cost at the current point x along the search direction.
            df0 = man.inner(x, grad, desc_dir)

            # If we didn't get a descent direction: restart, i.e., switch to
            # the negative gradient. Equivalent to resetting the CG direction
            # to a steepest descent step, which discards the past information.
            if df0 >= 0:
                # Or we switch to the negative gradient direction.
                if verbosity >= 3:
                    print(
                        "Conjugate gradient info: got an ascent direction "
                        f"(df0 = {df0:.2f}), reset to the (preconditioned) "
                        "steepest descent direction."
                    )
                # Reset to negative gradient: this discards the CG memory.
                desc_dir = -Pgrad
                df0 = -gradPgrad

            # Execute line search
            stepsize, newx = linesearch.search(
                objective, man, x, desc_dir, cost, df0
            )

            # Compute the new cost-related quantities for newx
            newcost = objective(newx)
            newgrad = gradient(newx)
            newgradnorm = man.norm(newx, newgrad)
            Pnewgrad = problem.precon(newx, newgrad)
            newgradPnewgrad = man.inner(newx, newgrad, Pnewgrad)

            # Apply the CG scheme to compute the next search direction
            oldgrad = man.transp(x, newx, grad)
            orth_grads = man.inner(newx, oldgrad, Pnewgrad) / newgradPnewgrad

            # Powell's restart strategy (see page 12 of Hager and Zhang's
            # survey on conjugate gradient methods, for example)
            if abs(orth_grads) >= self._orth_value:
                beta = 0
                desc_dir = -Pnewgrad
            else:
                desc_dir = man.transp(x, newx, desc_dir)

                if self._beta_type == BetaTypes.FletcherReeves:
                    beta = newgradPnewgrad / gradPgrad
                elif self._beta_type == BetaTypes.PolakRibiere:
                    diff = newgrad - oldgrad
                    ip_diff = man.inner(newx, Pnewgrad, diff)
                    beta = max(0, ip_diff / gradPgrad)
                elif self._beta_type == BetaTypes.HestenesStiefel:
                    diff = newgrad - oldgrad
                    ip_diff = man.inner(newx, Pnewgrad, diff)
                    try:
                        beta = max(
                            0, ip_diff / man.inner(newx, diff, desc_dir)
                        )
                    # if ip_diff = man.inner(newx, diff, desc_dir) = 0
                    except ZeroDivisionError:
                        beta = 1
                elif self._beta_type == BetaTypes.HagerZhang:
                    diff = newgrad - oldgrad
                    Poldgrad = man.transp(x, newx, Pgrad)
                    Pdiff = Pnewgrad - Poldgrad
                    deno = man.inner(newx, diff, desc_dir)
                    numo = man.inner(newx, diff, Pnewgrad)
                    numo -= (
                        2
                        * man.inner(newx, diff, Pdiff)
                        * man.inner(newx, desc_dir, newgrad)
                        / deno
                    )
                    beta = numo / deno
                    # Robustness (see Hager-Zhang paper mentioned above)
                    desc_dir_norm = man.norm(newx, desc_dir)
                    eta_HZ = -1 / (desc_dir_norm * min(0.01, gradnorm))
                    beta = max(beta, eta_HZ)
                else:
                    types = ", ".join(
                        [f"BetaTypes.{t}" for t in BetaTypes._fields]
                    )
                    raise ValueError(
                        f"Unknown beta_type {self._beta_type}. Should be one "
                        f"of {types}."
                    )

                desc_dir = -Pnewgrad + beta * desc_dir

            # Update the necessary variables for the next iteration.
            x = newx
            cost = newcost
            grad = newgrad
            Pgrad = Pnewgrad
            gradnorm = newgradnorm
            gradPgrad = newgradPnewgrad

            iter += 1

        if self._logverbosity <= 0:
            return x
        else:
            self._stop_optlog(
                x,
                cost,
                stop_reason,
                time0,
                stepsize=stepsize,
                gradnorm=gradnorm,
                iter=iter,
            )
            return x, self._optlog
