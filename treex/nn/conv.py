import typing as tp

import jax
import jax.numpy as jnp
import numpy as np
from flax.linen import linear as flax_module

from treex import tree_object, types
from treex.module import Module


class Conv(Module):
    """Convolution Module wrapping lax.conv_general_dilated.

    `Conv` is implemented as a wrapper over `flax.linen.Conv`, its constructor
    arguments accept almost the same arguments including any Flax artifacts such as initializers.
    Main differences:

    * receives `features_in` as a first argument since shapes must be statically known.
    * `features` argument is renamed to `features_out`.
    """

    # pytree
    kernel: tp.Optional[jnp.ndarray] = types.Parameter.field()
    bias: tp.Optional[jnp.ndarray] = types.Parameter.field()

    # props
    features_in: int
    features_out: int
    kernel_size: tp.Union[int, tp.Iterable[int]]
    strides: tp.Optional[tp.Iterable[int]]
    padding: tp.Union[str, tp.Iterable[tp.Tuple[int, int]]]
    input_dilation: tp.Optional[tp.Iterable[int]]
    kernel_dilation: tp.Optional[tp.Iterable[int]]
    feature_group_count: int
    use_bias: bool
    dtype: flax_module.Dtype
    precision: tp.Any
    kernel_init: tp.Callable[
        [flax_module.PRNGKey, flax_module.Shape, flax_module.Dtype],
        flax_module.Array,
    ]
    bias_init: tp.Callable[
        [flax_module.PRNGKey, flax_module.Shape, flax_module.Dtype],
        flax_module.Array,
    ]

    def __init__(
        self,
        features_in: int,
        features_out: int,
        kernel_size: tp.Union[int, tp.Iterable[int]],
        strides: tp.Optional[tp.Iterable[int]] = None,
        padding: tp.Union[str, tp.Iterable[tp.Tuple[int, int]]] = "SAME",
        input_dilation: tp.Optional[tp.Iterable[int]] = None,
        kernel_dilation: tp.Optional[tp.Iterable[int]] = None,
        feature_group_count: int = 1,
        use_bias: bool = True,
        dtype: flax_module.Dtype = jnp.float32,
        precision: tp.Any = None,
        kernel_init: tp.Callable[
            [flax_module.PRNGKey, flax_module.Shape, flax_module.Dtype],
            flax_module.Array,
        ] = flax_module.default_kernel_init,
        bias_init: tp.Callable[
            [flax_module.PRNGKey, flax_module.Shape, flax_module.Dtype],
            flax_module.Array,
        ] = flax_module.zeros,
    ):
        """
        Arguments:
            features_in: the number of input features.
            features_out: number of convolution filters.
            kernel_size: shape of the convolutional kernel. For 1D convolution,
                the kernel size can be passed as an integer. For all other cases, it must
                be a sequence of integers.
            strides: a sequence of `n` integers, representing the inter-window
                strides.
            padding: either the string `'SAME'`, the string `'VALID'`, or a sequence
                of `n` `(low, high)` integer pairs that give the padding to apply before
                and after each spatial dimension.
            input_dilation: `None`, or a sequence of `n` integers, giving the
                dilation factor to apply in each spatial dimension of `inputs`.
                Convolution with input dilation `d` is equivalent to transposed
                convolution with stride `d`.
            kernel_dilation: `None`, or a sequence of `n` integers, giving the
                dilation factor to apply in each spatial dimension of the convolution
                kernel. Convolution with kernel dilation is also known as 'atrous
                convolution'.
            feature_group_count: integer, default 1. If specified divides the input
                features into groups.
            use_bias: whether to add a bias to the output (default: True).
            dtype: the dtype of the computation (default: float32).
            precision: numerical precision of the computation see `jax.lax.Precision`
                for details.
            kernel_init: initializer for the convolutional kernel.
            bias_init: initializer for the bias.
        """
        super().__init__()
        self.features_in = features_in
        self.features_out = features_out
        self.kernel_size = kernel_size
        self.strides = strides
        self.padding = padding
        self.input_dilation = input_dilation
        self.kernel_dilation = kernel_dilation
        self.feature_group_count = feature_group_count
        self.use_bias = use_bias
        self.dtype = dtype
        self.precision = precision
        self.kernel_init = kernel_init
        self.bias_init = bias_init

        self.kernel = None
        self.bias = None

    @property
    def module(self) -> flax_module.Conv:
        return flax_module.Conv(
            features=self.features_out,
            kernel_size=self.kernel_size,
            strides=self.strides,
            padding=self.padding,
            input_dilation=self.input_dilation,
            kernel_dilation=self.kernel_dilation,
            feature_group_count=self.feature_group_count,
            use_bias=self.use_bias,
            dtype=self.dtype,
            precision=self.precision,
            kernel_init=self.kernel_init,
            bias_init=self.bias_init,
        )

    def module_init(self, key: jnp.ndarray):
        if isinstance(self.module.kernel_size, int):
            ndim = 1
            mindim = self.module.kernel_size
        else:
            ndim = len(list(self.module.kernel_size))
            mindim = min(self.module.kernel_size)

        mindim *= 2

        shape = list(range(mindim, mindim + ndim + 1))
        shape[-1] = self.features_in

        x = jax.random.uniform(key, shape=shape)

        variables = self.module.init(key, x).unfreeze()

        # Extract collections
        self.kernel = variables["params"]["kernel"]

        if self.use_bias:
            self.bias = variables["params"]["bias"]

    def __call__(self, x: np.ndarray) -> jnp.ndarray:
        """Applies a convolution to the inputs.

        Arguments:
            x: input data with dimensions (batch, spatial_dims..., features).

        Returns:
            The convolved data.
        """
        assert self.initialized, "Module not initialized"

        params = dict(kernel=self.kernel)

        if self.use_bias:
            params["bias"] = self.bias

        output = self.module.apply(dict(params=params), x)

        return tp.cast(jnp.ndarray, output)
