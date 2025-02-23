from datetime import datetime
import enum
import warnings

from typing import Any
from typing import Dict
from typing import NamedTuple
from typing import Optional

from optuna import exceptions
from optuna import logging
from optuna import type_checking

if type_checking.TYPE_CHECKING:
    from optuna.distributions import BaseDistribution  # NOQA


class TrialState(enum.Enum):
    """State of a :class:`~optuna.trial.Trial`.

    Attributes:
        RUNNING:
            The :class:`~optuna.trial.Trial` is running.
        COMPLETE:
            The :class:`~optuna.trial.Trial` has been finished without any error.
        PRUNED:
            The :class:`~optuna.trial.Trial` has been pruned with
            :class:`~optuna.exceptions.TrialPruned`.
        FAIL:
            The :class:`~optuna.trial.Trial` has failed due to an uncaught error.
    """

    RUNNING = 0
    COMPLETE = 1
    PRUNED = 2
    FAIL = 3

    def __repr__(self):
        # type: () -> str

        return str(self)

    def is_finished(self):
        # type: () -> bool

        return self != TrialState.RUNNING


class StudyDirection(enum.Enum):
    """Direction of a :class:`~optuna.study.Study`.

    Attributes:
        NOT_SET:
            Direction has not been set.
        MINIMIZE:
            :class:`~optuna.study.Study` minimizes the objective function.
        MAXIMIZE:
            :class:`~optuna.study.Study` maximizes the objective function.
    """

    NOT_SET = 0
    MINIMIZE = 1
    MAXIMIZE = 2


class FrozenTrial(object):
    """Status and results of a :class:`~optuna.trial.Trial`.

    Attributes:
        number:
            Unique and consecutive number of :class:`~optuna.trial.Trial` for each
            :class:`~optuna.study.Study`. Note that this field uses zero-based numbering.
        state:
            :class:`TrialState` of the :class:`~optuna.trial.Trial`.
        value:
            Objective value of the :class:`~optuna.trial.Trial`.
        datetime_start:
            Datetime where the :class:`~optuna.trial.Trial` started.
        datetime_complete:
            Datetime where the :class:`~optuna.trial.Trial` finished.
        params:
            Dictionary that contains suggested parameters.
        distributions:
            Dictionary that contains the distributions of :attr:`params`.
        user_attrs:
            Dictionary that contains the attributes of the :class:`~optuna.trial.Trial` set with
            :func:`optuna.trial.Trial.set_user_attr`.
        intermediate_values:
            Intermediate objective values set with :func:`optuna.trial.Trial.report`.
    """

    def __init__(
        self,
        number,  # type: int
        state,  # type: TrialState
        value,  # type: Optional[float]
        datetime_start,  # type: Optional[datetime]
        datetime_complete,  # type: Optional[datetime]
        params,  # type: Dict[str, Any]
        distributions,  # type: Dict[str, BaseDistribution]
        user_attrs,  # type: Dict[str, Any]
        system_attrs,  # type: Dict[str, Any]
        intermediate_values,  # type: Dict[int, float]
        trial_id,  # type: int
    ):
        # type: (...) -> None

        self.number = number
        self.state = state
        self.value = value
        self.datetime_start = datetime_start
        self.datetime_complete = datetime_complete
        self.params = params
        self.user_attrs = user_attrs
        self.system_attrs = system_attrs
        self.intermediate_values = intermediate_values
        self._distributions = distributions
        self._trial_id = trial_id

    # Ordered list of fields required for `__repr__`, `__hash__` and dataframe creation.
    # TODO(hvy): Remove this list in Python 3.6 as the order of `self.__dict__` is preserved.
    _ordered_fields = [
        'number', 'state', 'value', 'datetime_start', 'datetime_complete', 'params',
        '_distributions', 'user_attrs', 'system_attrs', 'intermediate_values', '_trial_id', ]

    def __eq__(self, other):
        # type: (Any) -> bool

        if isinstance(other, type(self)):
            return other.__dict__ == self.__dict__
        return False

    def __ne__(self, other):
        # type: (Any) -> bool

        return not self.__eq__(other)

    def __hash__(self):
        # type: () -> int

        return hash(tuple(getattr(self, field) for field in self._ordered_fields))

    def __repr__(self):
        # type: () -> str

        return ('{cls}({kwargs})'.format(
            cls=self.__class__.__name__,
            kwargs=', '.join('{field}={value}'.format(
                field=field if not field.startswith('_') else field[1:],
                value=repr(getattr(self, field))) for field in self._ordered_fields)))

    def _validate(self):
        # type: () -> None

        if self.datetime_start is None:
            raise ValueError('`datetime_start` is supposed to be set.')

        if self.state.is_finished():
            if self.datetime_complete is None:
                raise ValueError('`datetime_complete` is supposed to be set for a finished trial.')
        else:
            if self.datetime_complete is not None:
                raise ValueError(
                    '`datetime_complete` is supposed to not be set for a finished trial.')

        if self.state == TrialState.COMPLETE and self.value is None:
            raise ValueError('`value` is supposed to be set for a complete trial.')

        if set(self.params.keys()) != set(self.distributions.keys()):
            raise ValueError('Inconsistent parameters {} and distributions {}.'.format(
                set(self.params.keys()), set(self.distributions.keys())))

        for param_name, param_value in self.params.items():
            distribution = self.distributions[param_name]

            param_value_in_internal_repr = distribution.to_internal_repr(param_value)
            if not distribution._contains(param_value_in_internal_repr):
                raise ValueError(
                    "The value {} of parameter '{}' isn't contained in the distribution {}.".
                    format(param_value, param_name, distribution))

    @property
    def distributions(self):
        # type: () -> Dict[str, BaseDistribution]
        """Return the distributions for this trial.

        Returns:
            The distributions.
        """

        return self._distributions

    @distributions.setter
    def distributions(self, value):
        # type: (Dict[str, BaseDistribution]) -> None
        """Set the distributions for this trial.

        Args:
            value: The distributions.
        """

        self._distributions = value

    @property
    def trial_id(self):
        # type: () -> int
        """Return the trial ID.

        .. deprecated:: 0.19.0
            The direct use of this attribute is deprecated and it is recommended that you use
            :attr:`~optuna.trial.FrozenTrial.number` instead.

        Returns:
            The trial ID.
        """

        warnings.warn(
            'The use of `FrozenTrial.trial_id` is deprecated. '
            'Please use `FrozenTrial.number` instead.', DeprecationWarning)

        logger = logging._get_library_root_logger()
        logger.warning(
            'The use of `FrozenTrial.trial_id` is deprecated. '
            'Please use `FrozenTrial.number` instead.')

        return self._trial_id

    @property
    def last_step(self):
        # type: () -> Optional[int]

        if len(self.intermediate_values) == 0:
            return None
        else:
            return max(self.intermediate_values.keys())


