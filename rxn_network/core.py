import logging
from itertools import combinations, chain

import numpy as np
from scipy.constants import physical_constants

import networkx as nx

from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.analysis.reaction_calculator import ComputedReaction

from rxn_network.helpers import RxnEntries, RxnPathway, CombinedPathway, GibbsComputedStructureEntry


__author__ = "Matthew McDermott"
__email__ = "mcdermott@lbl.gov"


class ReactionNetwork:
    """
    This class creates and stores a weighted, directed graph (implemented in NetworkX) which enumerates and
        explores all possible chemical reactions (edges) between reactant/product combinations (nodes) in a
        chemical system.
    """
    def __init__(self, entries, max_num_components=2, include_metastable=False, include_polymorphs=False,
                    use_g_sisso = True):
        """
        Constructs a ReactionNetwork object with necessary initialization steps
        (but does not generate the actual network).

        Args:
            entries ([ComputedEntry]): list of ComputedEntry objects to consider in network
            max_num_components (int): maximum number of components allowed on each side of the reaction (default 2)
            include_metastable (float or bool): either the specified cutoff for energy above hull, or False if
                considering only stable entries
            include_polymorphs (bool): Whether or not to consider non-ground state polymorphs (defaults to False)
            use_g_sisso (bool): Whether or not to use Gibbs Free Energy descriptor from Bartel et al. (2018)
        """
        self._all_entries = entries
        self._pd = PhaseDiagram(entries)
        self._max_num_components = max_num_components
        self._e_above_hull = include_metastable
        self._include_polymorphs = include_polymorphs
        self._use_g_sisso = use_g_sisso

        self._starters = None
        self._all_targets = None
        self._selected_target = None
        self._cost_function = None
        self._complex_loopback = None
        self._most_negative_rxn = float("inf")  # used for shifting reaction energies in some cost functions

        self._rxn_network = None

        self.logger = logging.getLogger('ReactionNetwork')
        self.logger.setLevel("INFO")

        self._filtered_entries = self.filter_entries(self._pd, include_metastable, include_polymorphs)

        filtered_entries_str = ', '.join([entry.composition.reduced_formula for entry in self._filtered_entries])

        self.logger.info(
            f"Building network with {len(self._filtered_entries)} entries: \n{filtered_entries_str}")

        self._all_combos = self.generate_all_combos(self._filtered_entries, max_num_components)
        self.logger.info(f"Found {len(self._all_combos)} combinations of entries (size <= {self._max_num_components}).")

    def generate_rxn_network(self, starters, targets, cost_function="softplus", complex_loopback = True):
        """
        Generates the actual reaction network (weighted, directed graph) using Networkx.

        Args:
            starters (list of ComputedEntries): entries for all phases which serve as the main reactants
            targets (list of ComputedEntries): entries for all phases which are the final products
            cost_function (str): name of cost function to use for entire network (e.g. "softplus")
            loopback (bool): whether or not to add edges looping back to
                combinations of intermediates and initial reactants

        Returns:
            None
        """
        self._starters = starters
        self._all_targets = targets
        self._selected_target = [targets[0]]  # take first entry to be first designated target
        self._cost_function = cost_function
        self._complex_loopback = complex_loopback
        self._most_negative_rxn = float("inf")  # used for shifting reaction energies in some cost functions

        if False in [isinstance(starter, ComputedEntry) for starter in starters] or False in [
                isinstance(target, ComputedEntry) for target in targets]:
            raise TypeError("Starters and target must be ComputedEntries.")

        g = nx.DiGraph()

        starters = set(self._starters)
        target = set(self._selected_target)

        starter_entries = RxnEntries(starters, "s")
        target_entry = RxnEntries(target, "t")

        g.add_nodes_from([starter_entries, target_entry])

        self.logger.info("Generating reactions...")

        for reactants in self._all_combos:
            reactant_entries = RxnEntries(reactants, "r")
            g.add_node(reactant_entries)

            if reactants.issubset(starters):
                g.add_edge(starter_entries, reactant_entries, weight=0)

        for products in self._all_combos:
            product_entries = RxnEntries(products, "p")
            g.add_node(product_entries)

            if complex_loopback:
                linking_combos = self.generate_all_combos(list(products.union(starters)), self._max_num_components)

                for combo in linking_combos:
                    g.add_edge(product_entries, RxnEntries(combo, "r"), weight=0)
            else:
                g.add_edge(product_entries, RxnEntries(products, "r"), weight=0)

            if target.issubset(products):
                g.add_edge(product_entries, target_entry, weight=0)  # add edge connecting to target

            for reactants in self._all_combos:
                if products == reactants:
                    continue  # removes many identity-like reactions

                reactants_elems = set([elem for entry in reactants for elem in entry.composition.elements])
                products_elems = set([elem for entry in products for elem in entry.composition.elements])

                if reactants_elems != products_elems:
                    continue  # removes reactions which change chemical systems

                reactant_entries = RxnEntries(reactants, "r")

                try:
                    rxn = ComputedReaction(list(reactants), list(products))
                    reactants_comps = {reactant.composition.reduced_composition for reactant in reactants}
                    products_comps = {product.composition.reduced_composition for product in products}

                    if (True in (abs(rxn.coeffs) < rxn.TOLERANCE)) or (reactants_comps != set(rxn.reactants)) or (
                            products_comps != set(rxn.products)):
                        continue  # removes reactions which have components that either change sides or disappear
                except:
                    continue

                total_num_atoms = sum([rxn.get_el_amount(elem) for elem in rxn.elements])
                dg_per_atom = rxn.calculated_reaction_energy / total_num_atoms

                weight = self.determine_rxn_weight(dg_per_atom, cost_function)
                g.add_edge(reactant_entries, product_entries, weight=weight, rxn=rxn)

        self.logger.info(f"Complete: Created graph with {g.number_of_nodes()} nodes and {g.number_of_edges()} edges.")

        if cost_function == "enthalpies_positive":
            self.logger.info(f"Adjusting enthalpies up by {-round(self._most_negative_rxn, 3)} eV")
            # shift all energies to be on a positive scale
            for (u, v, rxn) in g.edges.data(data='rxn'):
                if rxn is not None:
                    g[u][v]["weight"] -= self._most_negative_rxn

        elif cost_function == "bipartite":
            self.logger.info(f"Adjusting enthalpies using {-round(self._most_negative_rxn, 3)} eV")
            # shift all exothermic energies to be on a positive scale between 0-1
            for (u, v, rxn) in g.edges.data(data='rxn'):
                if rxn is not None and (g[u][v]["weight"] < 0):
                    g[u][v]["weight"] = 1 - (g[u][v]["weight"] / self._most_negative_rxn)

        self._rxn_network = g

    def find_k_shortest_paths(self, k, target=None):
        """
        Finds k shortest paths to designated target using Yen's Algorithm (as defined in Networkx)

        Args:
            k (int): desired number of shortest pathways (ranked by cost)

        Returns:
            [RxnPathway]: list of RxnPathway objects
        """
        starters = RxnEntries(set(self._starters), "s")

        if target is None:
            target = set(self._selected_target)

        target = RxnEntries(target, "t")

        paths = []
        num_found = 0

        for path in nx.shortest_simple_paths(self._rxn_network, starters, target, weight="weight"):
            if num_found == k:
                break

            path_reactants = None
            path_products = None
            rxns = []
            weights = []

            for step in path:
                if step.description == "Reactants":
                    path_reactants = step
                elif step.description == "Products":
                    path_products = step
                    rxn_data = self._rxn_network.get_edge_data(path_reactants, path_products)
                    rxn = rxn_data["rxn"]
                    weight = rxn_data["weight"]

                    rxns.append(rxn)
                    weights.append(weight)

            rxn_pathway = RxnPathway(rxns, weights)
            paths.append(rxn_pathway)
            print(rxn_pathway)
            print("\n")

            num_found += 1

        return paths

    def find_best_starters(self):
        """
        Finds shortest path to target for every possible combination of starters.

        Args:

        Returns:
        """
        paths_from_all_starters = set()
        filtered_entries = self._filtered_entries.copy()
        filtered_entries.remove(self._selected_target[0])
        all_possible_starters = self.generate_all_combos(filtered_entries, self._max_num_components)

        for starters in all_possible_starters:
            try:
                print(f"PATHS from {[starter.composition.reduced_formula for starter in starters]} \n")
                self.set_starters(list(starters))
                paths_from_all_starters.update(self.find_k_shortest_paths(5))
            except:
                continue

        return sorted(paths_from_all_starters, key=lambda path: path.total_weight)

    def find_combined_paths(self, k, targets=None, max_num_combos=3):
        """
        Builds k shortest paths to provided targets and then seeks to combine them to achieve a "net reaction"
            with balanced stoichiometry. In other words, the full conversion of all intermediates to final products.

        Args:
            k (int): calculated free energy of reaction
            targets ([ComputedEntries]): list of all target ComputedEntry objects
            max_num_combos (int): upper limit on how many pathways to consider at a time (default 3).

        Returns:
            [CombinedPathway]: list of CombinedPathway objects, sorted by average cost
        """
        paths_to_all_targets = []

        if targets is None:
            targets = self._all_targets
        for target in targets:
            print(f"PATHS to {target.composition.reduced_formula} \n")
            self.set_target([target])
            paths_to_all_targets.extend(self.find_k_shortest_paths(k))

        balanced_total_paths = []
        for combo in self.generate_all_combos(paths_to_all_targets, max_num_combos):
            combined_pathway = CombinedPathway(combo, targets)

            if combined_pathway.net_rxn:
                reactants_set = set(combined_pathway.net_rxn._reactant_entries)
                products_set = set(combined_pathway.net_rxn._product_entries)

                common_entries = reactants_set.intersection(products_set)
                reactants_set = reactants_set - common_entries
                products_set = products_set - common_entries

                if (set(targets).issubset(products_set)) and (set(self._starters) == reactants_set):
                    balanced_total_paths.append(combined_pathway)

                leftover_products = products_set - set(targets)

                leftover_rxns = set()

                for leftover_reactants in chain.from_iterable(
                        [combinations(leftover_products, num) for num in range(1, len(leftover_products) + 1)]):
                    for target_combos in chain.from_iterable(
                            [combinations(targets, num) for num in range(1, len(targets) + 1)]):
                        try:
                            leftover_rxns.add(ComputedReaction(list(leftover_reactants), list(target_combos)))
                        except:
                            continue

                for leftover_rxn in leftover_rxns:
                    leftover_path = RxnPathway([leftover_rxn], [0])
                    all_paths = combined_pathway.paths.copy()
                    all_paths.append(leftover_path)

                    appended_combined_path = CombinedPathway(all_paths, targets)
                    print(appended_combined_path)

                    if appended_combined_path.net_rxn:
                        balanced_total_paths.append(combined_pathway)

        return sorted(balanced_total_paths, key=lambda combined_path: combined_path.average_weight)

    def determine_rxn_weight(self, energy, cost_function):
        """
        Helper method which determines reaction cost/weight.

        Args:
            energy (float): calculated free energy of reaction
            cost_function (str): name of cost function (e.g. "softplus")

        Returns:
            float: cost/weight of individual reaction edge
        """
        if cost_function == "softplus":
            weight = self._softplus(energy, t=500)
        elif cost_function == "bipartite":
            weight = energy
            if weight < self._most_negative_rxn:
                self._most_negative_rxn = weight
            if weight >= 0:
                weight = 2 * weight + 1
        elif cost_function == "rectified":
            weight = energy
            if weight < 0:
                weight = 0
        elif cost_function == "arrhenius":
            weight = self._arrhenius(energy, t=100)
        elif cost_function == "enthalpies_positive":
            weight = energy
            if weight < self._most_negative_rxn:
                self._most_negative_rxn = weight
        else:
            weight = 0

        return weight

    def set_cost_function(self, cost_function):
        """
        Replaces network's current cost function with provided new function by recomputing edge weights.

        Args:
            cost_function (str): name of cost function (e.g. "softplus")

        Returns:
            None
        """
        for (u, v, rxn) in self._rxn_network.edges.data(data='rxn'):
            if rxn is not None:
                total_num_atoms = sum([rxn.get_el_amount(elem) for elem in rxn.elements])
                dg_per_atom = rxn.calculated_reaction_energy / total_num_atoms

                weight = self.determine_rxn_weight(dg_per_atom, cost_function)
                self._rxn_network[u][v]["weight"] = weight

    def set_starters(self, starters):
        """
        Replaces network's previous starter nodes with provided new starters.
            Recreates edges that link products back to reactants.

        Args:
            starters ([ComputedEntry]): list of new starter entries

        Returns:
            None
        """

        for node in self._rxn_network.nodes():
            if node.description == "Starters":
                self._rxn_network.remove_node(node)

                starters = set(starters)
                starter_entries = RxnEntries(starters, "s")

                self._rxn_network.add_node(starter_entries)

                for reactants in self._all_combos:
                    if reactants.issubset(starters):  # link starting node to reactant nodes
                        reactant_entries = RxnEntries(reactants, "r")
                        self._rxn_network.add_edge(starter_entries, reactant_entries, weight=0)
                break

        if not self._complex_loopback:
            self._starters = starters
            return

        for products in self._all_combos:
            product_entries = RxnEntries(products, "p")

            old_loopbacks = self.generate_all_combos(list(products.union(self._starters)), self._max_num_components)
            for combo in old_loopbacks:
                # delete old edge linking back
                self._rxn_network.remove_edge(product_entries, RxnEntries(combo, "r"))

            new_loopbacks = self.generate_all_combos(list(products.union(starters)), self._max_num_components)
            for combo in new_loopbacks:
                # add new edges linking back
                self._rxn_network.add_edge(product_entries, RxnEntries(combo, "r"), weight=0)

        self._starters = starters

    def set_target(self, target):
        """
        Replaces network's previous target node with provided new target.

        Args:
            target (ComputedEntry): entry of new target

        Returns:
            None
        """
        if target in self._selected_target:
            return

        target = [target]

        self._selected_target = target

        for node in self._rxn_network.nodes():
            if node.description == "Target":
                self._rxn_network.remove_node(node)

                target = set(target)
                target_entry = RxnEntries(target, "t")

                for products in self._all_combos:
                    if target.issubset(products):
                        product_entries = RxnEntries(products, "p")
                        self._rxn_network.add_edge(product_entries, target_entry, weight=0) # link product node to target node

                break


    @staticmethod
    def filter_entries(pd, e_above_hull, include_polymorphs):
        """
        Helper method for filtering entries by specified energy above hull

        Args:
            e_above_hull (float): cutoff for energy above hull (** eV **)

        Returns:
            list: all entries less than or equal to specified energy above hull
        """

        if e_above_hull == 0:
            filtered_entries = list(pd.stable_entries)
        else:
            if include_polymorphs:
                filtered_entries = [entry for entry in pd.all_entries if
                                    pd.get_e_above_hull(entry) <= e_above_hull]
            else:
                stable_compositions = [entry.composition.reduced_composition for entry in pd.stable_entries]
                filtered_entries = list(pd.stable_entries)
                filtered_entries.extend([entry for entry in pd.all_entries if pd.get_e_above_hull(entry)
                                         <= e_above_hull and entry.composition.reduced_composition
                                         not in stable_compositions])

        return filtered_entries

    @staticmethod
    def generate_all_combos(entries, max_num_combos):
        """
        Static helper method for generating combination sets ranging from singular length to maximum length
            specified by max_num_combos.

        Args:
            entries (list): list of all entry objects to combine
            max_num_combos (int): upper limit for size of combinations of entries

        Returns:
            list: all combination sets
        """

        all_combos = [set(combo) for combo in chain.from_iterable(
            [combinations(entries, num_combos) for num_combos in range(1, max_num_combos + 1)])]
        return all_combos

    @staticmethod
    def _arrhenius(energy, t):
        ''' Simple Arrenhius relation involving energy and temperature '''
        kb = physical_constants["Boltzmann constant in eV/K"][0]
        return np.exp(energy / (kb * t))

    @staticmethod
    def _softplus(energy, t=1.0):
        return np.log(1 + (273 / t) * np.exp(energy))

    @property
    def all_entries(self):
        return self._all_entries

    @property
    def filtered_entries(self):
        return self._filtered_entries

    @property
    def rxn_network(self):
        return self._rxn_network

    def __repr__(self):
        return str(self._rxn_network)
