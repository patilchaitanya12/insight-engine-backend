from difflib import SequenceMatcher


def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def search_similar_query(db, dataset_id, question, user_id: str):

    history = await db.query_history.find(
        {"dataset_id": dataset_id, "user_id": user_id}
    ).to_list(50)

    best_match = None
    best_score = 0

    for item in history:

        score = similarity(question, item["question"])

        if score > best_score:
            best_score = score
            best_match = item

    if best_score > 0.85:
        return best_match

    return None