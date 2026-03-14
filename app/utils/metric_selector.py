from difflib import SequenceMatcher

def select_best_metric(question: str, metrics: list[str]):

    question = question.lower()

    best_metric = None
    best_score = 0

    for metric in metrics:

        score = SequenceMatcher(
            None,
            question,
            metric.lower()
        ).ratio()

        if score > best_score:
            best_score = score
            best_metric = metric

    return best_metric
