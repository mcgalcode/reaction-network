"""
Implements an Entry that looks up NIST pre-tabulated Gibbs free energies
"""
import hashlib
from typing import Dict, Any, List

from pymatgen.core.composition import Composition
from pymatgen.entries import Entry
from scipy.interpolate import interp1d

from rxn_network.entries.experimental import ExperimentalReferenceEntry
from rxn_network.data import PATH_TO_NIST, load_experimental_data

G_COMPOUNDS = load_experimental_data(PATH_TO_NIST / "compounds.json")
G_GASES = load_experimental_data(PATH_TO_NIST / "gases.json")


class NISTReferenceEntry(ExperimentalReferenceEntry):
    """
    An Entry class for NIST-JANAF experimental reference data. Given a composition,
    automatically finds the Gibbs free energy of formation, dGf(T) from tabulated
    reference values (G_GASES, G_COMPOUNDS).

    Reference:
        Malcolm W. Chase Jr. NIST-JANAF thermochemical tables. Fourth edition.
        Washington, DC : American Chemical Society;  New York : American Institute of
        Physics for the National Institute of Standards and Technology, 1998.
    """

    REFERENCES = {**G_COMPOUNDS, **G_GASES}

    def __init__(self, composition: Composition, temperature: float):
        """
        Args:
            composition: Composition object (pymatgen).
            temperature: Temperature in Kelvin. If temperature is not selected from
                one of [300, 400, 500, ... 2000 K], then free energies will be
                interpolated. Defaults to 300 K.
        """
        super().__init__(composition, temperature)

    @classmethod
    def _validate_temperature(cls, formula, temperature: float) -> None:
        """ Ensure that the temperature is from a valid range. """
        if temperature < 300 or temperature > 2000:
            raise ValueError("Temperature must be selected from range: [300, 2000] K")