class StudySummary(
        NamedTuple('StudySummary', [('study_id', int), ('study_name', str),
                                    ('direction', StudyDirection),
                                    ('best_trial', Optional[FrozenTrial]),
                                    ('user_attrs', Dict[str, Any]),
                                    ('system_attrs', Dict[str, Any]), ('n_trials', int),
                                    ('datetime_start', Optional[datetime])])):
    """Basic attributes and aggregated results of a :class:`~optuna.study.Study`.

    See also :func:`optuna.study.get_all_study_summaries`.

    Attributes:
        study_id:
            Identifier of the :class:`~optuna.study.Study`.
        study_name:
            Name of the :class:`~optuna.study.Study`.
        direction:
            :class:`StudyDirection` of the :class:`~optuna.study.Study`.
        best_trial:
            :class:`FrozenTrial` with best objective value in the :class:`~optuna.study.Study`.
        user_attrs:
            Dictionary that contains the attributes of the :class:`~optuna.study.Study` set with
            :func:`optuna.study.Study.set_user_attr`.
        system_attrs:
            Dictionary that contains the attributes of the :class:`~optuna.study.Study` internally
            set by Optuna.
        n_trials:
            The number of trials ran in the :class:`~optuna.study.Study`.
        datetime_start:
            Datetime where the :class:`~optuna.study.Study` started.
    """


class TrialPruned(exceptions.TrialPruned):
    """Exception for pruned trials.

    .. deprecated:: 0.19.0

        This class was moved to :mod:`~optuna.exceptions`. Please use
        :class:`~optuna.exceptions.TrialPruned` instead.

    This error tells a trainer that the current :class:`~optuna.trial.Trial` was pruned. It is
    supposed to be raised after :func:`optuna.trial.Trial.should_prune` as shown in the following
    example.

    Example:

        .. code::

            >>> def objective(trial):
            >>>     ...
            >>>     for step in range(n_train_iter):
            >>>         ...
            >>>         if trial.should_prune():
            >>>             raise TrailPruned()
    """

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None

        message = 'The use of `optuna.structs.TrialPruned` is deprecated. ' \
                  'Please use `optuna.exceptions.TrialPruned` instead.'
        warnings.warn(message, DeprecationWarning)
        logger = logging.get_logger(__name__)
        logger.warning(message)
