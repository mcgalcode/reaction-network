""" Tests for pathways/utils.py """
from pathlib import Path
import pytest
import numpy as np
from rxn_network.pathways.utils import balance_path_arrays


TEST_FILES_PATH = Path(__file__).parent.parent / "test_files"
ARRAY_FILE = "comp_matrices.npy"


@pytest.fixture(scope="module")
def comp_matrices():
    return np.load(str(TEST_FILES_PATH / ARRAY_FILE))


@pytest.fixture
def net_coeffs():
    return np.array([0.5, 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,
           0., 0., -1., 0., 0., 0., 0., 0., 0., 1., 0.,
           -1., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,
           0., 0., 0.])


@pytest.fixture()
def c_mats():
    arr = np.array([[[0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., -1., 0., 0.,
             0., 0., 0., 0.,
             1., 0., -1.6, 0.,
             0., 0., 0.2, 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.],
            [1., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., -1., 0., 0.,
             0., 0., 0., 0.,
             1., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., -1., 0., 0.],
            [0.5, 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., -1., 0.,
             0., 0., -1., 0.,
             0., 0., 0., 0.,
             0., 4., 0., 0.]],

           [[0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., -1., 0., 0.,
             0., 0., 0., 0.,
             1., 0., -1.6, 0.,
             0., 0., 0.2, 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.],
            [1., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., -0.90909091, 0., 0.,
             0., 0., 0., 0.,
             0.90909091, 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., -0.18181818,
             0., 0., 0., 0.],
            [0.1, 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., 0., 0.,
             0., 0., -1., 0.,
             0., 0., -1., 0.,
             0., 0., 0., 0.8,
             0., 0., 0., 0.]]])
    return arr


@pytest.fixture
def m_mats():
    arr = np.array([[0.55555556, 0.44444444, 0.11111111],
       [0.55555556, 0.48888889, 0.11111111]])

    return arr


def test_balance_path_arrays(comp_matrices, net_coeffs, c_mats, m_mats):
    c_mats_actual, m_mats_actual = balance_path_arrays(comp_matrices, net_coeffs,
                                                     tol=1e-6)
    assert np.allclose(c_mats, c_mats_actual)
    assert np.allclose(m_mats, m_mats_actual)
    