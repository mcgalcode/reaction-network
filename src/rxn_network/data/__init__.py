"""
Experimental Gibbs free energy data from NIST-JANAF (compounds, gases) and FactSage (elements)
"""
from pathlib import Path

from monty.serialization import loadfn

cwd = Path(__file__).parent.resolve()

PATH_TO_BARIN = cwd / "barin"
PATH_TO_NIST = cwd / "nist"

G_ELEMS = loadfn(cwd / "elements.json")


def load_experimental_data(fn):
    """
    Load experimental data from a json file
    """
    d = loadfn(fn)
    return {comp: make_float_keys(data) for comp, data in d.items()}


def make_float_keys(d):
    """
    Convert all keys in a dict to floats
    """
    return {float(k): v for k, v in d.items()}