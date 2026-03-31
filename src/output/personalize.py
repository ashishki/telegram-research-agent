WATCH_THRESHOLD = 0.45
STRONG_THRESHOLD = 0.75
BOOST_MULTIPLIER = 1.3
DOWNRANK_MULTIPLIER = 0.5


def apply_personalization(posts: list[dict], profile: dict) -> list[dict]:
    boost_topics = [str(topic).lower() for topic in profile.get("boost_topics", [])]
    downrank_topics = [str(topic).lower() for topic in profile.get("downrank_topics", [])]
    personalized_posts: list[dict] = []

    for post in posts:
        content = str(post.get("content") or "").lower()
        signal_score = float(post.get("signal_score") or 0.0)
        personalized_score = signal_score

        if any(topic in content for topic in boost_topics):
            personalized_score = min(personalized_score * BOOST_MULTIPLIER, 1.0)
        if any(topic in content for topic in downrank_topics):
            personalized_score *= DOWNRANK_MULTIPLIER

        if (post.get("bucket") == "strong" or signal_score >= STRONG_THRESHOLD) and personalized_score < WATCH_THRESHOLD:
            personalized_score = WATCH_THRESHOLD

        personalized_posts.append(
            {
                **post,
                "personalized_score": personalized_score,
            }
        )

    return sorted(
        personalized_posts,
        key=lambda post: float(post.get("personalized_score") or 0.0),
        reverse=True,
    )
