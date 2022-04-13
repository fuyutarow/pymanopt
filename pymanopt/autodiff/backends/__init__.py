__all__ = ["jax", "autograd", "numpy", "pytorch", "tensorflow"]

from .. import backend_decorator_factory
from ._jax import JaxBackend
from ._autograd import AutogradBackend
from ._numpy import NumPyBackend
from ._pytorch import PyTorchBackend
from ._tensorflow import TensorFlowBackend


jax = backend_decorator_factory(JaxBackend)
autograd = backend_decorator_factory(AutogradBackend)
numpy = backend_decorator_factory(NumPyBackend)
pytorch = backend_decorator_factory(PyTorchBackend)
tensorflow = backend_decorator_factory(TensorFlowBackend)
