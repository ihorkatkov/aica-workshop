"""Translate a failed business check into a LangWatch criterion."""

import scenario
from scenario.types import CriterionResult


def business_step(criterion, check):
    async def step(state):
        try:
            check()
        except AssertionError as error:
            reason = str(error).splitlines()[0]
            result = await scenario.fail(reason)(state)
            result.failed_criteria = [criterion]
            result.criteria.append(
                CriterionResult(
                    criterion=criterion,
                    requirement=criterion,
                    status="failed",
                    reasoning=reason,
                )
            )
            return result

    return step
