from pydantic import BaseModel, Field, field_validator
from .locations import normalize_location


class ReviewCreate(BaseModel):
    guest_name: str = Field(min_length=1, max_length=100)
    room_number: str = Field(min_length=1, max_length=20)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=5, max_length=3000)

    @field_validator('room_number')
    @classmethod
    def normalize_room(cls, value: str) -> str:
        room = normalize_location(value)
        if not room:
            raise ValueError('Укажите номер комнаты или место')
        return room


class ReviewOut(ReviewCreate):
    id: int

    class Config:
        from_attributes = True
