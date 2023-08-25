"""
Basic interface for a reaction pathway solver.
"""
from abc import ABCMeta
from typing import List

from monty.json import MSONable

from rxn_network.reactions.base import Reaction


class Pathway(MSONable, metaclass=ABCMeta):
    """
    Base definition for a reaction pathway.
    """

    _reactions: List[Reaction]

    @property
    def entries(self):
        """Entry objects in this Pathway"""
        return {entry for rxn in self._reactions for entry in rxn.entries}

    @property
    def all_reactants(self):
        """Entries serving as a reactant in any sub reaction"""
        return {entry for rxn in self._reactions for entry in rxn.reactants}

    @property
    def all_products(self):
        """Entries serving as a product in any sub reaction"""
        return {entry for rxn in self._reactions for entry in rxn.products}

    @property
    def compositions(self):
        """Compositions in the reaction"""
        return list(self.all_reactants | self.all_products)

    @property
    def reactants(self):
        """The reactants of this whole reaction pathway"""
        return self.all_reactants - self.all_products

    @property
    def products(self):
        """The products of this whole reaction pathway"""
        return self.all_products - self.all_reactants

    @property
    def intermediates(self):
        """Intermediates as entries in this reaction pathway"""
        return self.all_products & self.all_reactants

    @property
    def energy(self):
        """Total energy of this reaction pathway"""
        return sum(rxn.energy for rxn in self._reactions)

    @property
    def energy_per_atom(self):
        """Total energy per atom of this reaction pathway"""
        return sum(rxn.energy_per_atom for rxn in self._reactions)


class Solver(MSONable, metaclass=ABCMeta):
    """
    Base definition for a pathway solver class.
    """

    def __init__(self, pathways):
        self._pathways = pathways

        rxns = []
        costs = []

        for path in self._pathways.get_paths():
            for rxn, cost in zip(path.reactions, path.costs):
                if rxn not in rxns:
                    rxns.append(rxn)
                    costs.append(cost)

        self._reactions = rxns
        self._costs = costs

    @property
    def pathways(self) -> List[Pathway]:
        """Pathways used in solver class"""
        return self._pathways

    @property
    def reactions(self) -> List[Reaction]:
        """Reactions used in solver class"""
        return self._reactions

    @property
    def costs(self) -> List[float]:
        """Costs used in solver class"""
        return self._costs

    @property
    def num_rxns(self) -> int:
        """Length of the reaction list"""
        return len(self.reactions)

    @property
    def num_entries(self) -> int:
        """Length of entry list"""
        return len(self._entries)