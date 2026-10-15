from typing import List, Optional

from pydantic import BaseModel
from pydantic import RootModel

class ClickPosition(BaseModel):
    x: int
    y: int

class Click(BaseModel):
    description: str
    target: Optional[str] = None
    optional: Optional[bool] = False
    position: Optional[ClickPosition] = None
    go_back: Optional[bool] = False
    wait_time: Optional[float] = None

class WebsiteConfig(BaseModel):
    site_name: str
    starting_url: str
    use_playwright: Optional[bool] = False
    jobs_cap: Optional[int] = -1
    layer_to_wait_for: Optional[str] = None
    job_item: str
    job_title: str
    job_company: str
    job_location: str
    job_post_date: str
    pagination: Optional[str] = None
    max_page: Optional[int] = -1
    job_group: Optional[str] = None
    job_url: Optional[str] = "a"
    click_each_job: Optional[bool] = False
    clicks_per_job_before_parsing: Optional[List[Click]] = None
    clicks_per_job_after_parsing: Optional[List[Click]] = None
    clicks: Optional[List[Click]] = None
    job_description: Optional[str] = None
    is_date_in_detail: Optional[bool] = False
    is_location_in_detail: Optional[bool] = False
    job_post_date_prefix: Optional[str] = ""
    job_post_date_suffix: Optional[str] = ""

class WebScrapingRules(RootModel[list[WebsiteConfig]]):
    pass