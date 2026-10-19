from typing import List, Optional

from pydantic import BaseModel

from pydantic import BaseModel

class DescriptionScoringRule(BaseModel):
    topic: str
    target_keywords: List[str]
    score_per_match: int
    score_cap: Optional[int] = None

class HiringRulesModel(BaseModel):
    title_instant_win_keywords: List[str]
    title_target_keywords: List[str]
    title_exclude_keywords: List[str]
    description_scoring_rules: List[DescriptionScoringRule]
    required_description_score: int
    require_remote: Optional[bool] = False
    insta_win_locations: List[str]
    locations: List[str]