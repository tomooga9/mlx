
# Copyright © 2024 Apple Inc.

import math
from typing import Callable, Optional

import mlx.core as mx
from mlx.nn.layers.activations import tanh
from mlx.nn.layers.base import Module


class RNN(Module):
    r"""An Elman recurrent layer.

    The input is a sequence of shape ``NLD`` or ``LD`` where:

    * ``N`` is the optional batch dimension
    * ``L`` is the sequence length
    * ``D`` is the input's feature dimension

    Concretely, for each element along the sequence length axis, this
    layer applies the function:

    .. math::

        h_{t + 1} = \text{tanh} (W_{ih}x_t + W_{hh}h_t + b)

    The hidden state :math:`h` has shape ``NH`` or ``H``, depending on
    whether the input is batched or not. Returns the hidden state at each
    time step, of shape ``NLH`` or ``LH``.

    Args:
        input_size (int): Dimension of the input, ``D``.
        hidden_size (int): Dimension of the hidden state, ``H``.
        bias (bool, optional): Whether to use a bias. Default: ``True``.
        nonlinearity (callable, optional): Non-linearity to use. If ``None``,
            then func:`tanh` is used. Default: ``None``.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        bias: bool = True,
        nonlinearity: Optional[Callable] = None,
    ):
        super().__init__()

        self.nonlinearity = nonlinearity or tanh
        if not callable(self.nonlinearity):
            raise ValueError(
                f"Nonlinearity must be callable. Current value: {nonlinearity}."
            )

        scale = 1.0 / math.sqrt(hidden_size)
        self.hidden_size = hidden_size
        self.Wxh = mx.random.uniform(
            low=-scale, high=scale, shape=(input_size, hidden_size)
        )
        self.Whh = mx.random.uniform(
            low=-scale, high=scale, shape=(hidden_size, hidden_size)
        )
        self.bias = (
            mx.random.uniform(low=-scale, high=scale, shape=(hidden_size,))
            if bias
            else None
        )

    def _extra_repr(self):
        return (
            f"input_dims={self.Wxh.shape[0]}, "
            f"hidden_size={self.hidden_size}, "
            f"nonlinearity={self.nonlinearity}, bias={self.bias is not None}"
        )

    def __call__(self, x, hidden=None):
        if self.bias is not None:
            x = mx.addmm(self.bias, x, self.Wxh)
        else:
            x = x @ self.Wxh

        all_hidden = []
        for idx in range(x.shape[-2]):
            if hidden is not None:
                hidden = x[..., idx, :] + hidden @ self.Whh
            else:
                hidden = x[..., idx, :]
            hidden = self.nonlinearity(hidden)
            all_hidden.append(hidden)

        return mx.stack(all_hidden, axis=-2)


class GRU(Module):
    r"""A gated recurrent unit (GRU) RNN layer.

    The input has shape ``NLD`` or ``LD`` where:

    * ``N`` is the optional batch dimension
    * ``L`` is the sequence length
    * ``D`` is the input's feature dimension

    Concretely, for each element of the sequence, this layer computes:

    .. math::

        \begin{align*}
        r_t &= \sigma (W_{xr}x_t + W_{hr}h_t + b_{r}) \\
        z_t &= \sigma (W_{xz}x_t + W_{hz}h_t + b_{z}) \\
        n_t &= \text{tanh}(W_{xn}x_t + b_{n} + r_t \odot (W_{hn}h_t + b_{hn})) \\
        h_{t + 1} &= (1 - z_t) \odot n_t + z_t \odot h_t
        \end{align*}

    The hidden state :math:`h` has shape ``NH`` or ``H`` depending on
    whether the input is batched or not. Returns the hidden state at each
    time step of shape ``NLH`` or ``LH``.

    Args:
        input_size (int): Dimension of the input, ``D``.
        hidden_size (int): Dimension of the hidden state, ``H``.
        bias (bool): Whether to use biases or not. Default: ``True``.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        bias: bool = True,
    ):
        super().__init__()

        self.hidden_size = hidden_size
        scale = 1.0 / math.sqrt(hidden_size)
        self.Wx = mx.random.uniform(
            low=-scale, high=scale, shape=(input_size, 3 * hidden_size)
        )
        self.Wh = mx.random.uniform(
            low=-scale, high=scale, shape=(hidden_size, 3 * hidden_size)
        )
        self.b = (
            mx.random.uniform(low=-scale, high=scale, shape=(3 * hidden_size,))
            if bias
            else None
        )
        self.bhn = (
            mx.random.uniform(low=-scale, high=scale, shape=(hidden_size,))
            if bias
            else None
        )

    def _extra_repr(self):
        return (
            f"input_dims={self.Wx.shape[0]}, "
            f"hidden_size={self.hidden_size}, bias={self.b is not None}"
        )

    def __call__(self, x, hidden=None):
        if self.b is not None:
            x = mx.addmm(self.b, x, self.Wx)
        else:
            x = x @ self.Wx

        x_rz = x[..., : -self.hidden_size]
        x_n = x[..., -self.hidden_size :]

        all_hidden = []

        for idx in range(x.shape[-2]):
            rz = x_rz[..., idx, :]
            if hidden is not None:
                h_proj = hidden @ self.Wh
                h_proj_rz = h_proj[..., : -self.hidden_size]
                h_proj_n = h_proj[..., -self.hidden_size :]

                if self.bhn is not None:
                    h_proj_n += self.bhn

                rz = rz + h_proj_rz

            rz = mx.sigmoid(rz)

            r, z = mx.split(rz, 2, axis=-1)

            n = x_n[..., idx, :]

            if hidden is not None:
                n = n + r * h_proj_n
            n = mx.tanh(n)

            hidden = (1 - z) * n
            if hidden is not None:
                hidden = hidden + z * hidden
            all_hidden.append(hidden)

        return mx.stack(all_hidden, axis=-2)


