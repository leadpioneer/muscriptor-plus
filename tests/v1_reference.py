"""A minimal replica of the v1 solver's transition cost, kept as a test
reference only — it is not part of the product.

v1 modelled hand movement as `|Δfret| + w·|Δstring|` between neighbouring
notes, which is what let the "crawl up one string, frets 1→13" route look
cheap. v2 prices hand-position shifts instead; this reference exists so a
test can demonstrate the modelling change on identical inputs.
"""

from muscriptor.guitar_arrangement import FingeringState, FretPosition

_V1_FRETS_PER_STEP = 1.0
_V1_STRING_PER_STEP = 0.5


def v1_transition_cost(
    previous: FingeringState, following: FingeringState
) -> float:
    """The v1 cost: fret/string deltas of the notes, no hand state."""
    return _V1_FRETS_PER_STEP * abs(
        following.position.fret - previous.position.fret
    ) + _V1_STRING_PER_STEP * abs(
        following.position.string - previous.position.string
    )


def solve_phrase_v1(notes, candidate_positions) -> float:
    """Best total v1 cost for a phrase given string/fret candidate lists.

    `candidate_positions[i]` is a list of `(string, fret)` tuples for
    `notes[i]`. Returns the minimal total transition cost (v1 ignored
    per-note costs entirely).
    """
    states = [
        [
            FingeringState(
                position=FretPosition(string=string, fret=fret),
                hand_position=fret,
                finger=1,
            )
            for string, fret in options
        ]
        for options in candidate_positions
    ]
    costs = [0.0] * len(states[0])
    for i in range(1, len(states)):
        new_costs = []
        for state in states[i]:
            new_costs.append(
                min(
                    cost + v1_transition_cost(previous, state)
                    for cost, previous in zip(costs, states[i - 1])
                )
            )
        costs = new_costs
    return min(costs)
