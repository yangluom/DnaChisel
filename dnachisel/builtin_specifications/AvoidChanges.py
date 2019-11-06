"""Implementation of AvoidBlastMatches."""

import numpy as np

from ..Specification import Specification
from ..SpecEvaluation import SpecEvaluation

# from .VoidSpecification import VoidSpecification
from dnachisel.biotools import (
    sequences_differences_array,
    group_nearby_indices,
)
from dnachisel.Location import Location


class AvoidChanges(Specification):
    """Specify that some locations of the sequence should not be changed.

    Shorthand for annotations: "change".
    
    Parameters
    ----------
    location
      Location object indicating the position of the segment that must be
      left unchanged. Alternatively,
      indices can be provided. If neither is provided, the assumed location
      is the whole sequence.

    indices
      List of indices that must be left unchanged.

    target_sequence
      At the moment, this is rather an internal variable. Do not use unless
      you're not afraid of side effects.

    """

    localization_interval_length = 6  # used when optimizing the minimize_diffs
    best_possible_score = 0
    enforced_by_nucleotide_restrictions = True
    shorthand_name = "keep"

    def __init__(
        self, location=None, indices=None, target_sequence=None, boost=1.0
    ):

        """Initialize."""
        if location is None and (indices is not None):
            location = (min(indices), max(indices) + 1)
        if isinstance(location, tuple):
            location = Location.from_tuple(location)
        self.location = location
        if (self.location is not None) and self.location.strand == -1:
            self.location.strand = 1
        self.indices = np.array(indices) if (indices is not None) else None
        self.target_sequence = target_sequence
        # self.passive_objective = passive_objective
        self.boost = boost

    def extract_subsequence(self, sequence):
        """Extract a subsequence from the location or indices.

        Used to initialize the function when the sequence is provided.

        """
        if (self.location is None) and (self.indices is None):
            return sequence
        elif self.indices is not None:
            return "".join(np.array(list(sequence))[self.indices])
        else:  # self.location is not None:
            return self.location.extract_sequence(sequence)

    def initialized_on_problem(self, problem, role=None):
        """Find out what sequence it is that we are supposed to conserve."""
        result = self._copy_with_full_span_if_no_location(problem)

        # Initialize the "target_sequence" in two cases:
        # - Always at the very beginning
        # - When the new sequence is bigger than the previous one
        #   (used in CircularDnaOptimizationProblem)
        if self.target_sequence is None or (
            len(self.target_sequence) < len(self.location)
        ):
            result = result.copy_with_changes()
            result.target_sequence = self.extract_subsequence(problem.sequence)
        return result

    def evaluate(self, problem):
        """Return a score equal to -number_of modifications.

        Locations are "binned" modifications regions. Each bin has a length
        in nucleotides equal to ``localization_interval_length`.`
        """
        target = self.target_sequence
        sequence = self.extract_subsequence(problem.sequence)
        discrepancies = np.nonzero(
            sequences_differences_array(sequence, target)
        )[0]

        if self.indices is not None:
            discrepancies = self.indices[discrepancies]
        elif self.location is not None:
            if self.location.strand == -1:
                discrepancies = self.location.end - discrepancies
            else:
                discrepancies = discrepancies + self.location.start

        intervals = [
            (r[0], r[-1] + 1)
            for r in group_nearby_indices(
                discrepancies,
                max_group_spread=self.localization_interval_length,
            )
        ]
        locations = [Location(start, end, 1) for start, end in intervals]

        return SpecEvaluation(
            self, problem, score=-len(discrepancies), locations=locations
        )

    def localized(self, location, problem=None):
        """Localize the spec to the overlap of its location and the new.
        """
        start, end = location.start, location.end
        if self.indices is not None:
            pos = ((start <= self.indices) & (self.indices < end)).nonzero()[0]
            new_indices = self.indices[pos]
            new_target = "".join(np.array(list(self.target_sequence))[pos])
            return self.copy_with_changes(
                indices=new_indices, target_sequence=new_target
            )
        else:
            new_location = self.location.overlap_region(location)
            if new_location is None:
                return None
            else:
                new_constraint = self.copy_with_changes(location=new_location)
                relative_location = new_location + (-self.location.start)
                new_constraint.target_sequence = relative_location.extract_sequence(
                    self.target_sequence
                )
                return new_constraint

    def restrict_nucleotides(self, sequence, location=None):
        """When localizing, forbid any nucleotide but the one already there."""
        if location is not None:
            start = max(location.start, self.location.start)
            end = min(location.end, self.location.end)
        else:
            start, end = self.location.start, self.location.end

        if self.indices is not None:
            return [
                ((i, i + 1), set([sequence[i : i + 1]]))
                for i in self.indices
                if start <= i < end
            ]
        else:
            return [((start, end), set([sequence[start:end]]))]

    def short_label(self):
        return "keep"