class LSTM(Module):
    r"""An LSTM recurrent layer.

    The input has shape ``NLD`` or ``LD`` where:

    * ``N`` is the optional batch dimension
    * ``L`` is the sequence length
    * ``D`` is the input's feature dimension

    Concretely, for each element of the sequence, this layer computes:

    .. math::
        \begin{align*}
        i_t &= \sigma (W_{xi}x_t + W_{hi}h_t + b_{i}) \\
        f_t &= \sigma (W_{xf}x_t + W_{hf}h_t + b_{f}) \\
        g_t &= \text{tanh} (W_{xg}x_t + W_{hg}h_t + b_{g}) \\
        o_t &= \sigma (W_{xo}x_t + W_{ho}h_t + b_{o}) \\
        c_{t + 1} &= f_t \odot c_t + i_t \odot g_t \\
        h_{t + 1} &= o_t \text{tanh}(c_{t + 1})
        \end{align*}

    The hidden state :math:`h` and cell state :math:`c` have shape ``NH``
    or ``H``, depending on whether the input is batched or not.

    The layer returns two arrays, the hidden state and the cell state at
    each time step, both of shape ``NLH`` or ``LH``.

    Args:
        input_size (int): Dimension of the input, ``D``.
        hidden_size (int): Dimension of the hidden state, ``H``.
        bias (bool): Whether to use biases or not. Default: ``True``.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        bias: bool = True,
    ):
        super().__init__()

        self.hidden_size = hidden_size
        scale = 1.0 / math.sqrt(hidden_size)
        self.Wx = mx.random.uniform(
            low=-scale, high=scale, shape=(input_size, 4 * hidden_size)
        )
        self.Wh = mx.random.uniform(
            low=-scale, high=scale, shape=(hidden_size, 4 * hidden_size)
        )
        self.bias = (
            mx.random.uniform(low=-scale, high=scale, shape=(4 * hidden_size,))
            if bias
            else None
        )

    def _extra_repr(self):
        return (
            f"input_dims={self.Wx.shape[0]}, "
            f"hidden_size={self.hidden_size}, bias={self.bias is not None}"
        )

    def __call__(self, x, hidden=None, cell=None):
        if self.bias is not None:
            x = mx.addmm(self.bias, x, self.Wx)
        else:
            x = x @ self.Wx

        all_hidden = []
        all_cell = []

        for idx in range(x.shape[-2]):
            ifgo = x[..., idx, :]
            if hidden is not None:
                ifgo = ifgo + hidden @ self.Wh
            i, f, g, o = mx.split(ifgo, 4, axis=-1)

            i = mx.sigmoid(i)
            f = mx.sigmoid(f)
            g = mx.tanh(g)
            o = mx.sigmoid(o)

            if cell is not None:
                cell = f * cell + i * g
            else:
                cell = i * g
            hidden = o * mx.tanh(cell)

            all_cell.append(cell)
            all_hidden.append(hidden)

        return mx.stack(all_hidden, axis=-2), mx.stack(all_cell, axis=-2)

r"""A Convolutional LSTM Cell.
    
    The input has shape ``NHWC`` or ``HWC`` where:

    * ``N`` is the optional batch dimension
    * ``H`` is the input's spatial height dimension
    * ``W`` is the input's spatial weight dimension
    * ``C`` is the input's channel dimension

    Concretely, for the input, this layer computes:

    .. math::
        \begin{align*}
        i_t &= \sigma (W_{xi} \ast X_t + W_{hi} \ast H_{t-1} + W_{ci} \odot C_{t-1} + b_{i}) \\
        f_t &= \sigma (W_{xf} \odot X_t + W_{hf} \ast H_{t-1} + W_{cf} \odot C_{t-1} + b_{f}) \\
        C_t &= f_t \odot C_{t-1} + i_t \odot tanh(W_{xc} \ast X_{t} + W_{hc} * H_{t-1} + b_{c} \\
        o_t &= \sigma (W_{xo} * X_{t} + W_{ho} \ast H_{t-1} + W_{co} \odot C_{t} + b_{o} \\
        H_t &= o_{t} \dot tanh(C_{t})
        \end{align*}

    The hidden state :math:`H` and cell state :math:`C` have shape ``NHWO``
    or ``HWO``, depending on whether the input is batched or not.

    The cell returns two arrays, the hidden state and the cell state, at each time step, with shape ``NHWO`` or ``HWO``.

    Args:
        in_channels (int): The number of input channels, ``C``.
        out_channels (int): The number of output channels,  ``O``.
        kernel_size (int): The size of the convolution filters, must be odd to keep spatial dimensions with padding. Default: ``5``.
        bias (bool): Whether to use biases or not. Default: ``True``.
    """

class ConvLSTMCell(nn.Module):
    def __init__(
        self, 
        in_channels: int, 
        out_channels: int, 
        kernel_size: Union[int, tuple] = 5, 
        stride: Union[int, tuple] = 1, 
        padding: Union[int, tuple] = 2, 
        dilation: Union[int, tuple] = 1, 
        bias: bool = True,
        ):
        
        super(ConvLSTMCell, self).__init__()

        # creating one conv for all matrix generation
        self.conv = nn.Conv2d(in_channels + out_channels, out_channels * 4, kernel_size, stride, padding, dilation, bias)

    def __call__(self, x_t, prev):
        h_t, c_t = prev

        # concatenating input and hidden by channel dimension
        x = mx.concatenate([x_t, h_t], axis=-1)

        # getting weights for input, forget, cell, and hidden gates respectively through Conv2d layer
        xh_i, xh_f, xh_c, xh_o = mx.split(self.conv(x), 4, axis=-1)

        # forget gate
        f = mx.sigmoid(xh_f)

        # update cell state
        c = c_t * f

        # input gate
        i = mx.sigmoid(xh_i)

        # new candidate
        c_candidate = mx.tanh(xh_c)

        # update cell state
        c = c + i * c_candidate

        # output gate
        o = mx.sigmoid(xh_o)

        # update hidden state
        h = o * mx.tanh(c)

        # returns a tuple of the hidden state and cell state
        return (h, c)
        
r"""A Convolutional LSTM recurrent layer.
    
    The input has shape ``NLHWC`` or ``LHWC`` where:

    * ``N`` is the optional batch dimension
    * ``L`` is the sequence length
    * ``H`` is the input's spatial height dimension
    * ``W`` is the input's spatial weight dimension
    * ``C`` is the input's channel dimension

    Concretely, for each element of the sequence, this layer computes:

    .. math::
        \begin{align*}
        i_t &= \sigma (W_{xi} \ast X_t + W_{hi} \ast H_{t-1} + W_{ci} \odot C_{t-1} + b_{i}) \\
        f_t &= \sigma (W_{xf} \odot X_t + W_{hf} \ast H_{t-1} + W_{cf} \odot C_{t-1} + b_{f}) \\
        C_t &= f_t \odot C_{t-1} + i_t \odot tanh(W_{xc} \ast X_{t} + W_{hc} * H_{t-1} + b_{c} \\
        o_t &= \sigma (W_{xo} * X_{t} + W_{ho} \ast H_{t-1} + W_{co} \odot C_{t} + b_{o} \\
        H_t &= o_{t} \dot tanh(C_{t})
        \end{align*}

    The hidden state :math:`H` and cell state :math:`C` have shape ``NHWO``
    or ``HWO``, depending on whether the input is batched or not.

    The cell returns one array, the hidden state, at each time step, with 
    shape ``NLHWO`` or ``LHWO``.

    Args:
        in_channels (int): The number of input channels, ``C``.
        out_channels (int): The number of output channels,  ``O``.
        kernel_size (int): The size of the convolution filters, must be odd to keep spatial dimensions with padding. Default: ``5``.
        bias (bool): Whether to use biases or not. Default: ``True``.
    """

class ConvLSTM(nn.Module):
    def __init__(
        self, 
        in_channels: int, 
        out_channels: int, 
        kernel_size: int = 5, 
        bias: bool = True,
        ):
        super(ConvLSTM, self).__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size

        assert self.kernel_size % 2 == 1, f"Kernel size should be odd for same-dimensional spatial padding. Got: {self.kernel_size}"

        padding = kernel_size // 2
        self.cell = ConvLSTMCell(in_channels, out_channels, kernel_size, stride=1, padding, dilation=1, bias)


    def __call__(self, x):
        b, t, h, w, c = x.shape
        assert c == self.in_channels, f"Channel dimension should be {self.in_channels}. Got: {c}"

        # initializing tensor for initial hidden and cell states
        h_t = mx.zeros([b, h, w, self.out_channels])
        c_t = mx.zeros([b, h, w, self.out_channels])

        # initializing time-first array for unrolling over time-steps
        hidden_states = mx.zeros([t, b, h, w, self.out_channels])

        # unroll the cell over time
        for i in range(t):
            h_t, c_t = self.cell(x[:, i, :, :, :], (h_t, c_t))
            hidden_states[i] = h_t

        # reshaping back to batch-first
        hidden_states = hidden_states.reshape([b, t, h, w, self.out_channels])

        return hidden_states
