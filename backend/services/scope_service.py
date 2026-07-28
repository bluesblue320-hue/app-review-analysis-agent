"""Server-side review scope selection shared by API workflows."""

from __future__ import annotations

import pandas as pd

from backend.schemas.analytics import ReviewFilters
from backend.services.dataset_service import InMemoryDatasetStore
from visual_analysis import filter_reviews


class ReviewScopeService:
    def __init__(self, store: InMemoryDatasetStore) -> None:
        self._store = store

    def get_dataframe(
        self,
        dataset_id: str,
        filters: ReviewFilters,
        *,
        full_dataset: bool = False,
    ) -> pd.DataFrame:
        dataframe = self._store.get(dataset_id).dataframe
        if full_dataset:
            return dataframe.copy(deep=True)
        return self.apply_filters(dataframe, filters)

    @staticmethod
    def apply_filters(
        dataframe: pd.DataFrame,
        filters: ReviewFilters,
    ) -> pd.DataFrame:
        return filter_reviews(
            dataframe,
            rating_range=(filters.rating_min, filters.rating_max),
            sentiment_range=(filters.sentiment_min, filters.sentiment_max),
            categories=filters.categories or None,
            keyword=filters.keyword,
            high_risk_only=filters.high_risk_only,
        )
