from pydantic import BaseModel


class DiscussionRequest(BaseModel):
    text: str