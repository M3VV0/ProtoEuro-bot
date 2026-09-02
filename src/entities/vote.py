from dataclasses import dataclass

@dataclass
class Vote:
    user_id: int
    country_name: str
    p_12: str
    p_10: str 
    p_8: str
    p_7: str
    p_6: str 
    p_5: str
    p_4: str
    p_3: str 
    p_2: str
    p_1: str

def get_points(vote: Vote) -> dict[str, int]:
    return {
        vote.p_12: 12, 
        vote.p_10: 10,
        vote.p_8: 8,
        vote.p_7: 7,
        vote.p_6: 6,
        vote.p_5: 5,
        vote.p_4: 4,
        vote.p_3: 3,
        vote.p_2: 2,
        vote.p_1: 1,
        }
    
    
