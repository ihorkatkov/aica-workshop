"""Report observed business outcomes alongside the conversation judge's criteria."""

from scenario.types import CriterionResult


class Outcomes:
    def __init__(self):
        self.rows = []

    def record(self, criterion, passed, reason):
        status = "passed" if passed else "failed"
        self.rows.append(
            CriterionResult(
                criterion=criterion,
                requirement=criterion,
                status=status,
                reasoning=reason,
            )
        )
        return passed

    def unreached(self, criterion, reason):
        self.rows.append(
            CriterionResult(
                criterion=criterion,
                requirement=criterion,
                status="inconclusive",
                reasoning=f"Not reached: {reason}",
            )
        )

    def add_to(self, verdict):
        for row in self.rows:
            verdict.criteria.append(row)
            if row.status == "inconclusive":
                verdict.inconclusive_criteria.append(row.criterion)
            elif row.status == "passed":
                verdict.passed_criteria.append(row.criterion)
            else:
                verdict.failed_criteria.append(row.criterion)
                verdict.success = False
                verdict.reasoning = (
                    f"{verdict.reasoning or ''} {row.criterion}: {row.reasoning}"
                )
        return verdict
