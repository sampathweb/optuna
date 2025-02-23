import math
import numpy as np
import six

from optuna.pruners import BasePruner
from optuna import structs
from optuna import type_checking

if type_checking.TYPE_CHECKING:
    from typing import Iterator  # NOQA
    from typing import List  # NOQA

    from optuna.study import Study  # NOQA


def _get_best_intermediate_result_over_steps(trial, direction):
    # type: (structs.FrozenTrial, structs.StudyDirection) -> float

    values = np.array(list(trial.intermediate_values.values()), np.float)
    if direction == structs.StudyDirection.MAXIMIZE:
        return np.nanmax(values)
    return np.nanmin(values)


def _get_percentile_intermediate_result_over_trials(all_trials, direction, step, percentile):
    # type: (List[structs.FrozenTrial], structs.StudyDirection, int, float) -> float

    completed_trials = [t for t in all_trials if t.state == structs.TrialState.COMPLETE]

    if len(completed_trials) == 0:
        raise ValueError("No trials have been completed.")

    if direction == structs.StudyDirection.MAXIMIZE:
        percentile = 100 - percentile

    return float(
        np.nanpercentile(
            np.array([
                t.intermediate_values[step]
                for t in completed_trials if step in t.intermediate_values
            ], np.float),
            percentile))


def _is_first_in_interval_step(step, intermediate_steps, n_warmup_steps, interval_steps):
    # type: (int, Iterator[int], int, int) -> bool

    nearest_lower_pruning_step = (
        (step - n_warmup_steps - 1) // interval_steps * interval_steps + n_warmup_steps + 1)
    assert nearest_lower_pruning_step >= 0

    # `intermediate_steps` may not be sorted so we must go through all elements.
    second_last_step = six.moves.reduce(
        lambda second_last_step, s: s if s > second_last_step and s != step
        else second_last_step, intermediate_steps, -1)

    return second_last_step < nearest_lower_pruning_step


class PercentilePruner(BasePruner):
    """Pruner to keep the specified percentile of the trials.

    Prune if the best intermediate value is in the bottom percentile among trials at the same step.

    Example:

        .. code::

            >>> from optuna import create_study
            >>> from optuna.pruners import PercentilePruner
            >>>
            >>> def objective(trial):
            >>>     ...
            >>>
            >>> study = create_study(pruner=PercentilePruner(25.0))
            >>> study.optimize(objective)

    Args:
        percentile:
            Percentile which must be between 0 and 100 inclusive
            (e.g., When given 25.0, top of 25th percentile trials are kept).
        n_startup_trials:
            Pruning is disabled until the given number of trials finish in the same study.
        n_warmup_steps:
            Pruning is disabled until the trial reaches the given number of step.
        interval_steps:
            Interval in number of steps between the pruning checks, offset by the warmup steps.
            If no value has been reported at the time of a pruning check, that particular check
            will be postponed until a value is reported. Value must be at least 1.
    """

    def __init__(self, percentile, n_startup_trials=5, n_warmup_steps=0, interval_steps=1):
        # type: (float, int, int, int) -> None

        if not 0.0 <= percentile <= 100:
            raise ValueError(
                'Percentile must be between 0 and 100 inclusive but got {}.'.format(percentile))
        if n_startup_trials < 0:
            raise ValueError(
                'Number of startup trials cannot be negative but got {}.'.format(n_startup_trials))
        if n_warmup_steps < 0:
            raise ValueError(
                'Number of warmup steps cannot be negative but got {}.'.format(n_warmup_steps))
        if interval_steps < 1:
            raise ValueError(
                'Pruning interval steps must be at least 1 but got {}.'.format(interval_steps))

        self.percentile = percentile
        self.n_startup_trials = n_startup_trials
        self.n_warmup_steps = n_warmup_steps
        self.interval_steps = interval_steps

    def prune(self, study, trial):
        # type: (Study, structs.FrozenTrial) -> bool
        """Please consult the documentation for :func:`BasePruner.prune`."""

        all_trials = study.trials
        n_trials = len([t for t in all_trials
                        if t.state == structs.TrialState.COMPLETE])

        if n_trials == 0:
            return False

        if n_trials < self.n_startup_trials:
            return False

        step = trial.last_step
        if step is None:
            return False

        n_warmup_steps = self.n_warmup_steps
        if step <= n_warmup_steps:
            return False

        if not _is_first_in_interval_step(
                step, six.iterkeys(trial.intermediate_values), n_warmup_steps,
                self.interval_steps):
            return False

        direction = study.direction
        best_intermediate_result = _get_best_intermediate_result_over_steps(trial, direction)
        if math.isnan(best_intermediate_result):
            return True

        p = _get_percentile_intermediate_result_over_trials(
            all_trials, direction, step, self.percentile)
        if math.isnan(p):
            return False

        if direction == structs.StudyDirection.MAXIMIZE:
            return best_intermediate_result < p
        return best_intermediate_result > p
