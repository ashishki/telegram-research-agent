import logging
import os
import sqlite3
from datetime import datetime, timedelta

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score

from config.settings import Settings


LOGGER = logging.getLogger(__name__)
DEFAULT_CLUSTER_K = 8
MIN_CLUSTER_K = 2
MIN_POST_COUNT = 10
MAX_FEATURES = 500
TOP_KEYWORD_COUNT = 10
ENGLISH_STOPWORDS = list(ENGLISH_STOP_WORDS)
RUSSIAN_STOPWORDS = [
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она",
    "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее",
    "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда",
    "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до",
    "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем",
    "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет",
    "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь",
    "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем",
    "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть", "после",
    "над", "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много",
    "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда",
    "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю",
    "между",
]


def _utc_now() -> datetime:
    return datetime.utcnow()


def _get_cluster_k(total_posts: int) -> int:
    raw_value = os.environ.get("CLUSTER_K", str(DEFAULT_CLUSTER_K))
    try:
        configured_k = int(raw_value)
    except ValueError:
        LOGGER.warning("Invalid CLUSTER_K=%r; falling back to %d", raw_value, DEFAULT_CLUSTER_K)
        configured_k = DEFAULT_CLUSTER_K

    cluster_k = max(MIN_CLUSTER_K, configured_k)
    return min(cluster_k, total_posts)


def _fetch_recent_posts(
    connection: sqlite3.Connection,
    since_days: int,
) -> list[sqlite3.Row]:
    cutoff = (_utc_now() - timedelta(days=since_days)).isoformat() + "Z"
    cursor = connection.execute(
        """
        SELECT id, content
        FROM posts
        WHERE posted_at >= ?
        ORDER BY posted_at ASC, id ASC
        """,
        (cutoff,),
    )
    return cursor.fetchall()


def cluster_posts(settings: Settings, since_days: int = 30) -> list[dict]:
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = _fetch_recent_posts(connection, since_days)

    total_posts = len(rows)
    if total_posts < MIN_POST_COUNT:
        LOGGER.info(
            "Skipping clustering: not enough posts in the last %d days (count=%d)",
            since_days,
            total_posts,
        )
        return []

    post_ids = [row["id"] for row in rows]
    documents = [row["content"] or "" for row in rows]
    cluster_k = _get_cluster_k(total_posts)

    LOGGER.info(
        "Clustering %d posts from the last %d days with k=%d",
        total_posts,
        since_days,
        cluster_k,
    )

    vectorizer = TfidfVectorizer(
        max_features=MAX_FEATURES,
        stop_words=ENGLISH_STOPWORDS + RUSSIAN_STOPWORDS,
        token_pattern=r"(?u)\b\w+\b",
    )
    try:
        matrix = vectorizer.fit_transform(documents)
    except ValueError:
        LOGGER.info("Skipping clustering: TF-IDF could not build a vocabulary from recent posts")
        return []
    if matrix.shape[1] == 0:
        LOGGER.info("Skipping clustering: TF-IDF produced no usable features")
        return []

    model = KMeans(n_clusters=cluster_k, n_init=10, random_state=42)
    labels = model.fit_predict(matrix)
    inertia = float(model.inertia_)
    try:
        sil_score: float | None = float(silhouette_score(matrix, labels))
    except Exception:
        sil_score = None
        LOGGER.warning("Failed to compute silhouette score", exc_info=True)
    feature_names = np.asarray(vectorizer.get_feature_names_out())

    clusters: list[dict] = []
    unlabeled_count = 0
    for cluster_id in range(cluster_k):
        cluster_indexes = np.where(labels == cluster_id)[0]
        if cluster_indexes.size == 0:
            LOGGER.debug("Skipping empty cluster_id=%d", cluster_id)
            continue

        cluster_post_ids = [post_ids[index] for index in cluster_indexes.tolist()]
        mean_weights = matrix[cluster_indexes].mean(axis=0).A1
        top_indexes = np.argsort(mean_weights)[::-1][:TOP_KEYWORD_COUNT]
        top_keywords = [feature_names[index] for index in top_indexes if mean_weights[index] > 0]
        if not top_keywords:
            unlabeled_count += len(cluster_post_ids)

        clusters.append(
            {
                "cluster_id": cluster_id,
                "post_ids": cluster_post_ids,
                "top_keywords": top_keywords,
            }
        )

    LOGGER.info(
        "Clustering complete unlabeled_ratio=%.2f unlabeled=%d total=%d",
        unlabeled_count / total_posts,
        unlabeled_count,
        total_posts,
    )
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                "INSERT INTO cluster_runs (run_at, post_count, cluster_count, unlabeled_count, inertia, silhouette_score) VALUES (?, ?, ?, ?, ?, ?)",
                (_utc_now().isoformat() + "Z", total_posts, len(clusters), unlabeled_count, inertia, sil_score),
            )
            conn.commit()
    except Exception:
        LOGGER.warning("Failed to persist cluster run diagnostics", exc_info=True)
    LOGGER.info("Generated %d non-empty clusters", len(clusters))
    return clusters
