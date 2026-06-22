from abc import ABC, abstractmethod
class ScoringEngine(ABC):
    @abstractmethod
    def evaluate(self, evaluation_context, scoring_config): ...

