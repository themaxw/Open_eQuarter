# OeQ autogenerated correlation for 'Window/Wall Ratio North in Correlation to the Building Age'

import math
import numpy as np
from . import oeqCorrelation as oeq
def get(*xin):

    # OeQ autogenerated correlation for 'Window to Wall Ratio in Northern Direction'
    A_WIN_N_BY_AW= oeq.correlation(
    const= 13935.4897429,
    a=     -28.9315780487,
    b=     0.0225109615696,
    c=     -7.77964739498e-06,
    d=     1.00756447248e-09,
    mode= "lin")

    return dict(A_WIN_N_BY_AW=A_WIN_N_BY_AW.lookup(*xin))
