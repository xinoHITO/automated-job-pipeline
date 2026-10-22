from typing import Optional

from pydantic import BaseModel, RootModel

class JobModel(BaseModel):    
    url:str
    source_site:str
    title:str
    company:str
    location:Optional[str]
    date_posted:Optional[str] = None
    description:Optional[str] = None
    
class Jobs(RootModel[list[JobModel]]):
    pass